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
    """raw 스택 버스의 시그널 브리지 — 워커 → GUI 스레드 전환 담당."""

    concise = Signal(str, bool, bool)
    full = Signal(str, bool)


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


def raw(tag, msg, is_status=False, is_error=False, full_only=False):
    """단일 진입점 — 모든 앱 동작은 여기로.

    Args:
        tag: 발생원 (pot-readiness / prewarm-lock / pot / deps 등)
        msg: 로그 본문.
        is_status / is_error: concise 상태줄 계약 그대로 전달.
        full_only: True면 F12(full)+history 전용. 메인 콘솔에는 절대 안 나간다.

    [채널 규칙] 메인(F12 아님) TUI와 full은 병렬 관계다.
    - full_only=False & TUI 라인  → 메인 콘솔(concise) 전용. F12에는 실지 않는다.
    - full_only=False & non-TUI  → F12(full)+history 전용. 메인에는 안 나갔다.
    - full_only=True              → 무조건 F12(full)+history. (prewarm 단계별 상세용)

    [스레드 안전] 이 함수는 history 기록(자체 lock)과 Signal.emit만 수행한다.
    Signal.emit은 스레드 안전 — 워커 스레드에서 호출해도 UI 위젯을 만들러
    직접 건드리지 않는다.
    """
    from log_console import is_tui_line
    import log_history
    text = str(msg)
    try:
        log_history.log(f"[{tag}] {text}")
    except Exception:
        pass
    if full_only:
        tagged = f"[{tag}] {text}" if not text.startswith(f"[{tag}]") else text
        _hub.full.emit(tagged, bool(is_status))
        return
    if is_tui_line(text):
        _hub.concise.emit(text, bool(is_status), bool(is_error))
    else:
        tagged = f"[{tag}] {text}" if not text.startswith(f"[{tag}]") else text
        _hub.full.emit(tagged, bool(is_status))
