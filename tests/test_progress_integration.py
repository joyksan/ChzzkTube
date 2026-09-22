"""진행률(component_id / is_progress) 페이로드 누수 회귀 테스트."""
from types import SimpleNamespace

import pytest

from chzzktube.core.log_event import LogEvent
from chzzktube.core.log_emitter import emit_component
import chzzktube.core.raw_log as raw_log


def _subscribe(collector, kind="concise"):
    if kind == "concise":
        raw_log.subscribe_concise(collector)
        subs = raw_log._dispatcher._concise_subs
    else:
        raw_log.subscribe_full(collector)
        subs = raw_log._dispatcher._full_subs
    yield collector
    with raw_log._dispatcher._lock:
        if collector in subs:
            subs.remove(collector)
    raw_log.flush(timeout=0.5)


@pytest.fixture
def concise_collector():
    evs = []
    collector = lambda ev, is_status, is_error: evs.append(ev)
    raw_log.subscribe_concise(collector)
    try:
        yield evs
    finally:
        with raw_log._dispatcher._lock:
            if collector in raw_log._dispatcher._concise_subs:
                raw_log._dispatcher._concise_subs.remove(collector)
        raw_log.flush(timeout=0.5)


@pytest.fixture
def full_collector():
    evs = []
    collector = lambda ev, is_status: evs.append(ev)
    raw_log.subscribe_full(collector)
    try:
        yield evs
    finally:
        with raw_log._dispatcher._lock:
            if collector in raw_log._dispatcher._full_subs:
                raw_log._dispatcher._full_subs.remove(collector)
        raw_log.flush(timeout=0.5)
def test_raw_log_preserves_component_id_and_is_progress(concise_collector):
    evs = concise_collector
    ev = LogEvent(stage="DEPS", status="RUN", scope="ffmpeg", msg="10%",
                  is_status=True, is_progress=True, component_id="deps_ffmpeg")
    raw_log.raw("deps", ev, is_status=True, is_progress=True,
                to_tui=True, component_id="deps_ffmpeg")
    raw_log.flush(timeout=1.0)
    assert evs[-1].component_id == "deps_ffmpeg"
    assert evs[-1].is_progress is True
    assert evs[-1].is_status is True


def test_raw_log_normal_event_has_no_component(concise_collector):
    evs = concise_collector
    raw_log.raw("sys", "plain message", to_tui=True)
    raw_log.flush(timeout=1.0)
    assert evs[-1].component_id is None
    assert evs[-1].is_progress is False
def test_log_console_updates_progress_line_by_component_id():
    from PySide6.QtWidgets import QTextEdit
    from chzzktube.ui.log_console import ConciseLogConsole
    console = ConciseLogConsole(QTextEdit())
    console.append("ffmpeg 10%", component_id="deps_ffmpeg", is_progress=True)
    console.append("ffmpeg 50%", component_id="deps_ffmpeg", is_progress=True)
    console.append("node 30%", component_id="deps_node", is_progress=True)
    progress = [e for e in console._buffer if e["is_progress"]]
    assert len(progress) == 2
    assert "deps_ffmpeg" in console._progress_lines
    assert "deps_node" in console._progress_lines


def test_log_console_finalizes_progress_line():
    from PySide6.QtWidgets import QTextEdit
    from chzzktube.ui.log_console import ConciseLogConsole
    console = ConciseLogConsole(QTextEdit())
    console.append("ffmpeg 10%", component_id="deps_ffmpeg", is_progress=True)
    console.append("ffmpeg completed -> 9.0.2", component_id="deps_ffmpeg", is_progress=False)
    assert "deps_ffmpeg" not in console._progress_lines
    assert [e for e in console._buffer if e["is_progress"]] == []
    assert len([e for e in console._buffer if not e["is_progress"]]) == 2
def test_verbose_log_window_f12_updates_by_component_id():
    from chzzktube.ui.dialogs import VerboseLogWindow
    win = VerboseLogWindow()
    win.append("ffmpeg 10%", is_status=True, component_id="deps_ffmpeg")
    win.append("ffmpeg 50%", is_status=True, component_id="deps_ffmpeg")
    assert "deps_ffmpeg" in win._status_lines
    assert win.te.document().blockCount() == 2


def test_provisioning_manager_emits_component_id_on_progress():
    import asyncio
    from chzzktube.infra.provisioning.manager import ProvisioningManager

    captured = {}

    def fake_log(msg, is_status=False, is_error=False,
                 component_id=None, is_progress=False):
        captured["kwargs"] = dict(is_status=is_status, is_error=is_error,
                                 component_id=component_id, is_progress=is_progress)

    mgr = ProvisioningManager(log_func=fake_log)
    asyncio.run(mgr._on_progress("ffmpeg", 50, 100, 1024.0, 10.0))
    assert captured["kwargs"]["component_id"] == "deps_ffmpeg"
    assert captured["kwargs"]["is_progress"] is True
def test_update_worker_passes_component_id_is_progress_to_raw_log(full_collector):
    evs = full_collector
    from chzzktube.workers.update_worker import UpdateWorker

    worker = UpdateWorker.__new__(UpdateWorker)
    worker._tick = lambda ev: None
    worker._had_action = lambda tui_line: None
    ev = LogEvent(stage="DEPS", status="RUN", scope="ffmpeg", msg="10%",
                  is_status=True, is_progress=True, component_id="deps_ffmpeg")
    worker._provision_cb(ev, is_status=True, is_error=False,
                         component_id="deps_ffmpeg", is_progress=True)
    raw_log.flush(timeout=1.0)
    assert evs[-1].component_id == "deps_ffmpeg"
    assert evs[-1].is_progress is True


def test_main_window_render_concise_finalizes_progress_line():
    from chzzktube.ui.main_window import MainWindow

    w = MainWindow.__new__(MainWindow)
    buffer = [{"msg": "ffmpeg 10%", "is_status": True, "is_error": False,
               "fg_color": None, "no_wrap": False, "component_id": "deps_ffmpeg",
               "is_progress": True}]
    progress_lines = {"deps_ffmpeg": 0}
    refilled = []
    appended = []
    w.console = SimpleNamespace(
        _buffer=buffer, _progress_lines=progress_lines,
        reflow=lambda: refilled.append("reflow"),
        append=lambda *a, **k: appended.append((a, k)),
    )
    final = LogEvent(stage="DEPS", status="OK", scope="ffmpeg",
                     msg="completed -> 9.0.2", is_status=True, is_progress=False,
                     component_id="deps_ffmpeg")
    MainWindow._render_concise(w, final, is_status=True, is_error=False)
    assert "deps_ffmpeg" not in progress_lines
    assert buffer[0]["is_progress"] is False
    assert refilled == ["reflow"]
    assert appended == []


def test_no_duplicate_f12_lines_for_progress_ticks():
    full = []
    fn = lambda ev, is_status: full.append(ev)
    raw_log.subscribe_full(fn)
    raw_log.flush(timeout=0.5)
    try:
        for pct in (25, 50, 75, 100):
            raw_log.raw("f12", emit_component("DEPS", "RUN", "ffmpeg", msg=f"{pct}% bar"),
                        is_status=True, is_progress=True, to_tui=True,
                        component_id="deps_ffmpeg")
        raw_log.flush(timeout=1.0)
        assert full[-1].component_id == "deps_ffmpeg"
    finally:
        with raw_log._dispatcher._lock:
            if fn in raw_log._dispatcher._full_subs:
                raw_log._dispatcher._full_subs.remove(fn)
        raw_log.flush(timeout=0.5)


