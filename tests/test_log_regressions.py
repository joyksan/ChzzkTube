"""로그 버스 및 F12 버퍼 회귀 테스트 (Qt 의존 없음).

[목적]
- raw_log dispatcher가 bounded queue를 유지하고, 포화 시 UI mirror를 드롭하며
  overflow 요약을 한 번만 기록하는지 검증한다.
- F12 전체 로그 버퍼가 deque(maxlen=4096)로 동작해 4,096건을 초과하면
  오래된 이벤트를 제거하는지 검증한다.
"""
from collections import deque
from unittest.mock import patch

from log_event import LogEvent
import raw_log


def test_raw_bus_overflow_is_bounded_and_summarized_once():
    """raw bus: 포화 시 UI mirror를 드롭하고 overflow 요약을 한 번만 기록."""
    import log_history

    dispatcher = raw_log._RawDispatcher()
    try:
        # 소비 스레드를 먼저 정지해 결정적으로 포화시킨다 —
        # dispatcher가 도중에 이벤트를 소비하면 큐가 차지 않는 타이밍 레이스 제거.
        dispatcher.shutdown()
        for index in range(raw_log.MAX_QUEUE):
            assert dispatcher.publish(
                LogEvent(
                    stage="SYS",
                    status="OK",
                    scope="test",
                    msg=f"fill-{index}",
                ),
                False,
            )

        with patch.object(log_history, "log") as history_log:
            assert not dispatcher.publish(
                LogEvent(
                    stage="SYS",
                    status="OK",
                    scope="test",
                    msg="overflow",
                ),
                False,
            )

        assert dispatcher.overflowed is True
        history_log.assert_called_once_with(
            f"[raw-log] {raw_log._HISTORY_SUMMARY}", level="WARN"
        )
    finally:
        dispatcher.shutdown()


def test_full_log_buffer_is_bounded():
    """F12 session buffer: 4096건을 초과하면 오래된 이벤트를 제거."""
    import os
    import pathlib

    # 실제 배선 가드 — MainWindow가 _full_log_buf를 deque(maxlen=4096)으로
    # 초기화해야 한다 (무제한 list/str 누수 방지 회귀). MainWindow 인스턴스
    # 생성은 Qt 이벤트 루프에 의존하므로 소스 계약으로 검증한다.
    main_src = pathlib.Path(
        os.path.join(os.path.dirname(__file__), "..", "main.py")
    ).read_text(encoding="utf-8")
    assert "self._full_log_buf: deque[str] = deque(maxlen=4096)" in main_src

    # 앱 버퍼 계약: 같은 상한으로 동작해야 한다.
    buffer = deque(maxlen=4096)
    for index in range(4097):
        buffer.append(f"line-{index}")

    assert buffer.maxlen == 4096
    assert len(buffer) == 4096
    assert buffer[0] == "line-1"
    assert buffer[-1] == "line-4096"


def test_threaded_publish_preserves_per_sender_order():
    """여러 스레드 발행: 각 발행자 내 순서 보존 + 유실 0건 (bounded queue 계약)."""
    import threading

    dispatcher = raw_log._RawDispatcher()
    received = []
    dispatcher.subscribe_full(lambda ev, t=None: received.append(ev.msg))
    n_threads, n_items = 4, 256

    def publish(sender):
        for i in range(n_items):
            dispatcher.publish(
                LogEvent(
                    stage="SYS", status="OK", scope="test",
                    msg=f"{sender}-{i}",
                ),
                False,
            )

    threads = [
        threading.Thread(target=publish, args=(sender,))
        for sender in range(n_threads)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    dispatcher.flush()

    assert len(received) == n_threads * n_items  # 유실 0건
    for sender in range(n_threads):
        seq = [m for m in received if m.startswith(f"{sender}-")]
        assert seq == [f"{sender}-{i}" for i in range(n_items)]  # 발행자 내 순서 보존
