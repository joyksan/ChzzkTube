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
                import chzzktube.infra.pot_provider as pot_provider
                path = pot_provider.node_exe()
            except Exception:
                path = None
        if path:
            if label == "node":
                try:
                    import chzzktube.infra.pot_provider as pot_provider
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
        from chzzktube.infra.po_client import server_ping
        from chzzktube.infra.pot_server import pot_readiness
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
                from chzzktube.infra.components import ffmpeg_exe
                p = ffmpeg_exe()
            except Exception:
                p = None
        return [p] if p else None
    if label == "node":
        try:
            import chzzktube.infra.pot_provider as pot_provider
            p = pot_provider.node_exe()
        except Exception:
            p = None
        p = p or shutil.which("node")
        return [p] if p else None
    if label == "npm":
        try:
            import chzzktube.infra.pot_provider as pot_provider
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
        import chzzktube.infra.pot_provider as pot_provider
        node = pot_provider.node_exe()
    except Exception:
        node = None
    if not node:
        return None
    env = os.environ.copy()
    ndir = os.path.dirname(node)
    env["PATH"] = ndir + os.pathsep + env.get("PATH", "")
    return env


def cli_raw(label, *args, timeout=15):
    """실제 CLI를 실행해 '터미널에서 친 것과 동일한 원문 출력'을 반환.

    반환: (cmdline, output) — 도구 없으면 (None, None), 실행 예외면
    (cmdline, "[Type] msg"). 출력은 stdout+stderr 합본 원문 전체.

    [레이어 원칙] 수집층은 절대 절단하지 않는다. 원문은 history에 전량
    기록되며, F12 적재 시점의 절취는 호출부(truncate_for_full_log)가 담당.
    수집에서 자르면 원본이 영구 소실되어 복원 불가.
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
    return " ".join(full_cmd), out


def truncate_for_full_log(out, max_lines=6, max_width=160):
    """F12 적재 시점 절취 — history는 원문 전량을 이미 기록했으므로 뷰만 자른다.

    max_lines>0 → 앞 N줄만 + '… (M lines truncated)' 꼬리.
    over-long 단일 줄은 max_width로 절단 (ffmpeg configuration: 500자 대책).
    """
    text = str(out or "")
    if not text:
        return ""
    lines = text.splitlines()
    if max_width and max_width > 0:
        lines = [l if len(l) <= max_width else l[:max_width] + "…" for l in lines]
    if max_lines and max_lines > 0 and len(lines) > max_lines:
        kept = lines[:max_lines]
        kept.append(f"… ({len(lines) - max_lines} lines truncated)")
        return "\n".join(kept)
    return "\n".join(lines)


def _ffmpeg_version(path, timeout=3):
    """`ffmpeg -version`에서 숫자 코어 버전(MAJOR.MINOR[.PATCH]) 추출. 실패 시 None.

    - 표준/홈브루: 'ffmpeg version 9.0.1' → 9.0.1
    - extra version/빌드 태그/일자(YYYMMDD) 접미는 정규식으로 절단:
      '9.0.1_1'·'7.1.1-20240815-g…' → 9.0.1 · 7.1.1
      (homebrew bottle Cellar/ffmpeg/9.0.1_1 처럼 configuration 줄에만
      extra version이 드러나는 경우도 그대로 대응)
    - 첫 줄 미매치(N-일자 빌드 등) 시 configuration 줄 폴백: '…/ffmpeg/9.0.1_1'
    """
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
        text = (out.stdout or out.stderr or "")
        # 1) 표준 첫 줄 — 숫자 코어 3단만 (extra version 접미부 미포함)
        m = re.search(r"ffmpeg version\s+(\d+(?:\.\d+){1,2})", text)
        if not m:
            # 2) configuration 줄 폴백 — --prefix=…/ffmpeg/9.0.1_1
            m = re.search(r"ffmpeg[/\\\-](\d+(?:\.\d+){1,2})(?![0-9.])", text)
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

def _extract_streamlink_whl(whl_path, site_root):
    """streamlink whl을 site-packages **루트**에 해제하고 구 dist-info를 정리한다.

    [수리 v3.4.0] 기존 _frozen_upgrade_streamlink는 whl을 pkg_dir(=streamlink/
    코드 폴더 내부)에 풀어 importlib.metadata가 읽는 streamlink-*.dist-info 가
    구버전(예: 8.5.0) 그대로 남았다 → is_outdated()가 항상 True → 매 기동마다
    'update streamlink updated' 반복 루프가 돌았다.

    올바른 해제 위치는 site-packages 루트(streamlink/ 코드 + streamlink-<ver>
    .dist-info/ 메타데이터가 나란히 놓이는 곳)다. 구 dist-info는 제거해
    importlib.metadata가 신규 버전을 단일 판독하도록 보장한다.

    반환: 성공 여부. (순수 함수 — 테스트 가능)
    """
    import zipfile
    keep_dist = None
    try:
        with zipfile.ZipFile(whl_path) as zf:
            for name in zf.namelist():
                if name.endswith(".dist-info/") and name.startswith("streamlink-"):
                    keep_dist = name.rstrip("/")
        if not _extract_from_whl(whl_path, site_root):
            return False
        if keep_dist:
            import glob
            for old in glob.glob(os.path.join(site_root, "streamlink-*.dist-info")):
                if os.path.basename(old) != keep_dist:
                    shutil.rmtree(old, ignore_errors=True)
        return True
    except Exception:
        return False


def _frozen_upgrade_streamlink():
    """PyInstaller frozen build: streamlink를 직접 다운로드하여 교체.

    PyPI whl에서 패키지 전체를 site-packages에 압축 해제 — 코드 폴더가 아닌
    site-packages **루트**에 풀어야 streamlink-<ver>.dist-info 메타데이터가
    importlib.metadata에 반영된다 (_extract_streamlink_whl 참고).
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
            if _extract_streamlink_whl(whl_path, os.path.dirname(pkg_dir)):
                import importlib
                importlib.invalidate_caches()
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
