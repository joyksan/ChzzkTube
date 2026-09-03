### components.py - runtime component manager (yt-dlp / plugin / pot pack / streamlink pack)
"""Build (exe) contains only UI and main logic; external scraper components are
downloaded from GitHub/distributor releases at startup and extracted to
<exe>/components/ (Hitomi Downloader style).

*  yt-dlp        : official GitHub release pure-python wheel (.whl) — SHA2-256SUMS
                   verified, extracted to components/yt-dlp/. sys.path injection
                   gives us the Python API as-is.
*  bgutil plugin : Brainicism release zip — extracted to
                   components/yt-dlp/yt_dlp_plugins/ (yt-dlp plugin loader does
                   namespace discovery).
*  pot pack       : distributor self-hosted pot-pack.zip (pruned bgutil server +
                   node/node.exe) — spawned by pot_provider.
*  streamlink pack: distributor self-hosted streamlink-pack.zip — for live recording.
                   In frozen builds runs as child: `ChzzkTube.exe --run-streamlink ...`.

All functions receive a (msg, is_error) log callback to report progress in detail.
No-restart apply: after install, call downloader.reload_ytdlp() to swap the
session module.
"""
import hashlib
import importlib
import io
import json
import os
import shutil
import sys
import tempfile
import threading
import urllib.request
import zipfile
import tarfile

import config
import log_history
import platform
from log_console import emit_component

# --- 배포자 설정 (릴리스 에셋 URL) -----------------------------------------------
# pot-pack.zip / streamlink-pack.zip 은 make_components.py 로 만들어 자체 GitHub
# 릴리스에 업로드한다. 같은 이름의 .version 텍스트 파일(버전 문자열)을 함께 올리면
# 매 실행 시 전체 재다운로드 없이 갱신 여부만 확인한다.
YTDLP_REPO = "yt-dlp/yt-dlp"
BUTIL_PLUGIN_URL = (
    "https://github.com/Brainicism/bgutil-ytdlp-pot-provider/releases/latest/"
    "download/bgutil-ytdlp-pot-provider.zip"
)
POT_PACK_URL = os.environ.get(
    "CHZZKTUBE_POT_PACK_URL",
    "",  # 예: https://github.com/<user>/<repo>/releases/latest/download/pot-pack.zip
)
POT_PACK_VER_URL = os.environ.get(
    "CHZZKTUBE_POT_PACK_VER_URL",
    "",  # 예: .../releases/latest/download/pot-pack.version
)
SL_PACK_URL = os.environ.get(
    "CHZZKTUBE_SL_PACK_URL",
    "",  # 예: .../releases/latest/download/streamlink-pack.zip
)
SL_PACK_VER_URL = os.environ.get(
    "CHZZKTUBE_SL_PACK_VER_URL",
    "",  # 예: .../releases/latest/download/streamlink-pack.version
)
_UA = "ChzzkTube-Components/1.0"


def components_root():
    """구성요소 전개 루트. frozen: <exe>/components, source: <repo>/components."""
    env = os.environ.get("CHZZKTUBE_COMPONENTS_DIR")
    if env:
        return env
    if getattr(sys, "frozen", False):
        return os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "components")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "components")


def ytdlp_dir():
    return os.path.join(components_root(), "yt-dlp")


def pot_server_dir():
    return os.path.join(
        components_root(), "bgutil-ytdlp-pot-provider", "server"
    )


def pot_node_exe():
    """Node.js 실행 파일 경로 — 팩 번들 or 시스템 PATH."""
    # 팩 번들 우선 (윈도우: node.exe)
    pack_node = os.path.join(components_root(), "node", "node.exe")
    if os.path.isfile(pack_node):
        return pack_node
    # 번들 없으면 시스템 PATH의 node 사용
    system_node = shutil.which("node")
    return system_node


def streamlink_dir():
    return os.path.join(components_root(), "streamlink")


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
                log(emit_component("DEPS", "OK", "-", "ffmpeg cached — skip"))
                return None
            else:
                log(emit_component("DEPS", "WARN", "-", "cached ffmpeg not working, reinstalling"))
                # 캐시된 ffmpeg가 작동하지 않으므로 삭제
                try:
                    if os.path.exists(dest):
                        shutil.rmtree(dest, ignore_errors=True)
                except Exception:
                    pass

    # Homebrew가 설치되어 있으면 brew install ffmpeg 시도
    brew_path = shutil.which("brew")
    if brew_path:
        log(emit_component("DEPS", "RUN", "-", "ffmpeg installing via Homebrew...")
        )
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
                    log(emit_component("DEPS", "OK", "-", "ffmpeg installed via Homebrew"))
                    return None
            else:
                log(emit_component("DEPS", "WARN", "-", f"Homebrew install failed: {result.stderr[:100]}"))
        except subprocess.TimeoutExpired:
            log(emit_component("DEPS", "WARN", "-", "Homebrew install timed out"))
        except Exception as e:
            log(emit_component("DEPS", "WARN", "-", f"Homebrew install error: {e}"))

    # Homebrew 실패 시 bottle 다운로드 시도
    try:
        log(emit_component("DEPS", "RUN", "-", "ffmpeg downloading (Homebrew bottle)..."))
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
                log(emit_component("DEPS", "OK", "-", "SHA-256 ok"))

            log(emit_component("DEPS", "RUN", "-", "ffmpeg extracting..."))
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
                    log(emit_component("DEPS", "OK", "-", "ffmpeg installed (Homebrew bottle)"))
                    return None
                else:
                    return "ffmpeg installed but not working (verification failed)"
        return "ffmpeg exe not found after extract"
    except Exception as e:
        return f"{type(e).__name__}: {e}"

def ffmpeg_ready():
    """ffmpeg 실행 파일 확보 여부 (수급 캐시 or 시스템 PATH)."""
    return ffmpeg_exe() is not None

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
    try:
        # [맥 지원] 맥에서는 시스템 ffmpeg 우선 사용, 없으면 Homebrew bottle 자동 수급
        if os.name != "nt":
            which = shutil.which("ffmpeg")
            if which:
                # ffmpeg이 실제로 실행 가능한지 확인
                if os.access(which, os.X_OK) and _verify_ffmpeg(which):
                    log(emit_component("DEPS", "OK", "-", f"ffmpeg ok — skip ({which})"))
                    return None
                else:
                    log(emit_component("DEPS", "WARN", "-", f"ffmpeg found but not working ({which})"))
            return _ensure_ffmpeg_macos(log, force)

        if not force:
            which = shutil.which("ffmpeg")
            if which:
                log(emit_component("DEPS", "OK", "-", "ffmpeg ok — skip"))
                return None
            cached = ffmpeg_exe()
            if cached:
                _wire_ffmpeg_path(os.path.dirname(cached))
                log(emit_component("DEPS", "OK", "-", "ffmpeg cached — skip"))
                return None
        dest = os.path.join(config.writable_base(), FFMPEG_DIRNAME)
        bin_dir = os.path.join(dest, "bin")
        _exe = ".exe" if os.name == "nt" else ""
        if not force and os.path.isfile(os.path.join(bin_dir, f"ffmpeg{_exe}")):
            _wire_ffmpeg_path(bin_dir)
            log(emit_component("DEPS", "OK", "-", "ffmpeg cached — skip"))
            return None
        os.makedirs(dest, exist_ok=True)
        log(emit_component("DEPS", "RUN", "-", "ffmpeg downloading..."))
        with tempfile.TemporaryDirectory(prefix="cz_ffmpeg_") as td:
            zp = _download(
                FFMPEG_RELEASE_URL, os.path.join(td, "ffmpeg.zip"), log, "ffmpeg"
            )
            _extract_zip(zp, dest, log, "ffmpeg", promote_single_root=True)
        exe = os.path.join(bin_dir, f"ffmpeg{_exe}")
        if os.path.isfile(exe):
            _wire_ffmpeg_path(bin_dir)
            log(emit_component("DEPS", "OK", "-", "ffmpeg installed — ok"))
            return None
        return "ffmpeg exe not found after extract"
    except Exception as e:
        return f"{type(e).__name__}: {e}"

def ytdlp_installed_version():
    """설치된 yt-dlp 컴포넌트 버전(마커 파일). 없으면 None."""
    try:
        with open(os.path.join(ytdlp_dir(), ".version"), encoding="utf-8") as f:
            return f.read().strip() or None
    except OSError:
        return None


def ensure_ytdlp(log, force=False):
    """yt-dlp 휠을 최신 릴리스와 동기화. 성공 시 (버전, 캐시사용여부), 실패 시 (None, err)."""
    log = _logcb(log)
    try:
        os.makedirs(ytdlp_dir(), exist_ok=True)
        cur = ytdlp_installed_version()
        if not force and cur:
            log(emit_component("DEPS", "RUN", "ytdlp", f"checking... (cur: {cur})"))
            log_history.log(f"yt-dlp checking latest... (cur: {cur})")
            with _http_get(f"https://api.github.com/repos/{YTDLP_REPO}/releases/latest") as r:
                meta = json.loads(r.read().decode("utf-8"))
            tag = meta.get("tag_name", "")
            if tag and tag == cur:
                log(emit_component("DEPS", "OK", "ytdlp", f"{cur} up-to-date — skip"))
                log_history.log(f"yt-dlp {cur} up-to-date — skip")
                return cur, None
        else:
            log(emit_component("DEPS", "RUN", "ytdlp", "checking latest..."))
            log_history.log("yt-dlp checking latest...")
            with _http_get(f"https://api.github.com/repos/{YTDLP_REPO}/releases/latest") as r:
                meta = json.loads(r.read().decode("utf-8"))
        tag = meta.get("tag_name", "")
        assets = meta.get("assets") or []
        wheel = next(
            (a for a in assets
             if a.get("name", "").startswith("yt_dlp-")
             and a.get("name", "").endswith("-py3-none-any.whl")),
            None,
        )
        if not wheel:
            return None, "yt-dlp wheel asset not found in release"
        sums = next((a for a in assets if a.get("name") == "SHA2-256SUMS"), None)
        with tempfile.TemporaryDirectory(prefix="cz_comp_") as td:
            wl = _download(wheel["browser_download_url"], os.path.join(td, wheel["name"]), log,
                           f"yt-dlp {tag} wheel")
            if sums:
                sf = _download(sums["browser_download_url"], os.path.join(td, "sums"), log,
                               "SHA256 sums")
                want = ""
                with open(sf, encoding="utf-8", errors="replace") as f:
                    for line in f:
                        if line.strip().endswith(wheel["name"]):
                            want = line.split()[0].strip().lower()
                            break
                got = _sha256(wl)
                if want and got != want:
                    return None, f"yt-dlp wheel hash mismatch ({got[:12]}…)"
                log(emit_component("DEPS", "OK", "-", "SHA-256 ok"))
            _extract_zip(wl, ytdlp_dir(), log, "yt-dlp")
        with open(os.path.join(ytdlp_dir(), ".version"), "w", encoding="utf-8") as f:
            f.write(tag)
        log(emit_component("DEPS", "OK", "ytdlp", f"{tag} installed"))
        log_history.log(f"yt-dlp {tag} installed")
        return tag, None
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        log_history.log(f"yt-dlp fetch failed: {err}", "ERROR")
        return None, err


def ensure_bgutil_plugin(log, force=False):
    """bgutil 플러그인 zip을 components/yt-dlp/yt_dlp_plugins 로 전개.

    zip 이 8KB 수준이라 매 기동 재확인이 부담 없고, 항상 최신을 유지한다.
    """
    log = _logcb(log)
    try:
        marker = os.path.join(ytdlp_dir(), ".plugin-version")
        cur = None
        try:
            with open(marker, encoding="utf-8") as f:
                cur = f.read().strip() or None
        except OSError:
            pass
        # latest/download 는 리다이렉트라 버전을 미리 알 수 없다 — HEAD 대신
        # Last-Modified 를 비교한다(재다운로드 판정).
        req = urllib.request.Request(BUTIL_PLUGIN_URL, headers={"User-Agent": _UA},
                                     method="HEAD")
        with urllib.request.urlopen(req, timeout=30) as r:
            lm = r.headers.get("Last-Modified", "")
        if not force and cur and cur == lm:
            log(emit_component("DEPS", "OK", "bgutil", f"plugin up-to-date — skip" if cur else "plugin up-to-date — skip"))
            return None
        log(emit_component("DEPS", "RUN", "bgutil", "plugin downloading..."))
        os.makedirs(ytdlp_dir(), exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="cz_comp_") as td:
            zp = _download(BUTIL_PLUGIN_URL, os.path.join(td, "plugin.zip"), log,
                           "bgutil plugin")
            _extract_zip(zp, ytdlp_dir(), log, "bgutil plugin")
        with open(marker, "w", encoding="utf-8") as f:
            f.write(lm)
        log(emit_component("DEPS", "OK", "bgutil", "plugin installed"))
        log_history.log("bgutil plugin installed")
        return None
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        log_history.log(f"bgutil plugin fetch failed: {err}", "ERROR")
        return err


def _pack_current(remote_ver_url, local_pack_json):
    """원격 .version 파일과 로컬 pack.json 버전 비교 → (갱신불필요, 원격버전)."""
    local = None
    try:
        with open(local_pack_json, encoding="utf-8") as f:
            local = (json.load(f) or {}).get("version")
    except Exception:
        pass
    if not remote_ver_url:
        return False, None  # 버전 URL 미설정 → 기존분 유지 우선
    try:
        with _http_get(remote_ver_url, timeout=15) as r:
            remote = r.read().decode("utf-8", "replace").strip()
        if local and remote and local == remote:
            return True, remote
        return False, remote
    except Exception:
        return bool(local), None  # 원격 확인 실패 → 기존분 유지


def ensure_pot_pack(log, force=False):
    """pot server pack (pot-pack.zip: node/node.exe + pruned bgutil server) extraction.

    If URL unset/failed, pass as long as an existing extract or _internal bundle exists.
    Returns None on success/existing, or error string on complete failure.

    [macOS] Skip pot-pack.zip download (Windows-only); use system Node.js
    + bgutil source build path instead.
    """
    log = _logcb(log)
    try:
        root = components_root()
        pack_json = os.path.join(root, "bgutil-ytdlp-pot-provider", "server", "pack.json")
        node_ok = pot_node_exe() is not None
        srv_ok = os.path.isfile(os.path.join(pot_server_dir(), "build", "main.js"))

        # [맥 지원] 맥에서는 시스템 Node.js 확인 후 bgutil 소스 빌드 경로 사용
        if os.name != "nt":
            if node_ok and srv_ok:
                current, remote = _pack_current(POT_PACK_VER_URL, pack_json)
                if not force and current:
                    log(emit_component("DEPS", "OK", "pot", f"server up-to-date — skip"))
                    return None
            if not node_ok:
                log(emit_component("DEPS", "WARN", "pot", "node missing — brew install"))
                return "node missing — brew install node"
            # 맥에서는 pot-pack.zip 다운로드 없이 bgutil 소스 빌드로 진행
            if not POT_PACK_URL:
                if srv_ok:
                    log(emit_component("DEPS", "OK", "pot", "server using existing build"))
                    return None
                # bgutil 소스 빌드 시도 (pot_provider에서 처리)
                log(emit_component("DEPS", "RUN", "pot", "bgutil source build (system node)"))
                return None

        current, remote = _pack_current(POT_PACK_VER_URL, pack_json)
        if not force and node_ok and srv_ok and current:
            log(emit_component("DEPS", "OK", "pot", f"pack up-to-date — skip"))
            log_history.log(f"pot pack up-to-date — skip")
            return None
        if not POT_PACK_URL:
            if node_ok and srv_ok:
                log(emit_component("DEPS", "OK", "pot", "pack using existing (URL unset)"))
                return None
            return (
                "pot-pack.zip URL not set — distributor must upload and set POT_PACK_URL"
            )
        log(emit_component("DEPS", "RUN", "pot", "pack downloading..."))
        os.makedirs(root, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="cz_comp_") as td:
            zp = _download(POT_PACK_URL, os.path.join(td, "pot-pack.zip"), log,
                           "pot pack")
            _extract_zip(zp, root, log, "pot pack", promote_single_root=True)
        if not (os.path.isfile(os.path.join(components_root(), "node", "node.exe"))
                and os.path.isfile(os.path.join(pot_server_dir(), "build", "main.js"))):
            return "pot pack missing node.exe or server/build/main.js"
        log(emit_component("DEPS", "OK", "pot", "pack installed"))
        log_history.log("pot pack installed")
        return None
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        log_history.log(f"pot pack fetch failed: {err}", "ERROR")
        return err


def streamlink_ready():
    return os.path.isdir(streamlink_dir()) and os.path.isdir(
        os.path.join(streamlink_dir(), "streamlink_cli")
    )


def ensure_streamlink_pack(log, force=False):
    """streamlink 팩(치지직 라이브 녹화용) 전개. URL 미설정/실패 시 기존분 사용.

    [맥 지원] 맥에서도 streamlink-pip.zip이 아닌 공통 streamlink-pack.zip을
    다운로드한다 (pip 의존 제거).
    """
    log = _logcb(log)
    try:
        pack_json = os.path.join(streamlink_dir(), "pack.json")
        current, remote = _pack_current(SL_PACK_VER_URL, pack_json)
        if not force and streamlink_ready() and current:
            log(emit_component("DEPS", "OK", "streamlink", f"pack up-to-date — skip"))
            return None
        if not SL_PACK_URL:
            if streamlink_ready():
                log(emit_component("DEPS", "OK", "streamlink", "pack using existing (URL unset)"))
                return None
            return (
                "streamlink pack URL not set — required for chzzk live recording"
            )
        log(emit_component("DEPS", "RUN", "streamlink", "pack downloading..."))
        os.makedirs(streamlink_dir(), exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="cz_comp_") as td:
            zp = _download(SL_PACK_URL, os.path.join(td, "streamlink-pack.zip"), log,
                           "streamlink pack")
            _extract_zip(zp, streamlink_dir(), log, "streamlink pack",
                         promote_single_root=True)
        if not streamlink_ready():
            return "streamlink pack missing streamlink_cli"
        log(emit_component("DEPS", "OK", "streamlink", "pack installed"))
        return None
    except Exception as e:
        return f"{type(e).__name__}: {e}"


_ready_event = threading.Event()
_last_error = ""


def ensure_all(log, force=False):
    """기동 시 전체 구성요소 동기화. (ok, 요약오류) 반환.

    개별 실패는 계속 진행(가용한 것부터 사용)하고 최종 요약에 남긴다.
    완료 시 _ready_event 세움 — 다운로드 워커의 대기 해제 신호.
    """
    global _last_error
    _ready_event.clear()
    log(emit_component("DEPS", "RUN", "-", "syncing deps (ytdlp / plugin / pot / streamlink)"))
    errs = []
    _ver, err = ensure_ytdlp(log, force)
    if err:
        errs.append(f"ytdlp: {err}")
    err = ensure_bgutil_plugin(log, force)
    if err:
        errs.append(f"bgutil plugin: {err}")
    err = ensure_pot_pack(log, force)
    if err:
        errs.append(f"pot pack: {err}")
    err = ensure_streamlink_pack(log, force)
    if err:
        errs.append(f"streamlink pack: {err}")
    _last_error = "; ".join(errs)
    ok = not errs
    _ready_event.set()
    if ok:
        log(emit_component("DEPS", "OK", "-", "all deps ready"))
    else:
        log(emit_component("SYS", "FAIL", "DEPS", f"{len(errs)} error(s)"))
        for e in errs:
            log(emit_component("SYS", "FAIL", "DEPS", e))
    return ok, _last_error


def wait_until_ready(timeout=180.0):
    """구성요소 준비(완료 또는 최종 판정)까지 대기 — 다운로드 워커 진입점용."""
    return _ready_event.wait(timeout)


def inject_paths():
    """components 의 yt-dlp(+플러그인)를 sys.path 최우선으로 주입.

    main 의 downloader 임포트 전에 호출해야 `import yt_dlp` 가 컴포넌트 사본을
    가리킨다. 이미 임포트된 세션에서는 downloader.reload_ytdlp() 사용.
    """
    d = ytdlp_dir()
    if os.path.isdir(d) and d not in sys.path:
        sys.path.insert(0, d)
    return d


def run_streamlink_child(argv):
    """`ChzzkTube.exe --run-streamlink <streamlink 인자...>` 자식 모드.

    frozen exe는 `-m streamlink` 를 지원하지 않으므로, 같은 exe에 streamlink CLI
    성격을 부여해 _record_live_stream 의 stdout 파이프 계약을 그대로 유지한다.
    """
    d = streamlink_dir()
    if os.path.isdir(d) and d not in sys.path:
        sys.path.insert(0, d)
    idx = argv.index("--run-streamlink")
    sys.argv = ["streamlink"] + list(argv[idx + 1:])
    try:
        from streamlink_cli.main import main
        main()
    except SystemExit:
        pass
