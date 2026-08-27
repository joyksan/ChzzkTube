# sync_mirrors.py - .py 소스 → 동일 이름의 .md 미러 자동 동기화 스크립트
"""
사용법:
    python sync_mirrors.py              # 변경된 미러 파일 일괄 동기화
    python sync_mirrors.py --check      # 변경 여부만 확인 (쓰지 않음)
    python sync_mirrors.py main utils   # 특정 모듈만 대상 지정 (파일명 기준)
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# 미러 대상 (확장자 제외). .py → 동일 이름의 .md 로 복사된다.
MIRROR_MODULES = [
    "bump_version",
    "chzzk_api",
    "config",
    "controller",
    "cookies",
    "dialogs",
    "downloader",
    "log_console",
    "main",
    "media",
    "pot_provider",
    "theme",
    "ui_components",
    "updater",
    "utils"
]


def sync_module(name: str, dry_run: bool = False) -> int:
    """단일 모듈의 .py → .md 미러를 갱신한다. (변경 시 1, 동일 시 0, 누락 시 2)"""
    src = ROOT / f"{name}.py"
    dst = ROOT / f"{name}.md"

    if not src.exists():
        print(f"[skip] {src.name} 없음 — 대상 미러 확인 불가")
        return 2

    content = src.read_bytes()
    if dst.exists() and dst.read_bytes() == content:
        print(f"[동일] {name}.md 최신 상태")
        return 0

    action = "확인" if dry_run else "갱신"
    print(f"[{action}] {name}.py -> {name}.md ({len(content)} bytes)")
    if not dry_run:
        dst.write_bytes(content)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="ChzzkTube .py 소스의 .md 미러 파일을 동기화한다."
    )
    parser.add_argument(
        "modules",
        nargs="*",
        help="대상 모듈(예: main downloader). 미지정 시 전체 대상.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="변경될 파일만 나열하고 실제 쓰기는 하지 않는다.",
    )
    args = parser.parse_args()

    targets = args.modules or MIRROR_MODULES
    results = [sync_module(m, dry_run=args.check) for m in targets]

    changed = sum(1 for r in results if r == 1)
    missing = sum(1 for r in results if r == 2)

    print("-" * 40)
    print(f"총 {len(targets)}개 중 변경 {changed}개 / 누락 {missing}개")
    return 0


if __name__ == "__main__":
    sys.exit(main())
