"""ProvisioningManager — 외부 라이브러리 수급/검증/커밋 단일 오케스트레이터.

로그 버스 정책 (HANDOVER §5-21):
- 모든 앱 동작은 raw_log.raw() → LogEvent 단일 경로
- Qt 시그널은 결과/제어/브리지에만 사용 (log_full/log_concise 시그널 금지)
- 발행자가 라벨과 to_tui 결정
- history ⊇ full ⊇ TUI (큐 2048, 버퍼 4096 유한)

리팩토링(v3.11.0): Planner/Executor/Committer로 책임 분리
- Planner: resolve 단계 (최신 버전/URL/sha256 조회 → 플랜 생성)
- Executor: provision 단계 (다운로드 → 추출/설치 → 검증)
- Committer: commit 단계 (manifest 저장 + overlay/PATH 갱신)
"""
from pathlib import Path

from chzzktube.core import config, raw_log
from chzzktube.core.log_emitter import emit_component
from chzzktube.infra.provisioning.committer import Committer
from chzzktube.infra.provisioning.executor import Executor, ProvisionResult
from chzzktube.infra.provisioning.planner import Planner, ProvisionPlan


class ProvisioningManager:
    """단일 파사드 — Planner/Executor/Committer를 조합하여 resolve → download → verify → commit 수행."""

    def __init__(self, log_func=None):
        self.base_dir = Path(config.writable_base())
        self.log = log_func
        self.planner = Planner(self.base_dir, log_func)
        self.executor = Executor(self.base_dir, log_func)
        self.committer = Committer(self.base_dir, log_func)

    async def resolve(self, stale_only: bool = False, channel: str = "stable") -> list[ProvisionPlan]:
        """모든 구성요소에 대해 최신 버전 확인 + 플랜 생성 (Planner 위임)."""
        return await self.planner.resolve(stale_only=stale_only, channel=channel)

    async def provision(self, plans: list[ProvisionPlan]) -> list[ProvisionResult]:
        """플랜 실행: 다운로드 → 추출/설치 → 검증 (Executor 위임)."""
        return await self.executor.provision(plans)

    async def commit(self, plans: list[ProvisionPlan], results: list[ProvisionResult]) -> None:
        """manifest 갱신 + 오버레이/환경변수 리로드 (Committer 위임)."""
        self.committer.commit(plans, results)

    async def ensure_all(self, stale_only: bool = True, channel: str = "stable") -> list[ProvisionResult]:
        """전체 프로비저닝: resolve → download → verify → commit."""
        plans = await self.resolve(stale_only=stale_only, channel=channel)
        if not plans:
            self._emit(
                "DEPS", "SKIP", "DEPS", "all components up-to-date",
                component_id="deps_SUMMARY", is_progress=False,
            )
            return []

        update_comps = [p.component for p in plans if p.is_update]
        install_comps = [p.component for p in plans if not p.is_update]
        if update_comps and install_comps:
            action_summary = f"updating {', '.join(update_comps)}, installing {', '.join(install_comps)}"
        elif update_comps:
            action_summary = f"updating {', '.join(update_comps)}"
        else:
            action_summary = f"installing {', '.join(install_comps)}"

        self._emit(
            "DEPS", "RUN", "DEPS", f"provisioning {len(plans)} components ({action_summary})",
            component_id="deps_SUMMARY", is_progress=False,
        )

        results = await self.provision(plans)
        await self.commit(plans, results)

        ok_count = sum(1 for r in results if r.success)
        fail_count = len(results) - ok_count
        if fail_count == 0:
            self._emit(
                "DEPS", "DONE", "DEPS", f"provisioned {ok_count} components ready",
                component_id="deps_SUMMARY", is_progress=False,
            )
        else:
            fail_names = [r.component for r in results if not r.success]
            self._emit(
                "DEPS", "FAIL", "MAIN",
                f"deps fail ({', '.join(fail_names)}) → check network/F12 logs and restart app",
                component_id="deps_SUMMARY", is_progress=False, is_error=True,
            )

        return results

    def _emit(self, stage, status, scope, msg, is_status=False, is_error=False,
              component_id: str | None = None, is_progress: bool = False, to_tui: bool | None = None):
        """raw_log 버스 단일 경유 — 발행자만 raw_log.raw() 호출 (이중 적재 방지)."""
        evt = emit_component(stage, status, scope, msg, is_status=is_status, is_error=is_error)
        evt.component_id = component_id
        evt.is_progress = is_progress
        if to_tui is None:
            to_tui = is_status or is_progress or is_error or (status in ("OK", "DONE", "FAIL", "READY", "WARN", "SKIP"))
        raw_log.raw(
            "provisioning", evt, to_tui=to_tui, is_error=is_error,
            component_id=component_id, is_progress=is_progress,
        )

    async def _on_progress(self, component: str, downloaded: int, total: int, speed_bps: float = 0.0, eta_sec: float = 0.0):
        """Executor의 진행률 콜백 위임 — 테스트/브리지 호환용."""
        self.executor._on_progress(component, downloaded, total, speed_bps, eta_sec)
