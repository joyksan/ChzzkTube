"""finalizer.py - DownloadWorker의 _finalize 분할 — TUI 컬럼 포맷.

── Worker Contract ──────────────────────────────────────────────
본 모듈의 함수들이 요구하는 worker 객체의 인터페이스:
  worker.logger           : YtLoggerBridge — log_full/log_concise 시그널
  worker.total_count      : int   — 전체 대상 수
  worker.current_url       : str   — 현재 처리 중인 URL (실패 시 참조)
──────────────────────────────────────────────────────────────────
"""
import os

from progress_emitter import emit_dl, emit_err


def finalize(ctx, total, failed_targets, success_count):
    """완료 요약 — TUI 컬럼 라인 1줄 + 개별 실패는 ERR 라인."""
    fail_count = len(failed_targets)

    if ctx.state["canceled"]:
        if ctx.live_partially_saved:
            ctx.live_partially_saved = False
        else:
            ctx.logger.log_concise.emit(
                emit_dl("ABORT", "-", spec="-", speed="-", pct=0, bar_frac=0,
                        msg="download canceled by user"),
                False, False,
            )

    if failed_targets:
        if total > 1:
            ff_path = os.path.join(ctx.cfg["download_path"], "failed_urls.txt")
            try:
                with open(ff_path, "w", encoding="utf-8") as f:
                    for u, _ in failed_targets:
                        f.write(u + "\n")
            except Exception:
                pass
        # [개별 실패 라인] — ERR 컬럼 포맷으로 1건 1줄
        for u, reason in failed_targets:
            ctx.logger.log_concise.emit(
                emit_err(f"{u} — {reason}"),
                False, True,
            )

    # [결론 라인] — 성공/실패 카운트는 MSG 전용 (SPEC/SPEED 침범 금지)
    ctx.logger.log_concise.emit(
        emit_dl(
            status="DONE" if fail_count == 0 else "WARN",
            platform="-",
            spec="-",
            speed="-",
            pct=100,
            bar_frac=1.0,
            msg=f"batch finished (success: {success_count}, fail: {fail_count})",
        ),
        False, fail_count > 0,
    )

    ctx.finished_all.emit(success_count, fail_count)
    return not ctx.state["canceled"]
