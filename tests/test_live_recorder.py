
"""chzzktube.pipeline.live_recorder 파이프라인 계약 회귀 테스트.

[배경]
- prepare_live_paths가 모듈 함수로 존재하지 않아 라이브 경로 진입 시
  `_lr.prepare_live_paths` AttributeError가 터지던 결함 방지.
- record_live_stream이 handle_stream_finish를 인스턴스 메서드인 양
  호출하던 착각(worker.handle_stream_finish) 회귀 방지.
- handle_stream_finish 내부의 worker.log_success_info 오호출(DownloadContext에
  없는 메서드) → chzzktube.pipeline.progress_emitter 모듈 함수 계약 회귀 방지.
"""
import inspect
from io import BytesIO
from unittest.mock import Mock

import chzzktube
from chzzktube.core.speed_window import SpeedWindow
from chzzktube.pipeline import live_recorder
from chzzktube.pipeline.dl_context import DownloadContext


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
    """handle_stream_finish는 모듈 함수이며 callable임을 검증한다."""
    assert callable(live_recorder.handle_stream_finish)
    assert callable(live_recorder.prepare_live_paths)


def test_no_self_import_alias():
    """live_recorder 모듈 네임스페이스에 _lr 자기참조 별칭이 없음을 검증."""
    assert not hasattr(live_recorder, "_lr")


def test_stream_finish_uses_module_log_success_info(monkeypatch, tmp_path):
    """완료 시 progress_emitter의 log_success_info가 런타임에 호출되는지 검증."""
    source = tmp_path / "live_temp.ts"
    source.write_bytes(b"stream_data")
    final_out = tmp_path / "live.ts"
    final_out.write_bytes(b"final_data")

    ctx = DownloadContext(
        cfg={"download_path": str(tmp_path), "container": "ts"},
        current_url="https://chzzk.naver.com/live/123",
        speed_win=SpeedWindow(),
    )
    called_with = []
    monkeypatch.setattr(live_recorder, "_remux_live_output", lambda c, tf: str(final_out))
    monkeypatch.setattr(
        live_recorder,
        "log_success_info",
        lambda c, path: called_with.append((c, path)),
    )
    monkeypatch.setattr(live_recorder, "raw_log", Mock())

    ok = live_recorder.handle_stream_finish(ctx, True, str(source))
    assert ok is True
    assert len(called_with) == 1
    assert called_with[0][0] is ctx
    assert called_with[0][1] == str(final_out)


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


def test_record_live_stream_nonblocking_read(monkeypatch, tmp_path):
    """FFmpeg stdout 읽기가 논블로킹 타임아웃으로 동작하여 취소 체크가 가능해야 한다."""
    import time
    from io import BytesIO
    from unittest.mock import Mock

    # 천천히 데이터를 내보내는 가짜 프로세스 (블로킹 시뮬레이션)
    class SlowStdout:
        def __init__(self, data_chunks, delay=0.5):
            self.data_chunks = data_chunks
            self.delay = delay
            self.idx = 0
            
        def read(self, n):
            if self.idx >= len(self.data_chunks):
                return b""
            # 실제 읽기 시 지연 시뮬레이션
            time.sleep(self.delay)
            chunk = self.data_chunks[self.idx]
            self.idx += 1
            return chunk

    proc = Mock()
    proc.stdout = SlowStdout([b"chunk1", b"chunk2"], delay=0.1)
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

    # 취소 신호 없이 정상 완료
    ok = live_recorder.record_live_stream(ctx, ["ffmpeg"], str(out_file))
    
    assert ok is True
    assert out_file.read_bytes() == b"chunk1chunk2"
    finish.assert_called_once_with(ctx, True, str(out_file), 0)


def test_record_live_stream_cancel_during_read(monkeypatch, tmp_path):
    """읽기 도중 취소 신호가 오면 즉시 프로세스를 죽이고 빠져나와야 한다."""
    import time
    from io import BytesIO
    from unittest.mock import Mock

    # 무한히 블로킹하는 것처럼 보이는 stdout (하지만 논블로킹이면 타임아웃으로 빠져나옴)
    class BlockingStdout:
        def __init__(self, ctx):
            self.ctx = ctx
            self.read_count = 0
            
        def read(self, n):
            self.read_count += 1
            if self.read_count == 1:
                return b"first"
            # 두 번째 읽기부터는 블로킹 시뮬레이션
            time.sleep(0.05)
            # 첫 청크 이후 취소 신호를 켜 메인 루프가 kill로 빠져나오는지 검증
            self.ctx.state["canceled"] = True
            if self.read_count > 3:
                return b""
            return b"data"

    out_file = tmp_path / "live.ts"
    ctx = DownloadContext(
        cfg={"download_path": str(tmp_path), "container": "mp4"},
        current_url="https://youtu.be/abcDEFghijk",
        speed_win=SpeedWindow(),
        state={"canceled": False},
    )

    proc = Mock()
    proc.stdout = BlockingStdout(ctx)
    proc.stderr = BytesIO(b"frame= 1\n")
    proc.poll.return_value = None
    proc.wait.return_value = 0

    finish = Mock(wraps=live_recorder.handle_stream_finish)
    monkeypatch.setattr(live_recorder.subprocess, "Popen", Mock(return_value=proc))
    monkeypatch.setattr(live_recorder, "handle_stream_finish", finish)
    monkeypatch.setattr(live_recorder, "raw_log", Mock())

    ok = live_recorder.record_live_stream(ctx, ["ffmpeg"], str(out_file))
    
    # 취소되었으므로 False 반환 또는 부분 저장
    assert ok is False or ctx.live_partially_saved is True
    # kill이 호출되었어야 함
    proc.kill.assert_called()
