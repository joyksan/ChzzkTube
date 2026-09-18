"""파이프라인 P0/P1 회귀 테스트 — NameError 크래시·계약 불일치 수리 검증.

배경 (v3.4.0 패치 2 — LEGACY_AUDIT §A/§B/§C):
- chzzktube.pipeline.finalizer/downloader가 `_dl_platform`을 import 없이 사용 → 배치 완료/취소·
  SKIP 틱에서 NameError → `finished_all` 미발화 → UI 영구 락업 (P0-1/3)
- target_downloader가 정의 없는 `_chzzk_filename`을 호출 → 치지직 다운로드 전부 실패 (P0-2)
- chzzktube.control.pot_manager `_note/_dbg`의 발행 시점 `[:120]` 절단 — LOGGING_POLICY §3/§4 위반 (C1)
- live_recorder가 proc를 DownloadContext에 부착하는데 worker만 보던 정리 계약 (A4)
- main의 needs_pot 3중 중복 판정식 단일화 (E1)
"""
import chzzktube
from collections import deque
from types import SimpleNamespace

import chzzktube.core.raw_log as raw_log
import chzzktube.ui.main_window as main_module
from chzzktube.workers.downloader import DownloadWorker, _dl_platform as _dl_platform_dl
from chzzktube.pipeline.finalizer import _dl_platform as _dl_platform_fin, finalize
from chzzktube.control.pot_manager import _POTWorker
from chzzktube.pipeline.target_downloader import _chzzk_filename


# ── P0-1: chzzktube.pipeline.finalizer 배치 마감 NameError ───────────────────────────────

class _Sig:
    def __init__(self):
        self.calls = []

    def emit(self, *a):
        self.calls.append(a)


def _ctx(canceled=False):
    return SimpleNamespace(
        state={"canceled": canceled, "skip": False},
        live_partially_saved=False,
        cfg={"download_path": "/tmp"},
        current_url="https://youtu.be/abcDEFghijk",
        finished_all=_Sig(),
        _errors=[],
    )


def test_finalizer_finalize_success_no_nameerror(monkeypatch):
    """성공 배치 마감 — 구 NameError 지점(scope 계산) 통과 후 finished_all 발화."""
    monkeypatch.setattr(chzzktube.core.raw_log, "raw", lambda *a, **k: None)
    ctx = _ctx()
    ok = finalize(ctx, 1, [], 1)
    assert ok is True
    assert ctx.finished_all.calls == [(1, 0)]


def test_finalizer_finalize_cancel_emits_abort(monkeypatch):
    """취소 마감 — ABORT scope 계산(구 NameError 지점) 통과 + 실패 카운트 발화."""
    events = []
    monkeypatch.setattr(
        chzzktube.core.raw_log, "raw", lambda *a, **k: events.append(a[1] if len(a) > 1 else None))
    ctx = _ctx(canceled=True)
    ok = finalize(ctx, 1, [("https://x", "boom")], 0)
    assert ok is False
    assert ctx.finished_all.calls == [(0, 1)]
    statuses = [getattr(e, "status", "") for e in events if e is not None]
    assert "ABORT" in statuses
    # 취소 상태에서 실패가 있으면 배치 완료 라인은 FAIL로 출력됨
    assert "FAIL" in statuses


def test_dl_and_finalizer_share_dl_platform():
    """[정적 가드] NameError 재발 방지 — 두 모듈이 _dl_platform을 노출해야 한다."""
    assert _dl_platform_dl is _dl_platform_fin


# ── P0-2: 치지직 파일명 복구 ─────────────────────────────────────────

def test_chzzk_filename_default_suffix_id():
    info = {"title": "테스트 클립", "clip_id": "12345", "channel_name": "철수",
            "date": "2026-09-13"}
    name = _chzzk_filename(info, {"height": 1080},
                           {"filename_prefix": "none", "filename_suffix": "id"})
    assert name == "테스트 클립 [12345].mp4"


def test_chzzk_filename_uploader_prefix_and_res():
    info = {"title": "클립", "video_no": "99", "channel_name": "채널",
            "date": "2026-09-13"}
    name = _chzzk_filename(info, {"height": 1080},
                           {"filename_prefix": "uploader",
                            "filename_suffix": "id_res"})
    assert name == "[채널] 클립 [99] [1080p].mp4"


def test_chzzk_filename_sanitizes_and_falls_back():
    name = _chzzk_filename({"title": 'a/b:c*d?"<>|'}, {}, {})
    assert name == "a_b_c_d.mp4"


# ── E1: needs_pot 단일 판정 ───────────────────────────────────────────

def test_needs_pot_contract():
    assert main_module._needs_pot({"age_limit": 18, "availability": "public"}) is True
    assert main_module._needs_pot({"age_limit": 0, "availability": "needs_auth"}) is True
    assert main_module._needs_pot({"age_limit": 0, "availability": "subscriber_only"}) is True
    assert main_module._needs_pot({"age_limit": 0, "availability": "public"}) is False
    assert main_module._needs_pot({"age_limit": 0, "availability": None}) is False
    assert main_module._needs_pot(None) is False
    assert main_module._needs_pot({}) is False


# ── C1: POT 발행 원문 보존 ────────────────────────────────────────────

def test_pot_note_preserves_full_msg(monkeypatch):
    from chzzktube.core.log_event import LogEvent
    captured = []
    monkeypatch.setattr(chzzktube.core.raw_log, "raw", lambda *a, **k: captured.append(a))
    worker = _POTWorker(mode="gate")
    long = "x" * 300
    worker._note(long)
    worker._dbg(long)
    evs = [a[1] for a in captured if len(a) > 1]
    assert all(isinstance(e, LogEvent) for e in evs)
    assert [len(e.msg) for e in evs] == [300, 300]  # [:120] 절단 부재


# ── A4: 라이브 프로세스 정리 계약 ─────────────────────────────────────

class _Proc:
    def __init__(self):
        self.killed = False

    def kill(self):
        self.killed = True


def test_kill_live_process_handles_ctx_proc(monkeypatch):
    monkeypatch.setattr(chzzktube.core.raw_log, "raw", lambda *a, **k: None)
    worker = DownloadWorker(["https://youtu.be/abcDEFghijk"], {},
                            {"canceled": False, "skip": False}, "auto", "auto")
    p_worker, p_ctx = _Proc(), _Proc()
    worker._live_proc = p_worker
    worker._ctx = SimpleNamespace(_live_proc=p_ctx)
    worker.kill_live_process()
    assert p_worker.killed and p_ctx.killed
    assert worker._live_proc is None


# ── A5: F12 버퍼 흡수 인덱스 ──────────────────────────────────────────

class _Win:
    def __init__(self, visible):
        self._visible = visible
        self.appends = []

    def isVisible(self):
        return self._visible

    def append(self, line, is_status=False):
        self.appends.append(line)


def test_mirror_full_log_index_advances_only_when_visible():
    mirror = main_module.MainWindow._mirror_full_log
    m = SimpleNamespace(_full_log_buf=deque(maxlen=100), _full_log_win_n=0,
                        verbose_win=_Win(False))
    mirror(m, "hidden line")
    assert len(m._full_log_buf) == 1 and m._full_log_win_n == 0

    m.verbose_win = _Win(True)
    mirror(m, "visible line")
    assert m._full_log_win_n == 2

    m.verbose_win._visible = False
    mirror(m, "gap line")
    pending = list(m._full_log_buf)[m._full_log_win_n:]
    assert len(pending) == 1 and "gap line" in pending[0]


# ── B5/B1/B2: 죽은 코드 제거 가드 ────────────────────────────────────

def test_removed_dead_symbols():
    import chzzktube.pipeline.progress_emitter as progress_emitter
    assert not hasattr(chzzktube.pipeline.progress_emitter, "emit_live_header")
    assert not hasattr(chzzktube.pipeline.progress_emitter, "_apply_client_opts")
    import chzzktube.control.pot_manager as pot_manager
    assert not hasattr(chzzktube.control.pot_manager, "POTProviderWorker")
    assert _chzzk_filename({}, {}, {}) == "chzzk.mp4"