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
    PYTHON_PKG = "python_pkg"      # yt-dlp, streamlink → .pylib (whl)
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
    "yt-dlp": ComponentSpec(
        name="yt-dlp",
        type=ComponentType.PYTHON_PKG,
        version_strategy="latest_stable",
        channel="stable",
        mirrors=(
            Mirror("pypi", "https://pypi.org/pypi/yt-dlp/json", priority=0),
            Mirror("github", "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest", priority=1),
        ),
        verify_cmd=("python", "-m", "yt_dlp", "--version"),
        install_rel_path=".pylib",
    ),
    "streamlink": ComponentSpec(
        name="streamlink",
        type=ComponentType.PYTHON_PKG,
        version_strategy="latest_stable",
        channel="stable",
        mirrors=(
            Mirror("pypi", "https://pypi.org/pypi/streamlink/json", priority=0),
            Mirror("github", "https://api.github.com/repos/streamlink/streamlink/releases/latest", priority=1),
        ),
        verify_cmd=("python", "-m", "streamlink", "--version"),
        install_rel_path=".pylib",
    ),
    "ffmpeg": ComponentSpec(
        name="ffmpeg",
        type=ComponentType.BINARY,
        version_strategy="latest_stable",
        mirrors=(
            Mirror("github_gyan", "https://api.github.com/repos/GyanD/codexffmpeg/releases/latest", priority=0),
            Mirror("github_btb", "https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/latest", priority=1),
            Mirror("evermeet", "https://evermeet.cx/ffmpeg/getrelease/zip", priority=2),
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
    except Exception:
        pass

    if platform == "darwin":
        if machine == "arm64":
            return ("arm64", "macos", "darwin", "apple")
        return ("x86_64", "macos", "darwin", "apple")
    elif platform == "win32":
        return ("win64", "windows", "x64")
    else:
        return ("linux", "x86_64", "amd64")


def filter_assets(assets: list[dict], spec: ComponentSpec) -> list[dict]:
    """플랫폼 및 스펙 필터에 맞는 asset만 선별."""
    platform_filters = get_platform_asset_filters()
    spec_filters = spec.asset_filters
    all_filters = platform_filters + spec_filters

    filtered = []
    for asset in assets:
        name = asset.get("name", "").lower()
        if any(f in name for f in all_filters):
            # 제외 키워드
            if any(x in name for x in ("debug", "symbols", "pdb", ".sig", ".asc")):
                continue
            filtered.append(asset)
    return filtered