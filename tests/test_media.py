"""media 단위 테스트 — 순수 헬퍼 함수."""
import pytest

from media import (
    audio_spec,
    format_bytes,
    get_audio_codec_rank,
    get_video_codec_rank,
    short_codec,
)


class TestFormatBytes:
    @pytest.mark.parametrize(
        "size,expected",
        [
            (0, "0.00 B"),
            (512, "512.00 B"),
            (1024, "1.00 KB"),
            (1536, "1.50 KB"),
            (1048576, "1.00 MB"),
            (1073741824, "1.00 GB"),
            (104857600, "100.00 MB"),
        ],
    )
    def test_format(self, size, expected):
        assert format_bytes(size) == expected


class TestShortCodec:
    @pytest.mark.parametrize(
        "codec,expected",
        [
            ("avc1", "H264"),
            ("avc1.640028", "H264"),
            ("hev1.1.6.L93.B0", "HEV1.1.6.L93.B0"),
            ("opus", "OPUS"),
            ("mp4a", "AAC"),
            ("", "?"),
        ],
    )
    def test_shorten(self, codec, expected):
        assert short_codec(codec) == expected


class TestVideoCodecRank:
    def test_av1_highest(self):
        # av1(3) > avc1(1)
        assert get_video_codec_rank("av1") > get_video_codec_rank("avc1")

    def test_unknown_lowest(self):
        assert get_video_codec_rank("xyz") == get_video_codec_rank("")


class TestAudioSpec:
    def test_aac(self):
        assert audio_spec("aac") == "AAC"

    def test_opus(self):
        assert audio_spec("opus") == "OPUS"

    def test_empty(self):
        assert audio_spec("") == "?"