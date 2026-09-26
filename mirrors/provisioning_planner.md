"""Planner — 프로비저닝 플랜 생성 (resolve 단계만 담당).

ProvisioningManager에서 resolve 로직을 분리한 순수 플래너.
미러 체인에서 최신 버전/URL/sha256 조회 → ProvisionPlan 리스트 생성.
"""
import asyncio
import json
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from chzzktube.core import config, raw_log
from chzzktube.core.log_emitter import emit_component
from chzzktube.core.raw_log import log_f12_net
from chzzktube.infra.provisioning.manifest import ProvisionManifest
from chzzktube.infra.provisioning.resolver import (
    MIRROR_REGISTRY,
    ComponentSpec,
    ComponentType,
    filter_assets,
)


@dataclass
class ProvisionPlan:
    component: str
    spec: ComponentSpec
    mirror_name: str
    version: str
    download_url: str
    expected_sha256: str | None
    install_path: Path
    is_update: bool
    archive_type: str  # "whl", "zip", "tar.gz", "tar.xz", "server"


class Planner:
    """resolve 단계만 담당 — 플랜 생성."""

    def __init__(self, base_dir: Path, log_func=None):
        self.base_dir = base_dir
        self.manifest = ProvisionManifest.load(base_dir)
        self.log = log_func
        self.overlay_root = Path(config.pylib_overlay_path())

    def _emit(self, stage, status, scope, msg, is_status=False, is_error=False,
              component_id: str | None = None, is_progress: bool = False, to_tui: bool | None = None):
        """raw_log 버스 단일 경유."""
        evt = emit_component(stage, status, scope, msg, is_status=is_status, is_error=is_error)
        evt.component_id = component_id
        evt.is_progress = is_progress
        if to_tui is None:
            to_tui = is_status or is_progress or is_error or (status in ("OK", "DONE", "FAIL", "READY", "WARN"))
        raw_log.raw(
            "provisioning", evt, to_tui=to_tui, is_error=is_error,
            component_id=component_id, is_progress=is_progress,
        )

    async def _fetch_json(self, url: str, *, headers: dict[str, str] | None = None):
        """Worker thread에서 동기 urllib JSON 요청을 수행한다."""
        return await asyncio.to_thread(self._fetch_json_sync, url, headers)

    @staticmethod
    def _fetch_json_sync(
        url: str, headers: dict[str, str] | None = None
    ) -> dict | list | None:
        log_f12_net(f"HTTP GET {url}")
        request = urllib.request.Request(url, headers=headers or {})
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                return json.loads(response.read().decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, urllib.error.HTTPError) as e:
            log_f12_net(f"HTTP GET failed ({url}): {e}", is_error=True)
            return None

    async def _fetch_text(self, url: str) -> str | None:
        """Worker thread에서 동기 urllib 텍스트 요청을 수행한다."""
        return await asyncio.to_thread(self._fetch_text_sync, url)

    @staticmethod
    def _fetch_text_sync(url: str) -> str | None:
        log_f12_net(f"HTTP GET {url}")
        request = urllib.request.Request(url, headers={"User-Agent": "ChzzkTube-Provisioner/1.0"})
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                return response.read().decode("utf-8")
        except (OSError, UnicodeDecodeError, urllib.error.HTTPError) as e:
            log_f12_net(f"HTTP GET failed ({url}): {e}", is_error=True)
            return None

    async def _fetch_latest(self, spec: ComponentSpec):
        """미러 체인에서 최신 버전/URL/sha256/미러명/arch타입 조회."""
        for mirror in sorted(spec.mirrors, key=lambda m: m.priority):
            try:
                # macOS에서 BtbN mirror는 darwin 바이너리가 없으므로 skip
                if sys.platform == "darwin" and mirror.name == "github_btb":
                    continue

                if mirror.name == "pypi":
                    result = await self._fetch_from_pypi(spec, mirror)
                elif mirror.name == "homebrew":
                    result = await self._fetch_from_homebrew(spec, mirror)
                elif "github" in mirror.name:
                    result = await self._fetch_from_github(spec, mirror)
                elif mirror.name == "nodejs.org":
                    result = await self._fetch_from_nodejs(spec, mirror)
                else:
                    result = None

                if result and result[0] and result[1]:
                    log_f12_net(f"resolved {spec.name}: v{result[0]} via {result[3]} -> {result[1]}")
                    return result
            except Exception as e:  # noqa: BLE001 — 개별 미러 조회 실패는 다음 미러로 폴백
                from chzzktube.core import raw_log
                raw_log.raw("DEPS", f"_fetch_latest mirror {mirror.name} error: {type(e).__name__}: {e}", is_error=True, to_tui=False)
                log_f12_net(f"mirror {mirror.name} query error for {spec.name}: {e}", is_error=True)
        return None, None, None, None, None

    async def _fetch_from_homebrew(self, spec, mirror):
        """Homebrew formulae API에서 최신 버전 + bottle URL 조회 (macOS 전용)."""
        import platform as _platform
        if sys.platform != "darwin":
            return None, None, None, None, None

        data = await self._fetch_json(mirror.url_template)
        if not data:
            return None, None, None, None, None

        version = data.get("versions", {}).get("stable")
        if not version:
            return None, None, None, None, None

        files = data.get("bottle", {}).get("stable", {}).get("files", {})
        arch = _platform.machine().lower()
        prefix = "arm64_" if arch in ("arm64", "aarch64") else "x86_64_"
        candidates = [k for k in files if k.startswith(prefix) and "linux" not in k]

        try:
            darwin_major = int(_platform.release().split(".")[0])
        except (ValueError, IndexError):  # 빌드 번호 판정 실패 시 기본값(sequoia=24)
            darwin_major = 24

        _BUILD_ORDERS = (
            ("sequoia", 24),
            ("sonoma", 23),
            ("ventura", 22),
            ("monterey", 21),
            ("big_sur", 20),
            ("catalina", 19),
        )
        chosen_key = None
        for name, bnum in _BUILD_ORDERS:
            k = prefix + name
            if k in files and bnum <= darwin_major:
                chosen_key = k
                break
        if not chosen_key and candidates:
            chosen_key = candidates[0]
        if not chosen_key:
            return None, None, None, None, None

        entry = files[chosen_key]
        url = entry.get("url")
        sha256 = entry.get("sha256")
        return version, url, sha256, mirror.name, "tar.gz"

    @staticmethod
    def _archive_type_from(filename: str, spec: ComponentSpec) -> str:
        """아카이브 파일명 확장자로 해제 방법 판정 (하드코딩 금지).

        bgutil 서버는 npm 소스 구조이므로 항상 server로 간주하고(해제 후 npm 빌드),
        그 외는 .zip / .tar.gz / .tar.xz 확장자를 그대로 반환한다.
        """
        if spec.name == "bgutil-ytdlp-pot-provider":
            return "server"

        fn = filename.lower()
        if fn.endswith(".whl"):
            return "whl"
        if fn.endswith(".tar.xz"):
            return "tar.xz"
        if fn.endswith(".tar.gz"):
            return "tar.gz"
        if fn.endswith(".zip"):
            return "zip"
        return "binary"

    async def _fetch_from_pypi(self, spec, mirror):
        """PyPI JSON API에서 최신 버전 + whl URL."""
        data = await self._fetch_json(
            mirror.url_template.format(pkg=spec.name)
        )
        if not data:
            return None, None, None, None, None
        version = data.get("info", {}).get("version")
        sha256 = None

        for f in data.get("releases", {}).get(version, []):
            fn = f["filename"].lower()
            if "py3-none-any" in fn and "whl" in fn:
                sha256 = f.get("digests", {}).get("sha256")
                return version, f["url"], sha256, "pypi", "whl"

        for f in data.get("releases", {}).get(version, []):
            if "whl" in f["filename"].lower():
                sha256 = f.get("digests", {}).get("sha256")
                return version, f["url"], sha256, "pypi", "whl"

        return None, None, None, None, None

    async def _fetch_from_github(self, spec, mirror):
        """GitHub Releases API에서 최신 버전 + asset URL."""
        data = await self._fetch_json(mirror.url_template)
        if not data:
            return None, None, None, None, None
        version = (data.get("tag_name") or "").lstrip("v")
        if not version:
            return None, None, None, None, None

        if getattr(spec, "type", None) == ComponentType.SERVER:
            tag = data.get("tag_name") or version
            url = data.get("zipball_url") or f"https://github.com/Brainicism/bgutil-ytdlp-pot-provider/archive/refs/tags/{tag}.zip"
            return version, url, None, mirror.name, "server"

        assets = data.get("assets") or []
        if spec.name in ("yt-dlp", "ytdlp"):
            from chzzktube.infra.yt_dlp_binary import _platform_asset_name
            target_asset_name = _platform_asset_name(version)
            for a in assets:
                if a.get("name") == target_asset_name:
                    return version, a.get("browser_download_url"), None, mirror.name, "binary"

        candidates = filter_assets(assets, spec)
        if not candidates:
            return None, None, None, None, None

        asset = candidates[0]
        archive_type = self._archive_type_from(asset["name"], spec)
        return version, asset["browser_download_url"], None, mirror.name, archive_type

    async def _fetch_from_nodejs(self, spec, mirror):
        """nodejs.org dist index에서 latest LTS + SHA256 체크섬 조회."""
        data = await self._fetch_json(mirror.url_template)
        if not data:
            return None, None, None, None, None
        entries = data
        ver = next(
            (e.get("version") for e in entries if str(e.get("version", "")).startswith("v22.")),
            None,
        )
        if not ver:
            ver = entries[0]["version"]

        from chzzktube.infra.node_provider import _platform_node_url
        url = _platform_node_url(ver)
        archive_type = "tar.gz" if "darwin" in url else "zip"

        # SHA256 체크섬 조회 (SHASUMS256.txt에서 해당 파일 해시 추출)
        sha256 = await self._fetch_nodejs_sha256(ver, url)
        return ver, url, sha256, "nodejs.org", archive_type

    async def _fetch_nodejs_sha256(self, version: str, download_url: str) -> str | None:
        """nodejs.org SHASUMS256.txt에서 특정 버전/플랫폼 파일의 SHA256 조회."""
        # SHASUMS256.txt URL 구성
        shasums_url = f"https://nodejs.org/dist/{version}/SHASUMS256.txt"
        try:
            shasums_text = await self._fetch_text(shasums_url)
            if not shasums_text:
                return None
            # 파일명 추출 (URL에서)
            filename = download_url.split("/")[-1]
            # SHASUMS256.txt에서 해당 파일명 찾기
            for line in shasums_text.splitlines():
                line = line.strip()
                if not line:
                    continue
                # 형식: "sha256_hash  filename"
                parts = line.split()
                if len(parts) >= 2 and parts[1] == filename:
                    return parts[0]
        except Exception as e:  # noqa: BLE001 — SHASUMS 조회 실패는 None (무검증 채택 금지)
            from chzzktube.core import raw_log
            raw_log.raw("DEPS", f"_fetch_nodejs_sha256 error: {type(e).__name__}: {e}", is_error=True, to_tui=False)
        return None

    async def resolve(self, stale_only: bool = False, channel: str = "stable") -> list[ProvisionPlan]:
        """모든 구성요소에 대해 최신 버전 확인 + 플랜 생성."""
        self.manifest.last_check = time.time()
        plans = []

        for name, spec in MIRROR_REGISTRY.items():
            if spec.channel != channel:
                continue

            latest_ver, latest_url, sha256, mirror_name, archive_type = await self._fetch_latest(spec)
            if not latest_ver or not latest_url:
                self._emit(
                    "DEPS", "WARN", name.upper(), "no mirror resolved",
                    component_id=f"deps_{name}", is_progress=False,
                )
                continue

            if stale_only and not self.manifest.is_stale(name, latest_ver, base_dir=self.base_dir):
                continue

            if spec.type == ComponentType.PYTHON_PKG:
                install_path = self.overlay_root
            else:
                install_path = self.base_dir / spec.install_rel_path

            plans.append(ProvisionPlan(
                component=name,
                spec=spec,
                mirror_name=mirror_name,
                version=latest_ver,
                download_url=latest_url,
                expected_sha256=sha256,
                install_path=install_path,
                is_update=name in self.manifest.components,
                archive_type=archive_type,
            ))

        return plans