"""live_recorder 파이프라인 계약 회귀 테스트.

[배경]
- prepare_live_paths가 모듈 함수로 존재하지 않아 라이브 경로 진입 시
  `_lr.prepare_live_paths` AttributeError가 터지던 결함 방지.
- record_live_stream이 handle_stream_finish를 인스턴스 메서드인 양
  호출하던 착각(worker.handle_stream_finish) 회귀 방지.
- handle_stream_finish 내부의 worker.log_success_info 오호출(DownloadContext에
  없는 메서드) → progress_emitter 모듈 함수 계약 회귀 방지.
"""
import inspect

import live_recorder


def test_prepare_live_paths_derives_temp_and_thumb():
    temp_ts, thumb, out_file = live_recorder.prepare_live_paths(
        None, "/dl/video.mp4", "http://example.com/thumb.jpg"
    )
    assert temp_ts == "/dl/video_temp.ts"
    assert thumb == "/dl/video_temp_thumb.jpg"
    assert out_file == "/dl/video.mp4"


def test_prepare_live_paths_without_thumb():
    temp_ts, thumb, _ = live_recorder.prepare_live_paths(None, "/dl/live.mkv", None)
    assert temp_ts == "/dl/live_temp.ts"
    assert thumb is None


def test_stream_finish_is_module_function():
    """handle_stream_finish는 모듈 함수이며 record_live_stream은 직접 호출한다."""
    assert inspect.isfunction(live_recorder.handle_stream_finish)
    assert inspect.isfunction(live_recorder.prepare_live_paths)
    src = inspect.getsource(live_recorder.record_live_stream)
    assert "worker.handle_stream_finish" not in src
    assert "handle_stream_finish(worker" in src


def test_no_self_import_alias():
    """live_recorder는 자기 자신을 _lr 별칭으로 재참조하지 않는다 (계층 정합)."""
    src = inspect.getsource(live_recorder)
    assert "import live_recorder as _lr" not in src
    assert "_lr." not in src


def test_stream_finish_uses_module_log_success_info():
    """완료 로그는 progress_emitter 모듈 함수로 발행한다 (ctx 메서드 오호출 금지)."""
    src = inspect.getsource(live_recorder.handle_stream_finish)
    assert "worker.log_success_info" not in src
    assert "log_success_info(worker" in src
