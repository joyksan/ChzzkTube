"""v3.9.0 로그 미러 — MainWindow에서 추출한 TUI/F12 미러 전담 모듈.

HANDOVER §5-33 직교 분리 + §6 Thin Wrapper 금지:
로직 통째 이전 (위임 껍데기 아님). MainWindow는 이 모듈 함수에
(fake-self 호환) 바인딩으로 위임한다.
"""
from chzzktube.core.log_event import LogEvent
from chzzktube.core import log_emitter


def finalize_concise_progress(self, line, is_status, is_error, component_id):
    """component_id로 추적 중인 TUI 진행 라인을 마감 이벤트로 확정한다."""
    if not component_id:
        return False
    console = getattr(self, "console", None)
    progress_lines = getattr(console, "_progress_lines", None)
    buffer = getattr(console, "_buffer", None)
    if not isinstance(progress_lines, dict) or buffer is None:
        return False

    index = progress_lines.get(component_id)
    if not isinstance(index, int) or not (0 <= index < len(buffer)):
        progress_lines.pop(component_id, None)
        return False

    entry = dict(buffer[index])
    entry.update({
        "msg": line,
        "is_status": bool(is_status),
        "is_error": bool(is_error),
        "component_id": component_id,
        "is_progress": False,
    })
    buffer[index] = entry
    progress_lines.pop(component_id, None)
    reflow = getattr(console, "reflow", None)
    if callable(reflow):
        reflow()
    return True


def render_concise(self, event, is_status=False, is_error=False):
    if isinstance(event, LogEvent):
        line = log_emitter.format_log_line_for_event(event)
        no_wrap = True
        component_id = getattr(event, "component_id", None)
        is_progress = bool(getattr(event, "is_progress", False))
    else:
        line = str(event)
        no_wrap = False
        component_id = None
        is_progress = False
    if len(line) > 4096:
        line = line[:4096] + "…"
    if component_id and not is_progress and finalize_concise_progress(
        self, line, is_status, is_error, component_id
    ):
        return
    try:
        self.console.append(
            line, is_status, is_error, no_wrap=no_wrap,
            component_id=component_id, is_progress=is_progress,
        )
    except TypeError:
        self.console.append(line, is_status, is_error, no_wrap=no_wrap)


def mirror_event_full(self, event, is_status=False):
    if isinstance(event, LogEvent):
        line = event.msg if event.msg else ""
        self._last_full_event = event
        component_id = getattr(event, "component_id", None)
        is_progress = bool(getattr(event, "is_progress", False))
    else:
        line = str(event)
        component_id = None
        is_progress = False
    f12_is_status = bool(is_status or is_progress)
    if f12_is_status:
        self._last_status_line = line
    try:
        mirror_full_log(self, line, f12_is_status, component_id=component_id)
    except TypeError:
        mirror_full_log(self, line, f12_is_status)


def mirror_full_log(self, line, is_status=False, component_id: str = None):
    """F12 전체 로그 버퍼 적재 및 활성 다이얼로그 제자리 갱신 관통 (SSOT).

    [v3.9.0 선택지 B] 진행 틱(is_status/component_id)은 버퍼 스냅샷 치환.
    전량 보존은 raw_log history + full_events ring이 담당 (직교 분리).
    """
    import time
    from collections import deque

    msg = str(line)
    if len(msg) > 4096:
        msg = msg[:4096] + "…"
    ts = time.strftime("%H:%M:%S")
    stamped = "\n".join(f"[{ts}] {line}" if line else f"[{ts}]" for line in msg.split("\n"))

    buf = getattr(self, "_full_log_buf", None)
    if buf is None:
        # 테스트 대역 등 버퍼 미보유 호출자: 다이얼로그 미러 경로로 폴백.
        _mirror_to_window_only(self, stamped, is_status, component_id)
        return
    if not isinstance(buf, deque):
        buf = deque(buf, maxlen=4096)
        self._full_log_buf = buf

    if is_status or component_id:
        if getattr(self, "_last_full_was_status", False) and buf:
            buf[-1] = stamped
        else:
            buf.append(stamped)
        self._last_full_was_status = True
    else:
        buf.append(stamped)
        self._last_full_was_status = False

    win = getattr(self, "verbose_win", None)
    win_visible = win is not None and win.isVisible()
    if win_visible:
        self._full_log_win_n = len(buf)
        try:
            win.append(stamped, is_status, component_id)
        except (AttributeError, RuntimeError, TypeError):
            try:
                win.append(stamped, is_status)
            except (AttributeError, RuntimeError):
                pass
    # 버퍼 미보유 대역(_FakeMain 등) 호환: 기존 _mirror_full_log 오버라이드 경유.
    _mirror_compat = getattr(type(self), "_mirror_full_log", None)
    if buf is None and callable(_mirror_compat):
        pass  # 위 폴백에서 이미 처리


def _mirror_to_window_only(self, stamped, is_status, component_id):
    """버퍼 없이 다이얼로그 미러만 수행 (테스트 대역 호환).

    레거시 _FakeMain._mirror_full_log(line, is_status) 오버라이드가 있으면
    그것을 호출해 rendered 수집을 유지한다.
    """
    override = getattr(self, "_mirror_full_log", None)
    # 무한 재귀 방지: 바인딩된 메서드가 log_mirror.mirror_full_log 자체면 스킵.
    if callable(override) and getattr(override, "__func__", None) is not mirror_full_log:
        try:
            return override(stamped.split("] ", 1)[-1] if "] " in stamped else stamped,
                            is_status)
        except TypeError:
            pass
    win = getattr(self, "verbose_win", None)
    if win is not None and win.isVisible():
        try:
            win.append(stamped, is_status, component_id)
        except (AttributeError, RuntimeError, TypeError):
            pass
