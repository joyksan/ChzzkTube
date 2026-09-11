"""Node.js 런타임 수급 전용 모듈 (SRP: Node.js 런타임 관리만 담당).

- node_exe / node_major_version / npm_exe : node 실행 파일 탐색
- node_ok / ensure_node_runtime : bgutil 요구 버전 충족 검증·자동 수급
- bundled_npm_ok : 포터블 npm 무결성 검사

서버 기동/빌드/소스 수급은 pot_server.py가 담당.
"""
import os
import re
import sys
import json
import shutil
import zipfile
import tarfile
import platform
import subprocess
import urllib.request

import config
from log_console import emit_component


# ── 상수 (node_provider 전용) ──────────────────────────────────────
NODE_MIN_MAJOR = 22  # bgutil 서버의 Node 요구사항 (require(esm) 기본 지원선)
_NODE_FALLBACK_VER = "v22.23.2"  # nodejs.org index 조회 실패 시 폴백 (v22 LTS)
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_node_ver_cache: dict = {}


# ── 공유 헬퍼 ──────────────────────────────────────────────────────
def get_writable_base():
    """사용자 환경에서 쓰기 권한이 100% 보장되는 로컬 앱 데이터 디렉터리 반환."""
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


# ── Node.js 버전 탐색 ───────────────────────────────────────────────
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
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=timeout, **kwargs,
        )
        m = re.match(r"v?(\d+)", (out.stdout or "").strip())
        if m:
            major = int(m.group(1))
    except Exception:
        major = None
    _node_ver_cache[node_path] = major
    return major


def latest_lts_node_url(major=NODE_MIN_MAJOR):
    """nodejs.org dist index에서 지정 major의 최신 플랫뷸 URL (조회 실패 시 폴백)."""
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
        arch = "arm64" if platform.machine() == "arm64" else "x64"
        return f"https://nodejs.org/dist/{ver}/node-{ver}-darwin-{arch}.tar.gz"
    arch = "arm64" if platform.machine() == "arm64" else "x64"
    return f"https://nodejs.org/dist/{ver}/node-{ver}-linux-{arch}.tar.gz"


# ── Node.js 실행 파일 탐색 ─────────────────────────────────────────
def npm_exe():
    """현재 사용 중인 node 런타임과 동일한 디렉터리의 npm 스크립트 경로."""
    node = node_exe()
    if not node:
        return None
    base = os.path.dirname(node)
    name = "npm.cmd" if platform.system() == "Windows" else "npm"
    cand = os.path.join(base, name)
    return cand if os.path.isfile(cand) else None


def node_ok():
    """현재 탐색된 node가 bgutil 요구 버전(Node >= 22)을 충족하는지."""
    return (node_major_version(node_exe()) or 0) >= NODE_MIN_MAJOR


def node_exe():
    """PO Token 서버 기동용 node 탐색 — bgutil 요구(Node >= 22) 충족 후보만 유효.

    후보 순서: 시스템 PATH → 캐시된 포터블 node → frozen 번들.
    요구 버전을 충족하는 후보가 없으면 None → ensure_node_runtime 재구성 트리거.
    포터블 빌드 첫 실행시 다른 DEPS와 함께 다운로드됨.
    """
    _exe_suffix = ".exe" if os.name == "nt" else ""

    # 1. 시스템 Node.js 확인 (번들이 아닌 외부 참조)
    system_node = shutil.which("node") or shutil.which("node.exe")
    if system_node:
        maj = node_major_version(system_node)
        if maj is not None and maj >= NODE_MIN_MAJOR:
            return system_node

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


def bundled_npm_ok(node_path):
    """번들 Node dir의 npm 무결성 — validate-engines가 require하는 package.json.

    [크로스 플랫폼 레이아웃] 검사 경로는 플랫폼별 릴리스 구조를 모두 커버:
    - Windows zip :  <base>/node_modules/npm/package.json  (node.exe 옆)
    - Unix tarball : <base>/../lib/node_modules/npm/package.json  (macOS·Linux)
    """
    if not node_path:
        return False
    base = os.path.dirname(node_path)
    candidates = (
        os.path.join(base, "node_modules", "npm", "package.json"),
        os.path.join(base, "..", "lib", "node_modules", "npm", "package.json"),
    )
    return any(os.path.isfile(os.path.normpath(p)) for p in candidates)


def ensure_node_runtime(log_func):
    """bgutil 서버 요구(Node >= 22) 충족을 위한 Node.js 런타임 자동 수급/재구성.

    [수정 이력]
    - 구버전은 v20.18.0을 받아 bgutil의 require(esm) 요구를 충족하지
      못해 서버가 ERR_REQUIRE_ESM으로 크래시했다 (PO Token 기동 실패 근본 원인).
    - 자가 치유: node.exe는 살아있어도 번들 npm이 깨진 경우(부분 추출/AV 격리)
      재설치로 수리 — bundled_npm_ok 참조.
    - 번들이 아닌 외부 라이브러리 참조 전환:
      시스템 Node.js 22+ 우선 사용 → 없으면 로컬 포터블 → 마지막으로 다운로드.
      포터블 빌드 첫 실행시 다른 DEPS와 함께 다운로드됨.
    """
    from pot_server import _download_with_progress, _prune_outdated_node_dirs

    # 1. 시스템 Node.js 확인 (번들이 아닌 외부 참조)
    system_node = shutil.which("node")
    if system_node:
        system_major = node_major_version(system_node)
        if system_major is not None and system_major >= NODE_MIN_MAJOR:
            if shutil.which("npm"):
                log_func(f"using system Node.js v{system_major} ({system_node})")
                return True

    # 2. 로컬 포터블 Node.js 확인
    cur = node_exe()
    cur_major = node_major_version(cur) if cur else None
    if cur_major is not None and cur_major >= NODE_MIN_MAJOR and (
        bundled_npm_ok(cur) or shutil.which("npm")
    ):
        return True
    if cur_major is not None and cur_major >= NODE_MIN_MAJOR and not bundled_npm_ok(cur):
        log_func("[~] node ok but bundled npm broken — reinstalling runtime.")
    elif cur_major is not None:
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
                except Exception:
                    pass
                shutil.rmtree(node_dir, ignore_errors=True)
            os.makedirs(node_dir, exist_ok=True)
            try:
                result = subprocess.run(
                    ["tar", "-xzf", archive_dest, "-C", node_dir],
                    capture_output=True, text=True, timeout=120,
                )
                if result.returncode != 0:
                    raise RuntimeError(f"tar failed: {result.stderr}")
            except Exception:
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
            if os.path.exists(node_dir):
                try:
                    shutil.rmtree(node_dir, ignore_errors=True)
                except Exception:
                    pass
            os.makedirs(node_dir, exist_ok=True)
            with zipfile.ZipFile(archive_dest, "r") as z:
                z.extractall(node_dir)
        _node_ver_cache.clear()
        new_node = node_exe()
        new_major = node_major_version(new_node) if new_node else None
        if new_major is not None and new_major >= NODE_MIN_MAJOR and bundled_npm_ok(new_node):
            log_func(f"portable Node.js v{new_major} ready.")
            _prune_outdated_node_dirs(node_dir)
            return True
        log_func(
            f"Node.js still below requirement (>= {NODE_MIN_MAJOR}) after configure",
            False, True,
        )
        return False
    except Exception as e:
        log_func(f"Node.js auto-setup failed: {e}", False, True)
        return False