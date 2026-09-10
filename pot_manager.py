# POTManager
from PySide6.QtCore import QObject, QThread, Signal
import threading
import subprocess
import os
from log_event import LogEvent, Channel
import raw_log


class _POTWorker(QThread):
    log_full = Signal(str)
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
        import raw_log
        from log_event import LogEvent, Channel
        if self.mode == "prewarm":
            raw_log.raw("pot", str(msg), is_status=is_status, is_error=is_error, full_only=True)
        else:
            stage = "SYS" if is_error else "POT"
            status = "FAIL" if is_error else ("RUN" if is_status else "OK")
            event = LogEvent(stage=stage, status=status, platform="pot",
                             spec="-", msg=str(msg)[:120],
                             is_status=is_status, is_error=is_error)
            raw_log.raw("pot", event, channel=Channel.BOTH)
    
    def _dbg(self, msg):
        import raw_log
        from log_event import LogEvent, Channel
        if self.mode == "prewarm":
            raw_log.raw("pot-DEBUG", msg, full_only=True)
        else:
            event = LogEvent(stage="POT", status="RUN", platform="pot",
                             spec="-", msg=str(msg)[:120])
            raw_log.raw("pot", event, channel=Channel.BOTH)
    
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
            if _spawn_existing(self._dbg):
                self._server_proc = _spawn_existing(self._dbg)
                if self._server_proc is not None:
                    self.outcome = (True, f"pot server bound ({DEFAULT_HOST}:{DEFAULT_PORT})")
                    return
        self.outcome = (False, "bind fail — age-only")
    
    def terminate(self):
        self.request_interruption()
        super().terminate()

class POTManager(QObject):
    log_full = Signal(str)
    pot_status_changed = Signal(str)
    pot_finished = Signal(bool, str)
    
    def __init__(self):
        super().__init__()
        self._worker = None
        self._mode = "idle"
        self._pending_gate = False
        self._lock = threading.Lock()
    
    def ensure_ready(self, mode="gate"):
        with self._lock:
            if self._worker and self._worker.isRunning():
                if mode == "gate" and self._mode == "prewarm":
                    self._pending_gate = True
                return
            self._mode = mode
            self._worker = _POTWorker(mode=mode)
            self._worker.log_full.connect(self.log_full)
            self._worker.finished_signal.connect(self._on_worker_finished)
            self._worker.start()
            self.pot_status_changed.emit("starting" if mode == "gate" else "staging")
    
    def _on_worker_finished(self, ok: bool, msg: str):
        with threading.Lock():
            if self.mode == "prewarm" and self._pending_gate:
                self._pending_gate = False
                self.ensure_ready("gate")
            else:
                self.pot_status_changed.emit("staged" if ok else "failed")
                self.pot_finished.emit(ok, msg)
                self._mode = "idle"
    
    @property
    def mode(self):
        return self._mode
    
    def is_busy(self):
        return self._worker is not None and self._worker.isRunning()
    
    def cancel(self):
        if self._worker and self._worker.isRunning():
            self._worker.request_interruption()
            if not self._worker.wait(2000):
                self._worker.terminate()
                self._worker.wait(1000)

POTProviderWorker = _POTWorker