"""pot_provider — POTProviderWorker(QThread) facade (SRP 분리 결과물).

[구조]
- node_provider.py    : Node.js 런타임 수급 (node_exe, node_ok, ensure_node_runtime 등)
- pot_server.py       : bgutil 서버 빌드/기동 (ensure_node_server, _spawn_existing 등)
- po_client.py        : PO Token HTTP 클라이언트 (L0 leaf, 계층 역전 방지)
- pot_provider.py     : 위 3개 모듈을 재수출(re-export) + POTProviderWorker(QThread)

[호환성] 기존 `import pot_provider` 코드는 변경 없이 동작.
- main.py        : pot_provider.POTProviderWorker (기존 호환용, 현재는 POTManager 사용)
- update_worker.py: pot_provider.ensure_node_runtime
- updater.py      : pot_provider.node_exe / node_major_version / npm_exe
"""

# ── 재수출 (내부 호출 + 외부 역참조 모두 1경로) ──────────────────────────
from po_client import (  # L0 leaf — 계층 역전 방지
    DEFAULT_HOST,
    DEFAULT_PORT,
    extract_video_id,
    fetch_po_token,
    probe_server,
    server_ping,
)
from node_provider import (  # SRP: Node.js 런타임만 담당
    NODE_MIN_MAJOR,
    _NO_WINDOW,
    _node_ver_cache,
    get_writable_base,
    _is_portable,
    _bundle_root,
    node_major_version,
    latest_lts_node_url,
    _platform_node_url,
    npm_exe,
    node_ok,
    node_exe,
    bundled_npm_ok,
    ensure_node_runtime,
)
from pot_server import (  # SRP: bgutil 서버 빌드/기동만 담당
    _SERVER_FALLBACK_VER,
    _TAG_ZIP,
    server_home,
    assign_to_job_object,
    read_server_log_tail,
    latest_server_ver,
    server_installed_ver,
    clean_stale_plugin,
    _wait_port,
    _kill,
    built_server_js,
    pot_readiness,
    acquire_prewarm_lock,
    release_prewarm_lock,
    _spawn_existing,
    download_and_install_source,
    _run_and_stream_log,
    ensure_node_server,
    kill_process_on_port,
)

__all__ = [
    "DEFAULT_HOST", "DEFAULT_PORT", "extract_video_id",
    "fetch_po_token", "probe_server", "server_ping",
    "NODE_MIN_MAJOR", "get_writable_base", "_is_portable", "_bundle_root",
    "node_major_version", "latest_lts_node_url", "_platform_node_url",
    "npm_exe", "node_ok", "node_exe", "bundled_npm_ok", "ensure_node_runtime",
    "server_home", "assign_to_job_object", "read_server_log_tail",
    "latest_server_ver", "server_installed_ver", "clean_stale_plugin",
    "built_server_js", "pot_readiness", "acquire_prewarm_lock",
    "release_prewarm_lock", "_spawn_existing", "download_and_install_source",
    "ensure_node_server", "kill_process_on_port", "POTProviderWorker",
]

import os
import raw_log
from log_event import LogEvent
from PySide6.QtCore import QThread, Signal
import subprocess
class POTProviderWorker(QThread):
    """PO Token 서버 기동용 워커 (gate 모드만 담당, prewarm은 POTManager 담당).

    [v3.3.0] 로그는 raw 버스 단일 경유 — line/log_full 시그널 폐기.
    finished_signal(ok, msg)는 로그가 아닌 '결과 전달' 계약이므로 유지 —
    워커 스레드 → GUI 스레드 결과 통보는 시그널이 정답이고, 로그는 버스가 정답.
    """
    finished_signal = Signal(bool, str)  # (ok, message) — 결과 전달용, 로그 아님

    def __init__(self, parent=None):
        super().__init__(parent)
        self._abort = False
        self._child_procs = []
        self._server_proc = None
        self.outcome = (False, "")

    def request_interruption(self):
        """Graceful shutdown 요청."""
        self._abort = True
        for proc in self._child_procs:
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except Exception:
                proc.kill()

    def run(self):
        try:
            self._run()
        except Exception as e:
            self.outcome = (False, f"POT worker crash: {type(e).__name__}: {e}")
        finally:
            self._cleanup()
            self.finished_signal.emit(self.outcome[0], self.outcome[1])

    def _cleanup(self):
        """스레드 종료 시 무조건 실행."""
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

    def _run_child(self, cmd, **kwargs):
        proc = subprocess.Popen(cmd, **kwargs)
        self._child_procs.append(proc)
        try:
            return proc.wait()
        finally:
            if proc in self._child_procs:
                self._child_procs.remove(proc)

    def _note(self, msg, is_status=False, is_error=False):
        """로깅 브리지 — raw 버스 단일 경유.

        [발행자 결정] gate 전용 워커이므로 to_tui=True — TUI + F12 + history 전부.
        """
        stage = "SYS" if is_error else "POT"
        status = "FAIL" if is_error else ("RUN" if is_status else "OK")
        event = LogEvent(stage=stage, status=status, platform="pot",
                         spec="-", msg=str(msg)[:120],
                         is_status=is_status, is_error=is_error)
        raw_log.raw("pot", event, to_tui=True)

    def _dbg(self, msg):
        """로깅 브리지 — raw 버스 단일 경유 (to_tui=True, gate 전용)."""
        event = LogEvent(stage="POT", status="RUN", platform="pot",
                         spec="-", msg=str(msg)[:120])
        raw_log.raw("pot", event, to_tui=True)

    def _run(self):
        from pot_server import probe_server, built_server_js, _spawn_existing
        from pot_server import DEFAULT_HOST, DEFAULT_PORT
        self._dbg("POTProviderWorker starting (gate mode)")

        self._note("probing server...", True)
        state, detail = probe_server()
        self._dbg(f"probe: state={state!r}")
        if state == "ok":
            self.outcome = (True, f"pot server bound ({DEFAULT_HOST}:{DEFAULT_PORT})")
            return

        if built_server_js():
            self._note("pot server starting...", True)
            # [이중 스폰 방지] 조건 평가와 프로세스 핸들 할당을 단 1회 호출로 통합.
            # 구 버그: if _spawn_existing(...) + 재호출로 포트 점유 중 두 번째 서버 기동 → 좀비 양산.
            proc = _spawn_existing(self._dbg)
            if proc is not None:
                self._server_proc = proc
                self.outcome = (True, f"pot server bound ({DEFAULT_HOST}:{DEFAULT_PORT})")
                return
        self.outcome = (False, "bind fail — age-only")

    def terminate(self):
        self.request_interruption()
        super().terminate()