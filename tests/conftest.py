"""Shared pytest setup: exactly one QApplication for the whole session.

Why this file exists
--------------------
Qt allows only one application object per process, and the class matters:
a bare ``QCoreApplication`` is NOT a GUI application.

``QApplication.instance()`` is inherited from ``QCoreApplication``, so it
returns whatever application already exists. A test module that created a
``QCoreApplication`` first therefore made later widget tests believe an
application was ready; constructing ``QTextEdit`` without a real
``QApplication`` aborts the interpreter (SIGABRT / EXC_BAD_ACCESS, see the
note in tests/test_log_console.py).

Creating the GUI application session-wide - before any test body runs -
removes the ordering dependency: widget tests reuse it, and Qt-only tests
that call ``QCoreApplication.instance() or QCoreApplication([])`` receive
it as well. Headless runs stay headless through QT_QPA_PLATFORM=offscreen.

.pylib overlay bootstrap
------------------------
Ensures the project-local .pylib/ overlay (yt-dlp, streamlink, etc.) is
inserted at sys.path[0] before any test imports yt_dlp. This mirrors the
production bootstrap in main.py and eliminates namespace-package mocks.
"""
import importlib
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# 1) Bootstrap .pylib overlay BEFORE any yt_dlp import
# This runs at module load time, before pytest collects tests
from chzzktube.infra.pylib_bootstrap import bootstrap as _bootstrap_pylib

_BOOTSTRAPPED = _bootstrap_pylib()
if _BOOTSTRAPPED:
    sys.path.insert(0, _BOOTSTRAPPED)
    # Force namespace package re-scan if yt_dlp already loaded
    if "yt_dlp" in sys.modules:
        yt_dlp_mod = sys.modules["yt_dlp"]
        overlay_pkg = os.path.join(_BOOTSTRAPPED, "yt_dlp")
        if os.path.isdir(overlay_pkg) and hasattr(yt_dlp_mod, "__path__") and overlay_pkg not in yt_dlp_mod.__path__:
            yt_dlp_mod.__path__.insert(0, overlay_pkg)
    importlib.invalidate_caches()

import pytest


def pytest_configure(config):
    """Ensure .pylib is active for all test collection."""
    # Re-apply in case collection triggered new imports
    if _BOOTSTRAPPED and _BOOTSTRAPPED not in sys.path:
        sys.path.insert(0, _BOOTSTRAPPED)
    if "yt_dlp" in sys.modules:
        yt_dlp_mod = sys.modules["yt_dlp"]
        overlay_pkg = os.path.join(_BOOTSTRAPPED, "yt_dlp")
        if os.path.isdir(overlay_pkg) and hasattr(yt_dlp_mod, "__path__") and overlay_pkg not in yt_dlp_mod.__path__:
            yt_dlp_mod.__path__.insert(0, overlay_pkg)
        importlib.invalidate_caches()


@pytest.fixture(scope="session", autouse=True)
def qt_application():
    """세션 전체가 공유하는 QApplication (offscreen)."""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app
    app.processEvents()


@pytest.fixture(autouse=True)
def isolate_raw_log() -> None:
    """각 단위 테스트 간 raw_log 버스 잔여 큐 플러시 및 오염 방지."""
    from chzzktube.core import raw_log

    yield
    raw_log.flush(timeout=0.2)


@pytest.fixture
def live(monkeypatch, tmp_path):
    """치지직 라이브 테스트용 전체 모킹 픽스처."""
    from unittest.mock import Mock, create_autospec

    import chzzktube.core.chzzk_api as api
    import chzzktube.pipeline.target_downloader as td
    from chzzktube.pipeline.dl_context import DownloadContext

    formats = [
        {"id": "1080", "height": 1080, "url": "https://media.example/1080.m3u8"},
        {"id": "720", "height": 720, "url": "https://media.example/720.m3u8"},
    ]
    info = {"title": "방송", "live_id": "abc", "live_status": "PROGRESS", "formats": formats}
    analysis = Mock(return_value=info)
    monkeypatch.setattr(api, "analyze_chzzk_live_api", analysis)
    youtube = Mock(return_value=False)
    monkeypatch.setattr(td, "_download_youtube_live", youtube)
    monkeypatch.setattr(td, "_is_youtube_live_url", Mock(side_effect=AssertionError("YouTube probe")))
    record = create_autospec(td._lr.record_live_stream, return_value=True)
    monkeypatch.setattr(td._lr, "record_live_stream", record)
    monkeypatch.setattr(td.raw_log, "raw", Mock())
    ctx = DownloadContext(cfg={"download_path": str(tmp_path)},
                          current_url="https://chzzk.naver.com/live/abc", is_live_hint=True)
    return ctx, info, analysis, youtube, record
