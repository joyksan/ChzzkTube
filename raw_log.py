"""raw_log — 앱 전체 동작의 단일 진실 공급원 (raw 버스).

[계약 v3.3.0 — 포함관계 모델]
- 진입: raw(tag, msg) — msg는 LogEvent(문자열은 즉시 LogEvent로 정규화).
- 포함관계: history=전량, F12(full)=전량(⊇TUI), TUI(concise)=to_tui=True일 때만.
  → "F12가 안 받는 로그"는 존재하지 않는다.
- 라우팅: 채널은 발행자(raw() 호출점)가 결정한다 — 콘텐츠 정규식 판정 제로.
- 구독 전 호출도 history에 적재되므로 유실 없다.

[계층] 구독자(팬아웃 대상)는 QT SIGNAL로 연결한다. Signal.emit은 스레드
안전이며, 수신자(MainWindow 앱렌더)가 GUI 스레드 객체이므로 QueuedConnection
정책에 따라 슬롯은 항상 GUI 스레드에서 실행된다. 즉 워커 스레드에서 raw()를
호출해도 UI 위젯 직접 조작이 절대 발생하지 않는다.
"""
import sys
import threading

from PySide6.QtCore import QObject, Signal


class _RawHub(QObject):
    """raw 버스의 시그널 브리지 — 워커 → GUI 스레드 전환 담당."""
    concise = Signal(object, bool, bool)  # (LogEvent, is_status, is_error)
    full = Signal(object, bool)           # (LogEvent, is_status) — True면 F12 마지막 줄 갱신


_hub = _RawHub()
_LOCK = threading.RLock()
_concise_subs: list = []
_full_subs: list = []


def subscribe_concise(fn):
    """메인로그(TUI) 구독 등록 (중복 방지, 시그널 연결 1회)."""
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


from log_event import LogEvent


def raw(tag, msg, is_status=False, is_error=False, to_tui=False):
    """단일 진입점 — 앱의 모든 행동은 여기로 수신된다.

    Args:
        tag: 발행 원점 식별자 (pot / dl / deps / ytdlp / ui ...)
        msg: LogEvent 권장. 문자열은 즉시 LogEvent로 정규화된다 (하위 호환).
        is_status / is_error: 문자열 정규화 시 상태 계약.
        to_tui: True면 TUI(concise)에도 발사. history/F12는 항상 수신.

    [포함관계] history ⊆ F12 ⊆ (F12+TUI). 채널은 1비트(to_tui)로 축소됐다.
    """
    if not isinstance(msg, LogEvent):
        msg = LogEvent(
            stage="SYS", status="FAIL" if is_error else "OK",
            platform="-", spec="-", msg=str(msg),
            is_status=is_status, is_error=is_error,
            rendered=True,
        )
    try:
        import log_history
        log_history.log(
            f"[{tag}] {msg.msg}",
            level="ERROR" if msg.is_error else "INFO",
        )
    except Exception:
        pass
    # F12 = 전량 (슈퍼셋) — is_status 틱은 뷰에서 마지막 줄 갱신
    _hub.full.emit(msg, bool(msg.is_status))
    # TUI = 발행자 선택
    if to_tui:
        _hub.concise.emit(msg, bool(msg.is_status), bool(msg.is_error))
