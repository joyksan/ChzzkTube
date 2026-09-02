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
import config
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
        out = subprocess.run(
            [node_path, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=_NO_WINDOW,
        )
        m = re.match(r"v?(\d+)", (out.stdout or "").strip())
        if m:
            major = int(m.group(1))
    except Exception:
        major = None
    _node_ver_cache[node_path] = major
    return major

def latest_lts_node_url(major=NODE_MIN_MAJOR):
    """nodejs.org dist index에서 지정 major의 최신 win-x64 zip URL (조회 실패 시 폴백)."""
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
            return f"https://nodejs.org/dist/{ver}/node-{ver}-win-x64.zip"
    except Exception:
        pass
    return (
        f"https://nodejs.org/dist/{_NODE_FALLBACK_VER}/"
        f"node-{_NODE_FALLBACK_VER}-win-x64.zip"
    )

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

    if _is_portable():
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        cands.extend(
            c for c in [
                os.path.join(exe_dir, "node.exe"),
                os.path.join(exe_dir, "_internal", "node.exe"),
                os.path.join(exe_dir, "_internal", "node", "node.exe"),
            ]
            if os.path.isfile(c)
        )
        _me = getattr(sys, "_MEIPASS", None)
        if _me and os.path.isfile(os.path.join(_me, "node.exe")):
            cands.insert(0, os.path.join(_me, "node.exe"))

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
            return "conflict", "ping 무응답"
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
        log_full_func("[!] 서버 스폰 실패 사유: 빌드된 main.js 부재 (server/build)")
    if not node and log_full_func:
        log_full_func(f"[!] 서버 스폰 실패 사유: Node.js >= {NODE_MIN_MAJOR} 실행 파일 부재")
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
        
        proc = subprocess.Popen(
            [node, js],
            cwd=os.path.dirname(js),
            stdout=log_file,
            stderr=log_file,
            creationflags=_NO_WINDOW | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            env=env,
        )
        assign_to_job_object(proc)
    except Exception as e:
        if log_full_func:
            log_full_func(f"[!] 서버 Popen 실패: {e}")
        return None
    if _wait_port(45):
        return proc
    _kill(proc)
    if log_full_func:
        log_full_func(
            "[!] 서버 스폰 실패 사유: 45초 내 /ping 응답 없음 "
            "(기동 직후 크래시 추정 — bgutil_server.log 참조)"
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
                        log_func(f"[~] {desc}... {pct}% 완료", True, False)
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
            f"[~] 감지된 Node.js v{cur_major}이(가) bgutil 서버 요구사항"
            f"(Node >= {NODE_MIN_MAJOR}) 미달 — 최신 런타임으로 재구성합니다."
        )
    else:
        log_func("[~] 요구 버전 이상의 로컬 Node.js가 없어 포터블 Node.js 다운로드를 시작합니다.")

    node_dir = os.path.join(get_writable_base(), "node")
    os.makedirs(node_dir, exist_ok=True)

    node_url = latest_lts_node_url()
    zip_dest = os.path.join(get_writable_base(), "node_portable.zip")

    try:
        _download_with_progress(node_url, zip_dest, log_func, "Node.js 런타임 수신 중")
        log_func("[~] Node.js 런타임 압축 해제 중...")
        with zipfile.ZipFile(zip_dest, "r") as z:
            z.extractall(node_dir)
        _node_ver_cache.clear()
        new_node = node_exe()
        new_major = node_major_version(new_node) if new_node else None
        if new_major is not None and new_major >= NODE_MIN_MAJOR:
            log_func(f"[v] 포터블 Node.js v{new_major} 런타임 환경 구성 완료.")
            _prune_outdated_node_dirs(node_dir)
            return True
        log_func(
            f"[!] Node.js 런타임 구성 후에도 요구 버전(Node >= {NODE_MIN_MAJOR}) 미충족",
            False,
            True,
        )
        return False
    except Exception as e:
        log_func(f"[!] Node.js 자동 런타임 확보 실패: {e}", False, True)
        return False
    finally:
        if os.path.exists(zip_dest):
            try:
                os.remove(zip_dest)
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
            _download_with_progress(url, zpath, log_func, "bgutil 서버 소스 코드 수신 중")
        else:
            urllib.request.urlretrieve(url, zpath)
            
        with zipfile.ZipFile(zpath) as zf:
            names = zf.namelist()
            root = (names[0].split("/")[0] if names else "") or f"bgutil-ytdlp-pot-provider-{want_ver}"
            zf.extractall(tmp)
            
        inner = os.path.join(tmp, root)
        if not os.path.isfile(os.path.join(inner, "server", "package.json")):
            raise RuntimeError("내려받은 소스에 server/ 디렉터리가 존재하지 않습니다.")
            
        os.makedirs(dest_dir, exist_ok=True)
        shutil.copytree(inner, dest_dir, dirs_exist_ok=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

def _run_and_stream_log(cmd, cwd, log_full_func, env=None):
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=_NO_WINDOW,
            env=env
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
            log_full_func(f"[!] subprocess Popen error: {e}")
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
            "[~] 서버 빌드는 존재하나 Node 런타임이 없거나 요구 버전 미달 — "
            "런타임 재구성을 진행합니다."
        )
        if not ensure_node_runtime(log):
            return None, f"Node.js 런타임 확보 불가 (Node >= {NODE_MIN_MAJOR} 필요)"
        if node_ok():
            return os.path.dirname(os.path.dirname(js)), None
        return None, f"Node.js >= {NODE_MIN_MAJOR} 확보 실패"

    if not ensure_node_runtime(log):
        return None, "Node.js 런타임 확보 불가"
        
    curr_node = node_exe()
    if not curr_node:
        return None, "Node.js 실행 환경 식별 불가"
        
    npm_cli = None
    node_base_dir = os.path.dirname(curr_node)
    for root, dirs, files in os.walk(node_base_dir):
        if "npm-cli.js" in files:
            npm_cli = os.path.join(root, "npm-cli.js")
            break
            
    npm_cmd = [curr_node, npm_cli] if npm_cli else [shutil.which("npm") or "npm"]
    
    try:
        if os.path.isdir(server_home()) and os.path.isfile(os.path.join(server_home(), "server", "package.json")):
            log("[~] 기존 bgutil 서버 소스를 감지하여 빌드 단계를 수행합니다.")
        else:
            log(f"[~] bgutil 서버 소스 자동 다운로드 시작 (버전: v{want_ver})")
            download_and_install_source(want_ver, log)
            
        server_dir = os.path.join(server_home(), "server")
        log("[~] npm 의존성 패키지 설치 진행 중... (최초 1회 수 분 소요)")
        
        env = os.environ.copy()
        node_dir = os.path.dirname(os.path.abspath(curr_node))
        env["PATH"] = node_dir + os.pathsep + env.get("PATH", "")
        
        cmd_install = npm_cmd + ["ci", "--no-audit", "--no-fund"]
        ret = _run_and_stream_log(cmd_install, server_dir, log_full, env=env)
        if ret != 0:
            return None, f"npm 의존성 패키지 설치 실패 (exit code {ret})"
            
        log("[~] TypeScript 서버 트랜스파일링 컴파일(tsc) 진행 중...")
        local_tsc = os.path.join(server_dir, "node_modules", "typescript", "bin", "tsc")
        if os.path.isfile(local_tsc):
            cmd_build = [curr_node, local_tsc]
        else:
            cmd_build = [curr_node, npm_cli, "exec", "tsc"] if npm_cli else ["npx", "tsc"]
            
        ret = _run_and_stream_log(cmd_build, server_dir, log_full, env=env)
        if ret != 0:
            return None, f"tsc 빌드 컴파일 실패 (exit code {ret})"
            
        if built_server_js() is None:
            return None, "컴파일 성공 후에도 server/build/main.js 파일 부재"
            
        return server_dir, None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"

def download_and_hot_reload_plugin(log_func, want_ver=_FALLBACK_PLUGIN_VER):
    """PyPI의 bgutil-ytdlp-pot-provider 휠 패키지를 격리 경로에 직접 내려받아 무중단 핫 리로드한다."""
    log_func("[~] PO Token 플러그인 런타임 수급 중...")
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
        _download_with_progress(whl_url, tmp_whl, log_func, "PO Token 플러그인 수신 중")
        log_func("[~] 플러그인 추출 및 캐시 정렬 중...")
        
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
                
        log_func("[v] PO Token 플러그인 런타임 핫 리로드 적용 완료.")
        return True
    except Exception as e:
        log_func(f"[!] 플러그인 무중단 수급 중 실패: {e}", False, True)
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
                f"[!] PO Token 서버 자동 구성 실패: {type(e).__name__}: {e}",
            )

    def _note(self, msg, is_status=False, is_error=False):
        self.line.emit(msg, is_status, is_error)

    def _dbg(self, msg):
        """F12 verbose 창 + 히스토리 전용 디버그 마커 — 간결 로그엔 노출 안 됨."""
        self.log_full.emit(f"[POT-DEBUG] {msg}")

    def _run(self):
        self._dbg("POTProviderWorker 시작")
        # [ffmpeg 자동 수급] 리먹싱/병합용 — 시스템 설치 우선, 없으면 GitHub 바이너리.
        # PO 서버와 무관한 실패여도 기동 시퀀스는 계속 진행한다.
        try:
            import components
            self._dbg("ffmpeg 자동 수급 단계 진입")
            ff_err = components.ensure_ffmpeg(self._note)
            if ff_err:
                self._note(
                    f"[!] ffmpeg 자동 수급 실패 — 병합/리먹싱 기능 제한: {ff_err}",
                    False,
                    True,
                )
                self._dbg(f"ffmpeg 수급 실패: {ff_err}")
            else:
                self._dbg("ffmpeg 수급 완료")
        except Exception as ff_ex:
            self._note(f"[!] ffmpeg 수급 모듈 예외: {ff_ex}", False, True)
            self._dbg(f"ffmpeg 수급 모듈 예외: {type(ff_ex).__name__}: {ff_ex}")

        if not plugin_installed():
            self._note("[~] PO Token 플러그인 부재 감지 -> 최신 플러그인을 다운로드합니다.")
            self._dbg("플러그인 부재 → 다운로드 시도")
            ok = download_and_hot_reload_plugin(self._note, _FALLBACK_PLUGIN_VER)
            self._dbg(f"플러그인 다운로드 결과: {'OK' if ok else 'FAIL'}")
        else:
            self._dbg("플러그인 이미 설치됨 — 다운로드 생략")

        self._dbg(f"서버 probe 시도 → {DEFAULT_HOST}:{DEFAULT_PORT}")
        state, detail = probe_server()
        self._dbg(f"probe 결과: state={state!r} detail={detail[:200]!r}")
        if state == "ok":
            self.outcome = (
                "ok",
                f"[v] PO Token 서버 연결됨 ({DEFAULT_HOST}:{DEFAULT_PORT})",
            )
            self._dbg("ok 분기 — 워커 종료")
            return

        if state == "conflict":
            self.outcome = (
                "err",
                f"[!] 포트 {DEFAULT_PORT} 사용 중 — 해당 프로그램 종료 후 재실행해 주세요",
            )
            self._dbg("conflict 분기 — 포트 점유 감지")
            return

        self._dbg("기존 빌드 산출물 스폰 시도")
        if _spawn_existing(self.log_full.emit):
            self.outcome = (
                "ok",
                f"[v] PO Token 서버 구동됨 ({DEFAULT_HOST}:{DEFAULT_PORT})",
            )
            self._dbg("기존 빌드 스폰 성공")
            return
        self._dbg("기존 빌드 스폰 실패 — 신규 빌드 진행")

        ver = plugin_version() or _FALLBACK_PLUGIN_VER
        self._dbg(f"플러그인 버전 결정: {ver}")
        self._note("[~] PO Token 서버 환경 구성 및 빌드를 시작합니다.")
        _, err = ensure_node_server(self._note, self.log_full.emit, ver)
        self._dbg(f"ensure_node_server 종료: err={err!r}")

        if err is None and _spawn_existing(self.log_full.emit):
            self.outcome = (
                "ok",
                f"[v] PO Token 서버 구동됨 ({DEFAULT_HOST}:{DEFAULT_PORT})",
            )
            self._dbg("신규 빌드 후 스폰 성공")
            return

        self.outcome = (
            "err",
            "[!] PO Token 서버 기동 실패 — 연령제한 영상 다운로드 불가",
        )
        self._dbg("최종 실패 — 원인 tail 추출 단계")
        # [가시화] err 부재(스폰 실패) 케이스에서조차 원인이 화면에 안 떴던 문제 수리 —
        # 빌드 실패 사유와 서버 stdout/stderr(bgutil_server.log) 꼬리를 함께 노출.
        reasons = [l for l in (err or "").splitlines()[-4:] if l.strip()]
        tail = read_server_log_tail(6)
        reasons.extend(l.strip() for l in tail.splitlines() if l.strip())
        if reasons:
            self._note("[~] 실패 원인 (마지막 기록):")
            for l in reasons:
                self._note(f"      {l}")
