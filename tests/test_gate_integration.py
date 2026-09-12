"""MainWindow × POTManager 게이트 통합 흐름 회귀 테스트 (Qt 인스턴스 불필요).

MainWindow 인스턴스 생성은 헤드리스 스모크 범위라, 여기서는 비공개 메서드를
가벼운 self 대역에 바인딩해 다음 계약만 검증한다.
- pot_finished(ok) → _pending_download 회수 후 _start_download 재개
- is_ready() False / ok=False 시에는 큐를 소비하지 않음
- F12 _mirror_event_full이 LogEvent를 format_log_line_for_event로 복원
"""
from types import SimpleNamespace

from log_event import LogEvent
from log_console import format_log_line_for_event

import main as main_module


class _FakeMain:
    def __init__(self):
        self._pending_download = None
        self._pot_manager = SimpleNamespace(is_ready=lambda: True)
        self.started = []
        self.rendered = []
        self._last_status_line = ""

    def _start_download(self, targets, v_id, a_id):
        self.started.append((targets, v_id, a_id))

    def _mirror_full_log(self, line, is_status=False):
        self.rendered.append((line, is_status))


def test_pending_download_resumed_on_pot_finished():
    m = _FakeMain()
    m._pending_download = (["https://youtu.be/x"], "auto", "auto")
    main_module.MainWindow._on_pot_finished(m, True, "ready")
    assert m.started == [(["https://youtu.be/x"], "auto", "auto")]
    assert m._pending_download is None


def test_pending_download_not_resumed_when_not_ready():
    m = _FakeMain()
    m._pot_manager = SimpleNamespace(is_ready=lambda: False)
    m._pending_download = (["https://youtu.be/x"], "auto", "auto")
    main_module.MainWindow._on_pot_finished(m, True, "ready")
    assert m.started == []
    assert m._pending_download is not None


def test_pending_download_not_resumed_on_failure():
    m = _FakeMain()
    m._pending_download = (["https://youtu.be/x"], "auto", "auto")
    main_module.MainWindow._on_pot_finished(m, False, "failed")
    assert m.started == []


def test_full_log_mirror_preserves_raw_msg():
    m = _FakeMain()
    ev = LogEvent(stage="DL", status="RUN", platform="YT", spec="1080p30",
                  speed="12.4M/s", pct=50.0, bar_frac=0.5,
                  msg="video title", is_status=True)
    main_module.MainWindow._mirror_event_full(m, ev, True)
    # F12는 원문 보관소 — 컬럼화하지 않고 msg 원문을 적재한다 (이중 ts 방지).
    assert m.rendered and m.rendered[0][0] == "video title"
    assert m._last_status_line == "video title"


def test_emit_format_logs_uses_bus():
    """분석 성공 포맷 로그: _emit_format_logs가 raw 버스로 V-FMT/A-FMT LogEvent 발행."""
    from unittest.mock import patch

    import raw_log

    m = _FakeMain()
    v_list = [
        {"vcodec": "avc1", "height": 1080},
        {"vcodec": "avc1", "height": 720},
        {"vcodec": "vp9", "height": 1080},
    ]
    a_list = [{"acodec": "opus"}, {"acodec": "opus"}, {"acodec": "aac"}]
    sent = []
    with patch.object(raw_log, "raw") as raw:
        main_module.MainWindow._emit_format_logs(m, v_list, a_list, "YT")
        for call in raw.call_args_list:
            sent.append(call.args[1])

    msgs = [ev.msg for ev in sent]
    specs = [ev.spec for ev in sent]
    assert "video: avc1, vp9" in msgs[0]  # 중복 코덱 제거 + 순서 보존
    assert "audio: opus, aac" in msgs[1]
    assert specs == ["V-FMT", "A-FMT"]