"""test_url_gate.py — v3.8.0 URL Validation Gate 회귀 테스트.

[배경]
- `afqweqasd` 같은 임의 문자열이 무검증으로 DownloadWorker까지 유입되어
  [generic] Extracting URL 후 DL FAIL 다중 로그를 남기는 촌규를 원천 차단.
- 게이트는 컨트롤러(controller._is_valid_url / parse_targets)가 SSOT이고,
  뷰(toggle_download/_start_download)는 2차 방어선으로 재검증한다.
"""
import pytest

from chzzktube.control.controller import MediaController, _is_valid_url


class TestIsValidUrl:
    """게이트 순수 함수 규격."""

    @pytest.mark.parametrize("bad", [
        "afqweqasd",
        "afqweqasd.com",
        "www.afqweqasd.com",
        "https://afqweqasd.com/watch?v=x",  # 미지원 도메인
        "ftp://youtu.be/abc",
        "https://",
        "",
        None,
        12345,
    ])
    def test_rejects_non_url_or_unsupported(self, bad):
        assert _is_valid_url(bad) is False

    @pytest.mark.parametrize("good", [
        "https://youtu.be/abcDEFghijk",
        "https://www.youtube.com/watch?v=abc",
        "http://youtube.com/shorts/abc",
        "https://chzzk.naver.com/video/123456",
        "https://chzzk.naver.com/clips/abc",
        "https://music.youtube.com/watch?v=x",
        "https://www.twitch.tv/someone",
    ])
    def test_accepts_supported_urls(self, good):
        assert _is_valid_url(good) is True


class TestParseTargetsGate:
    """parse_targets 게이트 통합 — 배치 전체 차단 계약."""

    def test_arbitrary_string_raises_and_blocks_worker(self):
        # [검증 시나리오 1] 임의 문자열 → ValueError → DownloadWorker 미구동
        with pytest.raises(ValueError) as ei:
            MediaController.parse_targets("afqweqasd")
        assert "Invalid URL format" in str(ei.value)

    def test_mixed_batch_blocked_on_single_bad_line(self):
        with pytest.raises(ValueError):
            MediaController.parse_targets(
                "https://youtu.be/abcDEFghijk\nafqweqasd"
            )

    def test_valid_urls_pass_through(self):
        targets = MediaController.parse_targets(
            "https://youtu.be/abcDEFghijk\nhttps://chzzk.naver.com/video/123",
        )
        assert targets == [
            "https://youtu.be/abcDEFghijk",
            "https://chzzk.naver.com/video/123",
        ]