"""시작 시퀀스 단일 책임자 — Signal 경유, POTManager + raw 버스 연동."""

from __future__ import annotations

import threading
from PySide6.QtCore import QObject, Signal

from startup_state import StartupState
from pot_manager import POTManager


class StartupCoordinator(QObject):
    """기동 시퀀스 게이트.

    [Signal 기반]
    - Worker → Coordinator: report_*() (thread-safe)
    - Coordinator → View: ready_emitted / pot_status_changed / ui_unlocked (Qt Signal)
    - Coordinator → raw 버스: raw() (TUI=to_tui + F12 + history 전량)

    [구성 요소]
    - StartupState: 단일 상태 (thread-safe)
    - POTManager: POT 서버 수명주기 (prewarm + gate)
    - raw_log: 로그 라우팅 (라벨링은 여기서 LogEvent로 동봉)
    """

    # ── View로의 Signal ──────────────────────────────────────
    ready_emitted = Signal(str, bool, str)  # (stage, is_status, msg)
    pot_status_changed = Signal(str)
    ui_unlocked = Signal()

    def __init__(self, pot_manager: POTManager, parent=None):
        super().__init__()
        self._pot = pot_manager
        self._state = StartupState()
        self._lock = threading.RLock()
        self._fallback_done = False

        # POTManager 시그널 연결
        self._pot.pot_status_changed.connect(self._on_pot_status)
        self._pot.pot_finished.connect(self._on_pot_finished)

    # ── 버스 발행 (근원 라벨링 단일 경유) ─────────────────────

    def _emit(self, stage, status, msg, is_status=False, is_error=False):
        """READY/READY 경고 등 기동 라인을 LogEvent로 동봉해 버스로 발행."""
        import raw_log
        from log_event import LogEvent
        raw_log.raw(
            "startup",
            LogEvent(stage=stage, status=status, platform="SYS", msg=msg,
                     is_status=is_status, is_error=is_error),
            to_tui=True,
        )

    # ── Worker → Coordinator 보고 ────────────────────────────

    def report_deps(self, ok: bool, msg: str = ""):
        with self._lock:
            self._state.set_deps(ok)
            self._try_emit_ready()

    def report_upgrade(self, ok: bool, summary: str):
        with self._lock:
            self._state.set_upgrade(True)
            if summary:
                self._emit("SYS", "OK" if ok else "FAIL", f"update {summary}",
                           is_error=not ok)
            self._try_emit_ready()

    def report_pot(self, ok: bool, msg: str):
        with self._lock:
            status = msg if ok else "failed"
            # 실제 POTManager 완료 신호는 ``staged``/``ready``만 사용한다.
            # 기존 테스트/호출부의 ``standby`` 보고는 공개 영상용 준비 완료로만
            # 호환 처리하며, 임의의 성공 메시지는 READY 게이트를 열지 않는다.
            ready = ok and (status == "staged" or status == "ready" or status == "standby")
            self._state.set_pot(status, ready=ready)
            self._try_emit_ready()

    def report_ready(self, ok: bool = True, msg: str = "ready"):
        with self._lock:
            if self._state.ready_emitted:
                return
            self._state.mark_ready_emitted()
            self._emit("SYS", "READY" if ok else "WARN", msg)
            self.ready_emitted.emit("SYS", False, msg)
            self.ui_unlocked.emit()

    # ── POTManager 시그널 핸들러 ──────────────────────────────

    def _on_pot_status(self, status: str):
        self.pot_status_changed.emit(status)

    def _on_pot_finished(self, ok: bool, msg: str):
        self.report_pot(ok, msg)

    # ── 강제 READY (15초 폴백) ────────────────────────────────

    def force_unlock(self):
        with self._lock:
            if self._fallback_done:
                return
            self._fallback_done = True
        self._pot.cancel()
        self.report_ready(True, "ready (fallback timeout)")

    # ── READY 발산 게이트 ────────────────────────────────────

    def _try_emit_ready(self):
        with self._lock:
            if self._state.can_emit_ready():
                self._state.mark_ready_emitted()
                self._emit("SYS", "READY", "ready")
                self.ready_emitted.emit("SYS", False, "ready")
                self.ui_unlocked.emit()

    # ── 테스트 호환 프로퍼티 ──────────────────────────────────

    @property
    def _ready_emitted(self):
        return self._state.ready_emitted

    @_ready_emitted.setter
    def _ready_emitted(self, value):
        self._state.ready_emitted = value