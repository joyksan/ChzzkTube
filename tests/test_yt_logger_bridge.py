"""yt_logger_bridge 캐리지 리턴/\r 청크 처리 회귀 테스트.

[검증]
- 한 콜백 안 \r 반복 → 마지막 스냅샷만 발행 (중간 조각 폐기)
- \r로 끝나는 미완결 청크 → 다음 청크와 이어붙이도록 버퍼 이월
- warning/error는 버퍼에 갇히지 않고 즉시 보존
- progress tick 0.5초 스로틀 (2Hz 상한)
"""
from unittest.mock import patch

from yt_logger_bridge import YtLoggerBridge


def _bridge():
    b = YtLoggerBridge()
    b.snapshots = []
    b._emit_progress = lambda msg: b.snapshots.append(("progress", msg))
    b._emit_non_progress = lambda msg, level: b.snapshots.append(("non-progress", level, msg))
    return b


def test_multiple_carriage_snapshots_keep_latest():
    b = _bridge()
    b.debug("a\rb\r[download]  12%")
    assert b.snapshots[-1] == ("progress", "[download]  12%")


def test_carriage_ending_buffers_for_next_chunk():
    b = _bridge()
    # \r로 끝남 → 미완결 상태로 버퍼 이월, 무발행
    b.debug("first\r\nsecond\r")
    assert b.snapshots == []
    assert b._carriage_buffer == "second"
    # 다음 청크는 \r로 시작 → 이월 버퍼 폐기, 최신 스냅샷만 발행
    b.debug("\r[download]  25%")
    assert b.snapshots[-1] == ("progress", "[download]  25%")
    assert b._carriage_buffer == ""


def test_warning_immediate_not_buffered():
    b = _bridge()
    b.warning("some warning text")
    assert b.snapshots == [("non-progress", "warning", "some warning text")]


def test_progress_throttle_blocks_rapid_ticks():
    import raw_log

    b = YtLoggerBridge()
    b._last_progress = None
    b._last_progress_at = 0.0
    with patch.object(raw_log, "raw") as raw:
        b._emit_progress("[download]  1%")
        b._emit_progress("[download]  2%")  # 0.5s 내 → 2Hz 드롭
        assert raw.call_count == 1
    b._last_progress_at = 0.0  # 경과 강제 후 재발행
    with patch.object(raw_log, "raw") as raw:
        b._emit_progress("[download]  3%")
        assert raw.call_count == 1