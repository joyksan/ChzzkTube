"""Committer — 프로비저닝 결과 커밋 (manifest 저장, overlay/PATH 갱신).

Executor가 완료한 결과를 받아 manifest 업데이트, .pylib overlay 리로드, PATH 추가 수행.
"""
import os
import shutil
import time
from pathlib import Path

from chzzktube.core import config, raw_log
from chzzktube.core.log_emitter import emit_component
from chzzktube.core.log_event import LogEvent
from chzzktube.infra.provisioning.manifest import ComponentRecord, ProvisionManifest


class Committer:
    """commit 단계만 담당 — manifest 저장 + overlay/PATH 갱신."""

    def __init__(self, base_dir: Path, log_func=None):
        self.base_dir = base_dir
        self.log = log_func
        self.manifest = ProvisionManifest.load(base_dir)
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
            self.log(event)
        return True

    def commit(self, plans: list, results: list) -> None:
        """manifest 갱신 + 오버레이/환경변수 리로드."""
        now = time.time()

        for plan, result in zip(plans, results):
            if result.success:
                self.manifest.update_component(ComponentRecord(
                    name=plan.component,
                    version=plan.version,
                    source=plan.mirror_name,
                    mirror=plan.mirror_name,
                    install_path=plan.spec.install_rel_path,
                    verified_at=now,
                    verify_version=result.version or plan.version,
                    sha256=getattr(result, "sha256", "") or (plan.expected_sha256 or ""),
                ))

        self.manifest.last_full_update = now
        self.manifest.save(self.base_dir)

        self._refresh_overlay()
        self._refresh_path()

        downloads_dir = self.base_dir / "downloads"
        if downloads_dir.exists():
            shutil.rmtree(downloads_dir, ignore_errors=True)

    def _refresh_overlay(self):
        """.pylib overlay 리로드 (존재 시에만)."""
        try:
            from chzzktube.infra.pylib_bootstrap import bootstrap
            path = bootstrap(clear_caches=True)
            if path:
                self._emit(
                    "DEPS", "OK", "PY", f"overlay refreshed: {path}",
                    component_id="deps_PY", is_progress=False,
                )
        except Exception as e:  # noqa: BLE001 — overlay 리로드 실패는 WARN 발행
            self._emit(
                "DEPS", "WARN", "PY", f"overlay refresh failed: {e}",
                component_id="deps_PY", is_progress=False,
            )

    def _refresh_path(self):
        """PATH에 검증된 binary 디렉토리 추가 (SSOT)."""
        try:
            for name, rec in self.manifest.components.items():
                if name in ("ffmpeg", "node"):
                    target_path = self.base_dir / rec.install_path
                    bin_dir = target_path.parent if target_path.suffix or target_path.name in ("ffmpeg", "node") else target_path

                    if bin_dir.is_dir():
                        path_env = os.environ.get("PATH", "")
                        parts = path_env.split(os.pathsep) if path_env else []
                        bin_str = str(bin_dir)
                        if bin_str not in parts:
                            os.environ["PATH"] = os.pathsep.join([bin_str] + parts)
        except Exception as e:  # noqa: BLE001 — PATH 갱신 실패는 WARN 발행
            self._emit(
                "DEPS", "WARN", "PATH", f"PATH refresh failed: {e}",
                component_id="deps_PATH", is_progress=False,
            )