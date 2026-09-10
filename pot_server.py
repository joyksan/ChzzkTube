"""bgutil PO Token 서버 수명 주기 전용 모듈 (SRP: 서버 수급/빌드/기동만 담당).

- latest_server_ver / server_installed_ver : 버전 확인 (GitHub API + 로컬 마커)
- download_and_install_source : 지정 버전 소스 패치
- ensure_node_server : npm ci + tsc 빌드 파이프라인
- _spawn_node_server / _spawn_existing : Node.js HTTP 서버 기동
- _wait_port / _kill : 프로세스 생명주기 헬퍼
- _download_with_progress : 친절한 진행률 다운로드

Node.js 런타임 수급은 node_provider.py가 담당. 공유 헬퍼(get_writable_base,
server_home, assign_to_job_object 등)는 여기 정의 후 node_provider/pot_provider
가서 re-import.
"""
import os
import sys
import time
import json
import shutil
import zipfile
import tarfile
import platform
import subprocess
import urllib.request
import tempfile

import config
from log_console import emit_component
from po_client import DEFAULT_HOST, DEFAULT_PORT, probe_server
from node_provider import NODE_MIN_MAJOR, _NO_WINDOW


_TAG_ZIP = (
    "https://github.com/Brainicism/bgutil-ytdlp-pot-provider/archive/refs/tags/{ver}.zip"
)
_SERVER_FALLBACK_VER = "1.3.2"


# ── 공유 헬퍼 (node_provider에서도 사용) ──────────────────────────────
def get_writable_base():
    """사용자 환경에서 쓰기 권한이 100% 보장되는 로컬 앱 데이터 디렉터리 반환.

    경로 계산은 config.writable_base(단일 출처)에 위임하고 생성만 담당.
    ※ node_provider.get_writable_base와 동일 구현 — 중복을 허용하되
    pot_server가 독립 import 체인을 유지하도록 여기에 정의.
    """
    path = config.writable_base()
    os.makedirs(path, exist_ok=True)
    return path


def _is_portable():
    """PyInstaller(frozen) 패키징 여부."""
    return bool(getattr(sys, "frozen", False))


def _bundle_root():
    """포터블에서 번들 데이터가 풀린 디렉터리 (onedir) _MEIPASS."""
    if _is_portable():
        return getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(sys.executable)))
    return None


def server_home():
    """PO Token 서버 소스/빌드를 둘 위치."""
    writable_path = os.path.join(get_writable_base(), "bgutil-ytdlp-pot-provider")
    if os.path.isdir(writable_path):
        return writable_path

    if _is_portable():
        bundle_path = os.path.join(_bundle_root() or "", "bgutil-ytdlp-pot-provider")
        if os.path.isdir(bundle_path):
            return bundle_path

    os.makedirs(writable_path, exist_ok=True)
    return writable_path


def assign_to_job_object(proc):
    """Windows: 프로세스를 Job Object에 할당해 부모 종료 시 자동 정리."""
    if platform.system() != "Windows":
        return
    try:
        import ctypes
        from ctypes import wintypes

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("ReadOperationCount", ctypes.c_uint64),
                ("WriteOperationCount", ctypes.c_uint64),
                ("OtherOperationCount", ctypes.c_uint64),
                ("ReadTransferCount", ctypes.c_uint64),
                ("WriteTransferCount", ctypes.c_uint64),
                ("OtherTransferCount", ctypes.c_uint64),
            ]

        class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                ("IoInfo", IO_COUNTERS),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        kernel32 = ctypes.windll.kernel32
        h_job = kernel32.CreateJobObjectW(None, None)
        if not h_job:
            return

        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE

        kernel32.SetInformationJobObject(
            h_job, 9, ctypes.byref(info), ctypes.sizeof(info)
        )

        if hasattr(proc, "_handle") and proc._handle:
            kernel32.AssignProcessToJobObject(h_job, proc._handle)
    except Exception:
        pass


def read_server_log_tail(n=10):
    """bgutil_server.log의 마지막 n줄 반환 (디버깅용)."""
    log_file_path = os.path.join(get_writable_base(), "bgutil_server.log")
    if os.path.isfile(log_file_path):
        try:
            with open(log_file_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            return "".join(lines[-n:])
        except Exception:
            pass
    return ""


# ── 서버 버전·소스 관리 ─────────────────────────────────────────────
_SERVER_FALLBACK_VER = "1.3.2"
_TAG_ZIP = (
    "https://github.com/Brainicism/bgutil-ytdlp-pot-provider/archive/refs/tags/{ver}.zip"
)


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
    except Exception:
        return None


def server_installed_ver():
    """로컬에 전개된 bgutil 서버 버전 (.version 마커). 없으면 None."""
    try:
        with open(os.path.join(server_home(), ".version"), encoding="utf-8") as f:
            return f.read().strip() or None
    except OSError:
        return None


def clean_stale_plugin():
    """구버전에서 설치된 bgutil Python 플러그인 제거.

    yt_dlp_plugins/ 아래 getpot_bgutil이 남으면 yt-dlp 플러그인 로더가
    자동 로드해 fetch_po_token과 이중 주입 → 토큰 충돌 위험. 기동 시 1회.
    대상: <writable_base>/yt_dlp_plugins, <components>/yt-dlp/yt_dlp_plugins
    """
    import components
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
    except Exception:
        pass


def kill_process_on_port(port=DEFAULT_PORT, log_func=None):
    """지정된 포트를 점유한 프로세스 강제 종료 (크로스플랫폼).

    좀비 프로세스 정리용 — server_ping이 True인데 PID가 죽은 경우 호출.
    """
    import platform as _plat
    killed = False
    try:
        if _plat.system() == "Windows":
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
                                )
                                if log_func:
                                    log_func(f"[pot:zombie] killed windows pid={pid} on port {port}")
                                killed = True
            except Exception:
                pass
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
            except Exception:
                pass
    except Exception:
        pass
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
    from node_provider import node_exe
    try:
        exe = node_exe()
        if not exe:
            if log_func:
                try:
                    log_func("[pot-readiness] not ready: node missing")
                except Exception:
                    pass
            return False, "node missing"
    except Exception:
        return False, "node missing"
    try:
        js = built_server_js()
        if not js:
            if log_func:
                try:
                    log_func("[pot-readiness] not ready: no build")
                except Exception:
                    pass
            return False, "no build"
    except Exception:
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
                    except Exception:
                        pass
                if want_refresh:
                    return True, f"stale {local}→{remote} (refresh pending)"
                return False, f"stale {local}→{remote}"
        except Exception:
            pass
    if log_func:
        try:
            log_func(f"[pot-readiness] standby (node ok, build {js})")
        except Exception:
            pass
    return True, "standby"


def _spawn_node_server(log_full_func=None):
    """Node.js로 bgutil HTTP 서버 기동하고 45초 내에 /ping 응답 확인."""
    from node_provider import node_exe

    js, node = built_server_js(), node_exe()
    if not js and log_full_func:
        log_full_func("server spawn reason: built main.js missing (server/build)")
    if not node and log_full_func:
        log_full_func(f"server spawn reason: Node.js >= {NODE_MIN_MAJOR} binary missing")
    if not (js and node):
        return None

    log_file_path = os.path.join(get_writable_base(), "bgutil_server.log")
    try:
        log_file = open(log_file_path, "w", encoding="utf-8", errors="replace")
    except Exception:
        log_file = subprocess.DEVNULL

    try:
        env = os.environ.copy()
        node_dir = os.path.dirname(os.path.abspath(node))
        env["PATH"] = node_dir + os.pathsep + env.get("PATH", "")

        kwargs = {}
        if platform.system() == "Windows":
            kwargs["creationflags"] = _NO_WINDOW | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        proc = subprocess.Popen(
            [node, js],
            cwd=os.path.dirname(js),
            stdout=log_file,
            stderr=log_file,
            env=env,
            **kwargs,
        )
        assign_to_job_object(proc)
    except Exception as e:
        if log_full_func:
            log_full_func(f"server Popen failed: {e}")
        return None
    if _wait_port(20, log_full_func):
        return proc
    _kill(proc)
    if log_full_func:
        log_full_func(
            "server spawn reason: /ping not responding in 20s "
            "(crash after startup — see bgutil_server.log)"
        )
    return None


def _spawn_existing(log_full_func=None):
    """기존 빌드가 있으면 재사용, 없으면 _spawn_node_server 위임."""
    return _spawn_node_server(log_full_func)


def _download_with_progress(url, dest_path, log_func, desc):
    """청크 단위 분할 다운로드 및 콘솔에 친절한 진행률 출력."""
    temp_dest = dest_path + ".tmp"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ChzzkTube"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            total_size = int(resp.headers.get("content-length", 0))
            downloaded = 0
            with open(temp_dest, "wb") as f:
                while True:
                    chunk = resp.read(1024 * 1024)  # 1MB
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        pct = int(downloaded / total_size * 100)
                        log_func(f"{desc}... {pct}%", True, False)
            if os.path.exists(temp_dest):
                shutil.move(temp_dest, dest_path)
    finally:
        if os.path.exists(temp_dest):
            try:
                os.remove(temp_dest)
            except Exception:
                pass


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
            except Exception:
                return True  # 판별 자체 실패 → 보수적 유지
        else:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return False
            except PermissionError:
                return True  # 존재하나 권한 없음 → 살아있음
            except Exception:
                return True
            return True
    except Exception:
        return True


def _read_lock_info(path):
    """락 파일에서 (pid:int|None, epoch:float|None) 판독."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            parts = f.read().strip().split()
        pid = int(parts[0]) if parts else None
        epoch = float(parts[1]) if len(parts) > 1 else None
        return pid, epoch
    except Exception:
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
                os.write(fd, f"{os.getpid()} {_time.time()}".encode("utf-8"))
            except OSError:
                pass
            if log_func:
                try:
                    log_func("[prewarm-lock] acquired")
                except Exception:
                    pass
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
                    except Exception:
                        pass
                try:
                    os.remove(path)
                except OSError:
                    pass
                continue
            if log_func and not waited_note and timeout > 0:
                waited_note = True
                try:
                    log_func(f"[prewarm-lock] waiting (holder pid={pid}, alive={alive})")
                except Exception:
                    pass
        except OSError:
            return None
        if _time.monotonic() >= deadline:
            if log_func:
                try:
                    log_func("[prewarm-lock] busy — acquire timeout")
                except Exception:
                    pass
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
        except Exception:
            pass


def download_and_install_source(want_ver, log_func=None):
    """지정된 버전의 bgutil 서버 소스를 다운로드하여 세팅한다."""
    dest_dir = server_home()
    tmp = tempfile.mkdtemp(prefix="chzzktube_bgutil_")
    zpath = os.path.join(tmp, "src.zip")
    try:
        url = _TAG_ZIP.format(ver=want_ver)
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
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _run_and_stream_log(cmd, cwd, log_full_func, env=None, use_no_window=True):
    """서브프로세스 실행 + 출력 스트리밍.

    use_no_window=False로 설정하면 CREATE_NO_WINDOW 플래그를 적용하지 않음.
    tsc 등 콘솔 출력에 의존하는 도구는 이 옵션을 False로 설정해야 함.
    """
    try:
        kwargs = {}
        if platform.system() == "Windows" and use_no_window:
            kwargs["creationflags"] = _NO_WINDOW
        proc = subprocess.Popen(
            cmd, cwd=cwd,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
            env=env, **kwargs,
        )
        stdout, _ = proc.communicate()
        if stdout and log_full_func:
            for line in stdout.splitlines():
                stripped = line.strip()
                if stripped:
                    log_full_func(stripped)
        return proc.returncode
    except Exception as e:
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
    except Exception:
        pass


def ensure_node_server(log, log_full, want_ver, rebuild=False):
    """Node.js HTTP 서버 및 빌드 소스 구성을 완료한다.

    [rebuild 플래그]
    - True: 기존 빌드가 있더라도 npm ci / tsc 강제 재실행 (서버 업데이트용)
    - False: 빌드 산출물 존재 시 재사용 (런타임만 확인)

    [흐름]
    1. 빌드 디렉터리(server/) 존재 여부로 분기
       - server/ 없음 → source fetch → npm ci → tsc
       - server/ 있음 + rebuild=False → 기존 빌드 재사용
    2. 빌드 성공 시 server_dir 반환 → 호출부에서 _spawn_existing 기동
    """
    from node_provider import (
        node_exe, node_ok, node_major_version,
        ensure_node_runtime, bundled_npm_ok,
    )

    js = built_server_js()

    # [rebuild 모드] npm ci + tsc 강제 재실행
    if js is None or rebuild:
        server_src_dir = os.path.join(server_home(), "server")
        source_exists = os.path.isdir(server_src_dir) and os.path.isfile(
            os.path.join(server_src_dir, "package.json")
        )
        if not source_exists:
            ver = want_ver or latest_server_ver() or _SERVER_FALLBACK_VER
            log(emit_component("pot", "RUN", "pot", f"bgutil source fetching (v{ver})"))
            try:
                download_and_install_source(ver, log)
            except Exception as ds_ex:
                log_full(f"[pot] source fetch failed: {ds_ex}")
        else:
            log(emit_component("pot", "RUN", "pot", "bgutil source detected — building"))

        if not ensure_node_runtime(log):
            return None, f"Node.js runtime unavailable (>= {NODE_MIN_MAJOR} required)"
        curr_node = node_exe()
        if not curr_node:
            return None, "Node.js executable not found"

        npm_cli = None
        node_base_dir = os.path.dirname(curr_node)
        for root, dirs, files in os.walk(node_base_dir):
            if "npm-cli.js" in files:
                npm_cli = os.path.join(root, "npm-cli.js")
                break

        npm_cmd = [curr_node, npm_cli] if npm_cli else [shutil.which("npm") or "npm"]
        server_dir = os.path.join(server_home(), "server")

        try:
            log(emit_component("pot", "RUN", "pot", "npm install... (first run may take minutes)"))
            env = os.environ.copy()
            node_dir = os.path.dirname(os.path.abspath(curr_node))
            env["PATH"] = node_dir + os.pathsep + env.get("PATH", "")

            cmd_install = npm_cmd + ["ci", "--no-audit", "--no-fund"]
            ret = _run_and_stream_log(cmd_install, server_dir, log_full, env=env)
            if ret != 0:
                return None, f"npm install failed (exit code {ret})"

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
                cmd_build = [curr_node, npm_cli, "execute", "tsc"] if npm_cli else ["npx", "tsc"]

            ret = _run_and_stream_log(cmd_build, server_dir, log_full, env=env, use_no_window=False)
            if ret != 0:
                return None, f"tsc failed (exit code {ret})"

            if built_server_js() is None:
                return None, "server/build/main.js (or dist/main.js) missing after compile"
            return server_dir, None
        except Exception as e:
            return None, f"{type(e).__name__}: {e}"

    # [재사용 모드] 기존 빌드가 있으면 런타임만 확인 → 즉시 반환
    if not ensure_node_runtime(log):
        return None, "Node.js runtime unavailable"
    if node_ok():
        return os.path.dirname(server_home()), None
    return None, "Node.js runtime check failed"
