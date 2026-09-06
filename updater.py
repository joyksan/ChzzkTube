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

def latest_version(pypi_name, timeout=2):
    """Latest stable version from PyPI, or None on failure.

    [DNS hang defence] socket.setdefaulttimeout does not cover getaddrinfo;
    ThreadPoolExecutor + future.result cuts at DNS level too.
    """
    def _fetch():
        with urllib.request.urlopen(_PYPI_API.format(pkg=pypi_name), timeout=timeout) as resp:
            return json.load(resp)
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(_fetch)
            data = fut.result(timeout=timeout + 1)
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
    """List of (log_label, pypi_name, cur_ver, latest_ver) needing update or not installed.
    channel: 'stable' (PyPI release) or 'nightly' (yt-dlp-nightly / GitHub builds).
    """
    stale = []
    for label, pypi_name, pypi_nightly in PACKAGES:
        cur = installed_version(pypi_name)
        pkg_to_check = pypi_nightly if (channel == "nightly" and pypi_nightly) else pypi_name
        latest = latest_version(pkg_to_check)
        if not cur:
            stale.append((label, pypi_name, "not installed", latest or "?"))
        elif latest and is_outdated(cur, latest):
            stale.append((label, pypi_name, cur, latest))
    return stale

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

def _frozen_upgrade_ytdlp(channel="stable"):
    """PyInstaller frozen build: yt-dlp를 직접 다운로드하여 교체.
    Stable: PyPI release whl에서 yt-dlp.exe 추출.
    Nightly: GitHub nightly-builds release에서 yt-dlp.exe 다운로드.
    """
    suffix = _exe_suffix()
    # 현재 yt-dlp 위치 파싱
    try:
        import yt_dlp
        ytdlp_dir = os.path.dirname(yt_dlp.__file__)
    except Exception:
        return 1, "yt-dlp not found"
    dest = os.path.join(os.path.dirname(ytdlp_dir), f"yt-dlp{suffix}")

    if channel == "nightly":
        url = _NIGHTLY_API.format(_ext=suffix)
    else:
        # PyPI에서 최신 릴리즈 whl URL 획득
        try:
            with urllib.request.urlopen(_PYPI_API.format(pkg="yt-dlp"), timeout=10) as resp:
                data = json.load(resp)
            urls = (data.get("urls") or [])
            whl_url = None
            for u in urls:
                if u.get("filename", "").endswith(".whl"):
                    whl_url = u.get("url")
                    break
            if not whl_url:
                return 1, "No whl found on PyPI"
        except Exception as e:
            return 1, f"PyPI query failed: {e}"
        # whl 다운로드 후 zip으로 압축해제
        try:
            with tempfile.TemporaryDirectory() as tmp:
                whl_path = os.path.join(tmp, "yt-dlp.whl")
                if not _download_to(whl_url, whl_path):
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

def upgrade_packages(packages, channel="stable"):
    """Run pip upgrade (dev) or direct download (frozen).
    Returns (returncode, output tail). Worker thread only.
    """
    is_frozen = getattr(sys, "frozen", False)

    # yt-dlp frozen 처리
    if is_frozen and "yt-dlp" in packages:
        return _frozen_upgrade_ytdlp(channel)

    if is_frozen:
        # streamlink 등 나머지: pip 없음 → 다운로드 시도
        return 1, "Portable build: direct download not implemented for this package"

    # Dev 환경: pip 사용
    cmd = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--upgrade",
        "--no-input",
        "--disable-pip-version-check",
    ] + list(packages)
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
        )
        tail = "\n".join((proc.stdout or "").strip().splitlines()[-8:])
        if proc.returncode != 0 and (proc.stderr or "").strip():
            tail += "\n" + "\n".join(proc.stderr.strip().splitlines()[-3:])
        return proc.returncode, tail
    except Exception as e:
        return 1, str(e)
