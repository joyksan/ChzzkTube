"""Sync Bridge — 비동기 ProvisioningManager를 동기 컨텍스트에서 호출.

기존 동기 함수(components.ensure_ffmpeg, node_provider.ensure_node_runtime 등)가
ProvisioningManager(async)를 직접 호출할 수 있게 하는 어댑터.

로그 버스 정책: 모든 동작은 raw_log → LogEvent 단일 경로.
"""
import asyncio
from typing import Optional

from chzzktube.infra.provisioning.manager import ProvisioningManager, ProvisionResult


def provision_component_sync(
    component: str,
    log_func=None,
    channel: str = "stable",
    force: bool = False,
) -> Optional[ProvisionResult]:
    """단일 구성요소 동기 수급 — 기존 동기 코드에서 호출.

    Args:
        component: 구성요소명 (yt-dlp, ffmpeg, node, bgutil)
        log_func: 로그 콜백 (LogEvent 수신)
        channel: stable / nightly
        force: 이미 최신이어도 강제 재수급

    Returns:
        ProvisionResult (성공/실패) 또는 None (수급 대상 없음 = 이미 최신)
    """
    async def _run():
        mgr = ProvisioningManager(log_func=log_func)
        plans = await mgr.resolve(stale_only=not force, channel=channel)
        target = [p for p in plans if p.component == component]
        if not target:
            return None  # 이미 최신
        results = await mgr.provision(target)
        await mgr.commit(target, results)
        return results[0] if results else None

    return asyncio.run(_run())


def provision_all_sync(
    log_func=None,
    channel: str = "stable",
    stale_only: bool = True,
) -> list[ProvisionResult]:
    """전체 구성요소 동기 수급."""
    async def _run():
        mgr = ProvisioningManager(log_func=log_func)
        return await mgr.ensure_all(stale_only=stale_only, channel=channel)

    return asyncio.run(_run())


def resolve_all_sync(
    channel: str = "stable",
    stale_only: bool = False,
) -> list:
    """전체 구성요소 플랜 조회 (다운로드 없이)."""
    async def _run():
        mgr = ProvisioningManager()
        return await mgr.resolve(stale_only=stale_only, channel=channel)

    return asyncio.run(_run())