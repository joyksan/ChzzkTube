"""치지직 라이브 라우팅·화질 선택·HLS URL 계약 (네트워크 차단)."""
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock, create_autospec

import pytest

import chzzktube.core.chzzk_api as api
import chzzktube.pipeline.target_downloader as td
from chzzktube.pipeline.classifier import ClassifiedTarget, ContentKind, ItemClassifier
from chzzktube.pipeline.dl_context import DownloadContext


@pytest.fixture
def live_item(ctx):
    """치지직 라이브용 ClassifiedTarget 생성 헬퍼."""
    return ClassifiedTarget(
        url=ctx.current_url,
        title="방송",
        kind=ContentKind.LIVE_CHZZK,
        capability=ItemClassifier.classify(ctx.current_url, raw_info={"is_live": True}).capability,
        platform_tag="CHZ",
        downloadable=True,
        needs_pot=False,
    )


@pytest.mark.parametrize("selection,limit,expected", [
    ("auto", "none", "1080"), ("auto", "720", "720"), ("720", "none", "720"),
    ("1080", "720", "1080"),
])
def test_live_uses_api_and_pipe(live, selection, limit, expected):
    ctx, info, analysis, youtube, record = live
    ctx.v_sel = selection
    ctx.cfg["max_video_res"] = limit
    failures = []
    item = {"url": ctx.current_url, "title": "", "age_limit": 0, "availability": "public", "is_live": True, "has_video": True, "has_audio": True, "downloadable": True, "needs_pot": False}
    assert td.download_target(ctx, item, failures) is True
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
    item = {"url": ctx.current_url, "title": "", "age_limit": 0, "availability": "public", "is_live": True, "has_video": True, "has_audio": True, "downloadable": True, "needs_pot": False}
    assert td.download_target(ctx, item, failures) is False
    record.assert_not_called()
    youtube.assert_not_called()
    assert len(failures) == 1
    assert failures[0][0] == ctx.current_url


def test_live_recording_failure_is_counted(live):
    ctx, info, analysis, youtube, record = live
    record.return_value = False
    failures = []
    item = {"url": ctx.current_url, "title": "", "age_limit": 0, "availability": "public", "is_live": True, "has_video": True, "has_audio": True, "downloadable": True, "needs_pot": False}
    assert td.download_target(ctx, item, failures) is False
    assert len(failures) == 1


def test_live_cancel_not_counted_as_failure(live):
    ctx, info, analysis, youtube, record = live
    record.return_value = False
    def cancel(*args, **kwargs):
        ctx.state["canceled"] = True
        return False
    record.side_effect = cancel
    failures = []
    item = {"url": ctx.current_url, "title": "", "age_limit": 0, "availability": "public", "is_live": True, "has_video": True, "has_audio": True, "downloadable": True, "needs_pot": False}
    assert td.download_target(ctx, item, failures) is False
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


def test_live_detail_parses_hls_and_progress():
    content = {
        "liveId": 21160101,
        "liveTitle": "롤",
        "status": "OPEN",
        "openDate": "2026-09-17 20:30:47",
        "channel": {"channelName": "한동숙"},
        "livePlaybackJson": (
            '{"media": [{"mediaId": "HLS", "protocol": "HLS", "path": "https://media.example/hls.m3u8"},'
            ' {"mediaId": "LLHLS", "protocol": "HLS", "path": "https://media.example/llhls.m3u8"}],'
            ' "live": {"status": "STARTED"}}'
        ),
    }
    assert api._parse_live_status(content) == "PROGRESS"
    assert api._parse_live_playback_url(content) == "https://media.example/hls.m3u8"
    assert api._parse_live_status({**content, "status": "CLOSE"}) == "CLOSE"
    assert api._parse_live_status({}) == "UNKNOWN"
    assert api._parse_live_playback_url({}) == ""


def test_live_api_routes_channel_hash_to_v2(monkeypatch):
    seen = []

    def fake_get_json(url, headers):
        seen.append(url)
        if "live-detail" in url:
            return {"content": {
                "liveId": 21160101, "liveTitle": "롤", "status": "OPEN",
                "openDate": "2026-09-17 20:30:47",
                "channel": {"channelName": "한동숙"},
                "livePlaybackJson": '{"media": [], "live": {"status": "STARTED"}}',
            }}
        raise AssertionError(f"v1 must not be used: {url}")

    monkeypatch.setattr(api, "_get_json", fake_get_json)
    info = api.analyze_chzzk_live_api("https://chzzk.naver.com/live/75cbf189b3bb8f9f687d2aca0d0a382b")
    assert seen == ["https://api.chzzk.naver.com/service/v2/channels/75cbf189b3bb8f9f687d2aca0d0a382b/live-detail"]
    assert (info["title"], info["live_status"], info["channel_name"]) == ("롤", "PROGRESS", "한동숙")
    assert info["live_id"] == "21160101"
    assert info["formats"] == []


def test_live_api_routes_numeric_id_to_v1(monkeypatch):
    seen = []

    def fake_get_json(url, headers):
        seen.append(url)
        return {"content": {"liveTitle": "t", "liveStatus": "PROGRESS"}}

    monkeypatch.setattr(api, "_get_json", fake_get_json)
    monkeypatch.setattr(api, "_fetch_m3u8_streams", lambda *a, **k: [])
    api.analyze_chzzk_live_api("https://chzzk.naver.com/live/12345")
    assert seen == ["https://api.chzzk.naver.com/service/v1/live/12345"]
