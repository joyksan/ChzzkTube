"""Planner — 프로비저닝 플랜 생성 (resolve 단계만 담당).

ProvisioningManager에서 resolve 로직을 분리한 순수 플래너.
미러 체인에서 최신 버전/URL/sha256 조회 → ProvisionPlan 리스트 생성.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import asyncio
import json
import os
import sys
import time
import urllib.error
import urllib.request
import zipfile
import tarfile
import tempfile
import shutil

from chzzktube.core import config
from chzzktube.infra.provisioning.resolver import (
    ComponentSpec, ComponentType, MIRROR_REGISTRY, filter_assets,
)
from chzzktube.infra.provisioning.manifest import ProvisionManifest, ComponentRecord
import chzzktube.core.raw_log as raw_log
from chzzktube.core.log_emitter import emit_component, emit_progress
from chzzktube.core.log_event import LogEvent


@dataclass
class ProvisionPlan:
    component: str
    spec: ComponentSpec
    mirror_name: str
    version: str
    download_url: str
    expected_sha256: Optional[str]
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
              component_id: str | None = None, is_progress: bool = False):
        """raw_log 버스 단일 경유."""
        evt = emit_component(stage, status, scope, msg, is_status=is_status, is_error=is_error)
        evt.component_id = component_id
        evt.is_progress = is_progress
        raw_log.raw(
            "provisioning", evt, to_tui=is_status, is_error=is_error,
            component_id=component_id, is_progress=is_progress,
        )

    async def _fetch_json(self, url: str, *, headers: Optional[dict[str, str]] = None):
        """Worker thread에서 동기 urllib JSON 요청을 수행한다."""
        return await asyncio.to_thread(self._fetch_json_sync, url, headers)

    @staticmethod
    def _fetch_json_sync(
        url: str, headers: Optional[dict[str, str]] = None
    ) -> Optional[dict | list]:
        request = urllib.request.Request(url, headers=headers or {})
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                return json.loads(response.read().decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, urllib.error.HTTPError):
            return None

    async def _fetch_text(self, url: str) -> Optional[str]:
        """Worker thread에서 동기 urllib 텍스트 요청을 수행한다."""
        return await asyncio.to_thread(self._fetch_text_sync, url)

    @staticmethod
    def _fetch_text_sync(url: str) -> Optional[str]:
        request = urllib.request.Request(url, headers={"User-Agent": "ChzzkTube-Provisioner/1.0"})
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                return response.read().decode("utf-8")
        except (OSError, UnicodeDecodeError, urllib.error.HTTPError):
            return None

    async def _fetch_latest(self, spec: ComponentSpec):
        """미러 체인에서 최신 버전/URL/sha256/미러명/arch타입 조회."""
        for mirror in sorted(spec.mirrors, key=lambda m: m.priority):
            try:
                if mirror.name == "pypi":
                    result = await self._fetch_from_pypi(spec, mirror)
                elif "github" in mirror.name:
                    result = await self._fetch_from_github(spec, mirror)
                elif mirror.name == "nodejs.org":
                    result = await self._fetch_from_nodejs(spec, mirror)
                else:
                    result = None

                if result[0] and result[1]:
                    return result
            except Exception as e:
                import chzzktube.core.raw_log as raw_log
                raw_log.raw("DEPS", f"_fetch_latest mirror {mirror.name} error: {type(e).__name__}: {e}", is_error=True, to_tui=False)
                pass
        return None, None, None, None, None

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

        assets = data.get("assets") or []
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

    async def _fetch_nodejs_sha256(self, version: str, download_url: str) -> Optional[str]:
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
        except Exception as e:
            import chzzktube.core.raw_log as raw_log
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

            if stale_only and not self.manifest.is_stale(name, latest_ver):
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