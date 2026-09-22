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
import json
import os
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
from chzzktube.infra.provisioning.downloader import ParallelDownloader, DownloadTask
from chzzktube.infra.provisioning.verifier import Verifier
from chzzktube.infra.provisioning.manifest import ProvisionManifest, ComponentRecord
import chzzktube.core.raw_log as raw_log
from chzzktube.core.log_emitter import emit_component, emit_progress
from chzzktube.core.log_event import LogEvent  # _emit_via_log 타이ppo 어노테이션용


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


# ── 아카이브 바이너리 구조 평탄화 헬퍼 (모듈 레벨 단독 함수) ───────────
def _promote_extracted_binaries(temp_dir: str, target_dest: Path, component_name: str) -> Path:
    """Homebrew Bottle의 중첩된 Cellar/bin 구조 속에서 바이너리를 색출해 target_dest/bin/으로 승격시킵니다.
    초천재 병약 미소녀 해커의 미학이 담긴 무결점 경로 구출기랍니다.
    """
    td_path = Path(temp_dir)
    target_bin_dir = target_dest / "bin"
    target_bin_dir.mkdir(parents=True, exist_ok=True)

    # 컴포넌트별 필수 바이너리 정의
    targets = ("ffmpeg", "ffprobe") if component_name == "ffmpeg" else ("node", "npm")
    found_bins = {}

    for p in td_path.rglob("*"):
        if p.is_file() and p.name.lower() in [t + (".exe" if os.name == "nt" else "") for t in targets]:
            stem = p.name.replace(".exe", "").lower()
            if stem not in found_bins:
                found_bins[stem] = p

    # 바이너리가 색출되었다면 target_dest/bin/ 직하위로 평탄화 복사
    if "ffmpeg" in found_bins or "node" in found_bins:
        for stem, src_path in found_bins.items():
            dest_file = target_bin_dir / src_path.name
            if dest_file.exists():
                dest_file.unlink()
            shutil.copy2(src_path, dest_file)
            if os.name != "nt":
                dest_file.chmod(dest_file.stat().st_mode | 0o755)
        return target_dest

    # 단일 루트 폴더 승격 (일반 아카이브 구조 대응)
    entries = os.listdir(temp_dir)
    if len(entries) == 1 and os.path.isdir(os.path.join(temp_dir, entries[0])):
        inner = os.path.join(temp_dir, entries[0])
        if target_dest.exists():
            shutil.rmtree(target_dest, ignore_errors=True)
        shutil.move(inner, str(target_dest))
        return target_dest

    if target_dest.exists():
        shutil.rmtree(target_dest, ignore_errors=True)
    shutil.move(temp_dir, str(target_dest))
    return target_dest


class ProvisioningManager:
    """단일 파사드 — resolve → download → verify → commit."""
    
    def __init__(self, log_func=None):
        self.base_dir = Path(config.writable_base())
        self.overlay_root = Path(config.pylib_overlay_path())
        self.manifest = ProvisionManifest.load(self.base_dir)
        self.log = log_func
        self._downloader = ParallelDownloader(progress_cb=self._on_progress)
        self._active_progress: dict[str, dict] = {}  # component -> {downloaded, total, speed, eta}

    def _emit(self, stage, status, scope, msg, is_status=False, is_error=False,
              component_id: str | None = None, is_progress: bool = False):
        """raw_log 버스 단일 경유 — 발행자만 raw_log.raw() 호출 (이중 적재 방지)."""
        evt = emit_component(stage, status, scope, msg, is_status=is_status, is_error=is_error)
        evt.component_id = component_id
        evt.is_progress = is_progress
        raw_log.raw(
            "provisioning", evt, to_tui=is_status, is_error=is_error,
            component_id=component_id, is_progress=is_progress,
        )

    def _emit_via_log(self, event: LogEvent) -> bool:
        """Progress event를 기존 log_func 계약으로 한 번만 중계한다."""
        if self.log is None:
            return False
        try:
            self.log(
                event,
                is_status=event.is_status,
                is_error=event.is_error,
                component_id=event.component_id,
                is_progress=event.is_progress,
            )
        except TypeError:
            # 기존 동기 브리지처럼 LogEvent 하나만 받는 콜백과 호환
            self.log(event)
        return True

    async def _on_progress(self, component: str, downloaded: int, total: int, speed_bps: float = 0.0, eta_sec: float = 0.0):
        """다운로드 진행률 하트비트 — TUI: 컴포넌트별 개별 갱신형 라인, F12: 개별 누적."""
        if total <= 0:
            return

        pct = int(downloaded / total * 100)
        downloaded_mb = downloaded / (1024 * 1024)
        total_mb = total / (1024 * 1024)

        speed_str = self._format_speed(speed_bps)
        eta_str = self._format_eta(eta_sec)

        # 개별 진행 저장
        self._active_progress[component] = {
            "pct": pct,
            "downloaded_mb": downloaded_mb,
            "total_mb": total_mb,
            "speed": speed_str,
            "eta": eta_str,
            "state": "running",
        }

        # 진행률 메시지: §3.5-3.6 포맷
        progress_msg = f"{downloaded_mb:.1f}/{total_mb:.1f} MB"
        if eta_str:
            progress_msg += f" ETA {eta_str}"

        # TUI/F12가 같은 LogEvent의 원문과 component_id를 각각 렌더링한다.
        # is_status=True는 F12의 기존 갱신형 append 경로를 열고,
        # is_progress=True는 TUI의 다중 컴포넌트 갱신 경로를 선택한다.
        event = emit_component(
            "DEPS", "RUN", component.upper(),
            self._fmt_progress(pct, speed_str, progress_msg),
            is_status=True,
            is_error=False,
        )
        event.component_id = f"deps_{component}"
        event.is_progress = True
        if not self._emit_via_log(event):
            raw_log.raw(
                "provisioning", event, to_tui=True,
                component_id=event.component_id, is_progress=True,
            )

    @staticmethod
    def _format_speed(bps: float) -> str:
        """GB/s 승격으로 자릿수 폭주를 원천 차단"""
        if bps >= 1024 * 1024 * 1024:
            return f"{bps / (1024 * 1024 * 1024):.1f} GB/s"
        elif bps >= 1024 * 1024:
            return f"{bps / (1024 * 1024):.1f} MB/s"
        elif bps >= 1024:
            return f"{bps / 1024:.1f} KB/s"
        elif bps > 0:
            return f"{bps:.0f} B/s"
        return ""

    @staticmethod
    def _format_eta(seconds: float) -> str:
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            return f"{int(seconds // 60)}m {int(seconds % 60)}s"
        else:
            return f"{int(seconds // 3600)}h {int((seconds % 3600) // 60)}m"

    @staticmethod
    def _fmt_progress(pct: int, speed: str, msg: str = "") -> str:
        """§3.5-3.6 규격 엄수: PCT(3자리) · SPEED(10자리 고정) [GAUGE 10블록] · msg"""
        bar = "█" * (pct // 10) + "░" * (10 - pct // 10)
        
        # 속도가 있든 없든 정확히 10자리의 폭을 강제하여 [GAUGE]의 시작 위치를 완벽하게 세로 정렬!
        speed_padded = f"{speed:>10}" if speed else " " * 10
        speed_str = f" · {speed_padded}"
        
        msg_str = f" · {msg}" if msg else ""
        return f"{pct:3d}%{speed_str} [{bar}]{msg_str}"

    def _emit_f12_progress(self, component: str, pct: int, state: str, msg: str = "", speed: str = ""):
        """F12에 개별 진행/완료/실패 상태 갱신형 출력 (각각 별도 줄)."""
        scope = component.upper()
        status = "OK" if state == "completed" else "FAIL" if state == "failed" else "RUN"

        full_msg = self._fmt_progress(pct, speed, msg)

        event = emit_progress(
            stage="DEPS",
            status=status,
            scope=scope,
            msg=full_msg,
            speed=speed,
            pct=pct,
            bar_frac=pct / 100.0,
            is_status=True,
            is_error=(state == "failed"),
            component_id=f"deps_{component}",
            is_progress=False,
        )
        # 이 헬퍼는 호환용이며 호출 시 F12 갱신 이벤트를 한 번만 발행한다.
        raw_log.raw(
            "provisioning", event, to_tui=False,
            is_error=(state == "failed"),
            component_id=event.component_id,
            is_progress=False,
        )

    def _emit_f12_summary(self, total: int, ok: int, failed: int):
        """F12 마지막 줄: 완료/실패 요약 (갱신형, component_id로 추적)."""
        if failed > 0:
            msg = f"completed {ok}/{total} failed {failed} see f12"
        else:
            msg = f"completed {ok}/{total}"
        
        event = emit_progress(
            stage="DEPS",
            status="OK" if failed == 0 else "WARN",
            scope="SUMMARY",
            msg=msg,
            speed="",
            pct=100,
            bar_frac=1.0,
            is_status=True,
            is_error=(failed > 0),
            component_id="deps_SUMMARY",
            is_progress=False,
        )
        raw_log.raw(
            "provisioning", event, to_tui=False,
            is_error=(failed > 0),
            component_id=event.component_id,
            is_progress=False,
        )

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
            except Exception:
                pass
        return None, None, None, None, None

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

    @staticmethod
    def _archive_type_from(filename: str, spec: ComponentSpec) -> str:
        """아카이브 파일명 확장자로 해제 방법 판정 (하드코딩 금지).

        bgutil 서버는 npm 소스 구조이므로 항상 server로 간주하고(해제 후 npm 빌드),
        그 외는 .zip / .tar.gz / .tar.xz 확장자를 그대로 반환한다.
        """
        if spec.name == "bgutil-ytdlp-pot-provider":
            return "server"
        low = (filename or "").lower()
        if low.endswith(".tar.gz") or low.endswith(".tgz"):
            return "tar.gz"
        if low.endswith(".tar.xz"):
            return "tar.xz"
        if low.endswith(".whl"):
            return "whl"
        return "zip"

    async def _fetch_from_github(self, spec, mirror):
        """GitHub Releases API에서 최신 릴리스 asset 선택."""
        if spec.name == "bgutil-ytdlp-pot-provider":
            api_url = (
                "https://api.github.com/repos/Brainicism/"
                f"{spec.name}/releases/latest"
            )
        else:
            api_url = mirror.url_template
        data = await self._fetch_json(
            api_url,
            headers={"User-Agent": "ChzzkTube-Provisioner/1.0"},
        )
        if not data:
            return None, None, None, None, None
        tag_name = data.get("tag_name")
        assets = filter_assets(data.get("assets", []), spec)
        if tag_name and assets:
            asset = assets[0]
            archive_type = self._archive_type_from(asset["name"], spec)
            return tag_name, asset["browser_download_url"], None, mirror.name, archive_type

        return None, None, None, None, None

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
        except Exception:
            pass
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
        ok_count = 0
        fail_count = 0
        for plan, dl_result in zip(plans, results):
            if not dl_result.success:
                # 다운로드 실패: TUI 진행 라인 실패로 마무리, F12 실패 출력
                self._finalize_progress_line(plan.component, False, f"download failed: {dl_result.error[:50]}")
                self._emit(
                    "DEPS", "FAIL", plan.component.upper(),
                    f"download failed: {dl_result.error[:100]}",
                    component_id=f"deps_{plan.component}", is_progress=False,
                )
                fail_count += 1
                final_results.append(ProvisionResult(
                    plan.component, False, error=f"download failed: {dl_result.error}"
                ))
                continue

            installed_path = await self._extract_and_install(plan, dl_result.task.dest, dl_result.sha256 or "")

            if isinstance(installed_path, str):
                # 설치 실패
                self._finalize_progress_line(plan.component, False, f"install failed: {installed_path[:50]}")
                self._emit(
                    "DEPS", "FAIL", plan.component.upper(),
                    f"install failed: {installed_path}",
                    component_id=f"deps_{plan.component}", is_progress=False,
                )
                fail_count += 1
                final_results.append(ProvisionResult(
                    plan.component, False, error=f"install failed: {installed_path}"
                ))
                continue

            verify_result = Verifier.verify(plan.spec, installed_path)
            if not verify_result.success:
                # 검증 실패
                self._finalize_progress_line(plan.component, False, f"verification failed: {verify_result.error[:50]}")
                self._emit(
                    "DEPS", "FAIL", plan.component.upper(),
                    f"verification failed: {verify_result.error}",
                    component_id=f"deps_{plan.component}", is_progress=False,
                )
                fail_count += 1
                final_results.append(ProvisionResult(
                    plan.component, False, error=f"verification failed: {verify_result.error}"
                ))
                continue

            # 성공: TUI 진행 라인 100% 완료로 마무리, F12 완료 출력
            self._finalize_progress_line(plan.component, True, f"→ {verify_result.version}")
            self._emit(
                "DEPS", "OK", plan.component.upper(),
                f"{plan.component} {'updated' if plan.is_update else 'installed'} → {verify_result.version}",
                component_id=f"deps_{plan.component}", is_progress=False,
            )
            ok_count += 1
            final_results.append(ProvisionResult(
                plan.component, True, version=verify_result.version,
                action="updated" if plan.is_update else "installed",
                sha256=dl_result.sha256 or "",
            ))

        # 마지막: F12 요약 줄 출력
        self._emit_f12_summary(len(plans), ok_count, fail_count)

        return final_results

    def _finalize_progress_line(self, component: str, success: bool, msg: str):
        """TUI/F12의 같은 진행 라인을 완료/실패 상태로 한 번에 마감한다."""
        pct = 100 if success else 0
        status = "completed" if success else "failed"
        event = emit_component(
            "DEPS", "OK" if success else "FAIL", component.upper(),
            self._fmt_progress(pct, "", f"{status} {msg}"),
            is_status=False,            # ← True에서 False로 교정하여 삭제 방지
            is_error=not success,
        )
        event.component_id = f"deps_{component}"
        event.is_progress = False

        if not self._emit_via_log(event):
            raw_log.raw(
                "provisioning", event, to_tui=True,
                is_error=not success,
                component_id=event.component_id, is_progress=False,
            )
        self._active_progress.pop(component, None)

    def _ensure_nodejs_npm_links(self, node_dir: Path):
        """Node.js 설치 후 npm/npx 심볼릭 링크 보장."""
        try:
            bin_dir = node_dir / "bin"
            lib_npm = node_dir / "lib" / "node_modules" / "npm"
            if not lib_npm.exists():
                return
            
            npm_cli = lib_npm / "bin" / "npm-cli.js"
            npx_cli = lib_npm / "bin" / "npx-cli.js"
            
            # npm symlink
            npm_link = bin_dir / "npm"
            if npm_cli.exists() and not npm_link.exists():
                npm_link.symlink_to(os.path.relpath(npm_cli, bin_dir))
            
            # npx symlink
            npx_link = bin_dir / "npx"
            if npx_cli.exists() and not npx_link.exists():
                npx_link.symlink_to(os.path.relpath(npx_cli, bin_dir))
                
            # 실행 권한 보장
            for link in (npm_link, npx_link):
                if link.exists() or link.is_symlink():
                    try:
                        os.chmod(link, 0o755)
                    except OSError:
                        pass
        except Exception:
            pass

    async def _extract_and_install(self, plan: ProvisionPlan, archive: Path, sha256: str) -> Path:
        """아카이브 추출/설치 수행."""
        # stdlib-only: zip/tar.gz/tar.xz/whl/server만 지원, 7z 등 외부 의존성 차단
        if plan.archive_type not in ("zip", "tar.gz", "tar.xz", "whl", "server"):
            return f"unsupported archive type: {plan.archive_type} — stdlib-only"

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

            elif plan.archive_type in ("tar.gz", "tar.xz"):
                with tempfile.TemporaryDirectory(prefix=f"cz_{plan.component}_") as td:
                    mode = "r:gz" if plan.archive_type == "tar.gz" else "r:xz"
                    with tarfile.open(archive, mode) as tar:
                        # [초천재의 무결점 보안] gz/xz 가리지 않고 Python 3.12+ safe filter 강제
                        tar.extractall(td, filter="data")

                    dest = self.base_dir / plan.component
                    # 중첩된 Cellar/bin 및 일반 단일 루트 구조를 한 번에 평탄화 승격
                    _promote_extracted_binaries(td, dest, plan.component)

                    # Node.js 런타임일 경우 심볼릭 링크 일관 보장
                    if plan.component == "node":
                        self._ensure_nodejs_npm_links(dest)

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
            self._emit(
                "DEPS", "OK", "PY", f"overlay refreshed: {path}",
                component_id="deps_PY", is_progress=False,
            )
        except Exception as e:
            self._emit(
                "DEPS", "WARN", "PY", f"overlay refresh failed: {e}",
                component_id="deps_PY", is_progress=False,
            )

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
            self._emit(
                "DEPS", "SKIP", "DEPS", "all components up-to-date",
                component_id="deps_SUMMARY", is_progress=False,
            )
            return []
        
        results = await self.provision(plans)
        await self.commit(plans, results)
        
        ok_count = sum(1 for r in results if r.success)
        fail_count = len(results) - ok_count
        if fail_count == 0:
            self._emit(
                "DEPS", "DONE", "DEPS", f"provisioned {ok_count} components",
                component_id="deps_SUMMARY", is_progress=False,
            )
        else:
            self._emit(
                "DEPS", "WARN", "DEPS", f"{ok_count} ok, {fail_count} failed",
                component_id="deps_SUMMARY", is_progress=False,
            )
        
        return results
