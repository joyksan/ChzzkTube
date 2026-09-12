# POTManager
from PySide6.QtCore import QObject, QThread, QTimer, Signal
import threading
import subprocess
import os
from log_event import LogEvent
import raw_log


class _POTWorker(QThread):
    # [v3.3.0] 로그는 raw 버스 단일 경유 — log_full 시그널 폐기.
    finished_signal = Signal(bool, str)
    
    def __init__(self, parent=None, mode="prewarm"):
        super().__init__()
        self.mode = mode
        self._abort = False
        self._child_procs = []
        self._server_proc = None
        self.outcome = (False, "")
    
    def request_interruption(self):
        self._abort = True
        for proc in self._child_procs:
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
    
    def run(self):
        try:
            self._run()
        except Exception as e:
            self.outcome = (False, f"crash: {e}")
        finally:
            self._cleanup()
            self.finished_signal.emit(self.outcome[0], self.outcome[1])
    
    def _cleanup(self):
        for proc in self._child_procs:
            try: proc.kill()
            except: pass
        self._child_procs.clear()
        if self._server_proc:
            try:
                from pot_server import _kill
                _kill(self._server_proc)
            except: pass
            self._server_proc = None
    
    def _note(self, msg, is_status=False, is_error=False):
        """raw 버스 단일 경유 — 라벨링은 근원에서 LogEvent로 동봉.

        [채널 분기 — 발행자 결정]
        - prewarm 모드: to_tui=False → F12+history 전용 (TUI 오염 방지)
        - gate 모드: to_tui=True → TUI + F12 + history 전부 기록
        """
        if self.mode == "prewarm":
            raw_log.raw("pot", str(msg), is_status=is_status, is_error=is_error)
            return
        stage = "SYS" if is_error else "POT"
        status = "FAIL" if is_error else ("RUN" if is_status else "OK")
        event = LogEvent(stage=stage, status=status, scope="POT",
                         msg=str(msg)[:120],
                         is_status=is_status, is_error=is_error)
        raw_log.raw("pot", event, to_tui=True)

    def _dbg(self, msg):
        """raw 버스 단일 경유 — 직접 log_full.emit 금지 (F12 이중 적재 방지).

        [채널 분기 — 발행자 결정]
        - prewarm 모드: to_tui=False → F12+history 전용
        - gate 모드: to_tui=True → TUI + F12 + history 전부 기록
        """
        if self.mode == "prewarm":
            raw_log.raw("pot-DEBUG", str(msg))
        else:
            event = LogEvent(stage="POT", status="RUN", scope="POT",
                             msg=str(msg)[:120])
            raw_log.raw("pot", event, to_tui=True)
    
    def _run(self):
        from pot_server import probe_server, latest_server_ver, server_installed_ver
        from pot_server import built_server_js, DEFAULT_HOST, DEFAULT_PORT
        self._dbg(f"POTWorker starting (mode={self.mode})")
        if self.mode == "gate":
            try:
                import components
                self._dbg("entering ffmpeg ensure phase")
                ff_err = components.ensure_ffmpeg(self._note)
                if ff_err:
                    self._note(f"ffmpeg failed: {ff_err}", False, True)
                else:
                    self._dbg("ffmpeg fetch done")
            except Exception as ff_ex:
                self._note(f"ffmpeg ex: {ff_ex}", False, True)
        else:
            self._dbg("ffmpeg ensure skipped (prewarm)")
        try:
            from pot_server import clean_stale_plugin
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
            from pot_server import acquire_prewarm_lock, release_prewarm_lock
            fd = acquire_prewarm_lock(timeout=0, log_func=self._dbg)
            if fd is None:
                self.outcome = (False, "prewarm skipped — build busy")
                return
            try:
                self._note("pot prewarm staging...", True)
                from pot_server import ensure_node_server, server_home, _SERVER_FALLBACK_VER
                ver = remote or local or _SERVER_FALLBACK_VER
                have_build = built_server_js() is not None
                _, err = ensure_node_server(self._note, self._dbg, ver, rebuild=have_build)
                if err is None and built_server_js():
                    self.outcome = (True, "prewarm staged")
                else:
                    self.outcome = (False, f"prewarm fail: {err}")
            finally:
                release_prewarm_lock(fd, log_func=self._dbg)
            return
        if built_server_js():
            self._note("pot server starting...", True)
            from pot_server import _spawn_existing
            proc = _spawn_existing(self._dbg)
            if proc is not None:
                self._server_proc = proc
                self.outcome = (True, f"pot server bound ({DEFAULT_HOST}:{DEFAULT_PORT})")
                return
        self.outcome = (False, "bind fail — age-only")
    
    def terminate(self):
        self.request_interruption()
        super().terminate()

class POTManager(QObject):
    # [v3.3.0] 로그는 raw 버스 단일 경유 — log_full 릴레이 시그널 폐기.
    pot_status_changed = Signal(str)
    pot_finished = Signal(bool, str)

    def __init__(self):
        super().__init__()
        self._worker = None
        self._mode = "idle"
        self._pending_gate = False
        self._lock = threading.Lock()

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
        worker.start()
        self.pot_status_changed.emit("starting" if mode == "gate" else "staging")

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
                    QTimer.singleShot(0, self._start_pending_gate)
                    return
                self._worker = None
                self._mode = "staged" if ok else "failed"
            elif mode == "gate":
                self._worker = None
                self._mode = "ready" if ok else "failed"
            else:
                return

        self.pot_status_changed.emit("staged" if ok else "failed")
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

POTProviderWorker = _POTWorker