"""Task 1-1: MediaController 상태 머신 전이 및 수명주기 런타임 검증."""
from unittest.mock import Mock

from chzzktube.control.controller import MediaController


def test_media_controller_lifecycle_state_transitions():
    """MediaController의 다운로드 및 취소/스킵 상태 머신 전이를 런타임에 검증."""
    view_mock = Mock()
    view_mock.extracted_data = {"info": "existing", "v_list": [1], "a_list": [2]}
    ctrl = MediaController(view_mock)

    # 초기 상태
    assert ctrl.running is False
    assert ctrl.state.canceled is False
    assert ctrl.state.skip is False

    # 1. begin_download
    ctrl.begin_download()
    assert ctrl.running is True
    assert ctrl.state.canceled is False
    assert ctrl.state.skip is False

    # 2. request_cancel (running 상태일 때 canceled=True 전이 및 시그널 방출)
    canceled_spies = []
    ctrl.canceled_changed.connect(canceled_spies.append)
    ctrl.request_cancel()
    assert ctrl.state.canceled is True
    assert canceled_spies == [True]

    # 3. request_skip (running 상태일 때 skip=True 전이 및 시그널 방출)
    skip_spies = []
    ctrl.skip_changed.connect(skip_spies.append)
    ctrl.request_skip()
    assert ctrl.state.skip is True
    assert skip_spies == [True]

    # 4. on_download_finished (종료 및 상태 리셋, view.extracted_data 초기화)
    ctrl.on_download_finished(success_count=1, fail_count=0)
    assert ctrl.running is False
    assert ctrl.state.canceled is False
    assert ctrl.state.skip is False
    assert view_mock.extracted_data == {"info": None, "v_list": [], "a_list": []}
