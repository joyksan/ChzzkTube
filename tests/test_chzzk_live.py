"""치지직 라이브 라우팅·화질 선택·HLS URL 계약 (네트워크 차단)."""
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock, create_autospec

import pytest

import chzzktube.core.chzzk_api as api
import chzzktube.pipeline.target_downloader as td
from chzzktube.pipeline.dl_context import DownloadContext


@pytest.fixture
def live(monkeypatch, tmp_path):
    formats = [
        {"id": "1080", "height": 1080, "url": "https://media.example/1080.m3u8"},
        {"id": "720", "height": 720, "url": "https://media.example/720.m3u8"},
    ]
    info = {"title": "방송", "live_id": "abc", "live_status": "PROGRESS", "formats": formats}
    analysis = Mock(return_value=info)
    monkeypatch.setattr(api, "analyze_chzzk_live_api", analysis)
    youtube = Mock(return_value=False)
    monkeypatch.setattr(td, "_download_youtube_live", youtube)
    monkeypatch.setattr(td, "_is_youtube_live_url", Mock(side_effect=AssertionError("YouTube probe")))
    record = create_autospec(td._lr.record_live_stream, return_value=True)
    monkeypatch.setattr(td._lr, "record_live_stream", record)
    monkeypatch.setattr(td.raw_log, "raw", Mock())
    ctx = DownloadContext(cfg={"download_path": str(tmp_path)},
                          current_url="https://chzzk.naver.com/live/abc", is_live_hint=True)
    return ctx, info, analysis, youtube, record


@pytest.mark.parametrize("selection,limit,expected", [
    ("auto", "none", "1080"), ("auto", "720", "720"), ("720", "none", "720"),
    ("1080", "720", "1080"),
])
def test_live_uses_api_and_pipe(live, selection, limit, expected):
    ctx, info, analysis, youtube, record = live
    ctx.v_sel = selection
    ctx.cfg["max_video_res"] = limit
    failures = []
    assert td.download_target(ctx, ctx.current_url, failures) is True
    analysis.assert_called_once_with(ctx.current_url)
    youtube.assert_not_called()
    record.assert_called_once()
    args, kwargs = record.call_args
    assert args[0] is ctx
    cmd, source = args[1:3]
    assert cmd[cmd.index("-i") + 1] == f"https://media.example/{expected}.m3u8"
    assert cmd[-3:] == ["-f", "mpegts", "pipe:1"]
    assert source not in cmd
    assert Path(source).name == "방송 [abc]_temp.ts"
    assert Path(source).parent == Path(ctx.cfg["download_path"])
    assert kwargs["log_tag"] == "FFmpeg"
    assert ctx._meta_logged is True
    assert failures == []


@pytest.mark.parametrize("problem", ["offline", "empty", "missing_url", "missing_selection", "resolution"])
def test_live_unavailable_does_not_start_recording(live, problem):
    ctx, info, analysis, youtube, record = live
    if problem == "offline":
        info["live_status"] = "CLOSE"
    elif problem == "empty":
        info["formats"] = []
    elif problem == "missing_url":
        for fmt in info["formats"]:
            fmt["url"] = ""
    elif problem == "missing_selection":
        ctx.v_sel = "gone"
    else:
        ctx.cfg["max_video_res"] = "360"
    failures = []
    assert td.download_target(ctx, ctx.current_url, failures) is False
    record.assert_not_called()
    youtube.assert_not_called()
    assert len(failures) == 1
    assert failures[0][0] == ctx.current_url


def test_live_recording_failure_is_counted(live):
    ctx, info, analysis, youtube, record = live
    record.return_value = False
    failures = []
    assert td.download_target(ctx, ctx.current_url, failures) is False
    assert len(failures) == 1


def test_live_cancel_not_counted_as_failure(live):
    ctx, info, analysis, youtube, record = live
    record.return_value = False
    def cancel(*args, **kwargs):
        ctx.state["canceled"] = True
        return False
    record.side_effect = cancel
    failures = []
    assert td.download_target(ctx, ctx.current_url, failures) is False
    record.assert_called_once()
    assert failures == []


def test_hls_attributes_and_relative_urls(monkeypatch):
    manifest = b'''#EXTM3U
#EXT-X-STREAM-INF:BANDWIDTH=4000000,RESOLUTION=1920x1080,CODECS="avc1.640028,mp4a.40.2"
high/index.m3u8
#EXT-X-STREAM-INF:BANDWIDTH="2000000",RESOLUTION="1280x720"
/low/index.m3u8
'''
    monkeypatch.setattr(api.urllib.request, "urlopen", lambda *a, **k: BytesIO(manifest))
    formats = api._fetch_m3u8_streams("https://media.example/live/master.m3u8", {})
    assert [f["height"] for f in formats] == [1080, 720]
    assert [f["bitrate"] for f in formats] == [4000, 2000]
    assert [f["url"] for f in formats] == [
        "https://media.example/live/high/index.m3u8", "https://media.example/low/index.m3u8",
    ]
    # 분석 때 노출한 id를 다운로드 때도 그대로 선택할 수 있어야 한다.
    assert [f["id"] for f in formats] == ["high/index.m3u8", "/low/index.m3u8"]
