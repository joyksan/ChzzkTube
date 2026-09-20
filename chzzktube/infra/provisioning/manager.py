"""ProvisioningManager — 외부 라이브러리 수급/검증/커밋 단일 오케스트레이터.

로그 버스 정책 (HANDOVER §5-21):
- 모든 앱 동작은 raw_log.raw() → LogEvent 단일 경로
- Qt 시그널은 결과/제어/브리지에만 사용 (log_full/log_concise 시그널 금지)
- 발행자가 라벨과 to_tui 결정
- history ⊇ full ⊇ TUI (큐 2048, 버퍼 4096 유한)
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import asyncio
import time
import zipfile
import tarfile
import tempfile
import shutil

from chzzktube.core import config
from chzzktube.infra.provisioning.resolver import (
    ComponentSpec, ComponentType, MIRROR_REGISTRY, filter_assets,
)
from chzzktube.infra.provisioning.downloader import ParallelDownloader, DownloadTask
from chzzktube.infra.provisioning.verifier import Verifier
from chzzktube.infra.provisioning.manifest import ProvisionManifest, ComponentRecord
import chzzktube.core.raw_log as raw_log
from chzzktube.core.log_emitter import emit_component


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


@dataclass
class ProvisionResult:
    component: str
    success: bool
    version: Optional[str] = None
    error: Optional[str] = None
    action: str = ""
    sha256: str = ""


class ProvisioningManager:
    """단일 파사드 — resolve → download → verify → commit."""
    
    def __init__(self, log_func=None):
        self.base_dir = Path(config.writable_base())
        self.overlay_root = Path(config.pylib_overlay_path())
        self.manifest = ProvisionManifest.load(self.base_dir)
        self.log = log_func
        self._downloader = ParallelDownloader(progress_cb=self._on_progress)

    def _emit(self, stage, status, scope, msg, is_status=False, is_error=False):
        """raw_log 버스 단일 경유."""
        evt = emit_component(stage, status, scope, msg, is_status=is_status, is_error=is_error)
        if self.log:
            self.log(evt)
        raw_log.raw("provisioning", evt, to_tui=is_status, is_error=is_error)

    async def _on_progress(self, component: str, downloaded: int, total: int):
        """다운로드 진행률 하트비트 (무페이로드 아님 — TUI 상태용)."""
        if total > 0:
            pct = int(downloaded / total * 100)
            mb = downloaded // (1024 * 1024)
            self._emit("DEPS", "RUN", component.upper(),
                       f"downloading... {mb}MB ({pct}%)", is_status=True)

    # ── 1. Resolve ──────────────────────────────────────────────
    async def resolve(self, stale_only: bool = False, channel: str = "stable") -> list[ProvisionPlan]:
        """모든 구성요소에 대해 최신 버전 확인 + 플랜 생성."""
        self.manifest.last_check = time.time()
        plans = []
        
        for name, spec in MIRROR_REGISTRY.items():
            if spec.channel != channel:
                continue
            
            latest_ver, latest_url, sha256, mirror_name, archive_type = await self._fetch_latest(spec)
            if not latest_ver or not latest_url:
                self._emit("DEPS", "WARN", name.upper(), f"no mirror resolved")
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

    async def _fetch_latest(self, spec: ComponentSpec):
        """미러 체인에서 최신 버전/URL/sha256/미러명/arch타입 조회."""
        for mirror in sorted(spec.mirrors, key=lambda m: m.priority):
            try:
                if mirror.name == "pypi":
                    return await self._fetch_from_pypi(spec, mirror)
                elif "github" in mirror.name:
                    return await self._fetch_from_github(spec, mirror)
                elif mirror.name == "nodejs.org":
                    return await self._fetch_from_nodejs(spec, mirror)
            except Exception:
                continue
        return None, None, None, None, None

    async def _fetch_from_pypi(self, spec, mirror):
        """PyPI JSON API에서 최신 버전 + whl URL."""
        import httpx
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(mirror.url_template.format(pkg=spec.name))
            data = resp.json()
            version = data["info"]["version"]
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
        """GitHub Releases API에서 최신 릴리스 asset 선택."""
        import httpx
        async with httpx.AsyncClient(timeout=15) as client:
            if spec.name == "bgutil-ytdlp-pot-provider":
                api_url = f"https://api.github.com/repos/Brainicism/{spec.name}/releases/latest"
                resp = await client.get(api_url)
                data = resp.json()
                tag_name = data["tag_name"]
                assets = filter_assets(data.get("assets", []), spec)
                if assets:
                    asset = assets[0]
                    return tag_name, asset["browser_download_url"], None, "github", "server"
            else:
                resp = await client.get(mirror.url_template)
                data = resp.json()
                tag_name = data["tag_name"]
                assets = filter_assets(data.get("assets", []), spec)
                if assets:
                    asset = assets[0]
                    return tag_name, asset["browser_download_url"], None, mirror.name, "zip"
        
        return None, None, None, None, None

    async def _fetch_from_nodejs(self, spec, mirror):
        """nodejs.org dist index에서 latest LTS."""
        import httpx
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(mirror.url_template)
            entries = resp.json()
            ver = next(
                (e.get("version") for e in entries
                 if str(e.get("version", "")).startswith("v22.")),
                None
            )
            if not ver:
                ver = entries[0]["version"]
            
            from chzzktube.infra.node_provider import _platform_node_url
            url = _platform_node_url(ver)
            archive_type = "tar.gz" if "darwin" in url else "zip"
            return ver, url, None, "nodejs.org", archive_type
        
        return None, None, None, None, None

    # ── 2. Provision ────────────────────────────────────────────
    async def provision(self, plans: list[ProvisionPlan]) -> list[ProvisionResult]:
        """플랜 실행: 다운로드 → 추출/설치 → 검증."""
        if not plans:
            return []

        tasks = []
        for plan in plans:
            dest = self.base_dir / "downloads" / plan.component
            dest.parent.mkdir(parents=True, exist_ok=True)
            tasks.append(DownloadTask(
                component=plan.component,
                url=plan.download_url,
                dest=dest,
                expected_sha256=plan.expected_sha256,
                mirror_name=plan.mirror_name,
            ))

        results = await self._downloader.download_all(tasks)

        final_results = []
        for plan, dl_result in zip(plans, results):
            if not dl_result.success:
                self._emit("DEPS", "FAIL", plan.component.upper(),
                           f"download failed: {dl_result.error[:100]}")
                final_results.append(ProvisionResult(
                    plan.component, False, error=f"download failed: {dl_result.error}"
                ))
                continue

            installed_path = await self._extract_and_install(plan, dl_result.task.dest, dl_result.sha256 or "")
            if isinstance(installed_path, str):
                self._emit("DEPS", "FAIL", plan.component.upper(),
                           f"install failed: {installed_path}")
                final_results.append(ProvisionResult(
                    plan.component, False, error=f"install failed: {installed_path}"
                ))
                continue

            verify_result = Verifier.verify(plan.spec, installed_path)
            if not verify_result.success:
                self._emit("DEPS", "FAIL", plan.component.upper(),
                           f"verification failed: {verify_result.error}")
                final_results.append(ProvisionResult(
                    plan.component, False, error=f"verification failed: {verify_result.error}"
                ))
                continue

            self._emit("DEPS", "OK", plan.component.upper(),
                       f"{plan.component} {'updated' if plan.is_update else 'installed'} → {verify_result.version}")
            final_results.append(ProvisionResult(
                plan.component, True, version=verify_result.version,
                action="updated" if plan.is_update else "installed",
                sha256=dl_result.sha256 or "",
            ))

        return final_results

    async def _extract_and_install(self, plan: ProvisionPlan, archive: Path, sha256: str) -> Path:
        """아카이브 추출/설치 수행."""
        try:
            if plan.archive_type == "whl":
                from chzzktube.infra.updater import _extract_pylib_whl
                prefix = plan.component + "-" if plan.component != "yt-dlp" else "yt_dlp-"
                with zipfile.ZipFile(archive) as z:
                    z.extractall(str(self.overlay_root))
                _extract_pylib_whl(str(archive), str(self.overlay_root), prefix)
                return self.overlay_root

            elif plan.archive_type in ("zip", "server"):
                with tempfile.TemporaryDirectory(prefix=f"cz_{plan.component}_") as td:
                    with zipfile.ZipFile(archive) as z:
                        z.extractall(td)
                    dest = self.base_dir / plan.component
                    if dest.exists():
                        shutil.rmtree(dest, ignore_errors=True)
                    shutil.move(td, str(dest))
                    return dest

            elif plan.archive_type == "tar.gz":
                with tempfile.TemporaryDirectory(prefix=f"cz_{plan.component}_") as td:
                    with tarfile.open(archive, "r:gz") as tar:
                        tar.extractall(td)
                    dest = self.base_dir / plan.component
                    if dest.exists():
                        shutil.rmtree(dest, ignore_errors=True)
                    shutil.move(td, str(dest))
                    return dest

            elif plan.archive_type == "tar.xz":
                with tempfile.TemporaryDirectory(prefix=f"cz_{plan.component}_") as td:
                    with tarfile.open(archive, "r:xz") as tar:
                        tar.extractall(td, filter="data")
                    dest = self.base_dir / plan.component
                    if dest.exists():
                        shutil.rmtree(dest, ignore_errors=True)
                    shutil.move(td, str(dest))
                    return dest

            return f"unknown archive type: {plan.archive_type}"

        except Exception as e:
            return f"{type(e).__name__}: {e}"

    # ── 3. Commit ───────────────────────────────────────────────
    async def commit(self, plans: list[ProvisionPlan], results: list[ProvisionResult]) -> None:
        """manifest 갱신 + 오버레이/환경변수 리로드."""
        now = time.time()
        
        for plan, result in zip(plans, results):
            if result.success:
                self.manifest.update_component(ComponentRecord(
                    name=plan.component,
                    version=result.version or plan.version,
                    source=plan.mirror_name,
                    mirror=plan.mirror_name,
                    install_path=plan.spec.install_rel_path,
                    verified_at=now,
                    verify_version=result.version or "",
                    sha256=result.sha256,
                ))
        
        self.manifest.last_full_update = now
        self.manifest.save(self.base_dir)
        
        self._refresh_overlay()
        self._refresh_path()
        
        downloads_dir = self.base_dir / "downloads"
        if downloads_dir.exists():
            shutil.rmtree(downloads_dir, ignore_errors=True)

    def _refresh_overlay(self):
        """.pylib overlay 리로드."""
        try:
            from chzzktube.infra.pylib_bootstrap import bootstrap
            path = bootstrap(clear_caches=True)
            self._emit("DEPS", "OK", "PY", f"overlay refreshed: {path}")
        except Exception as e:
            self._emit("DEPS", "WARN", "PY", f"overlay refresh failed: {e}")

    def _refresh_path(self):
        """PATH에 검증된 binary 디렉토리 추가."""
        try:
            import os
            for name, rec in self.manifest.components.items():
                if name in ("ffmpeg", "node"):
                    spec = MIRROR_REGISTRY.get(name)
                    if spec and spec.type == ComponentType.BINARY:
                        bin_path = self.base_dir / rec.install_path
                        bin_dir = bin_path.parent if bin_path.is_file() else bin_path
                        if bin_dir.is_dir():
                            path_env = os.environ.get("PATH", "")
                            parts = path_env.split(os.pathsep) if path_env else []
                            if str(bin_dir) not in parts:
                                os.environ["PATH"] = os.pathsep.join([str(bin_dir)] + parts)
        except Exception:
            pass

    async def ensure_all(self, stale_only: bool = True, channel: str = "stable") -> list[ProvisionResult]:
        """전체 프로비저닝: resolve → download → verify → commit."""
        plans = await self.resolve(stale_only=stale_only, channel=channel)
        if not plans:
            self._emit("DEPS", "SKIP", "DEPS", "all components up-to-date")
            return []
        
        results = await self.provision(plans)
        await self.commit(plans, results)
        
        ok_count = sum(1 for r in results if r.success)
        fail_count = len(results) - ok_count
        if fail_count == 0:
            self._emit("DEPS", "DONE", "DEPS", f"provisioned {ok_count} components")
        else:
            self._emit("DEPS", "WARN", "DEPS", f"{ok_count} ok, {fail_count} failed")
        
        return results
