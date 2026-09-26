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

from chzzktube.control.pot_manager import POTManager, _POTWorker


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


def test_pot_worker_tick_emits_heartbeat():
    """[Followup-1] 빌드 수급 하트비트는 무페이로드 신호로 릴레이된다."""
    _app()
    w = _POTWorker(mode="prewarm")
    got = []
    w.heartbeat.connect(lambda: got.append(1))
    w._tick()
    assert got == [1]


def test_worker_registry_feeds_kill_tree():
    """[Followup-2] _POTWorker가 자식 프로세스를 레지스트리에 등록해 취소 시 정리한다."""
    _app()
    w = _POTWorker(mode="prewarm")
    assert w._child_procs == []

    class _Proc:
        killed = 0

        def kill(self):
            self.killed += 1

    proc = _Proc()
    w._child_procs.append(proc)
    w.request_interruption()
    assert proc.killed == 1  # kill_tree 경유(직접 kill 폴백)


def test_worker_finished_keeps_reference_until_finished():
    """[회귀 v3.4.0 SIGABRT] finished_signal 처리 시 워커 참조가 즉시 끊기지 않는다.

    finished_signal(큐잉)은 run()이 아직 반환 전에 도착할 수 있다 — 이때
    마지막 참조를 끊으면 워커 스레드 자신이 QThread 객체를 파괴하며
    Qt qFatal("QThread: Destroyed while thread is still running") →
    SIGABRT 크래시가 발생했다(2026-09-15 _POTWorker 실측). _retire가
    run() 완전 반환까지 참조를 보관하는지 검증한다.
    """
    from chzzktube.control.pot_manager import _POTWorker

    _app()
    m = POTManager()
    w = _POTWorker(mode="gate")
    m._worker = w
    m._mode = "gate"
    m._on_worker_finished(True, "x")
    assert w in m._retiring   # 수명 보증 — 워커가 즉시 파괴되지 않음
    assert m._worker is None  # 다음 워커 기동은 막히지 않음
    assert m.mode == "ready"


def test_gate_ok_emits_ready_status_token():
    """[회귀 v3.4.0] gate 성공 시 pot_status_changed도 실제 모드 "ready"를 emit.

    기존엔 무조건 "staged"를 emit해 gate 완료를 prewarm 완료로 오보고했다
    (Coordinator 토글 로그가 "staged — lazy standby"로 잘못 기록됨).
    """
    _app()
    m = _manager("gate")
    got = []
    m.pot_status_changed.connect(got.append)
    m._on_worker_finished(True, "ignored runtime detail")
    assert got and got[-1] == "ready"


def test_prewarm_ok_emits_staged_status_token():
    _app()
    m = _manager("prewarm")
    got = []
    m.pot_status_changed.connect(got.append)
    m._on_worker_finished(True, "ignored runtime detail")
    assert got and got[-1] == "staged"


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