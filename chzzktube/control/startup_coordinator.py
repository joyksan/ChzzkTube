"""시작 시퀀스 단일 책임자 — Signal 경유, POTManager + raw 버스 연동."""

from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Signal

from chzzktube.control.pot_manager import POTManager
from chzzktube.control.startup_state import StartupState
from chzzktube.core import raw_log
from chzzktube.core.log_emitter import emit_error_standard


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

        # POTManager 시그널 연결
        self._pot.pot_status_changed.connect(self._on_pot_status)
        self._pot.pot_finished.connect(self._on_pot_finished)

    # ── 버스 발행 (근원 라벨링 단일 경유) ─────────────────────

    def _emit(self, stage, status, msg, is_status=False, is_error=False):
        """READY/READY 경고 등 기동 라인을 LogEvent로 동봉해 버스로 발행."""
        from chzzktube.core import raw_log
        from chzzktube.core.log_event import LogEvent
        raw_log.raw(
            "startup",
            LogEvent(stage=stage, status=status, scope="MAIN", msg=msg,
                     is_status=is_status, is_error=is_error),
            to_tui=True,
        )

    # ── Worker → Coordinator 보고 ────────────────────────────

    # ── Worker → Coordinator 보고 ────────────────────────────

    def report_deps(self, ok: bool, msg: str = ""):
        with self._lock:
            # [v3.8.1] deps 실패 시 영구 실패 고정 — 한 번 실패면 끝 (최소값 원칙)
            if not ok and not self._state.deps_error_msg:
                self._state.deps_error_msg = msg
                self._state.deps_ok = False
            elif ok and not self._state.deps_error_msg:
                # 실패 기록이 없을 때만 성공으로 갱신
                self._state.deps_ok = True
            self._try_emit_ready()

    def report_upgrade(self, ok: bool, summary: str):
        with self._lock:
            self._state.set_upgrade(True)
            if ok:
                # 업그레이드 성공 시 초기 미설치로 인한 deps 에러 리셋 및 정상화
                self._state.set_deps(True)
                self._state.deps_error_msg = ""
                if summary:
                    self._emit("SYS", "OK", f"update {summary}")
            else:
                self._state.set_deps(False)
                if not self._state.deps_error_msg:
                    self._state.deps_error_msg = summary or "update failed"
                raw_log.raw(
                    "startup",
                    emit_error_standard("SYS", "MAIN", "update failed", "check logs (F12)"),
                    to_tui=True,
                )
            self._try_emit_ready()

    def report_pot(self, ok: bool, msg: str):
        with self._lock:
            status = msg if ok else "failed"
            # [HANDOVER §9.4] prewarm 완료(staged) 및 gate 완료(ready) 시 pot_ready=True 승격
            ready = ok and status in ("ready", "staged")
            self._state.set_pot(status, ready=ready)
            if not ok:
                # [v3.8.1] POT 실패 시 표준 에러 헬퍼 사용
                from chzzktube.core.log_emitter import emit_error_standard
                raw_log.raw(
                    "startup",
                    emit_error_standard("POT", "POT", "server failed", "check logs (F12)"),
                    to_tui=True,
                )
            self._try_emit_ready()

    def report_ready(self, ok: bool = True, msg: str = "ready — input unlocked"):
        with self._lock:
            if self._state.ready_emitted:
                return
            self._state.mark_ready_emitted()
            self._emit("SYS", "READY" if ok else "WARN", msg)
            self.ready_emitted.emit("SYS", False, msg)
            self.ui_unlocked.emit()

    # ── POTManager 시그널 핸들러 ──────────────────────────────

    def _on_pot_status(self, status: str):
        # View로만 포워드하던 것을 raw 버스에도 태워 TUI/F12/history에 남긴다.
        # [토글 계약] 시동 → 가동 → lazy 대기 전환이 메인/풀 로그에 모두 기록된다
        # (앱 동작 전량 기록 원칙 — HANDOVER §9).
        self.pot_status_changed.emit(status)
        if status == "failed":
            # [중복 방지] 실패 시의 TUI 안내는 직후 _on_pot_finished -> report_pot()에서
            # check logs (F12) 표준 에러 포맷으로 1회만 단일 발행한다.
            return
        from chzzktube.core.log_emitter import emit_event
        from chzzktube.core.raw_log import raw
        _POT_TOGGLE = {
            "prewarm":  ("RUN",  "server staging..."),
            "starting": ("RUN",  "server starting..."),
            "staged":   ("OK",   "server staged — lazy standby"),
            "ready":    ("OK",   "server running"),
        }
        st, msg = _POT_TOGGLE.get(status, ("RUN", str(status)))
        raw(
            "startup",
            emit_event("POT", st, "POT", msg, is_error=(st == "FAIL")),
            to_tui=True,
        )

    def _on_pot_finished(self, ok: bool, msg: str):
        self.report_pot(ok, msg)

    # ── READY 발산 게이트 ────────────────────────────────────

    def _try_emit_ready(self):
        with self._lock:
            if self._state.can_emit_ready():
                self._state.mark_ready_emitted()
                self._emit("SYS", "READY", "ready — input unlocked")
                self.ready_emitted.emit("SYS", False, "ready — input unlocked")
                self.ui_unlocked.emit()

    # ── 테스트 호환 프로퍼티 ──────────────────────────────────

    @property
    def _ready_emitted(self):
        return self._state.ready_emitted

    @_ready_emitted.setter
    def _ready_emitted(self, value):
        self._state.ready_emitted = value