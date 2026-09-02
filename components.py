### components.py - 런타임 구성요소 관리자 (yt-dlp / 플러그인 / PO 서버 팩 / streamlink 팩)
"""빌드(exe)에는 UI와 메인 로직만 담고, 외부 스크래퍼 컴포넌트는 실행 시
GitHub/자체 릴리스에서 내려받아 <exe>/components/ 에 전개한다 (Hitomi Downloader 방식).

*  yt-dlp        : 공식 GitHub 릴리스의 순수 파이썬 휠(.whl) — SHA2-256SUMS 검증 후
                   components/yt-dlp/ 에 추출. sys.path 주입으로 파이썬 API 그대로 사용.
*  bgutil 플러그인: Brainicism 릴리스 zip — components/yt-dlp/yt_dlp_plugins/ 로 추출
                   (yt-dlp 플러그인 로더가 namespace 탐색).
*  PO 서버 팩    : 배포자 자체 릴리스 에셋 pot-pack.zip (프루닝된 bgutil 서버 +
                   node/node.exe) — pot_provider 가 스폰.
*  streamlink 팩 : 배포자 자체 릴리스 에셋 streamlink-pack.zip — 라이브 녹화용.
                   frozen 에서 `ChzzkTube.exe --run-streamlink ...` 자식 모드로 실행.

모든 함수는 (msg, is_error) 로그 콜백을 받아 진행 상황을 상세히 알린다.
재시작 없이 적용: 설치 완료 후 downloader.reload_ytdlp() 로 세션 내 모듈 교체.
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
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    return urllib.request.urlopen(req, timeout=timeout)


def _download(url, dest, log, label=""):
    """파일 다운로드(진행 로그 포함). 성공 시 dest 경로 반환."""
    log(emit_component("DEPS", "RUN", "-", f"{label or os.path.basename(url)} 내려받는 중..."))
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
            if total >= 8 * 1024 * 1024 and mb != last_mb:
                last_mb = mb
                pct = f" ({done * 100 // total}%)" if total else ""
                log(emit_component("DEPS", "RUN", "-", f"{label or '다운로드'} {mb} MB{pct}"))
    os.replace(tmp, dest)
    log(emit_component("DEPS", "OK", "-", f"{label or os.path.basename(dest)} 완료 ({done / 1048576:.1f} MB)"))
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
    log(emit_component("DEPS", "OK", "-", f"{label} 전개 완료 → {os.path.relpath(dest_dir, components_root())}"))


FFMPEG_DIRNAME = "ffmpeg"
FFMPEG_RELEASE_URL = (
    "https://github.com/GyanD/codexffmpeg/releases/latest/download/"
    "ffmpeg-release-essentials.zip"
)

def ffmpeg_ready():
    """ffmpeg 실행 파일 확보 여부 (수급 캐시 or 시스템 PATH)."""
    return ffmpeg_exe() is not None

def ffmpeg_exe():
    """ffmpeg 실행 파일 경로. 수급 캐시 우선, 없으면 시스템 PATH."""
    exe_name = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    local = os.path.join(
        config.writable_base(), FFMPEG_DIRNAME, "bin", exe_name
    )
    if os.path.isfile(local):
        return local
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
    except Exception:
        pass

def ensure_ffmpeg(log, force=False):
    """병합/리먹싱용 ffmpeg 자동 수급 — 시스템 설치 우선, 없으면 GitHub 바이너리.

    [배경] media.py·downloader.py는 subprocess로 'ffmpeg'를 곧바로 호출하므로
    사용자 PC에 ffmpeg이 없으면 병합/썸네일/오디오 추출이 전부 실패한다.
    성공/스킵 시 None, 실패 시 오류 문자열.
    """
    log = _logcb(log)
    try:
        # [맥 지원] 맥에서는 시스템 ffmpeg 우선 사용, 없으면 Homebrew 권유
        if os.name != "nt":
            which = shutil.which("ffmpeg")
            if which:
                log(emit_component("DEPS", "OK", "-", f"ffmpeg 시스템 설치 확인 — 건너뜀 ({which})"))
                return None
            log(emit_component("DEPS", "WARN", "-", "ffmpeg 미설치 — brew install ffmpeg 로 설치 권장 (병합/리먹싱 제한)"))
            return "ffmpeg 미설치 — macOS에서는 brew install ffmpeg 로 설치하세요"

        if not force:
            which = shutil.which("ffmpeg")
            if which:
                log(emit_component("DEPS", "OK", "-", "ffmpeg 시스템 설치 확인 — 건너뜀"))
                return None
            cached = ffmpeg_exe()
            if cached:
                _wire_ffmpeg_path(os.path.dirname(cached))
                log(emit_component("DEPS", "OK", "-", "ffmpeg 캐시 존재 — 건너뜀 (PATH 연결 완료)"))
                return None
        dest = os.path.join(config.writable_base(), FFMPEG_DIRNAME)
        bin_dir = os.path.join(dest, "bin")
        _exe = ".exe" if os.name == "nt" else ""
        if not force and os.path.isfile(os.path.join(bin_dir, f"ffmpeg{_exe}")):
            _wire_ffmpeg_path(bin_dir)
            log(emit_component("DEPS", "OK", "-", "ffmpeg 캐시 존재 — 건너뜀 (PATH 연결 완료)"))
            return None
        os.makedirs(dest, exist_ok=True)
        log(emit_component("DEPS", "RUN", "-", "ffmpeg GitHub 바이너리 내려받는 중... (수십 MB)"))
        with tempfile.TemporaryDirectory(prefix="cz_ffmpeg_") as td:
            zp = _download(
                FFMPEG_RELEASE_URL, os.path.join(td, "ffmpeg.zip"), log, "ffmpeg"
            )
            _extract_zip(zp, dest, log, "ffmpeg", promote_single_root=True)
        exe = os.path.join(bin_dir, f"ffmpeg{_exe}")
        if os.path.isfile(exe):
            _wire_ffmpeg_path(bin_dir)
            log(emit_component("DEPS", "OK", "-", "ffmpeg 설치 완료 (병합/리먹싱 준비됨, PATH 연결 완료)"))
            return None
        return "ffmpeg 전개 후 ffmpeg.exe 를 찾지 못했습니다"
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
            log(emit_component("DEPS", "RUN", "yt-dlp", f"최신 릴리스 확인 중... (설치: {cur})"))
            log_history.log(f"yt-dlp 최신 릴리스 확인 중... (설치: {cur})")
            with _http_get(f"https://api.github.com/repos/{YTDLP_REPO}/releases/latest") as r:
                meta = json.loads(r.read().decode("utf-8"))
            tag = meta.get("tag_name", "")
            if tag and tag == cur:
                log(emit_component("DEPS", "OK", "yt-dlp", f"{cur} 최신 — 건너뜀"))
                log_history.log(f"yt-dlp {cur} 최신 — 건너뜀")
                return cur, None
        else:
            log(emit_component("DEPS", "RUN", "yt-dlp", "최신 릴리스 확인 중..."))
            log_history.log("yt-dlp 최신 릴리스 확인 중...")
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
            return None, "릴리스에서 yt-dlp 휠 에셋을 찾지 못했습니다"
        sums = next((a for a in assets if a.get("name") == "SHA2-256SUMS"), None)
        with tempfile.TemporaryDirectory(prefix="cz_comp_") as td:
            wl = _download(wheel["browser_download_url"], os.path.join(td, wheel["name"]), log,
                           f"yt-dlp {tag} 휠")
            if sums:
                sf = _download(sums["browser_download_url"], os.path.join(td, "sums"), log,
                               "SHA256 검증표")
                want = ""
                with open(sf, encoding="utf-8", errors="replace") as f:
                    for line in f:
                        if line.strip().endswith(wheel["name"]):
                            want = line.split()[0].strip().lower()
                            break
                got = _sha256(wl)
                if want and got != want:
                    return None, f"yt-dlp 휠 해시 불일치({got[:12]}…) — 변조/전송 오류"
                log(emit_component("DEPS", "OK", "-", "SHA-256 검증 통과"))
            _extract_zip(wl, ytdlp_dir(), log, "yt-dlp")
        with open(os.path.join(ytdlp_dir(), ".version"), "w", encoding="utf-8") as f:
            f.write(tag)
        log(emit_component("DEPS", "OK", "yt-dlp", f"{tag} 설치 완료"))
        log_history.log(f"yt-dlp {tag} 설치 완료")
        return tag, None
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        log_history.log(f"yt-dlp 수급 실패: {err}", "ERROR")
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
            log(emit_component("DEPS", "OK", "bgutil", f"플러그인 최신 — 건너뜀 ({cur[:22]}…)" if cur else "플러그인 최신 — 건너뜀"))
            return None
        log(emit_component("DEPS", "RUN", "bgutil", "플러그인 내려받는 중..."))
        os.makedirs(ytdlp_dir(), exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="cz_comp_") as td:
            zp = _download(BUTIL_PLUGIN_URL, os.path.join(td, "plugin.zip"), log,
                           "bgutil 플러그인")
            _extract_zip(zp, ytdlp_dir(), log, "bgutil 플러그인")
        with open(marker, "w", encoding="utf-8") as f:
            f.write(lm)
        log(emit_component("DEPS", "OK", "bgutil", "플러그인 설치 완료 (PO Token Provider)"))
        log_history.log("bgutil 플러그인 설치 완료 (PO Token Provider)")
        return None
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        log_history.log(f"bgutil 플러그인 수급 실패: {err}", "ERROR")
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
    """PO 서버 팩(pot-pack.zip: node/node.exe + 프루닝된 bgutil 서버) 전개.

    URL 이 미설정/실패여도 기존 전개분 또는 번들(_internal)이 있으면 통과.
    성공/기존유지 시 None, 완전 실패 시 오류 문자열.

    [맥 지원] 맥에서는 pot-pack.zip (윈도우 전용)을 다운로드하지 않고,
    시스템 Node.js + bgutil 소스를 직접 빌드하여 사용한다.
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
                    log(emit_component("DEPS", "OK", "POT", f"PO 서버 최신 — 건너뜀 ({remote or '알 수 없음'})"))
                    return None
            if not node_ok:
                log(emit_component("DEPS", "WARN", "POT", "Node.js 미설치 — brew install node 로 설치 권한 (PO Token 제한)"))
                return "Node.js 미설치 — macOS에서는 brew install node 로 설치하세요"
            # 맥에서는 pot-pack.zip 다운로드 없이 bgutil 소스 빌드로 진행
            if not POT_PACK_URL:
                if srv_ok:
                    log(emit_component("DEPS", "OK", "POT", "PO 서버 기존 빌드 사용"))
                    return None
                # bgutil 소스 빌드 시도 (pot_provider에서 처리)
                log(emit_component("DEPS", "RUN", "POT", "bgutil 서버 소스 빌드 준비 (시스템 Node.js 사용)"))
                return None

        current, remote = _pack_current(POT_PACK_VER_URL, pack_json)
        if not force and node_ok and srv_ok and current:
            log(emit_component("DEPS", "OK", "POT", f"PO 서버 팩 최신 — 건너뜀 ({remote or '알 수 없음'})"))
            log_history.log(f"PO 서버 팩 최신 — 건너뜀 ({remote or '알 수 없음'})")
            return None
        if not POT_PACK_URL:
            if node_ok and srv_ok:
                log(emit_component("DEPS", "OK", "POT", "PO 서버 팩 기존 버전 사용 (URL 미설정)"))
                return None
            return (
                "PO 서버 팩 URL이 설정되지 않았습니다 — 배포자가 pot-pack.zip 을"
                " 릴리스에 올리고 POT_PACK_URL 을 지정해야 합니다"
            )
        log(emit_component("DEPS", "RUN", "POT", "PO 서버 팩 내려받는 중... (node.exe + bgutil 서버, 수십 MB)"))
        os.makedirs(root, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="cz_comp_") as td:
            zp = _download(POT_PACK_URL, os.path.join(td, "pot-pack.zip"), log,
                           "PO 서버 팩")
            _extract_zip(zp, root, log, "PO 서버 팩", promote_single_root=True)
        if not (os.path.isfile(os.path.join(components_root(), "node", "node.exe"))
                and os.path.isfile(os.path.join(pot_server_dir(), "build", "main.js"))):
            return "PO 서버 팩에 node/node.exe 또는 server/build/main.js 가 없습니다"
        log(emit_component("DEPS", "OK", "POT", "PO 서버 팩 설치 완료 (node.exe + bgutil 서버)"))
        log_history.log("PO 서버 팩 설치 완료 (node.exe + bgutil 서버)")
        return None
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        log_history.log(f"PO 서버 팩 수급 실패: {err}", "ERROR")
        return err


def streamlink_ready():
    return os.path.isdir(streamlink_dir()) and os.path.isdir(
        os.path.join(streamlink_dir(), "streamlink_cli")
    )


def ensure_streamlink_pack(log, force=False):
    """streamlink 팩(치지직 라이브 녹화용) 전개. URL 미설정/실패 시 기존분 사용.

    [맥 지원] 맥에서는 streamlink-pip.zip (윈도우 전용)을 다운로드하지 않고,
    pip로 설치된 streamlink를 사용한다.
    """
    log = _logcb(log)
    try:
        # [맥 지원] 맥에서는 pip 설치 streamlink 우선 사용
        if os.name != "nt":
            try:
                import streamlink  # noqa: F401
                log(emit_component("DEPS", "OK", "streamlink", "streamlink pip 설치 확인 — 건너뜀"))
                return None
            except ImportError:
                pass
            if not SL_PACK_URL:
                log(emit_component("DEPS", "WARN", "streamlink", "streamlink 미설치 — pip install streamlink 로 설치 권장"))
                return "streamlink 미설치 — macOS에서는 pip install streamlink 로 설치하세요"

        pack_json = os.path.join(streamlink_dir(), "pack.json")
        current, remote = _pack_current(SL_PACK_VER_URL, pack_json)
        if not force and streamlink_ready() and current:
            log(emit_component("DEPS", "OK", "streamlink", f"팩 최신 — 건너뜀 ({remote or '알 수 없음'})"))
            return None
        if not SL_PACK_URL:
            if streamlink_ready():
                log(emit_component("DEPS", "OK", "streamlink", "팩 기존 버전 사용 (URL 미설정)"))
                return None
            return (
                "streamlink 팩 URL이 설정되지 않았습니다 — 치지직 라이브 녹화에는"
                " streamlink-pack.zip 이 필요합니다"
            )
        log(emit_component("DEPS", "RUN", "streamlink", "팩 내려받는 중... (치지직 라이브 녹화 엔진)"))
        os.makedirs(streamlink_dir(), exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="cz_comp_") as td:
            zp = _download(SL_PACK_URL, os.path.join(td, "streamlink-pack.zip"), log,
                           "streamlink 팩")
            _extract_zip(zp, streamlink_dir(), log, "streamlink 팩",
                         promote_single_root=True)
        if not streamlink_ready():
            return "streamlink 팩에 streamlink_cli 가 없습니다"
        log(emit_component("DEPS", "OK", "streamlink", "팩 설치 완료"))
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
    log(emit_component("DEPS", "RUN", "-", "외부 구성요소 동기화 시작 (yt-dlp / 플러그인 / PO 서버 / streamlink)"))
    errs = []
    _ver, err = ensure_ytdlp(log, force)
    if err:
        errs.append(f"yt-dlp: {err}")
    err = ensure_bgutil_plugin(log, force)
    if err:
        errs.append(f"bgutil 플러그인: {err}")
    err = ensure_pot_pack(log, force)
    if err:
        errs.append(f"PO 서버 팩: {err}")
    err = ensure_streamlink_pack(log, force)
    if err:
        errs.append(f"streamlink 팩: {err}")
    _last_error = "; ".join(errs)
    ok = not errs
    _ready_event.set()
    if ok:
        log(emit_component("DEPS", "OK", "-", "구성요소 준비 완료 — 모든 기능 사용 가능"))
    else:
        log(emit_component("SYS", "FAIL", "DEPS", f"일부 구성요소 미준비 — {len(errs)}개 오류"))
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
