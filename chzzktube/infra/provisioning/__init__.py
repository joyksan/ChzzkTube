"""Provisioning Package — 외부 라이브러리 수급/검증/매니페스트 단일 진실.

아키텍처:
- Resolver: 버전 해석 & 미러 선택
- Downloader: 병렬 다운로드 & 재시도/폴백
- Verifier: 다층 검증 (해시/실행/헬스체크)
- Manifest: JSON 매니페스트 (단일 진실 공급원)
- Manager: 오케스트레이터 파사드
- Bridge: 동기 컨텍스트 어댑터 (기존 동기 함수 지원)
"""
from chzzktube.infra.provisioning.bridge import (
    provision_all_sync,
    provision_component_sync,
    resolve_all_sync,
)
from chzzktube.infra.provisioning.downloader import (
    DownloadResult,
    DownloadTask,
    ParallelDownloader,
)
from chzzktube.infra.provisioning.manager import (
    ProvisioningManager,
    ProvisionPlan,
    ProvisionResult,
)
from chzzktube.infra.provisioning.manifest import ComponentRecord, ProvisionManifest
from chzzktube.infra.provisioning.resolver import (
    MIRROR_REGISTRY,
    ComponentSpec,
    ComponentType,
    Mirror,
)
from chzzktube.infra.provisioning.verifier import Verifier, VerifyResult

__all__ = [
    "MIRROR_REGISTRY",
    "ComponentRecord",
    "ComponentSpec",
    "ComponentType",
    "DownloadResult",
    "DownloadTask",
    "Mirror",
    "ParallelDownloader",
    "ProvisionManifest",
    "ProvisionPlan",
    "ProvisionResult",
    "ProvisioningManager",
    "Verifier",
    "VerifyResult",
    "provision_all_sync",
    "provision_component_sync",
    "resolve_all_sync",
]