##### progress_emitter.py - DownloadWorker 진행률/헤더 emit 파이프라인
"""다운로드 진행률·완료·헤더 로그의 단일 출처.

- VOD 진행 틱: yt-dlp hook → `_speed_win`(10초 이동평균) → 0.5초 스로틀 컬럼 라인
- 라이브 틱·마감: 릴레이 파이프 계수 → 동일 컬럼 규격 (용량 rjust(9) / 속도 rjust(11))
- 헤더(다운로드/라이브/치지직): 제목·포맷 트리 조판, 통합 포맷은 오디오 가지 미표기
- media.cli_format_desc 가 포맷 표기의 단일 출처.
"""
import os
import time

from log_console import (
    emit_event,
    format_log_line,
)
from media import cli_format_desc, format_bytes
from dl_platform import _dl_platform
from client_opts import _apply_client_opts, _apply_cookie_opts


def _dl_spec(worker):
    """다운로더 워커에서 사양 문자열 추출 (해상도·fps, 오디오 폴백)."""
    v = getattr(worker, "v_spec", None) or {}
    h = v.get("height") or 0
    fps = v.get("fps") or 0
    if h:
        return f"{h}p{fps}" if fps else f"{h}p"
    a_desc = getattr(worker, "audio_desc", "") or ""
    if a_desc and ("(" in a_desc or "AAC" in a_desc or "OPUS" in a_desc):
        return a_desc
    return ""


def emit_dl(status, platform, spec="", speed="", pct=None, bar_frac=None, msg="", stage="DL"):
    """DL 스테이지 컬럼 라인 — spec 뒤에 speed를 붙여 한 줄로 조판.

    예: [12:00:01] DL │ RUN │ YT  │ 1080p30 12.4M/s │ 65.0% │ [█⋯░] │ 제목
    """
    sp = str(spec or "-")
    if speed:
        sp = f"{sp} {speed}".strip()
    return format_log_line(
        stage=stage,
        status=status,
        platform=platform,
        spec=sp,
        pct=pct,
        bar_frac=bar_frac,
        msg=msg,
    )


def emit_err(msg):
    """DL 실패 컬럼 라인."""
    return format_log_line(
        stage="DL", status="FAIL", platform="-", spec="-", pct=None, bar_frac=None, msg=msg,
    )


def hook(worker, d):
    """yt-dlp progress_hook 콜백 — downloading→틱, finished→완료 메타."""
    status = d.get("status")
    if status == "downloading":
        return emit_progress_tick(worker, d)
    if status == "finished":
        fpath = d.get("filename") or getattr(worker, "current_file", "") or ""
        return log_success_info(worker, fpath)
    return None


_TICK_INTERVAL = 0.5  # VOD 틱 0.5초 스로틀


def emit_progress_tick(worker, d):
    """VOD 진행 틱 — 0.5초 스로틀, SpeedWindow 평균 속도, 컬럼 라인."""
    now = time.monotonic()
    last = getattr(worker, "_last_tick_t", 0) or 0
    if last and now - last < _TICK_INTERVAL:
        return
    worker._last_tick_t = now

    done = float(d.get("downloaded_bytes") or 0)
    total = float(d.get("total_bytes") or d.get("total_bytes_estimate") or 0)

    worker._speed_win.add(done)
    rate = worker._speed_win.speed()
    speed_s = f"{format_bytes(rate)}/s" if rate else "-"

    pct = (done / total * 100.0) if total else 0.0
    title = os.path.basename(d.get("filename") or getattr(worker, "current_file", "") or "")

    worker.log_concise.emit(
        emit_dl(
            status="RUN",
            platform=_dl_platform(getattr(worker, "current_url", "") or ""),
            spec=_dl_spec(worker),
            speed=speed_s,
            pct=pct,
            bar_frac=min(pct / 100.0, 1.0),
            msg=f'"{title}"' if title else "",
        ),
        is_status=False,
        is_error=False,
    )


def log_success_info(worker, file_path):
    """개별 파일 완료 — 용량 포함 한 줄."""
    size = 0
    if file_path and os.path.exists(file_path):
        size = os.path.getsize(file_path)
    worker.log_concise.emit(
        emit_event("DL", "OK", _dl_platform(getattr(worker, "current_url", "") or ""),
                   f"완료 — {os.path.basename(file_path)} ({format_bytes(size)})" if file_path else "완료"),
        is_status=False,
        is_error=False,
    )


# ── 헤더 ───────────────────────────────────────────────────────────────────


def _title_of(info):
    return str(info.get("title") or info.get("videoTitle") or "동영상")


def emit_download_header(worker, info):
    """VOD 다운로드 시작 헤더 — 컬럼 포맷 통일."""
    title = _title_of(info)
    fmt = info.get("format") or {}
    fmt_desc = cli_format_desc(fmt) if fmt and isinstance(fmt, dict) else ""
    msg = f"다운로드 시작 — {title}"
    if fmt_desc:
        msg += f" ({fmt_desc})"
    worker.log_concise.emit(
        emit_event("DL", "RUN", _dl_platform(getattr(worker, "current_url", "") or ""), msg),
        is_status=False,
        is_error=False,
    )
    worker._meta_logged = True


def emit_live_header(worker, info, res_label=""):
    """라이브 녹화 시작 헤더 — 컬럼 포맷 통일."""
    title = _title_of(info)
    msg = f"라이브 녹화 시작 — {title}"
    if res_label:
        msg += f" ({res_label})"
    worker.log_concise.emit(
        emit_event("DL", "RUN", _dl_platform(getattr(worker, "current_url", "") or ""), msg),
        is_status=False,
        is_error=False,
    )
    worker._meta_logged = True


def emit_chzzk_header(worker, ch_info, fmt):
    """치지직(클립/VOD) 헤더 — 컬럼 포맷 통일."""
    title = ch_info.get("videoTitle") or ch_info.get("title") or "치지직 영상"
    fmt_desc = cli_format_desc(fmt) if fmt else ""
    msg = f"치지직 다운로드 시작 — {title}"
    if fmt_desc:
        msg += f" ({fmt_desc})"
    worker.log_concise.emit(
        emit_event("DL", "RUN", "chzzk", msg),
        is_status=False,
        is_error=False,
    )
    worker._meta_logged = True


def emit_live_final_stats(worker, total_bytes, start_time):
    """라이브 종료 통계 — 용량 rjust(9)·속도 rjust(11) 고정폭."""
    dur = (time.monotonic() - start_time) if start_time else 0.0
    rate = (total_bytes / dur) if dur > 0 else 0.0
    worker.log_concise.emit(
        emit_dl(
            status="DONE",
            platform="-",
            spec=format_bytes(total_bytes).rjust(9),
            speed=f"{format_bytes(rate)}/s".rjust(11),
            pct=100,
            bar_frac=1.0,
            msg="라이브 녹화 완료",
        ),
        is_status=False,
        is_error=False,
    )
    worker.live_partially_saved = False
