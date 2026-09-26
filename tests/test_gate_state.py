"""Task 4-2 RED: GateState 무장/해제 + POT 재시도 URL당 1회 계약 (v3.9.0 신규).

MainWindow의 게이트/분석 워치독 플래그 + POT 재시도 상태를 gate_state.py로
통합 이전한 뒤 검증한다 — Thin Wrapper 금지(§6): 무장/해제 판정 로직 실체가
gate_state 모듈에 존재해야 한다.
"""
from chzzktube.control.gate_state import (
    GateState,
    arm_analysis,
    consume_retry,
    disarm_analysis,
    schedule_retry,
    start_gate,
    stop_gate,
)


class _FakeWatchdog:
    def __init__(self):
        self.resets = 0
        self.heartbeats = 0

    def reset(self):
        self.resets += 1

    def heartbeat(self):
        self.heartbeats += 1


def _state():
    return GateState(_FakeWatchdog(), _FakeWatchdog())


def test_start_gate_resets_and_activates():
    gs = _state()
    assert not gs.gate_active
    start_gate(gs)
    assert gs.gate_active
    assert gs.gate_watchdog.resets == 1


def test_stop_gate_deactivates_without_reset():
    gs = _state()
    start_gate(gs)
    before = gs.gate_watchdog.resets
    stop_gate(gs)
    assert not gs.gate_active
    assert gs.gate_watchdog.resets == before  # watchdog 인스턴스 보존


def test_arm_disarm_analysis():
    gs = _state()
    arm_analysis(gs)
    assert gs.analysis_active
    assert gs.analysis_watchdog.resets == 1
    disarm_analysis(gs)
    assert not gs.analysis_active


def test_schedule_retry_once_per_url():
    gs = _state()
    assert schedule_retry(gs, "https://youtu.be/abc")
    assert gs.pot_retry_pending
    assert not schedule_retry(gs, "https://youtu.be/abc")  # 중복 스케줄 거부
    assert not schedule_retry(gs, "https://youtu.be/abc")  # pending 중 거부
    url = consume_retry(gs)
    assert url == "https://youtu.be/abc"
    assert not gs.pot_retry_pending
    assert gs.pot_retry_url is None
    assert not schedule_retry(gs, "https://youtu.be/abc")  # done 셋에 추가됐으므로 거부
