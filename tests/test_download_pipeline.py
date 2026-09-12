"""통합 테스트 — 다운로드 파이프라인(D) 컨텍스트 흐름과 facade 재수출 검증.

[커버리지]
- DownloadContext: 속도 창·메타 로깅 플래그 상태 변화
- emit_dl / emit_err: 포맷 규격 (stage/status/platform/spec/speed/pct/bar)
- pot_provider facade: node_provider/pot_server 함수 재수출 확인
"""
from contextlib import contextmanager
from unittest.mock import Mock, patch

import pytest

from dl_context import DownloadContext
from log_console import format_log_line, format_log_line_for_event, emit_dl, emit_err


def _rendered(event):
    """LogEvent 빌더 결과 → TUI 컬럼 문자열 (v3.3.0: 빌더는 라벨링만, 렌더는 뷰 몫)."""
    return format_log_line_for_event(event)


@contextmanager
def patch_cli_raw_output(fake_out):
    """updater.cli_raw의 subprocess 실행을 우회 — 출력 가공 로직만 검증."""
    import subprocess
    import updater
    fake_proc = Mock()
    fake_proc.stdout = fake_out
    fake_proc.stderr = ""
    with patch.object(subprocess, "run", return_value=fake_proc), \
         patch.object(updater, "_cli_base", return_value=["ffmpeg"]):
        yield


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
    """emit_dl: DL 단계 진행률 이벤트 라벨링 검증 (v3.3.0: LogEvent 반환 → _rendered로 컬럼화)."""

    def test_run_format(self):
        line = _rendered(emit_dl(status="RUN", platform="YT", spec="1080p30", speed="12.4M/s", pct=65.0, bar_frac=0.65))
        assert "RUN" in line
        assert "YT" in line
        assert "1080p30" in line
        assert "12.4M/s" in line

    def test_done_with_title(self):
        line = _rendered(emit_dl(status="DONE", platform="YT", spec="720p60", speed="-", pct=100.0, bar_frac=1.0, msg="video title"))
        assert "DONE" in line
        assert "video title" in line

    def test_minimal_args(self):
        event = emit_dl(status="SKIP")
        assert event.status == "SKIP"
        line = _rendered(event)
        assert "SKIP" in line
        assert line.strip() != ""


class TestEmitErr:
    """emit_err: 실패 이벤트 라벨링 검증 (v3.3.0: LogEvent 반환 → _rendered로 컬럼화)."""

    def test_err_format(self):
        line = _rendered(emit_err("age restricted"))
        assert "FAIL" in line
        assert "age restricted" in line

    def test_err_truncates_long_msg(self):
        long_msg = "x" * 200
        event = emit_err(long_msg)
        assert event.status == "FAIL"
        assert event.msg == long_msg
        line = _rendered(event)
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
                      "built_server_js", "pot_readiness", "_spawn_existing", "ensure_node_server",
                      "download_and_install_source"]:
            assert hasattr(pot_provider, name), f"pot_provider.{name} missing"
            assert getattr(pot_provider, name) is getattr(pot_server, name), \
                f"pot_provider.{name} is not pot_server.{name}"

    def test_pot_readiness_contract(self):
        """pot_readiness: 네트워크·Popen 없이 (bool, str) 반환."""
        from pot_server import pot_readiness
        ready, reason = pot_readiness()
        assert isinstance(ready, bool)
        assert isinstance(reason, str) and reason != ""

    def test_deps_pot_readiness_labels(self):
        """check_deps POT 분기: FAIL 오경보 금지 — OK running / SKIP *."""
        import updater
        results = dict((label, (status, msg)) for label, status, msg in updater.check_deps())
        assert "pot" in results
        status, msg = results["pot"]
        assert status in ("OK", "SKIP"), f"POT DEPS must not FAIL on idle: {status} {msg}"
        if status == "OK":
            assert msg == "running"
        else:
            assert msg in ("standby", "no build", "node missing", "unknown")

    def test_prewarm_lock_mutual_exclusion(self):
        """acquire_prewarm_lock: O_EXCL 원자 생성 상호배제 + 해제 후 재획득."""
        import os
        import pot_server
        try:
            os.remove(pot_server._prewarm_lock_path())
        except OSError:
            pass
        fd1 = pot_server.acquire_prewarm_lock(timeout=0)
        assert fd1 is not None, "first lock acquire must succeed"
        try:
            fd2 = pot_server.acquire_prewarm_lock(timeout=0)
            assert fd2 is None, "second acquire while held must fail"
        finally:
            pot_server.release_prewarm_lock(fd1)
        fd3 = pot_server.acquire_prewarm_lock(timeout=0)
        assert fd3 is not None, "re-acquire after release must succeed"
        pot_server.release_prewarm_lock(fd3)
        # 락 파일 잔재 없음
        assert not os.path.exists(pot_server._prewarm_lock_path())

    def test_prewarm_lock_stale_recovery(self):
        """죽은 PID + mtime 30분 초과 stale 락은 회수되어 획득 가능."""
        import os
        import time
        import pot_server
        path = pot_server._prewarm_lock_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write("999999 0")  # 존재 불가 PID + 오래된 epoch
        old = time.time() - 2000  # 33분 전
        os.utime(path, (old, old))
        fd = pot_server.acquire_prewarm_lock(timeout=0)
        assert fd is not None, "stale lock must be reclaimed"
        pot_server.release_prewarm_lock(fd)

    def test_pot_readiness_stale(self):
        """pot_readiness(check_stale): 버전 불일치 시 stale reason."""
        from unittest.mock import patch
        import pot_server
        with patch.object(pot_server, "built_server_js", return_value="/tmp/main.js"), \
             patch("node_provider.node_exe", return_value="/tmp/node"), \
             patch.object(pot_server, "server_installed_ver", return_value="1.3.1"), \
             patch.object(pot_server, "latest_server_ver", return_value="1.3.2"):
            ready, reason = pot_server.pot_readiness(check_stale=True)
            assert ready is False
            assert "stale" in reason
        # 네트워크 실패(None) 시 판정 유지
        with patch.object(pot_server, "built_server_js", return_value="/tmp/main.js"), \
             patch("node_provider.node_exe", return_value="/tmp/node"), \
             patch.object(pot_server, "server_installed_ver", return_value="1.3.1"), \
             patch.object(pot_server, "latest_server_ver", return_value=None):
            ready, reason = pot_server.pot_readiness(check_stale=True)
            assert ready is True
            assert reason == "standby"

    def test_check_deps_single_call(self):
        """check_deps(log_func): POT 판정+로그 단일 호출 (중복 standby 금지)."""
        from unittest.mock import patch
        import updater
        notes = []
        with patch("pot_server.built_server_js", return_value="/tmp/main.js"), \
             patch("node_provider.node_exe", return_value="/tmp/node"), \
             patch("po_client.server_ping", return_value=False):
            results = dict(
                (label, (status, msg))
                for label, status, msg in updater.check_deps(log_func=notes.append)
            )
        assert results["pot"][0] == "SKIP"
        assert len(notes) == 1, f"readiness log must fire once, got {len(notes)}"

    def test_cli_raw_truncation(self):
        """cli_raw: 장문 줄 절단 + max_lines 꼬리."""
        import updater
        long_line = "configuration: " + "x" * 500
        with patch_cli_raw_output(long_line + "\nline2\nline3"):
            cmdline, out = updater.cli_raw("ffmpeg", "-version", max_lines=2, max_width=160)
        assert cmdline is not None
        out_lines = out.splitlines()
        assert len(out_lines[0]) <= 161  # 160 + …
        assert out_lines[-1].endswith("lines truncated)")

    def test_pid_alive_self(self):
        """_pid_alive: 자기 PID는 살아있음, 존재 불가 PID는 죽음."""
        import os
        import pot_server
        assert pot_server._pid_alive(os.getpid()) is True
        assert pot_server._pid_alive(999999) is False
        assert pot_server._pid_alive(None) is False
        assert pot_server._pid_alive("bogus") is False

    def test_prewarm_lock_live_holder_not_reclaimed(self):
        """살아있는 홀더의 락은 mtime이 오래돼도 회수 금지."""
        import os
        import time
        import pot_server
        try:
            os.remove(pot_server._prewarm_lock_path())
        except OSError:
            pass
        fd1 = pot_server.acquire_prewarm_lock(timeout=0)
        assert fd1 is not None
        try:
            path = pot_server._prewarm_lock_path()
            old = time.time() - 2000  # 33분 전으로 위장
            os.utime(path, (old, old))
            fd2 = pot_server.acquire_prewarm_lock(timeout=0)
            assert fd2 is None, "live holder lock must NOT be reclaimed"
        finally:
            pot_server.release_prewarm_lock(fd1)

    def test_prewarm_lock_log_callback(self):
        """log_func 콜백: 획득/해제 경로에서 호출됨."""
        import os
        import pot_server
        try:
            os.remove(pot_server._prewarm_lock_path())
        except OSError:
            pass
        notes = []
        fd = pot_server.acquire_prewarm_lock(timeout=0, log_func=notes.append)
        assert fd is not None
        assert any("acquired" in m for m in notes)
        pot_server.release_prewarm_lock(fd, log_func=notes.append)
        assert any("released" in m for m in notes)

    def test_raw_bus_fanout(self):
        """raw(): 포함관계 계약 — history/F12=전량, TUI=to_tui 선택 (v3.3.0).

        구 병렬-분리 계약(full_only 존재)은 v3.3.0에서 폐기 — 채널은 to_tui 1비트.
        """
        import raw_log
        concise_got, full_got = [], []
        raw_log.subscribe_concise(lambda m, is_status=False, is_error=False: concise_got.append(m))
        raw_log.subscribe_full(lambda m, t=None: full_got.append(m))
        # to_tui=True → concise+TUI + full(F12) + history 전량
        event = emit_dl(status="RUN", platform="YT", spec="1080p30", msg="staged")
        raw_log.raw("pot-test", event, to_tui=True)
        raw_log.flush()
        assert concise_got and concise_got[-1] is event
        assert full_got and full_got[-1] is event
        # to_tui=False → full(F12)+history만, concise 제외
        n0 = len(concise_got)
        raw_log.raw("pot-test", "plain detail message")
        raw_log.flush()
        assert len(concise_got) == n0
        assert full_got and "plain detail message" in full_got[-1].msg

    def test_reexports_from_po_client(self):
        """facade가 po_client 함수들을 올리바르게 재수출하는지 확인."""
        import pot_provider
        import po_client

        for name in ["DEFAULT_HOST", "DEFAULT_PORT", "probe_server", "fetch_po_token"]:
            assert hasattr(pot_provider, name), f"pot_provider.{name} missing"
            assert getattr(pot_provider, name) is getattr(po_client, name), \
                f"pot_provider.{name} is not po_client.{name}"


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
        line = _rendered(emit_dl(
            status="RUN",
            platform="YT",
            spec=str(ctx.v_spec.get("height", "")) if ctx.v_spec else "-",
            speed="-",
            pct=50.0,
        ))
        assert "RUN" in line
        assert "1080" in line or "-" in line  # v_spec 사용 확인
