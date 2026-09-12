"""tool_log 래퍼 + 외부툴 설정 fit 회귀 테스트."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def test_double_timestamp_absent():
    """이중 ts 금지 — TUI 컬럼 + F12 스탬프가 합쳐져도 ts는 1개.

    컬럼 라인 자체의 '[HH:MM:SS]' 1개 + 진행 바 '[██░░]' 대괄호는 별개.
    진짜 판정: _mirror_full_log에 컬럼 라인이 아닌 원문이 들어가므로
    ts가 중복 스탬핑되지 않는다.
    """
    import re
    from log_console import format_log_line
    line = format_log_line(stage="DL", status="RUN", platform="YT",
                           spec="1080p30", speed="12.4M/s",
                           pct=65.0, bar_frac=0.65, msg="title")
    ts = re.findall(r"\[\d{2}:\d{2}:\d{2}\]", line)
    assert len(ts) == 1  # 컬럼 라인 내 타임스탬프 1회


def test_f12_raw_msg_no_double_stamp():
    """F12 원문 보존 — 컬럼 문자열이 아닌 msg 원문이 적재된다."""
    from types import SimpleNamespace
    from log_event import LogEvent
    import main as main_module

    class _FakeMain:
        def __init__(self):
            self.rendered = []
            self._last_status_line = ""

        def _mirror_full_log(self, line, is_status=False):
            self.rendered.append((line, is_status))

    m = _FakeMain()
    ev = LogEvent(stage="DL", status="RUN", platform="YT", spec="1080p30",
                  speed="12.4M/s", pct=65.0, bar_frac=0.65, msg="raw line")
    main_module.MainWindow._mirror_event_full(m, ev, False)
    # 컬럼화 없이 원문만 — 스탬프는 _mirror_full_log 1곳에서만 찍힌다.
    assert m.rendered == [("raw line", False)]


def test_apply_post_opts_subtitles_thumbnail_chapters():
    from client_opts import _apply_post_opts
    opts = _apply_post_opts({}, {"embed_subtitles": True, "subtitle_langs": "ko,en",
                                 "embed_thumbnail": True, "embed_chapters": True})
    assert opts["writesubtitles"] is True
    assert opts["subtitleslangs"] == ["ko", "en"]
    keys = [p["key"] for p in opts["postprocessors"]]
    assert "FFmpegSubtitlesConvertor" in keys
    assert "FFmpegEmbedSubtitle" in keys
    assert "EmbedThumbnail" in keys
    assert "FFmpegMetadata" in keys


def test_apply_post_opts_all_langs():
    from client_opts import _apply_post_opts
    opts = _apply_post_opts({}, {"embed_subtitles": True, "subtitle_langs": "all"})
    assert opts.get("allsubtitles") is True
    assert "subtitleslangs" not in opts


def test_apply_post_opts_off_is_clean():
    from client_opts import _apply_post_opts
    opts = _apply_post_opts({}, {"embed_subtitles": False, "embed_thumbnail": False,
                                 "embed_chapters": False})
    assert opts.get("postprocessors") == []
    assert "writesubtitles" not in opts


def test_concurrent_fragments_fit():
    from client_opts import _concurrent_fragments
    assert _concurrent_fragments({"fast_download": True, "concurrent_fragments": 8}) == 8
    assert _concurrent_fragments({"fast_download": False, "concurrent_fragments": 8}) == 1
    assert _concurrent_fragments({"fast_download": True}) == 4
    assert _concurrent_fragments({"fast_download": True, "concurrent_fragments": 99}) == 16


def test_streamlink_quality_fit():
    from types import SimpleNamespace
    import target_downloader as td

    seen = {}

    class _FakeLR:
        @staticmethod
        def prepare_live_paths(ctx, out_file, thumb):
            return ("t.ts", None, out_file)

        @staticmethod
        def record_live_stream(ctx, cmd, temp_ts, out_file, thumb):
            seen["cmd"] = cmd
            return True

    orig = td._lr
    td._lr = _FakeLR
    try:
        ctx = SimpleNamespace(cfg={"download_path": "/tmp", "streamlink_quality": "720p,best"},
                              speed_win=SimpleNamespace(reset=lambda: None))
        assert td._download_streamlink(ctx, "https://x") is True
        assert seen["cmd"] == ["streamlink", "https://x", "720p,best", "-O"]
    finally:
        td._lr = orig


def test_tool_log_protocols_importable():
    import tool_log
    assert hasattr(tool_log, "ToolLogger")
    assert hasattr(tool_log, "LineRunner")
    assert hasattr(tool_log, "TokenProvider")
    assert callable(tool_log.make_ytdlp_logger)
    assert callable(tool_log.pump)
    assert callable(tool_log.run_cli)


def test_tool_log_pump_absorbs_stderr():
    """pump: 자식 stderr를 LogEvent 원문으로 흡수 → raw 버스."""
    import raw_log
    import tool_log

    got = []
    orig_raw = raw_log.raw
    raw_log.raw = lambda tag, msg, **kw: got.append((tag, str(getattr(msg, "msg", msg)), kw))
    try:
        import sys
        cmd = [sys.executable, "-c",
               "import sys; sys.stderr.write('hello-ffmpeg-line\\n'); sys.stderr.flush()"]
        proc, t = tool_log.pump(cmd, tag="ffmpeg", stage="FFMP")
        proc.wait(timeout=10)
        t.join(timeout=5)
    finally:
        raw_log.raw = orig_raw
    assert any("hello-ffmpeg-line" in m for _, m, _ in got)
