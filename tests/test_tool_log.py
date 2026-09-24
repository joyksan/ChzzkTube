"""chzzktube.core.tool_log 래퍼 + 외부툴 설정 fit 회귀 테스트."""
import chzzktube
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def test_double_timestamp_absent():
    """이중 ts 금지 — TUI 컬럼 + F12 스탬프가 합쳐져도 ts는 1개."""
    import re
    from chzzktube.core.log_emitter import format_log_line
    line = format_log_line(stage="DL", status="RUN", scope="YT",
                           pct=65.0, bar_frac=0.65, speed="12.4M/s", msg="title")
    ts = re.findall(r"\[\d{2}:\d{2}:\d{2}\]", line)
    assert len(ts) == 1  # 컬럼 라인 내 타임스탬프 1회


def test_f12_raw_msg_no_double_stamp():
    """F12 원문 보존 — 컬럼 문자열이 아닌 msg 원문이 적재된다."""
    from types import SimpleNamespace
    from chzzktube.core.log_event import LogEvent
    import chzzktube.ui.main_window as main_module

    class _FakeMain:
        def __init__(self):
            self.rendered = []
            self._last_status_line = ""

        def _mirror_full_log(self, line, is_status=False):
            self.rendered.append((line, is_status))

    m = _FakeMain()
    ev = LogEvent(stage="DL", status="RUN", scope="YT",
                  pct=65.0, bar_frac=0.65, speed="12.4M/s", msg="raw line")
    main_module.MainWindow._mirror_event_full(m, ev, False)
    # 컬럼화 없이 원문만 — 스탬프는 _mirror_full_log 1곳에서만 찍힌다.
    assert m.rendered == [("raw line", False)]


def test_apply_post_opts_subtitles_thumbnail_chapters():
    from chzzktube.core.client_opts import _apply_post_opts
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
    from chzzktube.core.client_opts import _apply_post_opts
    opts = _apply_post_opts({}, {"embed_subtitles": True, "subtitle_langs": "all"})
    assert opts.get("allsubtitles") is True
    assert "subtitleslangs" not in opts


def test_apply_post_opts_off_is_clean():
    from chzzktube.core.client_opts import _apply_post_opts
    opts = _apply_post_opts({}, {"embed_subtitles": False, "embed_thumbnail": False,
                                 "embed_chapters": False})
    assert opts.get("postprocessors") == []
    assert "writesubtitles" not in opts


def test_concurrent_fragments_fit():
    from chzzktube.core.client_opts import _concurrent_fragments
    assert _concurrent_fragments({"fast_download": True, "concurrent_fragments": 8}) == 8
    assert _concurrent_fragments({"fast_download": False, "concurrent_fragments": 8}) == 1
    assert _concurrent_fragments({"fast_download": True}) == 4
    assert _concurrent_fragments({"fast_download": True, "concurrent_fragments": 99}) == 16


def test_streamlink_fully_removed():
    """[v3.10.0] Streamlink 완전 제거 — 실행 인자/설정 키/재수출/의존성 부재."""
    import chzzktube.pipeline.target_downloader as td
    import chzzktube.core.config as config

    # 1. target_downloader 재수출 및 실체 제거
    assert not hasattr(td, "_download_streamlink")
    # 2. 설정 키 제거
    assert "streamlink_quality" not in config.default_config()
    # 3. updater의 streamlink 업그레이드 경로 제거
    import chzzktube.infra.updater as updater
    assert not hasattr(updater, "_frozen_upgrade_streamlink")
    assert not hasattr(updater, "_extract_streamlink_whl")
    assert all(label != "streamlink" for label, _, _ in updater.PACKAGES)
    # 4. 앱 코드에 streamlink '실행/설정/의존' 형태 잔존 없음
    #    (제거 이력 서술 주석은 허용 — 테스트 관례: 호출 형태만 금지)
    import os
    import re
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    violations = (
        r'"streamlink',           # 실행 인자/설정값 리터럴
        r"'streamlink",
        r"import streamlink",     # import 문
        r"from streamlink",
        r"streamlink_quality",    # 설정 키
        r"cmd\s*=\s*\[\s*[\"']streamlink",
    )
    for rel in ("chzzktube/pipeline/target_downloader/youtube_live.py",
                "chzzktube/pipeline/target_downloader/dispatch.py",
                "chzzktube/pipeline/target_downloader/__init__.py",
                "chzzktube/core/config.py",
                "chzzktube/ui/dialogs.py",
                "chzzktube/infra/updater.py"):
        with open(os.path.join(root, rel), encoding="utf-8") as f:
            src = f.read()
        for pattern in violations:
            assert not re.search(pattern, src), f"streamlink 잔존({pattern}): {rel}"
    # 5. pyproject 의존성에서도 제거
    with open(os.path.join(root, "pyproject.toml"), encoding="utf-8") as f:
        assert "streamlink" not in f.read().lower()


def test_tool_log_protocols_importable():
    import chzzktube.core.tool_log as tool_log
    assert hasattr(chzzktube.core.tool_log, "ToolLogger")
    assert hasattr(chzzktube.core.tool_log, "LineRunner")
    assert hasattr(chzzktube.core.tool_log, "TokenProvider")
    assert callable(tool_log.make_ytdlp_logger)
    assert callable(tool_log.pump)
    assert callable(tool_log.run_cli)


def test_tool_log_pump_absorbs_stderr():
    """pump: 자식 stderr를 LogEvent 원문으로 흡수 → raw 버스."""
    import chzzktube.core.raw_log as raw_log
    import chzzktube.core.tool_log as tool_log
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
