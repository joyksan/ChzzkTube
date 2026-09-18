"""결함 1: 유튜브 tv 클라이언트 폴백 시 화질 제한 및 포맷 무음 위험 회귀 테스트."""
from unittest.mock import Mock, patch
import pytest

import chzzktube.pipeline.target_downloader as td
from chzzktube.pipeline.dl_context import DownloadContext
from chzzktube.core.speed_window import SpeedWindow


class TestFormatSelector:
    """_format_selector 계약 검증."""

    def test_auto_returns_bv_plus_ba_no_b_fallback(self):
        """자동 모드에서 'bv*+ba' 반환 — 단일 포맷(b) 폴백 금지."""
        ctx = DownloadContext(cfg={}, v_sel="auto", a_sel="auto")
        fmt = td._format_selector(ctx)
        # tv 클라이언트 대비: 분리 포맷이 없으면 예외로 폴백 유도
        assert fmt == "bv*+ba"
        # 'b' 단일 포맷 폴백이 없어야 함
        assert "/b" not in fmt

    def test_max_res_returns_height_constrained(self):
        """최대 해상도 제한 시 height 제약 포함."""
        ctx = DownloadContext(cfg={"max_video_res": "720"}, v_sel="auto", a_sel="auto")
        fmt = td._format_selector(ctx)
        assert "height<=720" in fmt
        assert "+ba" in fmt

    def test_audio_only_returns_bestaudio(self):
        """오디오 전용 모드."""
        ctx = DownloadContext(cfg={"audio_only": True}, v_sel="auto", a_sel="auto")
        fmt = td._format_selector(ctx)
        assert fmt == "bestaudio/best"

    def test_manual_format_selection(self):
        """수동 포맷 지정."""
        ctx = DownloadContext(cfg={}, v_sel="123", a_sel="456")
        fmt = td._format_selector(ctx)
        assert fmt == "123+456"

    def test_manual_video_auto_audio(self):
        """비디오만 수동, 오디오는 자동."""
        ctx = DownloadContext(cfg={}, v_sel="123", a_sel="auto")
        fmt = td._format_selector(ctx)
        assert fmt == "123+bestaudio"


class TestDownloadVodClientChain:
    """_download_vod 클라이언트 폴백 체인 검증."""

    def test_client_chain_excludes_ios(self):
        """ios는 SUPPORTS_COOKIES=False로 쿠키 사용 시 스킵 → 체인에서 제외."""
        # 내부 상수 직접 검증 (구현 후)
        ctx = DownloadContext(cfg={"yt_player_client": "auto"}, current_url="https://youtu.be/test")
        # 실제 구현에서 client_chain 구성 로직 확인 필요
        # 이 테스트는 구현 후 통과해야 함

    def test_tv_client_warning_emitted(self):
        """tv 클라이언트 진입 시 화질 저하 경고 로그."""
        # 구현 후 검증


class TestDownloadVodTerminalFailFast:
    """터미널 에러(비공개/삭제)는 봇 차단으로 오판하지 않고 즉시 중단."""

    def test_private_video_not_retried(self, monkeypatch):
        """비공개 영상은 재시도 없이 즉시 에러."""
        ctx = DownloadContext(
            cfg={"yt_player_client": "auto"},
            current_url="https://youtu.be/private",
            speed_win=SpeedWindow(),
        )

        class FakeYDL:
            def __init__(self, opts):
                self.opts = opts
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False
            def extract_info(self, url, download=True):
                raise td.YtDownloadError("ERROR: [youtube] Private video")

        monkeypatch.setattr(td.yt_dlp, "YoutubeDL", FakeYDL)

        with pytest.raises(td.YtDownloadError, match="Private video"):
            td._download_vod(ctx, "https://youtu.be/private")


class TestHttpDownloadWatchdogHeartbeat:
    """결함 5: _http_download 루프 내 워치독 하트비트 호출."""

    def test_http_download_heartbeat_interval(self, monkeypatch, tmp_path):
        """5초마다 워치독 하트비트 호출 — 테스트용 0.5초 간격으로 단축."""
        import chzzktube.pipeline.target_downloader as td_module
        import time

        # [테스트용] 모듈 내 상수 단축 (5초 → 0.5초)
        td_module._WATCHDOG_HEARTBEAT_INTERVAL = 0.5

        # 느린 응답 시뮬레이션 - 0.1초 지연으로 총 1초 이상 소요
        class SlowResponse:
            def __init__(self):
                self.chunks = [b"a" * 1024] * 12
                self.idx = 0
            def read(self, n):
                if self.idx >= len(self.chunks):
                    return b""
                chunk = self.chunks[self.idx]
                self.idx += 1
                time.sleep(0.1)  # 0.1초 지연
                return chunk
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False

        ctx = DownloadContext(
            cfg={"download_path": str(tmp_path)},
            current_url="https://chzzk.naver.com/video/123",
            speed_win=SpeedWindow(),
        )

        # 워치독 모킹
        heartbeats = []
        class FakeWatchdog:
            def heartbeat(self):
                heartbeats.append(time.monotonic())
        ctx._download_watchdog = FakeWatchdog()

        monkeypatch.setattr(td.urllib.request, "urlopen", lambda req: SlowResponse())

        out_path = tmp_path / "test.mp4"
        td._http_download(ctx, "https://example.com/video.mp4", str(out_path))

        # 0.5초 간격으로 하트비트 호출되었는지 (최소 2회: 1.2초 / 0.5초)
        assert len(heartbeats) >= 2, f"워치독 하트비트가 호출되지 않음: {len(heartbeats)}회"