### updater.py - 구성요소(yt-dlp / streamlink / bgutil) 버전 확인 및 업데이트 헬퍼
"""PyPI 메타데이터로 최신 버전을 조회하고, 필요 시 pip로 업그레이드한다.
*  버전 확인: PyPI JSON API (네트워크 가벼운 조회, pip 불필요)
*  업그레이드: python -m pip install -U <pkg> 서브프로세스 → 반드시 워커 스레드에서 호출할 것 (수십 초 블로킹)
*  frozen(PyInstaller) 빌드에서는 pip가 없으므로 업그레이드를 거부한다. """
import importlib.metadata as im
import json
import subprocess
import sys
import urllib.request

PACKAGES = ["yt-dlp", "streamlink", "bgutil-ytdlp-pot-provider"]
_PYPI_API = "https://pypi.org/pypi/{pkg}/json"

def installed_version(pkg):
    """설치된 버전 문자열. 미설치/실패 시 None."""
    try:
        return im.version(pkg)
    except Exception:
        return None

def latest_version(pkg, timeout=5):
    """PyPI 최신 안정 버전 문자열. 조회 실패 시 None."""
    try:
        with urllib.request.urlopen(
            _PYPI_API.format(pkg=pkg), timeout=timeout
        ) as resp:
            data = json.load(resp)
            return (data.get("info") or {}).get("version")
    except Exception:
        return None

def _ver_tuple(version):
    """'2026.8.19' → (2026, 8, 19) 비교용 튜플 (숫자 아닌 문자는 무시)."""
    parts = []
    for p in str(version).split("."):
        digits = "".join(ch for ch in p if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)

def is_outdated(current, latest):
    """최신 버전이 더 높으면 True (문자열 비교 오차 방지를 위해 수치 비교)."""
    try:
        return _ver_tuple(latest) > _ver_tuple(current)
    except Exception:
        return False

def outdated_packages():
    """업데이트가 있거나 미설치된 구성요소 목록 [(pkg, 현재, 최신)]."""
    stale = []
    for pkg in PACKAGES:
        cur, latest = installed_version(pkg), latest_version(pkg)
        # 네트워크 지연/차단 시에도 미설치 항목은 무조건 감지해야 하므로 cur가 없으면 즉시 스케줄링!
        if not cur:
            stale.append((pkg, "미설치", latest or "1.3.2"))
        elif latest and is_outdated(cur, latest):
            stale.append((pkg, cur, latest))
    return stale

def upgrade_packages(packages):
    """pip로 업그레이드 실행. (returncode, 출력 꼬리) 반환 — 워커 스레드 전용.
    frozen 빌드는 자체 실행 파일 안에 파이썬이 묶여 pip를 쓸 수 없으므로
    실패(1)를 반환한다.
    """
    if getattr(sys, "frozen", False):
        return (
            1,
            "포터블 빌드에서는 자동 업데이트를 지원하지 않습니다.\n"
            "새 배포판을 받아 교체해주세요.",
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
