"""bgutil PO Token 서버 수명 주기 전용 모듈 (SRP: 서버 수급/빌드/기동만 담당).

- latest_server_ver / server_installed_ver : 버전 확인 (GitHub API + 로컬 마커)
- download_and_install_source : 지정 버전 소스 패치
- ensure_node_server : npm ci + tsc 빌드 파이프라인
- _spawn_node_server / _spawn_existing : Node.js HTTP 서버 기동
- _wait_port / _kill : 프로세스 생명주기 헬퍼
- _download_with_progress : 친절한 진행률 다운로드

Node.js 런타임 수급은 node_provider.py가 담당. 공유 경로 헬퍼는 infra.paths에서 import.
"""
import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.request
import zipfile
from dataclasses import dataclass

from chzzktube.core import DOWNLOAD_TIMEOUT, READ_TIMEOUT
from chzzktube.core.log_emitter import emit_component
from chzzktube.core.raw_log import log_f12_cli, log_f12_net
from chzzktube.infra.node_provider import NODE_MIN_MAJOR
from chzzktube.infra.paths import get_writable_base
from chzzktube.infra.platform import (
    attach_to_parent_lifecycle,
    daemon_spawn_kwargs,
    is_windows,
)
from chzzktube.infra.platform import kill_tree as kill_tree_platform
from chzzktube.infra.po_client import DEFAULT_PORT, probe_server
from chzzktube.ui import ProgressBar


@dataclass
class Result:
    """표준화된 성공/실패 결과 (예외 대신 명시적 반환)."""
    success: bool
    value: object | None = None
    error: str | None = None


_TAG_ZIP = (
    "https://github.com/Brainicism/bgutil-ytdlp-pot-provider/archive/refs/tags/{ver}.zip"
)
_SERVER_FALLBACK_VER = "1.3.2"

# [P3c] 빌드 단계 상한 (초) — npm ci/tsc가 무응답이면 프리웜 워커가 영구 점유되어
# is_busy()가 고정되고 POT 게이트 다운로드가 큐에서 풀리지 않는다.
_NPM_CI_TIMEOUT = 600
_TSC_TIMEOUT = 300


def server_home() -> str:
    """PO Token 서버 소스/빌드를 둘 위치 — SSOT 단일 경로 (v3.8.2).

    [SSOT 원칙] 오직 writable_base()/bgutil-ytdlp-pot-provider/ 하위만 사용.
    - frozen 번들(bundle_root), _MEIPASS 경로 탐색 완전 제거
    - 소스/빌드/런타임 모두 이 디렉토리에서 관리
    """
    writable_path = os.path.join(get_writable_base(), "bgutil-ytdlp-pot-provider")
    os.makedirs(writable_path, exist_ok=True)
    return writable_path


def assign_to_job_object(proc):
    """Windows: 프로세스를 Job Object에 할당해 부모 종료 시 자동 정리.

    실체는 platform.attach_to_parent_lifecycle — 여기는 하위 호환 재수출.

    [표식 정확성] `proc._ct_job`은 "Job Object에 실제로 할당됨"을 뜻한다.
    종전에는 `_handle` 존재만 보고 무조건 True를 붙여, 할당이 실패해도
    할당된 것처럼 보였다(부모 종료 정리가 무력화된 사실이 은폐됨).
    이제 platform의 반환값(실할당 여부)을 그대로 옮긴다.
    """
    assigned = attach_to_parent_lifecycle(proc)
    try:
        if proc is not None:
            proc._ct_job = bool(assigned)
    except Exception as e:  # noqa: BLE001 — 표식 부착 실패는 무시 (raw 버스 진단 유지)
        from chzzktube.core import raw_log
        raw_log.raw("POT", f"assign_to_job_object error: {type(e).__name__}: {e}", is_error=True, to_tui=False)


def read_server_log_tail(n=10):
    """bgutil_server.log의 마지막 n줄 반환 (디버깅용)."""
    log_file_path = os.path.join(get_writable_base(), "bgutil_server.log")
    if os.path.isfile(log_file_path):
        try:
            with open(log_file_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            return "".join(lines[-n:])
        except Exception as e:  # noqa: BLE001 — 로그 꼬리 읽기 실패는 빈 문자열 폴백
            from chzzktube.core import raw_log
            raw_log.raw("POT", f"read_server_log_tail error: {type(e).__name__}: {e}", is_error=True, to_tui=False)
    return ""


# ── 서버 버전·소스 관리 ─────────────────────────────────────────────
# [B4 정리] _TAG_ZIP·_SERVER_FALLBACK_VER는 상단(32~35행) 단일 정의만 유지 —
# 병합 잔재로 두 번 선언돼 있던 중복 상수는 제거했다.


def latest_server_ver(timeout=3):
    """bgutil 서버 최신 릴리즈 태그 (GitHub API). 실패 시 None — 호출부 폴백.

    [stale 감지용 경량 호출] timeout을 짧게(3초) 유지 — DEPS/프리웜 경로의
    블로킹 최소화. 네트워크 실패는 None으로 흡수해 판정 유지.
    """
    try:
        req = urllib.request.Request(
            "https://api.github.com/repos/Brainicism/bgutil-ytdlp-pot-provider/releases/latest",
            headers={"User-Agent": "ChzzkTube"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return (json.load(resp).get("tag_name") or "").strip() or None
    except Exception as e:  # noqa: BLE001 — GitHub API 실패는 None 폴백 (판정 유지)
        from chzzktube.core import raw_log
        raw_log.raw("POT", f"latest_server_ver error: {type(e).__name__}: {e}", is_error=True, to_tui=False)
        return None


def server_installed_ver():
    """로컬에 전개된 bgutil 서버 버전 (.version 마커 또는 package.json). 없으면 None."""
    for cand in (
        os.path.join(server_home(), ".version"),
        os.path.join(server_home(), "server", ".version"),
    ):
        try:
            if os.path.isfile(cand):
                with open(cand, encoding="utf-8") as f:
                    v = f.read().strip()
                    if v:
                        return v
        except OSError:
            pass
    # 폴백: server/package.json
    try:
        pkg_json = os.path.join(server_home(), "server", "package.json")
        if os.path.isfile(pkg_json):
            with open(pkg_json, encoding="utf-8") as f:
                return json.load(f).get("version")
    except Exception:  # noqa: BLE001, S110 — package.json 판독 실패는 None 폴백
        pass
    return None


def clean_stale_plugin():
    """구버전에서 설치된 bgutil Python 플러그인 제거.

    yt_dlp_plugins/ 아래 getpot_bgutil이 남으면 yt-dlp 플러그인 로더가
    자동 로드해 fetch_po_token과 이중 주입 → 토큰 충돌 위험. 기동 시 1회.
    대상: <writable_base>/yt_dlp_plugins, <components>/yt-dlp/yt_dlp_plugins
    """
    from chzzktube.infra import components
    roots = [
        os.path.join(get_writable_base(), "yt_dlp_plugins"),
        os.path.join(components.components_root(), "yt-dlp", "yt_dlp_plugins"),
    ]
    removed = False
    for d in roots:
        if os.path.isdir(d):
            shutil.rmtree(d, ignore_errors=True)
            removed = True
    return removed


# ── 서버 기동/빌드/수명주기 ─────────────────────────────────────────
def _wait_port(seconds, log_full_func=None):
    """포트가 열릴 때까지 폴링. log_full_func가 있으면 5초마다 진척 로그 출력."""
    deadline = time.time() + seconds
    last_log = 0.0
    while time.time() < deadline:
        if probe_server()[0] == "ok":
            return True
        now = time.time()
        if log_full_func and now - last_log >= 5.0:
            log_full_func(
                f"[pot:spawn] waiting for server... "
                f"{int(seconds - (deadline - now))}s / {seconds}s"
            )
            last_log = now
        time.sleep(0.5)
    return False


def _kill(proc):
    """서버 프로세스 강제 종료 (침묵형)."""
    try:
        proc.kill()
    except Exception as e:  # noqa: BLE001 — 강제 종료 자체가 best-effort
        from chzzktube.core import raw_log
        raw_log.raw("POT", f"_kill error: {type(e).__name__}: {e}", is_error=True, to_tui=False)


def kill_tree(proc):
    """프로세스 트리 종료 — 실체는 platform.kill_tree (하위 호환 재수출)."""
    kill_tree_platform(proc)
    try:
        if getattr(proc, "_ct_job", None):
            proc._ct_job = None
    except Exception as e:  # noqa: BLE001 — 표식 해제 실패는 무시 (종료 경로)
        from chzzktube.core import raw_log
        raw_log.raw("POT", f"kill_tree error: {type(e).__name__}: {e}", is_error=True, to_tui=False)


def kill_process_on_port(port=DEFAULT_PORT, log_func=None):
    """지정된 포트를 점유한 프로세스 강제 종료 (크로스플랫폼).

    좀비 프로세스 정리용 — server_ping이 True인데 PID가 죽은 경우 호출.
    """
    killed = False
    try:
        if is_windows():
            # Windows: netstat로 PID 찾기 → taskkill
            import subprocess as _sub
            try:
                out = _sub.check_output(
                    ["netstat", "-ano"], text=True, stderr=_sub.DEVNULL
                )
                for line in out.splitlines():
                    if f":{port} " in line and "LISTENING" in line:
                        parts = line.split()
                        if parts:
                            pid = parts[-1]
                            if pid.isdigit():
                                _sub.run(
                                    ["taskkill", "/F", "/PID", pid],
                                    stdout=_sub.DEVNULL,
                                    stderr=_sub.DEVNULL,
                                    check=False,  # PLW1510: 좀비 정리는 best-effort
                                )
                                if log_func:
                                    log_func(f"[pot:zombie] killed windows pid={pid} on port {port}")
                                killed = True
            except Exception as e:  # noqa: BLE001 — netstat/taskkill 실패는 로그 후 계속
                from chzzktube.core import raw_log
                raw_log.raw("POT", f"kill_process_on_port windows error: {type(e).__name__}: {e}", is_error=True, to_tui=False)
        else:
            # macOS/Linux: lsof로 PID 찾기 → kill
            import subprocess as _sub
            try:
                out = _sub.check_output(
                    ["lsof", "-ti", f":{port}"], text=True, stderr=_sub.DEVNULL
                )
                for pid_str in out.strip().split():
                    if pid_str.isdigit():
                        pid = int(pid_str)
                        os.kill(pid, 9)  # SIGKILL
                        if log_func:
                            log_func(f"[pot:zombie] killed posix pid={pid} on port {port}")
                        killed = True
            except Exception as e:  # noqa: BLE001 — lsof/kill 실패는 로그 후 계속
                from chzzktube.core import raw_log
                raw_log.raw("POT", f"kill_process_on_port posix error: {type(e).__name__}: {e}", is_error=True, to_tui=False)
    except Exception as e:  # noqa: BLE001 — 포트 정리 실패해도 killed 플래그 반환
        from chzzktube.core import raw_log
        raw_log.raw("POT", f"kill_process_on_port error: {type(e).__name__}: {e}", is_error=True, to_tui=False)
    return killed


def built_server_js():
    """컴파일된 main.js 경로 반환 (build/ 와 dist/ 모두 지원)."""
    base_dir = os.path.join(server_home(), "server")
    for out_dir in ("build", "dist"):
        js_path = os.path.join(base_dir, out_dir, "main.js")
        if os.path.isfile(js_path):
            return js_path
    return None


def pot_readiness(log_func=None, check_stale=False, want_refresh=False):
    """POT 서버 기동 가능성 경량 판정 — 파일시스템 스캔만 (L0, 네트워크·Popen 금지).

    [Lazy 2층 분리] DEPS 단계에서는 바이너리+빌드 산출물의 디스크 준비만
    확인하고 (RAM 0MB·포트 미점유), 실제 Popen은 분석 게이트까지 지연.
    - ready=True  → 게이트 히트 시 즉시 spawn 가능 (0.1~3초)
    - ready=False → reason에 부족분 명시 (node missing / no build / stale vX→vY)
    - stale + want_refresh=True → 자동 리프레시 유도 (reason은 여전히 stale)

    [성능] node_ok()의 subprocess 기동(수백ms)을 피하고 node_exe() 존재만으로
    판정 — UpdateWorker 스레드 블로킹 및 DEPS 1초 예산 초과 방지.
    정확한 버전 판별은 _do_upgrade의 ensure_node_runtime이 담당.
    log_func(msg): 판정 근거를 raw 스택으로 반환 (계층 역전 방지용 콜백).
    check_stale=True → GitHub 최신 태그와 로컬 .version 비교 (네트워크 3초).
    실패(None) 시 판정 유지 — stale 미확인을 FAIL로 승격 금지.
    want_refresh=True → stale 시 ready=True 복귀 + reason에 refresh 표기.
    "lazy는 언제든지 작동 가능한 데에서 의의가 있다"는 원칙에 따라,
    stale 빌드도 "준비 완료(staged/refresh pending)"로 간주.
    """
    from chzzktube.infra.node_provider import node_exe
    try:
        exe = node_exe()
        if not exe:
            if log_func:
                try:
                    log_func("[pot-readiness] not ready: node missing")
                except Exception as e:  # noqa: BLE001 — log_func 실패는 raw 버스 진단으로 흡수
                    from chzzktube.core import raw_log
                    raw_log.raw("POT", f"log_func error: {type(e).__name__}: {e}", is_error=True, to_tui=False)
            return False, "node missing"
    except Exception as e:  # noqa: BLE001 — node 판별 실패는 "node missing" 폴백
        from chzzktube.core import raw_log
        raw_log.raw("POT", f"node check error: {type(e).__name__}: {e}", is_error=True, to_tui=False)
        return False, "node missing"
    try:
        js = built_server_js()
        if not js:
            if log_func:
                try:
                    log_func("[pot-readiness] not ready: no build")
                except Exception as e:  # noqa: BLE001 — raw 버스 진단 유지 (동작 불변)
                    from chzzktube.core import raw_log
                    raw_log.raw("POT", f"log_func error: {type(e).__name__}: {e}", is_error=True, to_tui=False)
            return False, "no build"
    except Exception as e:  # noqa: BLE001 — raw 버스 진단 유지 (동작 불변)
        from chzzktube.core import raw_log
        raw_log.raw("POT", f"built_server_js error: {type(e).__name__}: {e}", is_error=True, to_tui=False)
        return False, "no build"
    if check_stale:
        # [stale 감지] 로컬 .version vs GitHub 최신 — 불일치면 리프레시 유도.
        # 네트워크 실패(None) 시 판정 유지 (stale 미확인 ≠ FAIL).
        # [auto-refresh] want_refresh=True면 stale이어도 "작동 가능한 준비됨"으로
        # 간주 — 프리웜이 자동으로 리프레시 진행. "lazy는 언제든 작동 가능해야 함"
        # 원칙: stale 빌드를 fail로 닫지 않고 staged/refresh pending으로 열어야 한다.
        try:
            local = server_installed_ver()
            remote = latest_server_ver()
            stale = remote and local and remote != local
            if stale:
                if log_func:
                    try:
                        log_func(f"[pot-readiness] stale build (local {local} → remote {remote})")
                    except Exception as e:  # noqa: BLE001 — raw 버스 진단 유지 (동작 불변)
                        from chzzktube.core import raw_log
                        raw_log.raw("POT", f"log_func error: {type(e).__name__}: {e}", is_error=True, to_tui=False)
                if want_refresh:
                    return True, f"stale {local}→{remote} (refresh pending)"
                return False, f"stale {local}→{remote}"
        except Exception as e:  # noqa: BLE001 — raw 버스 진단 유지 (동작 불변)
            from chzzktube.core import raw_log
            raw_log.raw("POT", f"stale check error: {type(e).__name__}: {e}", is_error=True, to_tui=False)
    if log_func:
        try:
            log_func(f"[pot-readiness] standby (node ok, build {js})")
        except Exception as e:  # noqa: BLE001 — raw 버스 진단 유지 (동작 불변)
            from chzzktube.core import raw_log
            raw_log.raw("POT", f"log_func error: {type(e).__name__}: {e}", is_error=True, to_tui=False)
    return True, "standby"


def _spawn_node_server(log_full_func=None):
    """Node.js로 bgutil HTTP 서버 기동하고 45초 내에 /ping 응답 확인."""
    from chzzktube.infra.node_provider import node_exe

    js, node = built_server_js(), node_exe()
    if not js and log_full_func:
        log_full_func("server spawn reason: built main.js missing (server/build)")
    if not node and log_full_func:
        log_full_func(f"server spawn reason: Node.js >= {NODE_MIN_MAJOR} binary missing")
    if not (js and node):
        return None

    log_file_path = os.path.join(get_writable_base(), "bgutil_server.log")
    # SIM115: open() 핸들은 Popen에 stdout/stderr로 넘겨지므로 with로 닫으면 안 된다 —
    # 자식 프로세스가 살아있는 동안 부모가 핸들을 유지해야 한다. 실패 시 DEVNULL 폴백.
    try:
        log_file = open(log_file_path, "w", encoding="utf-8", errors="replace")  # noqa: SIM115
    except Exception as e:  # noqa: BLE001 — raw 버스 진단 유지 (동작 불변)
        from chzzktube.core import raw_log
        raw_log.raw("POT", f"open server log error: {type(e).__name__}: {e}", is_error=True, to_tui=False)
        log_file = subprocess.DEVNULL

    try:
        env = os.environ.copy()
        node_dir = os.path.dirname(os.path.abspath(node))
        env["PATH"] = node_dir + os.pathsep + env.get("PATH", "")

        kwargs = daemon_spawn_kwargs()
        proc = subprocess.Popen(
            [node, js],
            cwd=os.path.dirname(js),
            stdout=log_file,
            stderr=log_file,
            env=env,
            **kwargs,
        )
        assign_to_job_object(proc)
    except Exception as e:  # noqa: BLE001 — 스폰 실패는 호출자 로그 + None 반환 계약
        if log_full_func:
            log_full_func(f"server Popen failed: {e}")
        return None
    if _wait_port(20, log_full_func):
        return proc
    _kill(proc)
    tail = read_server_log_tail(15)
    if log_full_func:
        log_full_func(
            "server spawn reason: /ping not responding in 20s "
            "(crash after startup — see bgutil_server.log)"
        )
        if tail:
            log_full_func(f"[pot:server.log tail]\n{tail.strip()}")
    return None


def _spawn_existing(log_full_func=None):
    """기존 빌드가 있으면 재사용, 없으면 _spawn_node_server 위임."""
    return _spawn_node_server(log_full_func)


def _download_with_progress(url, dest_path, log_func=None, desc="downloading", timeout=DOWNLOAD_TIMEOUT):
    """청크 단위 분할 다운로드 및 콘솔에 친절한 진행률 출력.

    ProgressBar를 사용하여 TUI 상태 줄 갱신형 + F12 갱신형으로 진행률 기록.
    """
    with ProgressBar(component=desc, log_func=log_func) as bar:
        bar.start()
        temp_dest = dest_path + ".tmp"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ChzzkTube"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                # Set per-read timeout
                try:
                    sock = resp.fp.raw._sock
                    if sock is not None:
                        sock.settimeout(READ_TIMEOUT)
                except AttributeError:
                    pass

                total_size = int(resp.headers.get("content-length", 0))
                downloaded = 0
                with open(temp_dest, "wb") as f:
                    while True:
                        chunk = resp.read(1024 * 1024)  # 1MB
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        bar.update(downloaded, total_size)

                if os.path.exists(temp_dest):
                    shutil.move(temp_dest, dest_path)
                bar.finish("completed")
        finally:
            if os.path.exists(temp_dest):
                try:
                    os.remove(temp_dest)
                except Exception as e:  # noqa: BLE001 — raw 버스 진단 유지 (동작 불변)
                    from chzzktube.core import raw_log
                    raw_log.raw("POT", f"temp file cleanup error: {type(e).__name__}: {e}", is_error=True, to_tui=False)


def _prewarm_lock_path():
    """프리웜/게이트 npm 빌드 상호배제용 락 파일 경로."""
    return os.path.join(server_home(), ".prewarm.lock")


def _pid_alive(pid):
    """PID 생존 확인 — Windows OpenProcess / POSIX kill(pid, 0).

    [PID-liveness] mtime 단일 기준의 오판(크래시 후 30분 프리웜 양보)을
    막기 위해 프로세스 실존 여부를 직접 확인. 판별 실패(권한 등)는
    보수적으로 살아있음으로 간주 (성급한 회수 금지).
    """
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    try:
        import platform as _plat
        if _plat.system() == "Windows":
            import ctypes as _ct
            from ctypes import wintypes as _wt
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            try:
                _k32 = _ct.WinDLL("kernel32", use_last_error=True)
                _k32.OpenProcess.argtypes = [_wt.DWORD, _wt.BOOL, _wt.DWORD]
                _k32.OpenProcess.restype = _wt.HANDLE
                _k32.CloseHandle.argtypes = [_wt.HANDLE]
                _k32.CloseHandle.restype = _wt.BOOL
                h = _k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
                if not h:
                    return False  # 존재하지 않거나 접근 불가 → 죽음으로 간주
                try:
                    return True
                finally:
                    _k32.CloseHandle(h)
            except Exception as e:  # noqa: BLE001 — raw 버스 진단 유지 (동작 불변)
                from chzzktube.core import raw_log
                raw_log.raw("POT", f"_pid_alive windows error: {type(e).__name__}: {e}", is_error=True, to_tui=False)
                return True  # 판별 자체 실패 → 보수적 유지
        else:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return False
            except PermissionError:
                return True  # 존재하나 권한 없음 → 살아있음
            except Exception as e:  # noqa: BLE001 — raw 버스 진단 유지 (동작 불변)
                from chzzktube.core import raw_log
                raw_log.raw("POT", f"_pid_alive posix error: {type(e).__name__}: {e}", is_error=True, to_tui=False)
                return True
            return True
    except Exception as e:  # noqa: BLE001 — raw 버스 진단 유지 (동작 불변)
        from chzzktube.core import raw_log
        raw_log.raw("POT", f"_pid_alive error: {type(e).__name__}: {e}", is_error=True, to_tui=False)
        return True


def _read_lock_info(path):
    """락 파일에서 (pid:int|None, epoch:float|None) 판독."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            parts = f.read().strip().split()
        pid = int(parts[0]) if parts else None
        epoch = float(parts[1]) if len(parts) > 1 else None
        return pid, epoch
    except Exception as e:  # noqa: BLE001 — raw 버스 진단 유지 (동작 불변)
        from chzzktube.core import raw_log
        raw_log.raw("POT", f"_read_lock_info error: {type(e).__name__}: {e}", is_error=True, to_tui=False)
        return None, None


def acquire_prewarm_lock(timeout=0, log_func=None):
    """원자적 락 획득 시도 — O_EXCL 생성으로 상호배제.

    [Zero-Base] msvcrt/filelock 외부 의존 없이 os.open(O_CREAT|O_EXCL)
    원자 생성으로 프로세스·스레드 경계를 모두 차단 (단일 앱 전제).
    stale 락 판정: PID 죽음 AND mtime 30분 초과 → 회수. PID 살아있으면
    mtime 무관하게 대기 (PID 재사용 레이스는 mtime 상한으로 차단).
    timeout=0 → 즉시 반환 (None이면 획득 실패). timeout>0 → 폴링 대기.
    반환: fd(int) 또는 None. 해제는 release_prewarm_lock(fd).
    log_func(msg): 획득/대기/양보/stale 회수 전 분기를 호출자 로그로 반환.
    """
    import time as _time
    path = _prewarm_lock_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
    except OSError:
        pass
    deadline = _time.monotonic() + max(0, timeout)
    waited_note = False
    while True:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            try:
                os.write(fd, f"{os.getpid()} {_time.time()}".encode())
            except OSError:
                pass
            if log_func:
                try:
                    log_func("[prewarm-lock] acquired")
                except Exception as e:  # noqa: BLE001 — raw 버스 진단 유지 (동작 불변)
                    from chzzktube.core import raw_log
                    raw_log.raw("POT", f"log_func error: {type(e).__name__}: {e}", is_error=True, to_tui=False)
            return fd
        except FileExistsError:
            pid, _epoch = _read_lock_info(path)
            alive = _pid_alive(pid) if pid else True
            try:
                age = _time.time() - os.path.getmtime(path)
            except OSError:
                age = 0
            if not alive and age > 1800:  # PID 죽음 + 30분 stale → 회수
                if log_func:
                    try:
                        log_func(f"[prewarm-lock] stale reclaimed (pid={pid} dead, age={int(age)}s)")
                    except Exception as e:  # noqa: BLE001 — raw 버스 진단 유지 (동작 불변)
                        from chzzktube.core import raw_log
                        raw_log.raw("POT", f"log_func error: {type(e).__name__}: {e}", is_error=True, to_tui=False)
                try:
                    os.remove(path)
                except OSError:
                    pass
                continue
            if log_func and not waited_note and timeout > 0:
                waited_note = True
                try:
                    log_func(f"[prewarm-lock] waiting (holder pid={pid}, alive={alive})")
                except Exception as e:  # noqa: BLE001 — raw 버스 진단 유지 (동작 불변)
                    from chzzktube.core import raw_log
                    raw_log.raw("POT", f"log_func error: {type(e).__name__}: {e}", is_error=True, to_tui=False)
        except OSError:
            return None
        if _time.monotonic() >= deadline:
            if log_func:
                try:
                    log_func("[prewarm-lock] busy — acquire timeout")
                except Exception as e:  # noqa: BLE001 — raw 버스 진단 유지 (동작 불변)
                    from chzzktube.core import raw_log
                    raw_log.raw("POT", f"log_func error: {type(e).__name__}: {e}", is_error=True, to_tui=False)
            return None
        _time.sleep(0.2)


def release_prewarm_lock(fd, log_func=None):
    """락 해제 — fd close + 파일 제거 (best-effort)."""
    try:
        os.close(fd)
    except OSError:
        pass
    try:
        os.remove(_prewarm_lock_path())
    except OSError:
        pass
    if log_func:
        try:
            log_func("[prewarm-lock] released")
        except Exception as e:  # noqa: BLE001 — raw 버스 진단 유지 (동작 불변)
            from chzzktube.core import raw_log
            raw_log.raw("POT", f"log_func error: {type(e).__name__}: {e}", is_error=True, to_tui=False)


def download_and_install_source(want_ver, log_func=None):
    """지정된 버전의 bgutil 서버 소스를 다운로드하여 세팅한다."""
    dest_dir = server_home()
    tmp = tempfile.mkdtemp(prefix="chzzktube_bgutil_")
    zpath = os.path.join(tmp, "src.zip")
    try:
        url = _TAG_ZIP.format(ver=want_ver)
        log_f12_net(f"GET {url} -> {zpath}")
        if log_func:
            _download_with_progress(url, zpath, log_func, "bgutil source downloading")
        else:
            urllib.request.urlretrieve(url, zpath)

        with zipfile.ZipFile(zpath) as zf:
            names = zf.namelist()
            root = (names[0].split("/")[0] if names else "") or f"bgutil-ytdlp-pot-provider-{want_ver}"
            zf.extractall(tmp)

        inner = os.path.join(tmp, root)
        if not os.path.isfile(os.path.join(inner, "server", "package.json")):
            raise RuntimeError("downloaded source has no server/ directory")

        os.makedirs(dest_dir, exist_ok=True)
        shutil.copytree(inner, dest_dir, dirs_exist_ok=True)
        try:
            with open(os.path.join(dest_dir, ".version"), "w", encoding="utf-8") as vf:
                vf.write(str(want_ver))
            with open(os.path.join(dest_dir, "server", ".version"), "w", encoding="utf-8") as vf:
                vf.write(str(want_ver))
        except Exception as e:  # noqa: BLE001 — 버전 마커 기록 실패는 무시 (소스 전개 완료가 본질)
            log_f12_net(f".version marker write failed: {type(e).__name__}", is_error=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _communicate_with_ticks(proc, timeout, tick_func, tick_interval):
    """communicate waiting loop that fires tick_func() periodically.

    [Followup-1] communicate() blocks without output, so a long npm ci/tsc run was
    indistinguishable from a stall — the P5 fallback extension never got a heartbeat
    during the POT build phase. Windows cannot select() on pipes, so we wait with a
    short timeout repeatedly and emit a heartbeat each round; the final timeout is
    still honored by re-raising TimeoutExpired.
    """
    if tick_func is None or not tick_interval or tick_interval <= 0:
        return proc.communicate(timeout=timeout)
    import time as _time
    deadline = None if timeout is None else _time.monotonic() + timeout
    while True:
        try:
            return proc.communicate(timeout=tick_interval)
        except subprocess.TimeoutExpired:
            if proc.poll() is not None:
                return proc.communicate(timeout=1)
            tick_func()
            if deadline is not None and _time.monotonic() >= deadline:
                raise


def _run_and_stream_log(cmd, cwd, log_full_func, env=None, use_no_window=True,
                        timeout=None, tick_func=None, tick_interval=5.0,
                        proc_registry=None):
    """서브프로세스 실행 + 출력 스트리밍.

    use_no_window=False로 설정하면 CREATE_NO_WINDOW 플래그를 적용하지 않음.
    tsc 등 콘솔 출력에 의존하는 도구는 이 옵션을 False로 설정해야 함.

    [P3c] timeout 초과 시 직접 자식만 강제 종료하고 -1을 반환한다. npm ci/tsc가
    무응답이면 프리웜 워커가 영구 점유되어 is_busy()가 고정되고 POT 게이트
    다운로드가 큐에서 풀리지 않는다 — 상한이 반드시 필요하다.
    [Followup-2] job-object(TerminateJobObject)/process-group kill_tree로 트리 전체를 정리한다.
    [F12] 실행 원문(`$ cmdline` + stdout/stderr)은 log_f12_cli로만 발행한다 —
    to_tui=False 강제이므로 메인 TUI 콘솔은 오염되지 않는다.
    """
    cmd_line = " ".join(map(str, cmd))
    log_f12_cli(cmd_line, None, stage="POT", tag="pot-cli")
    try:
        kwargs = daemon_spawn_kwargs(use_no_window=use_no_window)
        proc = subprocess.Popen(
            cmd, cwd=cwd,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
            env=env, **kwargs,
        )
        assign_to_job_object(proc)  # [Followup-2] app-exit cleanup (kill-on-close)
        if proc_registry is not None:
            proc_registry.append(proc)
        try:
            stdout, _ = _communicate_with_ticks(proc, timeout, tick_func, tick_interval)
        except subprocess.TimeoutExpired:
            kill_tree(proc)  # [Followup-2] tree kill (job object / process group)
            log_f12_cli(None, f"timeout ({timeout}s) — killed", is_error=True, stage="POT", tag="pot-cli")
            if log_full_func:
                log_full_func(
                    f"subprocess timeout ({timeout}s) — killed: {' '.join(map(str, cmd))}"
                )
            return -1
        if proc_registry is not None:
            try:
                proc_registry.remove(proc)
            except ValueError:
                pass
        if stdout:
            log_f12_cli(None, stdout, is_error=(proc.returncode != 0), stage="POT", tag="pot-cli")
            if log_full_func:
                for line in stdout.splitlines():
                    stripped = line.strip()
                    if stripped:
                        log_full_func(stripped)
        return proc.returncode
    except Exception as e:  # noqa: BLE001 — Popen 실패는 F12 진단 + -1 반환 계약
        log_f12_cli(None, f"[{type(e).__name__}] {e}", is_error=True, stage="POT", tag="pot-cli")
        if log_full_func:
            log_full_func(f"subprocess Popen error: {e}")
        return -1


def _prune_outdated_node_dirs(node_dir):
    """요구 버전 미만의 구형 Node.js 캐시 폴더 정리 (디스크 낭비 방지)."""
    import re as _re
    try:
        for name in os.listdir(node_dir):
            m = _re.match(r"node-v(\d+)\.", name)
            if m and int(m.group(1)) < NODE_MIN_MAJOR:
                shutil.rmtree(os.path.join(node_dir, name), ignore_errors=True)
    except Exception as e:  # noqa: BLE001 — raw 버스 진단 유지 (동작 불변)
        from chzzktube.core import raw_log
        raw_log.raw("POT", f"_prune_outdated_node_dirs error: {type(e).__name__}: {e}", is_error=True, to_tui=False)


def _ensure_node_runtime(log) -> Result:
    """Node.js 런타임 가용성 확인."""
    from chzzktube.infra.node_provider import ensure_node_runtime, node_exe
    if not ensure_node_runtime(log):
        return Result(success=False, error=f"Node.js runtime unavailable (>= {NODE_MIN_MAJOR} required)")
    curr_node = node_exe()
    if not curr_node:
        return Result(success=False, error="Node.js executable not found")
    return Result(success=True, value=curr_node)


def _resolve_npm_command(curr_node) -> Result:
    """npm 명령어 결정 (npm-cli.js → npm_exe 우선순위)."""
    npm_cli = None
    node_base_dir = os.path.dirname(curr_node)
    search_dirs = [node_base_dir]
    if os.path.basename(node_base_dir) == "bin":
        search_dirs.append(os.path.dirname(node_base_dir))
    for s_dir in search_dirs:
        for root, dirs, files in os.walk(s_dir):
            if "npm-cli.js" in files:
                npm_cli = os.path.join(root, "npm-cli.js")
                break
        if npm_cli:
            break
    if npm_cli:
        return Result(success=True, value=[curr_node, npm_cli])
    from chzzktube.infra.node_provider import npm_exe
    npm_path = npm_exe()
    if not npm_path:
        return Result(success=False, error="npm not found in isolated Node.js runtime")
    return Result(success=True, value=[npm_path])


def _ensure_source_fetched(ver, log, log_full):
    """소스 코드 존재 확인 및 필요 시 다운로드."""
    server_src_dir = os.path.join(server_home(), "server")
    source_exists = os.path.isdir(server_src_dir) and os.path.isfile(
        os.path.join(server_src_dir, "package.json")
    )
    if not source_exists:
        log(emit_component("pot", "RUN", "pot", f"bgutil source fetching (v{ver})"))
        try:
            download_and_install_source(ver, log)
        except Exception as ds_ex:  # noqa: BLE001 — 소스 수급 실패는 호출자 로그 후 폴백
            log_full(f"[pot] source fetch failed: {ds_ex}")
    else:
        log(emit_component("pot", "RUN", "pot", "bgutil source detected — building"))


def _run_npm_install(server_dir, npm_cmd, curr_node, log, log_full, tick_func, proc_registry) -> Result:
    """npm ci 실행."""
    log(emit_component("pot", "RUN", "pot", "npm install... (first run may take minutes)"))
    env = os.environ.copy()
    node_dir = os.path.dirname(os.path.abspath(curr_node))
    env["PATH"] = node_dir + os.pathsep + env.get("PATH", "")
    ret = _run_and_stream_log(
        npm_cmd + ["ci", "--no-audit", "--no-fund"], server_dir, log_full, env=env,
        timeout=_NPM_CI_TIMEOUT, tick_func=tick_func, proc_registry=proc_registry,
    )
    if ret != 0:
        return Result(success=False, error=f"npm install failed (exit code {ret})")
    return Result(success=True)


def _run_tsc_compile(server_dir, curr_node, npm_cmd, log, log_full, tick_func, proc_registry) -> Result:
    """tsc 컴파일 실행."""
    log(emit_component("pot", "RUN", "pot", "tsc compiling..."))
    # [tsc incremental 함정 수리]
    if built_server_js() is None:
        tsbi = os.path.join(server_dir, "tsconfig.tsbuildinfo")
        if os.path.isfile(tsbi):
            try:
                os.remove(tsbi)
                log_full("[pot] stale tsbuildinfo purged — forcing full tsc compile")
            except OSError as tsbi_ex:
                log_full(f"[pot] tsbuildinfo purge failed: {tsbi_ex}")

    local_tsc = os.path.join(server_dir, "node_modules", "typescript", "bin", "tsc")
    if os.path.isfile(local_tsc):
        cmd_build = [curr_node, local_tsc]
    else:
        cmd_build = [*npm_cmd, "exec", "tsc"] if npm_cmd else ["npx", "tsc"]

    # env 구성 (npm install과 동일하게)
    env = os.environ.copy()
    node_dir = os.path.dirname(os.path.abspath(curr_node))
    env["PATH"] = node_dir + os.pathsep + env.get("PATH", "")

    ret = _run_and_stream_log(
        cmd_build, server_dir, log_full, env=env,
        use_no_window=False, timeout=_TSC_TIMEOUT,
        tick_func=tick_func, proc_registry=proc_registry,
    )
    if ret != 0:
        return Result(success=False, error=f"tsc failed (exit code {ret})")
    return Result(success=True)


def _verify_build_output() -> Result:
    """빌드 산출물 검증."""
    if built_server_js() is None:
        return Result(success=False, error="server/build/main.js (or dist/main.js) missing after compile")
    return Result(success=True)


def ensure_node_server(log, log_full, want_ver, rebuild=False,
                       tick_func=None, proc_registry=None) -> Result:
    """Node.js HTTP 서버 및 빌드 소스 구성을 완료한다.

    [rebuild 플래그]
    - True: 기존 빌드가 있더라도 npm ci / tsc 강제 재실행 (서버 업데이트용)
    - False: 빌드 산출물 존재 시 재사용 (런타임만 확인)

    [흐름]
    1. 빌드 디렉터리(server/) 존재 여부로 분기
       - server/ 없음 → source fetch → npm ci → tsc
       - server/ 있음 + rebuild=False → 기존 빌드 재사용
    2. 빌드 성공 시 server_dir 반환 → 호출부에서 _spawn_existing 기동

    반환: Result(success=True, value=server_dir) 또는 Result(success=False, error=str)
    """
    from chzzktube.infra.node_provider import (
        ensure_node_runtime,
        node_ok,
    )

    js = built_server_js()

    # [rebuild 모드] npm ci + tsc 강제 재실행
    if js is None or rebuild:
        ver = want_ver or latest_server_ver() or _SERVER_FALLBACK_VER
        # 1단계: 소스 확보
        _ensure_source_fetched(ver, log, log_full)

        # 2단계: Node.js 런타임 확인
        node_result = _ensure_node_runtime(log)
        if not node_result.success:
            return Result(success=False, error=node_result.error)
        curr_node = node_result.value

        # 3단계: npm 명령 결정
        npm_result = _resolve_npm_command(curr_node)
        if not npm_result.success:
            return Result(success=False, error=npm_result.error)
        npm_cmd = npm_result.value

        server_dir = os.path.join(server_home(), "server")

        # 4단계: npm install
        install_result = _run_npm_install(server_dir, npm_cmd, curr_node, log, log_full, tick_func, proc_registry)
        if not install_result.success:
            return Result(success=False, error=install_result.error)

        # 5단계: tsc 컴파일
        tsc_result = _run_tsc_compile(server_dir, curr_node, npm_cmd, log, log_full, tick_func, proc_registry)
        if not tsc_result.success:
            return Result(success=False, error=tsc_result.error)

        # 6단계: 빌드 산출물 검증
        verify_result = _verify_build_output()
        if not verify_result.success:
            return Result(success=False, error=verify_result.error)

        try:
            with open(os.path.join(server_home(), ".version"), "w", encoding="utf-8") as vf:
                vf.write(str(ver))
            with open(os.path.join(server_home(), "server", ".version"), "w", encoding="utf-8") as vf:
                vf.write(str(ver))
        except Exception as e:  # noqa: BLE001 — 버전 마커 기록 실패는 무시 (빌드 성공이 본질)
            log_f12_net(f".version marker write failed: {type(e).__name__}", is_error=True)

        return Result(success=True, value=server_dir)

    # [재사용 모드] 기존 빌드가 있으면 런타임만 확인 → 즉시 반환
    if not ensure_node_runtime(log):
        return Result(success=False, error="Node.js runtime unavailable")
    if node_ok():
        return Result(success=True, value=os.path.dirname(server_home()))
    return Result(success=False, error="Node.js runtime check failed")
