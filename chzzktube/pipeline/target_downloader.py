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
import urllib.request
import yt_dlp

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
from chzzktube.core.dl_platform import detect_content_type
from chzzktube.core.playlist import normalize_youtube_channel_url
import chzzktube.core.raw_log as raw_log
from chzzktube.core.utils import get_filename_template
from chzzktube.infra.po_client import extract_video_id
import chzzktube.pipeline.live_recorder as _lr
import chzzktube.pipeline.progress_emitter as _pe


def _make_ytdl_opts(ctx, fmt, url):
    """yt-dlp 다운로드 옵션 — outtmpl/훅/병합/쿠키/player_client 주입."""
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
    _apply_client_opts(opts, ctx.cfg, forced=ctx.yt_client)
    _apply_ejs_opts(opts)
    _apply_pot_opts(
        opts,
        _extract_yt_id(url),
        client=(ctx.yt_client if ctx.yt_client != "auto" else "web_embedded"),
    )
    _apply_ffmpeg_opts(opts)
    _apply_post_opts(opts, ctx.cfg)
    return opts


def _extract_yt_id(url):
    """YouTube URL에서 video ID 추출 (PO 토큰 content_binding용)."""
    return extract_video_id(url)


def _format_selector(ctx):
    """yt-dlp format 선택 문자열 — 자동(해상도 제한 내 최고)/포맷 직접 고르기 대응."""
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
        return f"bv*[height<={res}]+ba/b"
    return "bv*+ba/b"


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
    """치지직 progressive MP4 직접 스트림 다운로드 + 진행률 틱."""
    ctx.speed_win.reset()
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as resp, open(out_path, "wb") as f:
        done = 0
        while True:
            chunk = resp.read(262144)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            ctx.speed_win.add(done)
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


def _download_youtube_live(ctx, url):
    """유튜브 라이브 — ffmpeg 녹화 파이프라인 (live_recorder)."""
    return _lr.download_youtube_live(ctx, url)


def _download_streamlink(ctx, url):
    """streamlink 대상 — 자식 프로세스 녹화 파이프라인 (화질은 cfg fit)."""
    out_file = os.path.join(ctx.cfg["download_path"], "streamlink_live.mp4")
    temp_ts, thumb, _ = _lr.prepare_live_paths(ctx, out_file, None)
    quality = str(ctx.cfg.get("streamlink_quality") or "best").strip() or "best"
    cmd = ["streamlink", url, quality, "-O"]
    return _lr.record_live_stream(ctx, cmd, temp_ts, out_file, thumb)


def _download_vod(ctx, url):
    """유튜브 VOD — yt-dlp 다운로드 (progress_hook → hook/틱)."""
    fmt = _format_selector(ctx)
    opts = _make_ytdl_opts(ctx, fmt, url)
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


def download_target(ctx, url, failed_targets):
    """개별 URL 다운로드 — 콘텐츠 타입 분기 및 정밀한 예외 식별."""
    try:
        ct = detect_content_type(url)
        if ct in ("clip", "vod"):
            return _download_chzzk(ctx, url, ct)
        if ct == "live":
            return _download_youtube_live(ctx, url)
        if ct == "stream":
            return _download_streamlink(ctx, url)
        if ctx.is_live_hint or _is_youtube_live_url(ctx, url):
            return _download_youtube_live(ctx, url)
        return _download_vod(ctx, url)

    except yt_dlp.utils.DownloadError as de:
        err_str = str(de).lower()
        if (
            "challenge solving failed" in err_str
            or "sign in" in err_str
            or "the page needs to be reloaded" in err_str
        ):
            reason = "age/bot restricted"
        elif "requested format not available" in err_str:
            reason = "format missing"
        elif "video unavailable" in err_str or "this video is not available" in err_str:
            reason = "video unavailable"
        elif "private video" in err_str:
            reason = "video private"
        else:
            reason = f"download blocked ({str(de)[:60]})"
        _emit_error_log(ctx, url, reason, failed_targets)
        return False

    except KeyError as ke:
        reason = f"parse error ({ke})"
        _emit_error_log(ctx, url, reason, failed_targets)
        return False

    except (ConnectionError, TimeoutError, OSError) as net_ex:
        reason = f"network error ({type(net_ex).__name__})"
        _emit_error_log(ctx, url, reason, failed_targets)
        return False

    except Exception as ex:  # noqa: BLE001
        reason = f"unknown error ({type(ex).__name__}: {str(ex)[:50]})"
        _emit_error_log(ctx, url, reason, failed_targets)
        return False


def _flatten(ctx, url):
    """yt-dlp extract_flat 으로 재생목록/채널 항목 URL 집합."""
    opts = {
        "logger": ctx.logger,
        "extract_flat": True,
        "skip_download": True,
    }
    _apply_cookie_opts(opts, ctx.cfg)
    _apply_client_opts(opts, ctx.cfg, forced=ctx.yt_client)
    _apply_light_analysis_opts(opts)
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


def expand_targets(ctx):
    """재생목록/채널 URL을 개별 동영상 URL로 펼친다."""
    expanded = []
    for url in ctx.targets:
        try:
            urls = None
            if detect_content_type(url) == "playlist":
                urls = _flatten(ctx, url)
            else:
                u = url.lower()
                if "/@" in u or "/channel/" in u or "/c/" in u:
                    urls = _flatten(ctx, normalize_youtube_channel_url(url))
            expanded.extend(urls or [url])
        except Exception as ex:  # noqa: BLE001
            url_short = url[:40] + ("..." if len(url) > 40 else "")
            raw_log.raw("dl", _pe.emit_err(f"{url_short} — {str(ex)}"), to_tui=True)
    return expanded or ctx.targets