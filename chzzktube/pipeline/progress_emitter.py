##### progress_emitter.py - DownloadWorker 진행률/헤더 emit 파이프라인
"""다운로드 진행률·완료·헤더 로그의 단일 출처.

- VOD 진행 틱: yt-dlp hook → `ctx.speed_win`(10초 이동평균) → 0.5초 스로틀 컬럼 라인
- 라이브 틱·마감: 릴레이 파이프 계수 → 동일 컬럼 규격 (용량 rjust(9) / 속도 rjust(11))
- 헤더(다운로드/라이브/치지직): 제목·포맷 트리 조판, 통합 포맷은 오디오 가지 미표기
- media.cli_format_desc 가 포맷 표기의 단일 출처.

── Worker Contract ──────────────────────────────────────────────
본 모듈의 함수들이 요구하는 worker 객체의 인터페이스:
  worker.logger           : YtLoggerBridge — raw 버스 직행 (log_full/log_concise 시그널 폐기)
  worker.cfg              : dict  — download_path, container 등 설정
  worker.v_spec           : dict  — height, fps 등 비디오 스펙
  worker.audio_desc       : str   — 오디오 설명
  worker.current_url       : str   — 현재 처리 중인 URL
  worker.current_file      : str|None — 현재 다운로드 파일 경로
  ctx.speed_win        : SpeedWindow — 이동평균 속도 (hook 내부에서 add)
  worker.total_count / current_idx : int — 배치 진행 현황
  worker.live_partially_saved : bool — 라이브 부분 저장 플래그
──────────────────────────────────────────────────────────────────
"""
import os
import re
import time

from chzzktube.core.log_emitter import (
    emit_event,
    emit_dl,
)
import chzzktube.core.raw_log as raw_log
from chzzktube.core.media import cli_format_desc, format_bytes
from chzzktube.core.dl_platform import _dl_platform
from chzzktube.core.watchdog import LivenessWatchdog


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
    """VOD 진행 틱 — 0.5초 스로틀, SpeedWindow 평균 속도, 컬럼 라인.
    [Watchdog] 다운로드 진행 시 게이트/분석 워치독 하트비트 연장."""
    # [Watchdog] 진행 이벤트 발생 시 메인 워치독 하트비트 (ctx에서 메인 윈도우 접근 불가하므로 raw_log 이벤트로 전달)
    # 실제 하트비트는 DownloadWorker.run()에서 _gate_watchdog/_analysis_watchdog에 직접 연결 권장
    # 여기서는 진행 중임을 알리는 이벤트만 로깅
    raw_log.raw("dl", "progress_tick", to_tui=False)
    # 실제 워치독 하트비트는 DownloadWorker가 대상 진입 직전/직후에 호출한다.
    # 이 모듈은 UI/워커 역참조 없이 진행 데이터만 처리한다.

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

    raw_log.raw(
        "dl",
        emit_dl(
            status="RUN",
            scope=_dl_platform(ctx.current_url or ""),
            msg="",
            speed=speed_s,
            pct=pct,
            bar_frac=min(pct / 100.0, 1.0),
            is_status=True,
        ),
        to_tui=True,
    )


def log_success_info(ctx, file_path):
    """개별 파일 수급 완료 — 용량 포함 한 줄.

    [v3.8.0 Hyper-Minimalist TUI] 중간 임시 스트림(.f399/.f251 등)은 TUI에서
    은닉한다(to_tui=False). 병합 완료 후 최종 결과물 1줄은 yt-dlp
    postprocessor 훅(`pp_hook`)이 발행한다 — 지시서 §3 Task 5-2.
    """
    size = 0
    if file_path and os.path.exists(file_path):
        size = os.path.getsize(file_path)
    # [채널명 포함] DL 완료 Msg에 채널명 추가
    channel = _dl_platform(ctx.current_url or "")
    fname = os.path.basename(file_path) if file_path else "done"
    msg = f"{fname} ({format_bytes(size)})" if file_path else "done"
    raw_log.raw(
        "dl",
        emit_event("DL", "OK", channel, msg),
        to_tui=not _is_intermediate_stream(fname),
    )


### [v3.8.0] yt-dlp 분리 포맷 스트림 조각 식별 — '.f399.mp4' / '.f251.webm'
_INTERMEDIATE_RE = re.compile(r"\.f\d+\.")
# 병합/후처리 단계에서 최종 결과물만 TUI 노출 (모든 소스 스트림 은닉)
_PP_FINAL_STATUS = "finished"


def _is_intermediate_stream(fname):
    """분리 포맷 중간 조각(.fNNN) 여부 — TUI 은닉 판정."""
    return bool(_INTERMEDIATE_RE.search(str(fname or "")))


def pp_hook(ctx, d):
    """yt-dlp postprocessor 훅 — 병합/후처리 완료 시 최종 결과물 1줄만 발행.

    MergeVideo 등 후처리 finished 시 info_dict.filename이 최종 산출물이다.
    중복 방지: 이미 발행한 경로는 재발행하지 않는다 (ctx._pp_last_file).
    """
    if not isinstance(d, dict) or d.get("status") != _PP_FINAL_STATUS:
        return None
    info = d.get("info_dict") or {}
    final = info.get("filepath") or info.get("_filename") or ""
    if not final or _is_intermediate_stream(os.path.basename(final)):
        return None
    if getattr(ctx, "_pp_last_file", None) == final:
        return None
    ctx._pp_last_file = final
    size = os.path.getsize(final) if os.path.exists(final) else 0
    raw_log.raw(
        "dl",
        emit_dl(
            status="OK",
            scope=_dl_platform(ctx.current_url or ""),
            msg=f"{os.path.basename(final)} ({format_bytes(size)})",
        ),
        to_tui=True,
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
    raw_log.raw(
        "dl",
        emit_event("DL", "RUN", _dl_platform(ctx.current_url or ""), msg),
        to_tui=True,
    )
    ctx._meta_logged = True


def emit_chzzk_header(ctx, ch_info, fmt):
    """치지직(클립/VOD) 헤더 — 컬럼 포맷 통일."""
    title = ch_info.get("videoTitle") or ch_info.get("title") or "untitled"
    fmt_desc = cli_format_desc(fmt) if fmt else ""
    msg = f"chzzk - {title}"
    if fmt_desc:
        msg += f" ({fmt_desc})"
    raw_log.raw("dl", emit_event("DL", "RUN", "CHZ", msg), to_tui=True)
    ctx._meta_logged = True


def emit_live_final_stats(ctx, total_bytes, start_time):
    """라이브 종료 통계 — LIVE 스테이지, 용량은 MSG·평균 속도는 SPEED."""
    dur = (time.monotonic() - start_time) if start_time else 0.0
    rate = (total_bytes / dur) if dur > 0 else 0.0
    raw_log.raw(
        "dl",
        emit_dl(
            status="DONE",
            scope=_dl_platform(ctx.current_url or ""),
            speed=f"{format_bytes(rate)}/s",
            pct=100,
            bar_frac=1.0,
            stage="LIVE",
            msg=f"live done ({format_bytes(total_bytes)})",
        ),
        to_tui=True,
    )
    ctx.live_partially_saved = False
