"""기동 게이트 회귀 테스트 (v3.5.2) — READY 폴백 결함 수리 검증.

[배경]
1. P1: `_on_update_check_done`이 `report_deps(not bool(stale))`로 보고해, 업데이트가
   감지된 기동은 deps_ok=False로 겨 정상 READY가 열리지 않았다.
2. P2: `UpdateWorker.run()`의 예외 분기가 upgrade 모드에서도 check_done을 발화했다.
   upgrade 커의 check_done은 구독자가 0이므로 upgrade_done이 영구 미발화 →
   `can_emit_ready()`의 upgrade_done 항이 False로 고정 → READY가 15초 폴백으로만 열렸다.
3. P3b: `get_current_app_state()`가 POT is_busy를 STARTUP 사유로 삼아, 프리웜 진행 중
   ENTER가 `toggle_download`의 큐잉 분기에 도달하지 못하고 무반응이었다.

테스트 관례는 tests/test_analyze_state.py(가벼운 self 대역)와
tests/test_pot_manager.py(QCoreApplication)를 따른다 — 헤드리스 위젯 생성 금지.
"""
from types import SimpleNamespace
from unittest.mock import Mock

import chzzktube
from PySide6.QtCore import QCoreApplication

from chzzktube.control.controller import MediaController
from chzzktube.workers.update_worker import UpdateWorker

import chzzktube.ui.main_window as main_module

# 게이트 하드닝 상수 — 소스와 값이 어긋나면 테스트가 즉시 잡아낸다.
_FALLBACK_GRACE_MS = main_module._FALLBACK_GRACE_MS
_POT_GATE_TIMEOUT_MS = main_module._POT_GATE_TIMEOUT_MS


def _app():
    return QCoreApplication.instance() or QCoreApplication([])


class _SignalStub:
    """시그널 대역 — connect 접수 슬롯을 기록해 배선을 검증할 수 있게 한다."""

    def __init__(self):
        self.slots = []

    def connect(self, slot, *a, **k):
        self.slots.append(slot)
        return None


class _WorkerStub:
    """UpdateWorker 대역 — 생성 인자와 start() 호출만 기록."""

    def __init__(self, *a, **k):
        self.args = a
        self.kwargs = k
        self.check_done = _SignalStub()
        self.upgrade_done = _SignalStub()
        self.work_tick = _SignalStub()
        self.started = 0

    def start(self, *a, **k):
        self.started += 1


class _FakeInput:
    def __init__(self, text=""):
        self._text = text

    def text(self):
        return self._text

    def setText(self, t):
        self._text = t


class _CheckDoneFake:
    """`_on_update_check_done`만 실제 MainWindow 구현으로 바인딩한 대역."""

    def __init__(self):
        self.cfg = {"update_channel": "stable", "auto_update_check": True}
        self._startup_coord = Mock()
        self._pot_manager = SimpleNamespace(ensure_ready=lambda m: None)
        self.update_worker = None
        self.logs = []
        self.deferred = []
        self._stale_updates = None

    def _on_update_check_done(self, stale):
        return main_module.MainWindow._on_update_check_done(self, stale)

    def append_concise_log(self, *a, **k):
        self.logs.append(a[0] if a else None)

    def _retire_qthread(self, worker):
        pass

    def defer_fallback_timer(self, extension_ms=15000):
        """[P5] 실제 슬롯 대역 — work_tick 배선이 요구하는 시그니처."""
        self.deferred.append(extension_ms)


class _DlFake:
    """`get_current_app_state`/`toggle_download`만 실제 구현으로 바인딩한 대역."""

    def __init__(self):
        self.ctrl = MediaController(self)
        self._startup_completed = True
        self._pot_manager = SimpleNamespace(
            is_busy=lambda: True,
            is_ready=lambda: False,
            use_existing=lambda: None,
            ensure_ready=lambda *a, **k: None,
        )
        self.url_input = _FakeInput("https://youtu.be/abcDEFghijk")
        self.extracted_data = {
            "info": {"age_limit": 19, "availability": "needs_auth", "is_live": False},
            "v_list": [],
            "a_list": [],
        }
        self.cfg = {"pick_format": False}
        self._pending_download = None
        self.logs = []

    def get_current_app_state(self):
        return main_module.MainWindow.get_current_app_state(self)

    def toggle_download(self):
        main_module.MainWindow.toggle_download(self)

    def append_concise_log(self, *a, **k):
        ev = a[0] if a else None
        self.logs.append(getattr(ev, "msg", str(ev)))

    def _start_download(self, *a):
        raise AssertionError("POT 대기 중인데 즉시 다운로드가 시작됨")


# ── P1: deps 게이트 배선 ─────────────────────────────────────────────


def test_check_done_reports_deps_true_even_on_stale(monkeypatch):
    """stale 감지 기동에서도 deps 게이트는 '검사 완료'=True로 보고된다."""
    fake = _CheckDoneFake()
    monkeypatch.setattr(main_module, "UpdateWorker", _WorkerStub)
    fake._on_update_check_done([("ytdlp", "yt-dlp", "2026.8.1", "2026.8.19")])
    assert fake._startup_coord.report_deps.call_count == 1
    ok_arg, msg_arg = fake._startup_coord.report_deps.call_args[0]
    assert ok_arg is True
    assert msg_arg == "update"


def test_check_done_reports_deps_true_when_clean(monkeypatch):
    fake = _CheckDoneFake()
    monkeypatch.setattr(main_module, "UpdateWorker", _WorkerStub)
    fake._on_update_check_done([])
    ok_arg, msg_arg = fake._startup_coord.report_deps.call_args[0]
    assert (ok_arg, msg_arg) == (True, "deps ok")
    # [P5] 업그레이드 워커의 수급 하트비트가 폴백 타이머 연장 슬롯에 배선된다
    assert fake.update_worker.work_tick.slots == [fake.defer_fallback_timer]


# ── P2: 워커 크래시 종료 시그널 분기 ─────────────────────────────────


def test_upgrade_worker_crash_emits_upgrade_done(monkeypatch):
    """upgrade 모드 크래시는 upgrade_done을 발화한다(check_done 오발행 금지)."""
    _app()
    worker = UpdateWorker(upgrade=True)
    got = []
    worker.upgrade_done.connect(lambda ok, msg: got.append((ok, msg)))

    def _boom(self, *a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(UpdateWorker, "_do_upgrade", _boom)
    worker.run()
    assert got == [(False, "worker crash")]


def test_check_worker_crash_still_emits_check_done(monkeypatch):
    """check 모드 크래시는 기존 복구 경로(check_done([]))를 그대로 탄다."""
    _app()
    worker = UpdateWorker(upgrade=False)
    got = []
    worker.check_done.connect(lambda stale: got.append(stale))

    def _boom(self, *a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(UpdateWorker, "_do_check", _boom)
    worker.run()
    assert got == [[]]


# ── P3b: is_busy는 입력 잠금 사유가 아니다 ───────────────────────────


def test_state_idle_while_pot_busy():
    fake = SimpleNamespace(
        _startup_completed=True,
        _pot_manager=SimpleNamespace(is_busy=lambda: True),
        ctrl=SimpleNamespace(running=False, analyzing=False, picking=False),
    )
    assert main_module.MainWindow.get_current_app_state(fake) == "IDLE"


def test_state_startup_before_unlock():
    fake = SimpleNamespace(
        _startup_completed=False,
        _pot_manager=SimpleNamespace(is_busy=lambda: False),
        ctrl=SimpleNamespace(running=False, analyzing=False, picking=False),
    )
    assert main_module.MainWindow.get_current_app_state(fake) == "STARTUP"


def test_toggle_download_queues_while_pot_busy():
    """프리웜 진행 중 ENTER는 큐잉 분기로 진입해 대기한다(사문 코드 부활 증명)."""
    fake = _DlFake()
    fake.toggle_download()
    assert fake._pending_download is not None
    assert fake._pending_download[1:] == ("auto", "auto")
    assert any("queued" in line for line in fake.logs)


# ── P5: 동적 치독(백 타이머 연장) ───────────────────────────────


class _FakeTimer:
    """QTimer 대역 — start() 호출을 결정적으로 기록한다."""

    def __init__(self, active=True):
        self.active = active
        self.starts = []

    def isActive(self):
        return self.active

    def start(self, ms):
        self.starts.append(ms)
        self.active = True


class _TimerFake:
    """`_fallback_timer`만 보유한 경량 대역."""

    def __init__(self, startup_completed=False, start=True):
        self._startup_completed = startup_completed
        self._fallback_timer = _FakeTimer(active=start)
        if start:
            self._fallback_timer.start(15000)

    def defer_fallback_timer(self, extension_ms: int = 15000):
        return main_module.MainWindow.defer_fallback_timer(self, extension_ms)

    def _on_pot_activity(self, status):
        return main_module.MainWindow._on_pot_activity(self, status)


def test_defer_fallback_timer_extends_while_startup():
    """수급 진행 하트비트는 15초 폴백 카운트다운을 되감는다."""
    fake = _TimerFake()
    assert fake._fallback_timer.starts == [15000]
    fake.defer_fallback_timer(15000)
    assert fake._fallback_timer.starts == [15000, 15000]


def test_defer_fallback_timer_noop_after_unlock_or_fired():
    # READY가 이미 열린 뒤에는 되살리지 않는다(타이머 재시작 0회)
    done = _TimerFake(startup_completed=True)
    done.defer_fallback_timer()
    assert done._fallback_timer.starts == [15000]
    # 폴백이 이미 발화한 뒤(타이머 비활성)에도 되살리지 않는다
    fired = _TimerFake(start=False)
    fired.defer_fallback_timer()
    assert fired._fallback_timer.starts == []


def test_pot_activity_defers_only_for_prewarm_phase():
    fake = _TimerFake()
    fake._on_pot_activity("staged")
    assert fake._fallback_timer.starts == [15000]  # 전환 토큰은 연장 사유 아님
    fake._on_pot_activity("prewarm")
    assert fake._fallback_timer.starts == [15000, 15000]


def test_work_tick_fires_only_on_real_provisioning():
    """하트비트는 실제 다운로드/설치 동사에서만 발화한다(로그 신호 아님)."""
    _app()
    worker = UpdateWorker(upgrade=True)
    ticks = []
    worker.work_tick.connect(lambda: ticks.append(1))
    worker._tick("Downloading yt_dlp-2026.8.19-py3-none-any.whl (3.1 MB)")
    worker._tick("Requirement already satisfied: streamlink")
    assert len(ticks) == 1


# ── Followup-2/3/4/5/6: 게이트 하드닝 회귀 ──────────────────────────


class _GateFake:
    """게이트 하드닝(워치독·유예·재시도) 검증용 경량 대역."""

    def __init__(self, *, pot_busy=False, pot_ready=True, worker_running=False,
                 startup_completed=False, timer_active=True, url="https://youtu.be/abcDEFghijk"):
        from unittest.mock import Mock

        self._startup_completed = startup_completed
        self._pot_manager = SimpleNamespace(
            is_busy=lambda: pot_busy,
            is_ready=lambda: pot_ready,
            mode="prewarm" if pot_busy else "idle",
            cancel=lambda: self.canceled.append(1),
            ensure_ready=lambda *a, **k: self.ensure_ready_calls.append(a),
        )
        self.update_worker = SimpleNamespace(isRunning=lambda: worker_running)
        self._fallback_timer = _FakeTimer(active=timer_active)
        self._gate_watchdog = _FakeTimer(active=False)
        self._startup_coord = Mock()
        self.url_input = _FakeInput(url)
        self._deps_failed = []
        self._pending_download = None
        self._pot_retry_pending = False
        self._pot_retry_url = None
        self._pot_retry_done = set()
        self.canceled = []
        self.ensure_ready_calls = []
        self.logs = []

    def _force_unlock_input(self):
        return main_module.MainWindow._force_unlock_input(self)

    def _startup_chain_active(self):
        return main_module.MainWindow._startup_chain_active(self)

    def _log_gate_pending(self, reason):
        return main_module.MainWindow._log_gate_pending(self, reason)

    def _start_gate_watchdog(self):
        self._gate_watchdog.start(_POT_GATE_TIMEOUT_MS)

    def _on_gate_timeout(self):
        return main_module.MainWindow._on_gate_timeout(self)

    def _maybe_retry_analysis(self, err_msg):
        return main_module.MainWindow._maybe_retry_analysis(self, err_msg)

    def append_concise_log(self, *a, **k):
        ev = a[0] if a else None
        self.logs.append(getattr(ev, "msg", str(ev)))

    def update_ui_state(self):
        pass


def test_gate_watchdog_cancels_pot_and_clears_queue(monkeypatch):
    """[Followup-3] gate hang 시 POT를 트리 종료하고 대기 큐를 해제한다."""
    import chzzktube.core.raw_log as raw_log

    monkeypatch.setattr(raw_log, "raw", lambda *a, **k: None)  # 전역 버스 오염 격리
    fake = _GateFake(pot_busy=True)
    fake._pending_download = (["https://youtu.be/x"], "auto", "auto")
    fake._on_gate_timeout()
    assert fake.canceled == [1]
    assert fake._pending_download is None
    assert any("gate timeout" in line for line in fake.logs)


def test_gate_watchdog_noop_when_pot_idle(monkeypatch):
    import chzzktube.core.raw_log as raw_log

    monkeypatch.setattr(raw_log, "raw", lambda *a, **k: None)  # 전역 버스 오염 격리
    fake = _GateFake()
    fake._on_gate_timeout()
    assert fake.canceled == []


def test_fallback_grace_defers_when_chain_active(monkeypatch):
    """[Followup-4] 체인이 실제로 동작 중이면 폴백을 1회 유예한다."""
    import chzzktube.core.raw_log as raw_log

    monkeypatch.setattr(raw_log, "raw", lambda *a, **k: None)
    fake = _GateFake(pot_busy=True)
    fake._force_unlock_input()
    assert fake._startup_coord.force_unlock.call_count == 0
    assert fake._fallback_timer.starts == [_FALLBACK_GRACE_MS]  # 유예로 재무장
    assert getattr(fake, "_fallback_grace_used") is True


def test_fallback_fires_after_grace_when_chain_idle(monkeypatch):
    import chzzktube.core.raw_log as raw_log

    monkeypatch.setattr(raw_log, "raw", lambda *a, **k: None)
    fake = _GateFake(worker_running=True)
    fake._force_unlock_input()  # 유예(체인 동작 중)
    fake.update_worker.isRunning = lambda: False
    fake._force_unlock_input()  # 유예 후 재판정 → 개방
    assert fake._startup_coord.force_unlock.call_count == 1


def test_deps_fail_promoted_to_gate(monkeypatch):
    """[Followup-5] DEPS 실제 FAIL은 게이트를 막는다(stale은 막지 않는다)."""
    import chzzktube.core.raw_log as raw_log

    monkeypatch.setattr(raw_log, "raw", lambda *a, **k: None)  # 전역 버스 오염 격리
    fake = _GateFake()
    main_module.MainWindow._on_deps_failed(fake, ["ytdlp"])
    assert fake._deps_failed == ["ytdlp"]
    # 수집된 FAIL 목록이 report_deps(False) 승격의 근거가 된다(_on_update_check_done).


def test_needs_pot_retry_detection():
    """[Followup-6] 봇 체크/PO 토큰 사유만 재시도 대상으로 판별한다."""
    assert main_module._needs_pot_retry("Sign in to confirm you're not a bot") is True
    assert main_module._needs_pot_retry("ERROR: po token provider failed") is True
    assert main_module._needs_pot_retry("HTTP Error 404: Not Found") is False
    assert main_module._needs_pot_retry("") is False


def test_bot_retry_schedules_once_and_blocks_loop(monkeypatch):
    """[Followup-6] 재시도는 URL당 1회 — 재실패 시 루프를 만들지 않는다."""
    import chzzktube.core.raw_log as raw_log

    monkeypatch.setattr(raw_log, "raw", lambda *a, **k: None)
    fake = _GateFake(pot_ready=False)
    first = fake._maybe_retry_analysis("Sign in to confirm you're not a bot")
    second = fake._maybe_retry_analysis("Sign in to confirm you're not a bot")
    assert (first, second) == (True, False)
    assert fake.ensure_ready_calls == [("gate",)]
    assert fake._pot_retry_pending is True
    assert fake._pot_retry_done == {"https://youtu.be/abcDEFghijk"}