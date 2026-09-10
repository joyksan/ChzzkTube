"""시작 시퀀스 단일 책임자 — Signal 경유, POTManager + LogBus 연동."""

from __future__ import annotations

import threading
from PySide6.QtCore import QObject, Signal

from log_bus import emit as log_bus_emit, Channel
from startup_state import StartupState
from log_console import format_log_line
from pot_manager import POTManager


class StartupCoordinator(QObject):
    """기동 시퀀스 게이트.

    [Signal 기반]
    - Worker → Coordinator: report_*() (thread-safe)
    - Coordinator → View: ready_emitted / pot_status_changed / ui_unlocked (Qt Signal)
    - Coordinator → LogBus: emit() (TUI + F12 + history)

    [구성 요소]
    - StartupState: 단일 상태 (thread-safe)
    - POTManager: POT 서버 수명주기 (prewarm + gate)
    - LogBus: 로그 라우팅
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

    # ── View로의 Signal ──────────────────────────────────────
    ready_emitted = Signal(str, bool, str)  # (stage, is_status, msg)
    pot_status_changed = Signal(str)
    ui_unlocked = Signal()

    # ── Worker → Coordinator 보고 ────────────────────────────

    def report_deps(self, ok: bool, msg: str = ""):
        with self._lock:
            self._state.set_deps(ok)
            self._try_emit_ready()

    def report_upgrade(self, ok: bool, summary: str):
        with self._lock:
            self._state.set_upgrade(True)
            if summary:
                line = format_log_line(
                    stage="SYS", status="OK" if ok else "FAIL",
                    platform="DEPS", spec="-", speed="-",
                    pct=None, bar_frac=None, msg=f"update {summary}",
                )
                log_bus_emit(line, Channel.BOTH,
                             is_status=False, is_error=not ok)
            self._try_emit_ready()

    def report_pot(self, ok: bool, msg: str):
        with self._lock:
            self._state.set_pot(msg if ok else "failed")
            self._try_emit_ready()

    def report_ready(self, ok: bool = True, msg: str = "ready"):
        with self._lock:
            if self._state.ready_emitted:
                return
            self._state.mark_ready_emitted()
            line = format_log_line(
                stage="SYS", status="READY" if ok else "WARN",
                platform="SYS", spec="-", speed="-",
                pct=None, bar_frac=None, msg=msg,
            )
            log_bus_emit(line, Channel.BOTH,
                         is_status=False, is_error=False)
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
                line = format_log_line(
                    stage="SYS", status="READY", platform="SYS",
                    spec="-", speed="-", pct=None, bar_frac=None, msg="ready",
                )
                log_bus_emit(line, Channel.BOTH,
                             is_status=False, is_error=False)
                self.ready_emitted.emit("SYS", False, "ready")
                self.ui_unlocked.emit()

    # ── 테스트 호환 프로퍼티 ──────────────────────────────────

    @property
    def _ready_emitted(self):
        return self._state.ready_emitted

    @_ready_emitted.setter
    def _ready_emitted(self, value):
        self._state.ready_emitted = value

    @property
    def _stage_complete(self):
        class StageProxy:
            def __init__(self, state):
                self._state = state
            def __getitem__(self, key):
                if key == "deps": return self._state.deps_ok
                if key == "upgrade": return self._state.upgrade_done
                if key == "pot": return self._state.pot_status != "unknown"
                if key == "fallback": return getattr(self, "_fb", False)
                return False
            def __setitem__(self, key, value):
                if key == "deps": self._state.set_deps(value)
                elif key == "upgrade": self._state.set_upgrade(value)
                elif key == "pot": self._state.set_pot(value if value else "unknown")
                elif key == "fallback": self._fb = value
        return StageProxy(self._state)