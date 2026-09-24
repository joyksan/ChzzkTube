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
    """완료(is_progress=False) 시 진행 라인은 히스토리로 남고 중복되지 않는다."""
    from PySide6.QtWidgets import QTextEdit
    from chzzktube.ui.log_console import ConciseLogConsole
    console = ConciseLogConsole(QTextEdit())
    console.append("ffmpeg 10%", component_id="deps_ffmpeg", is_progress=True)
    console.append("ffmpeg 50%", component_id="deps_ffmpeg", is_progress=True)
    # 진행 라인이 갱신형으로 1개 블록만 유지
    assert len([e for e in console._buffer if e["is_progress"] and e["component_id"] == "deps_ffmpeg"]) == 1
    console.append("ffmpeg completed -> 9.0.2", component_id="deps_ffmpeg", is_progress=False)
    assert "deps_ffmpeg" not in console._progress_lines
    # 히스토리: 완료 메시지가 남아있고 is_progress=False로 잠겨있다.
    completed = [e for e in console._buffer
                 if e["component_id"] == "deps_ffmpeg" and "completed" in e["msg"]]
    assert len(completed) == 1
    assert completed[0]["is_progress"] is False
    # 펜싱: 아직 is_progress=True 라인은 남아 있으면 안 된다.
    assert [e for e in console._buffer if e["is_progress"] and e["component_id"] == "deps_ffmpeg"] == []
def test_verbose_log_window_f12_updates_by_component_id():
    from chzzktube.ui.dialogs import VerboseLogWindow
    win = VerboseLogWindow()
    win.append("ffmpeg 10%", is_status=True, component_id="deps_ffmpeg")
    win.append("ffmpeg 50%", is_status=True, component_id="deps_ffmpeg")
    assert "deps_ffmpeg" in win._status_lines
    assert win.te.document().blockCount() == 2


def test_verbose_log_window_set_content_resets_component_blocks():
    from chzzktube.ui.dialogs import VerboseLogWindow
    win = VerboseLogWindow()
    win.append("ffmpeg 10%", is_status=True, component_id="deps_ffmpeg")
    win.set_content("plain history")
    assert win._status_lines == {}
    win.append("ffmpeg 50%", is_status=True, component_id="deps_ffmpeg")
    assert win.te.toPlainText().splitlines() == ["plain history", "ffmpeg 50%"]


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


def test_f12_buffer_snapshot_replaces_progress_ticks():
    """F12 선택지 B (§5-33): 뷰 버퍼는 진행 틱을 스냅샷 치환, 전량은 history/full_events가 보장.

    - _full_log_buf: 동일 진행 라인은 제자리 치환 → 길이 1, 최종 100%만 남는다.
    - 전량 보존은 raw_log history + dispatcher full_events ring의 책임 (별도 테스트).
    - 창 열림 시 win.append(msg, is_status, component_id) 치환 호출은 유지.
    """
    from chzzktube.core.log_event import LogEvent
    from chzzktube.ui.main_window import MainWindow

    class FakeWin:
        def __init__(self):
            self.appended = []
        def append(self, msg, is_status=False, component_id=None, **kw):
            self.appended.append((msg, is_status, component_id))
        def isVisible(self):
            return True

    class FakeMainWindow:
        from collections import deque
        _full_log_buf = deque(maxlen=4096)
        _last_full_was_status = False

    FakeMainWindow._mirror_full_log = MainWindow._mirror_full_log

    events = []
    for pct in (25, 50, 75, 100):
        ev = LogEvent(stage="DEPS", status="RUN", scope="ffmpeg", msg=f"{pct}%",
                      is_status=True, is_progress=True, component_id="deps_ffmpeg")
        events.append(ev)

    # 진행 틱 4개 → 버퍼는 스냅샷 1개로 치환되어야 한다 (뷰 폭발 방지).
    m = FakeMainWindow()
    for ev in events:
        FakeMainWindow._mirror_full_log(
            m, ev.msg, is_status=True, component_id="deps_ffmpeg"
        )

    assert len(m._full_log_buf) == 1
    assert "100%" in m._full_log_buf[0]

    # F12 창이 보일 때 진행 메시지도 갱신형 append로 전달된다.
    win = FakeWin()
    FakeMainWindow.verbose_win = win
    for ev in events:
        FakeMainWindow._mirror_full_log(
            FakeMainWindow(), ev.msg, is_status=True, component_id="deps_ffmpeg"
        )
    assert len(win.appended) == 4
    assert win.appended[-1][2] == "deps_ffmpeg"
    assert all(a[1] is True for a in win.appended)  # is_status 진행 틱


def test_f12_full_history_keeps_every_tick():
    """전량 보존은 dispatcher full_events ring이 담당 (버퍼 치환과 직교)."""
    import chzzktube.core.raw_log as raw_log
    from chzzktube.core.log_emitter import emit_component

    seen = []
    fn = lambda ev, is_status: seen.append(ev)
    raw_log.subscribe_full(fn)
    try:
        for pct in (25, 50, 75, 100):
            raw_log.raw("f12", emit_component("DEPS", "RUN", "ffmpeg", msg=f"{pct}% bar"),
                        is_status=True, is_progress=True, to_tui=True,
                        component_id="deps_ffmpeg")
        raw_log.flush(timeout=1.0)
        tails = [e.msg for e in seen if getattr(e, "component_id", None) == "deps_ffmpeg"][-4:]
        assert tails == ["25% bar", "50% bar", "75% bar", "100% bar"]
    finally:
        with raw_log._dispatcher._lock:
            if fn in raw_log._dispatcher._full_subs:
                raw_log._dispatcher._full_subs.remove(fn)
        raw_log.flush(timeout=0.5)


