import re
import sys

FILE_PATH = "config.py"

try:
    with open(FILE_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    # 큰따옴표/작은따옴표 및 한글/특수문자 괄호 조합까지 모두 허용하는 정규식
    pattern = r'(APP_VERSION\s*=\s*["\']v)(\d+)\.(\d+)\.(\d+)(.*?["\'])'

    def bump_patch(match):
        prefix = match.group(1)         # APP_VERSION = "v
        major = match.group(2)          # 3
        minor = match.group(3)          # 0
        patch = int(match.group(4)) + 1 # 0 -> 1
        suffix = match.group(5)         #  (PyQt6안정화버전)"
        
        new_ver = f"{prefix}{major}.{minor}.{patch}{suffix}"
        print(f"[Labmem 004] Version Bump: {match.group(0)} -> {new_ver}")
        return new_ver

    updated_content, count = re.subn(pattern, bump_patch, content)

    if count > 0:
        with open(FILE_PATH, "w", encoding="utf-8") as f:
            f.write(updated_content)
        print("[Labmem 004] config.py 버전 업그레이드 성공!")
    else:
        print("[Labmem 004 ERROR] config.py에서 _APP_VERSION 패턴을 찾지 못했습니다!")
        sys.exit(1)

except Exception as e:
    print(f"[Labmem 004 CRITICAL] 오류 발생: {e}")
    sys.exit(1)