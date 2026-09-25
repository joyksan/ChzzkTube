"""Executor — 프로비저닝 실행 (download → verify 단계 담당).

Planner가 생성한 플랜을 받아 다운로드, 추출/설치, 검증을 수행.
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
from chzzktube.infra.provisioning.downloader import ParallelDownloader, DownloadTask
from chzzktube.infra.provisioning.verifier import Verifier
from chzzktube.infra.provisioning.manifest import ProvisionManifest, ComponentRecord
import chzzktube.core.raw_log as raw_log
from chzzktube.core.log_emitter import emit_component, emit_progress
from chzzktube.core.log_event import LogEvent


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
    """Homebrew Bottle의 중첩된 Cellar/bin 구조 속에서 바이너리를 색출해 target_dest/bin/으로 승격시킵니다."""
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

        # 진행률 메시지
        progress_msg = f"{downloaded_mb:.1f}/{total_mb:.1f} MB"
        if eta_str:
            progress_msg += f" ETA {eta_str}"

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
    def _format_eta(seconds: float) -> str:
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            return f"{int(seconds // 60)}m {int(seconds % 60)}s"
        else:
            return f"{int(seconds // 3600)}h {int((seconds % 3600) // 60)}m"

    @staticmethod
    def _fmt_progress(pct: int, speed: str, msg: str = "") -> str:
        """TUI 규격 칼정렬: strip() 무시 정렬 포맷"""
        bar = "█" * (pct // 10) + "░" * (10 - pct // 10)

        pct_val = min(max(pct, 0), 100)
        pct_str = f"{pct_val:3d}%"

        speed_padded = f"{speed:>10}" if speed else " " * 10

        msg_str = f" · {msg}" if msg else ""
        return f"{pct_str} · {speed_padded} [{bar}]{msg_str}"