"""시작 시퀀스 단일 책임자 - 시그널 교통정리 및 READY 로그 중앙 관리"""

from __future__ import annotations

import threading
from PySide6.QtCore import QObject
from log_console import format_log_line
from startup_state import StartupState


class StartupCoordinator(QObject):
    """
    시작 시퀀스의 모든 단계를 중앙에서 관리.
    
    책임:
    1. Worker 스레드에서 오는 시그널을 1차 수신 (thread-safe)
    2. 중복 제거 및 순서 보장
    3. READY 로그를 정확히 한 번만 출력 (콘솔 + F12 + 히스토리)
    4. 3대 로그 시스템에 동시 전파
    """
    
    def __init__(self, main_window):
        super().__init__()
        self._view = main_window
        # [RLock 필수] report_* 메서드가 lock을 잡은 상태에서 _try_emit_ready가
        # 재차 lock을 획득하므로 재진입 가능한 Lock이어야 한다 (Lock은 deadlock).
        self._lock = threading.RLock()
        # 상태는 StartupState로 위임 (단일 진실 공급원)
        self._state = StartupState()
        # 테스트 호환용 별칭 (기존 속성 접근 유지)
        self._ready_emitted = False
        self._fallback_done = False

    # 테스트 호환용 프로퍼티
    @property
    def _ready_emitted(self):
        return self._state.ready_emitted

    @_ready_emitted.setter
    def _ready_emitted(self, value):
        self._state.ready_emitted = value

    @property
    def _stage_complete(self):
        """테스트 호환용: _state를 dict처럼 동작하게 하는 프록시"""
        class StageProxy:
            def __init__(self, state):
                self._state = state
            def __getitem__(self, key):
                if key == "deps": return self._state.deps_ok
                if key == "upgrade": return self._state.upgrade_done
                if key == "pot": return self._state.pot_status != "unknown"
                if key == "fallback": return getattr(self, "_fallback_done", False)
                return False
            def __setitem__(self, key, value):
                if key == "deps": self._state.set_deps(value)
                elif key == "upgrade": self._state.set_upgrade(value)
                elif key == "pot": self._state.set_pot(value if value else "unknown")
                elif key == "fallback": self._fallback_done = value
        return StageProxy(self._state)
    
    def _emit_log(self, stage: str, status: str, platform: str, spec: str, msg: str, 
                  is_status: bool = False, is_error: bool = False):
        """
        3대 로그 시스템에 동시에 출력.
        
        Args:
            stage: DEPS, SYS, ANAL 등
            status: OK, READY, FAIL, WARN 등
            platform: YTDL, FFMP 등 (will be shortened)
            spec: 버전 등
            msg: 메시지
            is_status: 진행 상태 표시 (덮어쓰기 모드)
            is_error: 오류 상태
        """
        # 로그 라인 생성
        line = format_log_line(
            stage=stage,
            status=status,
            platform=platform,
            spec=spec,
            speed="-",
            pct=None,
            bar_frac=None,
            msg=msg
        )
        
        # [히스토리 2중 기록 방지] append_concise_log가 is_status=False 라인의
        # 히스토리 기록을 이미 담당 — 여기서 또 쓰면 2건 적재된다.
        self._view.append_concise_log(line, is_status=is_status, is_error=is_error)
    
    def report_deps(self, ok: bool, msg: str = ""):
        """DEPS 체크 완료 보고 — 플래그만 세팅.

        [중복 방지] DEPS 개별 5줄(YTDL/STRE/FFMP/NODE/POT)은 UpdateWorker.line
        → _component_line 경로에서, 결론 라인(deps ok / update —)은
        _on_update_check_done에서 이미 출력된다. 여기서 또 찍으면 3중 출력.
        """
        with self._lock:
            self._state.set_deps(ok)
            self._try_emit_ready()

    def report_upgrade(self, ok: bool, summary: str):
        """업그레이드 완료 보고 — 변화가 있었을 때만 결론 1줄 출력."""
        with self._lock:
            self._state.set_upgrade(True)
            if summary:  # 변화가 있었으면 결론 라인 출력 (없으면 침묵)
                status = "OK" if ok else "FAIL"
                self._emit_log("SYS", status, "DEPS", "-", f"update {summary}",
                               is_status=False, is_error=not ok)
            self._try_emit_ready()

    def report_pot(self, ok: bool, msg: str):
        """POT 기동 완료 보고 — 플래그만 세팅 (라인은 _component_line 경유)."""
        with self._lock:
            self._state.set_pot(msg if ok else "failed")
            self._try_emit_ready()

    def report_ready(self, ok: bool = True, msg: str = "ready"):
        """강제 READY 발산 — 15초 폴백 타이머용. 기존 READY는 무시."""
        with self._lock:
            if self._ready_emitted:
                return
            self._ready_emitted = True
            self._emit_log("SYS", "READY" if ok else "WARN", "SYS", "-", msg,
                           is_status=False, is_error=False)
            self._view.add_concise_task_separator()
            # [순서 고정] 플래그를 먼저 세워야 update_ui_state()가
            # url_input.setEnabled(True)로 판단한다 (역순이면 영구 lock).
            self._view._startup_completed = True
            self._view.update_ui_state()

    def _on_force_unlock(self):
        """15초 폴백 타이머 타임아웃 — 강제 READY."""
        with self._lock:
            if self._stage_complete["fallback"]:
                return
            self._stage_complete["fallback"] = True
            self._stage_msgs["fallback"] = "input unlocked (timeout)"
        self.report_ready(True, "ready (fallback timeout)")
    
    def _try_emit_ready(self):
        """
        모든 필수 단계가 완료되면 READY 로그 출력.
        순서: DEPS → (upgrade 시 upgrade 완료) → POT (필요 시) → READY
        """
        with self._lock:
            # READY 중복 방지
            if self._ready_emitted:
                return
            
            # 필수 단계 확인 - View 역참조 제거, 플래그 기반으로 전환
            deps_ok = self._stage_complete["deps"]
            upgrade_ok = self._stage_complete["upgrade"]
            # POT은 _stage_complete["pot"]로만 판단 (View 플래그 역참조 제거)
            pot_ok = self._stage_complete["pot"]
            # 폴백은 선택적
            
            if deps_ok and upgrade_ok and pot_ok:
                # 모든 단계 완료 - READY 출력
                self._ready_emitted = True
                self._emit_log("SYS", "READY", "SYS", "-", "ready", is_status=False, is_error=False)

                # 작업 로그와 구분하기 위한 separator
                self._view.add_concise_task_separator()

                # [순서 고정] 플래그를 먼저 세워야 update_ui_state()가
                # url_input.setEnabled(True)로 판단한다 (역순이면 영구 lock).
                self._view._startup_completed = True

                # UI 상태 업데이트 (입력 잠금 해제 등)
                self._view.update_ui_state()