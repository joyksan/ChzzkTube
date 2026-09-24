### components.py - ffmpeg runtime manager
"""ffmpeg 자동 수급/관리 전용 모듈 — 앱 전용 격리 캐시 (v3.8.0).

*  [격리 원칙] 시스템 PATH 탐색(shutil.which)·OS 패키지 매니저(brew install,
   apt-get 등) 서브프로세스 호출 완전 철폐. 오직 writable_base()/ffmpeg/
   단일 캐시만 검사하고, 없으면 아카이브를 직접 수급한다.
*  [stdlib 순수성] 의존성 수급 모듈은 순수 파이썬 기반이다. 7z 모듈을 추가로
   끌어오지 않기 위해 zip/tar만 타겟팅한다 (.7z 자산은 후보에서 제외).
*  [동적 버전] 동적 모듈은 생명주기 갱신을 위해 항상 최신 릴리스를 받는다.
   버전 하드코딩 금지 — GitHub API latest + checksums.sha256로 재해석.
*  Windows/Linux: BtbN/FFmpeg-Builds GitHub Release (zip / tar.xz, SHA-256 필수)
*  macOS: Homebrew formulae API (bottle tar.gz, SHA-256 필수 + _verify_ffmpeg 실측 판정)

[전수조사 정리 2026-09-04] 구 설계(Hitomi Downloader style 전체 구성요소
자동수급: yt-dlp 휠 / bgutil 플러그인 / pot-pack / 라이브팩)는
main.py에 연결된 적이 없는 죽은 코드였음 — 실제 의존 흐름은
앱 전용 캐시(yt-dlp 바이너리 / ffmpeg) + pot_provider(bgutil 서버 빌드) + 본 모듈.
"""
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

import chzzktube.core.config as config
from chzzktube.core import (
    CONNECT_TIMEOUT,
    READ_TIMEOUT,
    DOWNLOAD_TIMEOUT,
    SHORT_API_TIMEOUT,
    TEMP_FILE_MODE,
    EXECUTABLE_FILE_MODE,
)
from chzzktube.core.log_emitter import emit_component, emit_error_standard, emit_error_warn
from chzzktube.core.raw_log import log_f12_cli, log_f12_net
from chzzktube.ui import ProgressBar

_UA = "ChzzkTube-Components/1.0"


def components_root():
    """구성요소 전개 루트 — SSOT: writable_base()/components 단일 경로 (v3.8.2).

    [SSOT 원칙] frozen과 source 모두 writable_base() 하위를 사용.
    - frozen 시 <exe>/components 경로 참조 완전 제거
    - 환경변수 CHZZKTUBE_COMPONENTS_DIR로만 오버라이드
    """
    env = os.environ.get("CHZZKTUBE_COMPONENTS_DIR")
    if env:
        return env
    return os.path.join(config.writable_base(), "components")



def _logcb(log):
    return log if callable(log) else (lambda *a, **k: None)


def _http_get(url, timeout=READ_TIMEOUT):
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
    with urllib.request.urlopen(url, timeout=SHORT_API_TIMEOUT) as resp:
        data = json.load(resp)
    return data.get("token")


def _download(url, dest, log=None, label="", expected_sha256=None):
    """파일 다운로드(진행 바 포함). 성공 시 dest 경로 반환.

    ProgressBar를 사용하여 raw_log 히스토리에 진행 바를 기록 (상태 줄 덮어쓰기 방지).
    """
    # log 함수가 없으면 기본 raw_log 사용
    log_func = log if callable(log) else None

    with ProgressBar(component=label or os.path.basename(url), log_func=log_func) as bar:
        bar.start()
        tmp = dest + ".part"
        req = urllib.request.Request(url, headers={"User-Agent": _UA})

        # ghcr.io 토큰 처리
        if "ghcr.io" in url:
            try:
                token = _ghcr_token("repository:homebrew/core/ffmpeg:pull")
                req.headers["Authorization"] = f"Bearer {token}"
            except Exception:
                pass

        hasher = hashlib.sha256() if expected_sha256 else None
        try:
            # 임시 파일을 0o600 권한으로 생성 (소유자만 읽기/쓰기)
            with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT) as resp:
                # Set per-read timeout
                try:
                    sock = resp.fp.raw._sock
                    if sock is not None:
                        sock.settimeout(READ_TIMEOUT)
                except AttributeError:
                    pass

                total = int(resp.headers.get("Content-Length", 0))
                downloaded = 0

                with open(tmp, "wb", opener=lambda p, f: os.open(p, f, TEMP_FILE_MODE)) as f:
                    while True:
                        chunk = resp.read(1024 * 512)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if hasher is not None:
                            hasher.update(chunk)
                        bar.update(downloaded, total)

            # SHA-256 검증
            if hasher is not None:
                computed_sha256 = hasher.hexdigest()
                if computed_sha256 != expected_sha256:
                    raise ValueError(f"SHA256 mismatch: {computed_sha256} != {expected_sha256}")

            os.replace(tmp, dest)
            bar.finish("completed")
            return dest

        except BaseException:
            # 정리
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise



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
    import zipfile
    
    # 사전 검증: zip 파일 무결성 확인
    try:
        with zipfile.ZipFile(zip_path) as zf:
            bad_file = zf.testzip()
            if bad_file is not None:
                raise zipfile.BadZipFile(f"Corrupted zip entry: {bad_file}")
    except zipfile.BadZipFile as e:
        log(emit_component("DEPS", "FAIL", "DEPS", f"{label} zip validation failed: {e}"))
        raise
    
    tmp = dest_dir + ".tmp"
    _rmtree(tmp)
    os.makedirs(os.path.dirname(tmp) or ".", exist_ok=True)
    try:
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(tmp)
    except zipfile.BadZipFile as e:
        _rmtree(tmp)
        log(emit_component("DEPS", "FAIL", "DEPS", f"{label} zip extraction failed: {e}"))
        raise
    
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
# [v3.8.4 동적 수급] 하드코딩 릴리스 URL 전면 폐기.
# Windows/Linux: BtbN/FFmpeg-Builds GitHub Release API + checksums.sha256
# macOS: Homebrew formulae API (bottle tar.gz) — cellar 메타데이터로 스킵하지 않고 실측으로 판정
BTBN_RELEASE_API = "https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/latest"
BTBN_CHECKSUM_ASSET = "checksums.sha256"
BTBN_UA = "ChzzkTube-Provisioner/1.0"
_SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")


def _normalize_arch(machine=None):
    """platform.machine() → canonical arch token ('amd64' | 'arm64').

    [stdlib 전용] 미지원 아키텍처는 조용히 추측하지 않고 ValueError로 중단한다.
    """
    mach = (machine or platform.machine() or "").lower()
    if mach in ("amd64", "x86_64", "x64"):
        return "amd64"
    if mach in ("arm64", "aarch64"):
        return "arm64"
    raise ValueError(f"unsupported architecture: {mach or 'unknown'}")


def _parse_btbn_checksums(manifest_text, asset_name):
    """checksums.sha256 텍스트에서 asset_name의 SHA-256을 추출.

    [실측 계약] GitHub REST API의 release asset 응답에는 개별 파일의 SHA-256
    digest 필드가 존재하지 않는다. 따라서 BtbN 릴리스가 함께 게시하는
    `checksums.sha256` 텍스트 자산을 받아 정확한 basename 매칭으로만 검증한다.
    """
    if not manifest_text or not asset_name:
        raise ValueError("checksum manifest or asset name missing")
    for raw in manifest_text.splitlines():
        parts = raw.strip().split()
        if len(parts) < 2:
            continue
        digest, name = parts[0].strip().lower(), parts[-1].strip().lstrip("*")
        if name == asset_name and _SHA256_HEX_RE.match(digest):
            return digest
    raise ValueError(f"valid SHA-256 for {asset_name} not found in manifest")


def _fetch_btbn_checksums(url, timeout=SHORT_API_TIMEOUT):
    """checksums.sha256 자산 텍스트 다운로드 (stdlib only)."""
    req = urllib.request.Request(url, headers={"User-Agent": BTBN_UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _select_btbn_asset(assets, arch_token, ext):
    """BtbN 릴리스 자산 목록에서 정적 GPL 아카이브 1개를 선택.

    [실측 명명 규칙] BtbN 자산은 `ffmpeg-<build>-win64-gpl.zip` 또는
    `ffmpeg-<build>-linux64-gpl.tar.xz` 형태로, `-gpl.`/`-gpl-`가 모두 나온다.
    따라서 `gpl` 토큰만 확인하고 `shared`를 배제한다.

    제외 규칙: shared(dylib 동반), debug/symbols/pdb, .7z(7z 의존성 회피),
    이외 아키텍처 토큰.
    """
    for asset in assets:
        name = asset.get("name", "")
        low = name.lower()
        if "gpl" not in low or not low.endswith(ext):
            continue
        if "shared" in low or arch_token not in low:
            continue
        if any(tok in low for tok in ("debug", "symbols", "pdb")):
            continue
        return asset
    return None


def _resolve_btbn_ffmpeg(timeout=SHORT_API_TIMEOUT):
    """BtbN 최신 릴리스에서 (에셋 + 체크섬) 단일 트랜잭션 해석.

    반환: component/version/asset_name/url/sha256/archive_type/platform/architecture
    """
    system = platform.system().lower()
    arch = _normalize_arch()
    if system == "windows":
        arch_token = "win64" if arch == "amd64" else "winarm64"
        ext, archive_type = ".zip", "zip"
    elif system == "linux":
        arch_token = "linux64" if arch == "amd64" else "linuxarm64"
        ext, archive_type = ".tar.xz", "tar.xz"
    else:
        raise ValueError(f"BtbN does not provide builds for: {system}")

    req = urllib.request.Request(BTBN_RELEASE_API, headers={"User-Agent": BTBN_UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        release = json.load(resp)

    assets = release.get("assets", []) or []
    target = _select_btbn_asset(assets, arch_token, ext)
    if target is None:
        raise RuntimeError(f"no BtbN {arch_token} gpl asset for {system}")

    checksum_asset = next(
        (a for a in assets if a.get("name") == BTBN_CHECKSUM_ASSET), None
    )
    if checksum_asset is None:
        raise RuntimeError("BtbN checksums.sha256 manifest missing from release")

    manifest = _fetch_btbn_checksums(
        checksum_asset.get("browser_download_url", ""), timeout=timeout
    )
    digest = _parse_btbn_checksums(manifest, target.get("name", ""))

    return {
        "component": "ffmpeg",
        "version": release.get("tag_name") or "latest",
        "asset_name": target.get("name", ""),
        "url": target.get("browser_download_url", ""),
        "sha256": digest,
        "archive_type": archive_type,
        "platform": system,
        "architecture": arch,
    }


def _safe_extract(archive_path, archive_type, dest_dir):
    """stdlib 전용 안전 압축 해제 — Zip Slip / tar traversal 차단.

    * zip:  멤버 경로 정규화 후 dest_dir 밖으로 벗어나면 ValueError
    * tar*: Python 3.12+ `filter="data"` 로 절대경로/상위경로/링크 이탈 차단
    """
    dest = Path(dest_dir).resolve()
    dest.mkdir(parents=True, exist_ok=True)
    if archive_type == "zip":
        with zipfile.ZipFile(archive_path) as zf:
            for member in zf.infolist():
                target = (dest / member.filename).resolve()
                if target != dest and dest not in target.parents:
                    raise ValueError(f"path traversal in zip: {member.filename}")
            zf.extractall(dest)
        return dest
    if archive_type in ("tar.xz", "tar.gz", "tar"):
        mode = {"tar.xz": "r:xz", "tar.gz": "r:gz", "tar": "r:"}[archive_type]
        with tarfile.open(archive_path, mode) as tf:
            try:
                # Python 3.12+ : filter="data" 가 절대경로/상위경로/링크 이탈을
                # tarfile.InsideDestinationError 등 FilterError로 차단한다.
                # 호출자 계약은 ValueError 단일 예외이므로 정규화해 올린다.
                tf.extractall(dest, filter="data")
            except TypeError:  # Python < 3.12 — filter 파라미터 부재
                for member in tf.getmembers():
                    target = (dest / member.name).resolve()
                    if target != dest and dest not in target.parents:
                        raise ValueError(f"path traversal in tar: {member.name}")
                tf.extractall(dest)
            except tarfile.TarError as e:
                raise ValueError(f"unsafe tar archive: {e}") from e
        return dest
    raise ValueError(f"unsupported archive type: {archive_type}")


def _locate_binaries(root):
    """추출 트리에서 ffmpeg/ffprobe 실행 파일 탐색 (중첩 Cellar/bin 대응)."""
    found = {}
    for path in Path(root).rglob("*"):
        if not path.is_file():
            continue
        stem = path.stem.lower()
        if stem in ("ffmpeg", "ffprobe") and stem not in found:
            found[stem] = path
    return found


def _atomic_install(binaries, dest_dir):
    """추출 바이너리를 dest_dir/bin 으로 원자 교체 (기존 버전 보존).

    Windows는 기존 디렉터리 rename 시 PermissionError/FileExistsError가
    나므로 incoming → backup → 교체 순서를 쓰고, 실패 시 backup을 되돌린다.
    """
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    bin_dir = dest / "bin"
    incoming = dest / "bin_incoming"
    backup = dest / "bin_backup"
    suffix = _exe_suffix()

    _rmtree(str(incoming))
    _rmtree(str(backup))
    incoming.mkdir(parents=True, exist_ok=True)

    for stem, src in binaries.items():
        target = incoming / f"{stem}{suffix}"
        shutil.copy2(src, target)
        if os.name != "nt":
            target.chmod(target.stat().st_mode | 0o755)
            try:
                subprocess.run(
                    ["xattr", "-dr", "com.apple.quarantine", str(target)],
                    capture_output=True, check=False,
                )
            except Exception:
                pass

    if bin_dir.exists():
        try:
            os.replace(str(bin_dir), str(backup))
        except OSError:
            _rmtree(str(bin_dir))
    installed = False
    try:
        os.replace(str(incoming), str(bin_dir))
        installed = True
    finally:
        if not installed and backup.exists():
            try:
                os.replace(str(backup), str(bin_dir))
            except OSError:
                pass
    _rmtree(str(backup))
    return bin_dir
_FFMPEG_BREW_API = "https://formulae.brew.sh/api/formula/ffmpeg.json"
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
_FFMPEG_BREW_API = "https://formulae.brew.sh/api/formula/ffmpeg.json"


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
    - Windows: 캐시 → BtbN GitHub latest (win64/winarm64 static gpl zip)
    - macOS: 캐시 → Homebrew formulae bottle (tar.gz, _verify_ffmpeg 실측 판정)
    - Linux: 캐시 → BtbN GitHub latest (linux64/linuxarm64 static gpl tar.xz)
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

def _record_provision_plan(plan, install_path):
    """수급 결과를 provisioning manifest에 기록 (감사 가능성 확보).

    [실측 계약] manifest에는 `record_install` 같은 헬퍼가 없다.
    `ProvisionManifest.load/save` + `ComponentRecord` + `update_component`가
    유일한 공식 API이므로 이를 그대로 사용한다. 기록 실패는 본 수급 흐름을
    깨뜨리지 않는다 — best-effort.
    """
    try:
        from chzzktube.infra.provisioning.manifest import (
            ComponentRecord, ProvisionManifest,
        )

        base = Path(config.writable_base())
        manifest = ProvisionManifest.load(base)
        manifest.update_component(ComponentRecord(
            name=plan.get("component", "ffmpeg"),
            version=plan.get("version", "latest"),
            source=plan.get("platform", "github"),
            mirror=plan.get("asset_name", ""),
            install_path=os.path.relpath(install_path, base),
            verified_at=time.time(),
            verify_version=plan.get("architecture", ""),
            sha256=plan.get("sha256", ""),
        ))
        manifest.save(base)
    except Exception:
        pass


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
    """Windows용 ffmpeg 자동 수급 — BtbN 최신 릴리스 동적 해석 (v3.8.4).

    [동적 버전] 하드코딩 릴리스 태그 없음. GitHub API latest + checksums.sha256
    으로 에셋·해시를 매 트랜잭션 재해석한다. .7z 자산은 7z 의존성 회피를 위해
    후보에서 제외하고 static(비 shared) GPL zip만 채택한다.

    [v3.8.0 격리] 시스템 PATH 참조 없음 — 캐시는 ensure_ffmpeg 선검.
    """
    dest = Path(config.writable_base()) / FFMPEG_DIRNAME
    exe_name = "ffmpeg.exe"

    max_retries = 3
    last_err = None
    for attempt in range(max_retries):
        if attempt > 0:
            log(emit_component("DEPS", "WARN", "FFMP", f"retry {attempt}/{max_retries}"))
            time.sleep(2 ** attempt)

        try:
            log(emit_component("DEPS", "RUN", "FFMP", "resolving latest (github)..."))
            plan = _resolve_btbn_ffmpeg()
            log(emit_component("DEPS", "RUN", "FFMP", f"downloading {plan['version']}..."))

            os.makedirs(dest, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix="cz_ffmpeg_") as td:
                archive = _download(
                    plan["url"], os.path.join(td, plan["asset_name"]),
                    log, "ffmpeg", expected_sha256=plan["sha256"],
                )
                staging = _safe_extract(archive, plan["archive_type"], Path(td) / "x")
                binaries = _locate_binaries(staging)

            if "ffmpeg" not in binaries:
                last_err = f"ffmpeg binary not found in {plan['asset_name']}"
                log(emit_error_warn("DEPS", "FFMP", "binary missing", "retry mirror (1/3)"))
                continue

            bin_dir = _atomic_install(binaries, dest)
            exe_path = bin_dir / exe_name
            if not exe_path.is_file():
                last_err = "ffmpeg.exe not installed"
                continue
            if not _verify_ffmpeg(str(exe_path)):
                last_err = "ffmpeg.exe install verification failed"
                continue

            _wire_ffmpeg_path(str(bin_dir))
            log(emit_component("DEPS", "OK", "FFMP", f"ok ({plan['version']})"))
            _record_provision_plan(plan, str(exe_path))
            return None
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
            log(emit_error_warn("DEPS", "FFMP", "download failed", f"{type(e).__name__} (F12)"))

    return f"ffmpeg install failed after {max_retries} attempts: {last_err}"


def _normalize_bottle_binaries(extracted_dir, cache_dir):
    """Homebrew Bottle의 중첩 bin 디렉터리를 앱 격리 캐시로 정규화.

    [v3.8.4] _locate_binaries/_atomic_install로 대체되었지만, 외부 호출/계약
    테스트 호환을 위해 얇은 래퍼로 유지한다. ffmpeg·ffprobe 둘 다 있어야 한다.
    """
    found = _locate_binaries(extracted_dir)
    if "ffmpeg" not in found:
        return None
    try:
        bin_dir = _atomic_install(found, cache_dir)
    except OSError:
        return None
    return bin_dir / "ffmpeg"


def _ffmpeg_progress_event(text):
    """Bottle 진행 틱 → 진행형 LogEvent (component_id=ffmpeg, is_progress=True).

    TUI/F12 브리지가 동일 라인 제자리 갱신을 수행하도록 진행 메타데이터를
    반드시 실어 보낸다 (§3.7-5 다중 컴포넌트 갱신형).
    """
    return emit_component(
        "DEPS", "RUN", "FFMP", text, component_id="ffmpeg", is_progress=True
    )


def _ffmpeg_done_event(text):
    """Bottle 진행 종료 → 히스토리 확정 로그 (is_progress=False)."""
    return emit_component(
        "DEPS", "OK", "FFMP", text, component_id="ffmpeg", is_progress=False
    )


def _write_bottle_payload(url, dest_path, expected_sha256):
    """Homebrew bottle 페이로드 기록 + SHA-256 강제 검증.

    [v3.9.0] 기존 생략 주석 구간의 누락된 다운로드 단계를 복원.
    ghcr.io 토큰 인증이 필요하므로 _http_get 경유. SHA 없으면 채택 금지
    (무검증 수급 차단, §5-28). 해시 불일치는 ValueError로 호출자에게 전달.
    """
    hasher = hashlib.sha256()
    with _http_get(url, timeout=DOWNLOAD_TIMEOUT) as resp, open(dest_path, "wb") as f:
        while True:
            chunk = resp.read(1024 * 512)
            if not chunk:
                break
            f.write(chunk)
            hasher.update(chunk)
    if hasher.hexdigest() != (expected_sha256 or "").lower():
        raise ValueError(f"SHA256 mismatch for bottle: {url}")


def _ensure_ffmpeg_macos(log, force):
    """맥용 ffmpeg 자동 수급 — Bottle 내부 라이브러리 경로 바인딩 및 호스트 승격 안전망."""
    dest = os.path.join(config.writable_base(), FFMPEG_DIRNAME)

    try:
        log(emit_component("DEPS", "RUN", "FFMP", "resolving (homebrew formula)..."))
        with urllib.request.urlopen(_FFMPEG_BREW_API, timeout=SHORT_API_TIMEOUT) as resp:
            data = json.load(resp)

        bottle = data.get("bottle", {}).get("stable", {})
        files = bottle.get("files", {})
        keys = _macos_bottle_keys(files)

        last_err = None
        for key in keys:
            entry = files.get(key) or {}
            url = entry.get("url")
            sha256 = entry.get("sha256")
            if not url or not sha256:
                continue

            try:
                with tempfile.TemporaryDirectory(prefix="cz_ffmpeg_") as td:
                    tar_path = os.path.join(td, "ffmpeg.tar.gz")
                    _write_bottle_payload(url, tar_path, sha256)

                    staging = _safe_extract(tar_path, "tar.gz", Path(td) / "x")
                    binaries = _locate_binaries(staging)
                    if "ffmpeg" not in binaries or "ffprobe" not in binaries:
                        continue

                    staged = str(binaries["ffmpeg"])
                    os.chmod(staged, 0o755)
                    subprocess.run(["xattr", "-dr", "com.apple.quarantine", staged], capture_output=True, check=False)

                    # [핵심 교정 1] Bottle 내부의 lib 디렉터리를 찾아 dyld 경로로 주입!
                    # 임시 폴더에 풀린 libavcodec 등을 바이너리가 인식할 수 있도록 길을 열어줍니다.
                    lib_dirs = [str(p) for p in Path(staging).rglob("lib") if p.is_dir()]
                    env_extra = {"DYLD_FALLBACK_LIBRARY_PATH": ":".join(lib_dirs)} if lib_dirs else {}

                    if not _verify_ffmpeg(staged, env_extra=env_extra):
                        last_err = f"ffmpeg [{key}] execution test failed (dyld incompatible)"
                        log(emit_error_warn("DEPS", "FFMP", "binary incompatible", "trying next bottle (F12)"))
                        continue

                    # 검증 성공 시 원자 교체 및 라이브러리 동반 복사
                    bin_dir = _atomic_install(binaries, Path(dest))
                    _wire_ffmpeg_path(str(bin_dir))
                    log(_ffmpeg_done_event(f"bottle [{key}] verified"))
                    return None

            except Exception as e:
                last_err = str(e)
                continue

        # [핵심 교정 2: 호스트 승격 구출책]
        # 모든 Bottle이 순정 상태에서 dylib 부재로 전멸했을 경우,
        # 시스템(/opt/homebrew 등)에 이미 존재하는 유효한 ffmpeg를 격리 캐시로 승격 복사!
        log(emit_error_warn("DEPS", "FFMP", "binary incompatible", "check logs (F12)"))
        host_candidates = [Path("/opt/homebrew/bin/ffmpeg"), Path("/usr/local/bin/ffmpeg")]
        for host_bin in host_candidates:
            if host_bin.is_file() and _verify_ffmpeg(host_bin):
                bin_dir = Path(dest) / "bin"
                bin_dir.mkdir(parents=True, exist_ok=True)
                target_ffmpeg = bin_dir / "ffmpeg"
                shutil.copy2(host_bin, target_ffmpeg)
                target_ffmpeg.chmod(0o755)

                host_probe = host_bin.parent / "ffprobe"
                if host_probe.is_file():
                    shutil.copy2(host_probe, bin_dir / "ffprobe")
                    (bin_dir / "ffprobe").chmod(0o755)

                _wire_ffmpeg_path(str(bin_dir))
                log(_ffmpeg_done_event(f"bootstrapped from host ({host_bin.parent})"))
                return None

        log(emit_error_standard("DEPS", "FFMP", "binary incompatible", "check logs (F12)"))
        return last_err or "no runnable bottle found"

    except Exception as e:
        return f"Homebrew formula resolve failed: {e}"


def _fetch_url(url, dest_path, timeout=60):
    """단일 파일 다운로드 — 302 redirector 추적 지원 (범용 helper).

    _http_get(단일 GET, 리다이렉트 미추적)과 달리 표준 opener로 리다이렉트를
    따라간다. 현재는 예비 유틸리티이며 수급 경로는 _download를 사용한다.
    """
    opener = urllib.request.build_opener(urllib.request.HTTPRedirectHandler())
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with opener.open(req, timeout=timeout) as resp, open(dest_path, "wb") as f:
        while True:
            chunk = resp.read(1024 * 512)
            if not chunk:
                break
            f.write(chunk)


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
    """리눅스용 ffmpeg 자동 수급 — BtbN 최신 릴리스 동적 해석 (v3.8.4).

    [동적 버전] johnvansickle 고정 amd64 URL을 폐기. GitHub API latest +
    checksums.sha256으로 linux64/linuxarm64 static GPL tar.xz를 해석한다.

    [격리] 시스템 패키지 매니저(apt/dnf/pacman) 서브프로세스 철폐 유지.
    """
    dest = Path(config.writable_base()) / FFMPEG_DIRNAME

    max_retries = 3
    last_err = None
    for attempt in range(max_retries):
        if attempt > 0:
            log(emit_component("DEPS", "WARN", "FFMP", f"retry {attempt}/{max_retries}"))
            time.sleep(2 ** attempt)

        try:
            log(emit_component("DEPS", "RUN", "FFMP", "resolving latest (github)..."))
            plan = _resolve_btbn_ffmpeg()
            log(emit_component("DEPS", "RUN", "FFMP", f"downloading {plan['version']}..."))

            os.makedirs(dest, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix="cz_ffmpeg_") as td:
                archive = _download(
                    plan["url"], os.path.join(td, plan["asset_name"]),
                    log, "ffmpeg", expected_sha256=plan["sha256"],
                )
                staging = _safe_extract(archive, plan["archive_type"], Path(td) / "x")
                binaries = _locate_binaries(staging)

            if "ffmpeg" not in binaries:
                last_err = f"ffmpeg binary not found in {plan['asset_name']}"
                log(emit_error_warn("DEPS", "FFMP", "binary missing", "retry mirror (1/3)"))
                continue

            bin_dir = _atomic_install(binaries, dest)
            exe_path = bin_dir / "ffmpeg"
            if not exe_path.is_file() or not _verify_ffmpeg(str(exe_path)):
                last_err = "ffmpeg install verification failed"
                continue

            _wire_ffmpeg_path(str(bin_dir))
            log(emit_component("DEPS", "OK", "FFMP", f"ok ({plan['version']})"))
            _record_provision_plan(plan, str(exe_path))
            return None
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
            log(emit_error_warn("DEPS", "FFMP", "download failed", f"{type(e).__name__} (F12)"))

    return f"linux ffmpeg install failed after {max_retries} attempts: {last_err}"


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

def _verify_ffmpeg(ffmpeg_path, env_extra=None):
    """ffmpeg 실행 가능 여부 검증 (dyld 에러 원인 보존).

    [F12] 실행 원문(`$ ffmpeg -version` + 출력/오류)은 log_f12_cli로만 발행한다 —
    to_tui=False 강제이므로 메인 콘솔은 오염되지 않는다.
    """
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    try:
        result = subprocess.run(
            [str(ffmpeg_path), "-version"],
            capture_output=True,
            timeout=10,
            env=env,
        )
        out = (result.stdout or b"").decode("utf-8", errors="replace")
        err = (result.stderr or b"").decode("utf-8", errors="replace")
        log_f12_cli(
            f"{ffmpeg_path} -version",
            (out + err).strip(),
            is_error=(result.returncode != 0),
        )
        return result.returncode == 0
    except Exception as e:
        log_f12_cli(f"{ffmpeg_path} -version", f"[{type(e).__name__}] {e}", is_error=True)
        return False


