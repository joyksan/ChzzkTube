"""startup_state.py — 앱 시작 시퀀스 상태 단일 공급원 (SRP: 상태만 관리)

[구조] StartupCoordinator, POTManager, MainWindow가 공유하는 불변 상태 컨테이너.
스레드 안전성을 위해 RLock으로 보호하며, 상태 전이 메서드만 제공.
단계별 순차 비교(phase.value >) 대신 플래그 조합으로 동시성 안전성 확보.
"""
import threading
from dataclasses import dataclass, field


@dataclass(slots=True)
class StartupState:
    """앱 시작 시퀀스 상태 단일 공급원."""
    
    # 단계별 완료 플래그
    deps_ok: bool = False
    upgrade_done: bool = False
    pot_status: str = "unknown"   # unknown/running/standby/staged/failed
    pot_ready: bool = False
    ready_emitted: bool = False
    
    # 내부 동기화
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    # ── 상태 변경 메서드 (RLock 보호) ──────────────────────────
    
    def set_deps(self, ok: bool) -> None:
        with self._lock:
            self.deps_ok = ok

    def set_upgrade(self, done: bool) -> None:
        with self._lock:
            self.upgrade_done = done

    def set_pot(self, status: str, ready: bool | None = None) -> None:
        with self._lock:
            self.pot_status = status
            if ready is not None:
                self.pot_ready = ready

    def mark_ready_emitted(self) -> None:
        with self._lock:
            self.ready_emitted = True

    # ── 판정 메서드 ────────────────────────────────────────
    
    def can_emit_ready(self) -> bool:
        """READY 발산 조건 충족 여부."""
        with self._lock:
            return (
                self.deps_ok
                and self.upgrade_done
                and self.pot_ready
                and not self.ready_emitted
            )

    def is_ready(self) -> bool:
        with self._lock:
            return self.ready_emitted

    def snapshot(self) -> dict:
        """디버깅용 상태 스냅샷."""
        with self._lock:
            return {
                "deps_ok": self.deps_ok,
                "upgrade_done": self.upgrade_done,
                "pot_status": self.pot_status,
                "pot_ready": self.pot_ready,
                "ready_emitted": self.ready_emitted,
            }