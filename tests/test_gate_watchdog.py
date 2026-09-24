"""POT 게이트의 만료 기준은 View의 LivenessWatchdog 하나다."""
from types import SimpleNamespace
from unittest.mock import Mock

from chzzktube.core.watchdog import GATE_TIMEOUT_SEC, LivenessWatchdog
from chzzktube.ui.main_window import MainWindow


def gate_view():
    now = [0.0]
    view = SimpleNamespace(
        _startup_completed=True,
        _gate_watchdog_active=False,
        _gate_watchdog=LivenessWatchdog(GATE_TIMEOUT_SEC, clock=lambda: now[0]),
        _analysis_watchdog_active=False,
        _analysis_watchdog=Mock(check_timeout=Mock(return_value=False)),
        _pot_manager=Mock(),
        _pending_download=(['url'], 'auto', 'auto'),
        append_concise_log=Mock(),
        update_ui_state=Mock(),
        defer_fallback_timer=Mock(),
    )
    view._pot_manager.is_busy.return_value = True
    for name in ('_start_gate_watchdog', '_stop_gate_watchdog', '_on_gate_timeout',
                 '_poll_watchdogs', '_on_pot_work_tick', '_ensure_gate_state',
                 '_arm_analysis_watchdog', '_disarm_analysis_watchdog',
                 '_on_analysis_timeout', '_maybe_retry_analysis', '_run_pending_retry'):
        method = getattr(MainWindow, name, None)
        if method is not None:
            setattr(view, name, method.__get__(view))
    # Initialize GateState first, then set retry state directly on GateState
    # to avoid property shadowing issues with SimpleNamespace test double.
    view._ensure_gate_state()
    view._gate_state.pot_retry_pending = True
    view._gate_state.pot_retry_url = 'url'
    view._pot_manager.is_busy.return_value = True
    return view, now


def test_gate_progress_extends_single_deadline():
    view, now = gate_view()
    view._start_gate_watchdog()
    now[0] = GATE_TIMEOUT_SEC - 1
    view._on_pot_work_tick()
    now[0] = GATE_TIMEOUT_SEC + 1
    view._poll_watchdogs()
    view._pot_manager.cancel.assert_not_called()
    now[0] += GATE_TIMEOUT_SEC
    view._poll_watchdogs()
    view._pot_manager.cancel.assert_called_once()
    assert not view._gate_watchdog_active
    assert view._pending_download is None
    # Access retry state through gate_state since it's stored there
    assert not view._gate_state.pot_retry_pending
    assert view._gate_state.pot_retry_url is None


def test_late_progress_does_not_restart_stopped_gate():
    view, now = gate_view()
    view._start_gate_watchdog()
    view._stop_gate_watchdog()
    now[0] = 1000
    view._on_pot_work_tick()
    view._poll_watchdogs()
    assert not view._gate_watchdog_active
    view._pot_manager.cancel.assert_not_called()
    assert view._gate_watchdog.elapsed() == 1000


def test_gate_clears_pending_retry_before_cancel_callback():
    view, now = gate_view()
    view._start_gate_watchdog()
    observed = []
    view._pot_manager.cancel.side_effect = lambda: observed.append(
        (view._gate_watchdog_active, view._gate_state.pot_retry_pending, view._pending_download)
    )
    now[0] = GATE_TIMEOUT_SEC + 1
    view._poll_watchdogs()
    assert observed == [(False, False, None)]
