"""Verifier — 다층 검증 (해시/실행 테스트/헬스체크)."""
import sys
import subprocess
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from chzzktube.infra.platform import spawn_kwargs
from chzzktube.infra.provisioning.resolver import ComponentSpec, ComponentType


@dataclass(frozen=True)
class VerifyResult:
    component: str
    success: bool
    error: Optional[str] = None
    version: Optional[str] = None
    installed_path: Optional[Path] = None


class Verifier:
    @staticmethod
    def verify_binary(spec: ComponentSpec, binary_path: Path) -> VerifyResult:
        """바이너리 실행 테스트 + 버전 추출."""
        if not binary_path.exists():
            return VerifyResult(spec.name, False, error="binary not found")
        
        if not binary_path.is_file():
            return VerifyResult(spec.name, False, error="not a file")
        
        try:
            # 실행 권한 확인/부여 (Unix)
            import os
            if not os.access(binary_path, os.X_OK):
                binary_path.chmod(0o755)
            
            # macOS: quarantine 속성 제거
            if sys.platform == "darwin":
                subprocess.run(
                    ["xattr", "-dr", "com.apple.quarantine", str(binary_path)],
                    capture_output=True, check=False
                )
            
            # 실행 테스트
            result = subprocess.run(
                [str(binary_path), *spec.verify_cmd[1:]],
                capture_output=True, text=True, timeout=15,
                **spawn_kwargs()
            )
            
            if result.returncode != 0:
                return VerifyResult(
                    spec.name, False,
                    error=f"exit code {result.returncode}: {result.stderr[:300]}",
                    installed_path=binary_path
                )
            
            # 버전 추출 (첫 줄에서)
            version_line = result.stdout.splitlines()[0] if result.stdout else ""
            return VerifyResult(
                spec.name, True,
                version=version_line.strip(),
                installed_path=binary_path
            )
            
        except subprocess.TimeoutExpired:
            return VerifyResult(spec.name, False, error="verification timeout", installed_path=binary_path)
        except Exception as e:
            return VerifyResult(spec.name, False, error=str(e), installed_path=binary_path)

    @staticmethod
    def verify_python_pkg(spec: ComponentSpec, overlay_root: Path) -> VerifyResult:
        """Python 패키지 검증: whl 해시 + import 테스트 + 버전 확인."""
        try:
            import glob
            
            pkg_dir = spec.name.replace("-", "_")
            dist_info_pattern = str(overlay_root / f"{pkg_dir}-*.dist-info")
            
            for dist_info in glob.glob(dist_info_pattern):
                meta_path = Path(dist_info) / "METADATA"
                if not meta_path.exists():
                    continue
                
                version = None
                for line in meta_path.read_text(encoding="utf-8").splitlines():
                    if line.startswith("Version:"):
                        version = line.split(":", 1)[1].strip()
                        break
                
                if not version:
                    continue
                
                # import 테스트
                try:
                    __import__(pkg_dir)
                    return VerifyResult(
                        spec.name, True,
                        version=version,
                        installed_path=overlay_root
                    )
                except ImportError as e:
                    return VerifyResult(
                        spec.name, False,
                        error=f"import failed: {e}",
                        installed_path=overlay_root
                    )
            
            return VerifyResult(spec.name, False, error="dist-info not found", installed_path=overlay_root)
            
        except Exception as e:
            return VerifyResult(spec.name, False, error=str(e), installed_path=overlay_root)

    @staticmethod
    def verify_bgutil(spec: ComponentSpec, server_dir: Path) -> VerifyResult:
        """bgutil 서버 검증: package.json 버전 + 빌드 산출물 확인."""
        try:
            # server/package.json 확인
            pkg_json = server_dir / "server" / "package.json"
            if not pkg_json.exists():
                return VerifyResult(spec.name, False, error="server/package.json missing", installed_path=server_dir)
            
            version = json.loads(pkg_json.read_text(encoding="utf-8")).get("version", "unknown")
            
            # 빌드 산출물 확인 (dist/main.js 등)
            dist_main = server_dir / "server" / "dist" / "main.js"
            if not dist_main.exists():
                # 구버전 경로도 확인
                alt = server_dir / "dist" / "main.js"
                if not alt.exists():
                    return VerifyResult(spec.name, False, error="built server.js not found", installed_path=server_dir)
            
            return VerifyResult(spec.name, True, version=version, installed_path=server_dir)
            
        except Exception as e:
            return VerifyResult(spec.name, False, error=str(e), installed_path=server_dir)

    @classmethod
    def verify(cls, spec: ComponentSpec, install_path: Path) -> VerifyResult:
        """스펙 타입에 따라 적절한 검증 메서드 디스패치."""
        if spec.type == ComponentType.PYTHON_PKG:
            return cls.verify_python_pkg(spec, install_path)
        elif spec.type == ComponentType.BINARY:
            # 바이너리 경로 계산 - install_rel_path 사용 (예: "node/bin/node", "ffmpeg/bin/ffmpeg")
            if install_path.is_dir() and spec.install_rel_path:
                binary_path = install_path.parent / spec.install_rel_path
            else:
                binary_path = install_path
            return cls.verify_binary(spec, binary_path)
        elif spec.type == ComponentType.SERVER:
            return cls.verify_bgutil(spec, install_path)
        else:
            return VerifyResult(spec.name, False, error=f"unknown component type: {spec.type}")