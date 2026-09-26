"""프로비저닝 아티팩트 정리 유틸리티.

앱 기동 시 또는 종료 시 호출하여 .part 파일, 아카이브, 락 파일 등을 정리한다.
"""
import os
import glob
import shutil
from chzzktube.core import config


def cleanup_provisioning_artifacts():
    """수급 과정에서 생성된 임시 파일/락 파일 정리."""
    base = config.writable_base()
    if not os.path.isdir(base):
        return

    # 1. ffmpeg .part 파일 정리
    ffmpeg_dir = os.path.join(base, "ffmpeg")
    if os.path.isdir(ffmpeg_dir):
        for part_file in glob.glob(os.path.join(ffmpeg_dir, "*.part")):
            try:
                os.remove(part_file)
            except Exception:
                pass

    # 2. node 아카이브 정리 (node_portable.zip/tar.gz)
    for archive in glob.glob(os.path.join(base, "node_portable.*")):
        try:
            if os.path.isfile(archive):
                os.remove(archive)
            elif os.path.isdir(archive):
                shutil.rmtree(archive, ignore_errors=True)
        except Exception:
            pass

    # 3. pot prewarm 락 파일 정리
    pot_dir = os.path.join(base, "pot")
    if os.path.isdir(pot_dir):
        lock_file = os.path.join(pot_dir, ".prewarm.lock")
        if os.path.isfile(lock_file):
            try:
                os.remove(lock_file)
            except Exception:
                pass

    # 4. components 루트의 .part 파일 정리 (Homebrew bottle 다운로드 등)
    from chzzktube.infra.components import components_root
    comp_root = components_root()
    if os.path.isdir(comp_root):
        for part_file in glob.glob(os.path.join(comp_root, "*.part")):
            try:
                os.remove(part_file)
            except Exception:
                pass
        # ffmpeg 아카이브 정리
        for archive in glob.glob(os.path.join(comp_root, "ffmpeg*.tar.xz")):
            try:
                os.remove(archive)
            except Exception:
                pass
        for archive in glob.glob(os.path.join(comp_root, "ffmpeg*.zip")):
            try:
                os.remove(archive)
            except Exception:
                pass

    # 5. 임의의 .part 파일 정리 (전역)
    for part_file in glob.glob(os.path.join(base, "*.part")):
        try:
            os.remove(part_file)
        except Exception:
            pass

    # 6. cz_* 임시 디렉터리 정리 (base 및 base 하위 디렉터리)
    for cz_dir in glob.glob(os.path.join(base, "cz_*")):
        try:
            if os.path.isdir(cz_dir):
                shutil.rmtree(cz_dir, ignore_errors=True)
        except Exception:
            pass
    for cz_dir in glob.glob(os.path.join(base, "*", "cz_*")):
        try:
            if os.path.isdir(cz_dir):
                shutil.rmtree(cz_dir, ignore_errors=True)
        except Exception:
            pass


def cleanup_on_startup():
    """앱 기동 시 호출 — 이전 세션 잔재 정리."""
    cleanup_provisioning_artifacts()


def cleanup_on_shutdown():
    """앱 종료 시 호출 — 현재 세션 잔재 정리."""
    cleanup_provisioning_artifacts()