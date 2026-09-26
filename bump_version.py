### bump_version.py - config.py와 pyproject.toml 원자적 버전 범프 스크립트
import re
import sys

CONFIG_PATH = "chzzktube/core/config.py"
PYPROJECT_PATH = "pyproject.toml"

try:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config_content = f.read()

    # APP_VERSION = "vX.Y.Z" 패턴
    cfg_pattern = r'((?:_)?APP_VERSION\s*=\s*["\']v)(\d+)\.(\d+)\.(\d+)(.*?["\'])'
    match = re.search(cfg_pattern, config_content)
    if not match:
        print("[Labmem 004 ERROR] config.py에서 APP_VERSION 패턴을 찾지 못했습니다!")
        sys.exit(1)

    major = match.group(2)
    minor = match.group(3)
    old_patch = int(match.group(4))
    new_patch = old_patch + 1

    old_ver = f"{major}.{minor}.{old_patch}"
    new_ver = f"{major}.{minor}.{new_patch}"

    # 1. config.py 갱신 (APP_VERSION 및 _APP_VERSION 일괄 갱신)
    def bump_cfg(m):
        prefix = m.group(1)
        suffix = m.group(5)
        return f"{prefix}{major}.{minor}{'.' if m.group(3) else ''}{new_patch}{suffix}"

    new_config, cfg_count = re.subn(cfg_pattern, f"\\g<1>{major}.{minor}.{new_patch}\\g<5>", config_content)
    if cfg_count == 0:
        print("[Labmem 004 ERROR] config.py 치환 실패!")
        sys.exit(1)

    # 2. pyproject.toml 갱신 (version = "X.Y.Z")
    with open(PYPROJECT_PATH, "r", encoding="utf-8") as f:
        toml_content = f.read()

    toml_pattern = r'(version\s*=\s*["\'])(\d+\.\d+\.\d+)(["\'])'
    new_toml, toml_count = re.subn(toml_pattern, f"\\g<1>{new_ver}\\g<3>", toml_content)
    if toml_count == 0:
        print("[Labmem 004 ERROR] pyproject.toml에서 version 패턴을 찾지 못했습니다!")
        sys.exit(1)

    # 원자적 쓰기
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        f.write(new_config)
    with open(PYPROJECT_PATH, "w", encoding="utf-8") as f:
        f.write(new_toml)

    print(f"[Labmem 004] Version Bump 성공: v{old_ver} -> v{new_ver}")
    print(f"  - {CONFIG_PATH}: v{new_ver}")
    print(f"  - {PYPROJECT_PATH}: {new_ver}")

except (OSError, re.error) as e:
    print(f"[Labmem 004 CRITICAL] 오류 발생: {e}")
    sys.exit(1)
