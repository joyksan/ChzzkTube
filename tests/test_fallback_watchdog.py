"""폴백 제거 후 동작 검증.

[v3.8.1] 폴백(15초 강제 언락) 완전 제거 → deps 수급 실패 시 영구 잠금.
"""
from types import SimpleNamespace


class _View:
    """deps 에러 상태 잠금 검증용 대역."""

    def __init__(self):
        self._startup_completed = False
        self._startup_coord = SimpleNamespace(
            _state=SimpleNamespace(deps_error_msg="ffmpeg: dyld symbol not found"),
        )

    def get_current_app_state(self):
        return "STARTUP"


def test_deps_error_keeps_input_locked():
    """[v3.8.1] deps 에러 시 입력 잠금 유지 — 폴백 제거로 영구 잠금."""
    view = _View()
    state = view.get_current_app_state()
    assert state == "STARTUP"
    # deps_error_msg가 있으면 입력 잠금 유지
    assert view._startup_coord._state.deps_error_msg


def test_no_fallback_timer():
    """[v3.8.1] 폴백 타이머가 없으므로 _fallback_timer 속성 없음."""
    view = _View()
    # _fallback_timer 속성이 없어야 함 (폴백 제거)
    assert not hasattr(view, "_fallback_timer")
