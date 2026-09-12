"""raw_log — 앱 전체 동작의 단일 진실 공급원 (raw 버스).

[계약 v3.3.0 — 포함관계 모델]
- 진입: raw(tag, msg) — msg는 LogEvent(문자열은 즉시 LogEvent로 정규화).
- 포함관계: history=전량, F12(full)=전량(⊇TUI), TUI(concise)=to_tui=True일 때만.
  → "F12가 안 받는 로그"는 존재하지 않는다.
- 라우팅: 채널은 발행자(raw() 호출점)가 결정한다 — 콘텐츠 정규식 판정 제로.
- 구독 전 호출도 history에 적재되므로 유실 없다.

[계층] 발행 스레드에서는 bounded queue 적재만 수행한다.
파일 I/O와 구독자 호출은 단일 dispatcher 스레드에서 순차 처리하며,
구독자 콜백은 dispatcher lock을 잡지 않은 상태에서 호출한다.
"""
from collections import deque
import queue
import threading
import time
from typing import Callable

from log_event import LogEvent


MAX_QUEUE = 2048
MAX_FULL_EVENTS = 4096
_HISTORY_SUMMARY = "raw_log queue overflow: UI mirror dropped"


class _RawDispatcher:
    """Single-consumer dispatcher; publishers only perform a non-blocking put."""

    def __init__(self) -> None:
        self._queue: queue.Queue[tuple] = queue.Queue(maxsize=MAX_QUEUE)
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._concise_subs: list[Callable] = []
        self._full_subs: list[Callable] = []
        self._full_events: deque[LogEvent] = deque(maxlen=MAX_FULL_EVENTS)
        self._overflowed = False
        self._thread = threading.Thread(target=self._run, name="raw-log-dispatcher", daemon=True)
        self._thread.start()

    def subscribe_concise(self, fn: Callable) -> None:
        with self._lock:
            if fn not in self._concise_subs:
                self._concise_subs.append(fn)

    def subscribe_full(self, fn: Callable) -> None:
        with self._lock:
            if fn not in self._full_subs:
                self._full_subs.append(fn)

    def publish(self, event: LogEvent, to_tui: bool) -> bool:
        try:
            self._queue.put_nowait((event, bool(to_tui)))
            return True
        except queue.Full:
            self._record_overflow()
            return False

    def _record_overflow(self) -> None:
        with self._lock:
            if self._overflowed:
                return
            self._overflowed = True
        event = LogEvent(
            stage="SYS",
            status="WARN",
            scope="RAW",
            msg=_HISTORY_SUMMARY,
            is_error=True,
        )
        try:
            self._queue.put_nowait((event, True))
        except queue.Full:
            pass
        try:
            import log_history
            log_history.log(f"[raw-log] {_HISTORY_SUMMARY}", level="WARN")
        except Exception:
            pass

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                event, to_tui = self._queue.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                self._dispatch(event, to_tui)
            except Exception:
                # A subscriber must never kill the log pipeline.
                pass
            finally:
                self._queue.task_done()

    def _dispatch(self, event: LogEvent, to_tui: bool) -> None:
        try:
            import log_history
            log_history.log(
                f"[{getattr(event, 'tag', 'raw')}] {event.msg}",
                level="ERROR" if event.is_error else "INFO",
            )
        except Exception:
            pass

        with self._lock:
            self._full_events.append(event)
            full_subs = tuple(self._full_subs)
            concise_subs = tuple(self._concise_subs) if to_tui else ()

        for fn in full_subs:
            try:
                fn(event, bool(event.is_status))
            except TypeError:
                try:
                    fn(event)
                except Exception:
                    pass
            except Exception:
                pass
        for fn in concise_subs:
            try:
                fn(event, bool(event.is_status), bool(event.is_error))
            except TypeError:
                try:
                    fn(event)
                except Exception:
                    pass
            except Exception:
                pass

    def shutdown(self, timeout: float = 1.0) -> None:
        self._stop.set()
        self._thread.join(timeout=timeout)

    def flush(self, timeout: float = 1.0) -> None:
        """현재 queue와 dispatcher가 처리 중인 이벤트를 순서대로 기다린다."""
        self._queue.join()
        deadline = time.monotonic() + timeout
        while self.pending and time.monotonic() < deadline:
            time.sleep(0.01)

    @property
    def pending(self) -> int:
        return self._queue.qsize()

    @property
    def overflowed(self) -> bool:
        with self._lock:
            return self._overflowed


_dispatcher = _RawDispatcher()


def subscribe_concise(fn):
    """메인로그(TUI) 구독 등록 (중복 방지)."""
    _dispatcher.subscribe_concise(fn)


def subscribe_full(fn):
    """F12 상세로그 구독 등록 (중복 방지)."""
    _dispatcher.subscribe_full(fn)


def raw(tag, msg, is_status=False, is_error=False, to_tui=False):
    """단일 진입점 — 앱의 모든 행동은 여기로 수신된다."""
    if not isinstance(msg, LogEvent):
        msg = LogEvent(
            stage="SYS",
            status="FAIL" if is_error else "OK",
            scope="-",
            msg=str(msg),
            is_status=is_status,
            is_error=is_error,
            rendered=True,
        )
    else:
        if is_status:
            msg.is_status = True
        if is_error:
            msg.is_error = True
    _dispatcher.publish(msg, to_tui)


def flush(timeout: float = 1.0) -> None:
    """테스트/종료용: 현재 queue가 처리될 때까지 기다린다."""
    _dispatcher.flush(timeout)


def shutdown(timeout: float = 1.0) -> None:
    _dispatcher.shutdown(timeout)

