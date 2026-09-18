"""대상 확장과 전환 시 DownloadContext 상태의 일관성."""
from unittest.mock import Mock

from chzzktube.core.speed_window import SpeedWindow
from chzzktube.pipeline.dl_context import DownloadContext
import chzzktube.pipeline.progress_emitter as progress
import chzzktube.workers.downloader as downloader


def test_next_target_emits_first_tick(monkeypatch):
    ctx = DownloadContext(cfg={}, speed_win=SpeedWindow(), total_count=2)
    clock = Mock(return_value=100.0)
    raw = Mock()
    monkeypatch.setattr(progress.time, "monotonic", clock)
    monkeypatch.setattr(progress.raw_log, "raw", raw)
    ctx.advance_target(1, "https://example.com/first")
    progress.emit_progress_tick(ctx, {"downloaded_bytes": 100})
    ctx.current_file = "old.mp4"
    ctx._meta_logged = True
    ctx.add_error("retained batch error")

    clock.return_value = 100.1
    ctx.advance_target(2, "https://example.com/second")
    assert ctx.current_file is None
    assert ctx._meta_logged is False
    assert ctx.speed_win._last_total == 0
    progress.emit_progress_tick(ctx, {"downloaded_bytes": 5})

    ticks = [call.args[1] for call in raw.call_args_list
             if len(call.args) > 1 and getattr(call.args[1], "status", "") == "RUN"]
    assert len(ticks) == 2
    assert ctx.speed_win._last_total == 5
    assert ctx.errors == ["retained batch error"]
    assert ctx.total_count == 2


def test_expanded_count_reaches_each_target(monkeypatch, tmp_path):
    worker = downloader.DownloadWorker(
        ["https://example.com/playlist"], {"download_path": str(tmp_path)},
        {"canceled": False, "skip": False}, "auto", "auto",
    )
    urls = ["https://example.com/one", "https://example.com/two"]
    # Create ClassifiedTarget objects for the mock
    from chzzktube.pipeline.classifier import ClassifiedTarget, ContentKind, ItemClassifier
    classified_urls = [ItemClassifier.classify(u) for u in urls]
    observed = []
    finished = []
    worker.finished_all.connect(lambda ok, bad: finished.append((ok, bad)))
    monkeypatch.setattr(downloader.raw_log, "raw", Mock())
    monkeypatch.setattr(downloader._td, "expand_targets", lambda ctx: classified_urls)

    def download(ctx, item, failures, skip_targets=None):
        observed.append((ctx.total_count, ctx.current_idx, item.url))
        return True

    monkeypatch.setattr(downloader._td, "download_target", download)
    worker.run()

    assert observed == [(2, 1, urls[0]), (2, 2, urls[1])]
    assert worker.total_count == worker._ctx.total_count == 2
    assert finished == [(2, 0)]
