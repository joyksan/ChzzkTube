##### target_downloader.py - 개별 URL 다운로드 / 대상 평탄화
"""DownloadWorker 의 다운로드 실행부 분할 모듈.

- expand_targets : 재생목록/채널 URL 을 개별 동영상 URL 로 평탄화
- download_target : 개별 URL 을 타입별로 분기해 실제 다운로드
  chzzk(clip/vod) → 직접 HTTP 스트림, youtube VOD → yt-dlp,
  youtube live → _download_youtube_live(ffmpeg), stream → streamlink
"""
import os
import re

import yt_dlp

from chzzk_api import analyze_chzzk_clip_api, analyze_chzzk_vod_api
from log_console import format_target_url
from utils import get_filename_template
from dl_platform import detect_content_type
from client_opts import _apply_client_opts, _apply_cookie_opts
from progress_emitter import emit_err


def _make_ytdl_opts(worker, fmt):
    """yt-dlp 다운로드 옵션 — outtmpl/훅/병합/쿠키/player_client 주입."""
    opts = {
        "logger": worker.logger,
        "noplaylist": True,
        "progress_hooks": [worker.hook],
        "outtmpl": os.path.join(
            worker.cfg.get("download_path") or ".",
            get_filename_template(worker.cfg),
        ),
        "format": fmt,
        "merge_output_format": worker.cfg.get("container", "mp4"),
        "retries": 3,
    }
    if worker.cfg.get("fast_download"):
        opts["concurrent_fragment_downloads"] = 4
    _apply_cookie_opts(opts, worker.cfg)
    _apply_client_opts(opts, worker.cfg)
    return opts


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
            if total:
                worker.progress_update.emit(done / total * 100.0, "chzzk")
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
        raise RuntimeError("치지직 스트림 정보를 가져오지 못했습니다 (치지직 로그인 쿠키 확인)")
    fmt = formats[0]  # 최고 품질 우선 (API 가 정렬)
    stream_url = fmt.get("url") or ""
    if not stream_url:
        raise RuntimeError("치지직 다운로드 URL 없음")

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
    return worker._download_youtube_live(url)


def _download_streamlink(worker, url):
    """streamlink 대상 — 자식 프로세스 녹화 파이프라인."""
    out_file = os.path.join(
        worker.cfg["download_path"], "streamlink_live.mp4"
    )
    temp_ts, thumb, _ = worker._prepare_live_paths(out_file, None)
    cmd = ["streamlink", url, "best", "-O"]
    return worker._record_live_stream(cmd, temp_ts, out_file, thumb)


def _download_vod(worker, url):
    """유튜브 VOD — yt-dlp 다운로드 (progress_hook → hook/틱)."""
    fmt = _format_selector(worker)
    opts = _make_ytdl_opts(worker, fmt)
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
    if not info:
        raise RuntimeError("동영상 정보 추출 실패")

    if not worker._meta_logged:
        worker._emit_download_header(info)

    # 병합(chzzk 무관) 후 실제 산출 파일 완료 로그
    for dl in info.get("requested_downloads") or []:
        worker.log_success_info(
            dl.get("filepath") or dl.get("_filename") or ""
        )
    worker._speed_win.reset()
    return True


def download_target(worker, url, failed_targets):
    """개별 URL 다운로드 — 콘텐츠 타입 분기."""
    try:
        ct = detect_content_type(url)
        if ct in ("clip", "vod"):
            return _download_chzzk(worker, url, ct)
        if ct == "live":
            return _download_youtube_live(worker, url)
        if ct == "stream":
            return _download_streamlink(worker, url)
        # youtube video — 라이브 힌트가 있으면 라이브 분기로
        if getattr(worker, "is_live_hint", False):
            return _download_youtube_live(worker, url)
        return _download_vod(worker, url)
    except Exception as ex:
        reason = str(ex)
        worker.log_concise.emit(
            emit_err(f"{format_target_url(url, 40)} — {reason}"),
            is_status=False,
            is_error=True,
        )
        failed_targets.append((url, reason))
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
    _apply_client_opts(opts, worker.cfg)
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