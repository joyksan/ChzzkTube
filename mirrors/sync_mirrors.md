# sync_mirrors.py - .py 소스 → mirrors/*.md 미러 자동 동기화 스크립트
"""
사용법:
    python sync_mirrors.py              # 변경된 미러 파일 및 chzzktube_codebase.md 일괄 동기화
    python sync_mirrors.py --check      # 변경 여부만 확인 (쓰지 않음)
    python sync_mirrors.py main utils   # 특정 모듈만 대상 지정 (파일명 기준)
"""

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MIRRORS_DIR = ROOT / "mirrors"

# 미러 대상 (확장자 제외). .py → mirrors/*.md 로 복사된다.
# 새 .py 모듈 추가 시 이 목록에도 반드시 추가할 것.
MIRROR_MODULES = [
    "analyze_worker",
    "bump_version",
    "chzzk_api",
    "client_opts",
    "components",
    "config",
    "controller",
    "cookies",
    "dialogs",
    "dl_platform",
    "dl_context",
    "downloader",
    "finalizer",
    "live_recorder",
    "log_console",
    "log_event",
    "log_history",
    "main",
    "media",
    "node_provider",
    "playlist",
    "po_client",
    "pot_manager",
    "pot_provider",
    "pot_server",
    "progress_emitter",
    "raw_log",
    "smoke_test",
    "speed_window",
    "startup_coordinator",
    "startup_state",
    "sync_mirrors",
    "target_downloader",
    "theme",
    "update_worker",
    "updater",
    "utils",
    "yt_logger_bridge",
]


def sync_module(name: str, dry_run: bool = False) -> int:
    """단일 모듈의 .py → mirrors/*.md 미러를 갱신한다. (변경 시 1, 동일 시 0, 누락 시 2)"""
    clean_name = name.removesuffix(".py")

    src = ROOT / f"{clean_name}.py"
    dst = MIRRORS_DIR / f"{clean_name}.md"

    if not src.exists():
        print(f"[skip] {src.name} 없음 — 대상 미러 확인 불가")
        return 2

    content = src.read_bytes()
    if dst.exists() and dst.read_bytes() == content:
        print(f"[동일] mirrors/{clean_name}.md 최신 상태")
        return 0

    action = "확인" if dry_run else "갱신"
    print(
        f"[{action}] {clean_name}.py -> mirrors/{clean_name}.md ({len(content)} bytes)"
    )
    if not dry_run:
        MIRRORS_DIR.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(content)
    return 1


def build_codebase_bundle():
    """모든 .py 소스를 mirrors/chzzktube_codebase.md 단일 합본으로 번들링한다."""
    bundle_path = MIRRORS_DIR / "chzzktube_codebase.md"
    exclude_dirs = {
        ".git",
        ".github",
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        "build",
        "dist",
        "tests",
        "mirrors",
    }

    MIRRORS_DIR.mkdir(parents=True, exist_ok=True)
    with open(bundle_path, "w", encoding="utf-8") as outfile:
        outfile.write("# ChzzkTube Project Full Codebase\n\n")
        for root, dirs, files in os.walk(ROOT):
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            for file in sorted(files):
                if file.endswith(".py"):
                    rel = os.path.relpath(os.path.join(root, file), ROOT)
                    outfile.write(f"\n## File: {rel}\n\n```python\n")
                    with open(
                        os.path.join(root, file), "r", encoding="utf-8", errors="ignore"
                    ) as infile:
                        outfile.write(infile.read())
                    outfile.write("\n```\n")
    print(f"[생성] mirrors/{bundle_path.name} 합본 생성 완료")


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

    # --check 모드가 아닐 때 단일 합본 파일도 함께 생성/최신화
    if not args.check:
        build_codebase_bundle()

    return 0


if __name__ == "__main__":
    sys.exit(main())
