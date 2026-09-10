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
import log_console
from log_console import emit_component
from PySide6.QtCore import QThread, Signal


class POTProviderWorker(QThread):
    """앱 시작 시 PO Token 서버 및 플러그인을 무중단으로 준비하고 로드하는 스레드.

    [계약] 외부 모듈(node_provider/pot_server)의 함수들을 조합해
    서버 기동 → 빌드 → probe → spawn 흐름을 orchestrate.

    [모드] prewarm(bool):
    - False(기본): 빌드 + spawn 전부 수행 — 분석 게이트 히트 시 사용.
    - True: 디스크 스테이징만 수행 (소스 fetch + npm ci + tsc, Popen 금지).
      READY 후 유휴 프리웜용 — RAM 0MB·포트 미점유 유지.
    """

    line = Signal(str, bool, bool)
    log_full = Signal(str)

    def __init__(self, parent=None, prewarm=False):
        super().__init__(parent)
        self.prewarm = bool(prewarm)
        self.outcome = ("err", "")
        self._server_proc = None  # 스폰된 서버 프로세스 핸들 (외부 정리용)

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
        """로깅 브리지 — raw 스택 단일 경유 (직접 시그널 emit 금지 — 중복 방지).

        [채널 분기]
        - prewarm 모드: F12(full) 전용 — 유휴 스테이징 로그는 TUI를 오염시키지 않음
        - 정식(gate) 모드: LogEvent → channel=BOTH → TUI + F12 + history 3채널 기록
        """
        import raw_log
        from log_event import LogEvent, Channel
        if self.prewarm:
            # [prewarm] 단계별 상세는 F12(full) 전용. TUI 래핑은 벗겨내고
            # 순수 메시지만 남긴다 — F12에 컬럼 노이즈가 쌓이지 않게.
            raw_msg = str(msg)
            if log_console.is_tui_line(raw_msg):
                raw_msg = raw_msg.split(" │ ")[-1].strip()
            raw_log.raw("pot", raw_msg, is_status=is_status, is_error=is_error,
                        full_only=True)
            return
        # [LogEvent 모드] 구조화된 이벤트 전송 — subscriber가 렌더링
        stage = "SYS" if is_error else "POT"
        status = "FAIL" if is_error else ("RUN" if is_status else "OK")
        # 오류 요약: 60자 초과 시 핵심만 추출 — 상세 원문은 raw로만
        concise_msg = msg
        if is_error and len(msg) > 60:
            for sep in [" — ", " —", ": ", ":"]:
                if sep in msg:
                    concise_msg = msg.split(sep)[0]
                    break
            raw_log.raw("pot-DETAIL", msg, full_only=True)
        event = LogEvent(
            stage=stage, status=status, platform="pot",
            spec="-", msg=concise_msg[:120],
            is_status=is_status, is_error=is_error,
        )
        raw_log.raw("pot", event, channel=Channel.BOTH)

    def _dbg(self, msg):
        """raw 스택 단일 경유 — 직접 log_full.emit 금지 (F12 이중 적재 방지).

        [채널 분기]
        - prewarm 모드: F12(full) 전용 — 유휴 스테이징 로그는 TUI를 오염시키지 않음
        - gate 모드: LogEvent → channel=BOTH → TUI + F12 + history 3채널 전부 기록
        """
        import raw_log
        from log_event import LogEvent, Channel
        if self.prewarm:
            raw_log.raw("pot-DEBUG", msg, full_only=True)
        else:
            # [LogEvent 모드] 구조화된 이벤트 전송 — subscriber가 렌더링
            event = LogEvent(
                stage="POT", status="RUN", platform="pot",
                spec="-", msg=str(msg)[:120],
            )
            raw_log.raw("pot", event, channel=Channel.BOTH)

    def _run(self):
        self._dbg("POTProviderWorker starting")

        # [ffmpeg ensure] — merge/remux용. system 우선, GitHub binary 폴백.
        # [prewarm 스킵] DEPS 업그레이드 단계에서 이미 확보됐다. 프리웜 목적은
        # POT 빌드 스테이징뿐이므로 재확인으로 인한 READY 후 메인 오염·중복을
        # 차단한다 (게이트/정식 모드에서만 수행).
        if not self.prewarm:
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
        else:
            self._dbg("ffmpeg ensure skipped (prewarm — handled at DEPS upgrade)")

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

        # [prewarm 모드] 디스크 스테이징만 — Popen 절대 금지.
        if self.prewarm:
            self._dbg("prewarm mode — staging to disk, no spawn")
            _lock_fd = acquire_prewarm_lock(timeout=0, log_func=self._dbg)
            if _lock_fd is None:
                self.outcome = (
                    "err",
                    emit_component("SYS", "SKIP", "pot", "prewarm skipped — build busy"),
                )
                self._dbg("prewarm skipped — gate holds build lock")
                return
            try:
                # [auto-refresh] stale build → "staging/refresh pending" 경로로
                # 자동 리프레시 진행. 프리웜이 방치하면 lazy가 "언제든 작동 가능한"
                # 준비 상태를 유지하지 못하므로, 산출물 갱신까지 책임을 진다.
                self._note("pot prewarm staging...", True)
                ver = remote or local or _SERVER_FALLBACK_VER
                have_build = built_server_js() is not None
                src_pkg = os.path.join(server_home(), "server", "package.json")
                if remote and (not os.path.isfile(src_pkg) or local != remote):
                    try:
                        download_and_install_source(remote, self._note)
                    except Exception as ds_ex:
                        self._dbg(f"prewarm source refresh failed ({ds_ex})")
                # stale refresh 시에는 rebuild=True로 최신 소스 재컴파일.
                # "노트북 닫힌 사이 서버에서 제거된 기능"은 다운로드 시점에
                # 실패 처리하므로, 프리웜 단계에서는 최신 빌드 확보가 우선.
                rebuild = have_build or (remote and local and remote != local)
                _, err = ensure_node_server(
                    self._note, self._dbg, ver, rebuild=rebuild
                )
                self._dbg(f"prewarm ensure_node_server done: err={err!r}")
                if err is None and built_server_js():
                    try:
                        with open(os.path.join(server_home(), ".version"), "w", encoding="utf-8") as f:
                            f.write(str(ver))
                    except OSError:
                        pass
                    self.outcome = (
                        "ok",
                        emit_component("pot", "OK", "pot", "prewarm staged"),
                    )
                    self._dbg("prewarm staged ok — no spawn")
                else:
                    self.outcome = (
                        "err",
                        emit_component("SYS", "FAIL", "pot", f"prewarm fail: {err or 'build missing'}"),
                    )
            finally:
                release_prewarm_lock(_lock_fd, log_func=self._dbg)
            return

        if built_server_js() and not need_refresh:
            self._dbg("trying to spawn existing build")
            self._note("pot server starting...", True)
            if _spawn_existing(self._dbg):
                self._server_proc = _spawn_existing(self._dbg)
                if self._server_proc is not None:
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
        # [게이트 우선] 프리웜 스테이징과 npm 락 경합 시 게이트가 우선.
        # 프리웜이 락을 쥐고 있으면 최대 120초 대기 후 이어받는다 —
        # 다운로드는 사용자 요청이므로 프리웜(유휴)보다 우선순위 높음.
        # 대기 실패 시에도 빌드 없이 spawn 폴백(기존 빌드 재사용)으로 진행.
        _gate_fd = acquire_prewarm_lock(timeout=120, log_func=self._dbg)
        if _gate_fd is None:
            self._dbg("gate: prewarm holds build lock — proceeding to spawn fallback")
        try:
            if remote and (not os.path.isfile(src_pkg) or local != remote):
                if _gate_fd is not None:
                    try:
                        download_and_install_source(remote, self._note)
                    except Exception as ds_ex:
                        self._dbg(f"source refresh failed ({ds_ex}) — building from existing source")
                else:
                    self._dbg("gate: skip source refresh (no build lock)")

            self._dbg(f"server source version target: {ver} (rebuild={have_build})")
            if _gate_fd is not None:
                _, err = ensure_node_server(self._note, self._dbg, ver, rebuild=have_build)
            else:
                _, err = (None, "build busy — spawn fallback")
            self._dbg(f"ensure_node_server done: err={err!r}")
        finally:
            if _gate_fd is not None:
                release_prewarm_lock(_gate_fd, log_func=self._dbg)

        if err is None:
            self._server_proc = _spawn_existing(self._dbg)
            if self._server_proc is not None:
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
        if built_server_js() and _spawn_existing(self._dbg):
            self._server_proc = _spawn_existing(self._dbg)
            if self._server_proc is not None:
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
            event = LogEvent(
                stage="POT", status="FAIL", platform="pot",
                spec="-", msg=str(l)[:120],
            )
            raw_log.raw("POT-FAIL", event, channel=Channel.FULL)

    def terminate(self):
        """스레드 강제 종료 시 서버 프로세스도 함께 정리."""
        if self._server_proc is not None:
            try:
                from pot_server import _kill
                _kill(self._server_proc)
                self._dbg("server process killed on worker terminate")
            except Exception:
                pass
            self._server_proc = None
        super().terminate()

    def kill_server_process(self):
        """외부에서 서버 프로세스만 강제 종료 (워커 스레드는 유지)."""
        if self._server_proc is not None:
            try:
                from pot_server import _kill
                _kill(self._server_proc)
                self._dbg("server process killed externally")
            except Exception:
                pass
            self._server_proc = None