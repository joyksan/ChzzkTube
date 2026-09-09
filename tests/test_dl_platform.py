"""dl_platform 단위 테스트 — URL 판정/축약 순수 함수."""
import pytest

from dl_platform import _dl_platform, _short_platform, detect_content_type


class TestShortPlatform:
    @pytest.mark.parametrize(
        "plat,expected",
        [
            ("youtube", "YT"),
            ("chzzk", "CHZ"),
            ("twitch", "TW"),
            ("-", "-"),
        ],
    )
    def test_shorten(self, plat, expected):
        assert _short_platform(plat) == expected


class TestDlPlatform:
    @pytest.mark.parametrize(
        "url,expected",
        [
            ("https://www.youtube.com/watch?v=abc", "youtube"),
            ("https://chzzk.naver.com/video/123", "chzzk"),
            ("https://www.twitch.tv/videos/123", "twitch"),
        ],
    )
    def test_detect(self, url, expected):
        assert _dl_platform(url) == expected

    def test_fallback_youtube(self):
        # 알 수 없는 도메인은 youtube로 폴백
        assert _dl_platform("https://unknown.example.com/video") == "youtube"


class TestDetectContentType:
    def test_youtube_vod(self):
        assert detect_content_type("https://youtube.com/watch?v=abc") == "video"

    def test_youtube_playlist(self):
        assert detect_content_type("https://youtube.com/playlist?list=abc") == "playlist"

    def test_chzzk_clip(self):
        assert detect_content_type("https://chzzk.naver.com/clips/abc") == "clip"

    def test_chzzk_vod(self):
        assert detect_content_type("https://chzzk.naver.com/video/123") == "vod"

    def test_chzzk_live(self):
        assert detect_content_type("https://chzzk.naver.com/live/abc") == "live"

    def test_unknown(self):
        assert detect_content_type("https://example.com/video") == "video"