"""startup_coordinator 단위 테스트 — 기동 시퀀스 게이트 로직."""
from unittest.mock import Mock

import pytest

from startup_coordinator import StartupCoordinator


@pytest.fixture
def coord():
    view = Mock()
    view.append_concise_log = Mock()
    view.add_concise_task_separator = Mock()
    view.update_ui_state = Mock()
    view._pot_provider_started = False
    view._prewarm_pending = False
    view._startup_completed = False
    return StartupCoordinator(view)


class TestReadyEmission:
    def test_ready_after_deps_and_upgrade(self, coord):
        coord.report_deps(True, "deps ok")
        coord.report_upgrade(True, "")
        coord.report_pot(True, "standby")  # POT 단계 완료 필요
        assert coord._ready_emitted is True

    def test_ready_not_emitted_before_upgrade(self, coord):
        coord.report_deps(True, "deps ok")
        assert coord._ready_emitted is False

    def test_duplicate_upgrade_no_double_ready(self, coord):
        coord.report_deps(True, "deps ok")
        coord.report_upgrade(True, "")
        coord.report_pot(True, "standby")
        first = coord._ready_emitted
        coord.report_upgrade(True, "late")
        assert coord._ready_emitted == first  # 여전히 True, 중복 아님


class TestForceUnlock:
    def test_force_unlock_emits_ready(self, coord):
        coord.report_ready(True, "ready (fallback timeout)")
        assert coord._ready_emitted is True

    def test_force_unlock_idempotent(self, coord):
        coord.report_ready(True, "first")
        coord.report_ready(True, "second")
        # 두 번째 호출은 무시
        assert coord._ready_emitted is True