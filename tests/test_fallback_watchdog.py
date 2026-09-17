"""기동 폴백의 만료 기준은 _fallback_timer 하나다.

[배경] 15초 폴백을 QTimer와 LivenessWatchdog가 각자 판정했다. QTimer가 발화해
Followup-4 유예(3초)로 재무장한 직후, 1초 주기 폴링 워치독이 자체 유예를 소진하고
_force_unlock_input을 재호출해 유예를 끊었다. 폴링 판정을 제거해 이중 만료를
정리한다 — 폴백 수명을 바꾸는 것은 진행 하트비트(defer)와 1회 유예뿐이다.
"""
from types import SimpleNamespace

from chzzktube.ui import main_window as main_module
from chzzktube.ui.main_window import MainWindow


class _View:
    """폴백 판정 경로만 실제 구현으로 바인딩한 대역."""

    def __init__(self):
        self.starts = []
        self.unlock_calls = []
        self._startup_completed = False
        self._fallback_grace_used = False
        self._gate_watchdog_active = False
        self._gate_watchdog = SimpleNamespace(check_timeout=lambda: False)
        self._analysis_watchdog_active = False
        self._analysis_watchdog = SimpleNamespace(check_timeout=lambda: False)
        self._fallback_timer = SimpleNamespace(isActive=lambda: True, start=self.starts.append)
        self._pot_manager = SimpleNamespace(is_busy=lambda: True, mode="prewarm")
        self.update_worker = None
        self._deps_failed = []
        self._startup_coord = SimpleNamespace(force_unlock=self.unlock_calls.append)
        self._log_gate_pending = lambda reason: None
        self._on_gate_timeout = lambda: None
        self._on_analysis_timeout = lambda: None

    def _poll_watchdogs(self):
        return MainWindow._poll_watchdogs(self)

    def _force_unlock_input(self):
        return MainWindow._force_unlock_input(self)

    def _startup_chain_active(self):
        return MainWindow._startup_chain_active(self)


def test_poll_does_not_judge_fallback_expiry():
    """폴링은 폴백 만료를 판정하지 않는다 — 단일 기준은 _fallback_timer다."""
    view = _View()
    view._poll_watchdogs()
    assert view.unlock_calls == []


def test_fallback_grace_survives_poll_ticks():
    """[Followup-4] 유예 재무장 직후 폴링 틱이 유예를 끊지 않는다(이중 판정 회귀)."""
    view = _View()
    view._force_unlock_input()  # 체인 동작 중 → 1회 유예로 재무장
    assert view.starts == [main_module._FALLBACK_GRACE_MS]
    assert view.unlock_calls == []

    for _ in range(5):  # 유예 3초 동안 폴링이 여러 번 지나가도 개방하지 않는다
        view._poll_watchdogs()
    assert view.unlock_calls == []
