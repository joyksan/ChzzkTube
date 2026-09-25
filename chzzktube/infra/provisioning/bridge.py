"""Sync Bridge - 비동기 ProvisioningManager를 동기 컨텍스트에서 호출.

기존 동기 함수(components.ensure_ffmpeg, node_provider.ensure_node_runtime 등)가
ProvisioningManager(async)를 직접 호출할 수 있게 하는 어댑터.

로그 버스 정책: 모든 동작은 raw_log -> LogEvent 단일 경로.

[v3.11.0] 이벤트 루프 재사용: asyncio.run() 대신 기존 루프가 있으면 재사용,
없으면 새로 생성. 중첩 호출 시 안전하게 동작. 생성한 루프는 사용 후 close로 정리.
"""
import asyncio
from typing import Optional

from chzzktube.infra.provisioning.manager import ProvisioningManager, ProvisionResult


_created_loops: set[int] = set()


def _get_or_create_event_loop() -> asyncio.AbstractEventLoop:
    """기존 이벤트 루프를 가져오거나 새로 생성.

    asyncio.run()은 매번 새 루프를 만드는데, 중첩 호출 시 RuntimeError 발생.
    이미 실행 중인 루프가 있으면 그것을 재사용한다. 새로 생성한 루프는
    추적하여 나중에 정리한다.
    """
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        # 실행 중인 루프가 없음 - 새로 생성
        loop = asyncio.new_event_loop()
        _created_loops.add(id(loop))
        return loop


def _run_sync(coro) -> object:
    """코루틴을 동기적으로 실행하며 루프 생명주기 관리.

    - 실행 중인 루프가 있으면 재사용 (run_until_complete)
    - 없으면 새로 생성 후 실행 뒤 close로 정리
    """
    loop = _get_or_create_event_loop()
    if loop.is_running():
        # 이미 실행 중인 루프가 있으면 재사용
        return loop.run_until_complete(coro)
    else:
        # 우리가 만든 루프 - 실행 후 close로 정리
        try:
            return loop.run_until_complete(coro)
        finally:
            loop_id = id(loop)
            if loop_id in _created_loops:
                _created_loops.discard(loop_id)
                if not loop.is_closed():
                    loop.close()


def provision_component_sync(
    component: str,
    log_func=None,
    channel: str = "stable",
    force: bool = False,
) -> Optional[ProvisionResult]:
    """단일 구성요소 동기 수급 - 기존 동기 코드에서 호출.

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

    return _run_sync(_run())


def provision_all_sync(
    log_func=None,
    channel: str = "stable",
    stale_only: bool = True,
) -> list[ProvisionResult]:
    """전체 구성요소 동기 수급."""
    async def _run():
        mgr = ProvisioningManager(log_func=log_func)
        return await mgr.ensure_all(stale_only=stale_only, channel=channel)

    return _run_sync(_run())


def resolve_all_sync(
    channel: str = "stable",
    stale_only: bool = False,
) -> list:
    """전체 구성요소 플랜 조회 (다운로드 없이)."""
    async def _run():
        mgr = ProvisioningManager()
        return await mgr.resolve(stale_only=stale_only, channel=channel)

    return _run_sync(_run())
