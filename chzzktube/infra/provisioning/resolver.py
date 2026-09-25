"""Component Resolver — 버전 해석 & 미러 선택.

설계 원칙:
- 버전 하드코딩 없음: latest_stable/latest_lts/channel 전략으로 런타임 해석
- 미러 체인: 우선순위 기반 자동 폴백
- 플랫폼별 asset 필터링: resolver 내부에서 처리
"""
from dataclasses import dataclass
from enum import Enum
from typing import Literal
import sys


class ComponentType(Enum):
    PYTHON_PKG = "python_pkg"      # yt-dlp → .pylib (whl)
    BINARY = "binary"              # ffmpeg, node → writable_base/bin (tar.gz/zip)
    SERVER = "server"              # bgutil → writable_base/bgutil (npm build)


@dataclass(frozen=True)
class Mirror:
    name: str                      # "pypi", "github", "nodejs.org", "ghcr.io"
    url_template: str              # "https://pypi.org/pypi/{pkg}/json"
    auth_required: bool = False
    priority: int = 0              # 낮을수록 우선


@dataclass(frozen=True)
class ComponentSpec:
    name: str
    type: ComponentType
    mirrors: tuple[Mirror, ...]
    verify_cmd: tuple[str, ...]    # ("ffmpeg", "-version")
    install_rel_path: str          # "ffmpeg/bin/ffmpeg", ".pylib/yt_dlp"
    # 버전 해석 전략
    version_strategy: Literal["latest_stable", "latest_lts", "pinned", "channel"] = "latest_stable"
    channel: str = "stable"        # "stable" | "nightly"
    # 플랫폼별 asset 필터 키워드
    asset_filters: tuple[str, ...] = ()


# 미러 레지스트리 — 외부 설정 파일로 분리 가능
MIRROR_REGISTRY: dict[str, ComponentSpec] = {
    "ffmpeg": ComponentSpec(
        name="ffmpeg",
        type=ComponentType.BINARY,
        version_strategy="latest_stable",
        mirrors=(
            # [v3.8.4] 거버넌스 정합 — 검증 불가/타깃 아키텍처 미지원 공급원 배제.
            # macOS는 Homebrew formulae bottle(SHA-256 + 실행 검증),
            # Windows/Linux는 BtbN 정적 GPL 아카이브를 components.py가 담당한다.
            Mirror("github_btb", "https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/latest", priority=0),
            Mirror("homebrew", "https://formulae.brew.sh/api/formula/ffmpeg.json", priority=1),
        ),
        verify_cmd=("ffmpeg", "-version"),
        install_rel_path="ffmpeg/bin/ffmpeg",
        asset_filters=("ffmpeg", "static"),
    ),
    "node": ComponentSpec(
        name="node",
        type=ComponentType.BINARY,
        version_strategy="latest_lts",
        mirrors=(
            Mirror("nodejs.org", "https://nodejs.org/dist/index.json", priority=0),
            Mirror("github_node", "https://api.github.com/repos/nodejs/node/releases/latest", priority=1),
        ),
        verify_cmd=("node", "--version"),
        install_rel_path="node/bin/node",
        asset_filters=("node",),
    ),
    "bgutil": ComponentSpec(
        name="bgutil-ytdlp-pot-provider",
        type=ComponentType.SERVER,
        version_strategy="latest_stable",
        mirrors=(
            Mirror("github", "https://api.github.com/repos/Brainicism/bgutil-ytdlp-pot-provider/releases/latest", priority=0),
        ),
        verify_cmd=("node", "server.js", "--health-check"),
        install_rel_path="bgutil-ytdlp-pot-provider",
    ),
}


def get_platform_asset_filters() -> tuple[str, ...]:
    """현재 플랫폼에 맞는 asset 필터 반환."""
    platform = sys.platform
    machine = ""
    try:
        import platform as _platform
        machine = _platform.machine().lower()
    except Exception as e:
        import chzzktube.core.raw_log as raw_log
        raw_log.raw("DEPS", f"get_platform_asset_filters error: {type(e).__name__}: {e}", is_error=True, to_tui=False)

    if platform == "darwin":
        if machine == "arm64":
            return ("arm64", "macos", "darwin", "apple")
        return ("x86_64", "macos", "darwin", "apple")
    elif platform == "win32":
        return ("win64", "windows", "x64")
    else:
        return ("linux", "x86_64", "amd64")


# [stdlib-only] 표준 라이브러리로 해제 불가능한 아카이브 — 수급 후보에서 배제.
# py7zr 등 외부 의존성을 수급 계층(L0)에 들이지 않기 위한 명시적 경계.
# .tar.xz/.tar.gz는 tarfile로 해제 가능하므로 배제 대상이 아니다.
ARCHIVE_UNSUPPORTED_EXT = (".7z", ".rar", ".tar.zst", ".zst")
# 선호 순위: 앞일수록 우선. .zip/.tar.xz 최우선, 확장자 없음(원시 바이너리) 차선.
ARCHIVE_PREFERRED_EXT = (".zip", ".tar.xz", ".tar.gz", "")


def filter_assets(assets: list[dict], spec: ComponentSpec) -> list[dict]:
    """플랫폼·스펙 필터 + 아카이브 확장자 선호 정렬로 asset 선별."""
    platform_filters = get_platform_asset_filters()
    spec_filters = spec.asset_filters

    candidates = []
    for asset in assets:
        name = asset.get("name", "").lower()
        
        # 플랫폼 키워드가 '반드시' 하나 이상 매칭되어야 함
        # 단순히 'ffmpeg' 단어가 들어있다고 다른 OS 아카이브를 낚아채는 참사를 원천 차단
        if platform_filters and not any(p in name for p in platform_filters):
            continue
            
        if spec_filters and not any(s in name for s in spec_filters):
            continue

        # 제외 키워드
        if any(x in name for x in ("debug", "symbols", "pdb", ".sig", ".asc")):
            continue
        if any(name.endswith(ext) for ext in ARCHIVE_UNSUPPORTED_EXT):
            continue

        rank = next(
            (i for i, ext in enumerate(ARCHIVE_PREFERRED_EXT) if name.endswith(ext)),
            len(ARCHIVE_PREFERRED_EXT),
        )
        candidates.append((rank, asset))

    candidates.sort(key=lambda pair: pair[0])
    return [asset for _, asset in candidates]
