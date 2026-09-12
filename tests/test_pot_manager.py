"""POTManager 게이트/READY 계약 회귀 테스트.

[배경]
- pot_finished.msg는 "staged"/"ready"/"failed" 상태 토큰으로만 발행해야 한다
  — StartupCoordinator.report_pot이 정확 일치로 READY를 판정한다.
  (사람용 메시지 "prewarm staged"/"pot server bound ..." 발행 시 READY 미개방 회귀 방지)
- 기존 서버 감지(server_ping True) 시 use_existing()으로 즉시 ready 승격 —
  _pending_download 영구 큐잉 방지.
"""
from types import SimpleNamespace

from PySide6.QtCore import QCoreApplication

from pot_manager import POTManager


def _app():
    return QCoreApplication.instance() or QCoreApplication([])


def _manager(mode):
    m = POTManager()
    m._mode = mode
    m._worker = SimpleNamespace()
    return m


def test_gate_ok_emits_ready_token():
    _app()
    m = _manager("gate")
    got = []
    m.pot_finished.connect(lambda ok, msg: got.append((ok, msg)))
    m._on_worker_finished(True, "ignored runtime detail")
    assert m.is_ready() is True
    assert got and got[-1] == (True, "ready")


def test_prewarm_ok_emits_staged_token():
    _app()
    m = _manager("prewarm")
    got = []
    m.pot_finished.connect(lambda ok, msg: got.append((ok, msg)))
    m._on_worker_finished(True, "ignored runtime detail")
    assert m.mode == "staged"
    assert got and got[-1] == (True, "staged")


def test_failure_emits_failed_token():
    _app()
    m = _manager("gate")
    got = []
    m.pot_finished.connect(lambda ok, msg: got.append((ok, msg)))
    m._on_worker_finished(False, "bind fail")
    assert m.is_ready() is False
    assert got and got[-1] == (False, "failed")


def test_use_existing_marks_ready():
    _app()
    m = POTManager()
    m.use_existing()
    assert m.is_ready() is True


def test_prewarm_pending_gate_auto_starts_gate():
    """prewarm 완료 + pending gate → QTimer로 gate 워커 자동 재기동."""
    from unittest.mock import patch

    from PySide6.QtCore import QTimer

    _app()
    m = _manager("prewarm")
    m._pending_gate = True
    scheduled = {}
    started = []

    def _fake_singleshot(delay, fn):
        scheduled["fn"] = fn

    with patch.object(QTimer, "singleShot", side_effect=_fake_singleshot), \
         patch.object(
             POTManager, "_start_worker_locked",
             side_effect=lambda mode: started.append(mode),
         ):
        m._on_worker_finished(True, "ignored runtime detail")

        assert "fn" in scheduled  # gate 재기동 스케줄 확인
        assert m._mode == "staged"
        scheduled["fn"]()  # QTimer 콜백 = _start_pending_gate
        assert started == ["gate"]