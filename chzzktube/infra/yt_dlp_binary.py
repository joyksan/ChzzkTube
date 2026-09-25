"""yt-dlp 바이너리 경로 관리 모듈 (SRP: yt-dlp 실행 파일 탐색·수급·갱신만 담당).

- system PATH의 yt-dlp 최우선 사용
- 없으면 OS 표준 경로(%LOCALAPPDATA%\\ChzzkTube\\bin\\ 또는 ~/.local/bin/)에서 탐색
- 없으면 GitHub releases에서 yt-dlp 바이너리 직접 다운로드
- 업데이트는 동일 경로에 덮어쓰기
"""
import os
import sys
import platform
import shutil
import subprocess
import tempfile
import urllib.request
import json
import stat
import re
from pathlib import Path

import chzzktube.core.config as config
from chzzktube.core.log_emitter import emit_component
from chzzktube.core.raw_log import log_f12_cli, log_f12_net
from chzzktube.infra.paths import get_writable_base, is_portable, bundle_root


# ── 상수 ──────────────────────────────────────────────────────────────
YTDLP_MIN_VERSION = (2024, 1, 1)  # 최소 요구 버전
_YTDLP_FALLBACK_VER = "2024.12.19"  # GitHub API 조회 실패 시 폴백

# GitHub releases URL 템플릿
_YTDLP_RELEASE_API = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"
# Nightly builds: 플랫폼별 asset 이름 사용 (stable과 동일 패턴)
_YTDLP_NIGHTLY_BASE = "https://github.com/yt-dlp/yt-dlp-nightly-builds/releases/latest/download"


def _exe_suffix() -> str:
    """현재 OS의 실행 파일 확장자 반환."""
    return ".exe" if sys.platform == "win32" else ""


def _bin_dir() -> Path:
    """yt-dlp 바이너리가 설치될 표준 디렉터리 반환.

    Dev/Frozen 공통: get_writable_base()/bin/
    Windows: %LOCALAPPDATA%/ChzzkTube/bin/
    Unix: ~/.local/bin/
    """
    base = get_writable_base()
    return Path(base) / "bin"


def _platform_asset_name(ver: str) -> str:
    """플랫폼별 yt-dlp 배포 에셋 이름 생성."""
    system = platform.system().lower()
    machine = platform.machine().lower()
    suffix = _exe_suffix()

    if system == "windows":
        # Windows는 x86_64만 공식 지원 (arm64는 별도 빌드 필요)
        return f"yt-dlp{suffix}"
    elif system == "darwin":
        # macOS: 유니버설 바이너리(arm64+x86_64)
        return f"yt-dlp_macos{suffix}"
    else:
        # Linux: x86_64 static 빌드
        return f"yt-dlp_linux{suffix}"


def _platform_asset_url(ver: str) -> str:
    """플랫폼별 yt-dlp 배포 URL 생성."""
    asset = _platform_asset_name(ver)
    return f"https://github.com/yt-dlp/yt-dlp/releases/download/{ver}/{asset}"


def _latest_stable_version() -> str:
    """GitHub API에서 최신 안정 버전 조회 (실패 시 폴백)."""
    try:
        req = urllib.request.Request(
            _YTDLP_RELEASE_API,
            headers={"User-Agent": "ChzzkTube", "Accept": "application/vnd.github.v3+json"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.load(resp)
            tag = data.get("tag_name", "").lstrip("v")
            if tag:
                return tag
    except Exception as e:
        log_f12_net(f"GitHub API failed for latest yt-dlp version: {e}")
    return _YTDLP_FALLBACK_VER


def _download_with_progress(url: str, dest: Path, log_func=None, label: str = "") -> bool:
    """진행 로그 포함 파일 다운로드. 성공 시 True 반환."""
    log_f12_net(f"GET {url} -> {dest}")
    if log_func:
        log_func(emit_component("DEPS", "RUN", "YTDL", f"{label or os.path.basename(url)} downloading..."))

    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ChzzkTube"})
        with urllib.request.urlopen(req, timeout=60) as resp, open(tmp, "wb") as f:
            total = int(resp.headers.get("Content-Length", 0))
            done = 0
            last_pct = -1
            while True:
                chunk = resp.read(1024 * 512)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if total:
                    pct = done * 100 // total
                    if pct != last_pct and pct % 5 == 0:
                        last_pct = pct
                        if log_func:
                            log_func(emit_component("DEPS", "RUN", "YTDL", f"{label} {pct}%"))
        os.replace(tmp, dest)
        log_f12_net(f"Saved {dest} ({dest.stat().st_size / 1048576:.1f} MB)")
        if log_func:
            log_func(emit_component("DEPS", "OK", "YTDL", f"{label} done ({dest.stat().st_size / 1048576:.1f} MB)"))
        return True
    except Exception as e:
        log_f12_net(f"Download failed: {url} ({e})", is_error=True)
        if log_func:
            log_func(emit_component("DEPS", "FAIL", "YTDL", f"{label} download failed: {e}", is_error=True))
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        return False


# ── yt-dlp 실행 파일 탐색 ─────────────────────────────────────────────
def yt_dlp_path() -> str | None:
    """현재 사용 가능한 yt-dlp 실행 파일 경로 반환 (없으면 None).

    우선순위 (앱 전용 경로만):
    1. OS 표준 경로 (get_writable_base()/bin/yt-dlp) — 앱 전용 설치 위치
    2. frozen 빌드 번들 (_MEIPASS) — 포터블 빌드
    3. .pylib 오버레이 (레거시 호환)
    4. system PATH (shutil.which) — 최후 수단으로만 폴백
    """
    suffix = _exe_suffix()
    candidates = []

    # 1. OS 표준 경로 (앱 전용 설치 위치) — 최우선
    local_bin = _bin_dir() / f"yt-dlp{suffix}"
    if local_bin.is_file():
        candidates.append(str(local_bin))

    # 2. frozen 빌드 번들 (_MEIPASS) — 포터블 빌드
    if is_portable():
        bundle = bundle_root()
        if bundle:
            bundled = Path(bundle) / f"yt-dlp{suffix}"
            if bundled.is_file():
                candidates.insert(0, str(bundled))  # 번들을 최우선

    # 3. .pylib 오버레이 (레거시 호환 - 점점 사용 안 함)
    try:
        overlay = config.pylib_overlay_path()
        overlay_bin = Path(overlay) / f"yt-dlp{suffix}"
        if overlay_bin.is_file():
            candidates.append(str(overlay_bin))
    except Exception:
        pass


    # 실행 가능 여부 확인 후 첫 번째 유효한 것 반환
    # 시스템 PATH 폴백 없음 — 앱 전용 경로에 없으면 None 반환 (FAIL)
    for c in candidates:
        if Path(c).is_file() and os.access(c, os.X_OK):
            return c
    return None


def yt_dlp_version(exe_path: str | None = None) -> tuple[int, int, int] | None:
    """yt-dlp --version 출력에서 (major, minor, patch) 튜플 반환."""
    exe = exe_path or yt_dlp_path()
    if not exe:
        return None
    try:
        result = subprocess.run(
            [exe, "--version"],
            capture_output=True, text=True, timeout=10, encoding="utf-8", errors="replace",
        )
        cmd_str = f"{exe} --version"
        output_str = result.stdout or result.stderr or ""
        log_f12_cli(cmd_str, output_str.strip())
        if result.returncode == 0:
            m = re.match(r"(\d+)\.(\d+)\.(\d+)", output_str.strip())
            if m:
                return tuple(map(int, m.groups()))
    except Exception as e:
        log_f12_cli(f"{exe} --version", f"Exception: {e}", is_error=True)
    return None


def yt_dlp_ok(exe_path: str | None = None, min_version: tuple[int, int, int] = YTDLP_MIN_VERSION) -> bool:
    """지정된 버전 이상인지 확인."""
    ver = yt_dlp_version(exe_path)
    return ver is not None and ver >= min_version


# ── yt-dlp 자동 수급/설치 ─────────────────────────────────────────────
def ensure_yt_dlp(log_func=None, channel: str = "stable") -> bool:
    """yt-dlp 실행 파일 확보 (없으면 자동 다운로드/설치)."""
    # 이미 유효한 버전이 있으면 스킵
    if yt_dlp_ok():
        if log_func:
            log_func(emit_component("DEPS", "OK", "YTDL", f"yt-dlp already available"))
        return True

    if log_func:
        log_func(emit_component("DEPS", "RUN", "YTDL", "yt-dlp missing or outdated — downloading..."))

    # 설치 대상 디렉터리
    bin_dir = _bin_dir()
    bin_dir.mkdir(parents=True, exist_ok=True)
    suffix = _exe_suffix()
    dest = bin_dir / f"yt-dlp{suffix}"

    # 채널별 다운로드 URL 결정
    if channel == "nightly":
        # Nightly도 플랫폼별 asset 이름 사용 (macOS는 _macos 접미사 필요)
        asset = _platform_asset_name("nightly")
        url = f"{_YTDLP_NIGHTLY_BASE}/{asset}"
    else:
        ver = _latest_stable_version()
        url = _platform_asset_url(ver)

    try:
        if not _download_with_progress(url, dest, log_func, "yt-dlp binary downloading"):
            return False

        # 실행 권한 부여
        if suffix == ".exe":
            # Windows에서는 확장자로 충분
            pass
        else:
            dest.chmod(dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

        # 버전 검증
        if yt_dlp_ok(str(dest)):
            if log_func:
                log_func(emit_component("DEPS", "OK", "YTDL", f"yt-dlp installed at {dest}"))
            return True
        else:
            if log_func:
                log_func(emit_component("DEPS", "FAIL", "YTDL", "installed binary version check failed", is_error=True))
            return False
    except Exception as e:
        if log_func:
            log_func(emit_component("DEPS", "FAIL", "YTDL", f"install failed: {e}", is_error=True))
        return False

    return False


# ── yt-dlp 업데이트 ───────────────────────────────────────────────────
def upgrade_yt_dlp(channel: str = "stable", log_func=None) -> tuple[int, str]:
    """yt-dlp 바이너리 업데이트 (OS 표준 경로에 직접 교체)."""
    if not ensure_yt_dlp(log_func, channel):
        return 1, "ensure_yt_dlp failed"

    # 현재 버전 확인
    current = yt_dlp_version()
    # 최신 버전 확인
    if channel == "nightly":
        # nightly는 항상 최신으로 간주 (버전 번호 없음)
        return 0, f"updated to nightly"
    else:
        latest = _latest_stable_version()
        if current:
            cur_ver = ".".join(map(str, current))
            if cur_ver == latest:
                return 0, f"already up to date ({cur_ver})"
        return 0, f"updated to {latest}"