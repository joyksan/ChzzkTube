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
    "chzzktube.ui.log_mirror",
    "chzzktube.ui.main_window",
    "chzzktube.ui.theme",
    # chzzktube.ui.components
    "chzzktube.ui.components.action_bar",
    "chzzktube.ui.components.header_bar",
    # chzzktube.control
    "chzzktube.control.controller",
    "chzzktube.control.gate_state",
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
    # chzzktube.pipeline.target_downloader (package)
    "chzzktube.pipeline.target_downloader.__init__",
    "chzzktube.pipeline.target_downloader.chzzk",
    "chzzktube.pipeline.target_downloader.dispatch",
    "chzzktube.pipeline.target_downloader.flatten",
    "chzzktube.pipeline.target_downloader.options",
    "chzzktube.pipeline.target_downloader.utils",
    "chzzktube.pipeline.target_downloader.youtube_live",
    "chzzktube.pipeline.target_downloader.youtube_vod",
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
    # chzzktube.infra.provisioning (flat basename 충돌 회피: provisioning_<name>.md)
    "chzzktube.infra.provisioning.bridge",
    "chzzktube.infra.provisioning.committer",
    "chzzktube.infra.provisioning.downloader",
    "chzzktube.infra.provisioning.executor",
    "chzzktube.infra.provisioning.manager",
    "chzzktube.infra.provisioning.manifest",
    "chzzktube.infra.provisioning.planner",
    "chzzktube.infra.provisioning.resolver",
    "chzzktube.infra.provisioning.verifier",
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

    # 미러 파일명 결정:
    # - chzzktube.<leaf> (단일 세그먼트, e.g. core/config.py) → <leaf>.md (기존 flat 규칙 유지)
    # - chzzktube.infra.provisioning.<leaf> (프리미티브 충돌 회피) → provisioning_<leaf>.md
    #   (e.g. chzzktube.workers.downloader ↔ chzzktube.infra.provisioning.downloader
    #    같은 basename 충돌을 방지하기 위함)
    basename = clean_name.split(".")[-1]
    if clean_name.startswith("chzzktube.infra.provisioning."):
        dst = MIRRORS_DIR / f"provisioning_{basename}.md"
    elif clean_name == "chzzktube.pipeline.target_downloader.utils":
        dst = MIRRORS_DIR / "target_downloader_utils.md"
    else:
        dst = MIRRORS_DIR / f"{basename}.md"

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
    parts = ["# ChzzkTube Project Full Codebase\n\n"]
    for root, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for file in sorted(files):
            if file.endswith(".py"):
                rel = os.path.relpath(os.path.join(root, file), ROOT)
                with open(
                    os.path.join(root, file), "r", encoding="utf-8",
                    errors="ignore"
                ) as infile:
                    parts.append(f"\n## File: {rel}\n\n```python\n")
                    parts.append(infile.read())
                    parts.append("\n```\n")
    bundle_text = "".join(parts)
    # git diff --check passes: strip trailing whitespace from blank lines (bundle artifact)
    bundle_text = "\n".join(
        line.rstrip() if line.rstrip() == "" else line
        for line in bundle_text.split("\n")
    ).rstrip() + "\n"
    bundle_path.write_text(bundle_text, encoding="utf-8")
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