##### updater.py - pip component (yt-dlp / streamlink) version check and update helper
"""PyPI metadata query for latest versions, optional pip upgrade on demand.
*  Version check: PyPI JSON API (lightweight, no pip needed)
*  Upgrade:
    - Stable channel: python -m pip install -U <pkg>
    - Nightly channel: python -m pip install -U yt-dlp-nightly (yt-dlp only)
*  frozen(PyInstaller) builds — pip이 없으므로 직접 다운로드:
    - yt-dlp: PyPI/GitHub release에서 yt-dlp.exe 다운로드 후 교체
    - streamlink: PyPI에서 whl 다운로드 후 importlib로 설치
    - 업데이트 실패 시 기존 버전 유지, 다음 실행 시 재시도
*  네트워크 의존은 이 앱에서 본질적이다 (웹 미디어 추출기). """
import concurrent.futures
import importlib.metadata as im
import json
import os
import shutil
import subprocess
import sys
import tempfile
import socket
import urllib.request

# (log_label, pypi_name, pypi_nightly) — log_label is shown in the DEPS PLATFORM column
# pypi_nightly: Nightly 채널 사용 시 설치할 PyPI 패키지명 (None이면 Stable only)
# [전환] bgutil-ytdlp-pot-provider 제외: 플러그인(pip)에서 독립 Node 서버로
# 이동 — 버전 관리 주체는 pot_provider(latest_server_ver)가 담당.
PACKAGES = [("ytdlp", "yt-dlp", "yt-dlp-nightly"), ("streamlink", "streamlink", None)]
# [주의] socket.setdefaulttimeout() 절대 사용 금지 — 프로세스 전체의 소켓 기본
# 타임아웃을 오염시켜 yt-dlp 미디어 스트림 재시도 루프(0.0% 스톨)를 유발.
# DNS hang 방어는 아래 latest_version의 ThreadPoolExecutor + urlopen(timeout)으로 충분.

_PYPI_API = "https://pypi.org/pypi/{pkg}/json"
_NIGHTLY_API = "https://github.com/yt-dlp/yt-dlp-nightly-builds/releases/latest/download/yt-dlp{_ext}"

def installed_version(pypi_name):
    """Installed version string, or None if not installed / failure."""
    try:
        return im.version(pypi_name)
    except Exception:
        return None

def latest_version(pypi_name, timeout=1.5):
    """Latest stable version from PyPI, or None on failure.

    [v3.1.0 변경] 타임아웃 2초→1.5초로 단축. DEPS 로그 표시 시간을
    줄이기 위해. PyPI JSON API는 충분히 빠르므로 1.5초면 충분.
    ThreadPoolExecutor는 DNS 레벨까지 카운트다운하므로 urlopen timeout
    보다 0.5초만 버퍼로 부여.

    [DNS hang defence] socket.setdefaulttimeout does not cover getaddrinfo;
    ThreadPoolExecutor + future.result cuts at DNS level too.
    """
    def _fetch():
        with urllib.request.urlopen(_PYPI_API.format(pkg=pypi_name), timeout=timeout) as resp:
            return json.load(resp)
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(_fetch)
            data = fut.result(timeout=timeout + 0.5)
            return (data.get("info") or {}).get("version")
    except Exception:
        return None

def _ver_tuple(version):
    """'2026.8.19' -> (2026, 8, 19) comparable tuple (non-digit chars dropped)."""
    parts = []
    for p in str(version).split("."):
        digits = "".join(ch for ch in p if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)

def is_outdated(current, latest):
    """True if latest > current (numeric tuple compare avoids string pitfalls)."""
    try:
        return _ver_tuple(latest) > _ver_tuple(current)
    except Exception:
        return False

def outdated_packages(channel="stable"):
    """List of (label, pypi_name, cur, latest) needing update or not installed.
    channel: stable / nightly (yt-dlp-nightly / GitHub builds).

    [downgrade support] stable channel with yt-dlp-nightly installed (user
    switched Nightly->Stable): force stale target=stable -- nightly version
    string compares higher so plain version check would be never-stale.
    """
    stale = []
    for label, pypi_name, pypi_nightly in PACKAGES:
        if channel == "nightly" and pypi_nightly:
            cur = installed_version(pypi_nightly) or installed_version(pypi_name)
            latest = latest_version(pypi_nightly)
            if not cur:
                stale.append((label, pypi_name, "not installed", latest or "unknown"))
            elif latest and is_outdated(cur, latest):
                stale.append((label, pypi_name, cur, latest))
            continue
        # stable channel: leftover nightly -> downgrade target
        if pypi_nightly and installed_version(pypi_nightly):
            stale.append((label, pypi_name, str(installed_version(pypi_nightly)) + " (nightly)", "stable"))
            continue
        cur = installed_version(pypi_name)
        latest = latest_version(pypi_name)
        if not cur:
            stale.append((label, pypi_name, "not installed", latest or "unknown"))
        elif latest and is_outdated(cur, latest):
            stale.append((label, pypi_name, cur, latest))
    return stale


def check_deps(log_func=None):
    """모든 의존성 체크 결과 리스트 반환.
    각 요소: (label, status, version_or_path)
    status: 표준 status (OK / FAIL 등) — `format_log_line`의 표준 사용.
    log_func(msg): POT readiness 판정 근거를 raw 스택으로 반환 (단일 호출).
    """
    import os
    import shutil
    results = []

    # 1. PyPI 패키지 (yt-dlp, streamlink) — nightly 채널 설치물 인지
    #    yt-dlp-nightly 는 dist 명이 달라 im.version("yt-dlp") 가 실패하므로
    #    nightly 설치물로 폴백 표기 (정상 설치 판정 유지)
    for label, pypi_name, pypi_nightly in PACKAGES:
        ver = installed_version(pypi_name)
        if not ver and pypi_nightly:
            nver = installed_version(pypi_nightly)
            if nver:
                ver = f"{nver} (nightly)"
        results.append((label, "OK" if ver else "FAIL", ver or "not installed"))

    # 2. 외부 실행 파일 (ffmpeg, node) — msg에는 버전/경로 같은 실질 정보만
    for label in ("ffmpeg", "node"):
        path = shutil.which(label)
        if not path and label == "node":
            # [포터블 폴백] 시스템 PATH 밖의 로컬 포터블 node (writable_base/node)도
            # DEPS 후보 — 없을 때만 'not found'.
            try:
                import pot_provider
                path = pot_provider.node_exe()
            except Exception:
                path = None
        if path:
            if label == "node":
                try:
                    import pot_provider
                    maj = pot_provider.node_major_version(path)
                except Exception:
                    maj = None
                msg = f"v{maj}" if maj else os.path.basename(path)
            elif label == "ffmpeg":
                msg = _ffmpeg_version(path) or os.path.basename(path)
            results.append((label, "OK", msg))
        else:
            # [v3.1.0 정책] 표준 status 사용. msg는 명시적 문자열.
            results.append((label, "FAIL", "not found"))

    # 3. PO token 서버 — [Lazy 2층 분리] liveness가 아니라 readiness.
    # 바이너리+빌드 산출물의 디스크 준비만 판정 (RAM 0MB·포트 미점유).
    # Popen은 분석 게이트(_ensure_pot_for_info)까지 지연. FAIL 오경보 금지:
    # 미기동 정상 상태는 SKIP standby, 산출물 미비는 SKIP + 사유.
    # [단일 호출] log_func 콜백을 내부 pot_readiness에 직접 전달 — 판정+로그
    # 1회로 해결 (별도 _pot_readiness 호출 시 standby 2중 출력 결함).
    try:
        from po_client import server_ping
        from pot_server import pot_readiness
        if server_ping():
            results.append(("pot", "OK", "running"))
        else:
            ready, reason = pot_readiness(log_func=log_func)
            if ready:
                results.append(("pot", "SKIP", "standby"))
            else:
                results.append(("pot", "SKIP", reason))
    except Exception:
        results.append(("pot", "SKIP", "unknown"))

    return results

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _cli_base(label):
    """라벨 → 실제 CLI 명령 배열 (없으면 None). F12 상세 로그용 원문 실행.

    importlib.metadata/shutil.which 로 대체하지 않는 이유: '터미널에서 직접
    쳤을 때 보이는 원문 출력'을 있는 그대로 남기는 것이 목적이므로, 판별이
    아닌 실제 실행이 필요하다.
    """
    if label == "ytdlp":
        if getattr(sys, "frozen", False):
            p = shutil.which("yt-dlp") or shutil.which("yt-dlp.exe")
            return [p] if p else None
        # dev: 앱이 실제로 쓰는 venv 파이썬으로 실행 (PATH 무관)
        return [sys.executable, "-m", "yt_dlp"]
    if label == "streamlink":
        if getattr(sys, "frozen", False):
            p = shutil.which("streamlink")
            return [p] if p else None
        return [sys.executable, "-m", "streamlink"]
    if label == "ffmpeg":
        p = shutil.which("ffmpeg")
        if not p:
            try:
                from components import ffmpeg_exe
                p = ffmpeg_exe()
            except Exception:
                p = None
        return [p] if p else None
    if label == "node":
        try:
            import pot_provider
            p = pot_provider.node_exe()
        except Exception:
            p = None
        p = p or shutil.which("node")
        return [p] if p else None
    if label == "npm":
        try:
            import pot_provider
            p = pot_provider.npm_exe()
        except Exception:
            p = None
        p = p or shutil.which("npm")
        return [p] if p else None
    return None


def _cli_env(label):
    """npm 시스 스크립트가 'env node'로 node를 찾도록 PATH 보강 (npm만)."""
    if label != "npm":
        return None
    try:
        import pot_provider
        node = pot_provider.node_exe()
    except Exception:
        node = None
    if not node:
        return None
    env = os.environ.copy()
    ndir = os.path.dirname(node)
    env["PATH"] = ndir + os.pathsep + env.get("PATH", "")
    return env


def cli_raw(label, *args, timeout=15, max_lines=0, max_width=160):
    """실제 CLI를 실행해 '터미널에서 친 것과 동일한 원문 출력'을 반환.

    반환: (cmdline, output) — 도구 없으면 (None, None), 실행 예외면
    (cmdline, "[Type] msg"). 출력은 stdout+stderr 합본 원문.
    호출부(F12 상세 로그)가 '$ <cmd>' + 원문 라인을 그대로 적재한다.
    max_lines>0 → 앞 N줄만 + '… (M lines truncated)' 꼬리.
    over-long 단일 줄은 max_width로 절단 (ffmpeg configuration: 대책).
    """
    cmd = _cli_base(label)
    if not cmd:
        return None, None
    full_cmd = cmd + list(args)
    env = _cli_env(label)
    try:
        proc = subprocess.run(
            full_cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=env,
            creationflags=_NO_WINDOW if os.name == "nt" else 0,
        )
    except Exception as e:
        return " ".join(full_cmd), f"[{type(e).__name__}] {e}"
    out = ((proc.stdout or "") + (proc.stderr or "")).strip()
    if not out:
        return " ".join(full_cmd), None
    lines = out.splitlines()
    # [F12 가독성] 장문 단일 줄 절단 (ffmpeg 'configuration:' 500자 대책)
    if max_width and max_width > 0:
        lines = [l if len(l) <= max_width else l[:max_width] + "…" for l in lines]
    if max_lines and max_lines > 0 and len(lines) > max_lines:
        kept = lines[:max_lines]
        kept.append(f"… ({len(lines) - max_lines} lines truncated)")
        return " ".join(full_cmd), "\n".join(kept)
    return " ".join(full_cmd), "\n".join(lines)


def _ffmpeg_version(path, timeout=3):
    """`ffmpeg -version` 첫 줄에서 버전 추출 (예: '7.1.1'). 실패 시 None."""
    try:
        import re
        out = subprocess.run(
            [path, "-version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=_NO_WINDOW if os.name == "nt" else 0,
        )
        line = (out.stdout or out.stderr or "").splitlines()[0]
        m = re.search(r"version\s+([0-9][0-9.]*)", line)
        return m.group(1) if m else None
    except Exception:
        return None

def _exe_suffix():
    return ".exe" if sys.platform == "win32" else ""

def _download_to(url, dest, timeout=120):
    """Download url to dest file. Returns True on success."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp, open(dest, "wb") as f:
            shutil.copyfileobj(resp, f)
        return True
    except Exception:
        return False

def _get_pypi_whl_url(pypi_name):
    """PyPI에서 최신 whl 다운로드 URL을 조회. 실패 시 None."""
    try:
        with urllib.request.urlopen(_PYPI_API.format(pkg=pypi_name), timeout=10) as resp:
            data = json.load(resp)
        urls = data.get("urls") or []
        # manylinux/macosx/windows whl 우선순호
        preferred = [f for f in urls if "whl" in f.get("filename", "")]
        if preferred:
            return preferred[0].get("url")
    except Exception:
        pass
    return None

def _extract_from_whl(whl_path, dest_dir):
    """whl 파일(zip)을 dest_dir에 압축 해제."""
    import zipfile
    try:
        with zipfile.ZipFile(whl_path) as zf:
            zf.extractall(dest_dir)
        return True
    except Exception:
        return False

def _frozen_upgrade_ytdlp(channel="stable"):
    """PyInstaller frozen build: yt-dlp를 직접 다운로드하여 교체.
    Stable: PyPI release whl에서 yt-dlp.exe 추출.
    Nightly: GitHub nightly-builds release에서 yt-dlp.exe 다운로드.
    """
    suffix = _exe_suffix()
    try:
        import yt_dlp
        ytdlp_dir = os.path.dirname(yt_dlp.__file__)
    except Exception:
        return 1, "yt-dlp not found"
    dest = os.path.join(os.path.dirname(ytdlp_dir), f"yt-dlp{suffix}")

    if channel == "nightly":
        url = _NIGHTLY_API.format(_ext=suffix)
    else:
        url = _get_pypi_whl_url("yt-dlp")
        if not url:
            return 1, "No whl found on PyPI"
        # whl에서 yt-dlp.exe 추출
        try:
            with tempfile.TemporaryDirectory() as tmp:
                whl_path = os.path.join(tmp, "yt-dlp.whl")
                if not _download_to(url, whl_path):
                    return 1, "whl download failed"
                import zipfile
                with zipfile.ZipFile(whl_path) as zf:
                    for name in zf.namelist():
                        if name.endswith(f"yt-dlp{suffix}"):
                            with zf.open(name) as src, open(dest, "wb") as dst:
                                shutil.copyfileobj(src, dst)
                            return 0, f"updated to {channel}"
            return 1, "yt-dlp binary not found in whl"
        except Exception as e:
            return 1, f"whl extract failed: {e}"

    if _download_to(url, dest):
        return 0, f"updated to {channel}"
    return 1, "download failed"

def _frozen_upgrade_streamlink():
    """PyInstaller frozen build: streamlink를 직접 다운로드하여 교체.
    PyPI whl에서 패키지 전체를 site-packages에 압축 해제.
    """
    try:
        import streamlink
        pkg_dir = os.path.dirname(streamlink.__file__)
    except Exception:
        return 1, "streamlink not found"

    whl_url = _get_pypi_whl_url("streamlink")
    if not whl_url:
        return 1, "No whl found on PyPI"

    try:
        with tempfile.TemporaryDirectory() as tmp:
            whl_path = os.path.join(tmp, "streamlink.whl")
            if not _download_to(whl_url, whl_path):
                return 1, "whl download failed"
            if _extract_from_whl(whl_path, pkg_dir):
                return 0, "updated to latest"
        return 1, "whl extract failed"
    except Exception as e:
        return 1, f"streamlink update failed: {e}"

def upgrade_packages(packages, channel="stable"):
    """직접 다운로드 방식으로 패키지 업데이트 (Dev/Frozen 통합).

    [v3.1.0 변경] Dev 환경에서도 pip 대신 직접 다운로드 경로 사용.
    이유: 포터블 빌드와 Dev에서 동일한 코드 경로를 타야 디버깅이 가능.
    pip install은 빌드 시에만 사용 (PyInstaller 번들 시점).

    Returns (returncode, output tail). Worker thread only.
    """
    is_frozen = getattr(sys, "frozen", False)

    # yt-dlp: Dev/Frozen 통합 - 직접 다운로드
    if "yt-dlp" in packages:
        return _frozen_upgrade_ytdlp(channel)

    # streamlink: Dev/Frozen 통합 - whl 직접 다운로드
    if "streamlink" in packages:
        return _frozen_upgrade_streamlink()
