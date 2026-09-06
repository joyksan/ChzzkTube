##### target_downloader.py - 개별 URL 다운로드 / 대상 평탄화
"""DownloadWorker 의 다운로드 실행부 분할 모듈.

- expand_targets : 재생목록/채널 URL 을 개별 동영상 URL 로 평탄화
- download_target : 개별 URL 을 타입별로 분기해 실제 다운로드
  chzzk(clip/vod) → 직접 HTTP 스트림, youtube VOD → yt-dlp,
  youtube live → _download_youtube_live(ffmpeg), stream → streamlink
"""
import functools
import os
import re

import yt_dlp

from chzzk_api import analyze_chzzk_clip_api, analyze_chzzk_vod_api
from log_console import format_target_url
from utils import get_filename_template
from dl_platform import detect_content_type
from client_opts import _apply_client_opts, _apply_cookie_opts, _apply_ejs_opts, _apply_ffmpeg_opts, _apply_pot_opts
from progress_emitter import emit_err
import progress_emitter as _pe
import live_recorder as _lr


def _make_ytdl_opts(worker, fmt, url):
    """yt-dlp 다운로드 옵션 — outtmpl/훅/병합/쿠키/player_client 주입."""
    opts = {
        "logger": worker.logger,
        "noplaylist": True,
        # [Thin Wrapper 제거 후속] progress hook은 모듈 함수(worker 선결 바인딩)
        "progress_hooks": [functools.partial(_pe.hook, worker)],
        "outtmpl": os.path.join(
            worker.cfg.get("download_path") or ".",
            get_filename_template(worker.cfg),
        ),
        "format": fmt,
        "merge_output_format": worker.cfg.get("container", "mp4"),
        "retries": 3,
        "socket_timeout": 30,
        # [0% 스톨 픽스] PO 토큰 불일치 시 googlevideo가 "묵살 스로틀"
        # (연결 수락 + 데이터 거의 안 보냄) → speed < 100KB/s 3초 지속되면
        # yt-dlp가 ThrottledDownload raise → 재추출+재시도.
        # [주의] dest가 throttledratelimit (camelCase 아님, yt-dlp 옵션 표준)
        "throttledratelimit": 100_000,
    }
    if worker.cfg.get("fast_download"):
        opts["concurrent_fragment_downloads"] = 4
    _apply_cookie_opts(opts, worker.cfg)
    _apply_client_opts(opts, worker.cfg, forced=worker.yt_client)
    _apply_ejs_opts(opts)
    _apply_pot_opts(opts, _extract_yt_id(url),
                    client=(worker.yt_client if worker.yt_client != "auto" else "web_embedded"))
    _apply_ffmpeg_opts(opts)
    return opts


def _extract_yt_id(url):
    """YouTube URL에서 video ID 추출 (PO 토큰 content_binding용)."""
    import pot_provider
    return pot_provider.extract_video_id(url)


def _format_selector(worker):
    """yt-dlp format 선택 문자열 — UI 단순화(auto 등)에 대응."""
    if worker.cfg.get("audio_only"):
        return "bestaudio/best"
    return "bv*+ba/b"  # 기본 최고 품질 (명시/통합 동일)


def _http_download(worker, url, out_path):
    """치지직 progressive MP4 직접 스트림 다운로드 + 진행률 틱."""
    import urllib.request

    worker._speed_win.reset()
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as resp, open(out_path, "wb") as f:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = resp.read(262144)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            worker._speed_win.add(done)
    return out_path


def _download_chzzk(worker, url, content_type):
    """치지직 클립/VOD — API 포맷의 progressive MP4 직접 스트림 다운로드."""
    ch_info = (
        analyze_chzzk_clip_api(url)
        if content_type == "clip"
        else analyze_chzzk_vod_api(url)
    )
    formats = ch_info.get("formats") or []
    if not formats:
        raise RuntimeError("chzzk stream fail (cookie)")
    fmt = formats[0]  # 최고 품질 우선 (API 가 정렬)
    stream_url = fmt.get("url") or ""
    if not stream_url:
        raise RuntimeError("chzzk URL missing")

    if not worker._meta_logged:
        worker._emit_chzzk_header(ch_info, fmt)

    out_path = os.path.join(
        worker.cfg["download_path"], _chzzk_filename(ch_info, fmt, worker.cfg)
    )
    real = _http_download(worker, stream_url, out_path)
    worker.log_success_info(real)
    worker._speed_win.reset()
    return True


def _download_youtube_live(worker, url):
    """유튜브 라이브 — ffmpeg 녹화 파이프라인 (live_recorder)."""
    return _lr.download_youtube_live(worker, url)


def _download_streamlink(worker, url):
    """streamlink 대상 — 자식 프로세스 녹화 파이프라인."""
    out_file = os.path.join(
        worker.cfg["download_path"], "streamlink_live.mp4"
    )
    temp_ts, thumb, _ = _lr.prepare_live_paths(worker, out_file, None)
    cmd = ["streamlink", url, "best", "-O"]
    return _lr.record_live_stream(worker, cmd, temp_ts, out_file, thumb)


def _download_vod(worker, url):
    """유튜브 VOD — yt-dlp 다운로드 (progress_hook → hook/틱)."""
    fmt = _format_selector(worker)
    opts = _make_ytdl_opts(worker, fmt, url)
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
    if not info:
        raise RuntimeError("info extract fail")

    if not worker._meta_logged:
        _pe.emit_download_header(worker, info)

    # 병합(chzzk 무관) 후 실제 산출 파일 완료 로그
    for dl in info.get("requested_downloads") or []:
        _pe.log_success_info(
            worker,
            dl.get("filepath") or dl.get("_filename") or ""
        )
        
    worker._speed_win.reset()
    return True


def _emit_error_log(worker, url, reason, failed_targets):
    """에러 로그 출력 및 실패 목록에 추가."""
    worker.log_concise.emit(
        emit_err(f"{format_target_url(url, 40)} — {reason}"),
        False,
        True,
    )
    failed_targets.append((url, reason))


def _is_youtube_live_url(worker, url):
    """유튜브 URL이 라이브인지 경량 프리체크 (yt-dlp extract_info 사용).

    배치(txt) 입력 시 is_live_hint가 없어 VOD 경로로 가는 문제를 해결하기 위해
    다운로드 전에 스트림 정보만 추출하여 is_live 여부를 확인한다.
    """
    try:
        opts = {
            "logger": worker.logger,
            "noplaylist": True,
            "skip_download": True,
            "extract_flat": False,
        }
        _apply_cookie_opts(opts, worker.cfg)
        _apply_client_opts(opts, worker.cfg, forced=worker.yt_client)
        _apply_ejs_opts(opts)
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return bool(info and info.get("is_live"))
    except Exception:
        return False


def download_target(worker, url, failed_targets):
    """개별 URL 다운로드 — 콘텐츠 타입 분기 및 정밀한 예외 식별."""
    try:
        ct = detect_content_type(url)
        if ct in ("clip", "vod"):
            return _download_chzzk(worker, url, ct)
        if ct == "live":
            return _download_youtube_live(worker, url)
        if ct == "stream":
            return _download_streamlink(worker, url)
        # youtube video — 라이브 힌트가 있거나 경량 프리체크로 라이브 확인 시 라이브 분기로
        if getattr(worker, "is_live_hint", False) or _is_youtube_live_url(worker, url):
            return _download_youtube_live(worker, url)
        return _download_vod(worker, url)

    except yt_dlp.utils.DownloadError as de:
        # YouTube 봇 체크/챌린지 실패 정밀 추적
        err_str = str(de).lower()
        if "challenge solving failed" in err_str or "sign in" in err_str or "the page needs to be reloaded" in err_str:
            reason = "age/bot-check restricted (우회 실패)"
        elif "requested format not available" in err_str:
            reason = "포맷 부재 (해상도/코덱 미지원)"
        elif "video unavailable" in err_str or "this video is not available" in err_str:
            reason = "영상 삭제/비공개 상태"
        elif "private video" in err_str:
            reason = "비공개 영상"
        else:
            reason = f"다운로드 차단: {str(de)[:60]}"
        _emit_error_log(worker, url, reason, failed_targets)
        return False

    except KeyError as ke:
        # 치지직 JSON 구조 변경 등 데이터 파싱 오류
        reason = f"데이터 파싱 오류 (API 변경 의심): {ke}"
        _emit_error_log(worker, url, reason, failed_targets)
        return False

    except (ConnectionError, TimeoutError, OSError) as net_ex:
        # 네트워크 계열 오류 세분화
        reason = f"네트워크 오류: {type(net_ex).__name__}"
        _emit_error_log(worker, url, reason, failed_targets)
        return False

    except Exception as ex:
        # 최후의 범용 에러 캐치
        reason = f"알 수 없는 오류: {type(ex).__name__}: {str(ex)[:50]}"
        _emit_error_log(worker, url, reason, failed_targets)
        return False


# ── 대상 평탄화 ────────────────────────────────────────────────────────────


def _flatten(worker, url):
    """yt-dlp extract_flat 으로 재생목록/채널 항목 URL 집합."""
    opts = {
        "logger": worker.logger,
        "extract_flat": True,
        "skip_download": True,
    }
    _apply_cookie_opts(opts, worker.cfg)
    _apply_client_opts(opts, worker.cfg, forced=worker.yt_client)
    _apply_ejs_opts(opts)
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    entries = info.get("entries") or []
    urls = []
    for e in entries:
        if not e:
            continue
        u = e.get("url") or e.get("webpage_url")
        if u:
            urls.append(u)
    return urls


def expand_targets(worker):
    """재생목록/채널 URL 을 개별 동영상 URL 로 펼친다."""
    expanded = []
    for url in worker.targets:
        try:
            urls = None
            if detect_content_type(url) == "playlist":
                urls = _flatten(worker, url)
            else:
                u = url.lower()
                if "/@" in u or "/channel/" in u or "/c/" in u:
                    from playlist import normalize_youtube_channel_url

                    urls = _flatten(worker, normalize_youtube_channel_url(url))
            expanded.extend(urls or [url])
        except Exception as ex:
            worker.log_concise.emit(
                emit_err(f"{format_target_url(url, 40)} — {str(ex)}"),
                is_status=False,
                is_error=True,
            )
    return expanded or worker.targets