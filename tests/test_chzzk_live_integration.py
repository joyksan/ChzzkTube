"""외부 방송 없이 치지직 API 분석부터 실제 HLS 녹화까지 검증한다."""
from io import BytesIO
from pathlib import Path
import shutil
import subprocess
from unittest.mock import Mock

import pytest

import chzzktube.core.chzzk_api as api
import chzzktube.pipeline.target_downloader as td
from chzzktube.core.speed_window import SpeedWindow
from chzzktube.pipeline.dl_context import DownloadContext


def test_chzzk_live_real_hls_pipeline(monkeypatch, tmp_path):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("ffmpeg is required")
    playlist = tmp_path / "source.m3u8"
    # 너무 작은 단색 MPEG-2 세그먼트는 FFmpeg probe가 MPEG-PS로 오인한다.
    subprocess.run(
        [ffmpeg, "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=25",
         "-t", "2", "-c:v", "mpeg2video", "-f", "hls", "-hls_time", "1", str(playlist)],
        check=True, capture_output=True, timeout=5,
    )
    hls_url = playlist.as_uri()
    analysis = Mock(return_value={
        "title": "integration", "live_id": "abc", "live_status": "PROGRESS",
        "formats": [{"id": "local", "height": 240, "bitrate": 1000, "url": hls_url}],
    })
    monkeypatch.setattr(api, "analyze_chzzk_live_api", analysis)
    # 실프로세스를 실행하는 spy: 명령 관찰만 하고 FFmpeg 동작은 대체하지 않는다.
    spawn = Mock(wraps=subprocess.Popen)
    monkeypatch.setattr(subprocess, "Popen", spawn)
    ctx = DownloadContext(
        cfg={"download_path": str(tmp_path), "container": "mkv"},
        current_url="https://chzzk.naver.com/live/abc", speed_win=SpeedWindow(),
    )
    failures = []

    assert td.download_target(ctx, ctx.current_url, failures) is True

    analysis.assert_called_once_with(ctx.current_url)
    cmd = spawn.call_args_list[0].args[0]
    assert cmd == ["ffmpeg", "-y", "-i", hls_url, "-c", "copy", "-f", "mpegts", "pipe:1"]
    assert spawn.call_args_list[0].kwargs["stdout"] == subprocess.PIPE
    output = tmp_path / "integration [abc].mkv"
    assert output.stat().st_size > 0
    assert not (tmp_path / "integration [abc]_temp.ts").exists()
    assert failures == []
