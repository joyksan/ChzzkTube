"""utils.clean_ansi 회귀 테스트 — ANSI 제어문자 제거/보존 계약.

[계약]
- ANSI 이스케이프 시퀀스는 제거한다.
- 캐리지 리턴(\r)은 제거하지 않는다 — yt-dlp progress tick 조립은
  YtLoggerBridge._flush_carriage가 담당한다 (분리된 책임).
"""
from utils import clean_ansi


def test_clean_ansi_strips_control_sequences():
    assert "\x1b" not in clean_ansi("\x1b[2K\r[download] 1.0%\r\x1b[1A")
    assert clean_ansi("\x1b[31mred\x1b[0m") == "red"


def test_clean_ansi_preserves_carriage_and_plain_text():
    assert clean_ansi("[download] a\r[download] b") == "[download] a\r[download] b"
    assert clean_ansi("plain text") == "plain text"