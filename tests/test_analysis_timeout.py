"""분석 타임아웃 계약 — 뷰 단독 소유, 워커는 무페이로드 하트비트만.

[배경] 종전에는 워커가 자기 `LivenessWatchdog`을 만들고 아무도 검사하지 않았으며
(`ANALYSIS_TIMEOUT_SEC` 미import + 죽은 `_timeout_timer.stop()` + 미연결
`_on_analysis_timeout`), 뷰의 워치독은 리셋·하트비트가 없어 앱 시작 45초 뒤부터
매초 "analysis timeout" 로그를 흘렸다.

[계약]
1. 워커는 `activity`(무페이로드)만 발행한다 — §5-21.
2. Controller가 `analyze_activity`로 포워딩하고, 유기 시 연결을 끊는다.
3. 뷰가 리셋·판정·복구를 단독 수행한다: `_on_analysis_timeout()`은
   워커 유기 + FAIL 1줄 마감, 강제 terminate 금지.
4. 분석 시작 때만 감시를 활성화하고 성공·실패·취소·만료 시 해제한다.
   비활성 감시는 폴링에서 만료를 재판정하지 않는다.

"""
from types import SimpleNamespace

from PySide6.QtCore import QObject, Signal

import chzzktube.control.controller as controller_module
from chzzktube.control.controller import MediaController

import chzzktube.ui.main_window as main_module


class _StubAnalyzer(QObject):
    """AnalyzeWorker 대역 — 실제 시그널만 제공하고 스레드는 시작하지 않는다."""

    result_ready = Signal(dict)
    error_occurred = Signal(str)
    activity = Signal()
    finished = Signal()

    def __init__(self, *args, **kwargs):
        super().__init__()
        self.args = args
        self.started = 0
        self._running = True

    def start(self):
        self.started += 1

    def isRunning(self):
        return self._running


class _FakeInput:
    def __init__(self, text=""):
        self._text = text

    def text(self):
        return self._text

    def setText(self, text):
        self._text = text


class _TimeoutFake:
    """`_on_analysis_timeout`만 실제 구현으로 바인딩한 대역."""

    def __init__(self, analyzing=True):
        self.abandoned = 0
        self.logs = []
        self.ui_updates = 0
        self.ctrl = SimpleNamespace(
            analyzing=analyzing,
            abandon_analysis=self._abandon,
            state={"picking": True},
        )
        self.url_input = _FakeInput("https://youtu.be/abcDEFghijk")
        self._analysis_watchdog_active = True

    def _abandon(self):
        self.abandoned += 1
        self.ctrl.analyzing = False

    def update_ui_state(self):
        self.ui_updates += 1

    def append_concise_log(self, *args, **kwargs):
        event = args[0] if args else None
        self.logs.append(getattr(event, "msg", str(event)))

    def _platform_of_url(self):
        return "YT"

    def _disarm_analysis_watchdog(self):
        return main_module.MainWindow._disarm_analysis_watchdog(self)

    def _on_analysis_timeout(self):
        return main_module.MainWindow._on_analysis_timeout(self)


# ── 1~2: 워커/컨트롤러 계약 ───────────────────────────────────────────


def test_controller_forwards_worker_activity(monkeypatch):
    """워커 activity → Controller.analyze_activity 포워딩."""
    monkeypatch.setattr(controller_module, "AnalyzeWorker", _StubAnalyzer)
    ctrl = MediaController(SimpleNamespace())
    ctrl.spawn_analyzer("https://youtu.be/abcDEFghijk", {})

    assert ctrl.worker_analyze.started == 1
    ticks = []
    ctrl.analyze_activity.connect(lambda: ticks.append(1))
    ctrl.worker_analyze.activity.emit()
    assert ticks == [1]


def test_abandon_analysis_disconnects_activity(monkeypatch):
    """유기된 워커의 늦은 하트비트가 뷰 워치독을 되살리지 않는다."""
    monkeypatch.setattr(controller_module, "AnalyzeWorker", _StubAnalyzer)
    ctrl = MediaController(SimpleNamespace())
    ctrl.spawn_analyzer("https://youtu.be/abcDEFghijk", {})
    worker = ctrl.worker_analyze

    ticks = []
    ctrl.analyze_activity.connect(lambda: ticks.append(1))
    worker.activity.emit()
    assert ticks == [1]

    ctrl.abandon_analysis()
    assert ctrl.worker_analyze is None
    assert ctrl.state["analyzing"] is False

    worker.activity.emit()  # 늦은 하트비트
    assert ticks == [1]
    assert ctrl._zombie_workers == [worker]


# ── 3~4: 뷰 복구 계약 ────────────────────────────────────────────────


def test_view_timeout_recovers_and_logs_once():
    fake = _TimeoutFake(analyzing=True)
    fake._on_analysis_timeout()

    assert fake.abandoned == 1
    assert fake.ui_updates == 1
    assert len(fake.logs) == 1, fake.logs
    assert "analysis timeout" in fake.logs[0]
    assert fake._analysis_watchdog_active is False  # 만료 1회 판정 뒤 해제


def test_view_timeout_noop_when_not_analyzing():
    fake = _TimeoutFake(analyzing=False)
    fake._on_analysis_timeout()

    assert fake.abandoned == 0
    assert fake.logs == []
    assert fake.ui_updates == 0
    assert fake._analysis_watchdog_active is False  # 재판정 루프 차단


# ── 6: 무장/해제 계약 — 게이트·폴백과 동일 (만료의 영속 재판정 금지) ──


def test_poll_skips_disarmed_expired_watchdog():
    """마감된 분석의 만료는 폴링에서 재판정되지 않는다."""
    fake = _PollFake()
    fake._analysis_watchdog_active = False
    fake._poll_watchdogs()
    assert fake.timeout_calls == 0


class _ArmFake:
    """스폰 3곳의 무장 계약 검증용 대역."""

    def __init__(self):
        self.resets = []
        self.spawns = []
        self.cfg = {}

        self._analysis_watchdog_active = False
        self._analysis_watchdog = SimpleNamespace(reset=lambda: self.resets.append(1))
        self.url_input = _FakeInput("https://youtu.be/abcDEFghijk")
        self.ctrl = SimpleNamespace(spawn_analyzer=lambda *a, **k: self.spawns.append(a))
        self.base_anim_url = ""

    def _arm_analysis_watchdog(self):
        return main_module.MainWindow._arm_analysis_watchdog(self)

    def append_concise_log(self, *a, **k):
        pass

    def update_ui_state(self):
        pass


def test_spawn_sites_arm_analysis_watchdog():
    """분석 스폰 3곳은 모두 워치독을 명시적으로 무장한다."""
    fake = _ArmFake()
    fake._discard_analysis_result = lambda: None
    main_module.MainWindow.run_analysis(fake)
    assert fake.resets == [1]
    assert fake._analysis_watchdog_active is True
    assert len(fake.spawns) == 1

    fake = _ArmFake()
    main_module.MainWindow._start_pick_flow(fake, "https://youtu.be/abcDEFghijk")
    assert fake.resets == [1]
    assert fake._analysis_watchdog_active is True

    fake = _ArmFake()
    fake._pot_retry_url = "https://youtu.be/abcDEFghijk"
    fake._pot_retry_pending = True
    main_module.MainWindow._run_pending_retry(fake)
    assert fake.resets == [1]
    assert fake._analysis_watchdog_active is True


class _EndFake:
    """분석 마감(성공/실패) 경로의 해제 계약 검증용 대역."""

    def __init__(self):
        self.ctrl = SimpleNamespace(state={"analyzing": True}, running=False, picking=False)
        self.url_input = _FakeInput("https://youtu.be/abcDEFghijk")
        self.extracted_data = {"info": None, "v_list": [], "a_list": []}
        self._pick_pending = False
        self._analysis_watchdog_active = True

    def _disarm_analysis_watchdog(self):
        return main_module.MainWindow._disarm_analysis_watchdog(self)

    def _is_stale_analyze_signal(self):
        return main_module.MainWindow._is_stale_analyze_signal(self)

    def stop_analysis_anim(self, ok=True):
        pass

    def update_ui_state(self):
        pass

    def append_concise_log(self, *a, **k):
        pass

    def _ensure_pot_for_info(self, info):
        pass

    def _maybe_retry_analysis(self, err_msg):
        return False


def test_analysis_end_disarms_watchdog():
    """성공·실패 마감 모두 워치독을 해제한다."""
    fake = _EndFake()
    main_module.MainWindow.on_analyze_success(fake, {"info": {}})
    assert fake._analysis_watchdog_active is False

    fake = _EndFake()
    main_module.MainWindow.on_analyze_error(fake, "boom")
    assert fake._analysis_watchdog_active is False


# ── 5: 폴링 분기 ────────────────────────────────────────────────────


class _DeadWatchdog:
    def check_timeout(self):
        return False


class _ExpiredWatchdog:
    def check_timeout(self):
        return True


class _InactiveTimer:
    def isActive(self):
        return False


class _PollFake:
    """`_poll_watchdogs`만 실제 구현으로 바인딩한 대역."""

    def __init__(self):
        self._startup_completed = True
        self._gate_watchdog = _DeadWatchdog()
        self._gate_watchdog_active = False
        self._analysis_watchdog = _ExpiredWatchdog()
        self._analysis_watchdog_active = True
        self.timeout_calls = 0

    def _force_unlock_input(self):
        raise AssertionError("폴백이 잘못 발화")

    def append_concise_log(self, *a, **k):
        pass

    def _on_analysis_timeout(self):
        self.timeout_calls += 1

    def _poll_watchdogs(self):
        return main_module.MainWindow._poll_watchdogs(self)


def test_poll_dispatch_calls_analysis_timeout():
    """분석 워치독 만료가 복구 경로로 디스패치된다(로그만 남기던 회귀 차단)."""
    fake = _PollFake()
    fake._poll_watchdogs()
    assert fake.timeout_calls == 1


def test_timeout_polling_stops_until_next_analysis():
    """만료 복구는 1회이며 재분석은 이전 만료와 독립된 기한을 갖는다."""
    from unittest.mock import Mock
    from chzzktube.core.watchdog import ANALYSIS_TIMEOUT_SEC, LivenessWatchdog

    now = [0.0]
    fake = _TimeoutFake()
    fake._gate_watchdog_active = False
    fake._analysis_watchdog = LivenessWatchdog(
        ANALYSIS_TIMEOUT_SEC, clock=lambda: now[0]
    )
    fake._on_analysis_timeout = Mock(wraps=fake._on_analysis_timeout)
    main_module.MainWindow._arm_analysis_watchdog(fake)

    now[0] = ANALYSIS_TIMEOUT_SEC + 1
    main_module.MainWindow._poll_watchdogs(fake)
    for _ in range(5):
        now[0] += 100
        main_module.MainWindow._poll_watchdogs(fake)
    fake._on_analysis_timeout.assert_called_once()
    assert fake.abandoned == 1
    assert len(fake.logs) == 1

    fake.ctrl.analyzing = True
    main_module.MainWindow._arm_analysis_watchdog(fake)
    main_module.MainWindow._poll_watchdogs(fake)
    assert fake._on_analysis_timeout.call_count == 1
    now[0] += ANALYSIS_TIMEOUT_SEC + 1
    main_module.MainWindow._poll_watchdogs(fake)
    assert fake._on_analysis_timeout.call_count == 2
    assert fake.abandoned == 2
