"""Provision Manifest — 단일 진실 공급원 (JSON).

writable_base()/provision_manifest.json에 저장.
모든 구성요소의 버전/출처/경로/검증시점 영구 기록.
"""
import json
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class ComponentRecord:
    name: str
    version: str
    source: str              # "pypi", "github", "nodejs.org", etc.
    mirror: str              # 실제 사용된 미러
    install_path: str        # writable_base 기준 상대 경로
    verified_at: float       # unix timestamp
    verify_version: str      # 검증 시 추출된 버전 문자열
    sha256: str = ""         # 다운로드 파일 해시


@dataclass
class ProvisionManifest:
    schema_version: int = 1
    components: dict[str, ComponentRecord] = field(default_factory=dict)
    last_check: float = 0
    last_full_update: float = 0

    MANIFEST_FILENAME = "provision_manifest.json"

    @classmethod
    def load(cls, base_dir: Path) -> "ProvisionManifest":
        path = base_dir / cls.MANIFEST_FILENAME
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                comps = {
                    k: ComponentRecord(**v) for k, v in data.get("components", {}).items()
                }
                return cls(
                    schema_version=data.get("schema_version", 1),
                    components=comps,
                    last_check=data.get("last_check", 0),
                    last_full_update=data.get("last_full_update", 0),
                )
            except Exception as e:
                import chzzktube.core.raw_log as raw_log
                raw_log.raw("DEPS", f"manifest load error: {type(e).__name__}: {e}", is_error=True, to_tui=False)
        return cls()

    def save(self, base_dir: Path) -> None:
        """원자적 쓰기 (.tmp → rename)."""
        path = base_dir / self.MANIFEST_FILENAME
        data = {
            "schema_version": self.schema_version,
            "components": {k: asdict(v) for k, v in self.components.items()},
            "last_check": self.last_check,
            "last_full_update": self.last_full_update,
        }
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)

    def is_stale(self, name: str, latest_version: str) -> bool:
        """manifest 버전 vs 최신 버전 비교."""
        rec = self.components.get(name)
        if not rec:
            return True
        return rec.version != latest_version

    def get_record(self, name: str) -> Optional[ComponentRecord]:
        return self.components.get(name)

    def update_component(self, record: ComponentRecord) -> None:
        self.components[record.name] = record

    def remove_component(self, name: str) -> None:
        self.components.pop(name, None)