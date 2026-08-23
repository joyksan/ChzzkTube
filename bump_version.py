import re

FILE_PATH = "main.py"

with open(FILE_PATH, "r", encoding="utf-8") as f:
    content = f.read()

# v2.0.1 형태에서 패치 번호(마지막 자리)만 1 증가
def bump_patch(match):
    prefix = match.group(1)   # APP_VERSION = "v
    major = match.group(2)    # 2
    minor = match.group(3)    # 0
    patch = int(match.group(4)) + 1  # 1 -> 2
    suffix = match.group(5)   # (PyQt6)"
    
    new_ver = f'{prefix}{major}.{minor}.{patch}{suffix}'
    print(f"[Labmem 004] Version Bump: {match.group(0)} -> {new_ver}")
    return new_ver

pattern = r'(APP_VERSION\s*=\s*"v)(\d+)\.(\d+)\.(\d+)(.*?")'
updated_content, count = re.subn(pattern, bump_patch, content)

if count > 0:
    with open(FILE_PATH, "w", encoding="utf-8") as f:
        f.write(updated_content)
else:
    print("[WARNING] APP_VERSION 패턴을 찾지 못했습니다.")