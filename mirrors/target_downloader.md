##### target_downloader.py - 개별 URL 다운로드 / 대상 평탄화
"""DownloadWorker의 다운로드 실행부 분할 모듈.

- expand_targets : 재생목록/채널 URL을 개별 동영상 URL로 평탄화
- download_target : 개별 URL을 타입별로 분기해 실제 다운로드
  chzzk(clip/vod) → 직접 HTTP 스트림, youtube VOD → yt-dlp,
  youtube live → _download_youtube_live(ffmpeg), stream → streamlink
"""
import functools
import os
import re
import time
import urllib.request
import yt_dlp

# yt_dlp.utils가 없을 수 있으므로 안전하게 참조
try:
    YtDownloadError = yt_dlp.utils.DownloadError
except AttributeError:
    # 네임스페이스 패키지 형태에서는 직접 import 시도
    try:
        from yt_dlp.utils import DownloadError as YtDownloadError
    except ImportError:
        class YtDownloadError(Exception):
            pass

import chzzktube.core.chzzk_api as chzzk_api
from chzzktube.core.chzzk_api import analyze_chzzk_clip_api, analyze_chzzk_vod_api
from chzzktube.core.client_opts import (
    _apply_client_opts,
    _apply_cookie_opts,
    _apply_ejs_opts,
    _apply_ffmpeg_opts,
    _apply_light_analysis_opts,
    _apply_post_opts,
    _apply_pot_opts,
    _concurrent_fragments,
)
from chzzktube.core.dl_platform import detect_content_type, _dl_platform
from chzzktube.core.playlist import normalize_youtube_channel_url
import chzzktube.core.raw_log as raw_log
from chzzktube.core.utils import get_filename_template
from chzzktube.infra.po_client import extract_video_id
import chzzktube.pipeline.live_recorder as _lr
import chzzktube.pipeline.progress_emitter as _pe
from chzzktube.pipeline.classifier import ClassifiedTarget, ContentKind, ItemClassifier

# ── 봇 차단 재시도 가능 마커 vs 터미널 에러 판별 (SSOT) ───────────────────────
_RETRYABLE_BOT_MARKERS = frozenset({
    "confirm you're not a bot",
    "not a bot",
    "sign in to confirm",
    "the page needs to be reloaded",
    "n challenge solving failed",
    "challenge solving failed",
    "po token",
    "failed to extract any player response",
    "http error 403",
})

_TERMINAL_FAIL_MARKERS = frozenset({
    "private video",
    "this video is private",
    "video unavailable",
    "this video is not available",
    "has been removed",
    "account has been terminated",
    "copyright",
    "members-only",
})

# [결함 5 수리] 워치독 하트비트 발행 간격 (초)
_WATCHDOG_HEARTBEAT_INTERVAL = 5.0


def _is_retryable_bot_error(err: Exception) -> bool:
    """봇 차단/JS 챌린지 계열인지 판별 — 터미널 에러는 즉시 상위로 탈출."""
    msg = str(err).lower()
    if any(term in msg for term in _TERMINAL_FAIL_MARKERS):
        return False
    return any(bot in msg for bot in _RETRYABLE_BOT_MARKERS)


def _make_ytdl_opts(ctx, fmt, url, forced_client=None):
    """yt-dlp 다운로드 옵션 — outtmpl/훅/병합/쿠키/player_client/PO 토큰 주입.
    
    Args:
        forced_client: 강제 사용할 player_client (None이면 ctx.yt_client 사용).
                       다운로드 클라이언트와 PO 토큰 클라이언트가 1:1 일치해야 함.
    """
    opts = {
        "logger": ctx.logger,
        "noplaylist": True,
        "progress_hooks": [functools.partial(_pe.hook, ctx)],
        "outtmpl": os.path.join(
            ctx.cfg.get("download_path") or ".",
            get_filename_template(ctx.cfg),
        ),
        "format": fmt,
        "merge_output_format": ctx.cfg.get("container", "mp4"),
        "retries": 3,
        "socket_timeout": 30,
        "throttledratelimit": 50_000,
    }
    frags = _concurrent_fragments(ctx.cfg)
    if frags > 1:
        opts["concurrent_fragment_downloads"] = frags
    _apply_cookie_opts(opts, ctx.cfg)
    
    # forced_client가 주어지면 강제 사용, 없으면 ctx.yt_client 사용
    effective_client = forced_client if forced_client is not None else ctx.yt_client
    _apply_client_opts(opts, ctx.cfg, forced=effective_client)
    _apply_ejs_opts(opts)
    
    # PO 토큰은 web 계열 클라이언트(web, web_safari) 전용 — ios/tv는 토큰 미주입
    # effective_client와 PO 토큰 client를 1:1 일치시킴 (쿠키 유무에 따라 auto → web/web_embedded 분기)
    vid = _extract_yt_id(url)
    if vid and effective_client in ("web", "web_safari"):
        _apply_pot_opts(opts, vid, client=effective_client)
    elif vid and effective_client == "auto":
        # _apply_client_opts와 동일한 쿠키 판정 로직 재사용하여 실제 사용될 client와 일치
        pot_client = "web" if _has_configured_cookies(ctx.cfg) else "web_embedded"
        _apply_pot_opts(opts, vid, client=pot_client)
    _apply_ffmpeg_opts(opts)
    _apply_post_opts(opts, ctx.cfg)
    return opts


def _extract_yt_id(url):
    """YouTube URL에서 video ID 추출 (PO 토큰 content_binding용)."""
    return extract_video_id(url)


def _format_selector(ctx):
    """yt-dlp format 선택 문자열 — 자동(해상도 제한 내 최고)/포맷 직접 고르기 대응.
    
    [결함 1 수리] tv 클라이언트 대비: 비디오+오디오 분리 포맷이 없을 때
    단일 포맷(b)으로 폴백하지 않고 명시적 에러 유도 → 상위에서 폴백 체인 계속.
    """
    if ctx.cfg.get("audio_only"):
        return "bestaudio/best"

    v_id = str(ctx.v_sel or "").strip()
    a_id = str(ctx.a_sel or "").strip()
    if v_id and v_id != "auto":
        if a_id and a_id != "auto":
            return f"{v_id}+{a_id}"
        return f"{v_id}+bestaudio"

    res = str(ctx.cfg.get("max_video_res") or "none").strip()
    if res.isdigit():
        return f"bv*[height<={res}]+ba"
    # [결함 1 수리] "bv*+ba/b" → "bv*+ba" (단일 포맷 폴백 제거)
    return "bv*+ba"


def _chzzk_filename(ch_info, fmt, cfg):
    """치지직 다운로드 파일명 — get_filename_template(cfg) 계약을 치지직 메타로 치환."""
    cfg = cfg or {}
    title = str(ch_info.get("title") or ch_info.get("videoTitle") or "chzzk")
    title = re.sub(r'[\\/:*?"<>|]+', "_", title).strip(" _") or "chzzk"
    cid = str(
        ch_info.get("clip_id")
        or ch_info.get("video_no")
        or ch_info.get("live_id")
        or ""
    ).strip()
    chan = str(ch_info.get("channel_name") or "").strip()
    date = str(ch_info.get("date") or "").strip()[:10]
    height = fmt.get("height") if isinstance(fmt, dict) else None

    prefix_map = {
        "none": "",
        "uploader": f"[{chan}] " if chan else "",
        "date_dash_uploader": f"{date} [{chan}] " if (date and chan) else "",
        "date_compact_uploader": (
            f"{date.replace('-', '')} [{chan}] " if (date and chan) else ""
        ),
        "date_dash": f"{date} " if date else "",
        "date_compact": f"{date.replace('-', '')} " if date else "",
    }
    prefix = prefix_map.get(str(cfg.get("filename_prefix", "none") or "none"), "")

    suffix = ""
    if cid:
        suffix = f" [{cid}]"
        if str(cfg.get("filename_suffix", "id") or "id") == "id_res" and height:
            suffix += f" [{height}p]"
    return f"{prefix}{title}{suffix}.mp4"


def _http_download(ctx, url, out_path):
    """치지직 progressive MP4 직접 스트림 다운로드 + 진행률 틱.
    
    [결함 5 수리] 5초마다 워치독 하트비트 호출.
    """
    ctx.speed_win.reset()
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as resp, open(out_path, "wb") as f:
        done = 0
        last_heartbeat = time.monotonic()
        while True:
            chunk = resp.read(262144)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            ctx.speed_win.add(done)

            # [결함 5 수리] 5초마다 워치독 하트비트
            now = time.monotonic()
            if now - last_heartbeat >= _WATCHDOG_HEARTBEAT_INTERVAL:
                last_heartbeat = now
                for attr in ("_download_watchdog", "_gate_watchdog", "_live_watchdog", "_analysis_watchdog"):
                    wd = getattr(ctx, attr, None)
                    if wd and hasattr(wd, "heartbeat"):
                        try:
                            wd.heartbeat()
                        except Exception:
                            pass
                        break
    return out_path


def _download_chzzk(ctx, url, content_type):
    """치지직 클립/VOD — API 포맷의 progressive MP4 직접 스트림 다운로드."""
    ch_info = (
        analyze_chzzk_clip_api(url)
        if content_type == "clip"
        else analyze_chzzk_vod_api(url)
    )
    formats = ch_info.get("formats") or []
    if not formats:
        raise RuntimeError("chzzk stream fail (cookie)")
    fmt = formats[0]
    stream_url = fmt.get("url") or ""
    if not stream_url:
        raise RuntimeError("chzzk URL missing")

    if not ctx._meta_logged:
        _pe.emit_chzzk_header(ctx, ch_info, fmt)

    out_path = os.path.join(
        ctx.cfg["download_path"], _chzzk_filename(ch_info, fmt, ctx.cfg)
    )
    real = _http_download(ctx, stream_url, out_path)
    _pe.log_success_info(ctx, real)
    ctx.speed_win.reset()
    return True


def _download_chzzk_live(ctx, url):
    """치지직 API의 HLS 포맷을 FFmpeg stdout 릴레이로 녹화한다."""
    info = chzzk_api.analyze_chzzk_live_api(url)
    if info.get("live_status") != "PROGRESS":
        raise RuntimeError("chzzk live offline")
    formats = [fmt for fmt in info.get("formats", []) if fmt.get("url")]
    selection = str(ctx.v_sel or "auto").strip()
    if selection and selection != "auto":
        formats = [fmt for fmt in formats if str(fmt.get("id")) == selection]
    else:
        limit = str(ctx.cfg.get("max_video_res") or "none")
        if limit.isdigit():
            formats = [fmt for fmt in formats if 0 < (fmt.get("height") or 0) <= int(limit)]
    if not formats:
        raise RuntimeError("chzzk live format unavailable")
    fmt = max(formats, key=lambda f: (f.get("height") or 0, f.get("bitrate") or 0))
    if not ctx._meta_logged:
        _pe.emit_chzzk_header(ctx, info, fmt)
    out_file = os.path.join(ctx.cfg["download_path"], _chzzk_filename(info, fmt, ctx.cfg))
    temp_ts, _, _ = _lr.prepare_live_paths(ctx, out_file)
    cmd = ["ffmpeg", "-y", "-i", fmt["url"]]
    if ctx.cfg.get("audio_only"):
        cmd.append("-vn")
    cmd.extend(["-c", "copy", "-f", "mpegts", "pipe:1"])
    ok = _lr.record_live_stream(ctx, cmd, temp_ts, log_tag="FFmpeg")
    if not ok and not ctx.state.get("canceled"):
        raise RuntimeError("chzzk live recording failed")
    return ok


def _download_youtube_live(ctx, url):
    """유튜브 라이브 — ffmpeg 녹화 파이프라인 (live_recorder)."""
    return _lr.download_youtube_live(ctx, url)


def _download_streamlink(ctx, url):
    """streamlink 대상 — 자식 프로세스 녹화 파이프라인 (화질은 cfg fit)."""
    out_file = os.path.join(ctx.cfg["download_path"], "streamlink_live.mp4")
    temp_ts, _, _ = _lr.prepare_live_paths(ctx, out_file, None)
    quality = str(ctx.cfg.get("streamlink_quality") or "best").strip() or "best"
    cmd = ["streamlink", url, quality, "-O"]
    return _lr.record_live_stream(ctx, cmd, temp_ts)


def _download_vod(ctx, url):
    """유튜브 VOD 다운로드 — 화질 우선 하향식 순차 폴백 (web -> web_safari -> tv)."""
    cfg_client = str(ctx.cfg.get("yt_player_client", "auto") or "auto")

    # auto 모드일 때만 지능형 하향식 체인 가동 (명시적 수동 선택 시 단일 시도)
    if cfg_client == "auto":
        # [결함 1 수리] ios는 SUPPORTS_COOKIES=False로 쿠키 사용 시 yt-dlp가 스킵
        # (analyze_worker.py _RETRY_CLIENTS = ["tv", "web_safari"]와 일치)
        # tv는 화질 제한(720p max) + 분리 포맷 부재 위험 → 마지막 수단으로만 사용
        client_chain = ["web", "web_safari", "tv"]
    else:
        client_chain = [cfg_client]

    fmt = _format_selector(ctx)
    last_err: Exception | None = None

    for idx, client in enumerate(client_chain):
        try:
            # tv 클라이언트 진입 시: 사용자에게 화질 저하 리스크 TUI 경고 발행
            if client == "tv":
                # [결함 1 수리] 분리 포맷(bv*+ba) 강제 → 없으면 예외로 폴백 유도
                # yt-dlp가 포맷을 못 찾으면 "Requested format is not available" 발생
                # 이는 _is_retryable_bot_error에서 True로 판별되어 다음 클라이언트 시도
                raw_log.raw(
                    "dl",
                    _pe.emit_event("DL", "WARN", "YTDL", "bot fallback: tv client (quality limited to 720p, no split formats)"),
                    to_tui=True,
                )

            opts = _make_ytdl_opts(ctx, fmt, url, forced_client=client)
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
            if not info:
                raise RuntimeError("info extract fail")

            if not ctx._meta_logged:
                _pe.emit_download_header(ctx, info)

            for dl in info.get("requested_downloads") or []:
                _pe.log_success_info(
                    ctx, dl.get("filepath") or dl.get("_filename") or ""
                )

            ctx.speed_win.reset()
            return True

        except Exception as ex:
            last_err = ex
            # 봇 차단 계열이 아니거나 마지막 체인이면 즉시 중단 및 전파
            if not _is_retryable_bot_error(ex):
                raise ex

            nxt = client_chain[idx + 1] if idx + 1 < len(client_chain) else "exhausted"
            raw_log.raw(
                "dl",
                _pe.emit_event("DL", "WARN", "YTDL", f"client fallback: {client} -> {nxt}"),
                to_tui=False,  # F12 상세 로그에만 기록
            )

    if last_err:
        raise last_err
    return False


def _emit_error_log(ctx, url, reason, failed_targets):
    """에러 로그 출력 및 실패 목록에 추가 (UI 모듈 역참조 배제)."""
    url_short = url[:40] + ("..." if len(url) > 40 else "")
    raw_log.raw("dl", _pe.emit_err(f"{url_short} — {reason}"), to_tui=True)
    failed_targets.append((url, reason))


def _is_youtube_live_url(ctx, url):
    """유튜브 URL이 라이브인지 경량 프리체크 (yt-dlp extract_info 사용)."""
    try:
        opts = {
            "logger": ctx.logger,
            "noplaylist": True,
            "skip_download": True,
            "extract_flat": False,
        }
        _apply_cookie_opts(opts, ctx.cfg)
        _apply_client_opts(opts, ctx.cfg, forced=ctx.yt_client)
        _apply_light_analysis_opts(opts)
        _apply_ejs_opts(opts)
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return bool(info and info.get("is_live"))
    except Exception:  # noqa: BLE001
        return False


def download_target(ctx, item, failed_targets, skip_targets=None):
    """개별 항목 다운로드 — 사전 분류 스킵 및 정적 디스패치 테이블 실행.
    
    Returns:
        True: 다운로드 성공
        "skip": 시스템 사전 필터링으로 스킵됨 (skip_targets에 기록됨)
        False: 다운로드 시도했으나 실패 (failed_targets에 기록됨)
    """
    # 1. 항목 분류 및 스킵 판정
    item = _classify_item(ctx, item)

    # 2. 다운로드 불가 항목 선제 필터링 (스킵 수집 및 TUI 로그 발행)
    if not item.downloadable:
        reason = item.skip_reason or "ineligible"
        _emit_skip_log(ctx, item, reason)
        if skip_targets is not None:
            skip_targets.append((item.url, reason))
        return "skip"

    # 3. URL 정규 문자열 추출
    url = item.url

    # 4. ContentKind 기반 정적 디스패치 (중복 regex 전면 철폐!)
    try:
        if item.kind == ContentKind.CLIP:
            return _download_chzzk(ctx, url, "clip")

        if item.kind == ContentKind.LIVE_CHZZK:
            return _download_chzzk_live(ctx, url)

        if item.kind == ContentKind.LIVE_YOUTUBE:
            return _download_youtube_live(ctx, url)

        if item.kind == ContentKind.VOD:
            if item.platform_tag == "CHZ":
                return _download_chzzk(ctx, url, "vod")
            return _download_vod(ctx, url)

        # UNKNOWN 또는 기타 플랫폼 폴백
        return _download_vod(ctx, url)

    # 5. 에러 분류 정교화 (봇 차단 vs 터미널 실패 vs 네트워크)
    except YtDownloadError as de:
        err_str = str(de).lower()
        if any(term in err_str for term in _TERMINAL_FAIL_MARKERS):
            reason = "unavailable"
        elif any(bot in err_str for bot in _RETRYABLE_BOT_MARKERS):
            reason = "age/bot restricted"
        elif "requested format not available" in err_str:
            reason = "format missing"
        else:
            reason = f"blocked ({str(de)[:40]})"

        _emit_error_log(ctx, url, reason, failed_targets)
        return False

    except (ConnectionError, TimeoutError, OSError) as net_ex:
        reason = f"net err ({type(net_ex).__name__})"
        _emit_error_log(ctx, url, reason, failed_targets)
        return False

    except Exception as ex:  # noqa: BLE001
        reason = f"err ({type(ex).__name__}: {str(ex)[:40]})"
        _emit_error_log(ctx, url, reason, failed_targets)
        return False


def _has_configured_cookies(cfg: dict) -> bool:
    """쿠키가 실제 yt-dlp에 주입되는지 판정 (_apply_cookie_opts와 동일 로직)."""
    browser = str(cfg.get("browser_cookie", "none") or "none").lower()
    # 브라우저 쿠키: none/auto/cookie_file 외 값이면 쿠키 있음
    if browser not in ("none", "auto", "cookie_file"):
        return True
    # cookie_file 모드: 파일이 존재해야만 쿠키 있음
    if browser == "cookie_file":
        cookie_file = str(cfg.get("cookie_file_path", "") or "").strip()
        return bool(cookie_file and os.path.exists(cookie_file))
    return False


def _emit_skip_log(ctx, item: ClassifiedTarget, reason: str) -> None:
    """TUI 고정 규격: DL │ SKIP │ SCOPE │ [reason] title 발행."""
    title_short = item.title[:35] + ("..." if len(item.title) > 35 else "")
    raw_log.raw(
        "dl",
        _pe.emit_event("DL", "SKIP", item.platform_tag, f"[{reason}] {title_short}"),
        to_tui=True,
    )


def _classify_item(ctx, raw_target: ClassifiedTarget | str | dict) -> ClassifiedTarget:
    """항목 정규화 및 I/O 격리 쿠키 정책 검증기.
    
    입력: ClassifiedTarget | dict | str(URL)
    출력: ClassifiedTarget (파이프라인 단일 계약)
    """
    # 1. ClassifiedTarget 규격 승격
    if isinstance(raw_target, ClassifiedTarget):
        item = raw_target
    elif isinstance(raw_target, dict):
        # dict에서 URL과 메타데이터 추출
        url = raw_target.get("url", "")
        raw_info = {k: v for k, v in raw_target.items() if k != "url"}
        item = ItemClassifier.classify(url, raw_info=raw_info)
    else:
        # str(URL)인 경우
        item = ItemClassifier.classify(str(raw_target))

    # 2. 이미 다운로드 불가로 마킹된 항목 (이미지 전용 등) 조기 반환
    if not item.downloadable:
        return item

    # 3. 인증 요구사항 교차 검증 (도메인 정책 vs 현재 런타임 cfg)
    if item.capability.requires_auth and not _has_configured_cookies(ctx.cfg):
        return ClassifiedTarget(
            url=item.url,
            title=item.title,
            kind=item.kind,
            capability=item.capability,
            platform_tag=item.platform_tag,
            downloadable=False,
            needs_pot=item.needs_pot,
            skip_reason="age/member gated",
            metadata=item.metadata,
        )

    return item


def _flatten(ctx, url: str) -> list[ClassifiedTarget]:
    """yt-dlp extract_flat 기반 재생목록/채널 평탄화.
    
    [원칙 준수]
    - 어설픈 하드코딩 dict 날조 금지: entries의 원시 메타를 ItemClassifier에 그대로 위임.
    - extract_flat 환경에서는 StreamCapability.indeterminate()가 자동 적용되어
      has_video/has_audio=None (미정) 상태가 거짓말 없이 정직하게 보존된다.
    """
    opts = {
        "logger": ctx.logger,
        "extract_flat": True,
        "skip_download": True,
        "noplaylist": False,
        "socket_timeout": 30,
    }
    _apply_cookie_opts(opts, ctx.cfg)
    _apply_client_opts(opts, ctx.cfg, forced=ctx.yt_client)
    _apply_light_analysis_opts(opts)
    _apply_ejs_opts(opts)

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
        entries = (info or {}).get("entries") or []
        targets: list[ClassifiedTarget] = []

        for e in entries:
            if not e:
                continue
            # yt-dlp flat 추출 시 url 또는 webpage_url 필드 참조
            target_url = e.get("url") or e.get("webpage_url")
            if not target_url:
                continue
            
            # YouTube ID만 떨어진 경우 정규 URL로 복원
            if not target_url.startswith("http"):
                target_url = f"https://www.youtube.com/watch?v={target_url}"

            # 1단계 ItemClassifier에 위임하여 TriState(None) 메타데이터 보존 객체 생성
            classified = ItemClassifier.classify(target_url, raw_info=e)
            targets.append(classified)

        return targets


def expand_targets(ctx) -> list[ClassifiedTarget]:
    """재생목록/채널 URL을 개별 동영상 항목 객체로 펼친다.
    
    반환: List[ClassifiedTarget] - 파이프라인 전체가 공유하는 단일 계약
    """
    expanded: list[ClassifiedTarget] = []
    for url in ctx.targets:
        try:
            urls: list[ClassifiedTarget] | None = None
            if detect_content_type(url) == "playlist":
                urls = _flatten(ctx, url)
            else:
                u = url.lower()
                if "/@" in u or "/channel/" in u or "/c/" in u or "/user/" in u:
                    urls = _flatten(ctx, normalize_youtube_channel_url(url))
            
            if urls:
                # _flatten이 이미 List[ClassifiedTarget] 반환
                expanded.extend(urls)
            else:
                # 단일 영상 - 정규화 팩토리를 통해 즉시 승격
                expanded.append(_normalize_single_item(url))
        except Exception as ex:  # noqa: BLE001
            url_short = url[:40] + ("..." if len(url) > 40 else "")
            raw_log.raw("dl", _pe.emit_err(f"{url_short} — {str(ex)}"), to_tui=True)
            # 실패 시에도 다운로드 루프에서 개별 에러로 처리될 수 있도록 정규화 타깃으로 유지
            expanded.append(_normalize_single_item(url))

    return expanded


def _normalize_single_item(url: str) -> ClassifiedTarget:
    """단일 영상 URL을 ClassifiedTarget으로 정규화 (메타는 다운로드 단계에서 채움)."""
    return ItemClassifier.classify(url, raw_info=None)