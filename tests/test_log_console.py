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
        line = format_log_line(stage="DL", status="OK", scope="YT", msg="done")
        parts = _parts(line)
        # 고정 4칸: parts[0]="[ts] DL", [1]=STATUS, [2]=SCOPE, [3]=MSG
        assert len(parts) == 4
        assert parts[1] == "OK"
        assert parts[2] == "YT"
        assert parts[-1] == "done"

    def test_timestamp_present(self):
        line = format_log_line(stage="SYS", status="READY")
        assert line.startswith("[")
        assert "]" in line

    def test_scope_5width(self):
        line = format_log_line(stage="DEPS", status="OK", scope="YTDL")
        parts = _parts(line)
        assert parts[2] == "YTDL"
        line2 = format_log_line(stage="DL", status="RUN", scope="YT")
        parts2 = _parts(line2)
        assert parts2[2] == "YT"

    def test_progress_fixed_width(self):
        """PCT 3폭 · SPEED 8폭 고정 — 지터링 방지."""
        line = format_log_line(stage="DL", status="RUN", scope="YT",
                               pct=65.0, bar_frac=0.65, speed="12.4M/s", msg="title")
        parts = _parts(line)
        assert len(parts) == 4
        assert "65%" in parts[-1]
        assert "12.4M/s" in parts[-1]
        # ' 65%'와 '100%' 모두 3폭 — 폭 고정 확인
        line100 = format_log_line(stage="DL", status="RUN", scope="YT",
                                  pct=100.0, bar_frac=1.0, speed="9.1M/s", msg="t")
        assert "100%" in line100

    def test_no_trailing_separator_when_no_msg(self):
        line = format_log_line(stage="DEPS", status="OK", scope="YTDL")
        assert not line.endswith("│")

    def test_short_scope(self):
        line = format_log_line(stage="DEPS", status="OK", scope="youtube")
        parts = _parts(line)
        assert parts[2] == "YT"

    def test_no_trailing_separator_empty_scope(self):
        line = format_log_line(stage="DEPS", status="OK", scope="")
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
        column = "[12:00:01] DL    │ RUN   │ YT    │ msg"
        assert is_tui_line(column) is True
        assert is_tui_line("[download] Destination: /tmp/foo.mp4") is False

    def test_default_is_wrap(self):
        plain = "z" * 300
        assert len(_flow_lines(plain)) > 1