"""폴백 제거 후 동작 검증.

[v3.8.1] 폴백(15초 강제 언락) 완전 제거 → deps 수급 실패 시 영구 잠금.
"""
from unittest.mock import Mock

from chzzktube.control.pot_manager import POTManager
from chzzktube.control.startup_coordinator import StartupCoordinator
from chzzktube.ui.main_window import MainWindow


def test_deps_error_keeps_input_locked():
    """[v3.8.1] deps 에러 시 입력 잠금 유지 — 폴백 제거로 영구 잠금."""
    pot_mock = Mock(spec=POTManager)
    coord = StartupCoordinator(pot_mock)

    unlocked_spy = Mock()
    ready_spy = Mock()
    coord.ui_unlocked.connect(unlocked_spy)
    coord.ready_emitted.connect(ready_spy)

    # 의존성 실패 보고
    coord.report_deps(False, "ffmpeg: dyld symbol not found")

    assert coord._state.deps_error_msg == "ffmpeg: dyld symbol not found"
    assert coord._state.deps_ok is False
    assert coord._state.ready_emitted is False
    unlocked_spy.assert_not_called()
    ready_spy.assert_not_called()


def test_no_fallback_timer_in_main_window():
    """[v3.8.1] MainWindow에 폴백 타이머가 없으므로 _fallback_timer 속성 없음."""
    assert not hasattr(MainWindow, "_fallback_timer")
    assert not hasattr(MainWindow, "_force_unlock_input")
