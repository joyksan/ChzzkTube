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


def test_view_timeout_noop_when_not_analyzing():
    fake = _TimeoutFake(analyzing=False)
    fake._on_analysis_timeout()

    assert fake.abandoned == 0
    assert fake.logs == []
    assert fake.ui_updates == 0


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
        self._fallback_watchdog = _DeadWatchdog()
        self._gate_watchdog = _DeadWatchdog()
        self._gate_watchdog_active = False
        self._analysis_watchdog = _ExpiredWatchdog()
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
