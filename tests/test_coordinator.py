"""chzzktube.control.startup_coordinator 단위 테스트 — 기동 시퀀스 게이트 로직."""
import chzzktube
from unittest.mock import Mock

import pytest

from chzzktube.control.startup_coordinator import StartupCoordinator


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

    def test_ready_not_emitted_for_arbitrary_pot_success_message(self, coord):
        coord.report_deps(True, "deps ok")
        coord.report_upgrade(True, "")
        coord.report_pot(True, "prewarm staged")
        assert coord._ready_emitted is False

    def test_ready_after_prewarm_staged(self, coord):
        coord.report_deps(True, "deps ok")
        coord.report_upgrade(True, "")
        coord.report_pot(True, "staged")
        assert coord._ready_emitted is True

    def test_ready_after_pot_gate_ready_token(self, coord):
        # POTManager가 gate 완료 시 발행하는 "ready" 토큰으로 READY 개방
        coord.report_deps(True, "deps ok")
        coord.report_upgrade(True, "")
        coord.report_pot(True, "ready")
        assert coord._ready_emitted is True


class TestForceUnlock:
    def test_force_unlock_emits_ready(self, coord):
        coord.report_ready(True, "ready (fallback timeout)")
        assert coord._ready_emitted is True

    def test_force_unlock_idempotent(self, coord):
        coord.report_ready(True, "first")
        coord.report_ready(True, "second")
        # 두 번째 호출은 무시
        assert coord._ready_emitted is True


class TestPotStatusBusWiring:
    """[회귀 v3.4.0] pot_status_changed → raw 버스 배선 검증.

    기존엔 Coordinator가 Signal만 포워드하고 아무도 로그로 남기지 않아
    POT 시동→가동→lazy 전환 토글이 메인/풀 로그에 전부 누락됐다
    (앱 동작 전량 기록 원칙 위반). 이제는 raw 버스에 반드시 기록된다.
    """

    def test_pot_status_wired_to_raw_bus(self):
        import time

        import chzzktube.core.raw_log as raw_log

        events = []
        raw_log.subscribe_concise(
            lambda ev, is_status, is_error: events.append(ev)
        )
        coord = StartupCoordinator(Mock())
        coord._on_pot_status("staged")

        deadline = time.time() + 2.0
        while time.time() < deadline and not events:
            time.sleep(0.02)
        assert events, "POT 상태 변경이 raw 버스에 기록되지 않음"
        ev = events[-1]
        assert ev.stage == "POT"
        assert ev.status == "OK"
        assert "lazy" in ev.msg

    def test_pot_failed_maps_to_fail_status(self):
        import time

        import chzzktube.core.raw_log as raw_log

        events = []
        raw_log.subscribe_concise(
            lambda ev, is_status, is_error: events.append(ev)
        )
        coord = StartupCoordinator(Mock())
        coord._on_pot_status("failed")

        deadline = time.time() + 2.0
        while time.time() < deadline and not events:
            time.sleep(0.02)
        ev = [e for e in events if getattr(e, "stage", "") == "POT"][-1]
        assert ev.status == "FAIL"
        assert ev.is_error is True