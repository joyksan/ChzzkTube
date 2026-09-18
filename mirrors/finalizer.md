"""finalizer.py - DownloadWorker의 _finalize 분할 — TUI 컬럼 포맷.

── Worker Contract ──────────────────────────────────────────────
본 모듈의 함수들이 요구하는 worker 객체의 인터페이스:
  ctx.logger           : YtLoggerBridge — raw 버스 직행 (log_full/log_concise 시그널 폐기)
  ctx.total_count      : int   — 전체 대상 수
  ctx.current_url       : str   — 현재 처리 중인 URL (실패 시 참조)
──────────────────────────────────────────────────────────────────
"""
import os

import chzzktube.core.raw_log as raw_log
from chzzktube.core.dl_platform import _dl_platform
from chzzktube.pipeline.progress_emitter import emit_dl, emit_err


def finalize(ctx, total, failed_targets, success_count, skip_targets=None, *, notify=True):
    """완료 요약을 기록한다.

    워커는 notify=False로 호출하고 자체 finally에서 종료 신호를 발행한다.
    notify=True는 기존 직접 호출자의 정상 마감 통지 호환용이다.
    
    Args:
        skip_targets: List[Tuple[url, skip_reason]] - 스킵된 항목들 (선택적)
    """
    fail_count = len(failed_targets)
    skip_count = len(skip_targets) if skip_targets else 0

    if ctx.state["canceled"]:
        if ctx.live_partially_saved:
            ctx.live_partially_saved = False
        else:
            raw_log.raw(
                "dl",
                emit_dl("ABORT", scope=_dl_platform(ctx.current_url or ""), msg="download canceled by user"),
                to_tui=True,
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
            raw_log.raw("dl", emit_err(f"{u} — {reason}"), to_tui=True)

    # [결론 라인] — 상태 세분화: DONE/WARN/FAIL/SKIP
    if ctx.state["canceled"]:
        status = "ABORT"
    elif fail_count == 0 and skip_count == 0:
        status = "DONE"
    elif fail_count == 0 and skip_count > 0:
        status = "DONE"  # 모두 스킵이거나 일부 스킵+성공
    elif success_count > 0 and fail_count > 0:
        status = "WARN"  # 일부 성공 + 일부 실패
    elif success_count == 0 and fail_count > 0:
        status = "FAIL"  # 모두 실패
    else:
        status = "WARN"

    msg_parts = [f"success: {success_count}"]
    if fail_count:
        msg_parts.append(f"fail: {fail_count}")
    if skip_count:
        msg_parts.append(f"skip: {skip_count}")
    msg = "batch finished (" + ", ".join(msg_parts) + ")"

    raw_log.raw(
        "dl",
        emit_dl(
            status=status,
            scope=_dl_platform(ctx.current_url or ""),
            pct=100,
            bar_frac=1.0,
            msg=msg,
            is_error=fail_count > 0,
        ),
        to_tui=True,
    )

    if notify:
        ctx.finished_all.emit(success_count, fail_count)
    return not ctx.state["canceled"]
