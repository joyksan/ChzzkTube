"""gate_state — MainWindow에서 추출한 게이트·분석 워치독 무장/해제·POT 재시도 상태.

[Task 4-2] MainWindow(1667행)의 게이트/분석 워치독 플래그 + POT 재시도 상태를
통합 컨테이너로 이전 — 상태 변수 개별 초기화 금지(§6) 준수.

Thin Wrapper 금지(§6) 준수: MainWindow 메서드는 이 모듈 함수에 위임하는
호환 바인딩만 유지하며, 무장/해제 판정 로직의 실체는 여기에 존재한다.

Qt 무의존 — LivenessWatchdog 인스턴스는 MainWindow.__init__에서 생성해
주입받는다 (테스트 주입 가능).
"""
from __future__ import annotations

from typing import Any


class GateState:
    """POT 게이트 + 분석 워치독 무장/해제 + POT 재시도 상태 컨테이너."""

    def __init__(self, gate_watchdog: Any, analysis_watchdog: Any):
        # 게이트 워치독 — POT gate 대기 시간 초과 판정
        self.gate_watchdog = gate_watchdog
        self.gate_active = False
        # 분석 워치독 — AnalyzeWorker 무페이로드 하트비트 연장
        self.analysis_watchdog = analysis_watchdog
        self.analysis_active = False
        # POT 봇 체크 재시도 상태 (URL당 1회 계약)
        self.pot_retry_pending: bool = False
        self.pot_retry_url: str | None = None
        self.pot_retry_done: set[str] = set()


# ── 게이트 무장/해제 ──────────────────────────────────────────────────

def start_gate(gate_state: GateState) -> None:
    """게이트 워치독 무장 — reset + active 플래그 설정."""
    gate_state.gate_watchdog.reset()
    gate_state.gate_active = True


def stop_gate(gate_state: GateState) -> None:
    """게이트 워치독 해제 — active 플래그 해제 (watchdog 인스턴스는 보존)."""
    gate_state.gate_active = False


def on_pot_work_tick(gate_state: GateState) -> None:
    """실제 POT 진행만 활성 게이트를 연장한다. 완료 후에는 재무장하지 않는다."""
    if gate_state.gate_active:
        gate_state.gate_watchdog.heartbeat()


# ── 분석 워치독 무장/해제 ────────────────────────────────────────────

def arm_analysis(gate_state: GateState) -> None:
    """분석 워치독 무장 — reset + active 플래그 설정."""
    gate_state.analysis_watchdog.reset()
    gate_state.analysis_active = True


def disarm_analysis(gate_state: GateState) -> None:
    """분석 워치독 해제 — active 플래그 해제 (성공·실패·취소·만료 시)."""
    gate_state.analysis_active = False


# ── POT 재시도 상태 ─────────────────────────────────────────────────

def clear_retry(gate_state: GateState) -> None:
    """POT 재시도 상태 초기화 — gate timeout/cancel 시 호출."""
    gate_state.pot_retry_pending = False
    gate_state.pot_retry_url = None


def schedule_retry(gate_state: GateState, url: str) -> bool:
    """봇 체크 재시도 스케줄 — URL당 1회 계약. 이미 스케줄됐으면 False."""
    if gate_state.pot_retry_pending:
        return False
    if not url or url in gate_state.pot_retry_done:
        return False
    gate_state.pot_retry_done.add(url)
    gate_state.pot_retry_url = url
    gate_state.pot_retry_pending = True
    return True


def consume_retry(gate_state: GateState) -> str | None:
    """재시도 대기 URL 회수 — pending 해제 후 URL 반환, 없으면 None."""
    url = gate_state.pot_retry_url
    gate_state.pot_retry_pending = False
    gate_state.pot_retry_url = None
    return url
