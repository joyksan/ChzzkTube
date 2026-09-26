"""공통 경로/런타임 헬퍼 — node_provider, pot_server, updater 등에서 중복 제거."""

from __future__ import annotations

import os
import sys

from chzzktube.core import config


def get_writable_base() -> str:
    """사용자 환경에서 쓰기 권한이 100% 보장되는 로컬 앱 데이터 디렉터리 반환."""
    path = config.writable_base()
    os.makedirs(path, exist_ok=True)
    return path


def is_portable() -> bool:
    """PyInstaller(frozen) 패키징 여부."""
    return bool(getattr(sys, "frozen", False))


def bundle_root() -> str | None:
    """포터블에서 번들 데이터가 풀린 디렉터리 (onedir) _MEIPASS."""
    if is_portable():
        return getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(sys.executable)))
    return None