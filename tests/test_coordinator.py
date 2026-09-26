"""chzzktube.control.startup_coordinator 단위 테스트 — 기동 시퀀스 게이트 로직."""
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
        coord.report_pot(True, "ready")  # POT 단계 완료 필요
        assert coord._ready_emitted is True

    def test_ready_not_emitted_before_upgrade(self, coord):
        coord.report_deps(True, "deps ok")
        assert coord._ready_emitted is False

    def test_duplicate_upgrade_no_double_ready(self, coord):
        coord.report_deps(True, "deps ok")
        coord.report_upgrade(True, "")
        coord.report_pot(True, "ready")
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
        coord.report_pot(True, "ready")
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

        from chzzktube.core import raw_log

        events = []
        raw_log.subscribe_concise(
            lambda ev, is_status, is_error: events.append(ev)
        )
        raw_log.subscribe_full(
            lambda ev: events.append(ev)
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

        from chzzktube.core import raw_log

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
class TestDepsGateSemantics:
    """[P1 회귀] deps 게이트의 의미는 "검사 단계 완료" — stale 존재가 READY를 잠그지 않는다.

    종전 배선은 `report_deps(not bool(stale), ...)`였다 → 업데이트가 감지되는 모든
    기동에서 deps_ok=False로 고정되어 정상 READY가 영원히 열리지 않고, 15초 폴백
    문구("ready — input unlocked (fallback timeout)")로만 입력이 풀렸다.
    """

    def test_stale_does_not_block_ready(self, coord):
        coord.report_deps(True, "update")  # stale 감지된 기동
        coord.report_upgrade(True, "yt-dlp updated")
        coord.report_pot(True, "ready")
        assert coord._ready_emitted is True


class TestForceUnlockRemoved:
    """[v3.8.1] force_unlock 제거 검증 — 폴백 제거로 READY는 deps 성공 시에만."""

    def test_no_force_unlock_method(self):
        """force_unlock 메서드가 없음 — 폴백 제거."""
        pot = Mock()
        coord = StartupCoordinator(pot)
        assert not hasattr(coord, "force_unlock")

    def test_ready_blocked_by_deps_error(self):
        """deps 에러 시 READY 차단."""
        pot = Mock()
        coord = StartupCoordinator(pot)
        coord.report_deps(False, "ffmpeg: not found")
        # READY 발산 시도 시 차단되어야 함
        coord._try_emit_ready()
        assert coord._ready_emitted is False
