"""버전 단일 진실 공급원(SSOT) 정합성 계약 테스트.

- config.APP_VERSION은 유일한 런타임 진실 공급원이다.
- pyproject.toml의 version은 config.APP_VERSION의 숫자 부분과 정확히 일치해야 한다.
- chzzktube.__version__은 pyproject.toml의 version과 일치해야 한다.
- README.md 및 docs/HANDOVER.md의 버전 선언이 config.APP_VERSION과 일치해야 한다.
"""
import re
from pathlib import Path

import chzzktube
from chzzktube.core import config


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def test_config_version_and_alias():
    """config.APP_VERSION과 _APP_VERSION 하위 호환 별칭이 일치해야 함."""
    assert config.APP_VERSION == config._APP_VERSION
    assert config.APP_VERSION.startswith("v")


def test_package_metadata_version_matches_config():
    """chzzktube.__version__이 config.APP_VERSION 숫자와 일치해야 함."""
    clean_ver = config.APP_VERSION.lstrip("v")
    assert chzzktube.__version__ == clean_ver
    assert chzzktube.APP_VERSION == config.APP_VERSION


def test_pyproject_version_matches_config():
    """pyproject.toml의 version이 config.APP_VERSION과 1:1 일치해야 함."""
    pyproject_path = _repo_root() / "pyproject.toml"
    assert pyproject_path.exists(), "pyproject.toml이 존재하지 않습니다."

    text = pyproject_path.read_text(encoding="utf-8")
    m = re.search(r'version\s*=\s*["\']([^"\']+)["\']', text)
    assert m is not None, "pyproject.toml에서 version을 찾을 수 없습니다."

    pyproject_ver = m.group(1)
    clean_ver = config.APP_VERSION.lstrip("v")
    assert pyproject_ver == clean_ver, f"버전 불일치: pyproject.toml({pyproject_ver}) != config.APP_VERSION({clean_ver})"


def test_readme_version_matches_config():
    """README.md의 버전 표기가 config.APP_VERSION과 일치해야 함."""
    readme_path = _repo_root() / "README.md"
    assert readme_path.exists(), "README.md가 존재하지 않습니다."

    text = readme_path.read_text(encoding="utf-8")
    m = re.search(r'\*\*버전\*\*:\s*`([^`]+)`', text)
    assert m is not None, "README.md에서 버전 표기를 찾을 수 없습니다."

    readme_ver = m.group(1)
    assert readme_ver == config.APP_VERSION, f"버전 불일치: README.md({readme_ver}) != config.APP_VERSION({config.APP_VERSION})"


def test_handover_version_matches_config():
    """HANDOVER.md 머리말의 버전 표기가 config.APP_VERSION과 일치해야 함."""
    handover_path = _repo_root() / "docs" / "HANDOVER.md"
    assert handover_path.exists(), "HANDOVER.md가 존재하지 않습니다."

    text = handover_path.read_text(encoding="utf-8")
    m = re.search(r'-\s*\*\*버전\*\*:\s*`([^`]+)`', text)
    assert m is not None, "HANDOVER.md에서 버전 표기를 찾을 수 없습니다."

    handover_ver = m.group(1)
    assert handover_ver == config.APP_VERSION, f"버전 불일치: HANDOVER.md({handover_ver}) != config.APP_VERSION({config.APP_VERSION})"
