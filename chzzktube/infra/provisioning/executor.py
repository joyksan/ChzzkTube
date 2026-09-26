"""Executor — 프로비저닝 실행 (download → verify 단계 담당).

Planner가 생성한 플랜을 받아 다운로드, 추출/설치, 검증을 수행.
"""
import shutil
import sys
import tarfile
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

from chzzktube.core import raw_log
from chzzktube.core.log_emitter import emit_component
from chzzktube.core.log_event import LogEvent
from chzzktube.core.raw_log import log_f12_cli, log_f12_net
from chzzktube.infra.platform import astrip_macos_quarantine, strip_macos_quarantine
from chzzktube.infra.provisioning.downloader import DownloadTask, ParallelDownloader
from chzzktube.infra.provisioning.planner import ProvisionPlan
from chzzktube.infra.provisioning.verifier import Verifier


@dataclass
class ProvisionResult:
    component: str
    success: bool
    version: str | None = None
    error: str | None = None
    action: str = ""
    sha256: str = ""


_SCOPE_MAP = {"ytdlp": "YTDL", "ffmpeg": "FFMP", "node": "NODE", "bgutil": "BGUT", "pot": "POT"}

def _to_scope(comp: str) -> str:
    return _SCOPE_MAP.get(str(comp).lower(), str(comp).upper()[:5])


def _promote_extracted_binaries(temp_dir: str, target_dest: Path, component_name: str) -> Path:
    """아카이브 추출 산출물을 target_dest로 배치 (node 레이아웃 보존, ffmpeg 검증/호스트 폴백, bgutil 서버 전개)."""
    td_path = Path(temp_dir)
    target_dest.mkdir(parents=True, exist_ok=True)

    # 1. node: npm 실행에 필요한 lib/node_modules/npm 구조 전체 보존
    if component_name == "node":
        entries = [e for e in td_path.iterdir() if e.is_dir()]
        src_dir = entries[0] if len(entries) == 1 else td_path
        for item in src_dir.iterdir():
            dest_item = target_dest / item.name
            if dest_item.exists():
                if dest_item.is_dir():
                    shutil.rmtree(dest_item, ignore_errors=True)
                else:
                    dest_item.unlink()
            shutil.move(str(item), str(dest_item))
        if sys.platform != "win32":
            for b in ("node", "npm", "npx"):
                bp = target_dest / "bin" / b
                if bp.exists():
                    bp.chmod(0o755)
                    strip_macos_quarantine(str(bp))
        return target_dest

    # 2. bgutil 서버: 소스 트리 전개 + .version 기록
    if component_name in ("bgutil", "bgutil-ytdlp-pot-provider"):
        entries = [e for e in td_path.iterdir() if e.is_dir()]
        src_dir = entries[0] if len(entries) == 1 else td_path
        for item in src_dir.iterdir():
            dest_item = target_dest / item.name
            if dest_item.exists():
                if dest_item.is_dir():
                    shutil.rmtree(dest_item, ignore_errors=True)
                else:
                    dest_item.unlink()
            shutil.move(str(item), str(dest_item))
        return target_dest

    # 3. ffmpeg: ffmpeg/ffprobe 바이너리 색출 및 배치
    target_bin_dir = target_dest / "bin"
    target_bin_dir.mkdir(parents=True, exist_ok=True)

    # macOS: 아카이브 내 미서명 바이너리의 AMFI 커널 트랩 방지를 위해 호스트 ffmpeg 우선 승격
    if sys.platform == "darwin":
        for host_bin in (Path("/opt/homebrew/bin/ffmpeg"), Path("/usr/local/bin/ffmpeg")):
            if host_bin.is_file():
                dest_ffmpeg = target_bin_dir / "ffmpeg"
                shutil.copy2(host_bin, dest_ffmpeg)
                dest_ffmpeg.chmod(0o755)
                strip_macos_quarantine(str(dest_ffmpeg))
                host_probe = host_bin.parent / "ffprobe"
                if host_probe.is_file():
                    dest_probe = target_bin_dir / "ffprobe"
                    shutil.copy2(host_probe, dest_probe)
                    dest_probe.chmod(0o755)
                    strip_macos_quarantine(str(dest_probe))
                return target_dest

    targets = ("ffmpeg", "ffprobe")
    found_bins = {}

    for p in td_path.rglob("*"):
        if p.is_file() and p.name.lower() in [t + (".exe" if sys.platform == "win32" else "") for t in targets]:
            stem = p.name.replace(".exe", "").lower()
            if stem not in found_bins:
                found_bins[stem] = p

    for stem, src_path in found_bins.items():
        dest_file = target_bin_dir / src_path.name
        if dest_file.exists():
            dest_file.unlink()
        shutil.copy2(src_path, dest_file)
        if sys.platform != "win32":
            dest_file.chmod(dest_file.stat().st_mode | 0o755)
            strip_macos_quarantine(str(dest_file))

    # Windows: DLL 동반 수급 — 아카이브 내 동반 DLL을 target_bin_dir로 복사
    if sys.platform == "win32":
        for dll_file in td_path.rglob("*.dll"):
            dest_dll = target_bin_dir / dll_file.name
            if not dest_dll.exists():
                shutil.copy2(dll_file, dest_dll)
                log_f12_net(f"copied companion DLL: {dll_file.name} -> {dest_dll}")

    return target_dest


class Executor:
    """download → verify 단계 담당."""

    def __init__(self, base_dir: Path, log_func=None):
        self.base_dir = base_dir
        self.log = log_func
        self._active_progress: dict[str, dict] = {}
        self._downloader = ParallelDownloader(progress_cb=self._on_progress)

    def _on_progress(self, component: str, downloaded: int, total: int, speed_bps: float = 0.0, eta_sec: float = 0.0):
        """다운로드 진행률 하트비트 — TUI: 컴포넌트별 개별 갱신형 라인, F12: 개별 누적."""
        if total <= 0:
            return

        pct = int(downloaded / total * 100)
        downloaded_mb = downloaded / (1024 * 1024)
        total_mb = total / (1024 * 1024)

        speed_str = self._format_speed(speed_bps)
        nm_str = f"{downloaded_mb:.1f}/{total_mb:.1f} MB"

        # 개별 진행 저장 (100% 완료 및 추출/실패 후에도 bar, pct, speed, n/m 유지)
        self._active_progress[component] = {
            "pct": pct,
            "speed": speed_str,
            "nm": nm_str,
            "downloaded_mb": downloaded_mb,
            "total_mb": total_mb,
        }

        # 다운로드 중에는 msg는 공백 (bar, pct, speed, n/m만 배치)
        line = self._fmt_progress(pct, speed_str, nm_str, msg="")

        event = emit_component(
            "DEPS", "RUN", _to_scope(component),
            line,
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

    @staticmethod
    def _format_speed(bps: float) -> str:
        """GB/s 승격으로 자릿수 폭주를 원천 차단"""
        if bps >= 1024 * 1024 * 1024:
            return f"{bps / (1024 * 1024 * 1024):.1f} GB/s"
        if bps >= 1024 * 1024:
            return f"{bps / (1024 * 1024):.1f} MB/s"
        if bps >= 1024:
            return f"{bps / 1024:.1f} KB/s"
        if bps > 0:
            return f"{bps:.0f} B/s"
        return ""

    @staticmethod
    def _fmt_progress(pct: int, speed: str = "", nm: str = "", msg: str = "") -> str:
        """TUI 규격: bar, pct, speed, n/m, msg 순으로 배치 (ETA 삭제)."""
        pct_val = min(max(pct, 0), 100)
        bar = "█" * (pct_val // 10) + "░" * (10 - pct_val // 10)
        pct_str = f"{pct_val:3d}%"
        speed_padded = f"{speed:>10}" if speed else " " * 10

        line = f"[{bar}] {pct_str} · {speed_padded}"
        if nm:
            line += f" · {nm}"
        if msg:
            line += f" · {msg}"
        return line

    async def provision(self, plans: list[ProvisionPlan]) -> list[ProvisionResult]:
        """플랜 실행: 다운로드 → 추출/설치 → 검증."""
        if not plans:
            return []
        
        self._plan_versions = {plan.component: plan.version for plan in plans}

        tasks = []
        for plan in plans:
            dest = self.base_dir / "downloads" / plan.component
            dest.parent.mkdir(parents=True, exist_ok=True)
            tasks.append(DownloadTask(
                url=plan.download_url,
                dest=dest,
                component=plan.component,
            ))
            log_f12_net(f"queue download: {plan.component} -> {plan.download_url}")

        dl_results = await self._downloader.download_all(tasks)

        final_results = []
        for plan in plans:
            comp_id = f"deps_{plan.component}"
            scope = _to_scope(plan.component)
            dl_result = next((r for r in dl_results if r.task.component == plan.component), None)

            prog = self._active_progress.get(plan.component, {})
            pct = prog.get("pct", 100)
            speed = prog.get("speed", "")
            nm = prog.get("nm", "")

            if not dl_result or not dl_result.success:
                error_msg = dl_result.error if dl_result else "download task vanished"
                fail_line = self._fmt_progress(pct, speed, nm, f"download failed: {error_msg}")
                self._emit("DEPS", "FAIL", scope, fail_line, component_id=comp_id, is_progress=False, is_error=True)
                log_f12_net(f"download failed for {plan.component}: {error_msg}", is_error=True)
                final_results.append(ProvisionResult(
                    plan.component, False, error=error_msg, action="fail"
                ))
                continue

            # 1. 추출 단계: bar, pct, speed, n/m 유지 + msg='extracting...'
            extract_line = self._fmt_progress(100, speed, nm, "extracting...")
            self._emit("DEPS", "RUN", scope, extract_line, component_id=comp_id, is_progress=True, is_status=True)
            log_f12_net(f"extracting {plan.component} ({plan.archive_type}) -> {plan.install_path}")

            installed_path = await self._extract_and_install(plan, dl_result.task.dest)
            
            if isinstance(installed_path, str):  # str means error message
                fail_line = self._fmt_progress(100, speed, nm, f"install failed: {installed_path}")
                self._emit("DEPS", "FAIL", scope, fail_line, component_id=comp_id, is_progress=False, is_error=True)
                log_f12_net(f"install failed for {plan.component}: {installed_path}", is_error=True)
                final_results.append(ProvisionResult(
                    plan.component, False, error=f"install failed: {installed_path}", action="fail"
                ))
                continue

            # 2. 검증 단계
            if plan.spec.verify_cmd:
                v_res = Verifier.verify(plan.spec, installed_path)
                cmd_str = f"{installed_path} {' '.join(plan.spec.verify_cmd[1:])}"
                log_f12_cli(cmd_str, v_res.version if v_res.success else v_res.error, is_error=not v_res.success)
                if not v_res.success:
                    fail_line = self._fmt_progress(100, speed, nm, f"verification failed: {v_res.error}")
                    self._emit("DEPS", "FAIL", scope, fail_line, component_id=comp_id, is_progress=False, is_error=True)
                    log_f12_net(f"verification failed for {plan.component}: {v_res.error}", is_error=True)
                    final_results.append(ProvisionResult(
                        plan.component, False, error=f"verification failed: {v_res.error}", action="fail"
                    ))
                    continue
                log_f12_net(f"verified {plan.component} binary -> {v_res.version or plan.version}")

            # 3. 마감 확정 (Commit): bar, pct, speed, n/m 유지 + msg='{component} installed' / '{component} updated'
            action_desc = "updated" if plan.is_update else "installed"
            status_text = f"{plan.component} {action_desc}"
            done_line = self._fmt_progress(100, speed, nm, status_text)
            self._emit("DEPS", "OK", scope, done_line, component_id=comp_id, is_progress=False, is_status=False)
            log_f12_net(f"provision complete: {plan.component} ({action_desc}) -> {plan.version}")
            final_results.append(ProvisionResult(
                plan.component, True, version=plan.version, sha256=plan.expected_sha256 or "", action="update" if plan.is_update else "install"
            ))

        return final_results

    async def _extract_and_install(self, plan: ProvisionPlan, archive: Path) -> Path | str:
        """아카이브 추출/설치 수행."""
        try:
            if plan.archive_type == "whl":
                from chzzktube.infra.updater import _extract_pylib_whl
                overlay_root = self.base_dir / ".pylib"
                prefix = plan.component + "-" if plan.component != "yt-dlp" else "yt_dlp-"
                with zipfile.ZipFile(archive) as z:
                    z.extractall(str(overlay_root))
                _extract_pylib_whl(str(archive), str(overlay_root), prefix)
                return overlay_root

            elif plan.archive_type in ("zip", "server"):
                with tempfile.TemporaryDirectory(prefix=f"cz_{plan.component}_") as td:
                    with zipfile.ZipFile(archive) as z:
                        z.extractall(td)
                    dest = plan.install_path
                    promoted = _promote_extracted_binaries(td, dest, plan.component)
                    if plan.archive_type == "server" and plan.version:
                        try:
                            (dest / ".version").write_text(str(plan.version), encoding="utf-8")
                            if (dest / "server").is_dir():
                                (dest / "server" / ".version").write_text(str(plan.version), encoding="utf-8")
                        except OSError as e:
                            # .version 마커 기록 실패는 설치를 막지 않는다 (F12 진단 기록만)
                            log_f12_net(
                                "failed to write .version marker for "
                                f"{plan.component}: {type(e).__name__}: {e}",
                                is_error=True,
                            )
                    return promoted

            elif plan.archive_type == "tar.gz":
                with tempfile.TemporaryDirectory(prefix=f"cz_{plan.component}_") as td:
                    with tarfile.open(archive, "r:gz") as tar:
                        tar.extractall(td)
                    dest = plan.install_path
                    return _promote_extracted_binaries(td, dest, plan.component)

            elif plan.archive_type == "tar.xz":
                with tempfile.TemporaryDirectory(prefix=f"cz_{plan.component}_") as td:
                    with tarfile.open(archive, "r:xz") as tar:
                        tar.extractall(td, filter="data")
                    dest = plan.install_path
                    return _promote_extracted_binaries(td, dest, plan.component)

            elif plan.archive_type == "binary":
                dest = plan.install_path
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(archive, dest)
                if sys.platform != "win32":
                    dest.chmod(0o755)
                    # async 컨텍스트 — xattr 프로세스는 worker thread에서 실행 (블로킹 금지)
                    await astrip_macos_quarantine(str(dest))
                return dest

            return f"unknown archive type: {plan.archive_type}"

        except PermissionError as e:
            return f"PermissionError: file locked or access denied ({e}) — close conflicting programs and restart app"
        except FileNotFoundError as e:
            return f"FileNotFoundError: required file missing ({e})"
        except OSError as e:
            if getattr(e, "winerror", None) == 32:
                return "file in use by another process (WinError 32) — close background processes and restart app"
            return f"{type(e).__name__}: {e}"
