"""Node.js 런타임 수급 전용 모듈 (SSOT: writable_base()/node 단일 경로).

- node_exe / node_major_version / npm_exe : node 실행 파일 탐색
- node_ok / ensure_node_runtime : bgutil 요구 버전 충족 검증·자동 수급
- bundled_npm_ok : 포터블 npm 무결성 검사

[SSOT 원칙 v3.10.0]
- 오직 writable_base()/node/ 단일 경로만 읽기/쓰기
- 시스템 PATH / frozen 번들(_MEIPASS, _internal) / bundle_root 탐색 완전 제거
- 수급은 ProvisioningManager(bridge) 위임 — 이 모듈은 경로 판정만 담당
- 앱 전용 경로에 없으면 정직하게 None 반환 (FAIL FAST, silent fallback 없음)

서버 기동/빌드/소스 수급은 pot_server.py가 담당.
"""
import json
import os
import platform
import re
import subprocess
import urllib.request

import chzzktube.core.config as config
from chzzktube.core.raw_log import log_f12_cli
from chzzktube.infra.paths import get_writable_base


# ── 상수 (node_provider 전용) ──────────────────────────────────────
NODE_MIN_MAJOR = 22  # bgutil 서버의 Node 요구사항 (require(esm) 기본 지원선)
_NODE_FALLBACK_VER = "v22.23.2"  # nodejs.org index 조회 실패 시 폴백 (v22 LTS)
# [HAL 이관] _NO_WINDOW는 하위 호환 별칭 — 실체는 platform.spawn_kwargs().
# pot_provider가 `from node_provider import _NO_WINDOW`로 재수출하므로 유지.
_NO_WINDOW = 0
_node_ver_cache: dict = {}


def node_major_version(node_path, timeout=10):
    """node --version 출력에서 major 버전 추출 (판별 실패 시 None, 결과 캐시)."""
    if not node_path:
        return None
    if node_path in _node_ver_cache:
        return _node_ver_cache[node_path]
    major = None
    try:
        from chzzktube.infra.platform import spawn_kwargs

        out = subprocess.run(
            [node_path, "--version"],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=timeout, **spawn_kwargs(),
        )
        version_out = (out.stdout or "").strip()
        log_f12_cli(f"{node_path} --version", version_out)
        m = re.match(r"v?(\d+)", version_out)
        if m:
            major = int(m.group(1))
    except Exception:
        major = None
    _node_ver_cache[node_path] = major
    return major


def latest_lts_node_url(major=NODE_MIN_MAJOR):
    """nodejs.org dist index에서 지정 major의 최신 플랫뷸 URL (조회 실패 시 폴백).

    [호환 유지] ProvisioningManager._fetch_from_nodejs가 사용.
    """
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
    """플랫폼별 Node.js 배포 URL 생성 (Windows: zip, macOS: tar.gz).

    [호환 유지] ProvisioningManager._fetch_from_nodejs에서 재사용.
    """
    from chzzktube.infra.platform import is_macos, is_windows

    if is_windows():
        return f"https://nodejs.org/dist/{ver}/node-{ver}-win-x64.zip"
    if is_macos():
        arch = "arm64" if platform.machine() == "arm64" else "x64"
        return f"https://nodejs.org/dist/{ver}/node-{ver}-darwin-{arch}.tar.gz"
    arch = "arm64" if platform.machine() == "arm64" else "x64"
    return f"https://nodejs.org/dist/{ver}/node-{ver}-linux-{arch}.tar.gz"


# ── Node.js 실행 파일 탐색 (SSOT: writable_base()/node 단일 경로) ──
def npm_exe():
    """현재 사용 중인 node 런타임과 동일한 디렉터리의 npm 스크립트 경로."""
    node = node_exe()
    if not node:
        return None
    base = os.path.dirname(node)
    from chzzktube.infra.platform import is_windows as _is_win

    name = "npm.cmd" if _is_win() else "npm"
    cand = os.path.join(base, name)
    return cand if os.path.isfile(cand) else None


def node_ok():
    """현재 탐색된 node가 bgutil 요구 버전(Node >= 22)을 충족하는지."""
    return (node_major_version(node_exe()) or 0) >= NODE_MIN_MAJOR


def node_exe():
    """PO Token 서버 기동용 node 탐색 — SSOT 단일 경로 (v3.8.2).

    [SSOT 원칙] 오직 writable_base()/node/ 하위만 탐색.
    - frozen 번들(_MEIPASS, _internal), bundle_root, 시스템 PATH 완전 제거
    - 실행 비트 보장(macOS) + 요구 버전 필터
    - 후보 없으면 None → ProvisioningManager 수급 트리거
    """
    from chzzktube.infra.platform import exe_suffix, is_windows as _np_is_win

    _exe_suffix = exe_suffix()

    cands = []
    local_node_dir = os.path.join(get_writable_base(), "node")
    if os.path.isdir(local_node_dir):
        exe_name = f"node{_exe_suffix}"
        for root, dirs, files in os.walk(local_node_dir):
            if exe_name in files:
                cands.append(os.path.join(root, exe_name))

    # [macOS] tar.gz 추출 시 실행 비트 누락 방지
    if not _np_is_win():
        for c in cands:
            try:
                mode = os.stat(c).st_mode
                if not (mode & 0o111):
                    os.chmod(c, mode | 0o755)
            except Exception:
                pass

    majors = [(c, node_major_version(c)) for c in cands]
    ok = [c for c, m in majors if m is not None and m >= NODE_MIN_MAJOR]
    return ok[0] if ok else (cands[0] if cands else None)


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
    """bgutil 서버 요구(Node >= 22) 충족 — ProvisioningManager 위임 (v3.8.2).

    [SSOT] 수급은 ProvisioningManager → bridge → ProvisioningManager로 위임.
    이 모듈은 판정(node_ok/bundled_npm_ok)만 담당.

    Returns:
        True: node 요구 버전 충족 + npm 무결
        False: 수급 실패 또는 수급 후에도 요구 미충족
    """
    # 1. 현재 상태 확인 (SSOT: writable_base()/node만)
    cur = node_exe()
    cur_major = node_major_version(cur) if cur else None
    if cur_major is not None and cur_major >= NODE_MIN_MAJOR and bundled_npm_ok(cur):
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

    # 2. ProvisioningManager 위임 (동기 브리지)
    try:
        from chzzktube.infra.provisioning.bridge import provision_component_sync

        def _bridge_log(evt):
            if isinstance(evt, str):
                log_func(evt)
            else:
                msg = getattr(evt, "msg", str(evt))
                if getattr(evt, "is_error", False):
                    log_func(msg, False, True)
                else:
                    log_func(msg)

        result = provision_component_sync("node", log_func=_bridge_log, force=True)
        if result is None or not result.success:
            log_func(f"Node.js provisioning failed: {result.error if result else 'unavailable'}", False, True)
            return False
    except Exception as e:
        log_func(f"Node.js provisioning failed: {e}", False, True)
        return False

    # 3. 재검증 (수급 후)
    _node_ver_cache.clear()
    new_node = node_exe()
    new_major = node_major_version(new_node) if new_node else None
    if new_major is not None and new_major >= NODE_MIN_MAJOR and bundled_npm_ok(new_node):
        log_func(f"portable Node.js v{new_major} ready.")
        _prune_outdated_node_dirs()
        return True
    log_func(
        f"Node.js still below requirement (>= {NODE_MIN_MAJOR}) after configure",
        False, True,
    )
    return False


def _prune_outdated_node_dirs():
    """오래된 node 버전 디렉토리 정리 (SSOT: writable_base()/node만 대상)."""
    node_dir = os.path.join(get_writable_base(), "node")
    if not os.path.isdir(node_dir):
        return
    import shutil as _shutil

    # 최신 node 실행파일 위치 기준으로 상위 디렉토리 유지
    current = node_exe()
    if not current:
        return
    keep_root = os.path.dirname(current)
    for entry in os.listdir(node_dir):
        full = os.path.join(node_dir, entry)
        if not os.path.isdir(full):
            continue
        # 유지 대상이면 스킵
        try:
            if os.path.samefile(full, keep_root) or keep_root.startswith(full + os.sep):
                continue
        except Exception:
            continue
        # npm/node_modules가 포함된 폴더만 대상 (안전장치)
        if any(f.startswith("node") for f in os.listdir(full)[:5]):
            try:
                _shutil.rmtree(full, ignore_errors=True)
            except Exception:
                pass