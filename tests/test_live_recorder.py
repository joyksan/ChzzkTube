
"""chzzktube.pipeline.live_recorder 파이프라인 계약 회귀 테스트.

[배경]
- prepare_live_paths가 모듈 함수로 존재하지 않아 라이브 경로 진입 시
  `_lr.prepare_live_paths` AttributeError가 터지던 결함 방지.
- record_live_stream이 handle_stream_finish를 인스턴스 메서드인 양
  호출하던 착각(worker.handle_stream_finish) 회귀 방지.
- handle_stream_finish 내부의 worker.log_success_info 오호출(DownloadContext에
  없는 메서드) → chzzktube.pipeline.progress_emitter 모듈 함수 계약 회귀 방지.
"""
import chzzktube
import inspect
from io import BytesIO
from unittest.mock import Mock

from chzzktube.core.speed_window import SpeedWindow
from chzzktube.pipeline.dl_context import DownloadContext

import chzzktube.pipeline.live_recorder as live_recorder


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
    assert "handle_stream_finish(ctx" in src


def test_no_self_import_alias():
    """live_recorder는 자기 자신을 _lr 별칭으로 재참조하지 않는다 (계층 정합)."""
    src = inspect.getsource(chzzktube.pipeline.live_recorder)
    assert "import chzzktube.pipeline.live_recorder as _lr" not in src
    assert "_lr." not in src


def test_stream_finish_uses_module_log_success_info():
    """완료 로그는 chzzktube.pipeline.progress_emitter 모듈 함수로 발행한다 (ctx 메서드 오호출 금지)."""
    src = inspect.getsource(live_recorder.handle_stream_finish)
    assert "worker.log_success_info" not in src
    assert "log_success_info(ctx" in src


def test_record_live_stream_writes_stdout_to_out_file(monkeypatch, tmp_path):
    """FFmpeg stdout 릴레이 경로에서 Python만 최종 파일을 기록한다."""
    proc = Mock()
    proc.stdout = BytesIO(b"abcdef")
    proc.stderr = BytesIO(b"frame= 1\n")
    proc.poll.return_value = None
    proc.wait.return_value = 0

    finish = Mock(return_value=True)
    monkeypatch.setattr(live_recorder.subprocess, "Popen", Mock(return_value=proc))
    monkeypatch.setattr(live_recorder, "handle_stream_finish", finish)
    monkeypatch.setattr(live_recorder, "raw_log", Mock())

    out_file = tmp_path / "live.ts"
    ctx = DownloadContext(
        cfg={"download_path": str(tmp_path), "container": "mp4"},
        current_url="https://youtu.be/abcDEFghijk",
        speed_win=SpeedWindow(),
    )

    ok = live_recorder.record_live_stream(ctx, ["ffmpeg"], str(out_file))

    assert ok is True
    assert out_file.read_bytes() == b"abcdef"
    assert ctx.speed_win._last_total == 6
    proc.wait.assert_called_once()
    proc.kill.assert_not_called()
    finish.assert_called_once_with(ctx, True, str(out_file), 0)


def test_record_live_stream_propagates_nonzero_exit(monkeypatch, tmp_path):
    """비정상 종료 코드는 FAIL 로그와 finish로 전달된다 (성공 위장 금지)."""
    proc = Mock()
    proc.stdout = BytesIO(b"x")
    proc.stderr = BytesIO(b"")
    proc.poll.return_value = None
    proc.wait.return_value = 255

    finish = Mock(wraps=live_recorder.handle_stream_finish)
    raw = Mock()
    monkeypatch.setattr(live_recorder.subprocess, "Popen", Mock(return_value=proc))
    monkeypatch.setattr(live_recorder, "handle_stream_finish", finish)
    monkeypatch.setattr(live_recorder, "raw_log", raw)

    ctx = DownloadContext(
        cfg={"download_path": str(tmp_path), "container": "mp4"},
        current_url="https://youtu.be/abcDEFghijk",
        speed_win=SpeedWindow(),
    )

    ok = live_recorder.record_live_stream(ctx, ["ffmpeg"], str(tmp_path / "live.ts"))

    assert ok is False
    assert finish.call_args.args[-1] == 255
    fail_events = [
        call.args[1]
        for call in raw.raw.call_args_list
        if len(call.args) > 1 and getattr(call.args[1], "status", "") == "FAIL"
    ]
    assert fail_events, raw.raw.call_args_list


def test_remux_failure_preserves_temporary_recording(monkeypatch, tmp_path):
    source = tmp_path / "live_temp.ts"
    source.write_bytes(b"recorded")
    ctx = DownloadContext(cfg={"container": "mp4"})
    monkeypatch.setattr(live_recorder.subprocess, "run", Mock(side_effect=OSError("ffmpeg failed")))
    monkeypatch.setattr(live_recorder, "raw_log", Mock())

    assert live_recorder.handle_stream_finish(ctx, True, str(source)) is False
    assert source.read_bytes() == b"recorded"


def test_cancel_preserves_temporary_recording(monkeypatch, tmp_path):
    source = tmp_path / "live_temp.ts"
    source.write_bytes(b"partial")
    ctx = DownloadContext(cfg={}, state={"canceled": True})
    monkeypatch.setattr(live_recorder, "raw_log", Mock())

    assert live_recorder.handle_stream_finish(ctx, True, str(source), -9) is False
    assert source.read_bytes() == b"partial"
    assert ctx.live_partially_saved is True


def test_empty_recording_is_not_success(monkeypatch, tmp_path):
    source = tmp_path / "live_temp.ts"
    source.touch()
    ctx = DownloadContext(cfg={})
    remux = Mock()
    monkeypatch.setattr(live_recorder, "_remux_live_output", remux)
    monkeypatch.setattr(live_recorder, "raw_log", Mock())

    assert live_recorder.handle_stream_finish(ctx, True, str(source)) is False
    remux.assert_not_called()

def test_real_ffmpeg_relay_and_remux(tmp_path):
    """네트워크 없이 실제 stdout → TS → MP4/MKV 컨테이너를 검사한다."""
    import json
    import shutil
    import subprocess

    import pytest

    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        pytest.skip("ffmpeg and ffprobe are required for integration test")
    for container in ("mp4", "mkv"):
        source = tmp_path / f"{container}_temp.ts"
        output = tmp_path / f"{container}.{container}"
        ctx = DownloadContext(cfg={"container": container}, speed_win=SpeedWindow())
        cmd = [ffmpeg, "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440",
               "-t", "0.2", "-c:a", "aac", "-f", "mpegts", "pipe:1"]

        assert live_recorder.record_live_stream(ctx, cmd, str(source), "FFmpeg") is True
        assert not source.exists()
        assert output.stat().st_size > 0
        probe = subprocess.run(
            [ffprobe, "-v", "error", "-show_format", "-of", "json", str(output)],
            capture_output=True, text=True, check=True, timeout=5,
        )
        name = json.loads(probe.stdout)["format"]["format_name"]
        assert ("mp4" if container == "mp4" else "matroska") in name
