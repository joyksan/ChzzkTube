##### progress_emitter.py - DownloadWorker 진행률/헤더 emit 파이프라인
"""다운로드 진행률·완료·헤더 로그의 단일 출처.

- VOD 진행 틱: yt-dlp hook → `_speed_win`(10초 이동평균) → 0.5초 스로틀 컬럼 라인
- 라이브 틱·마감: 릴레이 파이프 계수 → 동일 컬럼 규격 (용량 rjust(9) / 속도 rjust(11))
- 헤더(다운로드/라이브/치지직): 제목·포맷 트리 조판, 통합 포맷은 오디오 가지 미표기
- media.cli_format_desc 가 포맷 표기의 단일 출처.

── Worker Contract ──────────────────────────────────────────────
본 모듈의 함수들이 요구하는 worker 객체의 인터페이스:
  worker.logger           : YtLoggerBridge — log_full/log_concise 시그널
  worker.cfg              : dict  — download_path, container 등 설정
  worker.v_spec           : dict  — height, fps 등 비디오 스펙
  worker.audio_desc       : str   — 오디오 설명
  worker.current_url       : str   — 현재 처리 중인 URL
  worker.current_file      : str|None — 현재 다운로드 파일 경로
  worker._speed_win        : SpeedWindow — 이동평균 속도 (hook 내부에서 add)
  worker.total_count / current_idx : int — 배치 진행 현황
  worker.live_partially_saved : bool — 라이브 부분 저장 플래그
──────────────────────────────────────────────────────────────────
"""
import os
import time

from log_console import (
    emit_event,
    emit_dl,
    emit_err,
    format_log_line,
)
from media import cli_format_desc, format_bytes
from dl_platform import _dl_platform
from client_opts import _apply_client_opts, _apply_cookie_opts


def _dl_spec(ctx):
    """컨텍스트에서 사양 문자열 추출 (해상도·fps, 오디오 폴백)."""
    v = ctx.v_spec or {}
    h = v.get("height") or 0
    fps = v.get("fps") or 0
    if h:
        return f"{h}p{fps}" if fps else f"{h}p"
    a_desc = ctx.audio_desc or ""
    if a_desc and ("(" in a_desc or "AAC" in a_desc or "OPUS" in a_desc):
        return a_desc
    return ""


def hook(ctx, d):
    """yt-dlp progress_hook 콜백 — downloading→틱, finished→완료 메타."""
    status = d.get("status")
    if status == "downloading":
        return emit_progress_tick(ctx, d)
    if status == "finished":
        fpath = d.get("filename") or ctx.current_file or ""
        return log_success_info(ctx, fpath)
    return None


_TICK_INTERVAL = 0.5  # VOD 틱 0.5초 스로틀


def emit_progress_tick(ctx, d):
    """VOD 진행 틱 — 0.5초 스로틀, SpeedWindow 평균 속도, 컬럼 라인."""
    now = time.monotonic()
    last = ctx._last_tick_t or 0
    if last and now - last < _TICK_INTERVAL:
        return
    ctx._last_tick_t = now

    done = float(d.get("downloaded_bytes") or 0)
    total = float(d.get("total_bytes") or d.get("total_bytes_estimate") or 0)

    ctx.speed_win.add(done)
    rate = ctx.speed_win.speed()
    speed_s = f"{format_bytes(rate)}/s" if rate else "-"

    pct = (done / total * 100.0) if total else 0.0
    # 제목은 이미 ANAL 단계에서 표시되었으므로 제외 (중복 방지)
    title = ""

    ctx.logger.log_concise.emit(
        emit_dl(
            status="RUN",
            platform=_dl_platform(ctx.current_url or ""),
            spec=_dl_spec(ctx),
            speed=speed_s,
            pct=pct,
            bar_frac=min(pct / 100.0, 1.0),
            msg=title,
        ),
        True,   # is_status=True — 진행률 틱은 새 줄 금지, 한 줄 덮어쓰기(갱신형)
        False,
    )


def log_success_info(ctx, file_path):
    """개별 파일 완료 — 용량 포함 한 줄."""
    size = 0
    if file_path and os.path.exists(file_path):
        size = os.path.getsize(file_path)
    # [채널명 포함] DL 완료 Msg에 채널명 추가
    channel = _dl_platform(ctx.current_url or "")
    fname = os.path.basename(file_path) if file_path else "done"
    msg = f"{fname} ({format_bytes(size)})" if file_path else "done"
    ctx.logger.log_concise.emit(
        emit_event("DL", "OK", channel, msg),
        False,
        False,
    )


# ── 헤더 ───────────────────────────────────────────────────────────────────


def _title_of(info):
    return str(info.get("title") or info.get("videoTitle") or "video")


def emit_download_header(ctx, info):
    """VOD 다운로드 시작 헤더 — 컬럼 포맷 통일."""
    title = _title_of(info)
    fmt = info.get("format") or {}
    fmt_desc = cli_format_desc(fmt) if fmt and isinstance(fmt, dict) else ""
    msg = f"{title}"
    if fmt_desc:
        msg += f" ({fmt_desc})"
    ctx.logger.log_concise.emit(
        emit_event("DL", "RUN", _dl_platform(ctx.current_url or ""), msg),
        False,
        False,
    )
    ctx._meta_logged = True


def emit_live_header(ctx, info, res_label=""):
    """라이브 녹화 시작 헤더 — LIVE 스테이지, 해상도는 SPEC 분리."""
    title = _title_of(info)
    if res_label:
        ctx.logger.log_concise.emit(
            emit_dl("RUN", _dl_platform(ctx.current_url or ""),
                    spec=res_label, stage="LIVE", msg=title),
            False, False,
        )
    else:
        ctx.logger.log_concise.emit(
            emit_dl("RUN", _dl_platform(ctx.current_url or ""),
                    stage="LIVE", msg=title),
            False, False,
        )
    ctx._meta_logged = True


def emit_chzzk_header(ctx, ch_info, fmt):
    """치지직(클립/VOD) 헤더 — 컬럼 포맷 통일."""
    title = ch_info.get("videoTitle") or ch_info.get("title") or "untitled"
    fmt_desc = cli_format_desc(fmt) if fmt else ""
    msg = f"chzzk — {title}"
    if fmt_desc:
        msg += f" ({fmt_desc})"
    ctx.logger.log_concise.emit(
        emit_event("DL", "RUN", "chzzk", msg),
        False,
        False,
    )
    ctx._meta_logged = True


def emit_live_final_stats(ctx, total_bytes, start_time):
    """라이브 종료 통계 — LIVE 스테이지, 용량은 MSG·평균 속도는 SPEED."""
    dur = (time.monotonic() - start_time) if start_time else 0.0
    rate = (total_bytes / dur) if dur > 0 else 0.0
    ctx.logger.log_concise.emit(
        emit_dl(
            status="DONE",
            platform="-",
            spec="-",
            speed=f"{format_bytes(rate)}/s",
            pct=100,
            bar_frac=1.0,
            stage="LIVE",
            msg=f"live done ({format_bytes(total_bytes)})",
        ),
        False,
        False,
    )
    ctx.live_partially_saved = False
