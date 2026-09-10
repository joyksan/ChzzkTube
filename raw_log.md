"""raw_log — 앱 전체 동작의 단일 진실 공급원 (raw 스택 버스).

[구조] 모든 동작 로그는 raw(tag, msg) 하나로 진입 → 3채널 팬아웃:
- concise : MainWindow.append_concise_log (TUI 화면)
- full    : MainWindow.append_full_log (F12 상세)
- history : log_history.log (영구 파일)
필터링은 각 모듈이 알아서 — raw에는 모든 게 쌓인다.

[계층] 구독자(팬아웃 대상)는 QT SIGNAL로 연결한다. Signal.emit은 스레드
안전이며, 수신자(MainWindow 앱렌더)가 GUI 스레드 객체이므로 QueuedConnection
정책에 따라 슬롯은 항상 GUI 스레드에서 실행된다. 즉 워커 스레드에서 raw()를
호출해도 UI 위젯 직접 조작이 절대 발생하지 않는다. (단, 같은 스레드 내 직접
호출 테스트에서는 DirectConnection 정책이라 즉시 실행된다.)
구독 전 호출은 history에만 적재 (유실 방지).
"""
import threading

from PySide6.QtCore import QObject, Signal


class _RawHub(QObject):
    """raw 스택 버스의 시그널 브리지 — 워커 → GUI 스레드 전환 담당.

    [다형성] 시그니처를 (object, bool, bool)와 (object, str)로 변경하여
    기존 문자열(str)과 신규 LogEvent를 모두 수용.
    """
    concise = Signal(object, bool, bool)  # (str|LogEvent, is_status, is_error)
    full = Signal(object, str)            # (str|LogEvent, tag)


_hub = _RawHub()
_LOCK = threading.RLock()
_concise_subs: list = []
_full_subs: list = []


def subscribe_concise(fn):
    """메인로그 구독 등록 (중복 방지, 시그널 연결 1회)."""
    with _LOCK:
        if fn not in _concise_subs:
            _concise_subs.append(fn)
            _hub.concise.connect(fn)


def subscribe_full(fn):
    """F12 상세로그 구독 등록 (중복 방지, 시그널 연결 1회)."""
    with _LOCK:
        if fn not in _full_subs:
            _full_subs.append(fn)
            _hub.full.connect(fn)


from log_event import LogEvent, Channel


def raw(tag, msg, is_status=False, is_error=False, full_only=False, channel=None):
    """단일 진입점 — 문자열과 LogEvent 모두 수용하는 다형성 버스.

    Args:
        tag: 발생원 (pot-readiness / prewarm-lock / pot 등)
        msg: 로그 본문. **문자열** 또는 **LogEvent 객체**.
        is_status / is_error: concise 상태줄 계약 (문자열 전용).
        full_only: True면 F12(full)+history 전용 (문자열 전용 파라미터).
        channel: LogEvent 전송 시 채널 지정 (Channel enum). None이면 문자열 모드.

    [하위 호환] 레거시 문자열 수신 시 LogEvent로 자율 승격.
    [Event 모드] LogEvent 객체 + Channel enum — 정규식 판정 제로.
    """
    import log_history
    from log_console import is_tui_line

    # --- 문자열 → LogEvent 자동 승격 (하위 호환 브리지) ---
    if not isinstance(msg, LogEvent) and channel is None and not full_only:
        text = str(msg)
        try:
            log_history.log(f"[{tag}] {text}")
        except Exception:
            pass
        if is_tui_line(text):
            _hub.concise.emit(text, bool(is_status), bool(is_error))
        else:
            tagged = f"[{tag}] {text}" if not text.startswith(f"[{tag}]") else text
            _hub.full.emit(tagged, tag)
        return

    if full_only:
        channel = Channel.FULL | Channel.HISTORY

    # --- Event 모드 ---
    if not isinstance(msg, LogEvent):
        msg = LogEvent(stage="SYS", status="OK", platform="-", spec="-",
                       msg=str(msg), is_status=is_status, is_error=is_error)
    _emit_event(tag, msg, channel)


def _emit_event(tag, event, channel):
    """구조화된 LogEvent → 채널별 전송 (정규식 판정 없음).

    [다형성] 수신 시 Subscriber는 isinstance(event, LogEvent)으로 판별하여
    event.to_log_line() 호출 (TypeError 원천 차단).
    """
    try:
        # history: 항상 기록
        import log_history
        log_history.log(f"[{tag}] {event.msg}", is_status=event.is_status, is_error=event.is_error)

        # 채널별 emit (정규식 검사 0회)
        if channel is None:
            channel = Channel.BOTH
        if channel & Channel.CONCISE:
            _hub.concise.emit(event, event.is_status, event.is_error)
        if channel & Channel.FULL:
            _hub.full.emit(event, tag)
    except Exception:
        pass
