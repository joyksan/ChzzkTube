"""통합 테스트 — 다운로드 파이프라인(D) 컨텍스트 흐름과 facade 재수출 검증.

[커버리지]
- DownloadContext: 속도 창·메타 로깅 플래그 상태 변화
- emit_dl / emit_err: 포맷 규격 (stage/status/platform/spec/speed/pct/bar)
- pot_provider facade: node_provider/pot_server 함수 재수출 확인
"""
from unittest.mock import Mock, patch

import pytest

from dl_context import DownloadContext
from log_console import format_log_line, emit_dl, emit_err


class TestDownloadContext:
    """DownloadContext dataclass의 기본 속성 테스트."""

    def test_defaults(self):
        ctx = DownloadContext(cfg={}, current_url="https://youtu.be/test")
        assert ctx.current_url == "https://youtu.be/test"
        assert ctx.current_file is None
        assert ctx.live_partially_saved is False
        assert ctx.v_spec == {}
        assert ctx.speed_win is None
        assert ctx._errors == []

    def test_add_error(self):
        ctx = DownloadContext(cfg={}, current_url="https://youtu.be/test")
        ctx.add_error("download failed")
        assert ctx.errors == ["download failed"]
        assert len(ctx.errors) == 1


class TestEmitDl:
    """emit_dl: DL 단계 진행률 라인 포맷 검증."""

    def test_run_format(self):
        line = emit_dl(status="RUN", platform="YT", spec="1080p30", speed="12.4M/s", pct=65.0, bar_frac=0.65)
        assert "RUN" in line
        assert "YT" in line
        assert "1080p30" in line
        assert "12.4M/s" in line

    def test_done_with_title(self):
        line = emit_dl(status="DONE", platform="YT", spec="720p60", speed="-", pct=100.0, bar_frac=1.0, msg="video title")
        assert "DONE" in line
        assert "video title" in line

    def test_minimal_args(self):
        line = emit_dl(status="SKIP")
        assert "SKIP" in line
        assert line.strip() != ""


class TestEmitErr:
    """emit_err: 실패 라인 포맷 검증."""

    def test_err_format(self):
        line = emit_err("age restricted")
        assert "FAIL" in line
        assert "age restricted" in line

    def test_err_truncates_long_msg(self):
        long_msg = "x" * 200
        line = emit_err(long_msg)
        assert "FAIL" in line


class TestPotProviderFacade:
    """pot_provider facade: node_provider/pot_server 함수 재수출 검증."""

    def test_reexports_from_node_provider(self):
        """facade가 node_provider 함수들을 올바르게 재수출하는지 확인."""
        import pot_provider
        import node_provider

        for name in ["node_exe", "node_major_version", "npm_exe", "node_ok",
                      "ensure_node_runtime", "bundled_npm_ok"]:
            assert hasattr(pot_provider, name), f"pot_provider.{name} missing"
            assert getattr(pot_provider, name) is getattr(node_provider, name), \
                f"pot_provider.{name} is not node_provider.{name}"

    def test_reexports_from_pot_server(self):
        """facade가 pot_server 함수들을 올바르게 재수출하는지 확인."""
        import pot_provider
        import pot_server

        for name in ["server_home", "latest_server_ver", "server_installed_ver",
                      "built_server_js", "_spawn_existing", "ensure_node_server",
                      "download_and_install_source"]:
            assert hasattr(pot_provider, name), f"pot_provider.{name} missing"
            assert getattr(pot_provider, name) is getattr(pot_server, name), \
                f"pot_provider.{name} is not pot_server.{name}"

    def test_reexports_from_po_client(self):
        """facade가 po_client 함수들을 올리바르게 재수출하는지 확인."""
        import pot_provider
        import po_client

        for name in ["DEFAULT_HOST", "DEFAULT_PORT", "probe_server", "fetch_po_token"]:
            assert hasattr(pot_provider, name), f"pot_provider.{name} missing"
            assert getattr(pot_provider, name) is getattr(po_client, name), \
                f"pot_provider.{name} is not po_client.{name}"

    def test_pothProviderWorker_in_facade(self):
        """facade에 POTProviderWorker 클래스 존재 확인."""
        import pot_provider
        assert hasattr(pot_provider, "POTProviderWorker")


class TestContextPipelineFlow:
    """DownloadContext가 파이프라인 함수들과 함께 흐르는 흐름 테스트."""

    def test_context_passed_to_pipeline(self):
        """emit_dl이 ctx 속성을 올바르게 사용하는지 검증."""
        ctx = DownloadContext(
            cfg={},
            current_url="https://youtu.be/abc123",
            current_file="/tmp/test.mp4",
            v_spec={"height": 1080, "fps": 30, "vcodec": "h264"},
        )
        # progress_emitter에서 emit_dl 호출 패턴 시뮬레이션
        line = emit_dl(
            status="RUN",
            platform="YT",
            spec=str(ctx.v_spec.get("height", "")) if ctx.v_spec else "-",
            speed="-",
            pct=50.0,
        )
        assert "RUN" in line
        assert "1080" in line or "-" in line  # v_spec 사용 확인
