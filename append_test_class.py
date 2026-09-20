import sys

with open('tests/test_v38_contracts.py', 'r', encoding='utf-8') as f:
    content = f.read()

new_class = """

class TestErrorLogFormat:
    \"\"\"Task 9 -- 오류 로그 출력 규격(v3.8.0 §26) 회귀 테스트.\"\"\"

    def test_error_log_format_regex(self):
        \"\"\"TUI 포맷 정규식 검증.\"\"\"
        import re
        pattern = re.compile(r"^\\[\d{2}:\d{2}:\d{2}\\] (SYS|DEPS|ANAL|DL|LIVE|MERG|BATCH|POT) \| (READY|RUN|OK|DONE|SKIP|WARN|FAIL|ABORT|END) \| \w+ :: 원인: [^─]+ / 해결: .+$")
        assert pattern.match("[03:07:29] DEPS │ WARN │ FFMP :: 원인: binary incompatible / 해결: trying mirror (1/3)")
        assert pattern.match("[03:07:49] SYS  │ FAIL │ MAIN :: 원인: all mirrors exhausted / 해결: check network (F12)")

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
        assert _normalize_cause("Symbol not found: _av_default_item_name") == "binary incompatible"
        assert _normalize_cause("all mirrors exhausted") == "all mirrors exhausted"
        assert _normalize_cause("checksum mismatch") == "checksum mismatch"
        assert _normalize_cause("permission denied") == "permission denied"
        assert _normalize_cause("network error") == "network error"
        assert _normalize_cause("random unknown error") == "unknown error"
        assert _normalize_action("retry mirror (1/3)") == "retry mirror (1/3)"
        assert _normalize_action("CHECK NETWORK (F12)") == "check network (F12)"
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
        assert isinstance(evt, LogEvent) and evt.is_error is False and evt.status == "WARN"

    def test_emit_error_warn_default_status(self):
        from chzzktube.core.log_emitter import emit_error_warn
        evt = emit_error_warn("DEPS", "FFMP", "cached not working", "retry mirror (1/3)")
        assert evt.status == "WARN"


class TestAnalTuiSpec:
    \"\"\"Task 5-1 -- ANAL 마감 정갈 명세.\"\"\"
    def test_done_msg_constant(self):
        from chzzktube.core import log_emitter
        assert log_emitter.analysis_done_msg() == "analyzing complete!"
    def test_stop_analysis_anim_emits_spec_lines(self):
        src = _read("chzzktube/ui/main_window.py")
        import re
        m = re.search(r"def stop_analysis_anim.*?(?=\n    def )", src, re.S)
        body = m.group(0)
        assert "analysis_done_msg" in body and 'scope="POT"' in body and "availability" in body
"""

with open('tests/test_v38_contracts.py', 'w', encoding='utf-8') as f:
    f.write(content.rstrip() + "\n\n" + new_class)
print('Done')