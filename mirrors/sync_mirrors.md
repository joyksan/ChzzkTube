# sync_mirrors.py - .py source -> mirrors/*.md mirror auto-sync script
"""
Usage:
    python sync_mirrors.py              # sync all changed mirror files and chzzktube_codebase.md bundle
    python sync_mirrors.py --check      # check only (no writes)
    python sync_mirrors.py main utils   # target specific modules (by file name)
"""

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MIRRORS_DIR = ROOT / "mirrors"

# Mirror targets (extension excluded). .py -> mirrors/*.md
# New .py modules MUST be added here too.
MIRROR_MODULES = [
    # root
    "main",
    "bump_version",
    "smoke_test",
    "sync_mirrors",
    # chzzktube.ui
    "chzzktube.ui.dialogs",
    "chzzktube.ui.log_console",
    "chzzktube.ui.main_window",
    "chzzktube.ui.theme",
    # chzzktube.control
    "chzzktube.control.controller",
    "chzzktube.control.pot_manager",
    "chzzktube.control.startup_coordinator",
    "chzzktube.control.startup_state",
    # chzzktube.workers
    "chzzktube.workers.analyze_worker",
    "chzzktube.workers.downloader",
    "chzzktube.workers.update_worker",
    # chzzktube.pipeline
    "chzzktube.pipeline.classifier",
    "chzzktube.pipeline.dl_context",
    "chzzktube.pipeline.finalizer",
    "chzzktube.pipeline.live_recorder",
    "chzzktube.pipeline.progress_emitter",
    "chzzktube.pipeline.target_downloader",
    # chzzktube.core
    "chzzktube.core.chzzk_api",
    "chzzktube.core.client_opts",
    "chzzktube.core.config",
    "chzzktube.core.cookies",
    "chzzktube.core.dl_platform",
    "chzzktube.core.log_emitter",
    "chzzktube.core.log_event",
    "chzzktube.core.log_history",
    "chzzktube.core.media",
    "chzzktube.core.playlist",
    "chzzktube.core.raw_log",
    "chzzktube.core.speed_window",
    "chzzktube.core.tool_log",
    "chzzktube.core.utils",
    "chzzktube.core.watchdog",
    "chzzktube.core.yt_logger_bridge",
    # chzzktube.infra
    "chzzktube.infra.components",
    "chzzktube.infra.node_provider",
    "chzzktube.infra.paths",
    "chzzktube.infra.platform",
    "chzzktube.infra.po_client",
    "chzzktube.infra.pot_provider",
    "chzzktube.infra.pot_server",
    "chzzktube.infra.pylib_bootstrap",
    "chzzktube.infra.updater",
]


def sync_module(name: str, dry_run: bool = False) -> int:
    """Sync one module .py -> mirrors/*.md. (1=changed, 0=same, 2=missing)"""
    clean_name = name.removesuffix(".py")

    # Modules inside the chzzktube package live under chzzktube/<subpkg>/
    if name.startswith("chzzktube."):
        parts = clean_name.split(".")
        # parts = ["chzzktube", "core", "yt_logger_bridge"]
        # src = chzzktube/core/yt_logger_bridge.py
        src = ROOT / "chzzktube" / Path(*parts[1:-1]) / f"{parts[-1]}.py"
    else:
        src = ROOT / f"{clean_name}.py"

    # 미러 파일명은 flat 유지 — chzzktube/core/config.py → mirrors/config.md
    # (기존 conventions 유지: HANDOVER 참조·미러 diff 시 basename 추적 용이)
    dst = MIRRORS_DIR / f"{clean_name.split('.')[-1]}.md"

    if not src.exists():
        print(f"[skip] {src.name} missing - target mirror not found")
        return 2

    content = src.read_bytes()
    if dst.exists() and dst.read_bytes() == content:
        print(f"[same] mirrors/{dst.name} up to date")
        return 0

    action = "check" if dry_run else "update"
    print(
        f"[{action}] {clean_name}.py -> mirrors/{dst.name} ({len(content)} bytes)"
    )
    if not dry_run:
        MIRRORS_DIR.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(content)
    return 1


def build_codebase_bundle():
    """Bundle all .py sources into mirrors/chzzktube_codebase.md single file."""
    bundle_path = MIRRORS_DIR / "chzzktube_codebase.md"
    exclude_dirs = {
        ".git",
        ".github",
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        ".pylib",
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
    print(f"[created] mirrors/{bundle_path.name} bundle")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="ChzzkTube .py source .md mirror file sync tool."
    )
    parser.add_argument(
        "modules",
        nargs="*",
        help="target modules (e.g. main downloader). Default: all.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="check only (no writes)",
    )
    args = parser.parse_args()

    targets = args.modules or MIRROR_MODULES
    results = [sync_module(m, dry_run=args.check) for m in targets]

    changed = sum(1 for r in results if r == 1)
    missing = sum(1 for r in results if r == 2)

    print("-" * 40)
    print(f"total {len(targets)}: changed {changed} / missing {missing}")

    # When not in --check mode, also generate/refresh the single bundle file
    if not args.check:
        build_codebase_bundle()

    return 0


if __name__ == "__main__":
    sys.exit(main())