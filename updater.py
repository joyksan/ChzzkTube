##### updater.py - pip component (yt-dlp / streamlink) version check and update helper
"""PyPI metadata query for latest versions, optional pip upgrade on demand.
*  Version check: PyPI JSON API (lightweight, no pip needed)
*  Upgrade: python -m pip install -U <pkg> subprocess — must run in a worker thread (tens of seconds blocking)
*  frozen(PyInstaller) builds have no pip, so upgrades are rejected. """
import concurrent.futures
import importlib.metadata as im
import json
import subprocess
import sys
import socket
import urllib.request

# (log_label, pypi_name) — log_label is shown in the DEPS PLATFORM column
# [전환] bgutil-ytdlp-pot-provider 제외: 플러그인(pip)에서 독립 Node 서버로
# 이동 — 버전 관리 주체는 pot_provider(latest_server_ver)가 담당.
PACKAGES = [("ytdlp", "yt-dlp"), ("streamlink", "streamlink")]
# [주의] socket.setdefaulttimeout() 절대 사용 금지 — 프로세스 전체의 소켓 기본
# 타임아웃을 오염시켜 yt-dlp 미디어 스트림 재시도 루프(0.0% 스톨)를 유발.
# DNS hang 방어는 아래 latest_version의 ThreadPoolExecutor + urlopen(timeout)으로 충분.

_PYPI_API = "https://pypi.org/pypi/{pkg}/json"

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

def outdated_packages():
    """List of (log_label, pypi_name, cur_ver, latest_ver) needing update or not installed."""
    stale = []
    for label, pypi_name in PACKAGES:
        cur = installed_version(pypi_name)
        latest = latest_version(pypi_name)
        if not cur:
            stale.append((label, pypi_name, "not installed", latest or "?"))
        elif latest and is_outdated(cur, latest):
            stale.append((label, pypi_name, cur, latest))
    return stale

def upgrade_packages(packages):
    """Run pip upgrade. (returncode, output tail) — worker thread only."""
    if getattr(sys, "frozen", False):
        return (
            1,
            "Portable builds do not support auto-upgrade.\nDownload a new release to update.",
        )
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
