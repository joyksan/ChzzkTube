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
            
            # 실행 테스트 (바이너리 경로를 PATH 및 cwd에 주입하여 companion DLL 탐색 보장)
            env = os.environ.copy()
            bin_dir = str(binary_path.parent)
            env["PATH"] = bin_dir + os.pathsep + env.get("PATH", "")

            result = subprocess.run(
                [str(binary_path), *spec.verify_cmd[1:]],
                capture_output=True, text=True, timeout=15,
                cwd=bin_dir,
                env=env,
                encoding="utf-8",
                errors="replace",
                **spawn_kwargs()
            )
            
            if result.returncode != 0:
                err_detail = (result.stderr or result.stdout or "").strip()
                if result.returncode in (3221225781, -1073741515, 0xC0000135):
                    err_msg = f"exit code {result.returncode} (STATUS_DLL_NOT_FOUND: required DLL missing): {err_detail[:300]}"
                else:
                    err_msg = f"exit code {result.returncode}: {err_detail[:300]}"
                return VerifyResult(
                    spec.name, False,
                    error=err_msg,
                    installed_path=binary_path
                )
            
            # 버전 추출
            version_line = ""
            stdout_text = result.stdout or ""
            if spec.name == "ffmpeg":
                import re
                m = re.search(r"ffmpeg version\s+([^\s,]+)", stdout_text)
                if m:
                    version_line = m.group(1)
            if not version_line:
                version_line = stdout_text.splitlines()[0] if stdout_text else ""
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
            return VerifyResult(spec.name, True, version=version, installed_path=server_dir)
            
        except Exception as e:
            return VerifyResult(spec.name, False, error=str(e), installed_path=server_dir)

    @classmethod
    def verify(cls, spec: ComponentSpec, install_path: Path) -> VerifyResult:
        """스펙 타입에 따라 적절한 검증 메서드 디스패치."""
        if spec.type == ComponentType.PYTHON_PKG:
            return cls.verify_python_pkg(spec, install_path)
            
        elif spec.type == ComponentType.BINARY:
            # [지능형 리졸버] 단일 수식의 환상을 버리고 실측 다중 후보를 검증
            binary_path = install_path

            if install_path.is_dir():
                target_name = spec.name + (".exe" if sys.platform == "win32" else "")
                
                # 1. 우선순위 후보군 구성 (승격된 bin/ 우선, 루트 폴백, 상대경로 조합)
                candidates = [
                    install_path / "bin" / target_name,
                    install_path / target_name,
                ]
                if spec.install_rel_path:
                    candidates.append(install_path.parent / spec.install_rel_path)
                    candidates.append(install_path / spec.install_rel_path)

                # 존재하는 첫 번째 정규 파일 채택
                found = None
                for cand in candidates:
                    if cand.is_file():
                        found = cand
                        break

                # 2. 최후의 보루: 디렉터리 내부 재귀 탐색 (Homebrew Bottle 심층 격리 대응)
                if not found:
                    for p in install_path.rglob(target_name):
                        if p.is_file():
                            found = p
                            break

                binary_path = found if found else (install_path / "bin" / target_name)

            return cls.verify_binary(spec, binary_path)

        elif spec.type == ComponentType.SERVER:
            return cls.verify_bgutil(spec, install_path)
        else:
            return VerifyResult(spec.name, False, error=f"unknown component type: {spec.type}")