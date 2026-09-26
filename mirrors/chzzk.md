##### target_downloader/chzzk.py - 치지직 VOD/클립/라이브 다운로드
"""치지직 VOD/클립/라이브 직접 HTTP 스트림 다운로드."""
import os
import time
import urllib.request

from chzzktube.core import chzzk_api, raw_log
from chzzktube.core.chzzk_api import analyze_chzzk_clip_api, analyze_chzzk_vod_api
from chzzktube.core.log_emitter import emit_event
from chzzktube.pipeline.target_downloader import utils as td_utils


def _http_download(ctx, url: str, out_path: str) -> bool:
    """HTTP 스트림 직접 다운로드 — ffmpeg 없이 순수 urllib로 청크 기록.

    - ctx.speed_win에 수신 바이트 누적으로 속도 측정
    - 워치독 하트비트 5초 주기 발행 (원본 로직: 다중 워치독 속성 순회)
    """
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp, open(out_path, "wb") as f:
            last_heartbeat = time.monotonic()
            while True:
                chunk = resp.read(256 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                ctx.speed_win.add(len(chunk))

                # [결함 5 수리] 워치독 하트비트 5초 주기 — 다중 워치독 속성 순회
                now = time.monotonic()
                if now - last_heartbeat >= td_utils._WATCHDOG_HEARTBEAT_INTERVAL:
                    last_heartbeat = now
                    for attr in ("_download_watchdog", "_gate_watchdog", "_live_watchdog", "_analysis_watchdog"):
                        wd = getattr(ctx, attr, None)
                        if wd and hasattr(wd, "heartbeat"):
                            try:
                                wd.heartbeat()
                            except Exception:  # noqa: BLE001, S110 — 하트비트 실패는 다운로드 계속
                                pass
                            break
        return True
    except Exception as ex:  # noqa: BLE001 — HTTP 다운로드 실패는 raw 버스 기록
        raw_log.raw(emit_event("DL", "FAIL", "CHZZK", f"HTTP 다운로드 실패: {ex}"), to_tui=False)
        return False


def _download_chzzk(ctx, url: str, content_type: str) -> bool | str:
    """치지직 VOD/클립 다운로드 — API 분석 후 HTTP 스트림 직접 수신."""
    # 1. API로 메타데이터 + 스트림 URL 획득
    try:
        if content_type == "clip":
            ch_info = analyze_chzzk_clip_api(url)
        else:
            ch_info = analyze_chzzk_vod_api(url)
    except Exception as ex:  # noqa: BLE001
        td_utils._emit_error_log(ctx, url, f"Chzzk API 분석 실패: {ex}", ctx.failed_targets)
        return False

    # 2. 스트림 URL이 없으면 스킵
    if not ch_info.get("stream_url"):
        td_utils._emit_skip_log(ctx, ctx.current_item, "스트림 URL 없음")
        return "skip"

    # 3. 출력 경로 생성
    fmt = {"ext": "mp4"}  # 치지직은 기본 mp4
    out_path = td_utils._chzzk_filename(ch_info, fmt, ctx.cfg)

    # 4. HTTP 다운로드 실행
    if _http_download(ctx, ch_info["stream_url"], out_path):
        raw_log.raw(
            emit_event("DL", "OK", "CHZZK", f"완료: {os.path.basename(out_path)}", url=url),
            to_tui=True,
        )
        return True
    else:
        td_utils._emit_error_log(ctx, url, "HTTP 다운로드 실패", ctx.failed_targets)
        return False


def _download_chzzk_live(ctx, url: str) -> bool:
    """치지직 API의 HLS 포맷을 FFmpeg stdout 릴레이로 녹화한다."""
    import os

    import chzzktube.pipeline.live_recorder as _lr
    import chzzktube.pipeline.progress_emitter as _pe

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
    out_file = os.path.join(ctx.cfg["download_path"], td_utils._chzzk_filename(info, fmt, ctx.cfg))
    temp_ts, _, _ = _lr.prepare_live_paths(ctx, out_file)
    cmd = ["ffmpeg", "-y", "-i", fmt["url"]]
    if ctx.cfg.get("audio_only"):
        cmd.append("-vn")
    cmd.extend(["-c", "copy", "-f", "mpegts", "pipe:1"])
    ok = _lr.record_live_stream(ctx, cmd, temp_ts, log_tag="FFmpeg")
    if not ok and not ctx.state.get("canceled"):
        raise RuntimeError("chzzk live recording failed")
    return ok