"""결함 1: 순정 위임 계약 — 수동 로테이션 잔재 금지 (v3.9.0 갱신).

[v3.9.0 방침 전환] 구 todo Task 3(수동 client_chain 구성)는 폐기.
HANDOVER §5-6.x: 앱 수동 클라 로테이션(_RETRY_CLIENTS, client_chain) 완전 제거 →
yt-dlp 순정 단일 auto 호출 위임. 빈 스텁 테스트를 실제 계약 단언으로 교체.
"""
import pytest

import chzzktube.pipeline.target_downloader as td
from chzzktube.core.speed_window import SpeedWindow
from chzzktube.pipeline.dl_context import DownloadContext


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


class TestNoManualClientChain:
    """수동 클라이언트 체인 잔재 금지 — 순정 위임 계약."""

    def test_no_retry_clients_constant(self):
        """AnalyzeWorker._RETRY_CLIENTS는 빈 목록 (순정 위임)."""
        from chzzktube.workers.analyze_worker import AnalyzeWorker

        assert AnalyzeWorker._RETRY_CLIENTS == []

    def test_no_client_chain_symbol(self):
        """target_downloader 패키지에 client_chain/ios 잔재 없음."""
        import pathlib

        # 새 패키지 구조의 모든 .py 파일 검사
        pkg_dir = pathlib.Path("chzzktube/pipeline/target_downloader")
        for py_file in pkg_dir.glob("*.py"):
            src = py_file.read_text(encoding="utf-8")
            assert "client_chain" not in src, f"client_chain found in {py_file}"
            assert "_RETRY_CLIENTS" not in src, f"_RETRY_CLIENTS found in {py_file}"

    def test_pure_delegation_runtime_options(self):
        """yt-dlp 옵션 빌더가 수동 클라이언트 체인 없이 순정 단일 위임 설정을 생성하는지 검증."""
        from chzzktube.pipeline.target_downloader.options import _make_ytdl_opts

        ctx = DownloadContext(
            cfg={"download_path": "/tmp", "yt_player_client": "auto"},
            current_url="https://youtu.be/test1234",
            speed_win=SpeedWindow(),
        )
        opts = _make_ytdl_opts(ctx, "bv*+ba", ctx.current_url)

        # 수동 체인(여러 클라이언트 나열)이 아닌 단일 순정 auto 위임 확인
        ext_args = opts.get("extractor_args", {})
        yt_args = ext_args.get("youtube", {})
        client = yt_args.get("player_client", ["auto"])
        assert client == ["auto"]


class TestDownloadVodTerminalFailFast:
    """터미널 에러(비공개/삭제)는 봇 차단으로 오판하지 않고 즉시 중단."""

    def test_private_video_not_retried(self, monkeypatch):
        """비공개 영상은 재시도 없이 즉시 에러."""
        from chzzktube.pipeline.classifier import (
            ClassifiedTarget,
            ContentKind,
            StreamCapability,
        )

        ctx = DownloadContext(
            cfg={"yt_player_client": "auto"},
            current_url="https://youtu.be/private",
            speed_win=SpeedWindow(),
        )
        # _download_vod expects ctx.current_item to be set
        ctx.current_item = ClassifiedTarget(
            url="https://youtu.be/private",
            title="private",
            kind=ContentKind.VOD,
            capability=StreamCapability(has_video=True, has_audio=True),
            platform_tag="youtube",
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

        monkeypatch.setattr("chzzktube.pipeline.target_downloader.youtube_vod.yt_dlp.YoutubeDL", FakeYDL)
        # POT 서버 체크 건너뛰기 (터미널 에러는 POT 재시도 전에 즉시 전파되어야 함)
        monkeypatch.setattr("chzzktube.pipeline.target_downloader.youtube_vod._ensure_pot_server_ready", lambda ctx, timeout=60.0: False)

        with pytest.raises(td.YtDownloadError, match="Private video"):
            td._download_vod(ctx, "https://youtu.be/private")


class TestHttpDownloadWatchdogHeartbeat:
    """결함 5: _http_download 루프 내 워치독 하트비트 호출."""

    def test_http_download_heartbeat_interval(self, monkeypatch, tmp_path):
        """5초마다 워치독 하트비트 호출 — 테스트용 0.5초 간격으로 단축."""
        import time

        import chzzktube.pipeline.target_downloader as td
        import chzzktube.pipeline.target_downloader.utils as td_utils

        # [테스트용] 모듈 내 상수 단축 (5초 → 0.5초)
        td_utils._WATCHDOG_HEARTBEAT_INTERVAL = 0.5

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

        monkeypatch.setattr("chzzktube.pipeline.target_downloader.chzzk.urllib.request.urlopen", lambda req, timeout=None: SlowResponse())

        out_path = tmp_path / "test.mp4"
        td._http_download(ctx, "https://example.com/video.mp4", str(out_path))

        # 0.5초 간격으로 하트비트 호출되었는지 (최소 2회: 1.2초 / 0.5초)
        assert len(heartbeats) >= 2, f"워치독 하트비트가 호출되지 않음: {len(heartbeats)}회"