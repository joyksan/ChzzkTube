# log_bus.py — 로그 버스 단순화 (raw_log 후계자).
#
# [규칙]
# - emit(msg, channel): 문자열 1개만 수용 (LogEvent 래핑은 발행자 책임 아님)
# - concise: 사용자 행동 필요(버튼/입력) + 진행률
# - full: 디버깅/진단/원문 (기본값)
# - both: 상태 변화 알림(READY/ERROR)
#
# Channel enum은 log_event.py에 유지 (하위 호환).
from PySide6.QtCore import QObject, Signal
import threading

from log_event import Channel


class LogBus(QObject):
    concise = Signal(str, bool, bool)
    full = Signal(str)

    def __init__(self):
        super().__init__()
        self._history_buf: list[str] = []
        self._history_cap = 5000


bus = LogBus()
_LOCK = threading.RLock()
_concise_subs: list = []
_full_subs: list = []


def subscribe_concise(fn):
    with _LOCK:
        if fn not in _concise_subs:
            _concise_subs.append(fn)
            bus.concise.connect(fn)


def subscribe_full(fn):
    with _LOCK:
        if fn not in _full_subs:
            _full_subs.append(fn)
            bus.full.connect(fn)


def emit(msg: str, channel: Channel = Channel.FULL, is_status: bool = False, is_error: bool = False):
    """단일 진입점. 문자열만 수용."""
    import log_history
    try:
        log_history.log(msg)
    except Exception:
        pass
    if channel & Channel.CONCISE:
        bus.concise.emit(msg, bool(is_status), bool(is_error))
    if channel & Channel.FULL:
        bus.full.emit(msg)