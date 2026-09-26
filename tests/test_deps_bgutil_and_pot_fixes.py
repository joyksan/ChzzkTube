"""Tests for bgutil concurrent progress display, POT server creationflags fix, and duplicate log suppression."""
import asyncio
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from chzzktube.control.startup_coordinator import StartupCoordinator
from chzzktube.core import raw_log
from chzzktube.infra import platform
from chzzktube.infra.provisioning.executor import Executor
from chzzktube.infra.provisioning.planner import ProvisionPlan
from chzzktube.infra.provisioning.resolver import MIRROR_REGISTRY


def test_daemon_spawn_kwargs_use_no_window_false():
    """daemon_spawn_kwargs(False) must not raise KeyError and set creationflags correctly on Windows."""
    with patch.object(platform, "is_windows", return_value=True):
        kw = platform.daemon_spawn_kwargs(use_no_window=False)
        assert "creationflags" in kw
        expected_flag = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        assert kw["creationflags"] & expected_flag == expected_flag


def test_daemon_spawn_kwargs_use_no_window_true():
    """daemon_spawn_kwargs(True) on Windows includes both CREATE_NO_WINDOW and CREATE_NEW_PROCESS_GROUP."""
    with patch.object(platform, "is_windows", return_value=True):
        kw = platform.daemon_spawn_kwargs(use_no_window=True)
        assert "creationflags" in kw
        no_win = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        new_grp = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        assert kw["creationflags"] & no_win == no_win
        assert kw["creationflags"] & new_grp == new_grp


def test_startup_coordinator_no_duplicate_pot_failed(qt_application):
    """_on_pot_status('failed') does not emit to TUI, report_pot emits standard error once."""
    mock_pot = MagicMock()
    coord = StartupCoordinator(pot_manager=mock_pot)
    tui_events = []

    def mock_publish(event, to_tui):
        if to_tui:
            tui_events.append(event)
        return True

    with patch.object(raw_log._dispatcher, "publish", side_effect=mock_publish):
        # 1. pot_status_changed("failed")
        coord._on_pot_status("failed")
        assert len(tui_events) == 0, "pot_status_changed('failed') should not emit to TUI"

        # 2. report_pot(False, ...)
        coord.report_pot(False, "server failed")
        assert len(tui_events) == 1
        assert "server failed" in tui_events[0].msg
        assert "F12" in tui_events[0].msg


def test_executor_on_progress_handles_zero_or_negative_total():
    """_on_progress must not drop events when total <= 0 (e.g. chunked bgutil zipball)."""
    emitted = []
    executor = Executor(base_dir=Path("/tmp"), log_func=lambda ev, **kw: emitted.append(ev))

    executor._on_progress("bgutil", downloaded=1024 * 1024, total=0, speed_bps=500 * 1024)

    assert len(emitted) == 1
    ev = emitted[0]
    assert ev.component_id == "deps_bgutil"
    # Format contains 0% and MB size without crashing or returning early
    assert "0%" in ev.msg
    assert "1.0 MB" in ev.msg
    assert executor._active_progress["bgutil"]["downloaded_mb"] == 1.0


def test_executor_provision_emits_initial_zero_progress(tmp_path):
    """provision() must immediately emit 0% progress for all planned components before downloading."""
    emitted = []
    executor = Executor(base_dir=tmp_path, log_func=lambda ev, **kw: emitted.append(ev))

    spec_ytdlp = MIRROR_REGISTRY["ytdlp"]
    spec_bgutil = MIRROR_REGISTRY["bgutil"]
    plans = [
        ProvisionPlan("ytdlp", spec_ytdlp, "m1", "1.0", "http://fake/ytdlp", None, tmp_path / "ytdlp", False, "zip"),
        ProvisionPlan("bgutil", spec_bgutil, "m1", "1.0", "http://fake/bgutil", None, tmp_path / "bgutil", False, "zip"),
    ]

    async def fake_download_all(tasks):
        # When download_all starts, initial 0% events should already be emitted
        assert len([e for e in emitted if "0%" in e.msg]) == 2
        from chzzktube.infra.provisioning.downloader import DownloadResult
        return [
            DownloadResult(tasks[0], True, bytes_downloaded=1024 * 1024),
            DownloadResult(tasks[1], True, bytes_downloaded=2 * 1024 * 1024),
        ]

    executor._downloader.download_all = fake_download_all
    with (
        patch.object(executor, "_extract_and_install", return_value=tmp_path / "installed"),
        patch("chzzktube.infra.provisioning.verifier.Verifier.verify") as mock_v,
    ):
        mock_v.return_value = MagicMock(success=True, version="1.0")
        results = asyncio.run(executor.provision(plans))

    assert len(results) == 2
    assert all(r.success for r in results)


def test_log_f12_cli_two_phase_no_cmd_duplication():
    """Calling log_f12_cli(cmd) then log_f12_cli(None, output) does not duplicate $ cmd."""
    emitted = []

    def mock_raw(tag, event, **_kwargs):
        # **_kwargs absorbs optional raw() parameters (e.g. to_tui, is_status) without
        # declaring unused named parameters (avoids Pylance "not accessed" hints).
        emitted.append((tag, event))

    with patch("chzzktube.core.raw_log.raw", side_effect=mock_raw):
        raw_log.log_f12_cli("node compile.js", None, stage="POT", tag="pot-cli")
        raw_log.log_f12_cli(None, "compiled successfully", stage="POT", tag="pot-cli")

    assert len(emitted) == 2
    tag1, ev1 = emitted[0]
    tag2, ev2 = emitted[1]

    assert tag1 == "pot-cli"
    assert ev1.stage == "POT"
    assert ev1.msg == "$ node compile.js"

    assert tag2 == "pot-cli"
    assert ev2.stage == "POT"
    assert ev2.msg == "compiled successfully"
