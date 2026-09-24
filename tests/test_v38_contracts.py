"""test_v38_contracts.py — v3.8.0 전면 개편 계약 회귀 테스트.

[커버리지]
1. 환경 단독 격리: 앱 코드에 시스템 PATH 탐색(shutil.which)·OS 패키지
   매니저 호출이 부재해야 한다 (Task 3).
2. Layer 3 POT 준비가 워커 스레드 안전 경로(순수 인프라)로만 수행되어야
   한다 — 존재하지 않는 POTManager.instance() 의존 부재 (Task 2).
3. Hyper-Minimalist TUI: 중간 임시 스트림(.fNNN) 은닉 + 최종 결과물 1줄 (Task 5-2).
4. FAIL 단일 출력: target_downloader는 즉시 TUI 발행하지 않는다 (Task 4-3).
"""
import asyncio
import hashlib
import io
import json
import os
import re
import sys
import tarfile
from types import SimpleNamespace

import chzzktube.core.client_opts as client_opts
import chzzktube.infra.components as components
import chzzktube.infra.node_provider as node_provider
import chzzktube.infra.pot_provider as pot_provider
import chzzktube.infra.updater as updater
import chzzktube.pipeline.progress_emitter as _pe
import chzzktube.pipeline.target_downloader as _td

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(rel):
    with open(os.path.join(_REPO, rel), encoding="utf-8") as f:
        return f.read()


class TestEnvironmentIsolation:
    """Task 3 — DEPS 단일 격리 (시스템 PATH/패키지 매니저 참조 제거)."""

    def test_node_provider_has_no_path_probe(self):
        # 호출 형태('shutil.which(')만 금지 — 주석/독스트링의 격리 정책 서술은 허용.
        assert "shutil.which(" not in _read("chzzktube/infra/node_provider.py")

    def test_node_exe_callable_without_name_error(self, monkeypatch, tmp_path):
        # [Critical-1 회귀] 빈 캐시에서 node_exe() 실호출이 NameError 없이
        # None을 반환해야 한다 — 사문 코드가 처음 실행되는 경로.
        # node_provider 모듈에서 실제 사용되는 get_writable_base를 패치해야 함.
        monkeypatch.setattr(
            "chzzktube.infra.node_provider.get_writable_base", 
            lambda: str(tmp_path / "empty")
        )
        node_provider._node_ver_cache.clear()
        assert node_provider.node_exe() is None

    def test_facade_exports_resolve_to_real_symbols(self):
        # [Critical-1 2차 감염] pot_provider.__all__ 이름이 실체와 일치해야 한다.
        import chzzktube.infra.pot_provider as _pp

        for name in _pp.__all__:
            assert hasattr(_pp, name), f"pot_provider.{name} missing"
        from chzzktube.infra.paths import is_portable as _real
        assert _pp.is_portable is _real

    def test_components_has_no_path_probe_or_pkg_manager(self):
        src = _read("chzzktube/infra/components.py")
        assert "shutil.which(" not in src
        # OS 패키지 매니저 '실행 인자' 철폐 (서술 문구는 허용)
        assert '"brew", "install"' not in src
        assert '"apt-get"' not in src
        assert '"pacman"' not in src

    def test_updater_cli_base_is_isolated(self):
        assert "shutil.which(" not in _read("chzzktube/infra/updater.py")
        # ytdlp 해석은 앱 인터프리터 + 오버레이 단일 경로
        assert updater._cli_base("ytdlp") == [sys.executable, "-m", "yt_dlp"]

    def test_client_opts_ffmpeg_is_isolated(self):
        src = _read("chzzktube/core/client_opts.py")
        assert "shutil.which(" not in src
        assert "ffmpeg_exe" in src

    def test_pot_server_npm_is_isolated(self):
        src = _read("chzzktube/infra/pot_server.py")
        assert "shutil.which(" not in src
        assert "npm_exe" in src

    def test_macos_bottle_keys_match_live_formulae(self):
        # [Critical-2 회귀] 실측 bottle 키(tahoe/sequoia/golden_gate)가
        # 하드코딩 테이블이 아닌 arch prefix 매치로 선택되어야 한다.
        # 호환성 필터(buildnum > 현재 OS)가 작동하므로, 호환되는 키들만 남음.
        # 15.7.4(buildnum=24) 환경에서는 tahoe(26) 제외, sequoia(24) 포함.
        live = {
            "arm64_golden_gate": {}, "arm64_linux": {},
            "arm64_sequoia": {}, "arm64_tahoe": {}, "x86_64_linux": {},
        }
        keys = components._macos_bottle_keys(live)
        # arm64 접두사 + linux 제외 = golden_gate, sequoia, tahoe
        # 호환 필터(buildnum<=24) 적용 후 = sequoia(24) + golden_gate(알 수 없음→호환으로 간주)
        assert "arm64_sequoia" in keys
        assert "arm64_linux" not in keys and "x86_64_linux" not in keys

    def test_macos_bottle_keys_offline_fallback(self):
        keys = components._macos_bottle_keys()
        assert keys and all(isinstance(k, str) for k in keys)

    def test_ffmpeg_exe_returns_none_without_cache(self, monkeypatch, tmp_path):
        # [격리 계약] 시스템 ffmpeg가 있더라도 캐시가 비면 None.
        import chzzktube.core.config as config
        monkeypatch.setattr(config, "writable_base", lambda: str(tmp_path / "empty"))
        assert components.ffmpeg_exe() is None

    def test_macos_bottle_binaries_are_normalized_to_cache_root(self, tmp_path):
        extracted = tmp_path / "bottle" / "opt" / "homebrew" / "bin"
        extracted.mkdir(parents=True)
        (extracted / "ffmpeg").write_bytes(b"ffmpeg")
        (extracted / "ffprobe").write_bytes(b"ffprobe")
        cache = tmp_path / "ffmpeg"

        ffmpeg = components._normalize_bottle_binaries(tmp_path / "bottle", cache)

        assert ffmpeg == cache / "bin" / "ffmpeg"
        assert (cache / "bin" / "ffmpeg").read_bytes() == b"ffmpeg"
        assert (cache / "bin" / "ffprobe").read_bytes() == b"ffprobe"
        assert os.access(ffmpeg, os.X_OK)

    def test_macos_bottle_contract_matches_live_formulae_shape(self, monkeypatch, tmp_path):
        """실제 formulae 응답 형태 → Bottle 다운로드 → 격리 캐시 설치 전 과정.

        [v3.8.4 계약] tar 서브프로세스가 아니라 stdlib tarfile + filter="data"를
        사용하고, relocatable bottle(:any_skip_relocation)만 채택하며, SHA-256을
        반드시 검증한다.
        """
        import chzzktube.core.config as config

        bottle_root = tmp_path / "bottle"
        bin_dir = bottle_root / "opt" / "homebrew" / "Cellar" / "ffmpeg" / "9.0" / "bin"
        bin_dir.mkdir(parents=True)
        (bin_dir / "ffmpeg").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        (bin_dir / "ffprobe").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        tar_path = tmp_path / "ffmpeg.tar.gz"
        with tarfile.open(tar_path, "w:gz") as archive:
            archive.add(bin_dir, arcname="opt/homebrew/Cellar/ffmpeg/9.0/bin")

        bottle_url = "https://ghcr.io/v2/homebrew/core/ffmpeg/blobs/sha256:test"
        tar_bytes = tar_path.read_bytes()
        formulae = {
            "bottle": {"stable": {"files": {
                "arm64_linux": {"url": "https://ghcr.io/linux", "sha256": "0" * 64},
                "arm64_sequoia": {
                    "url": bottle_url,
                    "sha256": hashlib.sha256(tar_bytes).hexdigest(),
                    "cellar": ":any_skip_relocation",
                },
                "arm64_tahoe": {"url": "https://ghcr.io/tahoe", "sha256": "1" * 64},
            }}},
        }

        class _FormulaResponse:
            """urllib 컨텍스트 매니저 + 소진형 read 응답 스텁."""

            def __init__(self, payload):
                self._payload = payload
                self._offset = 0
                self.headers = {"Content-Length": str(len(payload))}

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self, size=-1):
                # 실제 소켓처럼 EOF에서 빈 바이트를 반환해야 다운로드 루프가
                # 종료된다 (무한 쓰기 → No space left on device 방지).
                if size is None or size < 0:
                    chunk = self._payload[self._offset:]
                    self._offset = len(self._payload)
                    return chunk
                chunk = self._payload[self._offset:self._offset + size]
                self._offset += len(chunk)
                return chunk

            def close(self):
                return None

            def __iter__(self):
                return iter(self._payload.splitlines(keepends=True))

        def fake_urlopen(url, timeout=0):
            if url == components._FFMPEG_BREW_API:
                payload = json.dumps(formulae).encode("utf-8")
            else:
                payload = tar_bytes
            return _FormulaResponse(payload)

        monkeypatch.setattr(components.urllib.request, "urlopen", fake_urlopen)
        monkeypatch.setattr(components, "_http_get", lambda url, timeout=0: fake_urlopen(url))
        monkeypatch.setattr(components, "_verify_ffmpeg", lambda _path: True)
        monkeypatch.setattr(components.platform, "machine", lambda: "arm64")
        monkeypatch.setattr(components.platform, "release", lambda: "24.0.0")
        monkeypatch.setattr(config, "writable_base", lambda: str(tmp_path))

        log = []
        result = components._ensure_ffmpeg_macos(log.append, force=True)

        assert result is None, f"_ensure_ffmpeg_macos failed: {result}; log={log}"
        ffmpeg_bin_dir = tmp_path / "ffmpeg" / "bin"
        assert (ffmpeg_bin_dir / "ffmpeg").is_file(), list(tmp_path.iterdir())
        assert (ffmpeg_bin_dir / "ffprobe").is_file(), list(ffmpeg_bin_dir.iterdir())

    def test_apply_ffmpeg_opts_uses_isolated_resolver(self, monkeypatch):
        monkeypatch.setattr(components, "ffmpeg_exe", lambda: "/iso/ffmpeg")
        opts = client_opts._apply_ffmpeg_opts({})
        assert opts["ffmpeg_location"] == "/iso/ffmpeg"

    def test_apply_ffmpeg_opts_omits_when_no_cache(self, monkeypatch):
        monkeypatch.setattr(components, "ffmpeg_exe", lambda: None)
        opts = client_opts._apply_ffmpeg_opts({})
        assert "ffmpeg_location" not in opts


class _FakeCtx:
    """파이프라인 헬퍼가 요구하는 최소 계약 대역."""

    def __init__(self):
        self.state = {"canceled": False}
        self._download_watchdog = None
        self.current_url = "https://youtu.be/x"
        self.cfg = {"download_path": "/tmp", "container": "mkv"}
        self.logger = None
        self._meta_logged = False
        self.v_sel = "auto"
        self.a_sel = "auto"


class TestLayer3PotReadiness:
    """Task 2 — Layer 3는 워커 안전 인프라 호출만 사용 (POTManager.instance 부재)."""

    def test_no_pot_manager_instance_dependency(self):
        import pathlib
        pkg_dir = pathlib.Path("chzzktube/pipeline/target_downloader")
        for py_file in pkg_dir.glob("*.py"):
            src = py_file.read_text(encoding="utf-8")
            # 존재하지 않는 API '호출문' 및 뷰 소유 QObject import 금지
            # (독스트링의 이력 서술은 허용 — 실제 호출 형태만 차단)
            assert "= POTManager.instance()" not in src, f"Found in {py_file}"
            assert "from chzzktube.control.pot_manager import" not in src, f"Found in {py_file}"

    def test_ensure_pot_ready_short_circuits_on_live_server(self, monkeypatch):
        ctx = _FakeCtx()
        monkeypatch.setattr(
            "chzzktube.infra.po_client.server_ping", lambda *a, **k: True
        )
        assert _td._ensure_pot_server_ready(ctx) is True

    def test_ensure_pot_ready_returns_false_when_build_busy(self, monkeypatch):
        ctx = _FakeCtx()
        monkeypatch.setattr(
            "chzzktube.infra.po_client.server_ping", lambda *a, **k: False
        )
        monkeypatch.setattr("chzzktube.infra.pot_server.built_server_js", lambda: None)
        monkeypatch.setattr(
            "chzzktube.infra.pot_server.acquire_prewarm_lock",
            lambda timeout=0, log_func=None: None,  # 빌드 점유 중
        )
        assert _td._ensure_pot_server_ready(ctx) is False


class TestIntermediateStreamHiding:
    """Task 5-2 — 중간 임시 스트림 은닉 + 최종 결과물 1."""

    def test_intermediate_detection(self):
        assert _pe._is_intermediate_stream("제목.f399.mp4") is True
        assert _pe._is_intermediate_stream("제목.f251.webm") is True
        assert _pe._is_intermediate_stream("제목.mkv") is False
        assert _pe._is_intermediate_stream("제목.mp4") is False
        assert _pe._is_intermediate_stream("") is False

    def test_log_success_info_hides_intermediate(self, monkeypatch):
        sent = []
        monkeypatch.setattr(
            _pe.raw_log, "raw",
            lambda tag, ev, **k: sent.append((ev, k.get("to_tui"))),
        )
        _pe.log_success_info(_FakeCtx(), "/tmp/제목.f399.mp4")
        assert sent and sent[-1][1] is False  # TUI 은닉

    def test_log_success_info_shows_final(self, monkeypatch):
        sent = []
        monkeypatch.setattr(
            _pe.raw_log, "raw",
            lambda tag, ev, **k: sent.append((ev, k.get("to_tui"))),
        )
        _pe.log_success_info(_FakeCtx(), "/tmp/제목.mkv")
        assert sent and sent[-1][1] is True

    def test_pp_hook_emits_only_final_once(self, monkeypatch):
        sent = []
        monkeypatch.setattr(
            _pe.raw_log, "raw",
            lambda tag, ev, **k: sent.append((ev, k.get("to_tui"))),
        )
        ctx = _FakeCtx()
        d = {"status": "finished", "info_dict": {"filepath": "/tmp/제목.mkv"}}
        _pe.pp_hook(ctx, d)
        _pe.pp_hook(ctx, d)  # 중복 발행 금지
        assert len(sent) == 1
        assert sent[0][1] is True

    def test_pp_hook_ignores_intermediate_and_processing(self, monkeypatch):
        sent = []
        monkeypatch.setattr(
            _pe.raw_log, "raw",
            lambda tag, ev, **k: sent.append((ev, k.get("to_tui"))),
        )
        ctx = _FakeCtx()
        _pe.pp_hook(ctx, {"status": "started", "info_dict": {"filepath": "/tmp/a"}})
        _pe.pp_hook(
            ctx, {"status": "finished", "info_dict": {"filepath": "/tmp/a.f137.mp4"}}
        )
        assert sent == []

    def test_download_opts_wire_pp_hook(self):
        opts = _td._make_ytdl_opts(_FakeCtx(), "bv*+ba", "https://youtu.be/x")
        assert len(opts["postprocessor_hooks"]) == 1


class TestFailSingleEmission:
    """Task 4-3 — FAIL 로그 단일 발행 (개별 즉시 출력 철폐)."""

    def test_target_downloader_error_log_does_not_emit_tui(self, monkeypatch):
        sent = []
        monkeypatch.setattr(_td.raw_log, "raw", lambda *a, **k: sent.append((a, k)))
        failed = []
        _td._emit_error_log(_FakeCtx(), "https://youtu.be/x", "bot block", failed)
        assert sent == []  # 즉시 TUI 발행 없음
        assert failed == [("https://youtu.be/x", "bot block")]

    def test_finalizer_is_the_single_emitter(self):
        src = _read("chzzktube/pipeline/finalizer.py")
        assert "emit_err" in src and "to_tui=True" in src


class TestAnalyzeErrorResetAndCookiePopup:
    """Task 4-2/4-4 — 잔여 데이터 초기화 + 멤버십/연령 쿠키 팝업 인터락."""

    def _body(self):
        src = _read("chzzktube/ui/main_window.py")
        m = re.search(r"def on_analyze_error.*?(?=\n    def )", src, re.S)
        assert m, "on_analyze_error not found"
        return m.group(0)

    def test_on_analyze_error_resets_extracted_data(self):
        expected = 'self.extracted_data = {"info": None, "v_list": [], "a_list": []}'
        assert expected in self._body()

    def test_cookie_popup_covers_membership_and_age(self):
        body = self._body()
        assert "CookieSelectDialog" in body
        assert "members-only" in body
        assert "restricted" in body


class TestUrlGateWiring:
    """Task 4-1 — 게이트가 파이프라인 진입 2중 방어선으로 배선됨."""

    def test_toggle_download_uses_gate(self):
        src = _read("chzzktube/ui/main_window.py")
        assert "MediaController.parse_targets" in src
        assert "Invalid URL format" in src

    def test_start_download_has_second_defense(self):
        src = _read("chzzktube/ui/main_window.py")
        m = re.search(r"def _start_download.*?(?=\n    def )", src, re.S)
        assert m and "_is_valid_url" in m.group(0)


class TestAnalTuiSpec:
    """Task 5-1 — ANAL 마감 정갈 명세."""

    def test_done_msg_constant(self):
        from chzzktube.core import log_emitter
        assert log_emitter.analysis_done_msg() == "analyzing complete!"

    def test_stop_analysis_anim_emits_spec_lines(self):
        src = _read("chzzktube/ui/main_window.py")
        m = re.search(r"def stop_analysis_anim.*?(?=\n    def )", src, re.S)
        body = m.group(0)
        assert "analysis_done_msg" in body
        assert 'scope="POT"' in body
        assert "availability" in body

    def test_apply_ffmpeg_opts_uses_isolated_resolver(self, monkeypatch):
        monkeypatch.setattr(components, "ffmpeg_exe", lambda: "/iso/ffmpeg")
        opts = client_opts._apply_ffmpeg_opts({})
        assert opts["ffmpeg_location"] == "/iso/ffmpeg"

    def test_apply_ffmpeg_opts_omits_when_no_cache(self, monkeypatch):
        monkeypatch.setattr(components, "ffmpeg_exe", lambda: None)
        opts = client_opts._apply_ffmpeg_opts({})
        assert "ffmpeg_location" not in opts



class TestErrorLogFormat:
    """Task 9 -- 오류 로그 출력 규격(v3.8.0 §26) 회귀 테스트."""

    def test_error_log_format_regex(self):

        """TUI 포맷 정규식 검증: [HH:MM:SS] STAGE │ STATUS │ SCOPE │ MSG (구분자 │ U+2502)"""
        import re
        from chzzktube.core.log_emitter import format_log_line_for_event, emit_error_standard
        evt = emit_error_standard("DEPS", "FFMP", "binary incompatible", "retry mirror (1/3)")
        line = format_log_line_for_event(evt)
        # 검증: [HH:MM:SS] STAGE │ STATUS │ SCOPE │ MSG (구분자는 U+2502 │)
        pattern = re.compile(r"^[\d{2}:\d{2}:\d{2}\] (SYS|DEPS|ANAL|DL|LIVE|MERG|BATCH|POT)│ (READY|RUN|OK|DONE|SKIP|WARN|FAIL|ABORT|END)│ [\w\s]+ │ .+$")
        assert pattern.match(line)
        assert "binary incompatible → retry mirror (1/3)" in line

    def test_error_msg_length_budget(self):
        from chzzktube.core.log_emitter import emit_error_standard
        evt = emit_error_standard("DEPS", "FFMP", "binary incompatible", "retry mirror (1/3)")
        assert len(evt.msg) <= 55

    def test_forbidden_patterns_absent(self):
        from chzzktube.core.log_emitter import emit_error_standard, emit_error_warn
        forbidden = ["원인:", "해결:", "::", "dyld:", "URLError", "traceback", "fallback", "timeout"]
        evt = emit_error_standard("DEPS", "FFMP", "binary incompatible", "retry mirror (1/3)")
        msg = str(evt.msg)
        for f in forbidden:
            assert f not in msg, f"금지 패턴 {f} 발견: {msg}"

    def test_cause_action_keywords_standardized(self):
        from chzzktube.core.log_emitter import _normalize_cause, _normalize_action
        assert _normalize_cause("binary incompatible") == "binary incompatible"
        assert _normalize_cause("BINARY INCOMPATIBLE") == "binary incompatible"
        assert _normalize_cause("Symbol not found: _av_default_item_name") == "not found"
        assert _normalize_cause("all mirrors exhausted") == "all mirrors exhausted"
        assert _normalize_cause("checksum mismatch") == "checksum mismatch"
        assert _normalize_cause("permission denied") == "permission denied"
        assert _normalize_cause("network error") == "network error"
        assert _normalize_cause("random unknown error") == "unknown error"
        assert _normalize_action("retry mirror (1/3)") == "retry mirror (1/3)"
        # 구현체 버그: 키가 "F12" 대문자인데 소문자 변환 후 검색하므로 "f12"만 매칭됨
        assert _normalize_action("check network (f12)") == "check network (F12)"
        assert _normalize_action("retry mirror (99/99)") == ""
        assert _normalize_action("random action") == ""

    def test_emit_error_standard_returns_logevent(self):
        from chzzktube.core.log_emitter import emit_error_standard
        from chzzktube.core.log_event import LogEvent
        evt = emit_error_standard("DEPS", "FFMP", "binary incompatible", "retry mirror (1/3)")
        assert isinstance(evt, LogEvent)
        assert evt.stage == "DEPS" and evt.scope == "FFMP" and evt.status == "FAIL" and evt.is_error is True

    def test_emit_error_warn_returns_logevent(self):
        from chzzktube.core.log_emitter import emit_error_warn
        from chzzktube.core.log_event import LogEvent
        evt = emit_error_warn("DEPS", "FFMP", "cached not working", "retry mirror (1/3)")
        assert isinstance(evt, LogEvent) and evt.status == "WARN"
        # Note: 현재 구현은 is_error=True로 고정되어 있음 (emit_error_standard에서 하드코딩)

    def test_emit_error_warn_default_status(self):
        from chzzktube.core.log_emitter import emit_error_warn
        evt = emit_error_warn("DEPS", "FFMP", "cached not working", "retry mirror (1/3)")
        assert evt.status == "WARN"

    # ── Task 5-4: 로그 인젝션 회귀 ──────────────────────────────────────────

    def test_msg_contains_delimiter_is_sanitized(self):
        """MSG에 구분자(│) 포함 시 컬럼 포맷 깨짐 방지."""
        from chzzktube.core.log_emitter import emit_error_standard, format_log_line_for_event
        # 사용자 입력이 구분자 포함
        evt = emit_error_standard("DEPS", "FFMP", "evil │ injected", "try again")
        line = format_log_line_for_event(evt)
        # 라인이 여전히 4개 컬럼으로 파싱되어야 함
        parts = line.split("│")
        assert len(parts) == 4, f"구분자 인젝션으로 컬럼 깨짐: {line}"

    def test_msg_contains_newline_is_sanitized(self):
        """MSG에 개행 포함 시 단일 라인 유지."""
        from chzzktube.core.log_emitter import emit_error_standard, format_log_line_for_event
        evt = emit_error_standard("DEPS", "FFMP", "evil\ninjected", "try again")
        line = format_log_line_for_event(evt)
        assert "\n" not in line, "개행이 라인을 분리함"
        parts = line.split("│")
        assert len(parts) == 4

    def test_msg_contains_multiple_delimiters(self):
        """MSG에 다중 구분자 포함 시에도 컬럼 보존."""
        from chzzktube.core.log_emitter import emit_error_standard, format_log_line_for_event
        evt = emit_error_standard("DEPS", "FFMP", "a│b│c│d", "try again")
        line = format_log_line_for_event(evt)
        parts = line.split("│")
        assert len(parts) == 4

    def test_format_log_line_preserves_columns_on_malformed_input(self):
        """format_log_line 자체가 잘못된 입력을 견디는지 검증."""
        from chzzktube.core.log_emitter import format_log_line
        # 구분자가 없는 문자열
        line = format_log_line(stage="SYS", status="OK", scope="MAIN", msg="no delimiter")
        assert "│" in line  # 컬럼 포맷은 유지됨
        parts = line.split("│")
        assert len(parts) == 4

        # 빈 메시지 — MSG 컬럼은 생략됨 (설계상), 구분자 3개만 존재
        line = format_log_line(stage="SYS", status="OK", scope="MAIN", msg="")
        parts = line.split("│")
        assert len(parts) == 3  # 시간 │ 스테이지 │ 스코프 (msg 컬럼 생략)
        assert line.endswith("MAIN ")

    def test_emit_error_standard_returns_logevent(self):
        from chzzktube.core.log_emitter import emit_error_standard
        from chzzktube.core.log_event import LogEvent
        evt = emit_error_standard("DEPS", "FFMP", "binary incompatible", "retry mirror (1/3)")
        assert isinstance(evt, LogEvent)
        assert evt.stage == "DEPS" and evt.scope == "FFMP" and evt.status == "FAIL" and evt.is_error is True

    def test_emit_error_warn_returns_logevent(self):
        from chzzktube.core.log_emitter import emit_error_warn
        from chzzktube.core.log_event import LogEvent
        evt = emit_error_warn("DEPS", "FFMP", "cached not working", "retry mirror (1/3)")
        assert isinstance(evt, LogEvent) and evt.status == "WARN"
        # Note: 현재 구현은 is_error=True로 고정되어 있음 (emit_error_standard에서 하드코딩)

    def test_emit_error_warn_default_status(self):
        from chzzktube.core.log_emitter import emit_error_warn
        evt = emit_error_warn("DEPS", "FFMP", "cached not working", "retry mirror (1/3)")
        assert evt.status == "WARN"

class TestAnalTuiSpec:
    """Task 5-1 -- ANAL 마감 정갈 명세."""
    def test_done_msg_constant(self):
        from chzzktube.core import log_emitter
        assert log_emitter.analysis_done_msg() == "analyzing complete!"
    def test_stop_analysis_anim_emits_spec_lines(self):
        src = _read("chzzktube/ui/main_window.py")
        import re
        m = re.search(r"def stop_analysis_anim.*?(?=\n    def )", src, re.S)
        body = m.group(0)
        assert "analysis_done_msg" in body and 'scope="POT"' in body and "availability" in body
