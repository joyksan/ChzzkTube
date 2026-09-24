"""Task 1-1 RED: MediaController 중복 메서드 정의 회귀 테스트.

HANDOVER §6 '시그널 다중 emit/중복 판정' 유사 — 동일 메서드 2회 정의는
뒤쪽 정의가 앞쪽을 덮어써 데드코드를 양산한다. 앞쪽 5종은 frozen
SessionState에 없는 state.update()와 존재하지 않는 _abandon_analyzer를
참조하므로 반드시 1회 정의여야 한다.
"""
import pathlib


def test_media_controller_has_no_duplicate_session_methods():
    src = pathlib.Path("chzzktube/control/controller.py").read_text(encoding="utf-8")
    for name in (
        "def begin_download",
        "def end_download",
        "def on_download_finished",
        "def request_cancel",
        "def request_skip",
    ):
        assert src.count(name) == 1, f"duplicate {name}"
    assert "self.state.update(" not in src
    assert "_abandon_analyzer" not in src
