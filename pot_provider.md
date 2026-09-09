"""pot_provider — PO Token 서버 수명주기 facade (SRP 분리 결과물).

[구조]
- node_provider.py    : Node.js 런타임 수급 (node_exe, node_ok, ensure_node_runtime 등)
- pot_server.py       : bgutil 서버 빌드/기동 (ensure_node_server, _spawn_existing 등)
- po_client.py        : PO Token HTTP 클라이언트 (L0 leaf, 계층 역전 방지)
- pot_provider.py     : 위 3개 모듈을 재수출(re-export) + POTProviderWorker(QThread)

[호환성] 기존 `import pot_provider` 코드는 변경 없이 동작.
- main.py        : pot_provider.POTProviderWorker
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
    _spawn_existing,
    download_and_install_source,
    _run_and_stream_log,
    ensure_node_server,
)

__all__ = [
    "DEFAULT_HOST", "DEFAULT_PORT", "extract_video_id",
    "fetch_po_token", "probe_server", "server_ping",
    "NODE_MIN_MAJOR", "get_writable_base", "_is_portable", "_bundle_root",
    "node_major_version", "latest_lts_node_url", "_platform_node_url",
    "npm_exe", "node_ok", "node_exe", "bundled_npm_ok", "ensure_node_runtime",
    "server_home", "assign_to_job_object", "read_server_log_tail",
    "latest_server_ver", "server_installed_ver", "clean_stale_plugin",
    "built_server_js", "_spawn_existing", "download_and_install_source",
    "ensure_node_server", "POTProviderWorker",
]

import os
import log_console
from log_console import emit_component
from PySide6.QtCore import QThread, Signal


class POTProviderWorker(QThread):
    """앱 시작 시 PO Token 서버 및 플러그인을 무중단으로 준비하고 로드하는 스레드.

    [계약] 외부 모듈(node_provider/pot_server)의 함수들을 조합해
    서버 기동 → 빌드 → probe → spawn 흐름을 orchestrate.
    """
    line = Signal(str, bool, bool)
    log_full = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.outcome = ("err", "")

    def run(self):
        try:
            self._run()
        except Exception as e:
            self.outcome = (
                "err",
                emit_component("SYS", "FAIL", "pot",
                               f"PO server auto-config failed: {type(e).__name__}: {e}"),
            )

    def _note(self, msg, is_status=False, is_error=False):
        """간결 로그 + log_full 브리지."""
        # [병기 방지] 이미 TUI 컬럼 포맷이면 그대로 emit — 재래핑 금지
        if log_console.is_tui_line(msg):
            self.line.emit(str(msg), is_status, is_error)
            return
        # [오류 요약] 60자 초과 시 핵심만 추출
        concise_msg = msg
        if is_error and len(msg) > 60:
            for sep in [" — ", " —", ": ", ":"]:
                if sep in msg:
                    concise_msg = msg.split(sep)[0]
                    break
            self.log_full.emit(f"[pot-DETAIL] {msg}")
        stage = "SYS" if is_error else "pot"
        status = "FAIL" if is_error else ("RUN" if is_status else "OK")
        tui = emit_component(stage, status, "pot", concise_msg)
        self.line.emit(tui, is_status, is_error)

    def _dbg(self, msg):
        """F12 verbose window + history only."""
        self.log_full.emit(f"[pot-DEBUG] {msg}")

    def _run(self):
        self._dbg("POTProviderWorker starting")

        # [ffmpeg ensure] — merge/remux용. system 우선, GitHub binary 폴백.
        try:
            import components
            self._dbg("entering ffmpeg ensure phase")
            ff_err = components.ensure_ffmpeg(self._note)
            if ff_err:
                self._note(
                    f"ffmpeg fetch failed — merge/remux limited: {ff_err}",
                    False, True,
                )
                self._dbg(f"ffmpeg fetch failed: {ff_err}")
            else:
                self._dbg("ffmpeg fetch done")
        except Exception as ff_ex:
            self._note(f"ffmpeg fetch module exception: {ff_ex}", False, True)
            self._dbg(f"ffmpeg fetch module exception: {type(ff_ex).__name__}: {ff_ex}")

        # [전환] Python 플러그인 설치/검사 제거 — 토큰은 다운로드 시점에
        # fetch_po_token()으로 직접 패칭. 구버전 잔재 정리.
        try:
            if clean_stale_plugin():
                self._dbg("stale yt_dlp_plugins removed")
        except Exception as cp_ex:
            self._dbg(f"stale plugin cleanup failed: {cp_ex}")

        self._note("probing server...", True)
        state, detail = probe_server()
        self._dbg(f"probe: state={state!r} detail={detail[:200]!r}")
        if state == "ok":
            self.outcome = (
                "ok",
                emit_component("pot", "OK", "pot",
                               f"pot server bound ({DEFAULT_HOST}:{DEFAULT_PORT})"),
            )
            self._dbg("ok branch — worker exits")
            return

        # [버전 체크] GitHub 최신 릴리즈 vs 로컬 .version 마커
        remote = latest_server_ver()
        local = server_installed_ver()
        need_refresh = local is None or (remote is not None and remote != local)
        self._dbg(f"server version: local={local!r} remote={remote!r} refresh={need_refresh}")

        if built_server_js() and not need_refresh:
            self._dbg("trying to spawn existing build")
            self._note("pot server starting...", True)
            if _spawn_existing(self.log_full.emit):
                self.outcome = (
                    "ok",
                    emit_component("pot", "OK", "pot",
                                   f"pot server bound ({DEFAULT_HOST}:{DEFAULT_PORT})"),
                )
                self._dbg("existing build spawn ok")
                self._note("pot server ready", True)
                return
            self._dbg("existing build spawn failed — rebuilding")

        self._note("building PO token server...", True)
        ver = remote or local or _SERVER_FALLBACK_VER
        have_build = built_server_js() is not None
        src_pkg = os.path.join(server_home(), "server", "package.json")
        if remote and (not os.path.isfile(src_pkg) or local != remote):
            try:
                download_and_install_source(remote, self._note)
            except Exception as ds_ex:
                self._dbg(f"source refresh failed ({ds_ex}) — building from existing source")

        self._dbg(f"server source version target: {ver} (rebuild={have_build})")
        _, err = ensure_node_server(self._note, self.log_full.emit, ver, rebuild=have_build)
        self._dbg(f"ensure_node_server done: err={err!r}")

        if err is None and _spawn_existing(self.log_full.emit):
            self.outcome = (
                "ok",
                emit_component("pot", "OK", "pot",
                               f"pot server bound ({DEFAULT_HOST}:{DEFAULT_PORT})"),
            )
            self._dbg("fresh build spawn ok")
            self._note("pot server ready", True)
            try:
                with open(os.path.join(server_home(), ".version"), "w", encoding="utf-8") as f:
                    f.write(str(ver))
            except OSError:
                pass
            return

        # [폴백] 갱신 실패 — 기존 빌드가 살아있으면 최소한 동작 서버로
        if built_server_js() and _spawn_existing(self.log_full.emit):
            self.outcome = (
                "ok",
                emit_component("pot", "WARN", "pot", "refresh failed — stale server"),
            )
            self._dbg("fallback spawn of existing build ok")
            self._note("pot server ready (stale)", True)
            return

        self.outcome = (
            "err",
            emit_component("SYS", "FAIL", "pot", "bind fail — age-only"),
        )
        self._dbg("final fail — extracting tail causes")
        reasons = [l for l in (err or "").splitlines()[-4:] if l.strip()]
        tail = read_server_log_tail(6)
        reasons.extend(l.strip() for l in tail.splitlines() if l.strip())
        for l in reasons:
            self.log_full.emit(f"[POT-FAIL] {l}")