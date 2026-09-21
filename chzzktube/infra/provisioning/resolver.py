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


# [stdlib-only] zipfile로 해제 불가능한 아카이브 — 수급 후보에서 완전 배제.
# py7zr 등 외부 의존성을 수급 계층(L0)에 들이지 않기 위한 명시적 경계.
ARCHIVE_UNSUPPORTED_EXT = (".7z", ".rar", ".xz", ".tar.zst", ".zst")
# 선호 순위: 앞일수록 우선. .zip 최우선, 확장자 없음(원시 바이너리) 차선.
ARCHIVE_PREFERRED_EXT = (".zip", "")


def filter_assets(assets: list[dict], spec: ComponentSpec) -> list[dict]:
    """플랫폼·스펙 필터 + 아카이브 확장자 선호 정렬로 asset 선별.

    [stdlib-only 원칙] 수급 계층(L0)은 외부 압축 라이브러리에 의존하지 않는다.
    해제 가능한 형식(.zip)만 유효 후보로 남기고, 파싱 불가 형식(.7z 등)은
    명시적으로 배제한다. 선정된 asset은 zipfile로 해제 가능해야 한다.

    [정렬 규칙] GyanD 릴리즈는 7z가 zip보다 파일명 앞에 오므로, 단순 목록
    순서(assets[0])로 뽑으면 7z를 낚아채 BadZipFile로 귀결된다.
    → .zip 최우선, 그다음 확장자 없는 원시 바이너리. 해제 불가 형식 제외.
    """
    platform_filters = get_platform_asset_filters()
    spec_filters = spec.asset_filters
    all_filters = platform_filters + spec_filters

    candidates = []
    for asset in assets:
        name = asset.get("name", "").lower()
        if not any(f in name for f in all_filters):
            continue
        # 제외 키워드
        if any(x in name for x in ("debug", "symbols", "pdb", ".sig", ".asc")):
            continue
        # [stdlib-only] zipfile로 해제 불가능한 아카이브 — 후보에서 완전 배제
        if any(name.endswith(ext) for ext in ARCHIVE_UNSUPPORTED_EXT):
            continue
        rank = next(
            (i for i, ext in enumerate(ARCHIVE_PREFERRED_EXT) if name.endswith(ext)),
            len(ARCHIVE_PREFERRED_EXT),
        )
        candidates.append((rank, asset))

    # 안정 정렬 — 동순위는 원래 순서 보존
    candidates.sort(key=lambda pair: pair[0])
    return [asset for _, asset in candidates]
