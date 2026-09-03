"""finalizer.py - DownloadWorker의 _finalize 분할 — TUI 컬럼 포맷."""
import os

from progress_emitter import emit_dl, emit_err


def finalize(worker, total, failed_targets, success_count):
    """완료 요약 — TUI 컬럼 라인 1줄 + 개별 실패는 ERR 라인."""
    fail_count = len(failed_targets)

    if worker.state["canceled"]:
        if getattr(worker, "live_partially_saved", False):
            worker.live_partially_saved = False
        else:
            worker.log_concise.emit(
                emit_dl("ABORT", "-", spec="-", speed="-", pct=0, bar_frac=0,
                        msg="download canceled by user"),
                is_status=False, is_error=False,
            )

    if failed_targets:
        if total > 1:
            ff_path = os.path.join(worker.cfg["download_path"], "failed_urls.txt")
            try:
                with open(ff_path, "w", encoding="utf-8") as f:
                    for u, _ in failed_targets:
                        f.write(u + "\n")
            except Exception:
                pass
        # [개별 실패 라인] — ERR 컬럼 포맷으로 1건 1줄
        for u, reason in failed_targets:
            worker.log_concise.emit(
                emit_err(f"{u} — {reason}"),
                is_status=False, is_error=True,
            )

    # [결론 라인] — 성공/실패 카운트는 MSG 전용 (SPEC/SPEED 침범 금지)
    worker.log_concise.emit(
        emit_dl(
            status="DONE" if fail_count == 0 else "WARN",
            platform="-",
            spec="-",
            speed="-",
            pct=100,
            bar_frac=1.0,
            msg=f"batch finished (success: {success_count}, fail: {fail_count})",
        ),
        is_status=False, is_error=fail_count > 0,
    )

    worker.finished_all.emit(success_count, fail_count)
    return not worker.state["canceled"]
