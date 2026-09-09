"""log_console 단위 테스트 — format_log_line 포맷 규격."""
import pytest

from log_console import format_log_line


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