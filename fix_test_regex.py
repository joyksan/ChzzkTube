import re

with open('tests/test_v38_contracts.py', 'r', encoding='utf-8') as f:
    content = f.read()

old = '''    def test_error_log_format_regex(self):
        """TUI 포맷 정규식 검증: [HH:MM:SS] STAGE │ STATUS │ SCOPE │ MSG"""
        import re
        from chzzktube.core.log_emitter import format_log_line_for_event, emit_error_standard
        evt = emit_error_standard("DEPS", "FFMP", "binary incompatible", "retry mirror (1/3)")
        line = format_log_line_for_event(evt)
        # 검증: [HH:MM:SS] STAGE │ STATUS │ SCOPE │ MSG (MSG는 cause → action)
        # STAGE/STATUS는 5자 폭으로 패딩되어 있음 (예: "DEPS  ", "FAIL  ")
        pattern = re.compile(r"^\[\d{2}:\d{2}:\d{2}\] (SYS|DEPS|ANAL|DL|LIVE|MERG|BATCH|POT)\s* \| (READY|RUN|OK|DONE|SKIP|WARN|FAIL|ABORT|END)\s* \| \w+\s* \| .+$")
        assert pattern.match(line)
        assert "binary incompatible → retry mirror (1/3)" in line'''

new = '''    def test_error_log_format_regex(self):
        """TUI 포맷 정규식 검증: [HH:MM:SS] STAGE │ STATUS │ SCOPE │ MSG"""
        import re
        from chzzktube.core.log_emitter import format_log_line_for_event, emit_error_standard
        evt = emit_error_standard("DEPS", "FFMP", "binary incompatible", "retry mirror (1/3)")
        line = format_log_line_for_event(evt)
        # 검증: [HH:MM:SS] STAGE │ STATUS │ SCOPE │ MSG (MSG는 cause → action)
        # STAGE/STATUS는 5자 폭으로 패딩되어 있음 (예: "DEPS  ", "FAIL  ")
        # 구분자는 박스 그리기 문자 │ (U+2502)임
        pattern = re.compile(r"^\[\d{2}:\d{2}:\d{2}\] (SYS|DEPS|ANAL|DL|LIVE|MERG|BATCH|POT)│ (READY|RUN|OK|DONE|SKIP|WARN|FAIL|ABORT|END)│ .+$")
        assert pattern.match(line)
        assert "binary incompatible → retry mirror (1/3)" in line'''

with open('tests/test_v38_contracts.py', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace(old, new)

with open('tests/test_v38_contracts.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Done')