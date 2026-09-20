# POTManager
from PySide6.QtCore import QObject, QThread, QTimer, Signal
import threading
import subprocess
import os
from chzzktube.core.log_event import LogEvent
import chzzktube.core.raw_log as raw_log
from chzzktube.core.log_emitter import emit_error_standard, emit_error_warn


class _POTWorker(QThread):
    # [v3.3.0] 로그는 raw 버스 단일 경유 — log_full 시그널 폐기.
    finished_signal = Signal(bool, str)
    # [Followup-1] 빌드 수급 진행 하트비트 — 문자열 없는 무페이로드 신호.
    # MainWindow가 기동 폴백 타이머 연장(defer_fallback_timer)에 사용한다.
    heartbeat = Signal()
    
    def __init__(self, parent=None, mode="prewarm"):
        super().__init__()
        self.mode = mode
        self._abort = False
        self._child_procs = []
        self._server_proc = None
        self.outcome = (False, "")
    
    def request_interruption(self):
        self._abort = True
        # [Followup-2] 자식 트리를 통째로 정리한다 — 종전 loop는 _child_procs가
        # 항상 빈 목록이라(append 0건) 아무것도 죽이지 못했다.
        from chzzktube.infra.pot_server import kill_tree
        for proc in list(self._child_procs):
            kill_tree(proc)
    
    def _tick(self):
        """[Followup-1] 빌드 수급 진행 하트비트 — 폴백 타이머 연장용 무페이로드 신호."""
        self.heartbeat.emit()

    def run(self):
        try:
            self._run()
        except Exception as e:
            self.outcome = (False, f"crash: {e}")
        finally:
            self._cleanup()
            self.finished_signal.emit(self.outcome[0], self.outcome[1])
    
    def _cleanup(self):
        # [Followup-2] 자식 트리도 kill_tree로 정리 — 고아 프로세스 잔존 방지.
        from chzzktube.infra.pot_server import kill_tree
        for proc in list(self._child_procs):
            kill_tree(proc)
        self._child_procs.clear()
        if self._server_proc:
            try:
                kill_tree(self._server_proc)
            except Exception:
                pass
            self._server_proc = None
    
    def _note(self, msg, is_status=False, is_error=False):
        """raw 버스 단일 경유 — 라벨링은 근원에서 LogEvent로 동봉.

        [채널 분기 — 발행자 결정]
        - prewarm 모드: to_tui=False → F12+history 전용 (TUI 오염 방지)
        - gate 모드: to_tui=True → TUI + F12 + history 전부 기록
        """
        if self.mode == "prewarm":
            raw_log.raw("POT", str(msg), is_status=is_status, is_error=is_error)
            return
        stage = "SYS" if is_error else "POT"
        status = "FAIL" if is_error else ("RUN" if is_status else "OK")
        event = LogEvent(stage=stage, status=status, scope="POT",
                         msg=str(msg),
                         is_status=is_status, is_error=is_error)
        raw_log.raw("POT", event, to_tui=True)

    def _dbg(self, msg):
        """raw 버스 단일 경유 — 직접 log_full.emit 금지 (F12 이중 적재 방지).

        [채널 분기 — 발행자 결정]
        - prewarm 모드: to_tui=False → F12+history 전용
        - gate 모드: to_tui=True → TUI + F12 + history 전부 기록
        """
        if self.mode == "prewarm":
            raw_log.raw("POT-DEBUG", str(msg))
        else:
            event = LogEvent(stage="POT", status="RUN", scope="POT",
                             msg=str(msg))
            raw_log.raw("POT", event, to_tui=True)
    
    def _run(self):
        from chzzktube.infra.pot_server import probe_server, latest_server_ver, server_installed_ver
        from chzzktube.infra.pot_server import built_server_js, DEFAULT_HOST, DEFAULT_PORT
        self._dbg(f"POTWorker starting (mode={self.mode})")
        if self.mode == "gate":
            try:
                import chzzktube.infra.components as components
                self._dbg("entering ffmpeg ensure phase")
                ff_err = components.ensure_ffmpeg(self._note)
                if ff_err:
                    # [v3.8.1] 표준 에러 헬퍼로 변환
                    if "binary incompatible" in ff_err.lower() or "not runnable" in ff_err.lower():
                        cause = "binary incompatible"
                        action = "retry mirror (1/3)"
                    elif "all mirrors exhausted" in ff_err.lower():
                        cause = "all mirrors exhausted"
                        action = "check network (F12)"
                    elif "checksum mismatch" in ff_err.lower() or "hash mismatch" in ff_err.lower():
                        cause = "checksum mismatch"
                        action = "retry mirror (1/3)"
                    elif "network" in ff_err.lower() or "timeout" in ff_err.lower() or "connection" in ff_err.lower():
                        cause = "network error"
                        action = "check network (F12)"
                    else:
                        cause = "setup failed"
                        action = "check logs (F12)"
                    self._note(emit_error_standard("DEPS", "FFMP", cause, action), False, True)
                else:
                    self._dbg("ffmpeg fetch done")
            except Exception as ff_ex:
                self._note(emit_error_standard("DEPS", "FFMP", "setup failed", "check logs (F12)", is_error=True), False, True)
        else:
            self._dbg("ffmpeg ensure skipped (prewarm)")
        try:
            from chzzktube.infra.pot_server import clean_stale_plugin
            if clean_stale_plugin():
                self._dbg("stale removed")
        except Exception as cp_ex:
            self._dbg(f"cleanup failed: {cp_ex}")
        self._note("probing server...", True)
        state, detail = probe_server()
        self._dbg(f"probe: state={state!r}")
        if state == "ok":
            self.outcome = (True, f"pot server bound ({DEFAULT_HOST}:{DEFAULT_PORT})")
            return
        remote = latest_server_ver()
        local = server_installed_ver()
        if self.mode == "prewarm":
            self._dbg("prewarm mode — staging to disk, no spawn")
            from chzzktube.infra.pot_server import acquire_prewarm_lock, release_prewarm_lock
            fd = acquire_prewarm_lock(timeout=0, log_func=self._dbg)
            if fd is None:
                self.outcome = (False, "prewarm skipped — build busy")
                return
            try:
                self._note("pot prewarm staging...", True)
                from chzzktube.infra.pot_server import ensure_node_server, server_home, _SERVER_FALLBACK_VER
                ver = remote or local or _SERVER_FALLBACK_VER
                # [A3 수리] "빌드 존재=재빌드" 반전 로직 교정 — 기존 rebuild=have_build는
                # 매 기동마다 npm ci+tsc를 강제했다(HANDOVER §1.3 경량 prewarm 위반).
                # remote·local 버전이 실제 어긋난 스테일일 때만 재빌드한다.
                stale = bool(remote and local and remote != local)
                _, err = ensure_node_server(
                    self._note, self._dbg, ver, rebuild=stale,
                    tick_func=self._tick, proc_registry=self._child_procs,
                )
                if err is None and built_server_js():
                    self.outcome = (True, "prewarm staged")
                else:
                    # [v3.8.1] 표준 에러 헬퍼로 변환
                    if "binary incompatible" in err.lower() or "not runnable" in err.lower():
                        cause = "binary incompatible"
                        action = "retry mirror (1/3)"
                    elif "all mirrors exhausted" in err.lower():
                        cause = "all mirrors exhausted"
                        action = "check network (F12)"
                    elif "checksum mismatch" in err.lower() or "hash mismatch" in err.lower():
                        cause = "checksum mismatch"
                        action = "retry mirror (1/3)"
                    elif "network" in err.lower() or "timeout" in err.lower() or "connection" in err.lower():
                        cause = "network error"
                        action = "check network (F12)"
                    else:
                        cause = "setup failed"
                        action = "check logs (F12)"
                    self._note(emit_error_standard("DEPS", "FFMP", cause, action), is_status=False, is_error=True)
                    self.outcome = (False, f"prewarm fail: {err}")
            finally:
                release_prewarm_lock(fd, log_func=self._dbg)
            return
        if built_server_js():
            self._note("pot server starting...", True)
            from chzzktube.infra.pot_server import _spawn_existing
            proc = _spawn_existing(self._dbg)
            if proc is not None:
                self._server_proc = proc
                self.outcome = (True, f"pot server bound ({DEFAULT_HOST}:{DEFAULT_PORT})")
                return
        # [v3.8.1] 표준 에러 헬퍼로 변환
        self._note(emit_error_standard("DEPS", "FFMP", "bind fail", "check logs (F12)"), is_status=False, is_error=True)
        self.outcome = (False, "bind fail — age-only")
    
    def terminate(self):
        self.request_interruption()
        super().terminate()

class POTManager(QObject):
    # [v3.3.0] 로그는 raw 버스 단일 경유 — log_full 릴레이 시그널 폐기.
    pot_status_changed = Signal(str)
    pot_finished = Signal(bool, str)
    # [Followup-1] 빌드 수급 진행 하트비트 릴레이 — 문자열 없는 무페이로드 신호.
    pot_work_tick = Signal()

    def __init__(self):
        super().__init__()
        self._worker = None
        self._mode = "idle"
        self._pending_gate = False
        self._lock = threading.Lock()
        # [수명 보증] finished_signal(큐잉)은 run()이 아직 반환 전에 도착할 수
        # 있다. 이 시점에 마지막 참조를 끊으면 워커 스레드 자신이 QThread 객체를
        # 파괴하며 Qt qFatal("QThread: Destroyed while thread is still running")
        # → SIGABRT 크래시가 발생한다(2026-09-15 실측). run()이 완전히 반환된
        # 뒤(Qt 내장 finished 발화)까지 참조를 보관하는 대피소.
        self._retiring: list = []

    def _retire(self, worker) -> None:
        """워커를 finished(run() 완전 반환)까지 보관 후 deleteLater로 정리.

        Qt 시그널이 없는 테스트 더블(SimpleNamespace 등)은 보관 대상에서
        제외한다 — 실제 QThread만 수명 보증 대상이다.
        """
        if worker is None:
            return
        is_finished = getattr(worker, "isFinished", None)
        if callable(is_finished) and is_finished():
            return
        finished = getattr(worker, "finished", None)
        if finished is None:
            return
        finished.connect(worker.deleteLater)
        finished.connect(lambda w=worker: self._drop_retired(w))
        self._retiring.append(worker)

    def _drop_retired(self, worker) -> None:
        try:
            self._retiring.remove(worker)
        except ValueError:
            pass

    def ensure_ready(self, mode="gate"):
        if mode not in {"prewarm", "gate"}:
            raise ValueError(f"unknown POT mode: {mode}")
        with self._lock:
            worker = self._worker
            if worker is not None and worker.isRunning():
                if mode == "gate" and self._mode == "prewarm":
                    self._pending_gate = True
                return
            self._start_worker_locked(mode)

    def _start_worker_locked(self, mode: str) -> None:
        self._mode = mode
        worker = _POTWorker(mode=mode)
        self._worker = worker
        worker.finished_signal.connect(self._on_worker_finished)
        # [Followup-1] 빌드 수급 하트비트를 View로 릴레이 — 폴백 타이머 연장에 사용
        worker.heartbeat.connect(self.pot_work_tick)
        worker.start()
        # [모드별 토큰] gate="starting" / prewarm="prewarm" — Coordinator가
        # 이 토큰을 raw 버스에 로그로 남긴다 (의미 왜곡 방지).
        self.pot_status_changed.emit("starting" if mode == "gate" else "prewarm")

    def _on_worker_finished(self, ok: bool, msg: str):
        # Qt may deliver this callback after cancel(); ignore stale workers.
        with self._lock:
            worker = self._worker
            mode = self._mode
            if worker is None or worker is not self._worker:
                return
            if mode == "prewarm":
                if ok and self._pending_gate:
                    self._pending_gate = False
                    self._worker = None
                    self._mode = "staged"
                    self._retire(worker)  # [수명 보증] 조기 반환 경로도 동일
                    QTimer.singleShot(0, self._start_pending_gate)
                    return
                self._worker = None
                self._mode = "staged" if ok else "failed"
            elif mode == "gate":
                self._worker = None
                self._mode = "ready" if ok else "failed"
            else:
                return

        # [토큰 정합] 상태 토큰은 실제 _mode("staged"/"ready")를 그대로 emit —
        # gate 성공을 "staged"로 잘못 보고하던 잠재 버그 수리.
        self.pot_status_changed.emit(self._mode if ok else "failed")
        # [수명 보증] 참조 해제는 run() 완전 반환 이후로 연기 — 워커 스레드가
        # 자기 자신을 파괴하는 SIGABRT 방지.
        self._retire(worker)
        # [READY 게이트 계약] pot_finished의 msg는 상태 토큰("staged"/"ready"/"failed")으로만
        # 발행한다 — StartupCoordinator.report_pot이 정확 일치로 READY를 판정한다.
        # 사람이 읽는 상세 메시지("prewarm staged", "pot server bound ...")는
        # 워커가 이미 로그 버스로 남겼으므로 여기서 중복 전달하지 않는다.
        self.pot_finished.emit(ok, self._mode if ok else "failed")

    def _start_pending_gate(self):
        """완료된 prewarm 워커의 Signal 처리 후 gate 워커를 시작한다."""
        with self._lock:
            if self._mode != "staged" or self._worker is not None:
                return
            self._start_worker_locked("gate")

    @property
    def mode(self):
        return self._mode

    def is_ready(self):
        with self._lock:
            return self._mode == "ready" and self._worker is None

    def use_existing(self):
        """외부/기존 POT 서버가 이미 /ping에 응답 중일 때 ready 상태로 승격.

        이 경로로는 gate 워커가 스폰되지 않으므로 pot_finished가 발행되지
        않는다 — _pending_download가 영구 큐잉되는 것을 막기 위해 즉시 ready로
        표시해야 한다 (Main._wait_pot_if_needed → toggle_download가 확인).
        """
        with self._lock:
            self._worker = None
            self._mode = "ready"

    def is_busy(self):
        return self._worker is not None and self._worker.isRunning()

    def cancel(self):
        with self._lock:
            worker = self._worker
            self._worker = None
            self._mode = "idle"
        if worker and worker.isRunning():
            worker.request_interruption()
            if not worker.wait(2000):
                worker.terminate()
                worker.wait(1000)
        # [수명 보증] wait 타임아웃으로 스레드가 살아있을 수 있다 — 종료 보장 후 해제
        self._retire(worker)