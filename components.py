### components.py - ffmpeg runtime manager
"""ffmpeg 자동 수급/관리 전용 모듈.

*  시스템 PATH의 ffmpeg 최우선 사용, 없으면 GitHub(GyanD/codexffmpeg)
   release 바이너리를 writable_base/ffmpeg/에 전개해 PATH에 연결.
*  macOS는 Homebrew 설치 우선, 실패 시 Homebrew bottle 직접 다운로드.

[전수조사 정리 2026-09-04] 구 설계(Hitomi Downloader style 전체 구성요소
자동수급: yt-dlp 휠 / bgutil 플러그인 / pot-pack / streamlink-pack)는
main.py에 연결된 적이 없는 죽은 코드였음 — 실제 의존 흐름은
venv pip(yt-dlp / streamlink) + pot_provider(bgutil 서버 빌드) + 본 모듈.
"""
import hashlib
import json
import os
import platform
import shutil
import sys
import tempfile
import urllib.request
import zipfile

import config
from log_console import emit_component

_UA = "ChzzkTube-Components/1.0"


def components_root():
    """구성요소 전개 루트. frozen: <exe>/components, source: <repo>/components."""
    env = os.environ.get("CHZZKTUBE_COMPONENTS_DIR")
    if env:
        return env
    if getattr(sys, "frozen", False):
        return os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "components")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "components")



def _logcb(log):
    return log if callable(log) else (lambda *a, **k: None)


def _http_get(url, timeout=30):
    """HTTP GET 요청, ghcr.io는 토큰 인증 자동 처리."""
    headers = {"User-Agent": _UA}
    if "ghcr.io" in url:
        try:
            token = _ghcr_token("repository:homebrew/core/ffmpeg:pull")
            headers["Authorization"] = f"Bearer {token}"
        except Exception:
            pass
    req = urllib.request.Request(url, headers=headers)
    return urllib.request.urlopen(req, timeout=timeout)


def _ghcr_token(scope):
    """ghcr.io 익명 토큰 획득."""
    url = f"https://ghcr.io/token?scope={scope}"
    with urllib.request.urlopen(url, timeout=15) as resp:
        data = json.load(resp)
    return data.get("token")


def _download(url, dest, log, label="", is_status=False):
    """파일 다운로드(진행 로그 포함). 성공 시 dest 경로 반환.
    
    is_status=True 면 진행률 로그를 상태 줄로 표시 (이전 줄 덮어쓰기).
    """
    log(emit_component("DEPS", "RUN", "-", f"{label or os.path.basename(url)} fetching..."), is_status)
    tmp = dest + ".part"
    with _http_get(url, timeout=60) as resp, open(tmp, "wb") as f:
        total = int(resp.headers.get("Content-Length") or 0)
        done, last_mb = 0, -1
        while True:
            chunk = resp.read(1024 * 512)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            mb = done // (1024 * 1024)
            # 진행률 로그 빈도 조절: 8MB 이상 파일은 2MB마다, 미만은 완료 시에만
            if total < 8 * 1024 * 1024 or mb != last_mb and mb % 2 == 0:
                last_mb = mb
                pct = f" ({done * 100 // total}%)" if total else ""
                log(emit_component("DEPS", "RUN", "-", f"{label or 'download'} {mb} MB{pct}"), is_status)
    os.replace(tmp, dest)
    log(emit_component("DEPS", "OK", "-", f"{label or os.path.basename(dest)} done ({done / 1048576:.1f} MB)"))
    return dest


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _rmtree(p):
    shutil.rmtree(p, ignore_errors=True)


def _extract_zip(zip_path, dest_dir, log, label, promote_single_root=False):
    """zip 을 임시 폴더에 풀고 완성 후 dest_dir 로 교체 (실패 시 기존 버전 보존).

    promote_single_root=True 면 zip 최상위에 폴더 하나만 있을 때(예: zipball 루트
    bgutil-ytdlp-pot-provider-1.3.2/) 그 내부를 dest_dir 로 승격한다.
    """
    tmp = dest_dir + ".tmp"
    _rmtree(tmp)
    os.makedirs(os.path.dirname(tmp) or ".", exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(tmp)
    if promote_single_root:
        entries = os.listdir(tmp)
        if len(entries) == 1 and os.path.isdir(os.path.join(tmp, entries[0])):
            inner = os.path.join(tmp, entries[0])
            _rmtree(dest_dir)
            shutil.move(inner, dest_dir)
            _rmtree(tmp)
    else:
        for entry in os.listdir(tmp):
            s = os.path.join(tmp, entry)
            d = os.path.join(dest_dir, entry)
            if os.path.isdir(d):
                shutil.rmtree(d, ignore_errors=True)
            os.makedirs(os.path.dirname(d) or ".", exist_ok=True)
            shutil.move(s, d)
        _rmtree(tmp)
    log(emit_component("DEPS", "OK", "-", f"{label} extracted → {os.path.relpath(dest_dir, components_root())}"))


FFMPEG_DIRNAME = "ffmpeg"
FFMPEG_RELEASE_URL = (
    "https://github.com/GyanD/codexffmpeg/releases/latest/download/"
    "ffmpeg-release-essentials.zip"
)
_FFMPEG_BREW_API = "https://formulae.brew.sh/api/formula/ffmpeg.json"

# macOS 버전 → Homebrew bottle 키 매핑 (arm64 우선, intel 폴백)
_MACOS_BOTTLE_KEY_ORDER = [
    # (major, minor), arm64_key, intel_key
    ((15, 0), "arm64_sonoma", "sonoma"),
    ((14, 0), "arm64_sonoma", "sonoma"),
    ((13, 0), "arm64_ventura", "ventura"),
    ((12, 0), "arm64_monterey", "monterey"),
    ((11, 0), "arm64_big_sur", "big_sur"),
    ((10, 15), "arm64_catalina", "catalina"),
]


def _macos_bottle_keys():
    """현재 macOS 버전/아키텍처에 맞는 Homebrew bottle 키 목록 (우선순위순)."""
    ver = platform.mac_ver()[0]
    if not ver:
        return []
    parts = ver.split(".")
    major = int(parts[0]) if parts else 0
    minor = int(parts[1]) if len(parts) > 1 else 0
    arch = platform.machine()  # 'arm64' or 'x86_64'

    # 현재 버전 이상의 bottle 키를 모두 수집
    keys = []
    for (m, M), arm_key, intel_key in _MACOS_BOTTLE_KEY_ORDER:
        if (major, minor) >= (m, M):
            if arch == "arm64":
                keys.append(arm_key)
            keys.append(intel_key)
    # 현재 버전 매칭이 없으면 최신 키로 폴백
    if not keys:
        _, arm_key, intel_key = _MACOS_BOTTLE_KEY_ORDER[0]
        if arch == "arm64":
            keys.append(arm_key)
        keys.append(intel_key)
    return keys


def _ensure_ffmpeg_macos(log, force):
    """맥용 ffmpeg 자동 수급 - Homebrew 우선, 없으면 bottle 다운로드."""
    dest = os.path.join(config.writable_base(), FFMPEG_DIRNAME)

    if not force:
        cached = ffmpeg_exe()
        if cached:
            # ffmpeg가 실제로 실행 가능한지 확인
            if _verify_ffmpeg(cached):
                _wire_ffmpeg_path(os.path.dirname(cached))
                log(emit_component("DEPS", "OK", "ffmpeg", "ok"))
                return None
            else:
                log(emit_component("DEPS", "WARN", "ffmpeg", "cached not working, reinstalling"))
                # 캐시된 ffmpeg가 작동하지 않으므로 삭제
                try:
                    if os.path.exists(dest):
                        shutil.rmtree(dest, ignore_errors=True)
                except Exception:
                    pass

    # Homebrew가 설치되어 있으면 brew install ffmpeg 시도
    brew_path = shutil.which("brew")
    if brew_path:
        log(emit_component("DEPS", "RUN", "ffmpeg", "installing via Homebrew..."))
        import subprocess
        try:
            result = subprocess.run(
                ["brew", "install", "ffmpeg"],
                capture_output=True,
                text=True,
                timeout=300  # 5분 타임아웃
            )
            if result.returncode == 0:
                # 설치 성공 - 경로 확인
                ffmpeg_path = shutil.which("ffmpeg")
                if ffmpeg_path and _verify_ffmpeg(ffmpeg_path):
                    log(emit_component("DEPS", "OK", "ffmpeg", "ok"))
                    return None
            else:
                log(emit_component("DEPS", "WARN", "ffmpeg", f"brew install failed: {result.stderr[:100]}"))
        except subprocess.TimeoutExpired:
            log(emit_component("DEPS", "WARN", "ffmpeg", "brew install timed out"))
        except Exception as e:
            log(emit_component("DEPS", "WARN", "ffmpeg", f"brew install error: {e}"))

    # Homebrew 실패 시 bottle 다운로드 시도
    try:
        log(emit_component("DEPS", "RUN", "ffmpeg", "downloading (Homebrew bottle)..."))
        with urllib.request.urlopen(_FFMPEG_BREW_API, timeout=15) as resp:
            data = json.load(resp)

        bottle = data.get("bottle", {}).get("stable", {})
        files = bottle.get("files", {})

        keys = _macos_bottle_keys()
        selected = None
        for key in keys:
            if key in files:
                selected = files[key]
                break

        if not selected:
            return "no compatible Homebrew bottle for this macOS version/arch"

        url = selected.get("url")
        sha256 = selected.get("sha256")
        if not url:
            return "Homebrew bottle URL missing"

        with tempfile.TemporaryDirectory(prefix="cz_ffmpeg_") as td:
            tar_path = os.path.join(td, "ffmpeg.tar.gz")
            _download(url, tar_path, log, "ffmpeg", is_status=True)

            if sha256:
                got = _sha256(tar_path)
                if got != sha256:
                    return f"ffmpeg bottle hash mismatch ({got[:12]}…)"
                log(emit_component("DEPS", "OK", "ffmpeg", "SHA-256 ok"))

            log(emit_component("DEPS", "RUN", "ffmpeg", "extracting..."))
            # 기존 디렉토리를 완전히 삭제
            if os.path.exists(dest):
                shutil.rmtree(dest, ignore_errors=True)
            os.makedirs(dest, exist_ok=True)

            # subprocess로 tar 명령어 직접 실행
            import subprocess
            result = subprocess.run(
                ["tar", "-xzf", tar_path, "-C", dest],
                capture_output=True,
                text=True,
                timeout=120
            )
            if result.returncode != 0:
                return f"tar extraction failed: {result.stderr}"

            # bottle 추출 구조에서 ffmpeg 검색
            ffmpeg_src = None
            ffmpeg_bin_dir = None
            for root, dirs, files in os.walk(dest):
                if "ffmpeg" in files:
                    candidate = os.path.join(root, "ffmpeg")
                    if os.path.isfile(candidate):
                        ffmpeg_src = candidate
                        ffmpeg_bin_dir = root
                        break

            if ffmpeg_src and ffmpeg_bin_dir:
                # 원래 디렉토리 구조를 유지하고 PATH에 추가
                _wire_ffmpeg_path(ffmpeg_bin_dir)
                # 설치 확인
                if _verify_ffmpeg(ffmpeg_src):
                    log(emit_component("DEPS", "OK", "ffmpeg", "ok"))
                    return None
                else:
                    return "ffmpeg installed but not working (verification failed)"
        return "ffmpeg exe not found after extract"
    except Exception as e:
        return f"{type(e).__name__}: {e}"

def ffmpeg_exe():
    """ffmpeg 실행 파일 경로. 수급 캐시 우선, 없으면 시스템 PATH."""
    exe_name = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    # 기존 위치 (bin_dir) 확인
    local = os.path.join(
        config.writable_base(), FFMPEG_DIRNAME, "bin", exe_name
    )
    if os.path.isfile(local) and os.access(local, os.X_OK):
        return local
    # Homebrew bottle 추출 디렉토리에서 검색
    dest = os.path.join(config.writable_base(), FFMPEG_DIRNAME)
    if os.path.isdir(dest):
        for root, dirs, files in os.walk(dest):
            if exe_name in files:
                candidate = os.path.join(root, exe_name)
                if os.access(candidate, os.X_OK):
                    return candidate
    return shutil.which("ffmpeg")

def _wire_ffmpeg_path(bin_dir):
    """수급/캐시된 ffmpeg bin을 프로세스 PATH 선두에 연결.

    media.py·downloader.py가 subprocess로 bare 'ffmpeg'를 호출하므로, 시스템
    설치가 없는 PC에서도 이 세션의 자식 프로세스가 수급본을 즉시 사용하게 한다.
    """
    try:
        if os.path.isdir(bin_dir):
            path_env = os.environ.get("PATH", "")
            parts = path_env.split(os.pathsep) if path_env else []
            if bin_dir not in parts:
                os.environ["PATH"] = os.pathsep.join([bin_dir] + parts)
                # 디버그: PATH 확인
                import logging
                logging.debug(f"ffmpeg bin added to PATH: {bin_dir}")
                logging.debug(f"ffmpeg executable check: {shutil.which('ffmpeg')}")
    except Exception:
        pass

def _verify_ffmpeg(ffmpeg_path):
    """ffmpeg이 실제로 실행 가능한지 확인."""
    import subprocess
    try:
        result = subprocess.run(
            [ffmpeg_path, "-version"],
            capture_output=True,
            timeout=10
        )
        return result.returncode == 0
    except Exception:
        return False

def ensure_ffmpeg(log, force=False):
    """병합/리먹싱용 ffmpeg 자동 수급 — 시스템 설치 우선, 없으면 GitHub 바이너리.

    [배경] media.py·downloader.py는 subprocess로 'ffmpeg'를 곧바로 호출하므로
    사용자 PC에 ffmpeg이 없으면 병합/썸네일/오디오 추출이 전부 실패한다.
    성공/스킵 시 None, 실패 시 오류 문자열.
    """
    log = _logcb(log)
    log(emit_component("DEPS", "RUN", "ffmpeg", "checking..."))
    try:
        # [맥 지원] 맥에서는 시스템 ffmpeg 우선 사용, 없으면 Homebrew bottle 자동 수급
        if os.name != "nt":
            which = shutil.which("ffmpeg")
            if which:
                # ffmpeg이 실제로 실행 가능한지 확인
                if os.access(which, os.X_OK) and _verify_ffmpeg(which):
                    log(emit_component("DEPS", "OK", "ffmpeg", "ok"))
                    return None
                else:
                    log(emit_component("DEPS", "WARN", "ffmpeg", f"found but not working ({which})"))
            return _ensure_ffmpeg_macos(log, force)

        if not force:
            which = shutil.which("ffmpeg")
            if which:
                log(emit_component("DEPS", "OK", "ffmpeg", "ok"))
                return None
            cached = ffmpeg_exe()
            if cached:
                _wire_ffmpeg_path(os.path.dirname(cached))
                log(emit_component("DEPS", "OK", "ffmpeg", "ok"))
                return None
        dest = os.path.join(config.writable_base(), FFMPEG_DIRNAME)
        bin_dir = os.path.join(dest, "bin")
        _exe = ".exe" if os.name == "nt" else ""
        if not force and os.path.isfile(os.path.join(bin_dir, f"ffmpeg{_exe}")):
            _wire_ffmpeg_path(bin_dir)
            log(emit_component("DEPS", "OK", "ffmpeg", "ok"))
            return None
        os.makedirs(dest, exist_ok=True)
        log(emit_component("DEPS", "RUN", "ffmpeg", "downloading..."))
        with tempfile.TemporaryDirectory(prefix="cz_ffmpeg_") as td:
            zp = _download(
                FFMPEG_RELEASE_URL, os.path.join(td, "ffmpeg.zip"), log, "ffmpeg"
            )
            _extract_zip(zp, dest, log, "ffmpeg", promote_single_root=True)
        exe = os.path.join(bin_dir, f"ffmpeg{_exe}")
        if os.path.isfile(exe):
            _wire_ffmpeg_path(bin_dir)
            log(emit_component("DEPS", "OK", "ffmpeg", "ok"))
            return None
        return "ffmpeg exe not found after extract"
    except Exception as e:
        return f"{type(e).__name__}: {e}"

