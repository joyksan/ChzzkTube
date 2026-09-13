"""분석 상태 머신 회귀 테스트 — ENTER 잠금/URL 클리어 크래시 수리 검증.

배경 (v3.4.0 회귀):
- `on_analyze_success`/`on_analyze_error`가 `ctrl.state["analyzing"]`을 해제하지 않아
  State-Button Matrix(`get_current_app_state`)가 ANALYZING에 영구 고정 → `toggle_download`가
  `state != "IDLE"`에서 조기 반환 → ENTER 잠금.
  (증상: 분석 완료 직후 "gated=False age_limit=0 availability=public" 로그와 함께 입력 무반응)
- `on_url_changed` URL 클리어 분기가 MVC 이관(94f1ee4)에서 사라진
  `_abandon_analyze_worker()`를 호출 → AttributeError.

여기서는 test_gate_integration.py와 동일하게 MainWindow 비공개 메서드를
가벼운 self 대역에 바인딩해 계약만 검증한다 (헤드리스 위젯 불필요).
"""
from types import SimpleNamespace

from controller import MediaController

import main as main_module


class _FakeInput:
    def __init__(self, text="https://youtu.be/abcDEFghijk"):
        self._text = text
        self.enabled = True

    def text(self):
        return self._text

    def setText(self, t):
        self._text = t

    def setEnabled(self, v):
        self.enabled = bool(v)

    def setFocus(self):
        pass


class _FakeConsole:
    def __init__(self):
        self.cleared = 0

    def clear_status_line(self):
        self.cleared += 1


class _FakeMain:
    """MainWindow의 분석/상태 머신/URL 변경 메서드를 실제로 바인딩할 대역."""

    def __init__(self, url="https://youtu.be/abcDEFghijk"):
        self.ctrl = MediaController(self)
        self._startup_completed = True
        self._pot_manager = SimpleNamespace(
            is_busy=lambda: False,
            is_ready=lambda: True,
            use_existing=lambda: None,
            ensure_ready=lambda *a, **k: None,
        )
        self.url_input = _FakeInput(url)
        self.console = _FakeConsole()
        self.extracted_data = {
            "info": {"age_limit": 0, "availability": "public", "is_live": False},
            "v_list": [],
            "a_list": [],
            "yt_client": "auto",
        }
        self.cfg = {}
        self.started = []
        self._pending_download = None
        self._pick_pending = False
        self._pick_targets = []
        self._last_input_len = 0
        self.analyze_timer = SimpleNamespace(stop=lambda: None)

    # ── 실제 MainWindow 메서드 바인딩 ─────────────────────────────
    def _is_stale_analyze_signal(self):
        return main_module.MainWindow._is_stale_analyze_signal(self)

    def get_current_app_state(self):
        return main_module.MainWindow.get_current_app_state(self)

    def on_analyze_success(self, data):
        main_module.MainWindow.on_analyze_success(self, data)

    def on_analyze_error(self, err_msg):
        main_module.MainWindow.on_analyze_error(self, err_msg)

    def toggle_download(self):
        main_module.MainWindow.toggle_download(self)

    def on_url_changed(self):
        main_module.MainWindow.on_url_changed(self)

    def _ensure_pot_for_info(self, info):
        main_module.MainWindow._ensure_pot_for_info(self, info)

    # ── stub ──────────────────────────────────────────────────────
    def append_concise_log(self, *a, **k):
        pass

    def stop_analysis_anim(self, ok=True):
        pass

    def update_ui_state(self):
        pass

    def _start_download(self, targets, v_id, a_id):
        self.started.append((targets, v_id, a_id))

    def _show_pick_menu(self, data):
        main_module.MainWindow._show_pick_menu(self, data)

    def _discard_analysis_result(self):
        pass


def _public_data():
    return {
        "info": {"age_limit": 0, "availability": "public", "is_live": False},
        "v_list": [],
        "a_list": [],
        "yt_client": "auto",
    }


def test_analyzing_cleared_on_success_unlocks_enter():
    """분석 성공 → analyzing 해제 → IDLE 복귀 → ENTER로 다운로드 재개."""
    m = _FakeMain()
    m.ctrl.state["analyzing"] = True  # spawn_analyzer 직후 상태

    m.on_analyze_success(_public_data())

    assert m.ctrl.state["analyzing"] is False
    assert m.get_current_app_state() == "IDLE"
    # ENTER (toggle_download) — ANALYZING에 갇히면 started가 비어 있다.
    m.toggle_download()
    assert m.started == [(["https://youtu.be/abcDEFghijk"], "auto", "auto")]


def test_analyzing_cleared_on_error():
    """분석 실패도 상태 종료 — analyzing 해제되어 IDLE 복귀."""
    m = _FakeMain()
    m.ctrl.state["analyzing"] = True

    m.on_analyze_error("media info fail")

    assert m.ctrl.state["analyzing"] is False
    assert m.get_current_app_state() == "IDLE"


def _pick_data():
    """포맷 고르기용 — v_list를 채워 _show_pick_menu가 메뉴 경로를 타게 한다."""
    return {
        "info": {"age_limit": 0, "availability": "public", "is_live": False},
        "v_list": [
            {"id": "137", "height": 1080, "fps": 30, "tbr": 3000,
             "vcodec": "avc1", "acodec": "mp4a", "proto": "https",
             "ext": "mp4", "label": "1080p H.264"},
        ],
        "a_list": [],
        "yt_client": "auto",
    }


def test_pick_flow_not_shadowed_by_analyzing():
    """딥 분석(포맷 고르기)에서 analyzing 해제로 PICKING 상태가 정상 활성화."""
    m = _FakeMain()
    m._pick_pending = True
    m._pick_targets = ["https://youtu.be/abcDEFghijk"]
    m.ctrl.state["analyzing"] = True

    m.on_analyze_success(_pick_data())

    assert m.ctrl.state["analyzing"] is False
    assert m.ctrl.state["picking"] is True
    assert m.get_current_app_state() == "PICKING"


def test_duplicate_result_after_completion_is_dropped():
    """완료 후 큐잉된 중복 시그널은 stale 판정으로 폐기 — extracted_data 불변."""
    m = _FakeMain()
    m.ctrl.state["analyzing"] = True
    m.on_analyze_success(_public_data())
    snapshot = m.extracted_data

    # 같은 분석의 이중 emit (유령 시그널) — analyzing이 False여야 stale로 폐기.
    m.on_analyze_success(_public_data())
    assert m.extracted_data is snapshot


def test_on_url_changed_clear_uses_controller_abandon():
    """URL 클리어 시 죽은 _abandon_analyze_worker 호출이 아니라 controller 유기로 동작.

    - 이전: self._abandon_analyze_worker() → 정의 없음 → AttributeError
      → console.clear_status_line() 이후 로직이 실행되지 않았다.
    - 이후: ctrl._abandon_analyzer() 경유 — 워커 참조 해제 + analyzing 해제.
    """
    m = _FakeMain()
    # 진행 중이던 분석 워커 흉내 (비실행 상태) — _abandon_analyzer가 참조를 끊어야 한다.
    m.ctrl.worker_analyze = SimpleNamespace(isRunning=lambda: False)
    m.ctrl.state["analyzing"] = True
    m.url_input.setText("")

    # 예외 없이 실행되어야 한다.
    m.on_url_changed()

    assert m.console.cleared == 1
    assert m.ctrl.worker_analyze is None
    assert m.ctrl.state["analyzing"] is False
    assert m.extracted_data["info"] is None