"""Tests for Windows dependency loop and provisioning consistency."""
import sys
from unittest.mock import MagicMock, patch

from chzzktube.infra.cleanup import cleanup_provisioning_artifacts
from chzzktube.infra.node_provider import node_exe
from chzzktube.infra.platform import astrip_macos_quarantine, strip_macos_quarantine
from chzzktube.infra.provisioning.committer import Committer
from chzzktube.infra.provisioning.manifest import ComponentRecord, ProvisionManifest
from chzzktube.infra.provisioning.planner import ProvisionPlan
from chzzktube.infra.provisioning.resolver import (
    MIRROR_REGISTRY,
    filter_assets,
    get_platform_asset_filters,
)
from chzzktube.infra.provisioning.verifier import Verifier, VerifyResult
from chzzktube.infra.updater import _ffmpeg_version


def test_windows_platform_asset_filters_prevent_linux64():
    """Windows asset filter must not match linux64 archives."""
    with (
        patch("sys.platform", "win32"),
        patch("platform.machine", return_value="AMD64"),
    ):
        filters = get_platform_asset_filters()
        assert "x64" not in filters  # bare 'x64' matches 'linux64'
        assert any("win" in f for f in filters)

    ffmpeg_spec = MIRROR_REGISTRY["ffmpeg"]
    assets = [
        {"name": "ffmpeg-master-latest-linux64-gpl.tar.xz", "browser_download_url": "https://invalid/linux"},
        {"name": "ffmpeg-master-latest-win64-gpl-shared.zip", "browser_download_url": "https://invalid/win-shared"},
        {"name": "ffmpeg-master-latest-win64-gpl.zip", "browser_download_url": "https://invalid/win-static"},
    ]

    with (
        patch("sys.platform", "win32"),
        patch("platform.machine", return_value="AMD64"),
    ):
        candidates = filter_assets(assets, ffmpeg_spec)
        assert len(candidates) == 1
        assert candidates[0]["name"] == "ffmpeg-master-latest-win64-gpl.zip"


def test_verifier_reports_status_dll_not_found(tmp_path):
    """Exit code 3221225781 (0xC0000135) reports STATUS_DLL_NOT_FOUND."""
    fake_exe = tmp_path / "ffmpeg.exe"
    fake_exe.write_text("dummy", encoding="utf-8")

    spec = MIRROR_REGISTRY["ffmpeg"]
    mock_proc = MagicMock()
    mock_proc.returncode = 3221225781
    mock_proc.stderr = ""
    mock_proc.stdout = ""

    with patch("subprocess.run", return_value=mock_proc):
        res = Verifier.verify_binary(spec, fake_exe)
        assert res.success is False
        assert "STATUS_DLL_NOT_FOUND" in res.error


def test_verifier_extracts_ffmpeg_version(tmp_path):
    """ffmpeg version string extraction handles git snapshot builds."""
    fake_exe = tmp_path / "ffmpeg.exe"
    fake_exe.write_text("dummy", encoding="utf-8")

    spec = MIRROR_REGISTRY["ffmpeg"]
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = "ffmpeg version N-126826-gc0e8b139fd-20260924 Copyright (c) 2000-2026 the FFmpeg developers\n"
    mock_proc.stderr = ""

    with patch("subprocess.run", return_value=mock_proc):
        res = Verifier.verify_binary(spec, fake_exe)
        assert res.success is True
        assert res.version == "N-126826-gc0e8b139fd-20260924"


def test_updater_ffmpeg_version_git_snapshot():
    """_ffmpeg_version extracts git snapshot version or falls back gracefully."""
    raw = "ffmpeg version N-126826-gc0e8b139fd-20260924 Copyright (c) 2000-2026"
    assert _ffmpeg_version(raw) == "N-126826-gc0e8b139fd-20260924"


def test_manifest_is_stale_with_base_dir_detects_missing_file(tmp_path):
    """is_stale returns True when installed binary is missing from disk."""
    manifest = ProvisionManifest()
    manifest.components["ytdlp"] = ComponentRecord(
        name="ytdlp",
        version="2026.01.01",
        source="github_ytdl",
        mirror="github_ytdl",
        install_path="bin/yt-dlp.exe",
        verified_at=100.0,
        verify_version="2026.01.01",
    )

    # File does not exist yet -> stale
    assert manifest.is_stale("ytdlp", "2026.01.01", base_dir=tmp_path) is True

    # Create the file -> no longer stale
    (tmp_path / "bin").mkdir(parents=True)
    (tmp_path / "bin" / "yt-dlp.exe").write_text("dummy", encoding="utf-8")
    assert manifest.is_stale("ytdlp", "2026.01.01", base_dir=tmp_path) is False

    # Different version -> stale
    assert manifest.is_stale("ytdlp", "2026.02.01", base_dir=tmp_path) is True


def test_committer_commits_plan_version(tmp_path):
    """Committer records plan.version in manifest so stale check succeeds."""
    committer = Committer(base_dir=tmp_path)
    plan = ProvisionPlan(
        component="ffmpeg",
        spec=MIRROR_REGISTRY["ffmpeg"],
        mirror_name="github_btb",
        version="latest",
        download_url="https://invalid/ffmpeg.zip",
        expected_sha256=None,
        install_path=tmp_path / "ffmpeg",
        is_update=False,
        archive_type="zip",
    )
    result = VerifyResult(
        component="ffmpeg",
        success=True,
        version="N-126826-gc0e8b139fd-20260924",
    )

    with patch.object(committer, "_refresh_overlay"), patch.object(committer, "_refresh_path"):
        committer.commit([plan], [result])

    manifest = ProvisionManifest.load(tmp_path)
    rec = manifest.get_record("ffmpeg")
    assert rec is not None
    assert rec.version == "latest"
    assert rec.verify_version == "N-126826-gc0e8b139fd-20260924"
    assert manifest.is_stale("ffmpeg", "latest") is False


def test_cleanup_removes_cz_temp_directories(tmp_path):
    """cleanup_provisioning_artifacts removes cz_* folders."""
    with patch("chzzktube.core.config.writable_base", return_value=str(tmp_path)):
        cz_dir1 = tmp_path / "cz_node_1234"
        cz_dir1.mkdir()
        (cz_dir1 / "test.txt").write_text("data")

        cz_dir2 = tmp_path / "node" / "cz_node_5678"
        cz_dir2.mkdir(parents=True)
        (cz_dir2 / "test.txt").write_text("data")

        cleanup_provisioning_artifacts()

        assert not cz_dir1.exists()
        assert not cz_dir2.exists()


def test_node_provider_ignores_cz_directories(tmp_path):
    """node_exe prioritizes root node.exe and ignores cz_ folders."""
    with patch("chzzktube.infra.node_provider.get_writable_base", return_value=str(tmp_path)):
        node_dir = tmp_path / "node"
        cz_dir = node_dir / "cz_node_stale"
        cz_dir.mkdir(parents=True)
        cz_node = cz_dir / ("node.exe" if sys.platform == "win32" else "node")
        cz_node.write_text("stale")

        real_node = node_dir / ("node.exe" if sys.platform == "win32" else "node")
        real_node.write_text("real")

        with patch("chzzktube.infra.node_provider.node_major_version", return_value=22):
            exe = node_exe()
            assert exe == str(real_node)


def test_strip_macos_quarantine_noop_on_non_macos(tmp_path):
    """HAL 헬퍼는 비-macOS에서 외부 프로세스를 스폰하지 않는다 (no-op)."""
    fake = str(tmp_path / "ffmpeg")
    with (
        patch("chzzktube.infra.platform.is_macos", return_value=False),
        patch("chzzktube.infra.platform.subprocess.run") as mock_run,
    ):
        strip_macos_quarantine(fake)
    mock_run.assert_not_called()


def test_astrip_macos_quarantine_offloads_to_thread_and_skips_on_non_macos(tmp_path):
    """async 헬퍼: macOS에서 worker thread 경유 실행, 비-macOS에서는 무동작."""
    import asyncio

    fake = str(tmp_path / "yt-dlp")

    with (
        patch("chzzktube.infra.platform.is_macos", return_value=False),
        patch("chzzktube.infra.platform.subprocess.run") as mock_run,
    ):
        asyncio.run(astrip_macos_quarantine(fake))
    mock_run.assert_not_called()

    with (
        patch("chzzktube.infra.platform.is_macos", return_value=True),
        patch("chzzktube.infra.platform.strip_macos_quarantine") as mock_sync,
    ):
        asyncio.run(astrip_macos_quarantine(fake))
        mock_sync.assert_called_once_with(fake)


def test_executor_binary_install_strips_quarantine_without_blocking(tmp_path):
    """executor의 binary 설치 경로가 async xattr 헬퍼를 await하고 이벤트 루프를 블로킹하지 않는다."""
    import asyncio
    from types import SimpleNamespace

    from chzzktube.infra.provisioning.executor import Executor

    archive = tmp_path / "yt-dlp.bin"
    archive.write_bytes(b"binary payload")
    dest = tmp_path / "out" / "yt-dlp"
    plan = SimpleNamespace(
        component="yt-dlp",
        archive_type="binary",
        install_path=dest,
        version="1.0.0",
    )

    executor = Executor.__new__(Executor)

    with patch("chzzktube.infra.provisioning.executor.astrip_macos_quarantine") as mock_strip:
        installed = asyncio.run(executor._extract_and_install(plan, archive))

    assert installed == dest
    assert dest.read_bytes() == b"binary payload"

    if sys.platform == "win32":
        mock_strip.assert_not_called()
    else:
        mock_strip.assert_awaited_once_with(str(dest))

def test_executor_progress_format_and_persistence():
    """Verify progress format: bar, pct, speed, n/m, msg without ETA, and bar persistence."""
    from chzzktube.infra.provisioning.executor import Executor

    # 1. 다운로드 중 (msg 없음, ETA 없음)
    download_line = Executor._fmt_progress(45, "4.8 MB/s", "15.2/33.9 MB", msg="")
    assert download_line.startswith("[████░░░░░░]  45% ·   4.8 MB/s · 15.2/33.9 MB")
    assert "ETA" not in download_line

    # 2. 압축 해제 중 (100% 유지 + extracting...)
    extract_line = Executor._fmt_progress(100, "5.5 MB/s", "33.9/33.9 MB", msg="extracting...")
    assert "[██████████] 100% ·   5.5 MB/s · 33.9/33.9 MB · extracting..." in extract_line

    # 3. 설치 마감 (100% 유지 + installed)
    installed_line = Executor._fmt_progress(100, "5.5 MB/s", "33.9/33.9 MB", msg="node installed")
    assert "[██████████] 100% ·   5.5 MB/s · 33.9/33.9 MB · node installed" in installed_line

    # 4. 업데이트 마감 (100% 유지 + updated)
    updated_line = Executor._fmt_progress(100, "5.5 MB/s", "33.9/33.9 MB", msg="node updated")
    assert "[██████████] 100% ·   5.5 MB/s · 33.9/33.9 MB · node updated" in updated_line


def test_downloader_max_concurrent_handles_all_components():
    """ParallelDownloader max_concurrent must be at least 4 to prevent bgutil stall."""
    from chzzktube.infra.provisioning.downloader import ParallelDownloader

    downloader = ParallelDownloader()
    assert downloader.semaphore._value >= 4


def test_log_f12_cli_and_net_isolated_from_tui():
    """log_f12_cli and log_f12_net must emit LogEvent with to_tui=False."""
    from chzzktube.core import raw_log
    from chzzktube.core.raw_log import log_f12_cli, log_f12_net

    emitted = []

    def mock_raw(tag, msg, is_status=False, is_error=False, to_tui=False, **kwargs):
        emitted.append((tag, msg, to_tui))

    from unittest.mock import patch
    with patch.object(raw_log, "raw", side_effect=mock_raw):
        log_f12_cli("node --version", "v22.23.3")
        log_f12_net("HTTP GET https://example.com/asset.zip")

    assert len(emitted) >= 3
    for tag, event, to_tui in emitted:
        assert to_tui is False
        assert getattr(event, "stage", None) == "DEPS"


def test_platform_warn_writes_single_stderr_diagnostic_line(capsys):
    """무음 pass 금지 계약: _warn은 scope + 예외 타입명을 stderr 1줄로 남긴다.

    stdout/stderr 직접 기록이어야 한다 — 상위 로깅 계층 역참조는 '바보 모듈' 원칙 위반.
    """
    from chzzktube.infra import platform

    platform._warn("selftest scope", ValueError("boom"))

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "[platform] selftest scope: ValueError" in captured.err


def test_strip_macos_quarantine_logs_when_xattr_spawn_fails(tmp_path, capsys):
    """xattr 스폰이 예외로 실패해도 전파하지 않고 진단만 남긴다 (S110/BLE001 해소 계약)."""
    with (
        patch("chzzktube.infra.platform.is_macos", return_value=True),
        patch(
            "chzzktube.infra.platform.subprocess.run",
            side_effect=FileNotFoundError("xattr"),
        ),
    ):
        strip_macos_quarantine(str(tmp_path / "ffmpeg"))  # 예외 미전파

    err = capsys.readouterr().err
    assert "[platform]" in err
    assert "FileNotFoundError" in err


def test_kill_tree_stops_when_poll_signals_already_exited():
    """poll()이 값을 보고하면 종료로 판단해 kill을 시도하지 않는다 (멱등 정리)."""
    from chzzktube.infra import platform

    proc = MagicMock()
    proc.poll.return_value = 0

    platform.kill_tree(proc)

    proc.poll.assert_called_once()
    proc.kill.assert_not_called()


def test_attach_to_parent_lifecycle_returns_false_offsets(monkeypatch):
    """[계약] 할당 실패는 False로 보고된다 — 종전엔 무음 None이라 오탐 여지가 있었다."""
    from chzzktube.infra import platform

    # 비-Windows / proc 없음 → False (no-op)
    monkeypatch.setattr(platform, "is_windows", lambda: False)
    assert platform.attach_to_parent_lifecycle(MagicMock()) is False
    monkeypatch.setattr(platform, "is_windows", lambda: True)
    assert platform.attach_to_parent_lifecycle(None) is False


def test_attach_to_parent_lifecycle_false_when_assign_fails():
    """AssignProcessToJobObject 실패 시 False — Job 핸들은 닫고 미할당으로 보고한다."""
    from chzzktube.infra import platform

    fake_k32 = MagicMock()
    fake_k32.CreateJobObjectW.return_value = 0x1234  # 유효 핸들
    fake_k32.SetInformationJobObject.return_value = 1
    fake_k32.AssignProcessToJobObject.return_value = 0  # 할당 실패

    proc = MagicMock()
    proc._handle = 0x5678

    fake_ctypes = MagicMock()
    fake_ctypes.windll.kernel32 = fake_k32
    fake_ctypes.c_int64 = fake_ctypes.c_size_t = int

    with (
        patch("chzzktube.infra.platform.is_windows", return_value=True),
        patch.dict("sys.modules", {"ctypes": fake_ctypes}),
    ):
        result = platform.attach_to_parent_lifecycle(proc)

    assert result is False
    fake_k32.CloseHandle.assert_called_once_with(0x1234)  # 실패 시 핸들 누수 없음


def test_assign_to_job_object_marks_only_on_real_assignment():
    """[오탐 회귀] _ct_job은 실할당 시에만 True — 핸들 존재만으로 True가 되면 안 된다."""
    from chzzktube.infra import pot_server

    proc = MagicMock()
    proc._handle = 0x5678  # 핸들은 있으나 할당은 실패하는 상황

    with patch.object(pot_server, "attach_to_parent_lifecycle", return_value=False):
        pot_server.assign_to_job_object(proc)
    assert proc._ct_job is False

    with patch.object(pot_server, "attach_to_parent_lifecycle", return_value=True):
        pot_server.assign_to_job_object(proc)
    assert proc._ct_job is True
