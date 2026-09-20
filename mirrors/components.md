### components.py - ffmpeg runtime manager
"""ffmpeg 자동 수급/관리 전용 모듈 — 앱 전용 격리 캐시 (v3.8.0).

*  [격리 원칙] 시스템 PATH 탐색(shutil.which)·OS 패키지 매니저(brew install,
   apt-get 등) 서브프로세스 호출 완전 철폐. 오직 writable_base()/ffmpeg/
   단일 캐시만 검사하고, 없으면 정적 바이너리를 직접 수급한다.
*  Windows: GitHub(GyanD/codexffmpeg) release zip → writable_base/ffmpeg/
*  macOS: Homebrew bottle HTTP 직접 다운로드 (brew 실행 없음)
*  Linux: johnvansickle.com 정적 빌드 tar.xz

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
from pathlib import Path

import chzzktube.core.config as config
from chzzktube.core.log_emitter import emit_component, emit_event, emit_dl, emit_error_standard, emit_error_warn

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
    log(emit_component("DEPS", "RUN", "DEPS", f"{label or os.path.basename(url)} fetching..."), is_status)
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
                log(emit_component("DEPS", "RUN", "DEPS", f"{label or 'download'} {mb} MB{pct}"), is_status)
    os.replace(tmp, dest)
    log(emit_component("DEPS", "OK", "DEPS", f"{label or os.path.basename(dest)} done ({done / 1048576:.1f} MB)"))
    return dest


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _rmtree(p):
    shutil.rmtree(p, ignore_errors=True)


def _exe_suffix():
    """현재 OS의 실행 파일 확장자를 반환한다."""
    from chzzktube.infra.platform import exe_suffix

    return exe_suffix()


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
    log(emit_component("DEPS", "OK", "DEPS", f"{label} extracted → {os.path.relpath(dest_dir, components_root())}"))


FFMPEG_DIRNAME = "ffmpeg"
# GitHub 릴리즈 URL: 버전 명시 (latest 사용 시 source code를 가리켜 404 발생)
FFMPEG_RELEASE_URL = (
    "https://github.com/GyanD/codexffmpeg/releases/download/7.1/"
    "ffmpeg-7.1-essentials.zip"
)
_FFMPEG_BREW_API = "https://formulae.brew.sh/api/formula/ffmpeg.json"

# [macOS] Homebrew bottle 키 선정 (v3.8.1) — formulae.brew.sh 응답의 실제
# bottle 키에서 arch prefix 매치로 선택한다. 과거처럼 OS 버전→키 하드코딩
# 테이블을 두면 신형 macOS(15.x Tahoe/Sequoia 등) 키가 누락되어
# "no compatible Homebrew bottle" FAIL이 난다.
# 실측(2026-09): arm64_tahoe / arm64_sequoia / arm64_golden_gate / arm64_linux.
#
# [중요] 현행 formulae(ffmpeg 9.x) bottle은 실행 중 OS에서 dyld 심볼 에러로
# 실행 불가할 수 있다 (Tahoe 26.x SDK 빌드 / Sequoia 빌드라도 깨진 dylib 링크).
# 따라서 bottle 전멸 시 evermeet.cx 정적 빌드로 최종 폴백한다.
_MAC_BOTTLE_ARCH_PREFIX = {
    "arm64": "arm64_",
    "x86_64": "x86_64_",
}
_MAC_BOTTLE_BUILDNUM_ORDER = (
    # (bottle 키 포함 문자열, 빌드 번호) — 낮을수록 구형 OS에서 실행 가능
    ("catalina", 19),
    ("big_sur", 20),
    ("monterey", 21),
    ("ventura", 22),
    ("sonoma", 23),
    ("sequoia", 24),
    ("tahoe", 26),
)
# [macOS 최종 폴백] evermeet.cx 정적 빌드 (Homebrew bottle 전멸 시).
# evermeet.cx가 DNS로 안 풀리는 환경도 있으므로 redirector(getrelease) +
# 버전별 직링크를 순서대로 시도한다. universal2 바이너리는 arm64·x86_64
# (Rosetta2) 모두에서 실행된다. 외부망 차단 환경에서는 전부 실패할 수
# 있으며, 그 경우 격리 캐시는 비게 된다 (시스템 복사는 §6 금지).
_FFMPEG_EVERMEET_URLS = (
    "https://evermeet.cx/ffmpeg/getrelease/ffmpeg/zip",
    "https://evermeet.cx/ffmpeg/ffmpeg-7.1.1.zip",
    "https://evermeet.cx/ffmpeg/ffmpeg-7.0.2.zip",
)


def _macos_buildnum():
    """실행 중 macOS의 Darwin major 번호 — bottle 호환 상한 판정용.

    예: macOS 15.7.4 → platform.release() '24.6.0' → 24.
    판별 실패 시 None (호환 필터 생략 — 기존 동작 유지).
    """
    try:
        return int(str(platform.release()).split(".")[0])
    except (ValueError, IndexError):
        return None


def _macos_bottle_keys(files=None):
    """현재 아키텍처에 맞는 Homebrew bottle 키 목록 (우선순위순).

    formulae.brew.sh 응답의 실제 bottle 키에서 arch prefix로 매치한다 —
    OS 버전→키 하드코딩 테이블을 쓰지 않으므로 신형 macOS에도 내성.
    `files=None`이면 이 머신의 arch prefix 단일 키로 폴백(오프라인 안전).
    """
    arch = platform.machine()  # 'arm64' or 'x86_64'
    prefix = _MAC_BOTTLE_ARCH_PREFIX.get(arch, "arm64_")
    if not files:
        return [prefix + "sonoma", prefix.rstrip("_")]
    candidates = [k for k in files if k.startswith(prefix) and "linux" not in k]
    # [호환성] 실행 중 OS(Darwin major)보다 새 SDK로 빌드된 bottle은 dyld
    # 심볼 에러로 실행 불가 → 호환 키만 남기고, 그 중 최신 세대부터 시도.
    buildnum = _macos_buildnum()

    def _gen_buildnum(key):
        low = key.lower()
        for gen, num in _MAC_BOTTLE_BUILDNUM_ORDER:
            if gen in low:
                return num
        return None

    if buildnum is not None:
        compat = [k for k in candidates if (_gen_buildnum(k) or 0) <= buildnum]
        if compat:
            candidates = compat
    # 최신 세대부터 (번호 내림차순), 미지의 키(golden_gate 등)는 번호 미상이므로
    # 실제 실행 검증(_verify_ffmpeg) 이후 순위로 — 호환 목록 뒤에 배치.
    known = [k for k in candidates if _gen_buildnum(k) is not None]
    unknown = [k for k in candidates if _gen_buildnum(k) is None]
    known.sort(key=lambda k: _gen_buildnum(k), reverse=True)
    return known + unknown



def ensure_ffmpeg(log=None, force=False):
    """ffmpeg 자동 수급 — 앱 전용 격리 캐시 단일 경로 (v3.8.0).

    [퍼사드 함수] 외부(pot_provider 등)에서 호출하는 단일 진입점.
    성공 시 None, 실패 시 오류 문자열.

    OS별 처리 (시스템 PATH/패키지 매니저 참조 없음):
    - Windows: 캐시 → GitHub GyanD/codexffmpeg zip 다운로드
    - macOS: 캐시 → Homebrew bottle HTTP 직접 다운로드
    - Linux: 캐시 → johnvansickle.com 정적 빌드 다운로드
    """
    log = _logcb(log)
    log(emit_component("DEPS", "RUN", "FFMP", "checking..."))
    try:
        # 1. 로컬 격리 캐시 확인
        cached = ffmpeg_exe()
        if cached and not force:
            if _verify_ffmpeg(cached):
                _wire_ffmpeg_path(os.path.dirname(cached))
                log(emit_component("DEPS", "OK", "FFMP", "ok"))
                return None
            log(emit_component("DEPS", "WARN", "FFMP", f"cached not working ({cached})"))
            # 파손된 캐시는 제거 후 재수급
            dest = os.path.join(config.writable_base(), FFMPEG_DIRNAME)
            _rmtree(dest)

        # 2. OS별 정적 바이너리 수급
        return _ensure_ffmpeg_by_platform(log, force)
    except Exception as e:
        return f"{type(e).__name__}: {e}"

def _ensure_ffmpeg_by_platform(log, force):
    """플랫폼에 따라 적절한 전략 함수에 위임 (전략 패턴)."""
    platform = sys.platform
    if platform == "win32":
        return _ensure_ffmpeg_windows(log, force)
    elif platform == "darwin":
        return _ensure_ffmpeg_macos(log, force)
    elif platform.startswith("linux"):
        return _ensure_ffmpeg_linux(log, force)
    else:
        return f"Unsupported OS: {platform}"


def _ensure_ffmpeg_windows(log, force):
    """Windows용 ffmpeg 자동 수급 - GitHub GyanD/codexffmpeg 정적 zip 다운로드.

    [v3.8.0 격리] 시스템 PATH 참조 없음 — 캐시는 ensure_ffmpeg 선검.
    """
    dest = os.path.join(config.writable_base(), FFMPEG_DIRNAME)
    bin_dir = os.path.join(dest, "bin")
    exe_path = os.path.join(bin_dir, "ffmpeg.exe")

    # GitHub에서 다운로드
    os.makedirs(dest, exist_ok=True)
    log(emit_component("DEPS", "RUN", "FFMP", "downloading..."))

    with tempfile.TemporaryDirectory(prefix="cz_ffmpeg_") as td:
        zp = _download(FFMPEG_RELEASE_URL, os.path.join(td, "ffmpeg.zip"), log, "ffmpeg")
        _extract_zip(zp, dest, log, "ffmpeg", promote_single_root=True)

    if os.path.isfile(exe_path):
        _wire_ffmpeg_path(bin_dir)
        log(emit_component("DEPS", "OK", "FFMP", "ok"))
        return None

    return "ffmpeg.exe not found after extract"


def _ensure_ffmpeg_macos(log, force):
    """맥용 ffmpeg 자동 수급 - Homebrew bottle HTTP 직접 다운로드 (v3.8.0).

    [격리] `brew` 서브프로세스 실행 철폐 — formulae.brew.sh API에서 bottle
    tar.gz URL을 받아 SHA-256 검증 후 직접 수급한다 (시스템 무간섭).
    """
    dest = os.path.join(config.writable_base(), FFMPEG_DIRNAME)

    try:
        log(emit_component("DEPS", "RUN", "FFMP", "downloading (Homebrew bottle)..."))
        with urllib.request.urlopen(_FFMPEG_BREW_API, timeout=15) as resp:
            data = json.load(resp)

        bottle = data.get("bottle", {}).get("stable", {})
        files = bottle.get("files", {})

        keys = _macos_bottle_keys(files)
        selected = None
        for key in keys:
            if key in files:
                selected = files[key]
                break

        if not selected:
            return "no compatible Homebrew bottle for this macOS version/arch"

        # 후보 키를 호환 순서대로 전부 시도한다 (SHA 불일치·실행 불가
        # bottle은 다음 후보로 폴백 — Tahoe 빌드의 구형 OS dyld abort 대응).
        # [인증] ghcr.io blob 다운로드는 Bearer 토큰 필수 — _http_get이 자동 처리.
        last_err = None
        for key in keys:
            entry = files.get(key) or {}
            url = entry.get("url")
            sha256 = entry.get("sha256")
            if not url:
                last_err = "Homebrew bottle URL missing"
                continue
            try:
                with tempfile.TemporaryDirectory(prefix="cz_ffmpeg_") as td:
                    tar_path = os.path.join(td, "ffmpeg.tar.gz")
                    with _http_get(url, timeout=60) as resp, open(tar_path, "wb") as f:
                        total = int(resp.headers.get("Content-Length") or 0)
                        done = 0
                        last_mb = -1
                        while True:
                            chunk = resp.read(1024 * 512)
                            if not chunk:
                                break
                            f.write(chunk)
                            done += len(chunk)
                            mb = done // (1024 * 1024)
                            if total >= 8 * 1024 * 1024 and mb != last_mb and mb % 2 == 0:
                                last_mb = mb
                                pct = f" ({done * 100 // total}%)" if total else ""
                                log(emit_component("DEPS", "RUN", "FFMP", f"ffmpeg [{key}] {mb} MB{pct}"), True)
                    if total and done != total:
                        last_err = f"ffmpeg [{key}] download incomplete"
                        continue
                    log(emit_component("DEPS", "OK", "FFMP", f"ffmpeg [{key}] done ({done / 1048576:.1f} MB)"))

                    if sha256:
                        got = _sha256(tar_path)
                        if got != sha256:
                            last_err = f"ffmpeg bottle hash mismatch [{key}]"
                            continue
                        log(emit_component("DEPS", "OK", "FFMP", "SHA-256 ok"))

                    log(emit_component("DEPS", "RUN", "FFMP", "extracting..."))
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
                        last_err = f"tar extraction failed [{key}]"
                        continue

                    # bottle 추출 구조에서 ffmpeg 검색
                    ffmpeg_src = None
                    ffmpeg_bin_dir = None
                    for root, dirs, names in os.walk(dest):
                        if "ffmpeg" in names:
                            candidate = os.path.join(root, "ffmpeg")
                            if os.path.isfile(candidate):
                                ffmpeg_src = candidate
                                ffmpeg_bin_dir = root
                                break

                    if ffmpeg_src and ffmpeg_bin_dir:
                        # 원래 디렉토리 구조를 유지하고 PATH에 추가
                        _wire_ffmpeg_path(ffmpeg_bin_dir)
                        # 설치 확인 — 실패하면 다음 후보 키로 폴백
                        if _verify_ffmpeg(ffmpeg_src):
                            log(emit_component("DEPS", "OK", "FFMP", "ok"))
                            return None
                        last_err = (
                            f"ffmpeg [{key}] not runnable on this macOS — trying older bottle"
                        )
                        log(emit_error_warn("DEPS", "FFMP", "binary incompatible", "retry mirror (1/3)"))
                        if os.path.exists(dest):
                            shutil.rmtree(dest, ignore_errors=True)
                        continue
                    last_err = f"ffmpeg exe not found after extract [{key}]"
            except Exception as e:  # noqa: BLE001 — 후보별 폴백
                last_err = f"ffmpeg [{key}] install failed: {type(e).__name__}"
                continue
        # bottle 전멸 — evermeet.cx 정적 빌드로 최종 폴백 (실측 2026-09:
        # formulae 9.x arm64 bottle 3종 전부 현행 15.7.4에서 dyld abort).
        ever_err = _ensure_ffmpeg_macos_static(log, dest)
        if ever_err is None:
            return None
        return emit_error_standard("DEPS", "FFMP", "all mirrors exhausted", "check network (F12)", status="FAIL", is_error=True)
    except Exception as e:
        return f"{type(e).__name__}: {e}"


def _fetch_url(url, dest_path, timeout=60):
    """단일 파일 다운로드 — 302 redirector(getrelease) 추적 지원.

    _http_get(단일 GET, 리다이렉트 미추적)과 달리 표준 opener로 리다이렉트를
    따라간다. evermeet.cx getrelease가 302를 반환하므로 정적 폴백 전용.
    """
    opener = urllib.request.build_opener(urllib.request.HTTPRedirectHandler())
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with opener.open(req, timeout=timeout) as resp, open(dest_path, "wb") as f:
        while True:
            chunk = resp.read(1024 * 512)
            if not chunk:
                break
            f.write(chunk)


def _ensure_ffmpeg_macos_static(log, dest):
    """macOS 최종 폴백 — evermeet.cx 정적 빌드 단일 바이너리 수급.

    bottle 전멸(dyld 실행 불가) 시에만 진입. 3종 URL을 순서대로 시도하고,
    실행 검증(_verify_ffmpeg) 통과본만 캐시한다.
    성공 시 None, 실패 시 오류 문자열.
    """
    try:
        from chzzktube.infra.platform import is_windows as _is_win

        if _is_win():
            return "static fallback is macOS-only"
        urls = _FFMPEG_EVERMEET_URLS
        last_err = None
        for url in urls:
            try:
                log(emit_component("DEPS", "RUN", "FFMP", f"downloading (static) {os.path.basename(url) or 'latest'}..."))
                with tempfile.TemporaryDirectory(prefix="cz_ffmpeg_") as td:
                    zp = os.path.join(td, "ffmpeg.zip")
                    # redirector(getrelease)는 302를 반환하므로 _http_get이 아닌
                    # 리다이렉트 추적 opener 사용
                    _fetch_url(url, zp)
                    _extract_zip(zp, dest, log, "ffmpeg", promote_single_root=True)
                cand = os.path.join(dest, "ffmpeg")
                if not os.path.isfile(cand):
                    for root, _dirs, names in os.walk(dest):
                        if "ffmpeg" in names:
                            cand = os.path.join(root, "ffmpeg")
                            break
                if os.path.isfile(cand):
                    try:
                        os.chmod(cand, 0o755)
                    except OSError:
                        pass
                    _wire_ffmpeg_path(os.path.dirname(cand))
                    if _verify_ffmpeg(cand):
                        log(emit_component("DEPS", "OK", "FFMP", "ok (static)"))
                        return None
                    last_err = f"static {os.path.basename(url)} not runnable"
                    continue
                last_err = f"static {os.path.basename(url)} missing binary"
            except Exception as e:  # noqa: BLE001 — URL별 폴백
                last_err = f"static {os.path.basename(url)} failed: {type(e).__name__}"
                continue
        return last_err or "static fallback failed"
    except Exception as e:
        return f"{type(e).__name__}: {e}"
    except Exception as e:
        return f"{type(e).__name__}: {e}"

def ffmpeg_exe():
    """ffmpeg 실행 파일 경로 — 앱 전용 격리 캐시 단일 참조 (v3.8.0).

    [격리 원칙] 시스템 PATH 폴백(shutil.which) 철폐 — writable_base()/ffmpeg
    캐시에 없으면 None을 반환한다 (ensure_ffmpeg가 수급을 담당).
    """
    from chzzktube.infra.platform import exe_suffix

    exe_name = f"ffmpeg{exe_suffix()}"
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
    return None


def _ensure_ffmpeg_linux(log, force):
    """리눅스용 ffmpeg 자동 수급 - 정적 빌드 다운로드 (v3.8.0).

    [격리] 시스템 패키지 매니저(apt/dnf/pacman) 서브프로세스 철폐 —
    johnvansickle.com의 정적 빌드를 어떤 배포판에서도 직접 수급한다.
    """
    dest = os.path.join(config.writable_base(), FFMPEG_DIRNAME)

    # 정적 빌드 다운로드 (johnvansickle.com)
    try:
        log(emit_component("DEPS", "RUN", "FFMP", "downloading (static build)..."))
        url = "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"
        with tempfile.TemporaryDirectory(prefix="cz_ffmpeg_") as td:
            tar_path = os.path.join(td, "ffmpeg.tar.xz")
            _download(url, tar_path, log, "ffmpeg", is_status=True)

            log(emit_component("DEPS", "RUN", "FFMP", "extracting..."))
            if os.path.exists(dest):
                shutil.rmtree(dest, ignore_errors=True)
            os.makedirs(dest, exist_ok=True)

            # tar.xz 압축 해제
            import tarfile
            with tarfile.open(tar_path, "r:xz") as tar:
                # ffmpeg와 ffprobe만 추출
                for member in tar.getmembers():
                    if member.name.endswith("/ffmpeg") or member.name.endswith("/ffprobe"):
                        member.name = os.path.basename(member.name)
                        tar.extract(member, dest)

            # 실행 권한 보장
            ffmpeg_bin = os.path.join(dest, "ffmpeg")
            if os.path.isfile(ffmpeg_bin):
                os.chmod(ffmpeg_bin, 0o755)
                if _verify_ffmpeg(ffmpeg_bin):
                    _wire_ffmpeg_path(dest)
                    log(emit_component("DEPS", "OK", "FFMP", "ok"))
                    return None

        return "ffmpeg binary not found after extract"
    except Exception as e:
        return f"linux ffmpeg install failed: {type(e).__name__}: {e}"


def _wire_ffmpeg_path(bin_dir):
    """수급/캐시된 ffmpeg bin을 프로세스 PATH 선두에 연결.

    media.py·downloader.py가 subprocess로 bare 'ffmpeg'를 호출하므로, 이 세션의
    자식 프로세스가 격리 캐시의 수급본을 즉시 사용하게 한다. [격리] 연결되는
    경로는 항상 writable_base()/ffmpeg 하위뿐이다 — 시스템 설치물은 대상 아님.
    """
    try:
        if os.path.isdir(bin_dir):
            path_env = os.environ.get("PATH", "")
            parts = path_env.split(os.pathsep) if path_env else []
            if bin_dir not in parts:
                os.environ["PATH"] = os.pathsep.join([bin_dir] + parts)
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


