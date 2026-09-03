import importlib.metadata as im
import importlib.util
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
import platform
import json
import re
import tarfile
import config
import log_console
from log_console import emit_component
from PyQt6.QtCore import QThread, pyqtSignal

_GLOBAL_JOB_HANDLE = None

def assign_to_job_object(proc):
    global _GLOBAL_JOB_HANDLE
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
            h_job,
            9,  # JobObjectExtendedLimitInformation
            ctypes.byref(info),
            ctypes.sizeof(info)
        )

        if hasattr(proc, "_handle") and proc._handle:
            kernel32.AssignProcessToJobObject(h_job, proc._handle)
            
        _GLOBAL_JOB_HANDLE = h_job
    except Exception:
        pass

def read_server_log_tail(n=10):
    log_file_path = os.path.join(get_writable_base(), "bgutil_server.log")
    if os.path.isfile(log_file_path):
        try:
            with open(log_file_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
                return "".join(lines[-n:])
        except Exception:
            pass
    return ""

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 4416
_PKG = "bgutil-ytdlp-pot-provider"
_FALLBACK_PLUGIN_VER = "1.3.2"
_TAG_ZIP = "https://github.com/Brainicism/bgutil-ytdlp-pot-provider/archive/refs/tags/{ver}.zip"
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

NODE_MIN_MAJOR = 22  # bgutil 서버의 Node 요구사항 (require(esm) 기본 지원선)
_NODE_FALLBACK_VER = "v22.23.2"  # nodejs.org index 조회 실패 시 폴백 (v22 LTS)
_node_ver_cache = {}

def node_major_version(node_path, timeout=10):
    """node --version 출력에서 major 버전 추출 (판별 실패 시 None, 결과 캐시)."""
    if not node_path:
        return None
    if node_path in _node_ver_cache:
        return _node_ver_cache[node_path]
    major = None
    try:
        kwargs = {}
        if platform.system() == "Windows":
            kwargs["creationflags"] = _NO_WINDOW
        out = subprocess.run(
            [node_path, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            **kwargs,
        )
        m = re.match(r"v?(\d+)", (out.stdout or "").strip())
        if m:
            major = int(m.group(1))
    except Exception:
        major = None
    _node_ver_cache[node_path] = major
    return major

def latest_lts_node_url(major=NODE_MIN_MAJOR):
    """nodejs.org dist index에서 지정 major의 최신 플랫폼별 URL (조회 실패 시 폴백)."""
    try:
        with urllib.request.urlopen(
            "https://nodejs.org/dist/index.json", timeout=15
        ) as resp:
            entries = json.load(resp)
        ver = next(
            (
                e.get("version")
                for e in entries
                if str(e.get("version", "")).startswith(f"v{major}.")
            ),
            None,
        )
        if ver:
            return _platform_node_url(ver)
    except Exception:
        pass
    return _platform_node_url(_NODE_FALLBACK_VER)


def _platform_node_url(ver):
    """플랫폼별 Node.js 배포 URL 생성 (Windows: zip, macOS: tar.gz)."""
    system = platform.system()
    if system == "Windows":
        return f"https://nodejs.org/dist/{ver}/node-{ver}-win-x64.zip"
    if system == "Darwin":
        # macOS: Apple Silicon 우선, 없으면 x64
        arch = "arm64" if platform.machine() == "arm64" else "x64"
        return f"https://nodejs.org/dist/{ver}/node-{ver}-darwin-{arch}.tar.gz"
    # Linux 등 기타 플랫폼
    arch = "arm64" if platform.machine() == "arm64" else "x64"
    return f"https://nodejs.org/dist/{ver}/node-{ver}-linux-{arch}.tar.gz"

def node_ok():
    """현재 탐색된 node가 bgutil 요구 버전(Node >= 22)을 충족하는지."""
    return (node_major_version(node_exe()) or 0) >= NODE_MIN_MAJOR

def _is_portable():
    """PyInstaller(frozen) 패키징 여부."""
    return bool(getattr(sys, "frozen", False))

def _bundle_root():
    """포터블에서 번들 데이터가 풀린 디렉터리 (onedir) _internal."""
    if _is_portable():
        return getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(sys.executable)))
    return None

def get_writable_base():
    """사용자 환경에서 쓰기 권한이 100% 보장되는 로컬 앱 데이터 디렉터리 반환.
    경로 계산은 config.writable_base(단일 출처)에 위임하고 생성만 담당."""
    path = config.writable_base()
    os.makedirs(path, exist_ok=True)
    return path

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

def node_exe():
    """PO Token 서버 기동용 node 탐색 — bgutil 요구(Node >= 22) 충족 후보만 유효.

    후보 순서: 캐시된 포터블 node → frozen 번들 → 시스템 PATH. 요구 버전을
    충족하는 후보가 하나도 없으면 None을 반환해 ensure_node_runtime의
    재구성(최신 v22 수급)을 트리거한다. 단, 전 후보의 버전 판별이 모두
    실패하면 첫 후보를 그대로 돌려 무한 재설치 루프를 막는다.
    """
    cands = []
    local_node_dir = os.path.join(get_writable_base(), "node")
    if os.path.isdir(local_node_dir):
        exe_name = "node.exe" if platform.system() == "Windows" else "node"
        for root, dirs, files in os.walk(local_node_dir):
            if exe_name in files:
                cands.append(os.path.join(root, exe_name))
    # [macOS] 포터블 node 실행 권한 보장 (tar.gz 추출 시 실행 비트 누락 방지)
    if platform.system() != "Windows":
        for c in cands:
            try:
                mode = os.stat(c).st_mode
                if not (mode & 0o111):
                    os.chmod(c, mode | 0o755)
            except Exception:
                pass

    if _is_portable():
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        _exe_suffix = ".exe" if os.name == "nt" else ""
        cands.extend(
            c for c in [
                os.path.join(exe_dir, f"node{_exe_suffix}"),
                os.path.join(exe_dir, "_internal", f"node{_exe_suffix}"),
                os.path.join(exe_dir, "_internal", "node", f"node{_exe_suffix}"),
            ]
            if os.path.isfile(c)
        )
        _me = getattr(sys, "_MEIPASS", None)
        if _me and os.path.isfile(os.path.join(_me, f"node{_exe_suffix}")):
            cands.insert(0, os.path.join(_me, f"node{_exe_suffix}"))

    which_node = shutil.which("node")
    if which_node:
        cands.append(which_node)

    majors = [(c, node_major_version(c)) for c in cands]
    ok = [c for c, m in majors if m is not None and m >= NODE_MIN_MAJOR]
    if ok:
        return ok[0]
    if majors and all(m is None for _, m in majors):
        return majors[0][0]  # 버전 판별 전면 실패 폴백 — 무한 재설치 방지
    return None

def plugin_version():
    """설치된 플러그인 버전 조회."""
    try:
        return im.version(_PKG)
    except Exception:
        return None

def plugin_installed():
    """yt-dlp 플러그인이 로컬 격리 경로 또는 시스템 패키지에 적재되어 있는지 확인."""
    if plugin_version():
        return True
    try:
        if importlib.util.find_spec("yt_dlp_plugins.extractor.getpot_bgutil") is not None:
            return True
    except Exception:
        pass
        
    local_plugin_dir = os.path.join(get_writable_base(), "yt_dlp_plugins", "extractor")
    if os.path.isdir(local_plugin_dir):
        if any(f.startswith("getpot_bgutil") and f.endswith(".py") for f in os.listdir(local_plugin_dir)):
            return True
            
    if _is_portable():
        root = _bundle_root()
        if root:
            ext_dir = os.path.join(root, "yt_dlp_plugins", "extractor")
            if os.path.isdir(ext_dir) and any(
                f.startswith("getpot_bgutil") and f.endswith(".py")
                for f in os.listdir(ext_dir)
            ):
                return True
    return False

def probe_server(host=DEFAULT_HOST, port=DEFAULT_PORT, timeout=1.5):
    """서버 상태 모니터링 (HTTP /ping 응답 기준)"""
    url = f"http://{host}:{port}/ping"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if 200 <= resp.status < 300:
                return "ok", ""
            return "conflict", f"HTTP {resp.status}"
    except urllib.error.HTTPError as e:
        return "conflict", f"HTTP {e.code}"
    except urllib.error.URLError as e:
        if isinstance(getattr(e, "reason", None), ConnectionRefusedError):
            return "down", ""
    except Exception:
        pass
        
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return "conflict", "ping no response"
    except OSError:
        return "down", ""

def server_running(host=DEFAULT_HOST, port=DEFAULT_PORT, timeout=1.5):
    return probe_server(host, port, timeout)[0] == "ok"

def _wait_port(seconds):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if server_running():
            return True
        time.sleep(0.5)
    return False

def _kill(proc):
    try:
        proc.kill()
    except Exception:
        pass

def built_server_js():
    js = os.path.join(server_home(), "server", "build", "main.js")
    return js if os.path.isfile(js) else None

def _spawn_node_server(log_full_func=None):
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
    if _wait_port(45):
        return proc
    _kill(proc)
    if log_full_func:
        log_full_func(
            "server spawn reason: /ping not responding in 45s "
            "(crash after startup — see bgutil_server.log)"
        )
    return None

def _spawn_existing(log_full_func=None):
    return _spawn_node_server(log_full_func)

def _tail(stdout, stderr, n=4):
    text = (stderr or "").strip() or (stdout or "").strip()
    lines = [l for l in text.splitlines() if l.strip()]
    return "\n".join(lines[-n:])

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

def ensure_node_runtime(log_func):
    """bgutil 서버 요구(Node >= 22) 충족을 위한 Node.js 런타임 자동 수급/재구성.

    [수정 이력] 구버전은 v20.18.0을 받아 bgutil의 require(esm) 요구를 충족하지
    못해 서버가 ERR_REQUIRE_ESM으로 크래시했다 (PO Token 기동 실패의 근본 원인).
    """
    cur = node_exe()
    cur_major = node_major_version(cur) if cur else None
    if cur_major is not None and cur_major >= NODE_MIN_MAJOR:
        return True
    if cur_major is not None:
        log_func(
            f"Node.js v{cur_major} is below bgutil requirement "
            f"(Node >= {NODE_MIN_MAJOR}) — reconfiguring to latest runtime."
        )
    else:
        log_func("node.js >= 22 missing — downloading portable runtime")

    node_dir = os.path.join(get_writable_base(), "node")
    os.makedirs(node_dir, exist_ok=True)

    node_url = latest_lts_node_url()
    is_tarball = node_url.endswith(".tar.gz")
    dest_name = "node_portable.tar.gz" if is_tarball else "node_portable.zip"
    archive_dest = os.path.join(get_writable_base(), dest_name)

    try:
        _download_with_progress(node_url, archive_dest, log_func, "node.js runtime downloading")
        log_func("node.js runtime extracting...")
        if is_tarball:
            # 기존 디렉토리를 완전히 삭제하여 권한 문제 회피
            if os.path.exists(node_dir):
                try:
                    for root, dirs, files in os.walk(node_dir):
                        for d in dirs:
                            try:
                                os.chmod(os.path.join(root, d), 0o755)
                            except (PermissionError, OSError):
                                pass
                        for f in files:
                            try:
                                os.chmod(os.path.join(root, f), 0o755)
                            except (PermissionError, OSError):
                                pass
                    shutil.rmtree(node_dir, ignore_errors=True)
                except Exception:
                    pass
            os.makedirs(node_dir, exist_ok=True)
            # subprocess로 tar 명령어 직접 실행 (권한 문제 회피)
            import subprocess
            try:
                result = subprocess.run(
                    ["tar", "-xzf", archive_dest, "-C", node_dir],
                    capture_output=True,
                    text=True,
                    timeout=120
                )
                if result.returncode != 0:
                    raise RuntimeError(f"tar failed: {result.stderr}")
            except Exception:
                # 실패 시 Python tarfile로 시도
                with tarfile.open(archive_dest, "r:gz") as tf:
                    if sys.version_info >= (3, 12):
                        tf.extractall(node_dir, filter="data")
                    else:
                        for member in tf.getmembers():
                            try:
                                tf.extract(member, node_dir)
                            except (PermissionError, OSError):
                                pass
        else:
            with zipfile.ZipFile(archive_dest, "r") as z:
                z.extractall(node_dir)
        _node_ver_cache.clear()
        new_node = node_exe()
        new_major = node_major_version(new_node) if new_node else None
        if new_major is not None and new_major >= NODE_MIN_MAJOR:
            log_func(f"portable Node.js v{new_major} ready.")
            _prune_outdated_node_dirs(node_dir)
            return True
        log_func(
            f"Node.js still below requirement (>= {NODE_MIN_MAJOR}) after configure",
            False,
            True,
        )
        return False
    except Exception as e:
        log_func(f"Node.js auto-setup failed: {e}", False, True)
        return False
    finally:
        if os.path.exists(archive_dest):
            try:
                os.remove(archive_dest)
            except Exception:
                pass

def _prune_outdated_node_dirs(node_dir):
    """요구 버전 미달의 구형 Node.js 캐시 폴더 정리 (디스크 낭비 방지)."""
    try:
        for name in os.listdir(node_dir):
            m = re.match(r"node-v(\d+)\.", name)
            if m and int(m.group(1)) < NODE_MIN_MAJOR:
                shutil.rmtree(os.path.join(node_dir, name), ignore_errors=True)
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

def _run_and_stream_log(cmd, cwd, log_full_func, env=None):
    try:
        kwargs = {}
        if platform.system() == "Windows":
            kwargs["creationflags"] = _NO_WINDOW
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            **kwargs,
        )
        while True:
            line = proc.stdout.readline()
            if not line and proc.poll() is not None:
                break
            if line:
                stripped = line.strip()
                if stripped and log_full_func:
                    log_full_func(stripped)
        proc.wait()
        return proc.returncode
    except Exception as e:
        if log_full_func:
            log_full_func(f"subprocess Popen error: {e}")
        return -1

def ensure_node_server(log, log_full, want_ver):
    """Node.js HTTP 서버 및 빌드 소스 구성을 완료한다."""
    js = built_server_js()
    if js:
        # [결함 수리] 빌드 산출물이 있어도 Node가 없거나 요구 버전(Node >= 22)
        # 미달이면 스폰이 무조건 실패하고 err=None이라 사유도 없었다 —
        # 런타임만 재구성한 뒤 성공 판정 (npm ci/tsc 재실행은 스킵).
        if node_ok():
            return os.path.dirname(os.path.dirname(js)), None
        log(
            "[~] server build exists but Node runtime missing or insufficient — "
            "reconfiguring runtime."
        )
        if not ensure_node_runtime(log):
            return None, f"Node.js runtime unavailable (>= {NODE_MIN_MAJOR} required)"
        if node_ok():
            return os.path.dirname(os.path.dirname(js)), None
        return None, f"Node.js >= {NODE_MIN_MAJOR} setup failed"

    if not ensure_node_runtime(log):
        return None, "Node.js runtime unavailable"

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
    
    try:
        if os.path.isdir(server_home()) and os.path.isfile(os.path.join(server_home(), "server", "package.json")):
            log(emit_component("pot", "RUN", "pot", "bgutil source detected — building"))
        else:
            log(emit_component("pot", "RUN", "pot", f"bgutil source fetching (v{want_ver})"))
            download_and_install_source(want_ver, log)

        server_dir = os.path.join(server_home(), "server")
        log(emit_component("pot", "RUN", "pot", "npm install... (first run may take minutes)"))

        env = os.environ.copy()
        node_dir = os.path.dirname(os.path.abspath(curr_node))
        env["PATH"] = node_dir + os.pathsep + env.get("PATH", "")

        cmd_install = npm_cmd + ["ci", "--no-audit", "--no-fund"]
        ret = _run_and_stream_log(cmd_install, server_dir, log_full, env=env)
        if ret != 0:
            return None, f"npm install failed (exit code {ret})"

        log(emit_component("pot", "RUN", "pot", "tsc compiling..."))
        local_tsc = os.path.join(server_dir, "node_modules", "typescript", "bin", "tsc")
        if os.path.isfile(local_tsc):
            cmd_build = [curr_node, local_tsc]
        else:
            cmd_build = [curr_node, npm_cli, "exec", "tsc"] if npm_cli else ["npx", "tsc"]
            
        ret = _run_and_stream_log(cmd_build, server_dir, log_full, env=env)
        if ret != 0:
            return None, f"tsc failed (exit code {ret})"

        if built_server_js() is None:
            return None, "server/build/main.js missing after compile"
            
        return server_dir, None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"

def download_and_hot_reload_plugin(log_func, want_ver=_FALLBACK_PLUGIN_VER):
    """Download bgutil-ytdlp-pot-provider wheel and hot-reload into isolated path."""
    log_func("PO plugin fetching...")
    target_plugin_dir = os.path.join(get_writable_base(), "yt_dlp_plugins")
    os.makedirs(target_plugin_dir, exist_ok=True)
    
    pypi_url = f"https://pypi.org/pypi/{_PKG}/json"
    whl_url = None
    try:
        req = urllib.request.Request(pypi_url, headers={"User-Agent": "ChzzkTube"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            releases = data.get("releases", {})
            current_ver = data.get("info", {}).get("version", want_ver)
            files = releases.get(current_ver, [])
            for f in files:
                if f.get("filename", "").endswith(".whl"):
                    whl_url = f.get("url")
                    break
    except Exception:
        pass
        
    if not whl_url:
        whl_url = f"https://files.pythonhosted.org/packages/py3/{_PKG[0]}/{_PKG}/{_PKG.replace('-', '_')}-{want_ver}-py3-none-any.whl"
        
    tmp_whl = os.path.join(get_writable_base(), "temp_plugin.whl")
    try:
        _download_with_progress(whl_url, tmp_whl, log_func, "PO plugin downloading...")
        log_func("PO plugin extracting...")
        
        with zipfile.ZipFile(tmp_whl, "r") as z:
            for member in z.namelist():
                if member.startswith("yt_dlp_plugins/"):
                    z.extract(member, get_writable_base())
                    
        writable_base_path = get_writable_base()
        if writable_base_path not in sys.path:
            sys.path.insert(0, writable_base_path)
            
        importlib.invalidate_caches()
        
        for mod_name in list(sys.modules.keys()):
            if mod_name.startswith("yt_dlp_plugins") or mod_name.startswith("yt_dlp.plugins"):
                del sys.modules[mod_name]
                
        log_func("PO plugin hot-reload applied.")
        return True
    except Exception as e:
        log_func(f"plugin hot-fetch failed: {e}")
        return False
    finally:
        if os.path.exists(tmp_whl):
            try:
                os.remove(tmp_whl)
            except Exception:
                pass

class POTProviderWorker(QThread):
    """앱 시작 시 PO Token 서버 및 플러그인을 무중단으로 준비하고 로드하는 스레드."""
    line = pyqtSignal(str, bool, bool)
    log_full = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.outcome = ("err", "")

    def run(self):
        try:
            self._run()
        except Exception as e:
            self.outcome = (
                "err",
                emit_component("SYS", "FAIL", "pot", f"PO server auto-config failed: {type(e).__name__}: {e}"),
            )

    def _note(self, msg, is_status=False, is_error=False):
        # [병기 방지] 이미 TUI 컬럼 포맷(이중 포맷 포함)이면 그대로 emit — 재래핑 금지
        if log_console.is_tui_line(msg):
            self.line.emit(str(msg), is_status, is_error)
            return
        
        # [로그 과잉 방지] 오류 메시지는 핵심만 간결 로그에, 상세는 log_full로
        concise_msg = msg
        if is_error and len(msg) > 60:
            # 첫 번째 구분자 이전까지를 핵심 메시지로 추출
            for sep in [' — ', ' —', ': ', ':']:
                if sep in msg:
                    concise_msg = msg.split(sep)[0]
                    break
            # 상세 오류는 log_full로 전송
            self.log_full.emit(f"[pot-DETAIL] {msg}")
        
        # 플레인 메시지만 TUI 컬럼 포맷으로 래핑
        stage = "SYS" if is_error else "pot"
        status = "FAIL" if is_error else ("RUN" if is_status else "OK")
        self.line.emit(emit_component(stage, status, "pot", concise_msg), is_status, is_error)

    def _dbg(self, msg):
        """F12 verbose window + history only — not shown in concise log."""
        self.log_full.emit(f"[pot-DEBUG] {msg}")

    def _run(self):
        self._dbg("POTProviderWorker starting")
        # [ffmpeg ensure] for remux/merge — prefer system install, fallback to GitHub binary.
        # Failures unrelated to the PO server should still allow startup sequence to proceed.
        try:
            import components
            self._dbg("entering ffmpeg ensure phase")
            ff_err = components.ensure_ffmpeg(self._note)
            if ff_err:
                self._note(
                    f"ffmpeg fetch failed — merge/remux limited: {ff_err}",
                    False,
                    True,
                )
                self._dbg(f"ffmpeg fetch failed: {ff_err}")
            else:
                self._dbg("ffmpeg fetch done")
        except Exception as ff_ex:
            self._note(f"ffmpeg fetch module exception: {ff_ex}", False, True)
            self._dbg(f"ffmpeg fetch module exception: {type(ff_ex).__name__}: {ff_ex}")

        if not plugin_installed():
            self._note("PO plugin missing — downloading latest", True)
            self._dbg("plugin missing → download attempt")
            ok = download_and_hot_reload_plugin(self._note, _FALLBACK_PLUGIN_VER)
            self._dbg(f"plugin download result: {'OK' if ok else 'FAIL'}")
        else:
            self._dbg("plugin already installed — skip download")

        self._dbg(f"서버 probe 시도 → {DEFAULT_HOST}:{DEFAULT_PORT}")
        state, detail = probe_server()
        self._dbg(f"probe 결과: state={state!r} detail={detail[:200]!r}")
        if state == "ok":
            self.outcome = (
                "ok",
                emit_component("pot", "OK", "pot", f"pot server bound ({DEFAULT_HOST}:{DEFAULT_PORT})"),
            )
            self._dbg("ok branch — worker exits")
            return

        if state == "conflict":
            self.outcome = (
                "err",
                emit_component("SYS", "FAIL", "pot", f"port {DEFAULT_PORT} in use — kill the holder and retry"),
            )
            self._dbg("conflict branch — port occupied")
            return

        self._dbg("trying to spawn existing build")
        if _spawn_existing(self.log_full.emit):
            self.outcome = (
                "ok",
                emit_component("pot", "OK", "pot", f"pot server bound ({DEFAULT_HOST}:{DEFAULT_PORT})"),
            )
            self._dbg("existing build spawn ok")
            return
        self._dbg("existing build spawn failed — building fresh")

        ver = plugin_version() or _FALLBACK_PLUGIN_VER
        self._dbg(f"plugin version: {ver}")
        self._note("building PO token server...", True)
        _, err = ensure_node_server(self._note, self.log_full.emit, ver)
        self._dbg(f"ensure_node_server done: err={err!r}")

        if err is None and _spawn_existing(self.log_full.emit):
            self.outcome = (
                "ok",
                emit_component("pot", "OK", "pot", f"pot server bound ({DEFAULT_HOST}:{DEFAULT_PORT})"),
            )
            self._dbg("fresh build spawn ok")
            return

        self.outcome = (
            "err",
            emit_component("SYS", "FAIL", "pot", "server start failed — age-restricted videos unavailable"),
        )
        self._dbg("final fail — extracting tail causes")
        # [가시화] err 부재(스폰 실패) 케이스에서조차 원인이 화면에 안 떴던 문제 수리 —
        # 빌드 실패 사유와 서버 stdout/stderr(bgutil_server.log) 꼬리를 함께 노출.
        reasons = [l for l in (err or "").splitlines()[-4:] if l.strip()]
        tail = read_server_log_tail(6)
        reasons.extend(l.strip() for l in tail.splitlines() if l.strip())
        # [콘솔 정리] 진단 원인은 상세 로그(log_full)로만 — 콘솔엔
        # '실패 원인 (마지막 기록):' 같은 의미 불분명한 헤더를 띄우지 않는다.
        for l in reasons:
            self.log_full.emit(f"[POT-FAIL] {l}")
