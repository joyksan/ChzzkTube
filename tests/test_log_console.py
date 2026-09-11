"""log_console 단위 테스트 — format_log_line 포맷 규격."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from log_console import _flow_lines, format_log_line, is_tui_line


def _parts(line):
    """│ 구분자로 분리, 앞뒤 공백 제거."""
    return [p.strip() for p in line.split("│")]


class TestFormatLogLine:
    def test_basic_structure(self):
        line = format_log_line(stage="DL", status="OK", platform="YT", msg="done")
        parts = _parts(line)
        # parts[0]="[ts] DL", [1]=STATUS, [2]=PLATFORM, [3]=SPEC, [4]=SPEED, [5]=MSG
        assert parts[1] == "OK"
        assert parts[2] == "YT"
        assert parts[-1] == "done"

    def test_timestamp_present(self):
        line = format_log_line(stage="SYS", status="READY")
        assert line.startswith("[")
        assert "]" in line

    def test_spec_omitted_when_empty(self):
        line = format_log_line(stage="DEPS", status="OK", platform="YTDL")
        parts = _parts(line)
        assert parts[3] == "-"

    def test_spec_included_when_present(self):
        line = format_log_line(stage="DL", status="RUN", platform="YT", spec="1080p30")
        parts = _parts(line)
        assert parts[3] == "1080p30"

    def test_progress_bar_in_msg(self):
        line = format_log_line(
            stage="DL", status="RUN", platform="YT",
            spec="1080p30", pct=50.0, bar_frac=0.5, msg="downloading"
        )
        parts = _parts(line)
        assert "50.0%" in parts[-1]
        assert "downloading" in parts[-1]

    def test_short_platform(self):
        line = format_log_line(stage="DEPS", status="OK", platform="youtube")
        parts = _parts(line)
        assert parts[2] == "YT"

    def test_no_trailing_separator_when_no_msg(self):
        line = format_log_line(stage="DEPS", status="OK", platform="YTDL")
        assert not line.endswith("│")


class TestFlowLinesNoWrapFlag:
    """_flow_lines 분기는 발행자 플래그만 따른다 — 콘텐츠 판정 제로."""

    def test_no_wrap_true_is_passthrough(self):
        line = (
            "[12:00:01] DL     │ RUN      │ YT    │ 1080p30 │ - │ "
            "msg " + "x" * 400
        )
        assert _flow_lines(line, True) == [line]

    def test_no_wrap_true_keeps_tree_branch(self):
        branch = " ├─ 라벨     : " + "y" * 400
        assert _flow_lines(branch, True) == [branch]

    def test_no_wrap_false_keeps_tree_branch(self):
        branch = " ├─ 라벨     : 값"
        assert _flow_lines(branch, False) == [branch]

    def test_no_wrap_false_wraps_long_plain(self):
        plain = "z" * 300
        assert len(_flow_lines(plain, False)) > 1

    def test_legacy_is_tui_line_still_structural(self):
        column = "[12:00:01] DL │ RUN │ YT │ 1080p30 │ - │ msg"
        assert is_tui_line(column) is True
        assert is_tui_line("[download] Destination: /tmp/foo.mp4") is False

    def test_default_is_wrap(self):
        plain = "z" * 300
        assert len(_flow_lines(plain)) > 1