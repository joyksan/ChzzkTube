"""배치 종료 신호는 Context/로그 실패와 무관하게 세션당 한 번."""
from unittest.mock import Mock

import pytest

import chzzktube.workers.downloader as downloader


@pytest.mark.parametrize("failure", ["extract", "expand", "download", "finalize", "logging", None])
def test_completion_once(monkeypatch, tmp_path, failure):
    worker = downloader.DownloadWorker(
        ["https://example.com/video"], {"download_path": str(tmp_path)},
        {"canceled": False, "skip": False}, "auto", "auto",
    )
    calls = []
    worker.finished_all.connect(lambda ok, bad: calls.append((ok, bad)))
    monkeypatch.setattr(downloader.raw_log, "raw", Mock())
    monkeypatch.setattr(downloader._td, "expand_targets", lambda ctx: ctx.targets)
    monkeypatch.setattr(downloader._td, "download_target", Mock(return_value=True))
    error = RuntimeError("injected failure")
    if failure == "extract":
        monkeypatch.setattr(worker, "extract", Mock(side_effect=error))
    elif failure == "expand":
        monkeypatch.setattr(downloader._td, "expand_targets", Mock(side_effect=error))
    elif failure == "download":
        monkeypatch.setattr(downloader._td, "download_target", Mock(side_effect=error))
    elif failure == "finalize":
        monkeypatch.setattr(downloader._fin, "finalize", Mock(side_effect=error))
    elif failure == "logging":
        monkeypatch.setattr(downloader.raw_log, "raw", Mock(side_effect=error))

    worker.run()

    assert len(calls) == 1
    if failure in ("extract", "expand", "download"):
        assert calls == [(0, 1)]
    else:
        assert calls == [(1, 0)]


def test_completion_on_cancel(monkeypatch, tmp_path):
    worker = downloader.DownloadWorker(
        ["https://example.com/video"], {"download_path": str(tmp_path)},
        {"canceled": True, "skip": False}, "auto", "auto",
    )
    calls = []
    worker.finished_all.connect(lambda ok, bad: calls.append((ok, bad)))
    monkeypatch.setattr(downloader.raw_log, "raw", Mock())
    monkeypatch.setattr(downloader._td, "expand_targets", lambda ctx: ctx.targets)
    download = Mock()
    monkeypatch.setattr(downloader._td, "download_target", download)
    worker.run()
    assert calls == [(0, 0)]
    download.assert_not_called()
