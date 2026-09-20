# ChzzkTube Project Full Codebase


## File: append_test_class.py

```python
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
```

## File: bump_version.py

```python
### bump_version.py
import re
import sys

FILE_PATH = "chzzktube/core/config.py"
try:
    with open(FILE_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    # 큰따옴표/작은따옴표 및 한글/특수문자 괄호 조합까지 모두 허용하는 정규식
    pattern = r'(_APP_VERSION\s*=\s*["\']v)(\d+)\.(\d+)\.(\d+)(.*?["\'])'

    def bump_patch(match):
        prefix = match.group(1)         # _APP_VERSION = "v
        major = match.group(2)          # 3
        minor = match.group(3)          # 1
        patch = int(match.group(4)) + 1 # 0 -> 1
        suffix = match.group(5)         
        
        new_ver = f"{prefix}{major}.{minor}.{patch}{suffix}"
        print(f"[Labmem 004] Version Bump: {match.group(0)} -> {new_ver}")
        return new_ver

    updated_content, count = re.subn(pattern, bump_patch, content)

    if count > 0:
        with open(FILE_PATH, "w", encoding="utf-8") as f:
            f.write(updated_content)
        print("[Labmem 004] config.py 버전 업그레이드 성공!")
    else:
        print("[Labmem 004 ERROR] config.py에서 _APP_VERSION 패턴을 찾지 못했습니다!")
        sys.exit(1)

except (OSError, re.error) as e:
    print(f"[Labmem 004 CRITICAL] 오류 발생: {e}")
    sys.exit(1)

```

## File: debug_test.py

```python
import chzzktube.core.raw_log as raw_log
events = []
raw_log.subscribe_concise(lambda ev, is_status, is_error: events.append(ev))
from chzzktube.control.startup_coordinator import StartupCoordinator
from unittest.mock import Mock
c = StartupCoordinator(Mock())
c._on_pot_status('staged')
import time
deadline = time.time() + 2.0
while time.time() < deadline and not events:
    time.sleep(0.02)
ev = events[-1]
print('stage:', repr(ev.stage), 'scope:', repr(ev.scope))
```

## File: debug_test2.py

```python
import chzzktube.core.raw_log as raw_log; events = []; raw_log.subscribe_concise(lambda ev, is_status, is_error: events.append(ev)); from chzzktube.control.startup_coordinator import StartupCoordinator; from unittest.mock import Mock; c = StartupCoordinator(Mock()); c._on_pot_status(\u0027staged\u0027); import time; deadline = time.time() + 2.0; while time.time() < deadline and not events: time.sleep(0.02); ev = events[-1]; print(\u0027stage:\u0027, repr(ev.stage), \u0027scope:\u0027, repr(ev.scope))

```

## File: fix_regex_test.py

```python
#!/usr/bin/env python3
import re

line = '[07:43:15] DEPS  │ FAIL  │ FFMP  │ binary incompatible → retry mirror (1/3)'
print("Input line:", repr(line))

# Current pattern in test
pattern = re.compile(r"^\[\d{2}:\d{2}:\d{2}\] (SYS|DEPS|ANAL|DL|LIVE|MERG|BATCH|POT)│ (READY|RUN|OK|DONE|SKIP|WARN|FAIL|ABORT|END)│ [\w\s]+ \| .+$")
result = pattern.match('[07:37:43] DEPS  │ FAIL  │ FFMP  │ binary incompatible → retry mirror (1/3)')
print("Test 1 (with │):", pattern.match('[07:37:43] DEPS  │ FAIL  │ FFMP  │ binary incompatible → retry mirror (1/3)'))

# The actual separator is " │ " (space + box char + space)
# The box drawing char is │ (U+2502)
# The pattern should match " │ " (space + box char + space)
pattern2 = re.compile(r"^\[\d{2}:\d{2}:\d{2}\] (SYS|DEPS|ANAL|DL|LIVE|MERG|BATCH|POT)\s*│\s*(READY|RUN|OK|DONE|SKIP|WARN|FAIL|ABORT|END)\s*│\s*[\w\s]+ │ .+$")
print("Test 2:", pattern2.match('[07:37:43] DEPS  │ FAIL  │ FFMP  │ binary incompatible → retry mirror (1/3)'))

# Let's check what the actual line looks like
print("Line:", repr('[07:37:43] DEPS  │ FAIL  │ FFMP  │ binary incompatible → retry mirror (1/3)'))
print("Has │:", '│' in '[07:37:43] DEPS  │ FAIL  │ FFMP  │ binary incompatible → retry mirror (1/3)')
print("Has |:", '|' in '[07:37:43] DEPS  │ FAIL  │ FFMP  │ binary incompatible → retry mirror (1/3)')]
```

## File: fix_test_regex.py

```python
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
```

## File: fix_tests.py

```python
import sys

with open('tests/test_v38_contracts.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find start and end of TestErrorLogFormat class
start = None
end = None
for i, line in enumerate(lines):
    if 'class TestErrorLogFormat:' in line:
        start = i
    if start is not None and i > start and line.strip() == 'class TestAnalTuiSpec:':
        end = i
        break

print(f"Start: {start}, End: {end}")

if start is not None and end is not None:
    # Replace lines[start:end] with new class
    new_class = '''class TestErrorLogFormat:
    """Task 9 -- 오류 로그 출력 규격(v3.8.0 §26) 회귀 테스트."""

    def test_error_log_format_regex(self):
        """TUI 포맷 정규식 검증: [HH:MM:SS] STAGE │ STATUS │ SCOPE │ MSG"""
        import re
        from chzzktube.core.log_emitter import format_log_line_for_event, emit_error_standard
        evt = emit_error_standard("DEPS", "FFMP", "binary incompatible", "retry mirror (1/3)")
        line = format_log_line_for_event(evt)
        # 검증: [HH:MM:SS] STAGE │ STATUS │ SCOPE │ MSG (MSG는 cause → action)
        pattern = re.compile(r"^\[\d{2}:\d{2}:\d{2}\] (SYS|DEPS|ANAL|DL|LIVE|MERG|BATCH|POT) \| (READY|RUN|OK|DONE|SKIP|WARN|FAIL|ABORT|END) \| \w+ \| .+$")
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
        assert isinstance(evt, LogEvent) and evt.status == "WARN"
        # Note: 현재 구현은 is_error=True로 고정되어 있음 (emit_error_standard에서 하드코딩)

    def test_emit_error_warn_default_status(self):
        from chzzktube.core.log_emitter import emit_error_warn
        evt = emit_error_warn("DEPS", "FFMP", "cached not working", "retry mirror (1/3)")
        assert evt.status == "WARN"
'''
    lines[start:end] = [new_class + '\n']
    with open('tests/test_v38_contracts.py', 'w', encoding='utf-8') as f:
        f.writelines(lines)
    print("Done")
else:
    print("Could not find class boundaries")
    sys.exit(1)
```

## File: main.py

```python
"""ChzzkTube — 씬 런처 (루트 진입점).

실행 계약:
- `python main.py` (개발) — chzzktube.ui.main_window.main() 호출
- PyInstaller `Analysis(['main.py'])` (번들) — 동일 진입점 자동 추적

앱 본체는 chzzktube/ 패키지에 계층별로 분리되어 있다.
"""
import sys

# Qt보다 먼저: 프로젝트 로컬 pip 오버레이(.pylib)를 sys.path 선두에.
# (venv는 uv 소유 → 앱이 직접 수정 금지. 상세: pylib_bootstrap.docstring)
import chzzktube.infra.pylib_bootstrap as _pylib_bootstrap
import chzzktube.infra.cleanup as _cleanup

_PYLIB_PATH = _pylib_bootstrap.bootstrap()

# 앱 기동 시 이전 세션 잔재 정리
_cleanup.cleanup_on_startup()

from chzzktube.ui.main_window import main

if __name__ == "__main__":
    sys.exit(main())

```

## File: smoke_test.py

```python
import os
import re
import sys
import traceback

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

from chzzktube.core.config import BASE_DIR
from chzzktube.ui.dialogs import (
    ActionCountdownDialog,
    CookieSelectDialog,
    CookieViewerDialog,
    ExitConfirmDialog,
    SettingsDialog,
    VerboseLogWindow,
)
from chzzktube.ui.main_window import MainWindow

# [Debug Dialogs] --debug-dialogs 감지 시 offscreen 미설정 → 네이티브 macOS 창으로 렌더링
if "--debug-dialogs" not in sys.argv:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"

# [Windows 리다이렉트 대비] stdout/stderr가 파이프·파일로 리다이렉트되면
# 로케일 인코딩(cp949)으로 떨어져 em-dash(\u2014) 등에서 UnicodeEncodeError가
# 발생한다 — 테스트 자체 결함이 아니라 하네스 결함이므로 UTF-8을 강제한다.
for _stream in (sys.stdout, sys.stderr):
    _reconfig = getattr(_stream, "reconfigure", None)
    if callable(_reconfig):
        try:
            _reconfig(encoding="utf-8", errors="replace")
        except (OSError, re.error):
            pass


def _setup_app():
    """공통 QApplication 세팅 (Windows 자글거림 박멸: 안티앨리어싱 및 힌팅 통제)."""
    from PySide6.QtCore import Qt

    # 1. High-DPI 스케일링 정책 동기화 (QApplication 생성 전 필수 지정)
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication.instance() or QApplication(sys.argv)

    # 2. Cascadia Mono 가변 폰트 에셋 로드
    font_path = os.path.join(BASE_DIR, "assets", "CascadiaMono-VariableFont_wght.ttf")
    if os.path.exists(font_path):
        QFontDatabase.addApplicationFont(font_path)

    # [핵심 교정] 라틴(Cascadia Mono) + CJK(맑은 고딕) 다중 패밀리 체인 구축
    font = QFont()
    font.setFamilies(["Cascadia Mono", "Malgun Gothic", "맑은 고딕", "Apple SD Gothic Neo"])
    font.setPointSize(11)

    # [한글 뭉개짐 방지] 힌팅을 완전 끄지 않고 수직 힌팅을 허용하여 한글 가독성 확보
    font.setHintingPreference(QFont.HintingPreference.PreferVerticalHinting)
    font.setStyleStrategy(
        QFont.StyleStrategy.PreferAntialias 
        | QFont.StyleStrategy.PreferQuality
    )

    # Windows CJK 인조 볼드 왜곡(자글거림)을 유발하던 Weight(550)을 제거하고 순정 Normal(400)로 안정화
    font.setWeight(QFont.Weight.Normal)

    app.setFont(font)
    return app


def test_main():
    print("[Smoke Test] PySide6 App 및 MainWindow 초기화 테스트 시작")
    app = _setup_app()
    assert app is not None

    try:
        win = MainWindow()
        print("[Smoke Test] MainWindow 생성 성공!")
        assert win is not None
        assert win.ctrl is not None
        # [v3.8.1] 폴백 제거 — _force_unlock_input 속성 없음
        print("[Smoke Test] ctrl.state 확인:", win.ctrl.state)

        dlg = SettingsDialog(win, is_running=False)
        assert dlg.cb_container.currentData() in ("mp4", "mkv", "webm")
        assert dlg.cb_container.count() == 3
        dlg.update_filename_preview()
        print("[Smoke Test] SettingsDialog 생성 OK — combos", dlg.cb_container.count())
        print("[Smoke Test] PASS")
        return 0
    except (OSError, re.error) as e:
        
        print("[Smoke Test] FAIL:", e)
        traceback.print_exc()
        return 1


def debug_show_all_dialogs():
    """메인 윈도우를 비 파이썬 창 전면에 띄우고, 7종 다이얼로그를 그 위에 완벽히 정렬"""
    print("[Debug Dialogs] 전면 프리뷰 모드 가동 (다이얼로그 7종)")
    app = _setup_app()

    # 1. 배경 캔버스 (메인 윈도우 먼저 전면에 전개)
    win = MainWindow()
    win.setWindowTitle("ChzzkTube [배경 캔버스]")
    win.resize(1000, 600)
    win.move(30, 420)
    win.show()
    win.raise_()
    win.activateWindow()

    # 다이얼로그 GC 방어 컨테이너 (여기에 메인 윈도우를 섞지 마세요!)
    dialogs = []

    # ── [1열: 좌측 소형 스택 (x=30)] ──
    d1 = ExitConfirmDialog(win, is_running=True)
    d1.move(30, 30)
    dialogs.append(d1)

    d2 = ExitConfirmDialog(win, is_running=False)
    d2.move(30, 175)
    dialogs.append(d2)

    d3 = ActionCountdownDialog("exit_app", win)
    d3.timer.stop()
    d3.lbl_msg.setText("Download complete.\n<b>60s</b> until [<b>exit</b>] runs. (Preview)")
    d3.move(30, 320)
    dialogs.append(d3)

    # ── [2열: 쿠키 관리 스택 (x=430)] ──
    d4 = CookieSelectDialog(win)
    d4.move(430, 30)
    dialogs.append(d4)

    # ── [3열: 660px 메인 설정창 (x=750)] ──
    d5 = SettingsDialog(win, is_running=False)
    d5.move(750, 30)
    dialogs.append(d5)

    # ── [4열: 대형 뷰어 스택 (x=1430)] ──
    sample_cookie = (
        "# Netscape HTTP Cookie File\n"
        ".naver.com\tTRUE\t/\tTRUE\t1799999999\tNID_AUT\tSAMPLE_TOKEN_VALUE\n"
        ".naver.com\tTRUE\t/\tTRUE\t1799999999\tNID_SES\tSAMPLE_SESSION_VALUE\n"
        ".youtube.com\tTRUE\t/\tTRUE\t1799999999\tVISITOR_INFO1_LIVE\tSAMPLE_VISITOR"
    )
    d6 = CookieViewerDialog("쿠키 뷰어 (테스트 프리뷰)", sample_cookie, win)
    d6.move(1430, 30)
    dialogs.append(d6)

    d7 = VerboseLogWindow(win)
    d7.set_content(
        "[12:00:00] SYS  │ OK    │ MAIN  │ System initialized\n"
        "[12:00:01] DEPS │ OK    │ YTDL  │ yt-dlp up to date\n"
        "[12:00:02] POT  │ READY │ POT   │ Server bound (127.0.0.1:4416)\n"
        "[12:00:03] ANAL │ OK    │ YT    │ [1080p60] Test Stream Isolated"
    )
    d7.move(1430, 550)
    dialogs.append(d7)

    # ── [무결점 계층 정렬 시퀀스] ──
    # 메인 윈도우 위로 다이얼로그들을 순차적으로 끌어올림
    for dlg in dialogs:
        dlg.show()
        dlg.raise_()

    # macOS 창 관리자의 비동기 렌더링 대비 1회 재정돈 (lower 호출 절대 금지)
    def _enforce_stack():
        for dlg in dialogs:
            dlg.raise_()
        # 설정창에 포커스를 주어 키보드 ESC 테스트 편의성 확보
        d5.activateWindow()

    QTimer.singleShot(100, _enforce_stack)

    print(f"[Debug Dialogs] 총 {len(dialogs)}개 핵심 팝업이 메인 윈도우 전면에 고정되었습니다.")
    return app.exec()

if __name__ == "__main__":
    if "--debug-dialogs" in sys.argv:
        sys.exit(debug_show_all_dialogs())
    sys.exit(test_main())

```

## File: sync_mirrors.py

```python
# sync_mirrors.py - .py source -> mirrors/*.md mirror auto-sync script
"""
Usage:
    python sync_mirrors.py              # sync all changed mirror files and chzzktube_codebase.md bundle
    python sync_mirrors.py --check      # check only (no writes)
    python sync_mirrors.py main utils   # target specific modules (by file name)
"""

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MIRRORS_DIR = ROOT / "mirrors"

# Mirror targets (extension excluded). .py -> mirrors/*.md
# New .py modules MUST be added here too.
MIRROR_MODULES = [
    # root
    "main",
    "bump_version",
    "smoke_test",
    "sync_mirrors",
    # chzzktube.ui
    "chzzktube.ui.dialogs",
    "chzzktube.ui.log_console",
    "chzzktube.ui.main_window",
    "chzzktube.ui.theme",
    # chzzktube.control
    "chzzktube.control.controller",
    "chzzktube.control.pot_manager",
    "chzzktube.control.startup_coordinator",
    "chzzktube.control.startup_state",
    # chzzktube.workers
    "chzzktube.workers.analyze_worker",
    "chzzktube.workers.downloader",
    "chzzktube.workers.update_worker",
    # chzzktube.pipeline
    "chzzktube.pipeline.classifier",
    "chzzktube.pipeline.dl_context",
    "chzzktube.pipeline.finalizer",
    "chzzktube.pipeline.live_recorder",
    "chzzktube.pipeline.progress_emitter",
    "chzzktube.pipeline.target_downloader",
    # chzzktube.core
    "chzzktube.core.chzzk_api",
    "chzzktube.core.client_opts",
    "chzzktube.core.config",
    "chzzktube.core.cookies",
    "chzzktube.core.dl_platform",
    "chzzktube.core.log_emitter",
    "chzzktube.core.log_event",
    "chzzktube.core.log_history",
    "chzzktube.core.media",
    "chzzktube.core.playlist",
    "chzzktube.core.raw_log",
    "chzzktube.core.speed_window",
    "chzzktube.core.tool_log",
    "chzzktube.core.utils",
    "chzzktube.core.watchdog",
    "chzzktube.core.yt_logger_bridge",
    # chzzktube.infra
    "chzzktube.infra.components",
    "chzzktube.infra.node_provider",
    "chzzktube.infra.paths",
    "chzzktube.infra.platform",
    "chzzktube.infra.po_client",
    "chzzktube.infra.pot_provider",
    "chzzktube.infra.pot_server",
    "chzzktube.infra.pylib_bootstrap",
    "chzzktube.infra.updater",
]


def sync_module(name: str, dry_run: bool = False) -> int:
    """Sync one module .py -> mirrors/*.md. (1=changed, 0=same, 2=missing)"""
    clean_name = name.removesuffix(".py")

    # Modules inside the chzzktube package live under chzzktube/<subpkg>/
    if name.startswith("chzzktube."):
        parts = clean_name.split(".")
        # parts = ["chzzktube", "core", "yt_logger_bridge"]
        # src = chzzktube/core/yt_logger_bridge.py
        src = ROOT / "chzzktube" / Path(*parts[1:-1]) / f"{parts[-1]}.py"
    else:
        src = ROOT / f"{clean_name}.py"

    # 미러 파일명은 flat 유지 — chzzktube/core/config.py → mirrors/config.md
    # (기존 conventions 유지: HANDOVER 참조·미러 diff 시 basename 추적 용이)
    dst = MIRRORS_DIR / f"{clean_name.split('.')[-1]}.md"

    if not src.exists():
        print(f"[skip] {src.name} missing - target mirror not found")
        return 2

    content = src.read_bytes()
    if dst.exists() and dst.read_bytes() == content:
        print(f"[same] mirrors/{dst.name} up to date")
        return 0

    action = "check" if dry_run else "update"
    print(
        f"[{action}] {clean_name}.py -> mirrors/{dst.name} ({len(content)} bytes)"
    )
    if not dry_run:
        MIRRORS_DIR.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(content)
    return 1


def build_codebase_bundle():
    """Bundle all .py sources into mirrors/chzzktube_codebase.md single file."""
    bundle_path = MIRRORS_DIR / "chzzktube_codebase.md"
    exclude_dirs = {
        ".git",
        ".github",
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        ".pylib",
        "build",
        "dist",
        "tests",
        "mirrors",
    }

    MIRRORS_DIR.mkdir(parents=True, exist_ok=True)
    with open(bundle_path, "w", encoding="utf-8") as outfile:
        outfile.write("# ChzzkTube Project Full Codebase\n\n")
        for root, dirs, files in os.walk(ROOT):
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            for file in sorted(files):
                if file.endswith(".py"):
                    rel = os.path.relpath(os.path.join(root, file), ROOT)
                    outfile.write(f"\n## File: {rel}\n\n```python\n")
                    with open(
                        os.path.join(root, file), "r", encoding="utf-8", errors="ignore"
                    ) as infile:
                        outfile.write(infile.read())
                    outfile.write("\n```\n")
    print(f"[created] mirrors/{bundle_path.name} bundle")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="ChzzkTube .py source .md mirror file sync tool."
    )
    parser.add_argument(
        "modules",
        nargs="*",
        help="target modules (e.g. main downloader). Default: all.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="check only (no writes)",
    )
    args = parser.parse_args()

    targets = args.modules or MIRROR_MODULES
    results = [sync_module(m, dry_run=args.check) for m in targets]

    changed = sum(1 for r in results if r == 1)
    missing = sum(1 for r in results if r == 2)

    print("-" * 40)
    print(f"total {len(targets)}: changed {changed} / missing {missing}")

    # When not in --check mode, also generate/refresh the single bundle file
    if not args.check:
        build_codebase_bundle()

    return 0


if __name__ == "__main__":
    sys.exit(main())
```

## File: chzzktube/__init__.py

```python

```

## File: chzzktube/ui/__init__.py

```python

```

## File: chzzktube/ui/dialogs.py

```python
##### 팝업 다이얼로그 모음
from __future__ import annotations

import datetime
import os
from functools import partial
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from chzzktube.core import config
from chzzktube.core.cookies import get_browser_cookies
from chzzktube.ui import theme

if TYPE_CHECKING:
    from chzzktube.ui.main_window import MainWindow

try:
    import winsound
except ImportError:
    winsound = None


def show_info_message(parent, title, text, detail=None, is_error=False):
    """[교정] 기본 경로는 TUI 규격 TuiNoticeDialog로 위임 — 텍스트 중앙 정렬·
    플랫 버튼으로 앱 안내창 규격을 통일한다. setDetailedText가 필요한
    (detail 지정) 예외 케이스만 기존 QMessageBox 경로를 유지한다."""
    if detail:
        msg_box = QMessageBox(parent)
        msg_box.setIcon(QMessageBox.Icon.NoIcon)
        msg_box.setWindowTitle(title)
        prefix = "▲  " if is_error else "✓  "
        msg_box.setText(prefix + text)
        msg_box.setDetailedText(detail)
        msg_box.setStyleSheet(theme.MSGBOX_QSS)
        msg_box.addButton(
            "OK" if not is_error else "Close", QMessageBox.ButtonRole.AcceptRole
        )
        msg_box.exec()
        return
    prefix = "▲  " if is_error else "✓  "
    TuiNoticeDialog(
        parent,
        title=title,
        text=prefix + text,
        ok_label="Close" if is_error else "OK",
    ).exec()


class CustomComboBox(QComboBox):
    """표준 QComboBox 기반 콤보 — addItem(text, userData, icon) 계약 유지.

    [qfluentwidgets 의존 제거] 실제로 쓰던 기능은 시그니처 정규화뿐이었고,
    표준 위젯 + 다이얼로그 QSS로 통일해 PyQt-Fluent-Widgets 의존을 뗀다.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

    def addItem(self, text, userData=None, icon=None):
        if icon is not None:
            super().addItem(icon, text)
        else:
            super().addItem(text)
        if userData is not None:
            self.setItemData(self.count() - 1, userData)


# 2026-09-15 가로 폭 360 -> 280으로 수정
class ExitConfirmDialog(QDialog):
    """[교정] 컴팩트 280x125 규격, 칠흑 배경, 텍스트 완전 중앙 정렬"""
    def __init__(self, parent=None, is_running=False):
        super().__init__(parent)
        self.is_running = is_running
        self.setWindowTitle("ChzzkTube")
        self.setFixedSize(280, 125)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self.setStyleSheet(theme.DIALOG_BG_QSS)

        vbox = QVBoxLayout(self)
        vbox.setSpacing(14)
        vbox.setContentsMargins(16, 16, 16, 16)

        msg = "⚠️ A download is in progress.\nStop and exit ChzzkTube?" if self.is_running else "Exit ChzzkTube?"

        lbl = QLabel(msg)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setWordWrap(True)
        lbl.setStyleSheet("font-size: 11px; color: #e3e3e3; line-height: 1.4;")
        vbox.addWidget(lbl)

        btn_box = QHBoxLayout()
        btn_box.setSpacing(8)

        btn_exit = QPushButton("Exit")
        btn_exit.setStyleSheet(theme.BTN_EXIT_DANGER_QSS)
        btn_exit.clicked.connect(lambda: self.done(1))

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setStyleSheet(theme.BTN_NEUTRAL_QSS)
        btn_cancel.clicked.connect(lambda: self.done(0))

        btn_box.addWidget(btn_exit)
        btn_box.addWidget(btn_cancel)
        vbox.addLayout(btn_box)


class DepsProvisioningDialog(QDialog):
    """수급 중 종료 확인 다이얼로그 — 280×125, 중앙 정렬, 영문 (HANDOVER §4.1 준수)."""
    def __init__(self, parent=None, is_upgrading=False, is_pot_busy=False):
        super().__init__(parent)
        self.setWindowTitle("ChzzkTube")
        self.setFixedSize(280, 125)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self.setStyleSheet(theme.DIALOG_BG_QSS)

        vbox = QVBoxLayout(self)
        vbox.setSpacing(14)
        vbox.setContentsMargins(16, 16, 16, 16)

        parts = []
        if is_upgrading:
            parts.append("updating dependencies")
        if is_pot_busy:
            parts.append("preparing pot server")
        msg = " ".join(parts) if parts else "provisioning in progress"
        msg += ".\nstop and exit?"

        lbl = QLabel(msg)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setWordWrap(True)
        lbl.setStyleSheet("font-size: 11px; color: #e3e3e3; line-height: 1.4;")
        vbox.addWidget(lbl)

        btn_box = QHBoxLayout()
        btn_box.setSpacing(8)

        btn_stop = QPushButton("Stop & Exit")
        btn_stop.setStyleSheet(theme.BTN_EXIT_DANGER_QSS)
        btn_stop.clicked.connect(lambda: self.done(1))

        btn_continue = QPushButton("Continue")
        btn_continue.setStyleSheet(theme.BTN_NEUTRAL_QSS)
        btn_continue.clicked.connect(lambda: self.done(0))

        btn_box.addStretch(1)
        btn_box.addWidget(btn_stop)
        btn_box.addWidget(btn_continue)
        vbox.addLayout(btn_box)


class CookieSelectDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.selected_type = None
        self.selected_path = ""
        self.setWindowTitle("Load cookies…")
        self.setFixedSize(320, 220)  # [수정] 300x380 -> 320x220 컴팩트화
        self.setStyleSheet(theme.DIALOG_BG_QSS)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        grid = QGridLayout()
        grid.setSpacing(6)

        buttons = [
            ("Cookies.txt", "file"),
            ("Chrome", "chrome"),
            ("Firefox", "firefox"),
            ("Edge", "edge"),
            ("Opera", "opera"),
            ("Brave", "brave"),
            ("Vivaldi", "vivaldi"),
            ("Chromium", "chromium"),
            ("Whale", "whale"),
        ]

        # [수정] 2열 그리드 배치
        # [수정] partial을 이용한 클린 바인딩
        for idx, (text, b_type) in enumerate(buttons):
            btn = QPushButton(text)
            btn.setStyleSheet(theme.BTN_GRID_QSS)
            btn.clicked.connect(partial(self.on_select, b_type))
            grid.addWidget(btn, idx // 2, idx % 2)

        layout.addLayout(grid)

    def on_select(self, b_type):
        if b_type == "file":
            path, _ = QFileDialog.getOpenFileName(
                self,
                "Netscape HTTP Cookie Files",
                "",
                "Text Files (*.txt);;All Files (*.*)",
            )
            if path:
                self.selected_type = "cookie_file"
                self.selected_path = path
                self.accept()
            return

        else:
            if b_type in ["chrome", "edge", "whale", "chromium", "brave", "vivaldi"]:
                try:
                    import yt_dlp.cookies

                    yt_dlp.cookies.extract_cookies_from_browser(b_type)
                except Exception as ex:  # noqa: BLE001
                    show_info_message(
                        self,
                        "Error",
                        f"Failed to read browser ({b_type}) cookies.\n\nThe browser may be running, or\nsecurity policy (permission denied) blocks access.",
                        detail=str(ex),
                        is_error=True,
                    )
                    return

            self.selected_type = b_type
            self.selected_path = ""
            self.accept()

        self.selected_type = b_type
        self.selected_path = ""
        self.accept()


class ActionCountdownDialog(QDialog):
    """[교정] 칠흑 배경(#0d0d0d) 동화, 둥근 모서리 박멸, 플랫 TUI 스타일 재구축"""
    def __init__(self, action_type, parent=None):
        super().__init__(parent)
        self.action_type = action_type
        self.remaining_seconds = 60
        action_names = {"sleep": "sleep", "shutdown": "PC shutdown", "exit_app": "exit"}
        self.action_name = action_names.get(action_type, "action")

        self.setWindowTitle("Post-Download Action")
        self.setFixedSize(300, 125)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self.setStyleSheet(theme.DIALOG_BG_QSS)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        self.lbl_msg = QLabel(
            f"Download complete.\n<b>{self.remaining_seconds}s</b> until [<b>{self.action_name}</b>] runs."
        )
        self.lbl_msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_msg.setStyleSheet("font-size: 11px; color: #e0e0e0; line-height: 1.4;")
        layout.addWidget(self.lbl_msg)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        self.btn_now = QPushButton("Run Now")
        self.btn_now.setStyleSheet(theme.BTN_EXIT_DANGER_QSS)
        self.btn_now.clicked.connect(self.execute_now)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setStyleSheet(theme.BTN_NEUTRAL_QSS)
        self.btn_cancel.clicked.connect(self.cancel_action)

        btn_layout.addWidget(self.btn_now)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)

        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.update_timer)
        self.timer.start()

    def update_timer(self):
        self.remaining_seconds -= 1
        if self.remaining_seconds <= 0:
            self.timer.stop()
            self.accept()
        else:
            self.lbl_msg.setText(
                f"Download complete.\n<b>{self.remaining_seconds}s</b> until [<b>{self.action_name}</b>] runs."
            )

    def execute_now(self):
        self.timer.stop()
        self.accept()

    def cancel_action(self):
        self.timer.stop()
        self.reject()


class TuiNoticeDialog(QDialog):
    """[신규] TUI 규격 통합 안내창 — ExitConfirmDialog와 동일 규격(280x125,
    칠흑 배경, 텍스트 중앙 정렬). show_info_message의 QMessageBox를 대체하며,
    alt_label 지정 시 부가 버튼(View 등)이 추가된다. done 코드로 구분:
    RESULT_OK(0, 기본) / RESULT_ALT(2, 부가 — View 누르면 확인창이 닫히고
    호출자가 부가 동작을 이어간다)."""

    RESULT_OK = 0
    RESULT_ALT = 2

    def __init__(self, parent=None, title="", text="", ok_label="OK", alt_label=None):
        super().__init__(parent)
        self.setWindowTitle(title or "ChzzkTube")
        self.setFixedSize(280, 125)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self.setStyleSheet(theme.DIALOG_BG_QSS)

        vbox = QVBoxLayout(self)
        vbox.setSpacing(14)
        vbox.setContentsMargins(16, 16, 16, 16)

        lbl = QLabel(text)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setWordWrap(True)
        lbl.setStyleSheet("font-size: 11px; color: #e3e3e3; line-height: 1.4;")
        vbox.addWidget(lbl)

        btn_box = QHBoxLayout()
        btn_box.setSpacing(8)

        if alt_label:
            btn_alt = QPushButton(alt_label)
            btn_alt.setStyleSheet(theme.BTN_NEUTRAL_QSS)
            btn_alt.clicked.connect(lambda: self.done(self.RESULT_ALT))
            btn_box.addWidget(btn_alt)

        btn_ok = QPushButton(ok_label)
        btn_ok.setStyleSheet(theme.BTN_NEUTRAL_QSS)
        btn_ok.clicked.connect(self.accept)
        btn_box.addWidget(btn_ok)

        vbox.addLayout(btn_box)


class CookieViewerDialog(QDialog):
    """[교정] 10px 고밀도 TUI 뷰어 및 플랫 Close 버튼"""
    def __init__(self, title_text, content_text, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title_text)
        self.setFixedSize(650, 480)
        self.setStyleSheet(theme.DIALOG_BG_QSS)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        self.te_content = QTextEdit(self)
        self.te_content.setReadOnly(True)
        # [수정] 자동 줄바꿈 차단 및 8칸 탭 스톱 설정으로 TSV 컬럼 정렬 유지
        self.te_content.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        font_metrics = self.te_content.fontMetrics()
        self.te_content.setTabStopDistance(font_metrics.horizontalAdvance(" ") * 8)
        self.te_content.setPlainText(content_text)
        self.te_content.setStyleSheet(theme.TE_CONTENT_QSS)
        layout.addWidget(self.te_content)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_close = QPushButton("Close")
        btn_close.setFixedWidth(90)
        btn_close.setStyleSheet(theme.BTN_CLOSE_QSS)
        btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)


# [raw 상세 로그] DEPS 확인 시 실제 CLI를 실행해 셸에서 친 것과 동일한 원문을
# 2026-09-15 모던 TUI 하이퍼미니멀리즘 전면 개편
# F12 상세 로그에 기록한다. yt-dlp --version → '2026.08.19', streamlink
# --version → 'streamlink 8.5.0' 식의 터미널 출력 그대로.
class SettingsDialog(QDialog):
    """하이퍼미니멀 모던 TUI 스타일 설정 패널 (Flat, Monospace, Borderless)."""

    def __init__(self, parent: MainWindow | None = None, is_running: bool = False):
        super().__init__(parent)
        self.parent_win: MainWindow | None = parent  # [교정] 따옴표 제거로 UP037 박멸
        self.cfg = (
            parent.cfg
            if parent and hasattr(parent, "cfg")
            else config.load_config()
        )
        self.is_running = is_running
        self._loading = True

        self.setWindowTitle("Settings")
        self.setFixedSize(660, 680)
        self.setStyleSheet(theme.TUI_STYLE)

        self.init_ui()
        self.load_settings()
        self._loading = False

    def closeEvent(self, event):
        event.accept()

    # ── 자체 방어적 위임 메서드 ───────────────────────────────
    def save_cfg(self):
        if self.parent_win and hasattr(self.parent_win, "save_cfg"):
            self.parent_win.save_cfg()
        else:
            config.save_config(self.cfg)

    def update_ui_state(self):
        if self.parent_win and hasattr(self.parent_win, "update_ui_state"):
            self.parent_win.update_ui_state()

    # ── [복구] 누락되었던 TUI 빌더 헬퍼 4종 ────────────────────
    def _tui_sep(self):
        """1px 단색 TUI 구분선 생성."""
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("background-color: #1a1a1a; max-height: 1px; min-height: 1px; border: none;")
        return line

    def _sec_header(self, text):
        """아스키 스타일 섹션 헤더 라벨 생성."""
        lbl = QLabel(f"// {text}")
        lbl.setStyleSheet("color: #4ec9b0; font-weight: bold; font-size: 11px; padding-top: 6px;")
        return lbl

    def _key_label(self, text, width=120):
        """키 라벨 고정폭 생성."""
        lbl = QLabel(text)
        lbl.setFixedWidth(width)
        lbl.setStyleSheet("color: #888888; font-size: 11px;")
        return lbl

    def _make_combo(self, options):
        """TUI 스타일 드롭다운 콤보박스 생성."""
        cb = CustomComboBox()
        cb.setStyleSheet("""
            QComboBox { background-color: #141414; color: #d4d4d4; border: 1px solid #282828; padding: 3px 8px; font-size: 11px; }
            QComboBox:hover { border-color: #4ec9b0; }
            QComboBox::drop-down { border: none; width: 14px; }
            QComboBox QAbstractItemView { background-color: #141414; color: #d4d4d4; border: 1px solid #333333; selection-background-color: #1d3a34; selection-color: #4ec9b0; outline: none; }
        """)
        for k, v in options:
            cb.addItem(v, k)
        return cb

    # ── UI 조립 ───────────────────────────────────────────────
    def init_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # 1. 상단 스크롤 영역
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(theme.SETTINGS_SCROLL_QSS)

        body = QWidget()
        body.setStyleSheet("background-color: #0d0d0d;")
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        layout = QVBoxLayout(body)
        layout.setSpacing(8)
        layout.setContentsMargins(20, 14, 20, 14)

        # ── 1. CONTAINER & FORMAT ──
        layout.addWidget(self._sec_header("CONTAINER & FORMAT"))
        layout.addWidget(self._tui_sep())

        r_cont = QHBoxLayout()
        r_cont.addWidget(self._key_label("Container"))
        self.cb_container = self._make_combo([
            ("mkv", "mkv (universal subtitle)"),
            ("mp4", "mp4 (broad compatibility)"),
            ("webm", "webm (web efficient)"),
        ])
        self.cb_container.currentIndexChanged.connect(
            lambda: self._apply_change("container", self.cb_container.currentData())
        )
        r_cont.addWidget(self.cb_container, 1)
        layout.addLayout(r_cont)

        r_res = QHBoxLayout()
        r_res.addWidget(self._key_label("Max Resolution"))
        self.cb_max_res = self._make_combo([
            ("none", "None (Source Max)"),
            ("2160", "4K (2160p)"),
            ("1440", "2K (1440p)"),
            ("1080", "1080p"),
            ("720", "720p"),
            ("480", "480p"),
            ("360", "360p"),
        ])
        self.cb_max_res.currentIndexChanged.connect(
            lambda: self._apply_change("max_video_res", self.cb_max_res.currentData())
        )
        r_res.addWidget(self.cb_max_res, 1)

        self.chk_pick = QCheckBox("Manual Select")
        self.chk_pick.setStyleSheet("color: #d4d4d4; font-size: 11px;")
        self.chk_pick.toggled.connect(lambda on: self._apply_change("pick_format", on))
        r_res.addWidget(self.chk_pick)
        layout.addLayout(r_res)

        r_sl = QHBoxLayout()
        r_sl.addWidget(self._key_label("Streamlink / Sub"))
        self.cb_slq = self._make_combo([
            ("best", "best (auto)"),
            ("1080p60,1080p,best", "1080p60 fallback"),
            ("720p,best", "720p fallback"),
            ("worst", "worst (save data)"),
        ])
        self.cb_slq.currentIndexChanged.connect(
            lambda: self._apply_change("streamlink_quality", self.cb_slq.currentData())
        )
        r_sl.addWidget(self.cb_slq, 2)

        self.cb_sublangs = self._make_combo([
            ("all", "Sub: all"),
            ("ko,en", "Sub: ko+en"),
            ("ko", "Sub: ko"),
            ("en", "Sub: en"),
        ])
        self.cb_sublangs.currentIndexChanged.connect(
            lambda: self._apply_change("subtitle_langs", self.cb_sublangs.currentData())
        )
        r_sl.addWidget(self.cb_sublangs, 1)

        self.cb_frags = self._make_combo([
            (4, "Frag: 4"),
            (1, "Frag: 1"),
            (8, "Frag: 8"),
            (16, "Frag: 16"),
        ])
        self.cb_frags.currentIndexChanged.connect(
            lambda: self._apply_change("concurrent_fragments", self.cb_frags.currentData())
        )
        r_sl.addWidget(self.cb_frags, 1)
        layout.addLayout(r_sl)

        # ── 2. COOKIE & CLIENT ──
        layout.addSpacing(6)
        layout.addWidget(self._sec_header("COOKIE & CLIENT"))
        layout.addWidget(self._tui_sep())

        r_cookie = QHBoxLayout()
        r_cookie.addWidget(self._key_label("Cookie Source"))
        self.lbl_cookie_status = QLabel(self._cookie_status_text())
        self.lbl_cookie_status.setStyleSheet("color: #ce9178; font-size: 11px;")
        r_cookie.addWidget(self.lbl_cookie_status, 1)

        self.cookie_buttons = []
        for text, func in [("View", self.view_cookie), ("Load", self.load_cookie), ("Reset", self.reset_cookie)]:
            btn = QPushButton(f"[ {text} ]")
            btn.setStyleSheet(theme.TUI_STYLE)
            btn.setProperty("class", "tui-tag")
            btn.clicked.connect(func)
            self.cookie_buttons.append(btn)
            r_cookie.addWidget(btn)
        layout.addLayout(r_cookie)

        r_client = QHBoxLayout()
        r_client.addWidget(self._key_label("YT Player Client"))
        self.cb_yt_client = self._make_combo([
            ("auto", "auto (default)"),
            ("tv", "tv (age-gated safe)"),
            ("web_safari", "web_safari"),
            ("tv_simply", "tv_simply"),
            ("mweb", "mweb"),
        ])
        self.cb_yt_client.currentIndexChanged.connect(
            lambda: self._apply_change("yt_player_client", self.cb_yt_client.currentData())
        )
        r_client.addWidget(self.cb_yt_client, 1)
        layout.addLayout(r_client)

        # ── 3. DOWNLOAD OPTIONS ──
        layout.addSpacing(6)
        layout.addWidget(self._sec_header("DOWNLOAD OPTIONS"))
        layout.addWidget(self._tui_sep())

        self.chk_sub = QCheckBox("Embed subtitles (SRT auto-convert + merge)")
        self.chk_thumb = QCheckBox("Embed thumbnail (cover art)")
        self.chk_chapters = QCheckBox("Embed chapters + metadata")
        self.chk_audio = QCheckBox("Audio only (extract MP3)")
        self.chk_dedup = QCheckBox("Auto-remove duplicate URLs")
        self.chk_fast = QCheckBox("Fast segmented download (multi-thread)")
        self.chk_auto_open = QCheckBox("Open download folder on finish")
        self.chk_sound = QCheckBox("Play notification sound on complete")

        self.chk_sub.toggled.connect(lambda v: self._apply_change("embed_subtitles", v))
        self.chk_thumb.toggled.connect(lambda v: self._apply_change("embed_thumbnail", v))
        self.chk_chapters.toggled.connect(lambda v: self._apply_change("embed_chapters", v))
        self.chk_audio.toggled.connect(self._on_audio_only_toggled)
        self.chk_dedup.toggled.connect(lambda v: self._apply_change("remove_duplicates", v))
        self.chk_fast.toggled.connect(lambda v: self._apply_change("fast_download", v))
        self.chk_auto_open.toggled.connect(lambda v: self._apply_change("auto_open_folder", v))
        self.chk_sound.toggled.connect(lambda v: self._apply_change("play_sound", v))

        chk_grid = QHBoxLayout()
        chk_col1 = QVBoxLayout()
        chk_col2 = QVBoxLayout()
        chk_col1.setSpacing(6)
        chk_col2.setSpacing(6)

        for w in [self.chk_sub, self.chk_thumb, self.chk_chapters, self.chk_audio]:
            w.setStyleSheet("color: #d4d4d4; font-size: 11px;")
            chk_col1.addWidget(w)

        for w in [self.chk_dedup, self.chk_fast, self.chk_auto_open, self.chk_sound]:
            w.setStyleSheet("color: #d4d4d4; font-size: 11px;")
            chk_col2.addWidget(w)

        chk_grid.addLayout(chk_col1)
        chk_grid.addSpacing(14)
        chk_grid.addLayout(chk_col2)
        layout.addLayout(chk_grid)

        # ── 4. AUTOMATION & UPDATE ──
        layout.addSpacing(6)
        layout.addWidget(self._sec_header("AUTOMATION & UPDATE"))
        layout.addWidget(self._tui_sep())

        r_comp = QHBoxLayout()
        r_comp.addWidget(self._key_label("Post-Action"))
        self.cb_completion = self._make_combo([
            ("none", "None (Idle)"),
            ("sleep", "Enter Sleep Mode"),
            ("shutdown", "Shutdown Computer"),
            ("exit_app", "Exit Program"),
        ])
        self.cb_completion.currentIndexChanged.connect(
            lambda: self._apply_change("completion_action", self.cb_completion.currentData())
        )
        r_comp.addWidget(self.cb_completion, 1)
        layout.addLayout(r_comp)

        r_upd = QHBoxLayout()
        r_upd.addWidget(self._key_label("Update Channel"))
        self.cb_update_channel = self._make_combo([
            ("stable", "Stable (Release)"),
            ("nightly", "Nightly (Latest bypass)"),
        ])
        self.cb_update_channel.currentIndexChanged.connect(
            lambda: self._apply_change("update_channel", self.cb_update_channel.currentData())
        )
        r_upd.addWidget(self.cb_update_channel, 1)

        self.chk_auto_update = QCheckBox("Check updates on launch")
        self.chk_auto_update.setStyleSheet("color: #d4d4d4; font-size: 11px;")
        self.chk_auto_update.toggled.connect(lambda on: self._apply_change("auto_update_check", on))
        r_upd.addWidget(self.chk_auto_update)
        layout.addLayout(r_upd)

        # ── 5. FILENAME TEMPLATE ──
        layout.addSpacing(6)
        layout.addWidget(self._sec_header("FILENAME TEMPLATE"))
        layout.addWidget(self._tui_sep())

        r_fn = QHBoxLayout()
        r_fn.addWidget(self._key_label("Pattern"))
        self.cb_prefix = self._make_combo([
            ("none", "Prefix: None"),
            ("uploader", "Prefix: [Channel]"),
            ("date_dash_uploader", "Prefix: YYYY-MM-DD [Channel]"),
            ("date_compact_uploader", "Prefix: YYYYMMDD [Channel]"),
            ("date_dash", "Prefix: YYYY-MM-DD"),
            ("date_compact", "Prefix: YYYYMMDD"),
        ])
        self.cb_prefix.currentIndexChanged.connect(
            lambda: self._apply_change("filename_prefix", self.cb_prefix.currentData())
        )
        r_fn.addWidget(self.cb_prefix, 2)

        self.cb_suffix = self._make_combo([
            ("id_res_fps", "Suffix: [ID] [Res] [fps]"),
            ("id_res", "Suffix: [ID] [Res]"),
            ("id", "Suffix: [ID]"),
        ])
        self.cb_suffix.currentIndexChanged.connect(
            lambda: self._apply_change("filename_suffix", self.cb_suffix.currentData())
        )
        r_fn.addWidget(self.cb_suffix, 2)
        layout.addLayout(r_fn)

        self.lbl_filename_preview = QLabel("Preview : title.mp4")
        self.lbl_filename_preview.setStyleSheet("color: #4ec9b0; font-size: 11px; padding-left: 120px;")
        layout.addWidget(self.lbl_filename_preview)

        self.cb_prefix.currentIndexChanged.connect(self.update_filename_preview)
        self.cb_suffix.currentIndexChanged.connect(self.update_filename_preview)
        self.cb_container.currentIndexChanged.connect(self.update_filename_preview)

        layout.addStretch()

        # 2. 하단 고정 풋터 액션 바
        outer.addWidget(self._tui_sep())

        footer = QWidget()
        footer.setStyleSheet("background-color: #0d0d0d;")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(18, 8, 18, 10)
        footer_layout.addStretch()

        btn_done = QPushButton("[ Close: Esc ]")
        btn_done.setProperty("class", "tui-tag")
        btn_done.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_done.clicked.connect(self.close)
        footer_layout.addWidget(btn_done)

        outer.addWidget(footer)

    # ── 비즈니스 로직 & 내부 헬퍼 ──────────────────────────────
    def update_filename_preview(self):
        today = datetime.datetime.now().astimezone()
        date_dash = today.strftime("%Y-%m-%d")
        date_compact = today.strftime("%Y%m%d")

        prefix_map = {
            "none": "",
            "uploader": "[Channel] ",
            "date_dash_uploader": f"{date_dash} [Channel] ",
            "date_compact_uploader": f"{date_compact} [Channel] ",
            "date_dash": f"{date_dash} ",
            "date_compact": f"{date_compact} ",
        }
        suffix_map = {
            "id_res_fps": " [PLCAxEuddBvAs] [1080p] [60fps]",
            "id_res": " [PLCAxEuddBvAs] [1080p]",
            "id": " [PLCAxEuddBvAs]",
        }
        p_text = prefix_map.get(self.cb_prefix.currentData(), "")
        s_text = suffix_map.get(self.cb_suffix.currentData(), "")
        ext = self.cb_container.currentData() or "mp4"
        self.lbl_filename_preview.setText(f"Preview : {p_text}Video_Title{s_text}.{ext}")

    def load_settings(self):
        def set_combo(cb, val):
            idx = cb.findData(val)
            if idx >= 0:
                cb.setCurrentIndex(idx)

        set_combo(self.cb_container, self.cfg.get("container", "mkv"))
        set_combo(self.cb_completion, self.cfg.get("completion_action", "none"))
        set_combo(self.cb_prefix, self.cfg.get("filename_prefix", "none"))
        set_combo(self.cb_suffix, self.cfg.get("filename_suffix", "id"))
        set_combo(self.cb_yt_client, self.cfg.get("yt_player_client", "auto"))
        set_combo(self.cb_update_channel, self.cfg.get("update_channel", "stable"))
        set_combo(self.cb_max_res, self.cfg.get("max_video_res", "none"))
        set_combo(self.cb_slq, self.cfg.get("streamlink_quality", "best"))
        set_combo(self.cb_sublangs, self.cfg.get("subtitle_langs", "all"))
        set_combo(self.cb_frags, self.cfg.get("concurrent_fragments", 4))
        self.chk_pick.setChecked(self.cfg.get("pick_format", False))

        self.chk_sub.setChecked(self.cfg.get("embed_subtitles", False))
        self.chk_thumb.setChecked(self.cfg.get("embed_thumbnail", False))
        self.chk_chapters.setChecked(self.cfg.get("embed_chapters", True))
        self.chk_audio.setChecked(self.cfg.get("audio_only", False))
        self.chk_dedup.setChecked(self.cfg.get("remove_duplicates", True))
        self.chk_fast.setChecked(self.cfg.get("fast_download", True))
        self.chk_auto_open.setChecked(self.cfg.get("auto_open_folder", True))
        self.chk_sound.setChecked(self.cfg.get("play_sound", True))
        self.chk_auto_update.setChecked(self.cfg.get("auto_update_check", True))
        self.update_filename_preview()

    def view_cookie(self):
        cookie_src = self.cfg.get("browser_cookie", "none")
        content = "no cookies loaded."
        if cookie_src == "cookie_file" and os.path.exists(self.cfg.get("cookie_file_path", "")):
            try:
                with open(self.cfg["cookie_file_path"], "r", encoding="utf-8") as f:
                    file_size = os.path.getsize(self.cfg["cookie_file_path"])
                    content = f.read(5000) + ("\n... (truncated)" if file_size > 5000 else "")
            except Exception as ex:  # noqa: BLE001
                content = f"file read error: {ex}"
        elif cookie_src not in ["none", "auto"]:
            try:
                # [교정] 인라인 import get_browser_cookies 제거
                cookie_data = get_browser_cookies()
                if cookie_data:
                    lines = []
                    for host, kv_dict in cookie_data.items():
                        lines.append(f"[{host}]")
                        for k, v in kv_dict.items():
                            lines.append(f"  {k} = {v}")
                        lines.append("")
                    content = f"[{cookie_src}] extracted browser cookies:\n\n" + "\n".join(lines)
                else:
                    content = f"[{cookie_src}] browser returned no cookies (running browser or permission denied)"
            except Exception as ex:  # noqa: BLE001
                content = f"cookie lookup error: {ex}"

        viewer = CookieViewerDialog("Cookie Viewer (details)", content, self)
        viewer.exec()

    def load_cookie(self):
        dlg = CookieSelectDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.cfg["browser_cookie"] = dlg.selected_type
            self.cfg["cookie_file_path"] = dlg.selected_path
            self.save_cfg()
            self._refresh_cookie_status()
            names = {"cookie_file": "Cookies.txt"}
            src_name = names.get(dlg.selected_type, dlg.selected_type)
            notice = TuiNoticeDialog(
                self,
                title="ChzzkTube",
                text=f"\u2713 Cookie configured.\n({src_name})",
                alt_label="View",
            )
            if notice.exec() == TuiNoticeDialog.RESULT_ALT:
                self.view_cookie()

    def reset_cookie(self):
        self.cfg["browser_cookie"] = "none"
        self.cfg["cookie_file_path"] = ""
        self.save_cfg()
        self._refresh_cookie_status()
        show_info_message(self, "Reset", "Cookie cleared.")

    def _cookie_status_text(self):
        src = self.cfg.get("browser_cookie", "none")
        names = {
            "none": "None",
            "auto": "Auto (browser)",
            "cookie_file": "Cookies.txt",
        }
        label = names.get(src, f"Browser ({src})")
        if src == "cookie_file" and self.cfg.get("cookie_file_path"):
            label += f" \u2014 {os.path.basename(self.cfg['cookie_file_path'])}"
        return f"Current: {label}"

    def _refresh_cookie_status(self):
        self.lbl_cookie_status.setText(self._cookie_status_text())

    def _apply_change(self, key, value):
        if getattr(self, "_loading", False):
            return
        self.cfg[key] = value
        self.save_cfg()

    def _on_audio_only_toggled(self, on):
        self._apply_change("audio_only", on)
        self.update_ui_state()


class VerboseLogWindow(QDialog):
    """상세(Full Detailed) 로그 전용 서브 윈도우 — 메인 뷰에서 상세 로그 탭을
    분리해 접근한다(F12). MainWindow가 외부로 유출하는 상세 로그를 그대로
    미러링하며, 항상 하단(최신)을 팔로우한다."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Full Log (F12)")
        self.resize(760, 480)
        self.setStyleSheet(theme.DIALOG_BG_QSS)

        self.te = QTextEdit(self)
        self.te.setReadOnly(True)
        self.te.setStyleSheet(theme.TE_CONTENT_QSS)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        layout.addWidget(self.te)

        btn_row = QHBoxLayout()
        self.lbl_info = QLabel("")
        self.lbl_info.setStyleSheet("color: #888888; font-size: 11px;")
        btn_close = QPushButton("[ Close: Esc ]")
        btn_close.setProperty("class", "tui-tag")
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.setStyleSheet(theme.TUI_STYLE)
        btn_close.clicked.connect(self.close)

        btn_row.addWidget(self.lbl_info)
        btn_row.addStretch(1)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

    def append(self, msg, is_status=False):
        if not msg:
            return
        if is_status:
            cursor = self.te.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock, QTextCursor.MoveMode.KeepAnchor)
            cursor.removeSelectedText()
            cursor.insertText(str(msg))
        else:
            self.te.append(msg)
        sb = self.te.verticalScrollBar()
        sb.setValue(sb.maximum())
        self.lbl_info.setText(f"mirroring — {self.te.document().blockCount()} lines")

    def set_content(self, text):
        self.te.setPlainText(text)
        self.lbl_info.setText(f"buffer — {self.te.document().blockCount()} lines")

```

## File: chzzktube/ui/log_console.py

```python
### log_console.py - 간결 로그 콘솔 렌더러
"""간결 로그 QTextEdit의 렌더링 책임을 MainWindow로부터 분리한 모듈.
상태 줄 덮어쓰기(진행률 갱신), 색상 출력, 작업 구분 여백을 담당하며, MainWindow는 이 모듈에 로그 출력만 위임한다. """
from collections import deque

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QTextEdit

from chzzktube.core.log_emitter import (
    STEMLESS_CONT_WIDTH,
    TREE_TOTAL_WIDTH,
    _flow_lines,
    _wrap_by_width,
)
from chzzktube.ui.theme import (
    LOG_COLOR_ACCENT,
    LOG_COLOR_DIM,
    LOG_COLOR_ERROR,
    LOG_COLOR_INFO,
    LOG_COLOR_STRUCT,
    LOG_COLOR_SUCCESS,
    LOG_COLOR_VALUE,
    LOG_COLOR_WARN,
)


class ConciseLogConsole:
    """간결 로그 패널 전용 렌더러."""

    def __init__(self, text_edit):
        self.te = text_edit
        # 직전 로그가 덮어쓰기용 상태 로그였는지 기록하는 플래그
        self.last_log_was_status = False
        self.last_status_block_count = 1
        # 작업 종료 시 보증한 여백(add_task_separator) — 다음 append가 살린다
        self._pending_blank = False
        # [버그 수정] 상태 블록 제거 직후 플래그 — 다음 메시지가 새 블록에서 시작하도록 보장
        self._just_removed_status = False
        # [핵심] 자동 워드랩 금지 — QTextEdit이 임의로 줄을 접으면 '│' 줄기 없는
        # 침범 줄이 생겨 트리 문법이 파괴된다. 줄바꿈은 format_tree_item의
        # 예산 기반 wrap이 유일해야 하며, 화면 초과분은 가로로 흘러버리는 것을
        # 방지하기 위해 가로 스크롤로 흘린다.
        self.te.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        # [가로 스크롤 금지] 넘치는 내용은 '…' 절단이 처리 — 스크롤바가 생기지 않는다.
        self.te.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # 예산 동기화 캐시 — (뷰포트 폭, 글자 폭)이 바뀐 때만 재계산
        self._budget_key = None
        # [리플로우 대비] 원본 로그 버퍼 — msg는 잘리지 않은 전체를 보관하고,
        # 화면에는 렌더 시점 예산으로 잘라서 그린다. 창 폭 변경 시 재구성 루트.
        self._buffer = deque(maxlen=4096)  # list[dict] = {msg, is_status, is_error, fg_color}

    def _sync_budget(self):
        """로그를 찍는 시점 기준으로 트리 줄바꿈 예산을 재동기화한다.

        init_ui 시점엔 레이아웃이 실행 전이라 뷰포트 폭이 부정확하고,
        스플리터로 콘솔 폭을 조정하면 MainWindow.resizeEvent 자체가
        호출되지 않는다. append 직전에 폭/폰트를 검사해 바뀌었을 때만
        재계산하므로 비용은 사실상 없다.

        [리플로우] 예산이 실제로 바뀌면 _buffer의 원본 로그들을 새 예산으로
        전체 재구성한다 — 창을 가로로 늘리면 기존 로그까지 펼쳐진다.
        """
        self.on_resize()

    def on_resize(self):
        """콘솔 뷰포트 폭/폰트 변화 감시 — 바뀌면 예산 갱신 + 전체 reflow."""
        vp_w = self.te.viewport().width()
        char_w = self.te.fontMetrics().horizontalAdvance(" ")
        key = (vp_w, char_w)
        if key != self._budget_key:
            self._budget_key = key
            update_tree_budget(self.te)
            if self._buffer:
                self.reflow()

    def append(self, msg, is_status=False, is_error=False, fg_color=None, no_wrap=False):
        """빈 줄 생성 차단 및 정밀 문단 삭제 파이프라인.

        [진행률 갱신형 계약] 진행률/진행 중 상태 로그는 반드시 is_status=True로
        호출할 것 — ConciseLogConsole이 직전 상태 블록을 같은 줄에 덮어쓴다
        (Single-Line In-Place Status, HANDOVER §6). is_status=False로 emit하면
        매 틱 새 줄이 쌓여 '한 행 = 한 정보' 규칙을 위반한다. DL/LIVE 틱,
        DEPS 다운로드 %, PO 서버 진행 등 모든 반복 로그가 해당.

        [줄바꿈 계약] 줄바꿈 결정은 발행자(raw() 경유 LogEvent → 구독자) 측의
        no_wrap 플래그를 그대로 따르며, 렌더 레이어에서 문자열 내용을 다시
        뜯어 판단하지 않는다(정규식 라우팅 제로). LogEvent 경유분(컬럼 포맷·
        프리포맷)은 True, 큐 호환용 bare 문자열은 False다.
        """
        self._sync_budget()  # 현재 뷰포트/폰트 기준 예산 보장 — 자동랩 침범 방지
        # [리플로우 대비] 원본 로그를 버퍼에 보관 (렌더 시점 절단을 위해 잘리지 않음)
        self._buffer.append(
            {"msg": msg, "is_status": is_status, "is_error": is_error,
             "fg_color": fg_color, "no_wrap": bool(no_wrap)}
        )
        doc = self.te.document()
        cursor = self.te.textCursor()

        # 0. 바닥 여백용 빈 블록을 치운다 — 새 로그는 항상 내용 위에 붙고,
        #    여백은 삽입 완료 후 다시 깔린다(상시 유지). 직전에 작업 종료
        #    여백이 보증됐다면(add_task_separator) 빈 블록 '한 줄'은 살려
        #    둔다 — 완료 로그와 다음 로그 사이의 한 칸 띄우기.
        keep_blank = self._pending_blank
        self._pending_blank = False
        self._strip_tail_padding(keep_one=keep_blank)

        # 1. 직전 로그가 상태 메시지(is_status=True)였다면 상태 블록을 정리한다.
        #    이때 마지막 블록은 '빈 홈 블록'으로 남긴다 — 상태 줄의 첫 블록을
        #    직전 블록(작업 구분 여백)에 병합하면 여백이 먹혀 중단 로그와
        #    다음 작업 로그가 붙어버리는 문제의 원인이었다.
        if self.last_log_was_status and not doc.isEmpty():
            self._remove_status_blocks()
            self.last_log_was_status = False
            self._just_removed_status = True  # 빈 홈 재사용 좌표 시그널

        # 2. 커서 최하단 이동 (문서가 비어있지 않고 줄 시작점이 아니면 1줄 개행).
        #    커서가 '보증된 여백' 빈 블록 위에 서 있으면 그 블록을 내용으로
        #    채우지 않고 한 줄 더 개행해 여백을 살린다.
        cursor.movePosition(QTextCursor.MoveOperation.End)
        # [핵심] 상태 틱 종료/업데이트 → 빈 홈 블록 시작점으로 재사용(같은 줄)
        #    상태 틱 재사용도 허용(not is_status 한정 X) — 퍼센트 업데이트가
        #    매번 새 줄에 나오는 '붙어나오는 퍼센트 로그' 버그 예방.
        if self._just_removed_status and not doc.isEmpty() and not doc.lastBlock().text():
            cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        on_kept_blank = (
            keep_blank
            and not doc.isEmpty()
            and cursor.atBlockStart()
            and not doc.lastBlock().text()
        )
        # [핵심] 블록 삽입 판정 — Single-Line In-Place Status를 지킨다.
        # 재사용 중(빈 홈 시작점)이면 insertBlock 생략 → 같은 블록에 텍스트 삽입
        reuse_status_home = (
            self._just_removed_status
            and not doc.isEmpty()
            and not doc.lastBlock().text()
            and cursor.atBlockStart()
        )
        if not doc.isEmpty() and not reuse_status_home and (
            not cursor.atBlockStart()
            or on_kept_blank
            or doc.lastBlock().text()
        ):
            cursor.insertBlock()
        self._just_removed_status = False  # 플래그 소비

        clean_msg = msg

        # 3. [핵심] 줄바꿈(\n) 사이에만 insertBlock()을 호출하여 문장 끝 불필요한 빈 줄 생성 완전 차단
        #    비트리 일반 라인(pip 출력 등)은 예산 폭을 넘기면 여기서 wrap한다 —
        #    NoWrap 콘솔에서 화면 초과분이 가로로 흘러버리는 것을 방지.
        #    [리플로우] 렌더 시점 예산으로 msg를 잘라서 그린다 (원본은 버퍼 보존).
        inserted = self._insert_clamped(
            cursor, clean_msg, is_status, is_error, fg_color, bool(no_wrap)
        )

        # 4. 상태 플래그 및 블록 수 기록 — wrap 포함 실제 삽입 블록 수
        self.last_log_was_status = is_status
        self.last_status_block_count = max(1, inserted)

        # 5. 바닥 여백 상시 유지 — 마지막 로그와 콘솔 바닥 사이 2줄 간격
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self._add_tail_padding(cursor)

        self.te.moveCursor(QTextCursor.MoveOperation.End)
        sb = self.te.verticalScrollBar()
        sb.setValue(sb.maximum())

    def add_task_separator(self):
        """하나의 다운로드 작업이 완전히 종료되었을 때만 1줄 여백 추가.

        삽입한 빈 블록은 다음 append of _strip_tail_padding에서 걷히지 않게
        _pending_blank로 보증한다 — '완료 로그 다음 한 칸 띄우기'.
        """
        doc = self.te.document()
        if not doc.isEmpty():
            self._strip_tail_padding()
            cursor = self.te.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            cursor.insertBlock()
            self._add_tail_padding(cursor)
            self.last_log_was_status = False
            self._pending_blank = True

    def clear_status_line(self):
        """남아있는 애니메이션 상태 로그 블록을 깔끔하게 삭제.

        블록 자체는 빈 홈으로 남긴다 — 상태 줄이 차지했던 자리가 원래
        작업 구분 여백이었다면 원상복구되어야 하기 때문이다.
        """
        if self.last_log_was_status:
            self._remove_status_blocks()
            self.last_log_was_status = False
            self._just_removed_status = True

    def _remove_status_blocks(self):
        """상태 로그 블록 last_status_block_count개를 '빈 홈 블록 1개'로 정리.

        블록 경계는 (n-1)개만 병합하고 마지막 블록은 텍스트만 지워 빈 채로
        남긴다. 기존 방식(n회 clear+병합)은 상태 줄의 첫 블록을 직전 블록에
        병합해버려서, 직전 블록이 작업 구분 여백(빈 줄)이면 여백이 먹혔다 —
        '중단 로그 바로 아래에 다음 작업 로그가 붙는' 현상의 원인.
        """
        cursor = self.te.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        for _ in range(max(0, self.last_status_block_count - 1)):
            cursor.movePosition(
                QTextCursor.MoveOperation.StartOfBlock,
                QTextCursor.MoveMode.KeepAnchor,
            )
            cursor.removeSelectedText()
            if not cursor.atStart():
                cursor.deletePreviousChar()
            cursor.movePosition(QTextCursor.MoveOperation.End)
        # 마지막 남은 상태 블록의 텍스트만 제거 (블록/여백은 유지)
        cursor.movePosition(
            QTextCursor.MoveOperation.StartOfBlock,
            QTextCursor.MoveMode.KeepAnchor,
        )
        cursor.removeSelectedText()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        # [버그 수정] 상태 블록 제거 직후 — 다음 append가 새 블록을 삽입하도록 플래그 설정
        self._just_removed_status = True

    def reset_status_flag(self):
        """상태 로그를 히스토리로 확정 보존(덮어쓰기 중단)."""
        self.last_log_was_status = False

    def _render_clamp(self, line):
        """렌더 시점 절단 — 마지막 ' │ ' 이후 msg를 viewport 우측까지 픽셀 정렬.

        원본(msg 전체)은 _buffer에 보존되고, 이 함수는 화면 표시만
        viewport 픽셀 폭에 맞춰 '…'로 자른다. 핵심은 display_width
        (east_asian_width 기반 문자 단위 추정)가 아니라 fontMetrics의
        horizontalAdvance로 *실제 픽셀 폭*을 재는 것이다 — Cascadia Mono는
        한글 2칸·latin 1칸·'│'(U+2502, Ambiguous)는 폰트에 따라 1칸이
        되는 비일관성이 있어, 문자 단위 추론만으로는 짤림 위치가 들쭉날쭉
        해진다. 픽셀 단위 절단으로 폰트/Ambiguous 폭/한영 혼용에 무관하게
        viewport 우측에서 일정하게 끝난다.

        우측에는 RIGHT_PADDING_PX 만큼 가독성 여백을 남긴다 — 글자
        가장자리가 프레임에 붙는 것을 막아 위 압박감을 줄인다.
        """
        fm = self.te.fontMetrics()
        viewport_px = self.te.viewport().width()
        if viewport_px <= 0:
            # 위젯이 아직 실측되지 않은 시점(초기화 직후) — 보수적으로 원본 유지
            return line
        if " │ " not in line:
            # TUI 가 아닌 라인 — viewport 폭에서 우측 패딩을 뺀 만큼 통째로 자른다
            return _truncate_by_pixels(line, viewport_px - RIGHT_PADDING_PX, fm)
        head, _, msg = line.rpartition(" │ ")
        if not head:
            return line
        # head + 마지막 ' │ ' 까지의 실제 픽셀 폭을 잰다 — '│'의 Ambiguous
        # 폭(1칸/2칸)과 Cascadia Mono의 한글/라틴 폭 차이를 그대로 반영한다.
        head_px = fm.horizontalAdvance(head + " │ ")
        msg_budget_px = viewport_px - head_px - RIGHT_PADDING_PX
        return head + " │ " + _truncate_by_pixels(msg, msg_budget_px, fm)

    def _insert_clamped(self, cursor, msg, is_status, is_error, fg_color, no_wrap=False):
        """한 로그(다중 줄 허용)를 렌더 클램프 후 삽입. (삽입 블록 수 반환)

        append와 reflow가 공유하는 유일한 삽입 경로 — 파이프라인 중복 제거.
        no_wrap 플래그를 _flow_lines에 그대로 전달한다.
        """
        inserted = 0
        lines = msg.split("\n")
        for idx, raw in enumerate(lines):
            for f_idx, line in enumerate(_flow_lines(raw, no_wrap)):
                if idx > 0 or f_idx > 0:
                    cursor.insertBlock()
                inserted += 1
                line = self._render_clamp(line)
                if fg_color is not None:
                    fmt = QTextCharFormat()
                    fmt.setFont(self.te.font())
                    fmt.setForeground(QColor(fg_color))
                    cursor.insertText(line, fmt)
                else:
                    for seg, color in _line_segments(line, is_error, is_status):
                        fmt = QTextCharFormat()
                        fmt.setFont(self.te.font())
                        fmt.setForeground(QColor(color))
                        cursor.insertText(seg, fmt)
        return inserted

    def reflow(self):
        """창 폭 변경 시 전체 재렌더링 — 버퍼의 원본 로그를 새 예산으로 다시 그린다.

        상태 로그는 연속 그룹의 마지막 것만 그려 Single-Line In-Place를 유지한다.
        """
        buf = self._buffer
        if not buf:
            return
        self.te.clear()
        self.last_log_was_status = False
        self.last_status_block_count = 1
        self._pending_blank = False
        self._just_removed_status = False

        # 상태 로그 연속 그룹의 마지막만 렌더링 대상으로 추려낸다
        entries = []
        i = 0
        while i < len(buf):
            e = buf[i]
            if e["is_status"]:
                j = i
                while j + 1 < len(buf) and buf[j + 1]["is_status"]:
                    j += 1
                entries.append(buf[j])
                i = j + 1
            else:
                entries.append(e)
                i += 1

        doc = self.te.document()
        cursor = self.te.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        for idx, e in enumerate(entries):
            if idx > 0 or not doc.isEmpty():
                cursor.insertBlock()
            self._insert_clamped(
                cursor, e["msg"], e["is_status"], e["is_error"], e["fg_color"],
                e.get("no_wrap", False),
            )

        # 바닥 여백 상시 유지
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self._add_tail_padding(cursor)

        self.te.moveCursor(QTextCursor.MoveOperation.End)
        sb = self.te.verticalScrollBar()
        sb.setValue(sb.maximum())

    def remove_last_blocks(self, count):
        """마지막 count개 블록을 흔적 없이 제거 (분석 결과 블록 철회용).

        _remove_status_blocks가 '빈 홈'을 남기는 것과 달리 블록 경계까지
        완전히 삭제한다 — '없었던 일'로 만드는 것이 목적. 문서 첫 블록
        (초기 안내문)은 항상 남긴다.
        """
        doc = self.te.document()
        if count <= 0 or doc.isEmpty():
            return
        self._strip_tail_padding()
        count = min(count, doc.blockCount() - 1)
        if count <= 0:
            return
        cursor = self.te.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        for _ in range(count):
            cursor.movePosition(
                QTextCursor.MoveOperation.StartOfBlock,
                QTextCursor.MoveMode.KeepAnchor,
            )
            cursor.removeSelectedText()
            if not cursor.atStart():
                cursor.deletePreviousChar()
            cursor.movePosition(QTextCursor.MoveOperation.End)
        self._add_tail_padding()
        self.last_log_was_status = False

    def _strip_tail_padding(self, keep_one=False):
        """문서 끝의 여백용 빈 블록을 제거한다 (내용 블록이 마지막이 되도록).

        첫 블록은 어떤 경우에도 남긴다 — 문서 전체가 빈 블록뿐일 때는
        그 상태를 유지해야 QTextEdit '빈 문서' 판정(isEmpty)이 유효하기 때문.
        keep_one=True면 내용 블록 바로 뒤의 빈 블록 한 개는 남긴다 —
        작업 종료 시 보증된 여백(add_task_separator)이다.
        """
        doc = self.te.document()
        while doc.blockCount() > 1:
            b = doc.lastBlock()
            if b.text():
                break
            cursor = self.te.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            cursor.movePosition(
                QTextCursor.MoveOperation.StartOfBlock,
                QTextCursor.MoveMode.KeepAnchor,
            )
            cursor.removeSelectedText()
            if not cursor.atStart():
                cursor.deletePreviousChar()
        # keep_one — 마지막 내용 블록 바로 뒤 of 빈 블록 '한 개'를 보증한다.
        # (strip은 문서 앞쪽 크기와 무관하게 전부 걷으므로, 보증은 재삽입으로)
        if keep_one and not doc.isEmpty():
            b = doc.lastBlock()
            if b.text():
                cursor = self.te.textCursor()
                cursor.movePosition(QTextCursor.MoveOperation.End)
                cursor.insertBlock()

    def _add_tail_padding(self, cursor=None):
        """콘솔 바닥에 2줄 여백을 깐다 — 마지막 로그가 테두리에 붙지 않게.

        QSS padding-bottom(정적 여백)과 달리 문서 블록이라 스크롤 범위에
        포함되며, 새 로그 삽입 직전 _strip_tail_padding으로 걷어낸다.
        """
        if cursor is None:
            cursor = self.te.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
        for _ in range(TAIL_PADDING_BLOCKS):
            cursor.insertBlock()

    def last_content_block_text(self):
        """바닥 여백 빈 블록을 건너뛴 마지막 내용 블록의 텍스트.

        setHtml 산출 블록은 줄구분자(U+2028)·공백 꼬리를 가질 수 있어
        toPlainText 기반 문자열과 비교 가능하도록 잘라낸다.
        """
        b = self.te.document().lastBlock()
        while b.isValid() and not b.text():
            b = b.previous()
        return b.text().rstrip("\u2028 \t") if b.isValid() else ""

    def insert_after_ready(self, text):
        """기동 인사줄('[ChzzkTube vX.Y.Z] by Miorine') 바로 다음 줄에 로그를 삽입."""
        self._sync_budget()
        b = self.te.document().lastBlock()
        for _ in range(4):
            if not b.isValid():
                break
            t = b.text()
            if "by Miorine" in t:
                body = t.rstrip("\u2028 \t")
                cursor = QTextCursor(b)
                cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
                cursor.movePosition(
                    QTextCursor.MoveOperation.Right,
                    QTextCursor.MoveMode.MoveAnchor,
                    len(body),
                )
                fmt = QTextCharFormat()
                fmt.setFont(self.te.font())
                # 심볼별 색 — append 파이프라인의 색 위계와 동일하게
                if text.startswith("[v]"):
                    fmt.setForeground(QColor(LOG_COLOR_SUCCESS))
                elif text.startswith("[!]"):
                    fmt.setForeground(QColor(LOG_COLOR_ERROR))
                else:
                    fmt.setForeground(QColor(LOG_COLOR_INFO))
                # 인사줄 '다음 줄'에 새 블록으로 삽입한다(같은 줄 병기 아님).
                # 예산 초과분은 줄기 없는 연속 줄 문법(공백 나열)으로 접지
                # 않으면 NoWrap 콘솔에서 가로로 침범한다.
                chunks = _wrap_by_width(text, TREE_TOTAL_WIDTH)
                joined = "\n" + ("\n" + " " * STEMLESS_CONT_WIDTH).join(chunks)
                cursor.insertText(joined, fmt)
                # 삽입 후 커서가 남아 가로 스크롤을 밀지 않게 원점 복귀
                hsb = self.te.horizontalScrollBar()
                hsb.setValue(0)
                return True
            b = b.previous()
        return False

TAIL_PADDING_BLOCKS = 2  # 콘솔 바닥에 상시 유지하는 여백 빈 블록 수
RIGHT_PADDING_PX = 20  # 픽셀 기반 절단 시 viewport 우측에 남기는 가독성 여백 (한글 1자 너비)


def update_tree_budget(text_edit):
    """콘솔 뷰포트 폭을 글자 폭으로 나눠 트리 줄바꿈 예산을 동적 갱신한다.

    상한(100)을 두지 않는다 — 창을 가로로 늘리면 잘려 보이던 로그가
    유연하게 펼쳐진다. 초과분은 format_log_line의 '…' 절단이 처리한다.
    """
    from chzzktube.core import log_emitter
    char_w = text_edit.fontMetrics().horizontalAdvance(" ")
    if char_w > 0:
        # document margin(8px × 2) + QSS 프레임 여백을 제외한 실제 텍스트 폭
        cols = (text_edit.viewport().width() - 16) // char_w
        log_emitter.TREE_TOTAL_WIDTH = max(40, int(cols))


def _truncate_by_pixels(msg, budget_px, fm):
    """msg를 fontMetrics 기반 *실제 픽셀 폭*으로 절단 — 초과 시 '…' 부착."""
    if budget_px <= 0:
        return "…"
    ellipsis_px = fm.horizontalAdvance("…")
    if budget_px <= ellipsis_px:
        return "…"
    out = []
    for ch in msg:
        candidate = "".join(out) + ch + "…"
        if fm.horizontalAdvance(candidate) > budget_px:
            break
        out.append(ch)
    result = "".join(out)
    if len(result) < len(msg):
        result += "…"
    return result


def _line_segments(line, is_error, is_status=False):
    """간결 로그 한 줄의 색 위계 — 구조는 딤, 값은 화이트, 상태만 액센트."""
    if is_error:
        return [(line, LOG_COLOR_ERROR)]
    if is_status or " | 용량:" in line:
        return [(line, LOG_COLOR_INFO)]
    if line.startswith("[v]"):
        if "PO Token" in line:
            return [(line, LOG_COLOR_VALUE)]
        return [(line, LOG_COLOR_SUCCESS)]
    if line.startswith(("[+]", "[~]")):
        return [(line, LOG_COLOR_INFO)]
    if line[:2] in (" ├", " └"):
        head, sep, tail = line.partition(": ")
        if sep:
            return [(head + sep, LOG_COLOR_STRUCT), (tail, LOG_COLOR_VALUE)]
        return [(line[:2], LOG_COLOR_STRUCT), (line[2:], LOG_COLOR_VALUE)]
    if line[:2] in (" │", "  "):
        # 줄기/들여쓰기 2칸만 딤 — 나머지는 전부 값(화이트)
        return [(line[:2], LOG_COLOR_STRUCT), (line[2:], LOG_COLOR_VALUE)]
    return [(line, LOG_COLOR_VALUE)]


def _log_line_segments(line):
    """컬럼 로그 라인의 색상 — STATUS 기반 단색 분기 (v3.4.0 5폭)."""
    if " │ FAIL " in line or " │ FAIL│" in line or line.rstrip().endswith(" │ FAIL"):
        return [(line, LOG_COLOR_ERROR)]
    if " │ WARN " in line or line.rstrip().endswith(" │ WARN"):
        return [(line, LOG_COLOR_WARN)]
    if " │ ABORT" in line:
        return [(line, LOG_COLOR_WARN)]
    if " │ DONE " in line or " │ OK   " in line or " │ END  " in line or " │ READY" in line:
        return [(line, LOG_COLOR_SUCCESS)]
    if " │ SKIP " in line:
        return [(line, LOG_COLOR_DIM)]
    if " │ RUN  " in line:
        return [(line, LOG_COLOR_ACCENT)]
    return [(line, LOG_COLOR_INFO)]

```

## File: chzzktube/ui/main_window.py

```python
﻿##### main.py - 메인 윈도우 및 앱 실행 진입점
import os
import platform
import re
import sys
import time
from collections import deque

from PySide6.QtCore import (
    QEvent,
    QObject,
    Qt,
    QThread,
    QTimer,
    Signal,
    qInstallMessageHandler,
)
from PySide6.QtGui import QFont, QFontDatabase, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from chzzktube.control.controller import MediaController, _is_valid_url
from chzzktube.control.pot_manager import POTManager
from chzzktube.control.startup_coordinator import StartupCoordinator
from chzzktube.core import config, log_emitter, log_history, raw_log
from chzzktube.core.dl_platform import _dl_platform, _short_platform
from chzzktube.core.log_emitter import emit_component
from chzzktube.core.log_event import LogEvent
from chzzktube.core.media import short_codec
from chzzktube.core.utils import _open_windows_explorer
from chzzktube.core.watchdog import (
    ANALYSIS_TIMEOUT_SEC,
    FALLBACK_GRACE_SEC,
    FALLBACK_TIMEOUT_SEC,
    GATE_TIMEOUT_SEC,
    LivenessWatchdog,
)
from chzzktube.infra.po_client import server_ping
from chzzktube.infra.pylib_bootstrap import bootstrap as _bootstrap
from chzzktube.ui import log_console, theme
from chzzktube.ui.dialogs import DepsProvisioningDialog, ExitConfirmDialog, SettingsDialog, VerboseLogWindow
from chzzktube.workers.update_worker import UpdateWorker

try:
    import winsound
except ImportError:
    winsound = None

# Qt 내부 노이즈 필터링 핸들러
def qt_message_handler(mode, context, message):
    if "must be a top level window" in message:
        return
    sys.stderr.write(message + "\n")


qInstallMessageHandler(qt_message_handler)

# [URL 인식 디바운스] 키 입력(타이핑) 침묵 기준 지연 — "타이핑 끝남"은 미래 입력
# 부재를 감지해야만 알 수 있어 키 입력 경로에선 구조상 필수다.
_ANALYZE_DEBOUNCE_MS = 900
# [벌크 입력 공출화] 붙여넣기·드래그&드롭·TXT 로드는 통째로 들어오므로 즉시 분석.
# 0ms 대신 150ms를 두는 건 프로그램적 다중 setText가 한 프레임에 겹칠 때의 점화 병합용.
_BULK_INPUT_DELAY_MS = 150
# [Followup-4] 폴백 유예 — GUI 블록 등으로 15초 폴백이 체인보다 먼저 만기한 경우
# 1회 유예 후 재판정한다(위양성 폴백 차단).
_FALLBACK_GRACE_MS = int(FALLBACK_GRACE_SEC * 1000)
# [Followup-6] 분석 실패가 봇 체크/PO 토큰 사유인지 판별하는 마커(소문자 비교).
_BOT_CHECK_MARKERS = (
    "sign in to confirm you're not a bot",
    "not a bot",
    "po token",
    "failed to extract any player response",
    "confirm your age",
)


def _needs_pot_retry(err_msg: str) -> bool:
    """[Followup-6] 분석 실패가 봇 체크/PO 토큰 사유인지 — POT 기동 후 1회 재시도 대상."""
    text = (err_msg or "").lower()
    return any(marker in text for marker in _BOT_CHECK_MARKERS)

# [E1 단일화] POT 게이트 판정 — 3곳에 복사되던 판정식을 단일 진실로 통합한다.
# HANDOVER §3 '다운로드 게이트' 상수 목록의 유일한 코드 출처이다.
# [핵심 변경] subscriber_only(멤버십) 제거 — Layer 1/2에서 쿠키+JS솔버로 1080p+ 수급 가능
_POT_AVAIL_GATED = ("needs_auth", "premium_only", "private")


def _needs_pot(info):
    """PO 토큰 필요 여부 — age_limit>0(성인인증)만 필수 게이트.
    
    subscriber_only(멤버십)은 쿠키+EJS 솔버로 Layer 1/2에서 해결하므로
    POT 서버 기동 트리거에서 제외. 봇 체크 감지 시 _needs_pot_retry()가
    별도 처리하여 Layer 3로 라우팅한다.
    """
    if not info:
        return False
    age_limit = info.get("age_limit") or 0
    if age_limit > 0:
        return True
    availability = info.get("availability") or ""
    return isinstance(availability, str) and availability.lower() in _POT_AVAIL_GATED


APP_NAME = config._APP_NAME
APP_VERSION = config._APP_VERSION
BASE_DIR = config.BASE_DIR
CONFIG_DIR = config.CONFIG_DIR
CONFIG_FILE = config.CONFIG_FILE
ICON_PATH = config.ICON_PATH
DEFAULT_CONFIG = config.default_config()


class _GuiLogBridge(QObject):
    """순수 raw_log 백그라운드 스레드 이벤트를 Qt GUI 루프로 안전하게 흡수하는 브리지.

    raw_log의 데몬 dispatcher 스레드는 본 브리지의 Signal.emit만 호출하고,
    슬롯은 QueuedConnection으로 메인 스레드 이벤트 루프에서 실행된다 —
    배경 스레드의 QTextEdit 직접 접근(세그폴트/레이스 원인)을 차단한다.
    raw_log는 표준 라이브러리 기반 순수성을 유지하고, 스레드 경계 책임은
    GUI를 점유한 수신층(main.py)이 진다.
    """

    tui_signal = Signal(object, bool, bool)   # (event, is_status, is_error)
    full_signal = Signal(object, bool)        # (event, is_status)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # [히스토리] 실행 세션 시작 마커 — 이후 모든 구성요소/PO 서버/다운로드 로그 기록
        log_history.session_begin(APP_NAME, APP_VERSION)
        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        self.setMinimumSize(800, 680)
        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))

        self.setStyleSheet(theme.TUI_STYLE)

        self.cfg = self._load_config()

        # 다운로드 + 분석 세션 상태/워커는 컨트롤러가 소유 (ctrl.state 단일 참조)
        self.ctrl = MediaController(self)
        self.extracted_data = {"info": None, "v_list": [], "a_list": []}

                # StartupCoordinator: DEPS/POT/업데이트 시그널을 중앙에서 수신하고 3대 로그에 전파
        # POTManager: POT 서버 수명주기 단일 관리자 (prewarm + gate 통합).
        # 단일 인스턴스 원칙 (HANDOVER §7): 시그널 연결 전 최초 1회만 생성
        self._pot_manager = POTManager()
        self._startup_coord = StartupCoordinator(self._pot_manager, self)
        self._pot_manager.pot_finished.connect(self._on_pot_finished)
        # [v3.8.1] 폴백 타이머 제거로 _on_pot_activity 연결 제거
        # POT 진행은 기동 폴백과 활성 게이트의 생존 시간을 함께 연장한다.
        self._pot_manager.pot_work_tick.connect(self._on_pot_work_tick)
        self._startup_coord.ui_unlocked.connect(self._on_startup_unlocked)

        self.settings_dlg = None
        self.verbose_win = None

        self.analyze_timer = QTimer()
        self.analyze_timer.setSingleShot(True)
        self.analyze_timer.timeout.connect(self.run_analysis)

        # ── 분석 워커 시그널 바인딩 (Controller → View 포워딩) ──
        self.ctrl.analyze_result_ready.connect(self.on_analyze_success)
        self.ctrl.analyze_error_occurred.connect(self.on_analyze_error)

        # POTManager가 서버 수명주기를 담당
        self._startup_completed = False
        self._pending_download = None

        # [워치독] 단일 진실 시간(monotonic) 기반 워치독 인스턴스들.
        # 기동 폴백은 워치독으로 감시하지 않는다 — 만료의 단일 기준은 아래 _fallback_timer.
        self._gate_watchdog = LivenessWatchdog(GATE_TIMEOUT_SEC, 0.0)
        self._analysis_watchdog = LivenessWatchdog(ANALYSIS_TIMEOUT_SEC, 0.0)
        # [Watchdog] 워커의 무페이로드 진행 신호가 분석 워치독 수명을 연장한다.
        # 수명은 스폰 3곳의 명시적 무장에서만 시작되고, 만료 판정·복구·해제는
        # 뷰(_on_analysis_timeout)가 단독 수행한다(만료의 영속 재판정 금지).
        self.ctrl.analyze_activity.connect(self._analysis_watchdog.heartbeat)
        self._analysis_watchdog_active = False

        # 워치독 폴링용 타이머 (1초 주기)
        self._watchdog_poll_timer = QTimer(self)
        self._watchdog_poll_timer.setInterval(1000)
        self._watchdog_poll_timer.timeout.connect(self._poll_watchdogs)

        self.init_ui()

        # 구성요소(yt-dlp/streamlink) 자동 업데이트 확인 — 기동 직후 비동기 1회
        QTimer.singleShot(500, self._start_update_check)

        # [v3.8.1] 폴백 타이머 제거 — deps 수급 실패 시 영구 잠금, 사용자 재시도(ENTER) 대기
        # self._fallback_timer = QTimer(self)
        # self._fallback_timer.setSingleShot(True)
        # self._fallback_timer.timeout.connect(self._force_unlock_input)
        # self._fallback_timer.start(int(FALLBACK_TIMEOUT_SEC * 1000))
        # [정리] 기동 폴백 만료의 단일 기준 — 이 타이머가 유일한 판정자다(폴링
        # 워치독이 같은 만료를 따로 판정해 유예를 끊던 이중 구조 제거).
        # [v3.8.1] 폴백 완전 제거 — deps 수급 완료까지 입력 잠금 유지

        # 게이트 만료는 _gate_watchdog 하나로 판정한다. QTimer는 폴링에만 사용.
        self._gate_watchdog_active = False
        # [Followup-5] DEPS 검사의 실제 FAIL(미설치 등)은 게이트 사유로 승격한다.
        self._deps_failed = []
        # [Followup-6] 봇 체크 실패 시 POT 기동 후 1회 재시도용 상태.
        self._pot_retry_url = None
        self._pot_retry_pending = False
        self._pot_retry_done = set()
        self._watchdog_poll_timer.start()

    def _poll_watchdogs(self):
        """1초마다 워치독 타임아웃을 폴링해 발화 조건 충족 시 처리.

        기동 폴백은 여기서 판정하지 않는다 — 만료의 단일 기준은 _fallback_timer며,
        이중 판정은 Followup-4 유예(재무장 직후 폴링이 유예를 끊는 결함)를 낳았다.
        """
        # 1) 게이트 워치독
        if self._gate_watchdog_active and self._gate_watchdog.check_timeout():
            self._on_gate_timeout()
            return

        # 2) 분석 워치독 — 워커의 activity 신호가 수명을 연장하고,
        #    만료 시 여기서 복구(워커 유기 + FAIL 마감)를 단독 수행한다.
        if self._analysis_watchdog_active and self._analysis_watchdog.check_timeout():
            self._on_analysis_timeout()
            return

    def _platform_of_url(self) -> str:
            """[결함 수리] stop_analysis_anim 호출 대비 URL 플랫폼 축약 기호 추출."""
            url = self.url_input.text().strip()
            return _short_platform(_dl_platform(url))

    def closeEvent(self, event):
        # 1. 최소화 상태 해제 및 Qt 표준 창 활성화
        self.setWindowState(
            self.windowState() & ~Qt.WindowState.WindowMinimized
            | Qt.WindowState.WindowActive
        )
        self.activateWindow()

        is_running = self.ctrl.state.get("running", False)
        
        # 2. 수급 중(UpdateWorker/POTManager) 감지
        is_upgrading = (
            hasattr(self, "update_worker") 
            and self.update_worker is not None 
            and self.update_worker.isRunning()
        )
        is_pot_busy = (
            hasattr(self, "_pot_manager") 
            and self._pot_manager is not None 
            and self._pot_manager.is_busy()
        )

        parent_dlg = (
            self.settings_dlg
            if (hasattr(self, "settings_dlg")
                and self.settings_dlg
                and self.settings_dlg.isVisible())
            else self
        )

        # 수급 중이면 전용 다이얼로그 표시
        if is_upgrading or is_pot_busy:
            dlg = DepsProvisioningDialog(
                parent_dlg, 
                is_upgrading=is_upgrading, 
                is_pot_busy=is_pot_busy
            )
        else:
            dlg = ExitConfirmDialog(parent_dlg, is_running=is_running)

        # 3. [소리 복구 & 반짝임] Windows 시스템 알림 음(Beep) 재생 및 작업 표시줄 알림
        if platform.system() == "Windows":
            self._flash_dialog(dlg, winsound)

        result = dlg.exec()

        # [종료] 클릭 시 -> 스레드 안전 중단 후 즉시 종료
        if result == 1:
            # 수급 중 강제 종료 시 협조적 취소 요청
            if is_upgrading and hasattr(self, "update_worker") and self.update_worker is not None:
                self.update_worker.cancel()
            if is_pot_busy and hasattr(self, "_pot_manager") and self._pot_manager is not None:
                self._pot_manager.cancel()

            if hasattr(self, "settings_dlg") and self.settings_dlg:
                self.settings_dlg.close()
            if getattr(self, "verbose_win", None) is not None:
                self.verbose_win.close()
            self.ctrl.shutdown(1000)
            if self.ctrl.worker_dl is not None and self.ctrl.worker_dl.isRunning():
                raw_log.raw(
                    "shutdown",
                    LogEvent(
                        stage="SYS", status="WARN",
                        msg="shutdown: download worker not stopped (1s) — cancelling then exiting",
                        is_error=False,
                    ),
                    to_tui=False,
                )
            # [스레드 경계] 종료 전 러닝 QThread 회수 — 좀비 분석 워커/기동 워커가
            # 살아있으면 Qt가 "QThread: Destroyed while thread is still running"
            # 경고와 함께 종료 크래시를 낼 수 있다. terminate 금지 원칙 유지,
            # 짧은 wait만 시도 (워커들은 취소 플래그로 자연 종료를 약속받는다).
            for w in list(getattr(self, "_zombie_workers", []) or []):
                if w is not None and w.isRunning():
                    w.wait(1500)
                    if w.isRunning():
                        raw_log.raw(
                            "shutdown",
                            LogEvent(
                                stage="SYS",
                                status="WARN",
                                msg="shutdown: orphaned analyze worker (1.5s) — forcing exit",
                                is_error=False,
                            ),
                            to_tui=False,
                        )
            # POTManager가 서버/워커 정리 담당
            self._pot_manager.cancel()

            for name in ("update_worker",):
                w = getattr(self, name, None)
                if w is not None and w.isRunning():
                    w.wait(1500)
                    if w.isRunning():
                        raw_log.raw(
                            "shutdown",
                            LogEvent(
                                stage="SYS",
                                status="WARN",
                                msg=f"shutdown: startup worker ({name}) not stopped (1.5s) — forcing exit",
                                is_error=False,
                            ),
                            to_tui=False,
                        )

            # 다운로드 워커의 라이브 녹화 프로세스 정리
            if hasattr(self.ctrl, "worker_dl") and self.ctrl.worker_dl is not None:
                try:
                    if hasattr(self.ctrl.worker_dl, "kill_live_process"):
                        self.ctrl.worker_dl.kill_live_process()
                except OSError:
                    pass

            # 프로비저닝 아티팩트 정리 (종료 시)
            import chzzktube.infra.cleanup as _cleanup
            _cleanup.cleanup_on_shutdown()

            log_history.session_end()
            raw_log.flush()
            raw_log.shutdown()
            event.accept()

        # [취소] 클릭 시 -> 창 닫기 취소
        else:
            event.ignore()

    @staticmethod
    def _flash_dialog(dlg, winsound):
        """Windows에서 종료 확인 대화상자에 알림음 발생 + 작업 표시줄 반짝임."""
        from chzzktube.infra.platform import flash_window, play_beep

        play_beep()
        hwnd = int(dlg.winId())
        flash_window(hwnd)

    def save_cfg(self):
        config.save_config(self.cfg)

    def _load_config(self):
        """설정 로드 (기본값 + 기존 설정 병합). 상세 로직은 config 모듈에 위임."""
        return config.load_config()

    def init_ui(self):
        """[4단계] Blank Slate — setup_ui()로 위임."""
        self.setup_ui()

    def setup_ui(self):
        """[TUI Refactor] Hyper-Minimal Modern TUI — flat, borderless, mono.

        ├── Path ...  │ [F1] [F2] │ [F12] [F3]
        ├── ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─
        │ > [url_input..........................] [F4] [ENTER]
        ├── ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─
        └── [10:54:14] DEPS  │ OK  │ ...        ← console (stretch=1)
        """
        # ── 중앙 위젯 / 메인 레이아웃 (flat, no master wrapper) ──
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(12, 8, 12, 8)
        main_layout.setSpacing(0)

        # ── 헬퍼: tui-tag 클래스 버튼 ──
        def _tui_tag(text, tooltip, slot):
            b = QPushButton(text)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(slot)
            b.setToolTip(tooltip)
            b.setProperty("class", "tui-tag")
            b.style().unpolish(b)
            b.style().polish(b)
            return b

        # ── 헬퍼: 힌트 버튼 사이 딤 '│' 구분자 ──
        def _tui_sep():
            sep = QLabel("│")
            sep.setStyleSheet(
                f"color: {theme.FG_DIM}; border: none; background: transparent; padding: 0px;"
            )
            return sep

        # ── 헬퍼: 1px 섹션 구분선 ──
        def _separator():
            line = QFrame()
            line.setProperty("class", "tui-separator")
            line.setFrameShape(QFrame.Shape.HLine)
            line.setFrameShadow(QFrame.Shadow.Plain)
            line.setStyleSheet("QFrame { background-color: #1a1a1a; max-height: 1px; min-height: 1px; border: none; }")
            line.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            return line

        # ════════════════════════════════════════════════════════════════════
        # Layer 1: Configuration (flat — no border, no title)
        # ════════════════════════════════════════════════════════════════════
        self.header_group = QGroupBox("")
        self.header_group.setObjectName("header_group")
        self.header_group.setProperty("class", "tui-panel")
        self.header_group.style().unpolish(self.header_group)
        self.header_group.style().polish(self.header_group)
        hlay = QHBoxLayout(self.header_group)
        hlay.setContentsMargins(0, 0, 0, 0)
        hlay.setSpacing(6)

        self.path_label = QLabel()
        self.path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.path_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._update_path_label()
        hlay.addWidget(self.path_label, 1)

        self.btn_change = _tui_tag("[ F1: Change ]", "Change download folder (F1)", self.change_folder)
        self.btn_open = _tui_tag(
            "[ F2: Open ]",
            "Open download folder (F2)",
            lambda: _open_windows_explorer(self.cfg["download_path"]),
        )
        hlay.addWidget(self.btn_change)
        hlay.addWidget(self.btn_open)

        # v_line: Change/Open과 Full Log/Settings 그룹 사이 시각 구분
        self.v_line = QLabel("\u2502")
        self.v_line.setProperty("class", "tui-sep")
        hlay.addWidget(self.v_line)

        self.btn_full_log = _tui_tag("[ F12: Full Log ]", "Toggle full log window (F12)", self.toggle_verbose_log)
        self.btn_settings = _tui_tag("[ F3: Settings ]", "Open settings (F3)", self.open_settings)
        hlay.addWidget(self.btn_full_log)
        hlay.addWidget(self.btn_settings)

        main_layout.addWidget(self.header_group)

        # ── 1px 구분선 ──
        main_layout.addWidget(_separator())

        # ════════════════════════════════════════════════════════════════════
        # Layer 2: Input & Action (flat — no border, prompt-style)
        # ════════════════════════════════════════════════════════════════════
        self.input_group = QGroupBox("")
        self.input_group.setObjectName("input_group")
        self.input_group.setProperty("class", "tui-panel")
        self.input_group.style().unpolish(self.input_group)
        self.input_group.style().polish(self.input_group)
        ilay = QHBoxLayout(self.input_group)
        ilay.setContentsMargins(0, 0, 0, 0)
        ilay.setSpacing(6)

        # 프롬프트 `>` 기호 — 콘솔 출력처럼 보이게
        self.prompt_label = QLabel(">")
        self.prompt_label.setStyleSheet(
            "color: #4ec9b0;font-weight: bold; border: none; background: transparent; padding: 0px;")
        ilay.addWidget(self.prompt_label)

        self.url_input = QLineEdit()
        self.url_input.setObjectName("url_input")
        self.url_input.setPlaceholderText("URL, playlist, or channel URL...")
        self.url_input.setClearButtonEnabled(False)
        self.url_input.installEventFilter(self)
        self.url_input.textChanged.connect(self.on_url_changed)
        self.url_input.setDragEnabled(True)
        self.url_input.acceptDrops()
        self.url_input.dropEvent = lambda e: self._on_url_drop(e.mimeData())
        self.url_input.returnPressed.connect(self.toggle_download)
        ilay.addWidget(self.url_input, 1)

        self.btn_txt = _tui_tag("[ F4: Load .txt ]", "Load URL list from TXT (F4)", self.pick_txt)
        ilay.addWidget(self.btn_txt)
        ilay.addWidget(_tui_sep())

        self.btn_enter = _tui_tag("[ ENTER: Start ]", "Start download (Enter)", self.toggle_download)
        self.btn_esc = _tui_tag("[ ESC: Clear ]", "Clear input (Esc) — abort when running", self._esc_action)
        ilay.addWidget(self.btn_esc)
        ilay.addWidget(_tui_sep())
        ilay.addWidget(self.btn_enter)

        main_layout.addWidget(self.input_group)
        main_layout.addWidget(_separator())

        # Layer 3: Live Console Monitor
        self.console_group = QGroupBox("")
        self.console_group.setObjectName("console_group")
        self.console_group.setProperty("class", "tui-panel")
        self.console_group.style().unpolish(self.console_group)
        self.console_group.style().polish(self.console_group)
        self.console_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        clay = QVBoxLayout(self.console_group)
        clay.setContentsMargins(0, 0, 0, 0)
        clay.setSpacing(0)

        self.te_concise = QTextEdit()
        self.te_concise.setObjectName("console_log")
        self.te_concise.setReadOnly(True)
        self.te_concise.document().setDocumentMargin(0)
        self.console = log_console.ConciseLogConsole(self.te_concise)

        clay.addWidget(self.te_concise, 1)
        main_layout.addWidget(self.console_group, stretch=1)

        self._full_log_buf: deque[str] = deque(maxlen=4096)
        self._full_log_win_n = 0
        self._last_status_line = ""

        self._gui_bridge = _GuiLogBridge(self)
        self._gui_bridge.tui_signal.connect(self._render_concise, Qt.ConnectionType.QueuedConnection)
        self._gui_bridge.full_signal.connect(self._mirror_event_full, Qt.ConnectionType.QueuedConnection)

        raw_log.subscribe_concise(self._gui_bridge.tui_signal.emit)
        raw_log.subscribe_full(self._gui_bridge.full_signal.emit)
        self.update_ui_state()

    def _on_url_drop(self, mime_data):
        """드래그드롭된 .txt 파일 URL 자동 추출."""
        if not mime_data.hasUrls():
            return
        for url in mime_data.urls():
            path = url.toLocalFile()
            if path.lower().endswith(".txt"):
                self.pick_txt_from_path(path)
                return
            if path.startswith(("http://", "https://")):
                self.url_input.setText(path)
                return

    def pick_txt_from_path(self, path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = [l.strip() for l in f if l.strip() and not l.strip().startswith("#")]
            if lines:
                self.url_input.setText("\n".join(lines))
                self.append_concise_log(
                    log_emitter.emit_event("SYS", "OK", "MAIN", f"TXT — {len(lines)} URLs"),
                    is_status=False,
                    is_error=False,
                )
        except OSError:
            self.append_concise_log(
                log_emitter.emit_event("SYS", "FAIL", "MAIN", "TXT read fail"),
                is_status=False,
                is_error=True,
            )

    def abort_download(self):
        if self.ctrl.running:
            self.ctrl.request_cancel()
            self.append_concise_log(
                log_emitter.emit_event("DL", "ABORT", "-", "download canceled by user"),
                is_status=False,
                is_error=True,
            )

    def _esc_action(self):
        state = self.get_current_app_state()
        if state == "RUNNING":
            self.abort_download()
        elif state == "PICKING":
            self._cancel_pick()
        elif state == "ANALYZING":
            self._disarm_analysis_watchdog()

            self.ctrl.request_cancel()
        else:
            self.url_input.clear()

    def eventFilter(self, obj, event):
        if (
            obj is self.url_input
            and event.type() == QEvent.Type.KeyPress
            and event.key() == Qt.Key.Key_Escape
        ):
            self._esc_action()
            return True
        return super().eventFilter(obj, event)

    def _update_path_label(self):
        path = self.cfg.get("download_path", "")
        self.path_label.setText(
            f"<span style='color:#4ec9b0; font-weight:bold;'>Path</span> {path}"
        )

    def change_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select Download Folder", self.cfg["download_path"]
        )
        if folder:
            self.cfg["download_path"] = os.path.normpath(folder)
            self._update_path_label()
            self.save_cfg()
            self.append_concise_log(
                log_emitter.emit_event("SYS", "OK", "CFG", f"path → {self.cfg['download_path']}"),
                is_status=False,
                is_error=False,
            )

    def format_target_url(self, url, max_len=50):
        return log_emitter.format_target_url(url, max_len)

    def open_settings(self):
        if hasattr(self, "settings_dlg") and self.settings_dlg and self.settings_dlg.isVisible():
            self.settings_dlg.activateWindow()
            return
        self.settings_dlg = SettingsDialog(self)
        self.settings_dlg.show()

    def pick_txt(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select TXT File",
            self.cfg["download_path"],
            "Text Files (*.txt);;All Files (*.*)",
        )
        if path:
            self.url_input.setText(os.path.normpath(path))

    def on_url_changed(self):
        self.analyze_timer.stop()
        text = self.url_input.text().strip()

        if not text:
            self._last_input_len = 0
            self.extracted_data = {"info": None, "v_list": [], "a_list": []}
            self._disarm_analysis_watchdog()
            self.ctrl.abandon_analysis()
            self.console.clear_status_line()
            self._discard_analysis_result()
            return

        prev_len = getattr(self, "_last_input_len", 0)
        self._last_input_len = len(text)
        is_bulk_input = (len(text) - prev_len) > 1

        is_idle_state = not self.ctrl.running and not self.ctrl.picking
        is_valid_pattern = "://" in text or bool(re.search(r"\S\.\S", text))

        if is_idle_state and getattr(self, "_startup_completed", False) and is_valid_pattern:
            delay = _BULK_INPUT_DELAY_MS if is_bulk_input else _ANALYZE_DEBOUNCE_MS
            self.analyze_timer.start(delay)

    def _ensure_pot_for_info(self, info):
        info = info or {}
        needs_pot = _needs_pot(info)
        age_limit = info.get("age_limit") or 0
        availability = info.get("availability") or ""

        event = LogEvent(
            stage="POT",
            status="RUN",
            scope="POT",
            msg=f"gated={needs_pot} age_limit={age_limit if info else '-'} availability={availability or '-'}",
        )
        raw_log.raw("pot-gate", event, to_tui=True)

        if needs_pot:
            self.append_concise_log(
                log_emitter.emit_event("POT", "RUN", "POT", "starting..."),
                is_status=True,
                is_error=False,
            )
            self._pot_manager.ensure_ready("gate")
            self._start_gate_watchdog()

    def _preflight_deps_check(self) -> bool:
        """런타임 deps 무결성 사전 체크 — 실패 시 사용자 알림 후 False 반환."""
        from chzzktube.infra.updater import verify_deps_integrity
        ok, missing = verify_deps_integrity()
        if not ok:
            self.append_concise_log(
                log_emitter.emit_event("DEPS", "FAIL", "DEPS", f"deps missing: {', '.join(missing)}"),
                False,
                True,
            )
            try:
                from chzzktube.ui.dialogs import TuiNoticeDialog
                from PySide6.QtWidgets import QWidget
                # 부모가 유효한 QWidget인지 확인 (테스트 mock 환경 방지)
                if isinstance(self, QWidget):
                    TuiNoticeDialog(
                        self,
                        title="ChzzkTube",
                        text=f"missing dependencies:\n{', '.join(missing)}\nrestart to auto-provision",
                        ok_label="OK",
                    ).exec()
            except Exception:
                pass
            return False
        return True

    def run_analysis(self):
        url = self.url_input.text().strip()
        if not url:
            return
        if not self._preflight_deps_check():
            return
        self.append_concise_log(
            log_emitter.emit_event("ANAL", "RUN", "YT", "analyzing..."),
            is_status=True,
            is_error=False,
        )
        self._discard_analysis_result()
        self.base_anim_url = url
        self._arm_analysis_watchdog()
        self.ctrl.spawn_analyzer(url, self.cfg)
        self.update_ui_state()

    def stop_analysis_anim(self, ok=True):
        if not ok:
            return

        data = self.extracted_data or {}
        info = data.get("info") or {}
        v_list = data.get("v_list", [])
        a_list = data.get("a_list", [])
        uploader = (
            info.get("uploader")
            or info.get("channel")
            or info.get("uploader_id")
            or info.get("creator")
            or ""
        )
        title = info.get("title") or data.get("title") or ""
        meta = " · ".join(x for x in (uploader, title) if x)

        v_first = v_list[0] if v_list else {}
        res = ""
        if isinstance(v_first, dict):
            h = v_first.get("height") or v_first.get("v_height") or 0
            fps = v_first.get("fps") or v_first.get("v_fps") or 0
            if h:
                res = f"{h}p{fps}" if fps else f"{h}p"

        # [v3.8.0 Hyper-Minimalist TUI] ANAL 마감 정갈 명세:
        #   1) RUN  complete 라인            — analyzing complete!
        #   2) OK   제목 · 채널              — [제목] · [채널명]
        #   3) OK   가용성(public/member 등) — POT 스코프
        #   4) OK   대표 포맷(코덱)          — streams isolated
        availability = str(info.get("availability") or "").strip() or "-"
        platform_tag = self._platform_of_url()
        raw_log.raw(
            "anal",
            LogEvent(
                stage="ANAL", status="RUN", scope=platform_tag,
                msg=log_emitter.analysis_done_msg(), is_status=True, is_error=False,
            ),
            to_tui=True,
        )
        meta_msg = f"[{title}] · {uploader}" if (title and uploader) else (title or uploader or "unknown")
        raw_log.raw(
            "anal",
            LogEvent(
                stage="ANAL", status="OK", scope=platform_tag,
                msg=meta_msg, is_error=False,
            ),
            to_tui=True,
        )
        raw_log.raw(
            "anal",
            LogEvent(
                stage="ANAL", status="OK", scope="POT",
                msg=f"[{availability}]", is_error=False,
            ),
            to_tui=True,
        )

        self._analysis_block_active = True
        self._analysis_block_count = self.console.last_status_block_count
        self._analysis_last_line = self.console.last_content_block_text()

        self._emit_format_logs(v_list, a_list, platform_tag)

    def _emit_format_logs(self, v_list, a_list, platform_tag):
        # [v3.8.0 Hyper-Minimalist TUI] ANAL 마감 4행 명세의 4번째 행 —
        # 비디오/오디오 대표 코덱을 지시서 형식([codec] · [codec])으로 1줄 발행.
        v_seen = list(dict.fromkeys(short_codec(f.get("vcodec")) for f in v_list if f.get("vcodec")))
        a_seen = list(dict.fromkeys(short_codec(f.get("acodec")) for f in a_list if f.get("acodec")))
        parts = [f"[{c}]" for c in v_seen[:1] + a_seen[:1] if c]
        if not parts:
            return
        raw_log.raw(
            "anal",
            LogEvent(
                stage="ANAL",
                status="OK",
                scope=platform_tag,
                msg=" · ".join(parts),
            ),
            to_tui=True,
        )

    def _format_analysis_summary(self):
        data = self.extracted_data or {}
        info = data.get("info") or {}
        uploader = (
            info.get("uploader")
            or info.get("channel")
            or info.get("uploader_id")
            or info.get("creator")
            or ""
        )
        title = info.get("title") or data.get("title") or ""
        meta = " · ".join(x for x in (uploader, title) if x)
        if not meta:
            return ""
        return " — " + meta[:80]

    def _discard_analysis_result(self):
        if not getattr(self, "_analysis_block_active", False):
            return
        last_text = self.console.last_content_block_text()
        if last_text != getattr(self, "_analysis_last_line", None):
            self._analysis_block_active = False
            return
        self.console.remove_last_blocks(getattr(self, "_analysis_block_count", 0))
        self._analysis_block_active = False

    def _retire_qthread(self, worker):
        if worker is None:
            return
        retired = getattr(self, "_retired_workers", None)
        if retired is None:
            retired = []
            self._retired_workers = retired
        if worker.isFinished() or worker in retired:
            return
        worker.finished.connect(worker.deleteLater)
        worker.finished.connect(lambda w=worker: self._drop_retired(w))
        retired.append(worker)

    def _drop_retired(self, worker):
        retired = getattr(self, "_retired_workers", [])
        try:
            retired.remove(worker)
        except ValueError:
            pass

    def _start_update_check(self):
        if hasattr(self, "update_worker"):
            self._retire_qthread(self.update_worker)
        self.update_worker = UpdateWorker(
            self,
            upgrade=False,
            channel=self.cfg.get("update_channel", "stable"),
            check_updates=self.cfg.get("auto_update_check", True),
        )
        self.update_worker.check_done.connect(self._on_update_check_done)
        # [Followup-5] DEPS 검사 FAIL 목록 — 게이트 판정에 반영
        self.update_worker.deps_failed.connect(self._on_deps_failed)
        self.update_worker.start(QThread.Priority.LowPriority)

    def _on_update_check_done(self, stale):
        if stale:
            summary = ", ".join(f"{label} {cur}→{latest}" for label, _, cur, latest in stale)
            self.append_concise_log(
                log_emitter.emit_event("DEPS", "WARN", "-", f"update — {summary}"),
                is_status=False,
                is_error=False,
            )
            self._stale_updates = True
        else:
            self._stale_updates = False
            self.append_concise_log(
                log_emitter.emit_event("DEPS", "OK", "-", "deps ok"),
                is_status=False,
                is_error=False,
            )

        self._retire_qthread(self.update_worker)
        self.update_worker = UpdateWorker(
            self,
            upgrade=True,
            stale_updates=stale,
            channel=self.cfg.get("update_channel", "stable"),
            check_updates=self.cfg.get("auto_update_check", True),
        )
        self.update_worker.upgrade_done.connect(self._startup_coord.report_upgrade)
        # [P5] 수급 진행 하트비트 → 폴백 타이머 연장
        self.update_worker.start()
        # [P1] deps 게이트의 의미는 "검사 단계 완료"다 — stale(업데이트 대상) 존재는 게이트 사유가 아니다.
        # 업데이트 적용은 업데이트 워커의 일이며, READY 게이트를 막으면 안 된다.
        # (stale 발생 시 deps_ok=False로 잠겨, 업데이트가 감지되는 모든 기동이 정상
        #  READY 대신 15초 폴백 문구로만 열리는 구조적 결함이 있었다.)
        # [Followup-5] 실제 FAIL(미설치/미발견)은 게이트 사유로 승격한다.
        if getattr(self, "_deps_failed", []):
            self._startup_coord.report_deps(False, "deps fail: " + ", ".join(self._deps_failed))
        else:
            self._startup_coord.report_deps(True, "deps ok" if not stale else "update")
        self._pot_manager.ensure_ready("prewarm")

    def _on_deps_failed(self, labels):
        """[Followup-5] DEPS 검사 FAIL 목록 수신 — 게이트 판정에 반영한다."""
        self._deps_failed = list(labels or [])
        if self._deps_failed:
            self.append_concise_log(
                log_emitter.emit_event("DEPS", "FAIL", "MAIN",
                                       "deps fail: " + ", ".join(self._deps_failed)),
                is_status=False,
                is_error=True,
            )

    def _on_pot_finished(self, ok: bool, msg: str):
        self._stop_gate_watchdog()
        # [Followup-6] 봇 체크 재시도가 대기 중이면 POT 준비와 함께 재분석한다.
        if ok and self._pot_retry_pending:
            self._run_pending_retry()
            return
        pending = getattr(self, "_pending_download", None)
        if pending is None or not ok or not self._pot_manager.is_ready():
            return
        targets, v_id, a_id = pending
        self._pending_download = None
        self._start_download(targets, v_id, a_id)

    def _on_startup_unlocked(self):
        self._startup_completed = True
        self.update_ui_state()

    def _start_gate_watchdog(self):
        """[Followup-3] POT gate 대기 2차 워치독 기동."""
        self._gate_watchdog.reset()
        self._gate_watchdog_active = True

    def _stop_gate_watchdog(self):
        self._gate_watchdog_active = False

    def _on_pot_work_tick(self):
        """실제 POT 진행만 활성 게이트를 연장한다. 완료 후에는 재무장하지 않는다."""
        if self._gate_watchdog_active:
            self._gate_watchdog.heartbeat()

    def _on_gate_timeout(self):
        """[Followup-3] gate hang — POT 작업을 트리 종료하고 대기 큐를 해제한다."""
        if not self._gate_watchdog_active:
            return
        self._stop_gate_watchdog()
        if not self._pot_manager.is_busy():
            return
        # cancel()에서 pot_finished가 즉시 발행되어도 보류 요청은 재실행되지 않는다.
        self._pending_download = None
        self._pot_retry_pending = False
        self._pot_retry_url = None
        self._pot_manager.cancel()
        self.append_concise_log(
            log_emitter.emit_event("SYS", "WARN", "POT", "gate timeout — pot abandoned"),
            is_status=False,
            is_error=False,
        )
        self.update_ui_state()

    def _arm_analysis_watchdog(self):
        """[Watchdog] 분석 스폰 1회 무장 — 이후 만료 판정은 폴링이 담당한다."""
        self._analysis_watchdog.reset()
        self._analysis_watchdog_active = True

    def _disarm_analysis_watchdog(self):
        """[Watchdog] 분석 마감(성공/실패/만료) 해제 — 만료의 영속 재판정을 끊는다."""
        self._analysis_watchdog_active = False

    def _on_analysis_timeout(self):
        """[Watchdog] 분석 무응답 — 워커를 유기하고 FAIL로 마감한다.

        강제 terminate() 금지. 유기된 워커는 좀비 패턴으로 자연 종료를 기다리고,
        늦게 도착한 결과는 `_is_stale_analyze_signal()`이 폐기한다.
        """
        self._disarm_analysis_watchdog()
        if not self.ctrl.analyzing:
            return
        self.ctrl.abandon_analysis()
        self._pick_pending = False
        self._pick_targets = []
        self.ctrl._set_picking(False)
        self.update_ui_state()
        self.append_concise_log(
            log_emitter.emit_event(
                "ANAL", "FAIL", self._platform_of_url(),
                f"analysis timeout ({ANALYSIS_TIMEOUT_SEC:.0f}s) - no progress",
            ),
            True,
            True,
        )

    def _maybe_retry_analysis(self, err_msg: str) -> bool:
        """[Followup-6] 봇 체크 실패 시 POT 서버 기동 후 1회만 재분석을 큐잉한다."""
        if not _needs_pot_retry(err_msg):
            return False
        if self._pot_retry_pending:
            return False
        url = self.url_input.text().strip()
        if not url or url in self._pot_retry_done:
            return False
        self._pot_retry_done.add(url)
        self._pot_retry_url = url
        self._pot_retry_pending = True
        self.append_concise_log(
            log_emitter.emit_event("POT", "RUN", "POT",
                                   "bot-check detected — starting pot server, retrying once"),
            is_status=True,
            is_error=False,
        )
        if self._pot_manager.is_ready():
            self._run_pending_retry()
        else:
            self._pot_manager.ensure_ready("gate")
            self._start_gate_watchdog()
        return True

    def _run_pending_retry(self):
        """[Followup-6] POT 준비 완료 후 보류 URL을 명시적으로 재분석한다."""
        url = self._pot_retry_url
        self._pot_retry_pending = False
        self._pot_retry_url = None
        if not url:
            return
        self.url_input.setText(url)
        self.append_concise_log(
            log_emitter.emit_event("POT", "RUN", "YT", "retrying analysis with po token"),
            is_status=True,
            is_error=False,
        )
        self._arm_analysis_watchdog()
        if not self._preflight_deps_check():
            return
        self.ctrl.spawn_analyzer(url, self.cfg)
        self.update_ui_state()

    def _is_stale_analyze_signal(self) -> bool:
        """유령 분석 결과 판별 — 지운 뒤 "stream analyzed"가 한 번 더 뜨는 버그 차단."""
        if not self.ctrl.state.analyzing:
            return True
        return not bool(self.url_input.text().strip())

    def on_analyze_success(self, data):
        if self._is_stale_analyze_signal():
            return
        self._disarm_analysis_watchdog()
        self.ctrl._set_analyzing(False)
        self.extracted_data = data
        self._ensure_pot_for_info(data.get("info"))
        if data.get("is_playlist"):
            self.stop_analysis_anim()
            self.update_ui_state()
            return
        if getattr(self, "_pick_pending", False):
            self._pick_pending = False
            self._show_pick_menu(data)
            self.update_ui_state()
            return
        self.stop_analysis_anim()
        self.update_ui_state()

    def on_analyze_error(self, err_msg):
        if self._is_stale_analyze_signal():
            return
        self._disarm_analysis_watchdog()
        self.ctrl._set_analyzing(False)
        # [v3.8.0] 분석 실패 시 잔여 분석 데이터 즉시 초기화 —
        # 이전 URL의 info로 억지 다운로드가 실행되는 것을 원천 차단.
        self.extracted_data = {"info": None, "v_list": [], "a_list": []}
        pick_pending = getattr(self, "_pick_pending", False)
        self._pick_pending = False
        if pick_pending:
            self.ctrl._set_picking(False)
        self.stop_analysis_anim(ok=False)
        self.update_ui_state()
        self.append_concise_log(
            log_emitter.emit_event("ANAL", "FAIL", "-", err_msg),
            True,
            True,
        )
        # [쿠키 팝업 인터락 v3.8.0] 멤버십/연령제한 감지 시 쿠키 선택창 자동 표시
        low = (err_msg or "").lower()
        if (
            "chzzk cookie expired" in low
            or "members-only" in low
            or "member gated" in low
            or ("age" in low and "restricted" in low)
            or "confirm your age" in low
        ):
            from chzzktube.ui.dialogs import CookieSelectDialog
            dlg = CookieSelectDialog(self)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                self.cfg["browser_cookie"] = dlg.selected_type
                # 재분석 트리거
                if self._preflight_deps_check():
                    self.ctrl.spawn_analyzer(self.url_input.text().strip(), self.cfg)
            return
        # [Followup-6] 봇 체크/PO 토큰 사유면 POT 기동 후 1회 재시도를 큐잉한다.
        if self._maybe_retry_analysis(err_msg):
            return

    def _retry_deps(self):
        """[v3.8.1] deps 에러 시 ENTER로 재시도 — 에러 상태 초기화 후 재시도."""
        # 에러 상태 초기화
        self._startup_coord._state.deps_error_msg = ""
        # URL 입력창에 포커스
        self.url_input.setFocus()
        # deps 체크 재시도 (toggle_download와 유사하지만 에러 상태에서 호출)
        try:
            targets = MediaController.parse_targets(
                self.url_input.text().strip(),
                dedup=self.cfg.get("remove_duplicates"),
            )
        except ValueError as e:
            self.append_concise_log(
                log_emitter.emit_event("ANAL", "FAIL", "-", f"Invalid URL format — {e}" if "Invalid URL" not in str(e) else str(e)),
                False,
                True,
            )
            return
        if not targets:
            return
        # deps 재시도 트리거
        self._startup_coord.report_deps(False, "")  # 에러 상태 클리어용
        self.toggle_download()

    def get_current_app_state(self) -> str:
        # [P3b] POT 백그라운드 작업(is_busy)은 입력 잠금 사유가 아니다 — 그 역할은
        # toggle_download의 큐잉(_pending_download)이 맡는다. is_busy를 STARTUP 사유로
        # 두면 프리웜 진행 중 ENTER가 큐잉 분기에 도달하지 못하고 무반응으로 끝났다.
        if not getattr(self, "_startup_completed", False):
            return "STARTUP"
        if self.ctrl.running:
            return "RUNNING"
        if self.ctrl.analyzing:
            return "ANALYZING"
        if self.ctrl.picking:
            return "PICKING"
        return "IDLE"

    def update_ui_state(self):
        state = self.get_current_app_state()

        self.url_input.setEnabled(state in ("IDLE", "PICKING"))

        self.btn_open.setEnabled(True)
        self.btn_change.setEnabled(state == "IDLE")
        self.btn_settings.setEnabled(state in ("IDLE", "RUNNING"))
        self.btn_txt.setEnabled(state == "IDLE")

        if state == "STARTUP":
            self.btn_esc.setEnabled(False)
            self.btn_esc.setText("[ ESC: Clear ]")
        elif state == "RUNNING":
            self.btn_esc.setEnabled(True)
            self.btn_esc.setText("[ ESC: Abort ]")
        elif state in ("ANALYZING", "PICKING"):
            self.btn_esc.setEnabled(True)
            self.btn_esc.setText("[ ESC: Cancel ]")
        else:
            self.btn_esc.setEnabled(True)
            self.btn_esc.setText("[ ESC: Clear ]")

        if state == "IDLE":
            self.btn_enter.setEnabled(True)
            self.btn_enter.setText("[ ENTER: Start ]")
        elif state == "PICKING":
            self.btn_enter.setEnabled(True)
            self.btn_enter.setText("[ ENTER: Select ]")
        elif state == "STARTUP" and self._startup_coord._state.deps_error_msg:
            # [v3.8.1] deps 에러 시 재시도 버튼 표시
            self.btn_enter.setEnabled(True)
            self.btn_enter.setText("[ ENTER: Retry Setup ]")
        else:
            self.btn_enter.setEnabled(False)
            self.btn_enter.setText("[ ENTER: Start ]")

        self.console.reset_status_flag()

    def showEvent(self, event):
        super().showEvent(event)
        if hasattr(self, "console"):
            self.console.on_resize()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "console"):
            self.console.on_resize()

    def _render_concise(self, event, is_status=False, is_error=False):
        if isinstance(event, LogEvent):
            line = log_emitter.format_log_line_for_event(event)
            no_wrap = True
        else:
            line = str(event)
            no_wrap = False
        if len(line) > 4096:
            line = line[:4096] + "…"
        self.console.append(line, is_status, is_error, no_wrap=no_wrap)

    def _mirror_event_full(self, event, is_status=False):
        if isinstance(event, LogEvent):
            line = event.msg if event.msg else ""
        else:
            line = str(event)
        if is_status:
            self._last_status_line = line
        self._mirror_full_log(line, is_status)

    def _mirror_full_log(self, msg, is_status=False):
        msg = str(msg)
        if len(msg) > 4096:
            msg = msg[:4096] + "…"
        ts = time.strftime("%H:%M:%S")
        stamped = "\n".join(f"[{ts}] {l}" if l else f"[{ts}]" for l in msg.split("\n"))
        if not is_status:
            self._full_log_buf.append(stamped)
        win = getattr(self, "verbose_win", None)
        win_visible = win is not None and win.isVisible()
        if not is_status and win_visible:
            self._full_log_win_n = len(self._full_log_buf)
        if win_visible:
            try:
                win.append(stamped, is_status)
            except (AttributeError, RuntimeError):
                pass

    def append_concise_log(self, msg, is_status=False, is_error=False, fg_color=None):
        if isinstance(msg, LogEvent):
            msg.is_status = is_status
            msg.is_error = is_error
            raw_log.raw("ui", msg, to_tui=True)
        else:
            raw_log.raw("ui", msg, is_status=is_status, is_error=is_error, to_tui=True)

    def toggle_verbose_log(self):
        if getattr(self, "verbose_win", None) is not None and self.verbose_win.isVisible():
            self.verbose_win.close()
            return
        if self.verbose_win is None:
            self.verbose_win = VerboseLogWindow(self)
            content = "\n".join(self._full_log_buf)
            if not content.strip():
                content = log_emitter.emit_event("SYS", "OK", "LOG", "empty buffer")
            self.verbose_win.set_content(content)
            self._full_log_win_n = len(self._full_log_buf)
        else:
            pending = list(self._full_log_buf)[self._full_log_win_n:]
            for line in pending:
                self.verbose_win.append(line, False)
            self._full_log_win_n = len(self._full_log_buf)
        self.verbose_win.show()
        self.verbose_win.raise_()
        self.verbose_win.activateWindow()

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key.Key_F12:
            self.toggle_verbose_log()
            event.accept()
            return
        if key == Qt.Key.Key_F1:
            self.change_folder()
            event.accept()
            return
        if key == Qt.Key.Key_F2:
            _open_windows_explorer(self.cfg["download_path"])
            event.accept()
            return
        if key == Qt.Key.Key_F3:
            self.open_settings()
            event.accept()
            return
        if key == Qt.Key.Key_F4:
            self.pick_txt()
            event.accept()
            return
        if key == Qt.Key.Key_Escape:
            self._esc_action()
            event.accept()
            return
        if key == Qt.Key.Key_Return or key == Qt.Key.Key_Enter:
            # [v3.8.1] deps 에러 시 ENTER로 재시도
            if self._startup_coord._state.deps_error_msg and not self._startup_completed:
                self._retry_deps()
                event.accept()
                return
            # [v3.8.1] Setup 완료 후 ENTER로 다운로드 시작
            if self._startup_completed:
                self.toggle_download()
                event.accept()
                return
        super().keyPressEvent(event)

    def toggle_download(self):
        state = self.get_current_app_state()
        if state == "PICKING":
            self._submit_pick()
            return
        if state != "IDLE":
            return

        if not self._preflight_deps_check():
            return

        try:
            targets = MediaController.parse_targets(
                self.url_input.text().strip(),
                dedup=self.cfg.get("remove_duplicates"),
            )
        except ValueError as e:
            # [v3.8.0 게이트] 비URL 임의 문자열 등 — 파이프라인 진입 전 1회 경고 후 중단.
            self.append_concise_log(
                log_emitter.emit_event("ANAL", "FAIL", "-", f"Invalid URL format — {e}" if "Invalid URL" not in str(e) else str(e)),
                False,
                True,
            )
            return
        if not targets:
            return

        if self.cfg.get("pick_format") and len(targets) == 1:
            self._start_pick_flow(targets[0])
            return

        info = (self.extracted_data or {}).get("info") or {}
        needs_pot = _needs_pot(info)
        if needs_pot and self._pot_manager.is_busy():
            self._pending_download = (targets, "auto", "auto")
            self.append_concise_log(
                log_emitter.emit_event("SYS", "RUN", "POT", "queued — waiting for pot server"),
                is_status=True,
                is_error=False,
            )
            return
        if needs_pot:
            self._wait_pot_if_needed()
            if not self._pot_manager.is_ready():
                self._pending_download = (targets, "auto", "auto")
                self.append_concise_log(
                    log_emitter.emit_event("SYS", "RUN", "POT", "queued — waiting for pot server"),
                    is_status=True,
                    is_error=False,
                )
                return

        self._start_download(targets, "auto", "auto")

    def _start_download(self, targets, v_id, a_id):
        # [v3.8.0 2차 방어선] 워커 구동 직전 URL 재검증 — 잔여 데이터/직접 호출
        # 경로로 비URL이 유입되는 것을 최종 차단한다.
        bad = [t for t in targets or [] if not _is_valid_url(getattr(t, "url", t))]
        if bad:
            self.append_concise_log(
                log_emitter.emit_event(
                    "ANAL", "FAIL", "-",
                    f"Invalid URL format: {bad[0][:40]}",
                ),
                False,
                True,
            )
            return
        self.ctrl.begin_download()
        self.append_concise_log(
            log_emitter.emit_event("DL", "RUN", "YT", "downloading..."),
            is_status=True,
            is_error=False,
        )
        self.update_ui_state()

        live_hint = len(targets) == 1 and bool(
            (self.extracted_data.get("info") or {}).get("is_live")
        )
        self.ctrl.spawn_worker(
            targets,
            self.cfg,
            v_id,
            a_id,
            is_live_hint=live_hint,
            v_spec=None,
            audio_desc="",
            yt_client=self.extracted_data.get("yt_client", "auto"),
        )

    def _wait_pot_if_needed(self):
        info = (self.extracted_data or {}).get("info") or {}
        if not _needs_pot(info):
            return

        if server_ping():
            self._pot_manager.use_existing()
            return

        self.append_concise_log(
            log_emitter.emit_event("POT", "RUN", "POT", "starting server..."),
            is_status=True,
            is_error=False,
        )
        self._pot_manager.ensure_ready("gate")
        self._start_gate_watchdog()

    def _start_pick_flow(self, url):
        self._pick_targets = [url]
        self._pick_pending = True
        self.append_concise_log(
            log_emitter.emit_event("ANAL", "RUN", "YT", "analyzing formats..."),
            is_status=True,
            is_error=False,
        )
        self._arm_analysis_watchdog()
        if not self._preflight_deps_check():
            return
        self.ctrl.spawn_analyzer(url, self.cfg, deep=True)
        self.update_ui_state()

    def _show_pick_menu(self, data):
        v_list = data.get("v_list", [])
        a_list = data.get("a_list", [])
        if not v_list and not a_list:
            self.append_concise_log(
                log_emitter.emit_event("ANAL", "FAIL", "YT", "no formats for pick"),
                False,
                True,
            )
            self.update_ui_state()
            return
        from chzzktube.core.log_emitter import format_pick_menu

        lines = format_pick_menu(v_list, a_list)
        lines.append("enter: 'N' video  /  'N.M' v+a  /  empty=best")
        self.append_concise_log("\n".join(lines), False, False)
        self.ctrl._set_picking(True)
        self.url_input.setFocus()
        self.update_ui_state()

    def _submit_pick(self):
        targets = getattr(self, "_pick_targets", None)
        if not targets:
            self.ctrl._set_picking(False)
            return
        text = self.url_input.text().strip()
        v_list = self.extracted_data.get("v_list", [])
        a_list = self.extracted_data.get("a_list", [])
        v_id, a_id = "auto", "auto"
        if text:
            parts = re.split(r"[.,\s]+", text)
            try:
                if parts[0]:
                    idx = int(parts[0])
                    if not (1 <= idx <= len(v_list)):
                        raise ValueError
                    v_id = v_list[idx - 1]["id"]
                if len(parts) > 1 and parts[1].strip():
                    idx = int(parts[1])
                    if not (1 <= idx <= len(a_list)):
                        raise ValueError
                    a_id = a_list[idx - 1]["id"]
            except (ValueError, IndexError):
                self.append_concise_log(
                    log_emitter.emit_event("ANAL", "FAIL", "YT", "pick fail — retry"),
                    False,
                    True,
                )
                return
        self.ctrl._set_picking(False)
        self.append_concise_log(
            log_emitter.emit_event("DL", "OK", "YT", f"picked {v_id} · {a_id}"),
            False,
            False,
        )
        self._start_download(list(targets), v_id, a_id)

    def _cancel_pick(self):
        self.ctrl._set_picking(False)
        self._pick_pending = False
        self._pick_targets = []
        self.append_concise_log(
            log_emitter.emit_event("DL", "ABORT", "YT", "format pick canceled"),
            False,
            True,
        )
        self.update_ui_state()

    def skip_current(self):
        if self.ctrl.running:
            self.ctrl.request_skip()
            self.append_concise_log(
                log_emitter.emit_event("DL", "SKIP", "MAIN", "skip requested"),
                is_status=False,
                is_error=False,
            )

    def add_concise_task_separator(self):
        self.console.add_task_separator()

    def on_download_finished(self, success_count, fail_count):
        self.ctrl.on_download_finished(success_count, fail_count)
        self.update_ui_state()
        self.add_concise_task_separator()

        if success_count > 0:
            self.url_input.clear()
            if self.cfg.get("play_sound") and winsound:
                try:
                    winsound.MessageBeep(winsound.MB_ICONASTERISK)
                except OSError:
                    pass
            if self.cfg.get("auto_open_folder"):
                _open_windows_explorer(self.cfg["download_path"])


def main() -> int:
    try:
        _pylib = _bootstrap()
    except (OSError, ImportError):
        _pylib = ""

    sys.excepthook = lambda t, v, tb: log_history.exception("미처리 예외", t, v, tb)

    from chzzktube.infra.platform import set_app_user_model_id

    set_app_user_model_id("chzzktube.subapp.v2")

    app = QApplication(sys.argv)
    if os.path.exists(ICON_PATH):
        app.setWindowIcon(QIcon(ICON_PATH))

    font_path = os.path.join(BASE_DIR, "assets", "CascadiaMono-VariableFont_wght.ttf")
    if os.path.exists(font_path):
        QFontDatabase.addApplicationFont(font_path)

    # [핵심 교정] 라틴(Cascadia Mono) + CJK(맑은 고딕) 다중 패밀리 체인 구축
    font = QFont()
    font.setFamilies(["Cascadia Mono", "Malgun Gothic", "맑은 고딕", "Apple SD Gothic Neo"])
    font.setPointSize(11)

    # [한글 뭉개짐 방지] 힌팅을 완전 끄지 않고 수직 힌팅을 허용하여 한글 가독성 확보
    font.setHintingPreference(QFont.HintingPreference.PreferVerticalHinting)
    font.setStyleStrategy(
        QFont.StyleStrategy.PreferAntialias 
        | QFont.StyleStrategy.PreferQuality
    )

    # Windows CJK 인조 볼드 왜곡(자글거림)을 유발하던 Weight(550)을 제거하고 순정 Normal(400)로 안정화
    font.setWeight(QFont.Weight.Normal)

    app.setFont(font)

    try:
        if _pylib and os.path.isdir(_pylib):
            try:
                pkgs = sorted(
                    d.name for d in os.scandir(_pylib) if d.is_dir() and d.name.endswith(".dist-info")
                )
            except OSError:
                pkgs = []
            _suffix = f" [{', '.join(pkgs)}]" if pkgs else " [empty]"
            raw_log.raw(
                "deps",
                emit_component("DEPS", "OK", "PYLIB", f"overlay: {_pylib}{_suffix}"),
                to_tui=True,
            )
            sys.stderr.write(f"[DEPS] OK PYLIB overlay: {_pylib}{_suffix}\n")
    except OSError:
        pass

    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
```

## File: chzzktube/ui/theme.py

```python
### theme.py - TUI-inspired fzf 스타일 테마 (Dark Terminal Palette)
""" UI 스킨 문자열은 이 모듈에서만 정의한다. main.py / dialogs.py / log_console.py 는 여기서 임포트해 사용한다. """

### 색상 팔레트 (fzf-inspired dark terminal)
BG_WINDOW = "#0d0d0d"        # 메인/다이얼로그 콘솔 톤
BG_SURFACE = "#1a1a1a"       # 패널 배경
BG_CONSOLE = "#0d0d0d"       # 콘솔 배경
BG_HOVER = "#252526"         # 호버 배경
FG_TEXT = "#cccccc"          # 기본 전경
FG_DIM = "#888888"           # 딤 텍스트
BORDER = "#282828"           # 테두리
ACCENT = "#4ec9b0"           # 액센트 (청록)
ACCENT_ALT = "#ce9178"       # 보조 액센트 (주황)
ERROR = "#e06c75"            # 에러 레드 (soft pastel — Atom One Dark)
WARN = "#e5c07b"             # 경고 옐로
SUCCESS = "#6a9955"          # 성공 그린

### MainWindow 전역 스타일 (fzf border-line aesthetic)
MAIN_WINDOW_QSS = f"""
QMainWindow, QDialog {{ background-color: {BG_WINDOW}; color: {FG_TEXT}; font-family: 'Cascadia Mono', monospace; font-size: 11px; }}
QLabel {{ color: {FG_TEXT}; font-family: 'Cascadia Mono', monospace; }}
QPushButton {{ background-color: {BG_SURFACE}; color: {FG_TEXT}; border: 1px solid {BORDER}; border-radius: 0px; padding: 4px 12px; font-family: 'Cascadia Mono', monospace; font-size: 11px; }}
QPushButton:hover {{ background-color: {BG_HOVER}; border-color: {ACCENT}; }}
QPushButton:pressed {{ background-color: #333333; }}
QPushButton:disabled {{ background-color: #1a1a1a; color: #555555; border-color: #333333; }}
QLineEdit {{ background-color: {BG_SURFACE}; color: {FG_TEXT}; border: 1px solid {BORDER}; border-radius: 0px; padding: 6px 10px; font-family: 'Cascadia Mono', monospace; font-size: 11px; }}
QLineEdit:focus {{ border: 1px solid {ACCENT}; }}
QProgressBar {{ text-align: center; border: none; background-color: {BG_SURFACE}; height: 4px; color: transparent; }}
QProgressBar::chunk {{ background-color: {ACCENT}; }}
QScrollBar:vertical {{ border: none; background: transparent; width: 6px; }}
QScrollBar::handle:vertical {{ background: {BORDER}; min-height: 20px; border-radius: 0px; }}
QScrollBar::handle:vertical:hover {{ background: #555555; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
QListWidget {{ background-color: {BG_CONSOLE}; color: {FG_TEXT}; border: 1px solid {BORDER}; border-radius: 0px; font-family: 'Cascadia Mono', monospace; font-size: 11px; outline: none; }}
QListWidget::item {{ padding: 3px 6px; border: none; }}
QListWidget::item:hover {{ background-color: {BG_HOVER}; }}
QListWidget::item:selected {{ background-color: #1d3a34; color: {ACCENT}; }}
QSplitter::handle {{ background-color: {BORDER}; }}
"""

### fzf-style 보더 프레임 (타이틀을 보더 위 중앙 배치)
def groupbox_qss(title=""):
    """fzf-style QGroupBox — 타이틀을 보더 위 중앙에 배치."""
    return f"""
QGroupBox {{
    border: 1px solid {BORDER};
    border-radius: 0px;
    margin-top: 8px;
    padding-top: 12px;
    font-family: 'Cascadia Mono', monospace;
    font-size: 11px;
    color: {FG_DIM};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top center;
    padding: 0 6px;
    background-color: {BG_WINDOW};
    color: {ACCENT};
}}
"""

FRAME_QSS = f"""
QFrame {{
    border: 1px solid {BORDER};
    border-radius: 0px;
    background-color: {BG_SURFACE};
}}
"""
### 콘솔 로그 영역
CONSOLE_LOG_QSS = f"""
QTextEdit {{
    background-color: {BG_CONSOLE};
    color: {FG_TEXT};
    border: 1px solid {BORDER};
    border-radius: 0px;
    font-size: 11px;
    padding: 6px;
}}
QScrollBar:vertical {{ border: none; background: transparent; width: 6px; }}
QScrollBar::handle:vertical {{ background: {BORDER}; min-height: 20px; border-radius: 0px; }}
QScrollBar::handle:vertical:hover {{ background: #444444; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
"""
TE_CONTENT_QSS = CONSOLE_LOG_QSS

### 간결 로그 색 위계
LOG_COLOR_SUCCESS = SUCCESS
LOG_COLOR_ERROR = ERROR
LOG_COLOR_WARN = WARN
LOG_COLOR_INFO = "#b0b6bc"   # 회백 — 정보성 헤더
LOG_COLOR_STRUCT = "#5f6a72"  # 트리 글리프·라벨 (딤 그레이)
LOG_COLOR_VALUE = "#e8eaed"   # 트리 값·일반 텍스트
LOG_COLOR_DIM = FG_DIM
LOG_COLOR_ACCENT = ACCENT
LOG_COLOR_ACCENT_ALT = ACCENT_ALT

### 버튼 QSS — 새 팔레트 단일 출처
BTN_ACTION_QSS = f"""QPushButton {{ background-color: {BG_SURFACE}; color: {ACCENT}; border: 1px solid {ACCENT}; border-radius: 0px; padding: 6px 16px; font-family: 'Cascadia Mono', monospace; font-size: 11px; }}
QPushButton:hover {{ background-color: #2a3a35; }}
QPushButton:pressed {{ background-color: #1a2a25; }}
QPushButton:disabled {{ background-color: #1a1a1a; color: #555555; border-color: #333333; }}
"""

BTN_DANGER_QSS = f"""QPushButton {{ background-color: {BG_SURFACE}; color: {ERROR}; border: 1px solid {ERROR}; border-radius: 0px; padding: 6px 16px; font-family: 'Cascadia Mono', monospace; font-size: 11px; }}
QPushButton:hover {{ background-color: #3a2525; }}
QPushButton:pressed {{ background-color: #2a1515; }}
QPushButton:disabled {{ background-color: #1a1a1a; color: #555555; border-color: #333333; }}
"""

BTN_NEUTRAL_QSS = f"""QPushButton {{ background-color: {BG_SURFACE}; color: {FG_TEXT}; border: 1px solid {BORDER}; border-radius: 0px; padding: 6px 16px; font-family: 'Cascadia Mono', monospace; font-size: 11px; }}
QPushButton:hover {{ background-color: {BG_HOVER}; }}
QPushButton:disabled {{ background-color: #1a1a1a; color: #555555; border-color: #333333; }}
"""
### 다이얼로그 QSS
MSGBOX_QSS = f"""
QMessageBox {{ background-color: {BG_WINDOW}; }}
QLabel {{ color: {FG_TEXT}; padding: 8px 16px; }}
QPushButton {{ background-color: {BG_SURFACE}; color: {FG_TEXT}; border: 1px solid {BORDER}; border-radius: 0px; padding: 6px 16px; min-width: 70px; }}
QPushButton:hover {{ background-color: {BG_HOVER}; border-color: {ACCENT}; }}
QTextEdit {{ background-color: {BG_CONSOLE}; color: {FG_TEXT}; border: 1px solid {BORDER}; border-radius: 0px; padding: 4px; }}
"""

### 설정 다이얼로그 — 모던 TUI 패널
SETTINGS_TUI_QSS = """
QGroupBox.tui-panel {
    border: 1px solid #2a2a2a;
    border-radius: 6px;
    margin-top: 10px;
    padding: 8px;
    background-color: #0d0d0d;
}
QGroupBox.tui-panel::title {
    subcontrol-origin: margin;
    subcontrol-position: top center;
    padding: 0 8px;
    background-color: #0d0d0d;
    color: #4ec9b0;
    font-size: 11px;
    font-weight: bold;
}
QLabel { color: #cccccc; font-size: 11px; }
QCheckBox { color: #d4d4d4; spacing: 6px; }
QCheckBox::indicator {
    width: 14px; height: 14px;
    border: 1px solid #2a2a2a;
    background: #161616;
    border-radius: 2px;
}
QCheckBox::indicator:checked {
    background: #4ec9b0;
    border-color: #4ec9b0;
}
QPushButton {
    background: #161616;
    color: #d4d4d4;
    border: 1px solid #2a2a2a;
    padding: 4px 12px;
    font-size: 11px;
}
QPushButton:hover {
    border-color: #4ec9b0;
    color: #4ec9b0;
}
"""

DIALOG_BG_QSS = f"background-color: {BG_WINDOW}; color: {FG_TEXT}; font-size: 11px;"
TE_CONTENT_QSS = f"background-color: {BG_CONSOLE}; color: {FG_TEXT}; border: 1px solid {BORDER}; border-radius: 0px; padding: 4px;"
DLG_SECTION_TITLE_QSS = f"font-weight: bold; border: none; background: transparent; color: {ACCENT};"
DLG_STATUS_QSS = f"color: {FG_DIM}; border: none; background: transparent;"
DLG_GHOST_BTN_QSS = f"""
QPushButton {{ background-color: {BG_SURFACE}; color: {FG_TEXT}; border: 1px solid {BORDER}; border-radius: 0px; padding: 4px 10px; font-size: 11px; font-family: 'Cascadia Mono', monospace; }}
QPushButton:hover {{ background-color: {BG_HOVER}; border-color: {ACCENT}; }}
QPushButton:disabled {{ background-color: #1a1a1a; color: #555555; border-color: #333333; }}
"""

SETTINGS_SCROLL_QSS = f"""
QScrollArea {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 6px; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 0px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: #555555; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
"""

### MainWindow TUI 스타일 (Hyper-Minimal Modern TUI — flat, borderless, mono)
### ──────────────────────────────────────────────────────────────
# ── TUI_STYLE (메인 윈도우 및 설정창 공용) ──
TUI_STYLE = """
QWidget, QMainWindow {
    background-color: #0d0d0d;
    color: #cccccc;
    font-size: 11px;
}

QGroupBox.tui-panel {
    border: none;
    border-radius: 0px;
    margin-top: 0px;
    padding: 8px 0px 8px 0px;
    background-color: #0d0d0d;
}

QGroupBox.tui-panel::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0px;
    background-color: transparent;
    color: transparent;
    font-size: 1px;
}

QFrame.tui-separator {
    background-color: #1a1a1a;
    max-height: 1px;
    min-height: 1px;
    border: none;
}

QPushButton[class="tui-tag"] {
    background-color: transparent;
    border: none;
    color: #ce9178;
    font-size: 11px;
    padding: 2px 6px;
}

QPushButton[class="tui-tag"]:hover {
    color: #ffffff;
    background-color: #252526;
    border-radius: 3px;
}

QPushButton[class="tui-tag"]:pressed {
    color: #4ec9b0;
}

QLineEdit#url_input::placeholder { color: #555555; }

QLineEdit#url_input {
    background-color: transparent;
    border: none;
    border-bottom: 1px solid #333333;
    color: #dcdcdc;
    font-size: 11px;
    padding: 4px 0px 4px 0px;
    selection-background-color: #264f78;
}

QLineEdit#url_input:focus {
    border-bottom: 1px solid #4ec9b0;
}

QPlainTextEdit#console_log, QTextEdit#console_log {
    background-color: #0d0d0d;
    border: none;
    color: #d4d4d4;
    font-size: 11px;
    line-height: 1.3;
}

QScrollBar:vertical {
    border: none;
    background: #0d0d0d;
    width: 6px;
}

QScrollBar::handle:vertical {
    background: #333333;
    border-radius: 3px;
    min-height: 20px;
}

QScrollBar::handle:vertical:hover {
    background: #555555;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
"""

# ── 플랫 TUI 버튼 3종 (11px 일괄 매칭) ──
BTN_EXIT_DANGER_QSS = f"""
QPushButton {{ background-color: transparent; color: {ERROR}; border: 1px solid #5a1d1d; border-radius: 0px; padding: 4px 12px; font-size: 11px; }}
QPushButton:hover {{ background-color: #3a1515; border-color: {ERROR}; }}
QPushButton:pressed {{ background-color: #2a0f0f; }}
"""

BTN_NEUTRAL_QSS = f"""
QPushButton {{ background-color: transparent; color: {FG_TEXT}; border: 1px solid {BORDER}; border-radius: 0px; padding: 4px 12px; font-size: 11px; }}
QPushButton:hover {{ background-color: {BG_HOVER}; border-color: #555555; color: #ffffff; }}
QPushButton:pressed {{ background-color: #141414; }}
"""

DLG_GHOST_BTN_QSS = f"""
QPushButton {{ background-color: #141414; color: {FG_TEXT}; border: 1px solid {BORDER}; border-radius: 0px; padding: 4px 10px; font-size: 11px; }}
QPushButton:hover {{ background-color: {BG_HOVER}; border-color: {ACCENT}; color: {ACCENT}; }}
"""

### 호환 참조 (main.py / dialogs.py 가 참조하는 이름 — 새 팔레트로 연결)
BAR_PANEL_QSS = f"background-color: {BG_SURFACE}; border: 1px solid {BORDER}; border-radius: 0px;"
LBL_STREAM_QSS = f"color: {FG_DIM}; font-size: 11px; border: none; background: transparent; font-family: 'Cascadia Mono', monospace;"
LBL_META_QSS = f"color: {ACCENT_ALT}; font-size: 11px; border: none; background: transparent; font-family: 'Cascadia Mono', monospace;"
CONSOLE_INIT_QSS = CONSOLE_LOG_QSS

BTN_PRIMARY_QSS = BTN_ACTION_QSS        # 다운로드 시작 (액센트 아웃라인)
BTN_INFO_QSS = BTN_NEUTRAL_QSS          # 건너뛰기 (중립)
BTN_SETTINGS_FONT_QSS = BTN_NEUTRAL_QSS # 설정 (중립)
BTN_EXIT_DANGER_QSS = BTN_DANGER_QSS    # 종료 확인 (에러 아웃라인)
BTN_GRID_QSS = BTN_NEUTRAL_QSS          # 쿠키 소스 그리드
BTN_CLOSE_QSS = BTN_NEUTRAL_QSS         # 다이얼로그 닫기
```

## File: chzzktube/pipeline/__init__.py

```python

```

## File: chzzktube/pipeline/classifier.py

```python
"""chzzktube/pipeline/classifier.py — 미디어 항목 사전 분류 및 규격 단일 출처 (SSOT).

[원칙]
- I/O 및 UI 설정(cfg) 오염 0건: 디스크나 전역 상태를 절대 건드리지 않는 순수 도메인 로직.
- 정직한 TriState 삼치 논리: 포맷 미확정(extract_flat) 상태를 함부로 True/False로 날조하지 않는다.
- None-Safety 보장: 하류 파이프라인이 None을 False로 오판해 스트림을 강등시키지 않도록 명시적 질의 메서드 제공.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Mapping


class ContentKind(Enum):
    """콘텐츠 종류 — 플랫폼 및 스트림 성격의 명확한 분리."""
    VOD = auto()
    CLIP = auto()
    LIVE_YOUTUBE = auto()
    LIVE_CHZZK = auto()
    PLAYLIST = auto()
    UNKNOWN = auto()

    @property
    def is_live(self) -> bool:
        return self in (ContentKind.LIVE_YOUTUBE, ContentKind.LIVE_CHZZK)


@dataclass(frozen=True, slots=True)
class StreamCapability:
    """True / False / None(미확정) 삼치 논리를 엄격히 캡슐화한 스트림 역량 모델."""
    has_video: bool | None
    has_audio: bool | None
    requires_auth: bool = False

    @classmethod
    def indeterminate(cls, requires_auth: bool = False) -> StreamCapability:
        """extract_flat 등 메타데이터가 미비한 경우 사용하는 안전 팩토리."""
        return cls(has_video=None, has_audio=None, requires_auth=requires_auth)

    def is_video_confirmed(self) -> bool:
        """확정적으로 비디오가 존재하는지 여부 (None은 False 처리하여 보수적 접근)."""
        return self.has_video is True

    def is_audio_confirmed(self) -> bool:
        """확정적으로 오디오가 존재하는지 여부."""
        return self.has_audio is True

    def could_have_video(self) -> bool:
        """비디오가 존재할 가능성이 열려 있는지 (True 또는 None일 때 참)."""
        return self.has_video is not False

    def could_have_audio(self) -> bool:
        """오디오가 존재할 가능성이 열려 있는지 (True 또는 None일 때 참)."""
        return self.has_audio is not False


@dataclass(frozen=True, slots=True)
class CookiePolicyContext:
    """SRP 준수를 위한 인증/쿠키 요구사항 정책 명세 (I/O 없음)."""
    needs_cookie: bool
    reason: str = ""


@dataclass(slots=True)
class ClassifiedTarget:
    """파이프라인 전체가 공유하는 정규화된 항목 계약 객체."""
    url: str
    title: str
    kind: ContentKind
    capability: StreamCapability
    platform_tag: str
    downloadable: bool = True
    needs_pot: bool = False
    skip_reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_live(self) -> bool:
        return self.kind.is_live


class ItemClassifier:
    """UI cfg 및 부수 효과로부터 완벽히 격리된 순수 분류 엔진."""

    _POT_AVAIL_GATED = frozenset({
        "needs_auth", "premium_only", "private"
    })

    @classmethod
    def evaluate_cookie_policy(
        cls, info: Mapping[str, Any] | None = None
    ) -> CookiePolicyContext:
        """메타데이터 기반 인증 필요성 순수 판정."""
        if not info:
            return CookiePolicyContext(needs_cookie=False)
        age_limit = int(info.get("age_limit") or 0)
        availability = str(info.get("availability") or "").lower()

        if age_limit > 0:
            return CookiePolicyContext(needs_cookie=True, reason="age_limit")
        if availability in cls._POT_AVAIL_GATED:
            return CookiePolicyContext(needs_cookie=True, reason=availability)
        return CookiePolicyContext(needs_cookie=False)

    @classmethod
    def classify(
        cls, url: str, raw_info: Mapping[str, Any] | None = None
    ) -> ClassifiedTarget:
        """URL 및 메타데이터를 정밀 심사하여 ClassifiedTarget으로 변환."""
        info = dict(raw_info or {})
        u = url.lower().strip()

        # 1. 플랫폼 감별
        is_chzzk = "chzzk.naver.com" in u
        is_yt = any(p in u for p in ("youtube.com", "youtu.be"))
        platform = "CHZ" if is_chzzk else ("YT" if is_yt else "EXT")

        title = str(info.get("title") or info.get("videoTitle") or "untitled")
        is_live = bool(info.get("is_live"))
        cookie_policy = cls.evaluate_cookie_policy(info)
        # [핵심 변경] needs_pot는 age_limit>0(성인인증)만 — 멤버십은 Layer 1/2에서 해결
        needs_pot = is_yt and (info.get("age_limit", 0) > 0)

        # 2. 치지직 분기
        if is_chzzk:
            if "/clips/" in u or "/clip/" in u:
                return ClassifiedTarget(
                    url=url, title=title, kind=ContentKind.CLIP,
                    capability=StreamCapability(has_video=True, has_audio=True),
                    platform_tag=platform, needs_pot=False, metadata=info,
                )
            if "/live/" in u or is_live:
                return ClassifiedTarget(
                    url=url, title=title, kind=ContentKind.LIVE_CHZZK,
                    capability=StreamCapability(has_video=True, has_audio=True),
                    platform_tag=platform, needs_pot=False, metadata=info,
                )
            return ClassifiedTarget(
                url=url, title=title, kind=ContentKind.VOD,
                capability=StreamCapability(has_video=True, has_audio=True),
                platform_tag=platform, needs_pot=False, metadata=info,
            )

        # 3. 유튜브 라이브 정밀 판정 (회피 없이 일급 시민으로 등록)
        if is_yt and (is_live or "/live/" in u):
            return ClassifiedTarget(
                url=url, title=title, kind=ContentKind.LIVE_YOUTUBE,
                capability=StreamCapability(has_video=True, has_audio=True, requires_auth=cookie_policy.needs_cookie),
                platform_tag=platform, needs_pot=needs_pot, metadata=info,
            )

        # 4. 평탄화(Flat) 단계: 거짓말하지 않는 TriState 적용
        formats = info.get("formats")
        if info.get("_type") == "url" or not formats:
            is_audio_hint = "music.youtube.com" in u
            return ClassifiedTarget(
                url=url,
                title=title,
                kind=ContentKind.VOD,
                capability=StreamCapability(
                    has_video=False if is_audio_hint else None,
                    has_audio=True if is_audio_hint else None,
                    requires_auth=cookie_policy.needs_cookie,
                ),
                platform_tag=platform,
                needs_pot=needs_pot,
                metadata=info,
            )

        # 5. 완전 추출 포맷 메타데이터 심사 (이미지 전용 / 오디오 전용 정밀 감별)
        has_v = any(f.get("vcodec") not in (None, "none", "") for f in formats)
        has_a = any(f.get("acodec") not in (None, "none", "") for f in formats)

        # 비디오도 오디오도 없는 이미지 전용 영상 사전 필터링
        if not has_v and not has_a:
            return ClassifiedTarget(
                url=url, title=title, kind=ContentKind.UNKNOWN,
                capability=StreamCapability(has_video=False, has_audio=False),
                platform_tag=platform, downloadable=False,
                skip_reason="image-only", metadata=info,
            )

        return ClassifiedTarget(
            url=url,
            title=title,
            kind=ContentKind.VOD,
            capability=StreamCapability(
                has_video=has_v,
                has_audio=has_a,
                requires_auth=cookie_policy.needs_cookie,
            ),
            platform_tag=platform,
            needs_pot=needs_pot,
            metadata=info,
        )
```

## File: chzzktube/pipeline/dl_context.py

```python
### dl_context.py - 다운로드 파이프라인 컨텍스트 (D: worker grab-bag 해결)
"""DownloadWorker가 파이프라인 모듈에 넘기는 명시적 컨텍스트.

[문제] target_downloader/progress_emitter/finalizer가 worker 객체를 통째로
받아 worker.cfg, worker.logger, worker._speed_win 등을 암시적으로 접근.
"worker가 뭘 제공하는지"가 불명확해 신규 파이프라인 추가 시 계약을 알 수 없다.

[해결] 아래 dataclass로 계약을 명시한다. DownloadWorker는 자신의 상태에서
DownloadContext를 생성해 파이프라인에 넘기고, 파이프라인은 이 컨텍스트만 본다.
Qt Signal(YtLoggerBridge)은 그대로 참조로 전달된다 (QThread 상속 구조 유지).
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class DownloadContext:
    """다운로드 파이프라인 함수들이 소비하는 컨텍스트.

    DownloadWorker 인스턴스에서 extract()로 생성된다.
    파이프라인 모듈(target_downloader, progress_emitter, finalizer)은
    worker 객체 대신 이 컨텍스트만 받아 명시적 계약을 이행한다.
    """

    # 설정 (worker.cfg 딕셔너리 참조)
    cfg: Dict[str, Any]

    # 포맷 선택 ("auto"면 자동 선택)
    v_sel: str = "auto"
    a_sel: str = "auto"

    # 비디오 스펙 (v_list[0]에서 추출된 height/fps 등)
    v_spec: Dict[str, Any] = field(default_factory=dict)

    # 오디오 설명 (a_list[0]에서 추출)
    audio_desc: str = ""

    # 로거 (YtLoggerBridge — raw 버스 직행 어댑터)
    logger: Any = None

    # 현재 처리 중인 대상
    current_url: str = ""
    current_file: Optional[str] = None

    # 세션 상태 (UI→워커 단방향: canceled, skip)
    state: Dict[str, bool] = field(default_factory=lambda: {"canceled": False, "skip": False})

    # 속도 계산 (SpeedWindow — 이동평균)
    speed_win: Any = None

    # 진행 틱 타임스탬프 (progress_emitter에서 사용)
    _last_tick_t: float = 0.0

    # 배치 진행 현황
    total_count: int = 0
    current_idx: int = 0

    # 라이브 관련
    is_live_hint: bool = False
    live_partially_saved: bool = False
    # 라이브 녹화 프로세스 핸들 (kill_live_process에서 사용)
    _live_proc: Any = None
    # 메타 로그 발행 여부 (advance_target에서 초기화)
    _meta_logged: bool = False

    # 포맷 선택 (분석 단계에서 결정된 클라이언트)
    yt_client: str = "auto"

    # [결함 5 수리] 워치독 참조 — 파이프라인 함수들이 하트비트 호출 가능
    _download_watchdog: Any = None
    _gate_watchdog: Any = None
    _live_watchdog: Any = None
    _analysis_watchdog: Any = None

    # 대상 목록 (expand_targets에서 참조)
    targets: list = field(default_factory=list)

    # 배치 완료 시그널 (DownloadWorker.finished_all 바인딩)
    finished_all: Any = None

    # 오류 수집 (다운로드 실패 시 메시지 누적)
    _errors: List[str] = field(default_factory=list, repr=False)

    def add_error(self, msg: str) -> None:
        """오류 메시지를 수집한다. finalizer가 배치 마감에서 참조한다."""
        self._errors.append(msg)

    @property
    def errors(self) -> List[str]:
        """수집된 오류 목록 (읽기 전용)."""
        return list(self._errors)

    def advance_target(self, idx: int, url: str) -> None:
        """타겟 진행 상태를 단일 지점에서 안전하게 업데이트하고 속도계 윈도우를 초기화한다."""
        self.current_idx = idx
        self.current_url = url
        self.current_file = None
        self._meta_logged = False
        self._last_tick_t = 0.0
        if self.speed_win:
            self.speed_win.reset()
```

## File: chzzktube/pipeline/finalizer.py

```python
"""finalizer.py - DownloadWorker의 _finalize 분할 — TUI 컬럼 포맷.

── Worker Contract ──────────────────────────────────────────────
본 모듈의 함수들이 요구하는 worker 객체의 인터페이스:
  ctx.logger           : YtLoggerBridge — raw 버스 직행 (log_full/log_concise 시그널 폐기)
  ctx.total_count      : int   — 전체 대상 수
  ctx.current_url       : str   — 현재 처리 중인 URL (실패 시 참조)
──────────────────────────────────────────────────────────────────
"""
import os

import chzzktube.core.raw_log as raw_log
from chzzktube.core.dl_platform import _dl_platform
from chzzktube.pipeline.progress_emitter import emit_dl
from chzzktube.core.log_emitter import emit_error_standard


def finalize(ctx, total, failed_targets, success_count, skip_targets=None, *, notify=True):
    """완료 요약을 기록한다.

    워커는 notify=False로 호출하고 자체 finally에서 종료 신호를 발행한다.
    notify=True는 기존 직접 호출자의 정상 마감 통지 호환용이다.
    
    Args:
        skip_targets: List[Tuple[url, skip_reason]] - 스킵된 항목들 (선택적)
    """
    fail_count = len(failed_targets)
    skip_count = len(skip_targets) if skip_targets else 0

    if ctx.state["canceled"]:
        if ctx.live_partially_saved:
            ctx.live_partially_saved = False
        else:
            raw_log.raw(
                "dl",
                emit_dl("ABORT", scope=_dl_platform(ctx.current_url or ""), msg="download canceled by user"),
                to_tui=True,
            )

    if failed_targets:
        if total > 1:
            ff_path = os.path.join(ctx.cfg["download_path"], "failed_urls.txt")
            try:
                with open(ff_path, "w", encoding="utf-8") as f:
                    for u, _ in failed_targets:
                        f.write(u + "\n")
            except Exception:
                pass
        # [개별 실패 라인] — ERR 컬럼 포맷으로 1건 1줄 (v3.8.0 규격: cause → action)
        for u, reason in failed_targets:
            # 원인 분류: reason 문자열에서 원인 키워드 추출
            reason_lower = reason.lower()
            if "bot" in reason_lower or "bot check" in reason_lower:
                cause = "bot check"
                action = "check network (F12)"
            elif "network" in reason_lower or "timeout" in reason_lower or "connection" in reason_lower:
                cause = "network error"
                action = "check network (F12)"
            elif "permission" in reason_lower or "denied" in reason_lower:
                cause = "permission denied"
                action = "check folder permissions"
            elif "checksum" in reason_lower or "hash" in reason_lower:
                cause = "checksum mismatch"
                action = "retry mirror (1/3)"
            elif "not found" in reason_lower or "404" in reason_lower:
                cause = "not found"
                action = "check network (F12)"
            elif "private" in reason_lower or "member" in reason_lower or "unavailable" in reason_lower:
                cause = "private"
                action = "check network (F12)"
            else:
                cause = "download failed"
                action = "check logs (F12)"

            raw_log.raw("dl", emit_error_standard("DL", _dl_platform(u), cause, action), to_tui=True)

    # [결론 라인] — 상태 세분화: DONE/WARN/FAIL/SKIP
    if ctx.state["canceled"]:
        status = "ABORT"
    elif fail_count == 0 and skip_count == 0:
        status = "DONE"
    elif fail_count == 0 and skip_count > 0:
        status = "DONE"  # 모두 스킵이거나 일부 스킵+성공
    elif success_count > 0 and fail_count > 0:
        status = "WARN"  # 일부 성공 + 일부 실패
    elif success_count == 0 and fail_count > 0:
        status = "FAIL"  # 모두 실패
    else:
        status = "WARN"

    msg_parts = [f"success: {success_count}"]
    if fail_count:
        msg_parts.append(f"fail: {fail_count}")
    if skip_count:
        msg_parts.append(f"skip: {skip_count}")
    msg = "batch finished (" + ", ".join(msg_parts) + ")"

    raw_log.raw(
        "dl",
        emit_dl(
            status=status,
            scope=_dl_platform(ctx.current_url or ""),
            pct=100,
            bar_frac=1.0,
            msg=msg,
            is_error=fail_count > 0,
        ),
        to_tui=True,
    )

    if notify:
        ctx.finished_all.emit(success_count, fail_count)
    return not ctx.state["canceled"]

```

## File: chzzktube/pipeline/live_recorder.py

```python
##### live_recorder.py - 라이브 녹화 파이프라인 (streamlink/ffmpeg)
"""유튜브·치지직 라이브를 ffmpeg 자식 프로세스로 녹화한다.

- yt-dlp/streamlink 로 포맷 URL만 추출하고, 실제 수신은 ffmpeg로 위임
- **릴레이 계측**: ffmpeg stdout(파이프) 을 Python 이 256KB 청크로 읽어
  최종 파일에 실기록하며, 그 바이트 수 = 네트워크 실수신량 → ctx.speed_win(add) 로 속도 측정
- stderr 는 별도 스레드로 상세 로그 유지
- 취소 시 kill + stdout 큐 drain (이후 'truncated' 오탐 방지)
- **출력 소유권 단일화**: FFmpeg는 stdout 파이프로만 출력, Python이 파일 소유자로서 기록
- **논블로킹 읽기**: reader 스레드 + Queue로 1초 타임아웃 폴링 → 취소/워치독 하트비트 체크 가능
"""
import os
import queue
import subprocess
import threading
import time
from contextlib import suppress

import yt_dlp

from chzzktube.core import raw_log
from chzzktube.core.dl_platform import _dl_platform
from chzzktube.core.media import (
    cleanup_temp_files,
    format_bytes,
)
from chzzktube.core.utils import get_filename_template
from chzzktube.pipeline.progress_emitter import (
    emit_dl,
    emit_live_final_stats,
    log_success_info,
)

# FFmpeg stdout 읽기 청크 크기 (256KB)
_READ_CHUNK = 256 * 1024
# 진행 로그 발행 간격 (초)
_TICK_INTERVAL = 1.0
# [결함 2 수리] 논블로킹 읽기 셀렉터 타임아웃 (초) — 취소/워치독 체크 주기
_SELECTOR_TIMEOUT = 1.0
# [결함 5 수리] 워치독 하트비트 발행 간격 (초)
_WATCHDOG_HEARTBEAT_INTERVAL = 5.0


def download_youtube_live(ctx, url):
    """유튜브 라이브 — yt-dlp로 포맷 URL만 추출 후 Python이 파일을 기록한다.

    FFmpeg는 MPEG-TS를 stdout으로만 출력한다. Python이 최종 출력 파일의 유일한
    작성자가 되어 FFmpeg와 파일 소유권을 공유하지 않는다.
    """
    opts = {
        "logger": ctx.logger,
        "noplaylist": True,
        "format": "bv*+ba/b",
        "skip_download": True,
        "extract_flat": False,
    }
    from chzzktube.core.client_opts import (
        _apply_client_opts,
        _apply_cookie_opts,
        _apply_ejs_opts,
        _apply_ffmpeg_opts,
    )

    _apply_cookie_opts(opts, ctx.cfg)
    _apply_client_opts(opts, ctx.cfg, forced=None)  # 순정 위임
    _apply_ejs_opts(opts)
    _apply_ffmpeg_opts(opts)

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)

    if not info:
        raise RuntimeError("live info fail")

    stream_url = info.get("url")
    if not stream_url:
        raise RuntimeError("live URL missing")

    out_file = os.path.join(
        ctx.cfg["download_path"],
        get_filename_template(ctx.cfg) % info,
    )

    temp_ts, _, _ = prepare_live_paths(ctx, out_file)
    cmd = ["ffmpeg", "-y", "-i", stream_url, "-c", "copy", "-f", "mpegts", "pipe:1"]
    return record_live_stream(ctx, cmd, temp_ts, log_tag="FFmpeg")


def prepare_live_paths(ctx, out_file, thumb_url=None):
    """릴레이 기록용 임시 TS 및 썸네일·최종 출력 경로를 도출한다."""
    base, _ = os.path.splitext(out_file)
    temp_ts = f"{base}_temp.ts"
    thumb_file = f"{base}_temp_thumb.jpg" if thumb_url else None
    return temp_ts, thumb_file, out_file


def _remux_live_output(ctx, out_file):
    """TS를 별도 파일로 변환한 뒤 교체한다. 실패하면 원본을 보존한다."""
    from chzzktube.infra.platform import spawn_kwargs

    if not out_file or not os.path.isfile(out_file) or not os.path.getsize(out_file):
        return None
    target_ext = str(ctx.cfg.get("container", "mp4") or "mp4").lower()
    if target_ext not in ("mp4", "mkv"):
        target_ext = "mp4"
    base = os.path.splitext(out_file)[0].removesuffix("_temp")
    out_path = base + f".{target_ext}"
    # 기존 최종 파일과 원본 TS는 변환 성공 전까지 건드리지 않는다.
    import tempfile
    fd, staging = tempfile.mkstemp(suffix=f".{target_ext}", dir=os.path.dirname(out_file) or ".")
    os.close(fd)
    cmd = ["ffmpeg", "-y", "-i", out_file, "-c", "copy", staging]
    try:
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       check=True, timeout=120, **spawn_kwargs())
        if not os.path.getsize(staging):
            raise RuntimeError("empty remux output")
        os.replace(staging, out_path)
        if os.path.abspath(out_file) != os.path.abspath(out_path):
            os.remove(out_file)
        return out_path
    except Exception as ex:
        raw_log.raw(
            "media",
            emit_dl(status="FAIL", scope=_dl_platform(ctx.current_url or ""),
                    stage="LIVE", msg=f"live remux failed — {ex}; source retained: {out_file}",
                    is_error=True),
            to_tui=False,
        )
        return None
    finally:
        with suppress(OSError):
            os.remove(staging)



def handle_stream_finish(ctx, is_live, temp_file, proc_code=0):
    """성공한 변환만 완료 처리하고, 취소/실패한 원본 녹화는 보존한다."""
    has_data = bool(temp_file and os.path.isfile(temp_file) and os.path.getsize(temp_file))
    if ctx.state.get("canceled"):
        ctx.live_partially_saved = has_data
        if has_data:
            raw_log.raw("dl", emit_dl(status="ABORT", stage="LIVE",
                        msg=f"partial recording retained: {temp_file}"), to_tui=True)
        return False
    if not has_data:
        raw_log.raw("dl", emit_dl(status="FAIL", stage="LIVE",
                    msg="empty or missing recording", is_error=True), to_tui=True)
        return False
    if proc_code not in (0, None):
        raw_log.raw("dl", emit_dl(status="FAIL", stage="LIVE",
                    msg=f"exit code {proc_code}; source retained: {temp_file}",
                    is_error=True), to_tui=True)
        return False

    out_path = _remux_live_output(ctx, temp_file)
    if not out_path:
        return False
    if out_path and os.path.exists(out_path):
        size = os.path.getsize(out_path)
        raw_log.raw(
            "dl",
            emit_dl(
                status="DONE",
                scope=_dl_platform(ctx.current_url or ""),
                pct=100,
                bar_frac=1.0,
                stage="LIVE",
                msg=f"saved · {os.path.basename(out_path)} ({format_bytes(size)})",
            ),
            to_tui=True,
        )
        log_success_info(ctx, out_path)
    cleanup_temp_files(temp_file)
    return True


_READ_CHUNK = 256 * 1024
_TICK_INTERVAL = 1.0


def record_live_stream(ctx, cmd, out_file, log_tag="Streamlink"):
    """ffmpeg/streamlink 자식 프로세스 녹화 — 릴레이 계측 + stderr 로그 + 취소 처리.

    [결함 2 수리] reader 스레드 + Queue로 논블로킹 릴레이
    - Windows 파이프에서 selectors/select 미지원 문제 회피
    - 네트워크 단절 시에도 메인 루프가 1초마다 취소/워치독 체크
    [결함 5 수리] 5초마다 워치독 하트비트 호출
    """
    from chzzktube.infra.platform import spawn_kwargs

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=False,
        **spawn_kwargs(),
    )

    # 컨텍스트에 프로세스 핸들 저장 (앱 종료 시 정리용)
    ctx._live_proc = proc

    # [결함 2 수리] stdout 읽기를 별도 스레드로 분리
    # - 메인 루프는 queue.get(timeout=1.0)으로 논블로킹
    # - reader 스레드가 블로킹 read를 담당하므로 네트워크 멈춤도 메인 UI를 막지 않음
    stdout_queue = queue.Queue()
    def _read_stdout():
        try:
            while True:
                chunk = proc.stdout.read(_READ_CHUNK)
                stdout_queue.put(chunk)
                if not chunk:
                    break
        except Exception:
            # reader 스레드 예외도 메인 루프가 종료할 수 있도록 EOF sentinel 주입
            stdout_queue.put(b"")

    reader_t = threading.Thread(target=_read_stdout, daemon=True)
    reader_t.start()

    ctx.speed_win.reset()
    total_bytes = 0
    start_t = time.monotonic()
    last_tick = 0.0
    last_watchdog_heartbeat = 0.0

    def _drain_stderr():
        # stderr 는 별도 스레드로 실시간 상세 로그 유지 (버스 단일 경유)
        from chzzktube.core.log_event import LogEvent
        for raw in iter(proc.stderr.readline, b""):
            if raw:
                with suppress(Exception):
                    raw_log.raw("ffmpeg",
                                LogEvent(stage="LIVE", status="RUN",
                                         scope="FFMP",
                                         msg=raw.decode("utf-8", "replace").strip(),
                                     ),
                                )

    stderr_t = threading.Thread(target=_drain_stderr, daemon=True)
    stderr_t.start()

    returncode = -1
    try:
        with open(out_file, "wb") as out_f:
            while True:
                try:
                    chunk = stdout_queue.get(timeout=_SELECTOR_TIMEOUT)
                except queue.Empty:
                    # [결함 2 수리] 1초 타임아웃마다 취소/워치독/프로세스 상태 체크
                    if ctx.state.get("canceled") and proc.poll() is None:
                        with suppress(ProcessLookupError, OSError):
                            proc.kill()
                        break
                    # [결함 5 연동] 워치독 하트비트 (ctx에 워치독 참조가 있다면)
                    _try_watchdog_heartbeat(ctx, last_watchdog_heartbeat)
                    last_watchdog_heartbeat = time.monotonic()
                    continue

                if not chunk:
                    break
                out_f.write(chunk)
                total_bytes += len(chunk)
                ctx.speed_win.add(total_bytes)

                now = time.monotonic()
                if now - last_tick >= _TICK_INTERVAL:
                    last_tick = now
                    rate = ctx.speed_win.speed()
                    fname = os.path.basename(out_file)
                    raw_log.raw(
                        "dl",
                        emit_dl(
                            status="RUN",
                            scope=_dl_platform(ctx.current_url or ""),
                            speed=f"{format_bytes(rate)}/s" if rate else "-",
                            stage="LIVE",
                            msg=f"recording · {fname}",
                            is_status=True,
                        ),
                        to_tui=True,
                    )

                # [결함 2 수리] 취소 요청 즉시 처리
                if ctx.state.get("canceled") and proc.poll() is None:
                    with suppress(ProcessLookupError, OSError):
                        proc.kill()
                    break

        ctx.speed_win.add(total_bytes)
        returncode = proc.wait()
        if returncode not in (0, None) and not ctx.state.get("canceled"):
            raise RuntimeError(f"{log_tag} process exit code {returncode}")
        emit_live_final_stats(ctx, total_bytes, start_t)
    except Exception as ex:  # noqa: BLE001
        if proc.poll() is None:
            with suppress(ProcessLookupError, OSError):
                proc.kill()
        raw_log.raw(
            "dl",
            emit_dl(
                status="FAIL",
                scope=_dl_platform(ctx.current_url or ""),
                stage="LIVE",
                msg=f"{log_tag} fail — {type(ex).__name__}: {ex}",
                is_error=True,
            ),
            to_tui=True,
        )
    finally:
        reader_t.join(timeout=1.0)
        stderr_t.join(timeout=1.0)

    return handle_stream_finish(ctx, True, out_file, returncode)


def _try_watchdog_heartbeat(ctx, last_heartbeat_time):
    """컨텍스트에서 사용 가능한 워치독에 하트비트 시도 (5초 간격)."""
    now = time.monotonic()
    if now - last_heartbeat_time < _WATCHDOG_HEARTBEAT_INTERVAL:
        return
    for attr in ("_download_watchdog", "_gate_watchdog", "_live_watchdog", "_analysis_watchdog"):
        wd = getattr(ctx, attr, None)
        if wd and hasattr(wd, "heartbeat"):
            try:
                wd.heartbeat()
            except Exception:
                pass
            break

```

## File: chzzktube/pipeline/progress_emitter.py

```python
##### progress_emitter.py - DownloadWorker 진행률/헤더 emit 파이프라인
"""다운로드 진행률·완료·헤더 로그의 단일 출처.

- VOD 진행 틱: yt-dlp hook → `ctx.speed_win`(10초 이동평균) → 0.5초 스로틀 컬럼 라인
- 라이브 틱·마감: 릴레이 파이프 계수 → 동일 컬럼 규격 (용량 rjust(9) / 속도 rjust(11))
- 헤더(다운로드/라이브/치지직): 제목·포맷 트리 조판, 통합 포맷은 오디오 가지 미표기
- media.cli_format_desc 가 포맷 표기의 단일 출처.

── Worker Contract ──────────────────────────────────────────────
본 모듈의 함수들이 요구하는 worker 객체의 인터페이스:
  worker.logger           : YtLoggerBridge — raw 버스 직행 (log_full/log_concise 시그널 폐기)
  worker.cfg              : dict  — download_path, container 등 설정
  worker.v_spec           : dict  — height, fps 등 비디오 스펙
  worker.audio_desc       : str   — 오디오 설명
  worker.current_url       : str   — 현재 처리 중인 URL
  worker.current_file      : str|None — 현재 다운로드 파일 경로
  ctx.speed_win        : SpeedWindow — 이동평균 속도 (hook 내부에서 add)
  worker.total_count / current_idx : int — 배치 진행 현황
  worker.live_partially_saved : bool — 라이브 부분 저장 플래그
──────────────────────────────────────────────────────────────────
"""
import os
import re
import time

from chzzktube.core.log_emitter import (
    emit_event,
    emit_dl,
)
import chzzktube.core.raw_log as raw_log
from chzzktube.core.media import cli_format_desc, format_bytes
from chzzktube.core.dl_platform import _dl_platform
from chzzktube.core.watchdog import LivenessWatchdog


def _dl_spec(ctx):
    """컨텍스트에서 사양 문자열 추출 (해상도·fps, 오디오 폴백)."""
    v = ctx.v_spec or {}
    h = v.get("height") or 0
    fps = v.get("fps") or 0
    if h:
        return f"{h}p{fps}" if fps else f"{h}p"
    a_desc = ctx.audio_desc or ""
    if a_desc and ("(" in a_desc or "AAC" in a_desc or "OPUS" in a_desc):
        return a_desc
    return ""


def hook(ctx, d):
    """yt-dlp progress_hook 콜백 — downloading→틱, finished→완료 메타."""
    status = d.get("status")
    if status == "downloading":
        return emit_progress_tick(ctx, d)
    if status == "finished":
        fpath = d.get("filename") or ctx.current_file or ""
        return log_success_info(ctx, fpath)
    return None


_TICK_INTERVAL = 0.5  # VOD 틱 0.5초 스로틀


def emit_progress_tick(ctx, d):
    """VOD 진행 틱 — 0.5초 스로틀, SpeedWindow 평균 속도, 컬럼 라인.
    [Watchdog] 다운로드 진행 시 게이트/분석 워치독 하트비트 연장."""
    # [Watchdog] 진행 이벤트 발생 시 메인 워치독 하트비트 (ctx에서 메인 윈도우 접근 불가하므로 raw_log 이벤트로 전달)
    # 실제 하트비트는 DownloadWorker.run()에서 _gate_watchdog/_analysis_watchdog에 직접 연결 권장
    # 여기서는 진행 중임을 알리는 이벤트만 로깅
    raw_log.raw("dl", "progress_tick", to_tui=False)
    # 실제 워치독 하트비트는 DownloadWorker가 대상 진입 직전/직후에 호출한다.
    # 이 모듈은 UI/워커 역참조 없이 진행 데이터만 처리한다.

    now = time.monotonic()
    last = ctx._last_tick_t or 0
    if last and now - last < _TICK_INTERVAL:
        return
    ctx._last_tick_t = now

    done = float(d.get("downloaded_bytes") or 0)
    total = float(d.get("total_bytes") or d.get("total_bytes_estimate") or 0)

    ctx.speed_win.add(done)
    rate = ctx.speed_win.speed()
    speed_s = f"{format_bytes(rate)}/s" if rate else "-"

    pct = (done / total * 100.0) if total else 0.0
    # 제목은 이미 ANAL 단계에서 표시되었으므로 제외 (중복 방지)
    title = ""

    raw_log.raw(
        "dl",
        emit_dl(
            status="RUN",
            scope=_dl_platform(ctx.current_url or ""),
            msg="",
            speed=speed_s,
            pct=pct,
            bar_frac=min(pct / 100.0, 1.0),
            is_status=True,
        ),
        to_tui=True,
    )


def log_success_info(ctx, file_path):
    """개별 파일 수급 완료 — 용량 포함 한 줄.

    [v3.8.0 Hyper-Minimalist TUI] 중간 임시 스트림(.f399/.f251 등)은 TUI에서
    은닉한다(to_tui=False). 병합 완료 후 최종 결과물 1줄은 yt-dlp
    postprocessor 훅(`pp_hook`)이 발행한다 — 지시서 §3 Task 5-2.
    """
    size = 0
    if file_path and os.path.exists(file_path):
        size = os.path.getsize(file_path)
    # [채널명 포함] DL 완료 Msg에 채널명 추가
    channel = _dl_platform(ctx.current_url or "")
    fname = os.path.basename(file_path) if file_path else "done"
    msg = f"{fname} ({format_bytes(size)})" if file_path else "done"
    raw_log.raw(
        "dl",
        emit_event("DL", "OK", channel, msg),
        to_tui=not _is_intermediate_stream(fname),
    )


### [v3.8.0] yt-dlp 분리 포맷 스트림 조각 식별 — '.f399.mp4' / '.f251.webm'
_INTERMEDIATE_RE = re.compile(r"\.f\d+\.")
# 병합/후처리 단계에서 최종 결과물만 TUI 노출 (모든 소스 스트림 은닉)
_PP_FINAL_STATUS = "finished"


def _is_intermediate_stream(fname):
    """분리 포맷 중간 조각(.fNNN) 여부 — TUI 은닉 판정."""
    return bool(_INTERMEDIATE_RE.search(str(fname or "")))


def pp_hook(ctx, d):
    """yt-dlp postprocessor 훅 — 병합/후처리 완료 시 최종 결과물 1줄만 발행.

    MergeVideo 등 후처리 finished 시 info_dict.filename이 최종 산출물이다.
    중복 방지: 이미 발행한 경로는 재발행하지 않는다 (ctx._pp_last_file).
    """
    if not isinstance(d, dict) or d.get("status") != _PP_FINAL_STATUS:
        return None
    info = d.get("info_dict") or {}
    final = info.get("filepath") or info.get("_filename") or ""
    if not final or _is_intermediate_stream(os.path.basename(final)):
        return None
    if getattr(ctx, "_pp_last_file", None) == final:
        return None
    ctx._pp_last_file = final
    size = os.path.getsize(final) if os.path.exists(final) else 0
    raw_log.raw(
        "dl",
        emit_dl(
            status="OK",
            scope=_dl_platform(ctx.current_url or ""),
            msg=f"{os.path.basename(final)} ({format_bytes(size)})",
        ),
        to_tui=True,
    )


# ── 헤더 ───────────────────────────────────────────────────────────────────


def _title_of(info):
    return str(info.get("title") or info.get("videoTitle") or "video")


def emit_download_header(ctx, info):
    """VOD 다운로드 시작 헤더 — 컬럼 포맷 통일."""
    title = _title_of(info)
    fmt = info.get("format") or {}
    fmt_desc = cli_format_desc(fmt) if fmt and isinstance(fmt, dict) else ""
    msg = f"{title}"
    if fmt_desc:
        msg += f" ({fmt_desc})"
    raw_log.raw(
        "dl",
        emit_event("DL", "RUN", _dl_platform(ctx.current_url or ""), msg),
        to_tui=True,
    )
    ctx._meta_logged = True


def emit_chzzk_header(ctx, ch_info, fmt):
    """치지직(클립/VOD) 헤더 — 컬럼 포맷 통일."""
    title = ch_info.get("videoTitle") or ch_info.get("title") or "untitled"
    fmt_desc = cli_format_desc(fmt) if fmt else ""
    msg = f"chzzk - {title}"
    if fmt_desc:
        msg += f" ({fmt_desc})"
    raw_log.raw("dl", emit_event("DL", "RUN", "CHZ", msg), to_tui=True)
    ctx._meta_logged = True


def emit_live_final_stats(ctx, total_bytes, start_time):
    """라이브 종료 통계 — LIVE 스테이지, 용량은 MSG·평균 속도는 SPEED."""
    dur = (time.monotonic() - start_time) if start_time else 0.0
    rate = (total_bytes / dur) if dur > 0 else 0.0
    raw_log.raw(
        "dl",
        emit_dl(
            status="DONE",
            scope=_dl_platform(ctx.current_url or ""),
            speed=f"{format_bytes(rate)}/s",
            pct=100,
            bar_frac=1.0,
            stage="LIVE",
            msg=f"live done ({format_bytes(total_bytes)})",
        ),
        to_tui=True,
    )
    ctx.live_partially_saved = False

```

## File: chzzktube/pipeline/target_downloader.py

```python
##### target_downloader.py - 개별 URL 다운로드 / 대상 평탄화
"""DownloadWorker의 다운로드 실행부 분할 모듈.

- expand_targets : 재생목록/채널 URL을 개별 동영상 URL로 평탄화
- download_target : 개별 URL을 타입별로 분기해 실제 다운로드
  chzzk(clip/vod) → 직접 HTTP 스트림, youtube VOD → yt-dlp,
  youtube live → _download_youtube_live(ffmpeg), stream → streamlink
"""
import functools
import os
import re
import time
import urllib.request
import yt_dlp

# yt_dlp.utils가 없을 수 있으므로 안전하게 참조
try:
    YtDownloadError = yt_dlp.utils.DownloadError
except AttributeError:
    # 네임스페이스 패키지 형태에서는 직접 import 시도
    try:
        from yt_dlp.utils import DownloadError as YtDownloadError
    except ImportError:
        class YtDownloadError(Exception):
            pass

import chzzktube.core.chzzk_api as chzzk_api
from chzzktube.core.chzzk_api import analyze_chzzk_clip_api, analyze_chzzk_vod_api
from chzzktube.core.client_opts import (
    _apply_client_opts,
    _apply_cookie_opts,
    _apply_ejs_opts,
    _apply_ffmpeg_opts,
    _apply_light_analysis_opts,
    _apply_post_opts,
    _apply_pot_opts,
    _concurrent_fragments,
)
from chzzktube.core.dl_platform import detect_content_type, _dl_platform
from chzzktube.core.playlist import normalize_youtube_channel_url
import chzzktube.core.raw_log as raw_log
from chzzktube.core.utils import get_filename_template
from chzzktube.infra.po_client import extract_video_id
import chzzktube.pipeline.live_recorder as _lr
import chzzktube.pipeline.progress_emitter as _pe
from chzzktube.pipeline.classifier import ClassifiedTarget, ContentKind, ItemClassifier

# ── 봇 차단 재시도 가능 마커 vs 터미널 에러 판별 (SSOT) ───────────────────────
_RETRYABLE_BOT_MARKERS = frozenset({
    "confirm you're not a bot",
    "not a bot",
    "sign in to confirm",
    "the page needs to be reloaded",
    "n challenge solving failed",
    "challenge solving failed",
    "po token",
    "failed to extract any player response",
    "http error 403",
    "requested format is not available",
    "only images are available",
    "no video formats found",
})

_TERMINAL_FAIL_MARKERS = frozenset({
    "private video",
    "this video is private",
    "video unavailable",
    "this video is not available",
    "has been removed",
    "account has been terminated",
    "copyright",
    "members-only",
})

# [결함 5 수리] 워치독 하트비트 발행 간격 (초)
_WATCHDOG_HEARTBEAT_INTERVAL = 5.0


class _FormatQualityLoss(Exception):
    """1차 다운로드가 성공했지만 1080p+ 분리 포맷 수급에 실패한 내부 신호.

    봇 차단과 동일하게 Layer 3(POT 서버) 승격 트리거로 취급하되,
    720p tv 클라이언트로의 타협은 없다 (v3.8.0).
    """


def _is_retryable_bot_error(err: Exception) -> bool:
    """봇 차단/JS 챌린지 계열인지 판별 — 터미널 에러는 즉시 상위로 탈출."""
    msg = str(err).lower()
    if any(term in msg for term in _TERMINAL_FAIL_MARKERS):
        return False
    return any(bot in msg for bot in _RETRYABLE_BOT_MARKERS)


def _make_ytdl_opts(ctx, fmt, url, forced_client=None, inject_pot=False):
    """yt-dlp 다운로드 옵션 — outtmpl/훅/병합/쿠키/player_client/PO 토큰 주입.
    
    Args:
        forced_client: 강제 사용할 player_client (None이면 "auto"로 순정 위임).
        inject_pot: True면 PO token 강제 주입 (POT 서버 기동 후 재시도용).
    """
    opts = {
        "logger": ctx.logger,
        "noplaylist": True,
        "progress_hooks": [functools.partial(_pe.hook, ctx)],
        "postprocessor_hooks": [functools.partial(_pe.pp_hook, ctx)],
        "outtmpl": os.path.join(
            ctx.cfg.get("download_path") or ".",
            get_filename_template(ctx.cfg),
        ),
        "format": fmt,
        "merge_output_format": ctx.cfg.get("container", "mp4"),
        "retries": 3,
        "socket_timeout": 30,
        "throttledratelimit": 50_000,
    }
    frags = _concurrent_fragments(ctx.cfg)
    if frags > 1:
        opts["concurrent_fragment_downloads"] = frags
    _apply_cookie_opts(opts, ctx.cfg)
    
    # client 지정: forced_client가 있으면 사용, 없으면 "auto"로 순정 위임
    effective_client = forced_client if forced_client is not None else "auto"
    _apply_client_opts(opts, ctx.cfg, forced=effective_client)
    _apply_ejs_opts(opts)
    
    # PO token 주입: inject_pot=True일 때만 (POT 서버 기동 후 재시도)
    # client="auto" 시 순정이 선택할 클라와 일치하도록 web_embedded 기준 주입
    if inject_pot:
        vid = _extract_yt_id(url)
        if vid:
            pot_client = "web" if _has_configured_cookies(ctx.cfg) else "web_embedded"
            _apply_pot_opts(opts, vid, client=pot_client)
    
    _apply_ffmpeg_opts(opts)
    _apply_post_opts(opts, ctx.cfg)
    return opts


def _extract_yt_id(url):
    """YouTube URL에서 video ID 추출 (PO 토큰 content_binding용)."""
    return extract_video_id(url)


def _format_selector(ctx):
    """yt-dlp format 선택 문자열 — 자동(해상도 제한 내 최고)/포맷 직접 고르기 대응.
    
    [결함 1 수리] tv 클라이언트 대비: 비디오+오디오 분리 포맷이 없을 때
    단일 포맷(b)으로 폴백하지 않고 명시적 에러 유도 → 상위에서 폴백 체인 계속.
    """
    if ctx.cfg.get("audio_only"):
        return "bestaudio/best"

    v_id = str(ctx.v_sel or "").strip()
    a_id = str(ctx.a_sel or "").strip()
    if v_id and v_id != "auto":
        if a_id and a_id != "auto":
            return f"{v_id}+{a_id}"
        return f"{v_id}+bestaudio"

    res = str(ctx.cfg.get("max_video_res") or "none").strip()
    if res.isdigit():
        return f"bv*[height<={res}]+ba"
    # [결함 1 수리] "bv*+ba/b" → "bv*+ba" (단일 포맷 폴백 제거)
    return "bv*+ba"


def _chzzk_filename(ch_info, fmt, cfg):
    """치지직 다운로드 파일명 — get_filename_template(cfg) 계약을 치지직 메타로 치환."""
    cfg = cfg or {}
    title = str(ch_info.get("title") or ch_info.get("videoTitle") or "chzzk")
    title = re.sub(r'[\\/:*?"<>|]+', "_", title).strip(" _") or "chzzk"
    cid = str(
        ch_info.get("clip_id")
        or ch_info.get("video_no")
        or ch_info.get("live_id")
        or ""
    ).strip()
    chan = str(ch_info.get("channel_name") or "").strip()
    date = str(ch_info.get("date") or "").strip()[:10]
    height = fmt.get("height") if isinstance(fmt, dict) else None

    prefix_map = {
        "none": "",
        "uploader": f"[{chan}] " if chan else "",
        "date_dash_uploader": f"{date} [{chan}] " if (date and chan) else "",
        "date_compact_uploader": (
            f"{date.replace('-', '')} [{chan}] " if (date and chan) else ""
        ),
        "date_dash": f"{date} " if date else "",
        "date_compact": f"{date.replace('-', '')} " if date else "",
    }
    prefix = prefix_map.get(str(cfg.get("filename_prefix", "none") or "none"), "")

    suffix = ""
    if cid:
        suffix = f" [{cid}]"
        if str(cfg.get("filename_suffix", "id") or "id") == "id_res" and height:
            suffix += f" [{height}p]"
    return f"{prefix}{title}{suffix}.mp4"


def _http_download(ctx, url, out_path):
    """치지직 progressive MP4 직접 스트림 다운로드 + 진행률 틱.
    
    [결함 5 수리] 5초마다 워치독 하트비트 호출.
    """
    ctx.speed_win.reset()
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as resp, open(out_path, "wb") as f:
        done = 0
        last_heartbeat = time.monotonic()
        while True:
            chunk = resp.read(262144)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            ctx.speed_win.add(done)

            # [결함 5 수리] 5초마다 워치독 하트비트
            now = time.monotonic()
            if now - last_heartbeat >= _WATCHDOG_HEARTBEAT_INTERVAL:
                last_heartbeat = now
                for attr in ("_download_watchdog", "_gate_watchdog", "_live_watchdog", "_analysis_watchdog"):
                    wd = getattr(ctx, attr, None)
                    if wd and hasattr(wd, "heartbeat"):
                        try:
                            wd.heartbeat()
                        except Exception:
                            pass
                        break
    return out_path


def _download_chzzk(ctx, url, content_type):
    """치지직 클립/VOD — API 포맷의 progressive MP4 직접 스트림 다운로드."""
    ch_info = (
        analyze_chzzk_clip_api(url)
        if content_type == "clip"
        else analyze_chzzk_vod_api(url)
    )
    formats = ch_info.get("formats") or []
    if not formats:
        raise RuntimeError("chzzk stream fail (cookie)")
    fmt = formats[0]
    stream_url = fmt.get("url") or ""
    if not stream_url:
        raise RuntimeError("chzzk URL missing")

    if not ctx._meta_logged:
        _pe.emit_chzzk_header(ctx, ch_info, fmt)

    out_path = os.path.join(
        ctx.cfg["download_path"], _chzzk_filename(ch_info, fmt, ctx.cfg)
    )
    real = _http_download(ctx, stream_url, out_path)
    _pe.log_success_info(ctx, real)
    ctx.speed_win.reset()
    return True


def _download_chzzk_live(ctx, url):
    """치지직 API의 HLS 포맷을 FFmpeg stdout 릴레이로 녹화한다."""
    info = chzzk_api.analyze_chzzk_live_api(url)
    if info.get("live_status") != "PROGRESS":
        raise RuntimeError("chzzk live offline")
    formats = [fmt for fmt in info.get("formats", []) if fmt.get("url")]
    selection = str(ctx.v_sel or "auto").strip()
    if selection and selection != "auto":
        formats = [fmt for fmt in formats if str(fmt.get("id")) == selection]
    else:
        limit = str(ctx.cfg.get("max_video_res") or "none")
        if limit.isdigit():
            formats = [fmt for fmt in formats if 0 < (fmt.get("height") or 0) <= int(limit)]
    if not formats:
        raise RuntimeError("chzzk live format unavailable")
    fmt = max(formats, key=lambda f: (f.get("height") or 0, f.get("bitrate") or 0))
    if not ctx._meta_logged:
        _pe.emit_chzzk_header(ctx, info, fmt)
    out_file = os.path.join(ctx.cfg["download_path"], _chzzk_filename(info, fmt, ctx.cfg))
    temp_ts, _, _ = _lr.prepare_live_paths(ctx, out_file)
    cmd = ["ffmpeg", "-y", "-i", fmt["url"]]
    if ctx.cfg.get("audio_only"):
        cmd.append("-vn")
    cmd.extend(["-c", "copy", "-f", "mpegts", "pipe:1"])
    ok = _lr.record_live_stream(ctx, cmd, temp_ts, log_tag="FFmpeg")
    if not ok and not ctx.state.get("canceled"):
        raise RuntimeError("chzzk live recording failed")
    return ok


def _download_youtube_live(ctx, url):
    """유튜브 라이브 — ffmpeg 녹화 파이프라인 (live_recorder)."""
    return _lr.download_youtube_live(ctx, url)


def _download_streamlink(ctx, url):
    """streamlink 대상 — 자식 프로세스 녹화 파이프라인 (화질은 cfg fit)."""
    out_file = os.path.join(ctx.cfg["download_path"], "streamlink_live.mp4")
    temp_ts, _, _ = _lr.prepare_live_paths(ctx, out_file, None)
    quality = str(ctx.cfg.get("streamlink_quality") or "best").strip() or "best"
    cmd = ["streamlink", url, quality, "-O"]
    return _lr.record_live_stream(ctx, cmd, temp_ts)


def _ensure_pot_server_ready(ctx, timeout=60.0):
    """[Layer 3] POT 서버 준비 — 워커 스레드 안전 (v3.8.0).

    [근본 수리] v3.7.2는 `POTManager.instance()`를 호출했지만 그런 API는
    존재하지 않았다(잠재 AttributeError — POT 경로 전체가 즉사). 게다가
    POTManager는 뷰가 소유한 QObject라 워커 스레드에서 접근하는 것 자체가
    스레드 경계 위반이다. 여기서는 L0(po_client.server_ping)과 L1
    (pot_server의 순수 스폰/빌드 헬퍼)만 호출해 동일 목적을 달성한다 —
    모두 Qt 무의존 순수 인프라라 백그라운드 스레드에서 안전하다.

    절차: /ping 생존 확인 → 빌드 존재 시 스폰 → (없으면) 프리웜 락 하에
    스테이징 빌드 → 스폰 → 포트 준비까지 폴링.

    Returns:
        True  : 서버가 /ping에 응답 (PO 토큰 패칭 가능)
        False : 미준비/타임아웃 — 호출부는 PO 없이 진행 여부를 판단한다
    """
    import time

    from chzzktube.infra.po_client import server_ping

    def _alive():
        return bool(server_ping())

    if _alive():
        return True

    def _log(msg):
        raw_log.raw(
            "dl",
            _pe.emit_event("DL", "RUN", "POT", str(msg)[:80]),
            to_tui=True,
        )

    def _heartbeat():
        wd = getattr(ctx, "_download_watchdog", None)
        if wd is not None:
            try:
                wd.heartbeat()
            except Exception:
                pass

    try:
        from chzzktube.infra.pot_server import (
            _spawn_existing, acquire_prewarm_lock, built_server_js,
            ensure_node_server, release_prewarm_lock, server_home,
            _SERVER_FALLBACK_VER,
        )
    except Exception as ex:  # noqa: BLE001 — 인프라 import 실패 시 PO 없이 진행
        _log(f"pot infra unavailable ({type(ex).__name__})")
        return False

    _log("starting POT server...")

    if not built_server_js():
        # 빌드 부재 — 프리웜 락 하에 1회 스테이징 후 스폰 재시도.
        fd = acquire_prewarm_lock(timeout=0, log_func=_log)
        if fd is None:
            _log("pot build busy — skipped")
            return False
        try:
            _, err = ensure_node_server(
                _log, _log, _SERVER_FALLBACK_VER, rebuild=False,
                tick_func=_heartbeat,
            )
            if err is not None:
                _log(f"pot build failed: {err}")
        finally:
            try:
                release_prewarm_lock(fd, log_func=_log)
            except Exception:
                pass

    if built_server_js():
        try:
            _spawn_existing(_log)
        except Exception as ex:  # noqa: BLE001
            _log(f"pot spawn fail: {type(ex).__name__}")
    else:
        _log("pot build unavailable")
        return False

    deadline = time.time() + max(1.0, float(timeout))
    while time.time() < deadline:
        if ctx.state.get("canceled"):
            return False
        if _alive():
            return True
        _heartbeat()
        time.sleep(0.5)
    _log("pot server startup timeout")
    return False


def _download_vod(ctx, url):
    """유튜브 VOD 다운로드 — yt-dlp 순정 위임 + POT 서버 1회 재시도.

    1차: yt-dlp 순정 단일 호출 (player_client="auto") →
         내부 로테이션: web_embedded → tv_downgraded → web_safari → mweb → tv...
         EJS 솔버(deno/node) 자동 작동 + 쿠키 있으면 인증 클라 우선

    2차: 1차 실패(봇 차단/포맷 상실) 또는 1차 성공이 1080p 미달이면
         POT 서버 기동 → PO token + visitorData 주입하여 동일 순정 호출
         재시도 (1회만). 720p tv 타협 없이 최고 화질을 강제 개방.

    수동 클라 체인 완전 제거 — 순정이 알아서 최적 경로 찾음
    """
    cfg_client = str(ctx.cfg.get("yt_player_client", "auto") or "auto")

    # 명시적 클라 지정 시에만 forced_client 사용 (테스트/디버깅용)
    forced = None if cfg_client == "auto" else cfg_client

    fmt = _format_selector(ctx)

    first_info = None

    # 1차: 순정 위임 (PO token 미주입)
    try:
        opts = _make_ytdl_opts(ctx, fmt, url, forced_client=forced, inject_pot=False)
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
        if not info:
            raise RuntimeError("info extract fail")

        # [Layer 3 승격 판정] 분리 포맷 시도에도 1080p 미달로 수급되면
        # 720p 타협하지 않고 POT 서버로 강제 승격한다 (1회).
        if _needs_pot_promotion(ctx, info) and not ctx.state.get("canceled"):
            first_info = info
            raise _FormatQualityLoss()

        _emit_vod_success(ctx, info)
        ctx.speed_win.reset()
        return True

    except _FormatQualityLoss:
        # 화질 상실 — 아래 2차(POT 재시도)로 낙하
        ex = RuntimeError("1080p+ format loss (promoting to POT)")
    except Exception as ex:
        # 봇 차단/포맷 상실 계열이 아니면 즉시 전파
        if not _is_retryable_bot_error(ex):
            raise ex

    # 봇 차단/화질 상실 감지 → POT 서버 준비 후 1회 재시도 (Layer 3)
    raw_log.raw(
        "dl",
        _pe.emit_event(
            "DL", "WARN", "YTDL",
            f"{str(ex)[:60]} — preparing POT for retry",
        ),
        to_tui=True,
    )

    if not _ensure_pot_server_ready(ctx):
        if first_info is not None:
            # POT 미가용 — 1차 수급본을 파기하지 않고 정직하게 보고한다.
            h = _max_requested_height(first_info) or 0
            raw_log.raw(
                "dl",
                _pe.emit_event(
                    "DL", "WARN", "YTDL",
                    f"hd unavailable — kept {h}p (POT offline)",
                ),
                to_tui=True,
            )
            _emit_vod_success(ctx, first_info)
            ctx.speed_win.reset()
            return True
        raise RuntimeError("POT server unavailable for retry")

    # 2차: PO token 주입하여 순정 재호출
    opts = _make_ytdl_opts(ctx, fmt, url, forced_client=forced, inject_pot=True)
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
    if not info:
        raise RuntimeError("info extract fail (with PO token)")

    _emit_vod_success(ctx, info)
    ctx.speed_win.reset()
    return True


def _emit_vod_success(ctx, info):
    """수급 완료 포맷 라인 발행 (헤더 + 개별 스트림/최종 결과물)."""
    if not ctx._meta_logged:
        _pe.emit_download_header(ctx, info)
    for dl in info.get("requested_downloads") or []:
        _pe.log_success_info(
            ctx, dl.get("filepath") or dl.get("_filename") or ""
        )


def _max_requested_height(info):
    """수급 완료 포맷 중 최대 해상도 높이 (없으면 0)."""
    heights = []
    for dl in info.get("requested_downloads") or []:
        h = dl.get("height") or (dl.get("format") or {}).get("height") if isinstance(dl, dict) else 0
        if h:
            heights.append(int(h))
    return max(heights) if heights else 0


def _needs_pot_promotion(ctx, info):
    """1차 성공 결과가 최고 화질 목표(1080p+)를 상실했는지 판정 (v3.8.0).

    - 분리 포맷(bv*+ba) 시도가 아닌 경우(오디오 추출·수동 포맷 선택)는 대상 아님.
    - 사용자가 max_video_res로 1080p 미만을 명시 제한한 경우도 대상 아님
      (사용자 의도가 우선).
    - 수급된 최대 높이가 1080 미만이면 화질 상실로 판정 → Layer 3 승격.
    """
    if ctx.cfg.get("audio_only"):
        return False
    v_id = str(ctx.v_sel or "").strip()
    if v_id and v_id != "auto":
        return False  # 수동 포맷 선택 — 사용자 의도 존중
    res = str(ctx.cfg.get("max_video_res") or "none").strip()
    if res.isdigit():
        return False  # 사용자 해상도 제한 — 타협 아닌 의도적 제한
    return _max_requested_height(info) < 1080


def _emit_error_log(ctx, url, reason, failed_targets):
    """실패 항목 기록 전용 (v3.8.0 — TUI 즉시 출력 철폐).

    [FAIL 단일 출력] 개별 실패 라인은 finalizer.finalize()가 배치 마감 시
    딱 1회 출력한다. 여기서 즉시 출력하면 yt-dlp 원문 에러(브리지) +
    개별 라인 + 마감 요약이 3~4줄로 중복 발행되는 촌규가 된다.
    """
    failed_targets.append((url, reason))


def _is_youtube_live_url(ctx, url):
    """유튜브 URL이 라이브인지 경량 프리체크 (yt-dlp extract_info 사용)."""
    try:
        opts = {
            "logger": ctx.logger,
            "noplaylist": True,
            "skip_download": True,
            "extract_flat": False,
        }
        _apply_cookie_opts(opts, ctx.cfg)
        _apply_client_opts(opts, ctx.cfg, forced=None)  # 순정 위임
        _apply_light_analysis_opts(opts)
        _apply_ejs_opts(opts)
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return bool(info and info.get("is_live"))
    except Exception:  # noqa: BLE001
        return False


def download_target(ctx, item, failed_targets, skip_targets=None):
    """개별 항목 다운로드 — 사전 분류 스킵 및 정적 디스패치 테이블 실행.
    
    Returns:
        True: 다운로드 성공
        "skip": 시스템 사전 필터링으로 스킵됨 (skip_targets에 기록됨)
        False: 다운로드 시도했으나 실패 (failed_targets에 기록됨)
    """
    # 1. 항목 분류 및 스킵 판정
    item = _classify_item(ctx, item)

    # 2. 다운로드 불가 항목 선제 필터링 (스킵 수집 및 TUI 로그 발행)
    if not item.downloadable:
        reason = item.skip_reason or "ineligible"
        _emit_skip_log(ctx, item, reason)
        if skip_targets is not None:
            skip_targets.append((item.url, reason))
        return "skip"

    # 3. URL 정규 문자열 추출
    url = item.url

    # 4. ContentKind 기반 정적 디스패치 (중복 regex 전면 철폐!)
    try:
        if item.kind == ContentKind.CLIP:
            return _download_chzzk(ctx, url, "clip")

        if item.kind == ContentKind.LIVE_CHZZK:
            return _download_chzzk_live(ctx, url)

        if item.kind == ContentKind.LIVE_YOUTUBE:
            return _download_youtube_live(ctx, url)

        if item.kind == ContentKind.VOD:
            if item.platform_tag == "CHZ":
                return _download_chzzk(ctx, url, "vod")
            return _download_vod(ctx, url)

        # UNKNOWN 또는 기타 플랫폼 폴백
        return _download_vod(ctx, url)

    # 5. 에러 분류 정교화 (봇 차단 vs 터미널 실패 vs 네트워크)
    except YtDownloadError as de:
        err_str = str(de).lower()
        if any(term in err_str for term in _TERMINAL_FAIL_MARKERS):
            reason = "unavailable"
        elif any(bot in err_str for bot in _RETRYABLE_BOT_MARKERS):
            reason = "age/bot restricted"
        elif "requested format not available" in err_str:
            reason = "format missing"
        else:
            reason = f"blocked ({str(de)[:40]})"

        _emit_error_log(ctx, url, reason, failed_targets)
        return False

    except (ConnectionError, TimeoutError, OSError) as net_ex:
        reason = f"net err ({type(net_ex).__name__})"
        _emit_error_log(ctx, url, reason, failed_targets)
        return False

    except Exception as ex:  # noqa: BLE001
        reason = f"err ({type(ex).__name__}: {str(ex)[:40]})"
        _emit_error_log(ctx, url, reason, failed_targets)
        return False


def _has_configured_cookies(cfg: dict) -> bool:
    """쿠키가 실제 yt-dlp에 주입되는지 판정 (_apply_cookie_opts와 동일 로직)."""
    browser = str(cfg.get("browser_cookie", "none") or "none").lower()
    # 브라우저 쿠키: none/auto/cookie_file 외 값이면 쿠키 있음
    if browser not in ("none", "auto", "cookie_file"):
        return True
    # cookie_file 모드: 파일이 존재해야만 쿠키 있음
    if browser == "cookie_file":
        cookie_file = str(cfg.get("cookie_file_path", "") or "").strip()
        return bool(cookie_file and os.path.exists(cookie_file))
    return False


def _emit_skip_log(ctx, item: ClassifiedTarget, reason: str) -> None:
    """TUI 고정 규격: DL │ SKIP │ SCOPE │ [reason] title 발행."""
    title_short = item.title[:35] + ("..." if len(item.title) > 35 else "")
    raw_log.raw(
        "dl",
        _pe.emit_event("DL", "SKIP", item.platform_tag, f"[{reason}] {title_short}"),
        to_tui=True,
    )


def _classify_item(ctx, raw_target: ClassifiedTarget | str | dict) -> ClassifiedTarget:
    """항목 정규화 및 I/O 격리 쿠키 정책 검증기.
    
    입력: ClassifiedTarget | dict | str(URL)
    출력: ClassifiedTarget (파이프라인 단일 계약)
    """
    # 1. ClassifiedTarget 규격 승격
    if isinstance(raw_target, ClassifiedTarget):
        item = raw_target
    elif isinstance(raw_target, dict):
        # dict에서 URL과 메타데이터 추출
        url = raw_target.get("url", "")
        raw_info = {k: v for k, v in raw_target.items() if k != "url"}
        item = ItemClassifier.classify(url, raw_info=raw_info)
    else:
        # str(URL)인 경우
        item = ItemClassifier.classify(str(raw_target))

    # 2. 이미 다운로드 불가로 마킹된 항목 (이미지 전용 등) 조기 반환
    if not item.downloadable:
        return item

    # 3. 인증 요구사항 교차 검증 (도메인 정책 vs 현재 런타임 cfg)
    if item.capability.requires_auth and not _has_configured_cookies(ctx.cfg):
        return ClassifiedTarget(
            url=item.url,
            title=item.title,
            kind=item.kind,
            capability=item.capability,
            platform_tag=item.platform_tag,
            downloadable=False,
            needs_pot=item.needs_pot,
            skip_reason="age/member gated",
            metadata=item.metadata,
        )

    return item


def _flatten(ctx, url: str) -> list[ClassifiedTarget]:
    """yt-dlp extract_flat 기반 재생목록/채널 평탄화.
    
    [원칙 준수]
    - 어설픈 하드코딩 dict 날조 금지: entries의 원시 메타를 ItemClassifier에 그대로 위임.
    - extract_flat 환경에서는 StreamCapability.indeterminate()가 자동 적용되어
      has_video/has_audio=None (미정) 상태가 거짓말 없이 정직하게 보존된다.
    """
    opts = {
        "logger": ctx.logger,
        "extract_flat": True,
        "skip_download": True,
        "noplaylist": False,
        "socket_timeout": 30,
    }
    _apply_cookie_opts(opts, ctx.cfg)
    _apply_client_opts(opts, ctx.cfg, forced=None)  # 순정 위임
    _apply_light_analysis_opts(opts)
    _apply_ejs_opts(opts)

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
        entries = (info or {}).get("entries") or []
        targets: list[ClassifiedTarget] = []

        for e in entries:
            if not e:
                continue
            # yt-dlp flat 추출 시 url 또는 webpage_url 필드 참조
            target_url = e.get("url") or e.get("webpage_url")
            if not target_url:
                continue
            
            # YouTube ID만 떨어진 경우 정규 URL로 복원
            if not target_url.startswith("http"):
                target_url = f"https://www.youtube.com/watch?v={target_url}"

            # 1단계 ItemClassifier에 위임하여 TriState(None) 메타데이터 보존 객체 생성
            classified = ItemClassifier.classify(target_url, raw_info=e)
            targets.append(classified)

        return targets


def expand_targets(ctx) -> list[ClassifiedTarget]:
    """재생목록/채널 URL을 개별 동영상 항목 객체로 펼친다.
    
    반환: List[ClassifiedTarget] - 파이프라인 전체가 공유하는 단일 계약
    """
    expanded: list[ClassifiedTarget] = []
    for url in ctx.targets:
        try:
            urls: list[ClassifiedTarget] | None = None
            if detect_content_type(url) == "playlist":
                urls = _flatten(ctx, url)
            else:
                u = url.lower()
                if "/@" in u or "/channel/" in u or "/c/" in u or "/user/" in u:
                    urls = _flatten(ctx, normalize_youtube_channel_url(url))
            
            if urls:
                # _flatten이 이미 List[ClassifiedTarget] 반환
                expanded.extend(urls)
            else:
                # 단일 영상 - 정규화 팩토리를 통해 즉시 승격
                expanded.append(_normalize_single_item(url))
        except Exception as ex:  # noqa: BLE001
            url_short = url[:40] + ("..." if len(url) > 40 else "")
            # [v3.8.1] 즉시 TUI 발행 금지 — finalizer에서 단일 출력
            _emit_error_log(ctx, url, str(ex), failed_targets=[])
            expanded.append(_normalize_single_item(url))

    return expanded


def _normalize_single_item(url: str) -> ClassifiedTarget:
    """단일 영상 URL을 ClassifiedTarget으로 정규화 (메타는 다운로드 단계에서 채움)."""
    return ItemClassifier.classify(url, raw_info=None)
```

## File: chzzktube/infra/__init__.py

```python

```

## File: chzzktube/infra/cleanup.py

```python
"""프로비저닝 아티팩트 정리 유틸리티.

앱 기동 시 또는 종료 시 호출하여 .part 파일, 아카이브, 락 파일 등을 정리한다.
"""
import os
import glob
import shutil
from chzzktube.core import config


def cleanup_provisioning_artifacts():
    """수급 과정에서 생성된 임시 파일/락 파일 정리."""
    base = config.writable_base()
    if not os.path.isdir(base):
        return

    # 1. ffmpeg .part 파일 정리
    ffmpeg_dir = os.path.join(base, "ffmpeg")
    if os.path.isdir(ffmpeg_dir):
        for part_file in glob.glob(os.path.join(ffmpeg_dir, "*.part")):
            try:
                os.remove(part_file)
            except Exception:
                pass

    # 2. node 아카이브 정리 (node_portable.zip/tar.gz)
    for archive in glob.glob(os.path.join(base, "node_portable.*")):
        try:
            if os.path.isfile(archive):
                os.remove(archive)
            elif os.path.isdir(archive):
                shutil.rmtree(archive, ignore_errors=True)
        except Exception:
            pass

    # 3. pot prewarm 락 파일 정리
    pot_dir = os.path.join(base, "pot")
    if os.path.isdir(pot_dir):
        lock_file = os.path.join(pot_dir, ".prewarm.lock")
        if os.path.isfile(lock_file):
            try:
                os.remove(lock_file)
            except Exception:
                pass

    # 4. components 루트의 .part 파일 정리 (Homebrew bottle 다운로드 등)
    from chzzktube.infra.components import components_root
    comp_root = components_root()
    if os.path.isdir(comp_root):
        for part_file in glob.glob(os.path.join(comp_root, "*.part")):
            try:
                os.remove(part_file)
            except Exception:
                pass
        # ffmpeg 아카이브 정리
        for archive in glob.glob(os.path.join(comp_root, "ffmpeg*.tar.xz")):
            try:
                os.remove(archive)
            except Exception:
                pass
        for archive in glob.glob(os.path.join(comp_root, "ffmpeg*.zip")):
            try:
                os.remove(archive)
            except Exception:
                pass

    # 5. 임의의 .part 파일 정리 (전역)
    for part_file in glob.glob(os.path.join(base, "*.part")):
        try:
            os.remove(part_file)
        except Exception:
            pass


def cleanup_on_startup():
    """앱 기동 시 호출 — 이전 세션 잔재 정리."""
    cleanup_provisioning_artifacts()


def cleanup_on_shutdown():
    """앱 종료 시 호출 — 현재 세션 잔재 정리."""
    cleanup_provisioning_artifacts()
```

## File: chzzktube/infra/components.py

```python
﻿### components.py - ffmpeg runtime manager
"""ffmpeg 자동 수급/관리 전용 모듈 — 앱 전용 격리 캐시 (v3.8.0).

*  [격리 원칙] 시스템 PATH 탐색(shutil.which)·OS 패키지 매니저(brew install,
   apt-get 등) 서브프로세스 호출 완전 철폐. 오직 writable_base()/ffmpeg/
   단일 캐시만 검사하고, 없으면 정적 바이너리를 직접 수급한다.
*  Windows: GitHub(GyanD/codexffmpeg) release zip → writable_base/ffmpeg/
*  macOS: Homebrew bottle HTTP 직접 다운로드 (brew 실행 없음)
*  Linux: johnvansickle.com 정적 빌드 tar.xz

[전수조사 정리 2026-09-04] 구 설계(Hitomi Downloader style 전체 구성요소
자동수급: yt-dlp 휠 / bgutil 플러그인 / pot-pack / streamlink-pack)는
main.py에 연결된 적이 없는 죽은 코드였음 — 실제 의존 흐름은
venv pip(yt-dlp / streamlink) + pot_provider(bgutil 서버 빌드) + 본 모듈.
"""
import hashlib
import json
import os
import platform
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

import chzzktube.core.config as config
from chzzktube.core.log_emitter import emit_component, emit_event, emit_dl, emit_error_standard, emit_error_warn

_UA = "ChzzkTube-Components/1.0"


def components_root():
    """구성요소 전개 루트 — SSOT: writable_base()/components 단일 경로 (v3.8.2).

    [SSOT 원칙] frozen과 source 모두 writable_base() 하위를 사용.
    - frozen 시 <exe>/components 경로 참조 완전 제거
    - 환경변수 CHZZKTUBE_COMPONENTS_DIR로만 오버라이드
    """
    env = os.environ.get("CHZZKTUBE_COMPONENTS_DIR")
    if env:
        return env
    return os.path.join(config.writable_base(), "components")



def _logcb(log):
    return log if callable(log) else (lambda *a, **k: None)


def _http_get(url, timeout=30):
    """HTTP GET 요청, ghcr.io는 토큰 인증 자동 처리."""
    headers = {"User-Agent": _UA}
    if "ghcr.io" in url:
        try:
            token = _ghcr_token("repository:homebrew/core/ffmpeg:pull")
            headers["Authorization"] = f"Bearer {token}"
        except Exception:
            pass
    req = urllib.request.Request(url, headers=headers)
    return urllib.request.urlopen(req, timeout=timeout)


def _ghcr_token(scope):
    """ghcr.io 익명 토큰 획득."""
    url = f"https://ghcr.io/token?scope={scope}"
    with urllib.request.urlopen(url, timeout=15) as resp:
        data = json.load(resp)
    return data.get("token")


def _download(url, dest, log, label="", is_status=False):
    """파일 다운로드(진행 로그 포함). 성공 시 dest 경로 반환.
    
    is_status=True 면 진행률 로그를 상태 줄로 표시 (이전 줄 덮어쓰기).
    """
    log(emit_component("DEPS", "RUN", "DEPS", f"{label or os.path.basename(url)} fetching..."), is_status)
    tmp = dest + ".part"
    with _http_get(url, timeout=60) as resp, open(tmp, "wb") as f:
        total = int(resp.headers.get("Content-Length") or 0)
        done, last_mb = 0, -1
        while True:
            chunk = resp.read(1024 * 512)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            mb = done // (1024 * 1024)
            # 진행률 로그 빈도 조절: 8MB 이상 파일은 2MB마다, 미만은 완료 시에만
            if total < 8 * 1024 * 1024 or mb != last_mb and mb % 2 == 0:
                last_mb = mb
                pct = f" ({done * 100 // total}%)" if total else ""
                log(emit_component("DEPS", "RUN", "DEPS", f"{label or 'download'} {mb} MB{pct}"), is_status)
    os.replace(tmp, dest)
    log(emit_component("DEPS", "OK", "DEPS", f"{label or os.path.basename(dest)} done ({done / 1048576:.1f} MB)"))
    return dest


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _rmtree(p):
    shutil.rmtree(p, ignore_errors=True)


def _exe_suffix():
    """현재 OS의 실행 파일 확장자를 반환한다."""
    from chzzktube.infra.platform import exe_suffix

    return exe_suffix()


def _extract_zip(zip_path, dest_dir, log, label, promote_single_root=False):
    """zip 을 임시 폴더에 풀고 완성 후 dest_dir 로 교체 (실패 시 기존 버전 보존).

    promote_single_root=True 면 zip 최상위에 폴더 하나만 있을 때(예: zipball 루트
    bgutil-ytdlp-pot-provider-1.3.2/) 그 내부를 dest_dir 로 승격한다.
    """
    tmp = dest_dir + ".tmp"
    _rmtree(tmp)
    os.makedirs(os.path.dirname(tmp) or ".", exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(tmp)
    if promote_single_root:
        entries = os.listdir(tmp)
        if len(entries) == 1 and os.path.isdir(os.path.join(tmp, entries[0])):
            inner = os.path.join(tmp, entries[0])
            _rmtree(dest_dir)
            shutil.move(inner, dest_dir)
            _rmtree(tmp)
    else:
        for entry in os.listdir(tmp):
            s = os.path.join(tmp, entry)
            d = os.path.join(dest_dir, entry)
            if os.path.isdir(d):
                shutil.rmtree(d, ignore_errors=True)
            os.makedirs(os.path.dirname(d) or ".", exist_ok=True)
            shutil.move(s, d)
        _rmtree(tmp)
    log(emit_component("DEPS", "OK", "DEPS", f"{label} extracted → {os.path.relpath(dest_dir, components_root())}"))


FFMPEG_DIRNAME = "ffmpeg"
# GitHub 릴리즈 URL: 버전 명시 (latest 사용 시 source code를 가리켜 404 발생)
FFMPEG_RELEASE_URL = (
    "https://github.com/GyanD/codexffmpeg/releases/download/7.1/"
    "ffmpeg-7.1-essentials.zip"
)
_FFMPEG_BREW_API = "https://formulae.brew.sh/api/formula/ffmpeg.json"

# [macOS] Homebrew bottle 키 선정 (v3.8.1) — formulae.brew.sh 응답의 실제
# bottle 키에서 arch prefix 매치로 선택한다. 과거처럼 OS 버전→키 하드코딩
# 테이블을 두면 신형 macOS(15.x Tahoe/Sequoia 등) 키가 누락되어
# "no compatible Homebrew bottle" FAIL이 난다.
# 실측(2026-09): arm64_tahoe / arm64_sequoia / arm64_golden_gate / arm64_linux.
#
# [중요] 현행 formulae(ffmpeg 9.x) bottle은 실행 중 OS에서 dyld 심볼 에러로
# 실행 불가할 수 있다 (Tahoe 26.x SDK 빌드 / Sequoia 빌드라도 깨진 dylib 링크).
# 따라서 bottle 전멸 시 evermeet.cx 정적 빌드로 최종 폴백한다.
_MAC_BOTTLE_ARCH_PREFIX = {
    "arm64": "arm64_",
    "x86_64": "x86_64_",
}
_MAC_BOTTLE_BUILDNUM_ORDER = (
    # (bottle 키 포함 문자열, 빌드 번호) — 낮을수록 구형 OS에서 실행 가능
    ("catalina", 19),
    ("big_sur", 20),
    ("monterey", 21),
    ("ventura", 22),
    ("sonoma", 23),
    ("sequoia", 24),
    ("tahoe", 26),
)
# [macOS 최종 폴백] evermeet.cx 정적 빌드 (Homebrew bottle 전멸 시).
# evermeet.cx가 DNS로 안 풀리는 환경도 있으므로 redirector(getrelease) +
# 버전별 직링크를 순서대로 시도한다. universal2 바이너리는 arm64·x86_64
# (Rosetta2) 모두에서 실행된다. 외부망 차단 환경에서는 전부 실패할 수
# 있으며, 그 경우 격리 캐시는 비게 된다 (시스템 복사는 §6 금지).
_FFMPEG_EVERMEET_URLS = (
    "https://evermeet.cx/ffmpeg/getrelease/ffmpeg/zip",
    "https://evermeet.cx/ffmpeg/ffmpeg-7.1.1.zip",
    "https://evermeet.cx/ffmpeg/ffmpeg-7.0.2.zip",
)


def _macos_buildnum():
    """실행 중 macOS의 Darwin major 번호 — bottle 호환 상한 판정용.

    예: macOS 15.7.4 → platform.release() '24.6.0' → 24.
    판별 실패 시 None (호환 필터 생략 — 기존 동작 유지).
    """
    try:
        return int(str(platform.release()).split(".")[0])
    except (ValueError, IndexError):
        return None


def _macos_bottle_keys(files=None):
    """현재 아키텍처에 맞는 Homebrew bottle 키 목록 (우선순위순).

    formulae.brew.sh 응답의 실제 bottle 키에서 arch prefix로 매치한다 —
    OS 버전→키 하드코딩 테이블을 쓰지 않으므로 신형 macOS에도 내성.
    `files=None`이면 이 머신의 arch prefix 단일 키로 폴백(오프라인 안전).
    """
    arch = platform.machine()  # 'arm64' or 'x86_64'
    prefix = _MAC_BOTTLE_ARCH_PREFIX.get(arch, "arm64_")
    if not files:
        return [prefix + "sonoma", prefix.rstrip("_")]
    candidates = [k for k in files if k.startswith(prefix) and "linux" not in k]
    # [호환성] 실행 중 OS(Darwin major)보다 새 SDK로 빌드된 bottle은 dyld
    # 심볼 에러로 실행 불가 → 호환 키만 남기고, 그 중 최신 세대부터 시도.
    buildnum = _macos_buildnum()

    def _gen_buildnum(key):
        low = key.lower()
        for gen, num in _MAC_BOTTLE_BUILDNUM_ORDER:
            if gen in low:
                return num
        return None

    if buildnum is not None:
        compat = [k for k in candidates if (_gen_buildnum(k) or 0) <= buildnum]
        if compat:
            candidates = compat
    # 최신 세대부터 (번호 내림차순), 미지의 키(golden_gate 등)는 번호 미상이므로
    # 실제 실행 검증(_verify_ffmpeg) 이후 순위로 — 호환 목록 뒤에 배치.
    known = [k for k in candidates if _gen_buildnum(k) is not None]
    unknown = [k for k in candidates if _gen_buildnum(k) is None]
    known.sort(key=lambda k: _gen_buildnum(k), reverse=True)
    return known + unknown



def ensure_ffmpeg(log=None, force=False):
    """ffmpeg 자동 수급 — 앱 전용 격리 캐시 단일 경로 (v3.8.0).

    [퍼사드 함수] 외부(pot_provider 등)에서 호출하는 단일 진입점.
    성공 시 None, 실패 시 오류 문자열.

    OS별 처리 (시스템 PATH/패키지 매니저 참조 없음):
    - Windows: 캐시 → GitHub GyanD/codexffmpeg zip 다운로드
    - macOS: 캐시 → Homebrew bottle HTTP 직접 다운로드
    - Linux: 캐시 → johnvansickle.com 정적 빌드 다운로드
    """
    log = _logcb(log)
    log(emit_component("DEPS", "RUN", "FFMP", "checking..."))
    try:
        # 1. 로컬 격리 캐시 확인
        cached = ffmpeg_exe()
        if cached and not force:
            if _verify_ffmpeg(cached):
                _wire_ffmpeg_path(os.path.dirname(cached))
                log(emit_component("DEPS", "OK", "FFMP", "ok"))
                return None
            log(emit_component("DEPS", "WARN", "FFMP", f"cached not working ({cached})"))
            # 파손된 캐시는 제거 후 재수급
            dest = os.path.join(config.writable_base(), FFMPEG_DIRNAME)
            _rmtree(dest)

        # 2. OS별 정적 바이너리 수급
        return _ensure_ffmpeg_by_platform(log, force)
    except Exception as e:
        return f"{type(e).__name__}: {e}"

def _ensure_ffmpeg_by_platform(log, force):
    """플랫폼에 따라 적절한 전략 함수에 위임 (전략 패턴)."""
    platform = sys.platform
    if platform == "win32":
        return _ensure_ffmpeg_windows(log, force)
    elif platform == "darwin":
        return _ensure_ffmpeg_macos(log, force)
    elif platform.startswith("linux"):
        return _ensure_ffmpeg_linux(log, force)
    else:
        return f"Unsupported OS: {platform}"


def _ensure_ffmpeg_windows(log, force):
    """Windows용 ffmpeg 자동 수급 - GitHub GyanD/codexffmpeg 정적 zip 다운로드.

    [v3.8.0 격리] 시스템 PATH 참조 없음 — 캐시는 ensure_ffmpeg 선검.
    """
    dest = os.path.join(config.writable_base(), FFMPEG_DIRNAME)
    bin_dir = os.path.join(dest, "bin")
    exe_path = os.path.join(bin_dir, "ffmpeg.exe")

    # GitHub에서 다운로드
    os.makedirs(dest, exist_ok=True)
    log(emit_component("DEPS", "RUN", "FFMP", "downloading..."))

    with tempfile.TemporaryDirectory(prefix="cz_ffmpeg_") as td:
        zp = _download(FFMPEG_RELEASE_URL, os.path.join(td, "ffmpeg.zip"), log, "ffmpeg")
        _extract_zip(zp, dest, log, "ffmpeg", promote_single_root=True)

    if os.path.isfile(exe_path):
        _wire_ffmpeg_path(bin_dir)
        log(emit_component("DEPS", "OK", "FFMP", "ok"))
        return None

    return "ffmpeg.exe not found after extract"


def _ensure_ffmpeg_macos(log, force):
    """맥용 ffmpeg 자동 수급 - Homebrew bottle HTTP 직접 다운로드 (v3.8.0).

    [격리] `brew` 서브프로세스 실행 철폐 — formulae.brew.sh API에서 bottle
    tar.gz URL을 받아 SHA-256 검증 후 직접 수급한다 (시스템 무간섭).
    """
    dest = os.path.join(config.writable_base(), FFMPEG_DIRNAME)

    try:
        log(emit_component("DEPS", "RUN", "FFMP", "downloading (Homebrew bottle)..."))
        with urllib.request.urlopen(_FFMPEG_BREW_API, timeout=15) as resp:
            data = json.load(resp)

        bottle = data.get("bottle", {}).get("stable", {})
        files = bottle.get("files", {})

        keys = _macos_bottle_keys(files)
        selected = None
        for key in keys:
            if key in files:
                selected = files[key]
                break

        if not selected:
            return "no compatible Homebrew bottle for this macOS version/arch"

        # 후보 키를 호환 순서대로 전부 시도한다 (SHA 불일치·실행 불가
        # bottle은 다음 후보로 폴백 — Tahoe 빌드의 구형 OS dyld abort 대응).
        # [인증] ghcr.io blob 다운로드는 Bearer 토큰 필수 — _http_get이 자동 처리.
        last_err = None
        for key in keys:
            entry = files.get(key) or {}
            url = entry.get("url")
            sha256 = entry.get("sha256")
            if not url:
                last_err = "Homebrew bottle URL missing"
                continue
            try:
                with tempfile.TemporaryDirectory(prefix="cz_ffmpeg_") as td:
                    tar_path = os.path.join(td, "ffmpeg.tar.gz")
                    with _http_get(url, timeout=60) as resp, open(tar_path, "wb") as f:
                        total = int(resp.headers.get("Content-Length") or 0)
                        done = 0
                        last_mb = -1
                        while True:
                            chunk = resp.read(1024 * 512)
                            if not chunk:
                                break
                            f.write(chunk)
                            done += len(chunk)
                            mb = done // (1024 * 1024)
                            if total >= 8 * 1024 * 1024 and mb != last_mb and mb % 2 == 0:
                                last_mb = mb
                                pct = f" ({done * 100 // total}%)" if total else ""
                                log(emit_component("DEPS", "RUN", "FFMP", f"ffmpeg [{key}] {mb} MB{pct}"), True)
                    if total and done != total:
                        last_err = f"ffmpeg [{key}] download incomplete"
                        continue
                    log(emit_component("DEPS", "OK", "FFMP", f"ffmpeg [{key}] done ({done / 1048576:.1f} MB)"))

                    if sha256:
                        got = _sha256(tar_path)
                        if got != sha256:
                            last_err = f"ffmpeg bottle hash mismatch [{key}]"
                            continue
                        log(emit_component("DEPS", "OK", "FFMP", "SHA-256 ok"))

                    log(emit_component("DEPS", "RUN", "FFMP", "extracting..."))
                    # 기존 디렉토리를 완전히 삭제
                    if os.path.exists(dest):
                        shutil.rmtree(dest, ignore_errors=True)
                    os.makedirs(dest, exist_ok=True)

                    # subprocess로 tar 명령어 직접 실행
                    import subprocess
                    result = subprocess.run(
                        ["tar", "-xzf", tar_path, "-C", dest],
                        capture_output=True,
                        text=True,
                        timeout=120
                    )
                    if result.returncode != 0:
                        last_err = f"tar extraction failed [{key}]"
                        continue

                    # bottle 추출 구조에서 ffmpeg 검색
                    ffmpeg_src = None
                    ffmpeg_bin_dir = None
                    for root, dirs, names in os.walk(dest):
                        if "ffmpeg" in names:
                            candidate = os.path.join(root, "ffmpeg")
                            if os.path.isfile(candidate):
                                ffmpeg_src = candidate
                                ffmpeg_bin_dir = root
                                break

                    if ffmpeg_src and ffmpeg_bin_dir:
                        # 원래 디렉토리 구조를 유지하고 PATH에 추가
                        _wire_ffmpeg_path(ffmpeg_bin_dir)
                        # [macOS] Gatekeeper quarantine 해제 + 실행 비트 보장
                        if platform.system() == "Darwin":
                            for _bin in ("ffmpeg", "ffprobe"):
                                _bp = os.path.join(ffmpeg_bin_dir, _bin)
                                if os.path.isfile(_bp):
                                    try:
                                        subprocess.run(["chmod", "+x", _bp],
                                                       check=False, capture_output=True)
                                        subprocess.run(
                                            ["xattr", "-dr", "com.apple.quarantine", _bp],
                                            check=False, capture_output=True)
                                    except Exception:
                                        pass
                        # 설치 확인 — 실패하면 다음 후보 키로 폴백
                        if _verify_ffmpeg(ffmpeg_src):
                            log(emit_component("DEPS", "OK", "FFMP", "ok"))
                            return None
                        last_err = (
                            f"ffmpeg [{key}] not runnable on this macOS — trying older bottle"
                        )
                        log(emit_error_warn("DEPS", "FFMP", "binary incompatible", "retry mirror (1/3)"))
                        if os.path.exists(dest):
                            shutil.rmtree(dest, ignore_errors=True)
                        continue
                    last_err = f"ffmpeg exe not found after extract [{key}]"
            except Exception as e:  # noqa: BLE001 — 후보별 폴백
                last_err = f"ffmpeg [{key}] install failed: {type(e).__name__}"
                continue
        # bottle 전멸 — evermeet.cx 정적 빌드로 최종 폴백 (실측 2026-09:
        # formulae 9.x arm64 bottle 3종 전부 현행 15.7.4에서 dyld abort).
        ever_err = _ensure_ffmpeg_macos_static(log, dest)
        if ever_err is None:
            return None
        # [계약] ensure_ffmpeg는 실패 시 문자열 반환 (LogEvent 아님)
        return "all mirrors exhausted"
    except Exception as e:
        return f"{type(e).__name__}: {e}"


def _fetch_url(url, dest_path, timeout=60):
    """단일 파일 다운로드 — 302 redirector(getrelease) 추적 지원.

    _http_get(단일 GET, 리다이렉트 미추적)과 달리 표준 opener로 리다이렉트를
    따라간다. evermeet.cx getrelease가 302를 반환하므로 정적 폴백 전용.
    """
    opener = urllib.request.build_opener(urllib.request.HTTPRedirectHandler())
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with opener.open(req, timeout=timeout) as resp, open(dest_path, "wb") as f:
        while True:
            chunk = resp.read(1024 * 512)
            if not chunk:
                break
            f.write(chunk)


def _ensure_ffmpeg_macos_static(log, dest):
    """macOS 최종 폴백 — evermeet.cx 정적 빌드 단일 바이너리 수급.

    bottle 전멸(dyld 실행 불가) 시에만 진입. 3종 URL을 순서대로 시도하고,
    실행 검증(_verify_ffmpeg) 통과본만 캐시한다.
    성공 시 None, 실패 시 오류 문자열.
    """
    try:
        from chzzktube.infra.platform import is_windows as _is_win

        if _is_win():
            return "static fallback is macOS-only"
        urls = _FFMPEG_EVERMEET_URLS
        last_err = None
        for url in urls:
            try:
                log(emit_component("DEPS", "RUN", "FFMP", f"downloading (static) {os.path.basename(url) or 'latest'}..."))
                with tempfile.TemporaryDirectory(prefix="cz_ffmpeg_") as td:
                    zp = os.path.join(td, "ffmpeg.zip")
                    # redirector(getrelease)는 302를 반환하므로 _http_get이 아닌
                    # 리다이렉트 추적 opener 사용
                    _fetch_url(url, zp)
                    _extract_zip(zp, dest, log, "ffmpeg", promote_single_root=True)
                cand = os.path.join(dest, "ffmpeg")
                if not os.path.isfile(cand):
                    for root, _dirs, names in os.walk(dest):
                        if "ffmpeg" in names:
                            cand = os.path.join(root, "ffmpeg")
                            break
                if os.path.isfile(cand):
                    try:
                        os.chmod(cand, 0o755)
                    except OSError:
                        pass
                    _wire_ffmpeg_path(os.path.dirname(cand))
                    if _verify_ffmpeg(cand):
                        log(emit_component("DEPS", "OK", "FFMP", "ok (static)"))
                        return None
                    last_err = f"static {os.path.basename(url)} not runnable"
                    continue
                last_err = f"static {os.path.basename(url)} missing binary"
            except Exception as e:  # noqa: BLE001 — URL별 폴백
                last_err = f"static {os.path.basename(url)} failed: {type(e).__name__}"
                continue
        return last_err or "static fallback failed"
    except Exception as e:
        return f"{type(e).__name__}: {e}"
    except Exception as e:
        return f"{type(e).__name__}: {e}"

def ffmpeg_exe():
    """ffmpeg 실행 파일 경로 — 앱 전용 격리 캐시 단일 참조 (v3.8.0).

    [격리 원칙] 시스템 PATH 폴백(shutil.which) 철폐 — writable_base()/ffmpeg
    캐시에 없으면 None을 반환한다 (ensure_ffmpeg가 수급을 담당).
    """
    from chzzktube.infra.platform import exe_suffix

    exe_name = f"ffmpeg{exe_suffix()}"
    # 기존 위치 (bin_dir) 확인
    local = os.path.join(
        config.writable_base(), FFMPEG_DIRNAME, "bin", exe_name
    )
    if os.path.isfile(local) and os.access(local, os.X_OK):
        return local
    # Homebrew bottle 추출 디렉토리에서 검색
    dest = os.path.join(config.writable_base(), FFMPEG_DIRNAME)
    if os.path.isdir(dest):
        for root, dirs, files in os.walk(dest):
            if exe_name in files:
                candidate = os.path.join(root, exe_name)
                if os.access(candidate, os.X_OK):
                    return candidate
    return None


def _ensure_ffmpeg_linux(log, force):
    """리눅스용 ffmpeg 자동 수급 - 정적 빌드 다운로드 (v3.8.0).

    [격리] 시스템 패키지 매니저(apt/dnf/pacman) 서브프로세스 철폐 —
    johnvansickle.com의 정적 빌드를 어떤 배포판에서도 직접 수급한다.
    """
    dest = os.path.join(config.writable_base(), FFMPEG_DIRNAME)

    # 정적 빌드 다운로드 (johnvansickle.com)
    try:
        log(emit_component("DEPS", "RUN", "FFMP", "downloading (static build)..."))
        url = "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"
        with tempfile.TemporaryDirectory(prefix="cz_ffmpeg_") as td:
            tar_path = os.path.join(td, "ffmpeg.tar.xz")
            _download(url, tar_path, log, "ffmpeg", is_status=True)

            log(emit_component("DEPS", "RUN", "FFMP", "extracting..."))
            if os.path.exists(dest):
                shutil.rmtree(dest, ignore_errors=True)
            os.makedirs(dest, exist_ok=True)

            # tar.xz 압축 해제
            import tarfile
            with tarfile.open(tar_path, "r:xz") as tar:
                # ffmpeg와 ffprobe만 추출
                for member in tar.getmembers():
                    if member.name.endswith("/ffmpeg") or member.name.endswith("/ffprobe"):
                        member.name = os.path.basename(member.name)
                        tar.extract(member, dest)

            # 실행 권한 보장
            ffmpeg_bin = os.path.join(dest, "ffmpeg")
            if os.path.isfile(ffmpeg_bin):
                os.chmod(ffmpeg_bin, 0o755)
                if _verify_ffmpeg(ffmpeg_bin):
                    _wire_ffmpeg_path(dest)
                    log(emit_component("DEPS", "OK", "FFMP", "ok"))
                    return None

        return "ffmpeg binary not found after extract"
    except Exception as e:
        return f"linux ffmpeg install failed: {type(e).__name__}: {e}"


def _wire_ffmpeg_path(bin_dir):
    """수급/캐시된 ffmpeg bin을 프로세스 PATH 선두에 연결.

    media.py·downloader.py가 subprocess로 bare 'ffmpeg'를 호출하므로, 이 세션의
    자식 프로세스가 격리 캐시의 수급본을 즉시 사용하게 한다. [격리] 연결되는
    경로는 항상 writable_base()/ffmpeg 하위뿐이다 — 시스템 설치물은 대상 아님.
    """
    try:
        if os.path.isdir(bin_dir):
            path_env = os.environ.get("PATH", "")
            parts = path_env.split(os.pathsep) if path_env else []
            if bin_dir not in parts:
                os.environ["PATH"] = os.pathsep.join([bin_dir] + parts)
    except Exception:
        pass

def _verify_ffmpeg(ffmpeg_path):
    """ffmpeg이 실제로 실행 가능한지 확인."""
    import subprocess
    try:
        result = subprocess.run(
            [ffmpeg_path, "-version"],
            capture_output=True,
            timeout=10
        )
        return result.returncode == 0
    except Exception:
        return False



```

## File: chzzktube/infra/node_provider.py

```python
"""Node.js 런타임 수급 전용 모듈 (SSOT: writable_base()/node 단일 경로).

- node_exe / node_major_version / npm_exe : node 실행 파일 탐색
- node_ok / ensure_node_runtime : bgutil 요구 버전 충족 검증·자동 수급
- bundled_npm_ok : 포터블 npm 무결성 검사

[SSOT 원칙 v3.8.2]
- 오직 writable_base()/node/ 단일 경로만 읽기/쓰기
- frozen 번들(_MEIPASS, _internal), bundle_root, 시스템 PATH 탐색 완전 제거
- 수급은 ProvisioningManager(bridge) 위임 — 이 모듈은 경로 판정만 담당

서버 기동/빌드/소스 수급은 pot_server.py가 담당.
"""
import json
import os
import platform
import re
import subprocess
import urllib.request

import chzzktube.core.config as config
from chzzktube.infra.paths import get_writable_base


# ── 상수 (node_provider 전용) ──────────────────────────────────────
NODE_MIN_MAJOR = 22  # bgutil 서버의 Node 요구사항 (require(esm) 기본 지원선)
_NODE_FALLBACK_VER = "v22.23.2"  # nodejs.org index 조회 실패 시 폴백 (v22 LTS)
# [HAL 이관] _NO_WINDOW는 하위 호환 별칭 — 실체는 platform.spawn_kwargs().
# pot_provider가 `from node_provider import _NO_WINDOW`로 재수출하므로 유지.
_NO_WINDOW = 0
_node_ver_cache: dict = {}


def node_major_version(node_path, timeout=10):
    """node --version 출력에서 major 버전 추출 (판별 실패 시 None, 결과 캐시)."""
    if not node_path:
        return None
    if node_path in _node_ver_cache:
        return _node_ver_cache[node_path]
    major = None
    try:
        from chzzktube.infra.platform import spawn_kwargs

        out = subprocess.run(
            [node_path, "--version"],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=timeout, **spawn_kwargs(),
        )
        m = re.match(r"v?(\d+)", (out.stdout or "").strip())
        if m:
            major = int(m.group(1))
    except Exception:
        major = None
    _node_ver_cache[node_path] = major
    return major


def latest_lts_node_url(major=NODE_MIN_MAJOR):
    """nodejs.org dist index에서 지정 major의 최신 플랫뷸 URL (조회 실패 시 폴백).

    [호환 유지] ProvisioningManager._fetch_from_nodejs가 사용.
    """
    try:
        with urllib.request.urlopen(
            "https://nodejs.org/dist/index.json", timeout=15
        ) as resp:
            entries = json.load(resp)
        ver = next(
            (
                e.get("version")
                for e in entries
                if str(e.get("version", "")).startswith(f"v{major}.")
            ),
            None,
        )
        if ver:
            return _platform_node_url(ver)
    except Exception:
        pass
    return _platform_node_url(_NODE_FALLBACK_VER)


def _platform_node_url(ver):
    """플랫폼별 Node.js 배포 URL 생성 (Windows: zip, macOS: tar.gz).

    [호환 유지] ProvisioningManager._fetch_from_nodejs에서 재사용.
    """
    from chzzktube.infra.platform import is_macos, is_windows

    if is_windows():
        return f"https://nodejs.org/dist/{ver}/node-{ver}-win-x64.zip"
    if is_macos():
        arch = "arm64" if platform.machine() == "arm64" else "x64"
        return f"https://nodejs.org/dist/{ver}/node-{ver}-darwin-{arch}.tar.gz"
    arch = "arm64" if platform.machine() == "arm64" else "x64"
    return f"https://nodejs.org/dist/{ver}/node-{ver}-linux-{arch}.tar.gz"


# ── Node.js 실행 파일 탐색 (SSOT: writable_base()/node 단일 경로) ──
def npm_exe():
    """현재 사용 중인 node 런타임과 동일한 디렉터리의 npm 스크립트 경로."""
    node = node_exe()
    if not node:
        return None
    base = os.path.dirname(node)
    from chzzktube.infra.platform import is_windows as _is_win

    name = "npm.cmd" if _is_win() else "npm"
    cand = os.path.join(base, name)
    return cand if os.path.isfile(cand) else None


def node_ok():
    """현재 탐색된 node가 bgutil 요구 버전(Node >= 22)을 충족하는지."""
    return (node_major_version(node_exe()) or 0) >= NODE_MIN_MAJOR


def node_exe():
    """PO Token 서버 기동용 node 탐색 — SSOT 단일 경로 (v3.8.2).

    [SSOT 원칙] 오직 writable_base()/node/ 하위만 탐색.
    - frozen 번들(_MEIPASS, _internal), bundle_root, 시스템 PATH 완전 제거
    - 실행 비트 보장(macOS) + 요구 버전 필터
    - 후보 없으면 None → ProvisioningManager 수급 트리거
    """
    from chzzktube.infra.platform import exe_suffix, is_windows as _np_is_win

    _exe_suffix = exe_suffix()

    cands = []
    local_node_dir = os.path.join(get_writable_base(), "node")
    if os.path.isdir(local_node_dir):
        exe_name = f"node{_exe_suffix}"
        for root, dirs, files in os.walk(local_node_dir):
            if exe_name in files:
                cands.append(os.path.join(root, exe_name))

    # [macOS] tar.gz 추출 시 실행 비트 누락 방지
    if not _np_is_win():
        for c in cands:
            try:
                mode = os.stat(c).st_mode
                if not (mode & 0o111):
                    os.chmod(c, mode | 0o755)
            except Exception:
                pass

    majors = [(c, node_major_version(c)) for c in cands]
    ok = [c for c, m in majors if m is not None and m >= NODE_MIN_MAJOR]
    return ok[0] if ok else (cands[0] if cands else None)


def bundled_npm_ok(node_path):
    """번들 Node dir의 npm 무결성 — validate-engines가 require하는 package.json.

    [크로스 플랫폼 레이아웃] 검사 경로는 플랫폼별 릴리스 구조를 모두 커버:
    - Windows zip :  <base>/node_modules/npm/package.json  (node.exe 옆)
    - Unix tarball : <base>/../lib/node_modules/npm/package.json  (macOS·Linux)
    """
    if not node_path:
        return False
    base = os.path.dirname(node_path)
    candidates = (
        os.path.join(base, "node_modules", "npm", "package.json"),
        os.path.join(base, "..", "lib", "node_modules", "npm", "package.json"),
    )
    return any(os.path.isfile(os.path.normpath(p)) for p in candidates)


def ensure_node_runtime(log_func):
    """bgutil 서버 요구(Node >= 22) 충족 — ProvisioningManager 위임 (v3.8.2).

    [SSOT] 수급은 ProvisioningManager → bridge → ProvisioningManager로 위임.
    이 모듈은 판정(node_ok/bundled_npm_ok)만 담당.

    Returns:
        True: node 요구 버전 충족 + npm 무결
        False: 수급 실패 또는 수급 후에도 요구 미충족
    """
    # 1. 현재 상태 확인 (SSOT: writable_base()/node만)
    cur = node_exe()
    cur_major = node_major_version(cur) if cur else None
    if cur_major is not None and cur_major >= NODE_MIN_MAJOR and bundled_npm_ok(cur):
        return True
    if cur_major is not None and cur_major >= NODE_MIN_MAJOR and not bundled_npm_ok(cur):
        log_func("[~] node ok but bundled npm broken — reinstalling runtime.")
    elif cur_major is not None:
        log_func(
            f"Node.js v{cur_major} is below bgutil requirement "
            f"(Node >= {NODE_MIN_MAJOR}) — reconfiguring to latest runtime."
        )
    else:
        log_func("node.js >= 22 missing — downloading portable runtime")

    # 2. ProvisioningManager 위임 (동기 브리지)
    try:
        from chzzktube.infra.provisioning.bridge import provision_component_sync

        def _bridge_log(evt):
            if isinstance(evt, str):
                log_func(evt)
            else:
                msg = getattr(evt, "msg", str(evt))
                if getattr(evt, "is_error", False):
                    log_func(msg, False, True)
                else:
                    log_func(msg)

        result = provision_component_sync("node", log_func=_bridge_log, force=True)
        if result is None or not result.success:
            log_func(f"Node.js provisioning failed: {result.error if result else 'unavailable'}", False, True)
            return False
    except Exception as e:
        log_func(f"Node.js provisioning failed: {e}", False, True)
        return False

    # 3. 재검증 (수급 후)
    _node_ver_cache.clear()
    new_node = node_exe()
    new_major = node_major_version(new_node) if new_node else None
    if new_major is not None and new_major >= NODE_MIN_MAJOR and bundled_npm_ok(new_node):
        log_func(f"portable Node.js v{new_major} ready.")
        _prune_outdated_node_dirs()
        return True
    log_func(
        f"Node.js still below requirement (>= {NODE_MIN_MAJOR}) after configure",
        False, True,
    )
    return False


def _prune_outdated_node_dirs():
    """오래된 node 버전 디렉토리 정리 (SSOT: writable_base()/node만 대상)."""
    node_dir = os.path.join(get_writable_base(), "node")
    if not os.path.isdir(node_dir):
        return
    import shutil as _shutil

    # 최신 node 실행파일 위치 기준으로 상위 디렉토리 유지
    current = node_exe()
    if not current:
        return
    keep_root = os.path.dirname(current)
    for entry in os.listdir(node_dir):
        full = os.path.join(node_dir, entry)
        if not os.path.isdir(full):
            continue
        # 유지 대상이면 스킵
        try:
            if os.path.samefile(full, keep_root) or keep_root.startswith(full + os.sep):
                continue
        except Exception:
            continue
        # npm/node_modules가 포함된 폴더만 대상 (안전장치)
        if any(f.startswith("node") for f in os.listdir(full)[:5]):
            try:
                _shutil.rmtree(full, ignore_errors=True)
            except Exception:
                pass
```

## File: chzzktube/infra/paths.py

```python
"""공통 경로/런타임 헬퍼 — node_provider, pot_server, updater 등에서 중복 제거."""

from __future__ import annotations

import os
import sys

import chzzktube.core.config as config


def get_writable_base() -> str:
    """사용자 환경에서 쓰기 권한이 100% 보장되는 로컬 앱 데이터 디렉터리 반환."""
    path = config.writable_base()
    os.makedirs(path, exist_ok=True)
    return path


def is_portable() -> bool:
    """PyInstaller(frozen) 패키징 여부."""
    return bool(getattr(sys, "frozen", False))


def bundle_root() -> str | None:
    """포터블에서 번들 데이터가 풀린 디렉터리 (onedir) _MEIPASS."""
    if is_portable():
        return getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(sys.executable)))
    return None
```

## File: chzzktube/infra/platform.py

```python
"""chzzktube/infra/platform.py - 크로스플랫폼 HAL (Hardware Abstraction Layer).

OS 종속 코드의 단일 격리 지점. 상위 비즈니스 로직은 이 모듈의 함수만
호출하고, OS 판정·ctypes·플래그를 직접 다루지 않는다.

원칙:
- OS 판정은 sys.platform 단일 출처 (is_windows/is_macos).
- Qt 역의존 금지: QWidget이 아니라 네이티브 핸들(int)/경로(str)만 받는다.
- 바보 모듈: chzzktube.* 상위 로직을 import하지 않는다 (stdlib only).
- 스폰 용도 분리: spawn_kwargs (단발/프로브) / daemon_spawn_kwargs (데몬).
"""
import subprocess
import sys
from typing import Any, Dict


def is_windows() -> bool:
    return sys.platform == "win32"


def is_macos() -> bool:
    return sys.platform == "darwin"


def exe_suffix() -> str:
    """현재 OS의 실행 파일 확장자."""
    return ".exe" if is_windows() else ""


def spawn_kwargs(use_no_window: bool = True) -> Dict[str, Any]:
    """단발/프로브용 스폰 인자 — Windows 창 억제만. POSIX는 빈 dict."""
    if is_windows() and use_no_window:
        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
    return {}


def daemon_spawn_kwargs(use_no_window: bool = True) -> Dict[str, Any]:
    """장기 데몬용 스폰 인자 — Win: NO_WINDOW|NEW_PROCESS_GROUP, POSIX: 세션 분리."""
    kw = spawn_kwargs(use_no_window)
    if is_windows():
        kw["creationflags"] |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        kw["start_new_session"] = True
    return kw


def flash_window(hwnd: int) -> None:
    """Windows 작업 표시줄 알림 (Qt 역의존 제거 — 순수 int 핸들 수신)."""
    if not is_windows() or not hwnd:
        return
    try:
        import ctypes

        class FLASHWINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", ctypes.c_uint),
                ("hwnd", ctypes.c_void_p),
                ("dwFlags", ctypes.c_uint),
                ("uCount", ctypes.c_uint),
                ("dwTimeout", ctypes.c_uint),
            ]

        info = FLASHWINFO(ctypes.sizeof(FLASHWINFO), hwnd, 3, 3, 0)
        ctypes.windll.user32.FlashWindowEx(ctypes.byref(info))
    except Exception:
        pass


def set_app_user_model_id(app_id: str) -> None:
    """Windows 작업 표시줄 그룹핑 ID (비-Windows는 no-op)."""
    if not is_windows() or not app_id:
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except (AttributeError, OSError):
        pass


def play_beep() -> None:
    """Windows 시스템 알림음 (비-Windows no-op, winsound 가드 내장)."""
    if not is_windows():
        return
    try:
        import winsound  # type: ignore[import-not-found]

        winsound.MessageBeep()
    except Exception:
        pass

def reveal_in_file_manager(path: str) -> None:
    """탐색기/파인더로 경로 노출 (utils._open_windows_explorer 승격)."""
    import os as _os

    target = _os.path.normpath(_os.path.abspath(path))
    if is_windows():
        import subprocess as _sp

        is_file = _os.path.isfile(target)
        folder = target if not is_file else _os.path.dirname(target)
        if is_file:
            _sp.Popen(["explorer.exe", "/n,", "/select," + target], close_fds=True)
        else:
            _sp.Popen(["explorer.exe", "/n,", folder], close_fds=True)
    elif is_macos():
        import subprocess as _sp

        _sp.Popen(["open", path])
    else:
        import subprocess as _sp

        _sp.Popen(["xdg-open", path])


def attach_to_parent_lifecycle(proc) -> None:
    """Windows: 자식을 Job Object에 할당 (부모 종료 시 자동 정리, POSIX no-op)."""
    if not is_windows() or proc is None:
        return
    try:
        import ctypes
        from ctypes import wintypes

        class JOB_BASIC(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        KILL_ON_CLOSE = 0x2000
        h_job = ctypes.windll.kernel32.CreateJobObjectW(None, None)
        if not h_job:
            return
        info = JOB_BASIC()
        info.LimitFlags = KILL_ON_CLOSE
        ok = ctypes.windll.kernel32.SetInformationJobObject(
            h_job, 4, ctypes.byref(info), ctypes.sizeof(info)
        )
        if not ok:
            ctypes.windll.kernel32.CloseHandle(h_job)
            return
        h_proc = getattr(proc, "_handle", None)
        if h_proc is None:
            ctypes.windll.kernel32.CloseHandle(h_job)
            return
        if not ctypes.windll.kernel32.AssignProcessToJobObject(h_job, h_proc):
            ctypes.windll.kernel32.CloseHandle(h_job)
    except Exception:
        pass


def kill_tree(proc) -> None:
    """프로세스 트리 종료 — Windows Job Object / POSIX 프로세스 그룹."""
    import os as _os
    import signal as _signal

    if proc is None:
        return
    try:
        if proc.poll() is not None:
            return
    except Exception:
        pass
    if is_windows():
        try:
            import ctypes

            h_proc = getattr(proc, "_handle", None)
            if h_proc is not None:
                h_job = ctypes.windll.kernel32.CreateJobObjectW(None, None)
                if h_job:
                    try:
                        ctypes.windll.kernel32.AssignProcessToJobObject(h_job, h_proc)
                        ctypes.windll.kernel32.TerminateJobObject(h_job, 1)
                    finally:
                        ctypes.windll.kernel32.CloseHandle(h_job)
                    try:
                        proc.wait(timeout=5)
                    except Exception:
                        pass
                    return
        except Exception:
            pass
        try:
            proc.kill()
        except Exception:
            pass
        return
    try:
        _os.killpg(_os.getpgid(proc.pid), _signal.SIGKILL)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


```

## File: chzzktube/infra/po_client.py

```python
### po_client.py - PO Token 서버 HTTP 클라이언트 (L0 leaf)
"""bgutil PO Token 서버와의 순수 HTTP 통신 계층.

[계층 규약] 서버 프로세스 수급·빌드·스폰(lifecycle)은 pot_server(L1)와
그 수명주기 관리자(POTManager)가 담당하고, 본 모듈은 그 서버에 대한
**순수 HTTP 클라이언트**만 제공한다 — 상위 계층 역참조(lazy import) 없이
표준 라이브러리만으로 완결된다.
- client_opts(L0) / updater(L0) 가 pot_provider(L1)를 역참조하던 계층 역전 해소:
  이제 옵션 빌더·버전 체커는 본 leaf만 본다.
- 의존: 표준 라이브러리만 — Qt/워커 무의존, 어디서 import해도 안전.
"""
import json
import re
import socket
import urllib.error
import urllib.request

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 4416


def server_ping(host=DEFAULT_HOST, port=DEFAULT_PORT, timeout=1):
    """PO token server alive 확인 (L0 순수 HTTP 핑). 성공 시 True.

    [계약] L0 leaf는 표준 라이브러리만 본다 — 상위 계층(pot_server)의 락
    파일을 들여다보던 PID 역참조는 폐기했다. TCP 연결 성공 + HTTP 200은
    Node.js 이벤트 루프가 실제로 I/O를 처리 중이라는 증거이므로 프로토콜
    검증만으로 생존 판정이 충분하다. 좀비 락 회수는 pot_server가 서버
    기동 시 본인의 책임 영역에서 처리한다.
    """
    try:
        url = f"http://{host}:{port}/ping"
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def probe_server(host=DEFAULT_HOST, port=DEFAULT_PORT, timeout=1.5):
    """서버 상태 모니터링 (HTTP /ping 응답 기준)"""
    url = f"http://{host}:{port}/ping"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if 200 <= resp.status < 300:
                return "ok", ""
            return "conflict", f"HTTP {resp.status}"
    except urllib.error.HTTPError as e:
        return "conflict", f"HTTP {e.code}"
    except urllib.error.URLError as e:
        if isinstance(getattr(e, "reason", None), ConnectionRefusedError):
            return "down", ""
    except Exception:
        pass

    # [폴백] HTTPError/URLError 외 (예: OS 레벨 연결 거부 랩핑) 소켓 직접 확인
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return "conflict", "ping no response"
    except OSError:
        return "down", ""


def fetch_po_token(video_id, host=DEFAULT_HOST, port=DEFAULT_PORT, timeout=5):
    """bgutil 독립 서버에서 PO 토큰 직접 패칭 (플러그인 우회).

    POST /get_pot {"content_binding": video_id} → {"poToken": "...", "visitorData": "..."}
    서버 미기동/오류 시 None 반환 — 호출부는 PO 없이 진행.
    
    Returns:
        tuple: (po_token, visitor_data) 또는 (None, None)
    """
    url = f"http://{host}:{port}/get_pot"
    try:
        body = json.dumps({"content_binding": video_id}).encode("utf-8")
        req = urllib.request.Request(
            url, data=body, method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        token = data.get("poToken") or ""
        visitor_data = data.get("visitorData") or ""
        if token:
            return token, visitor_data
    except Exception:
        pass
    return None, None


def extract_video_id(url):
    """YouTube URL에서 11자리 video ID 추출 (실패 시 None)."""
    m = re.search(
        r"(?:v=|/shorts/|/embed/|youtu\.be/)([a-zA-Z0-9_-]{11})", str(url or "")
    )
    return m.group(1) if m else None
```

## File: chzzktube/infra/pot_provider.py

```python
"""pot_provider — PO Token 3개 모듈 재수출 facade.

[구조]
- node_provider.py    : Node.js 런타임 수급 (node_exe, node_ok, ensure_node_runtime 등)
- pot_server.py       : bgutil 서버 빌드/기동 (ensure_node_server, _spawn_existing 등)
- po_client.py        : PO Token HTTP 클라이언트 (L0 leaf, 계층 역전 방지)
- pot_provider.py     : 위 3개 모듈을 재수출(re-export)

[호환성] 기존 `import pot_provider` 코드는 변경 없이 동작.
- update_worker.py: pot_provider.ensure_node_runtime
- updater.py      : pot_provider.node_exe / node_major_version / npm_exe

[제거 이력] POTProviderWorker(QThread)는 POTManager._POTWorker와 중복 선언된
좀비 인터페이스였다 — 런타임 사용 0건(tests/문서 전용), 진실의 근원은
POTManager 단독이다. 서버 수명주기 계약은 POTManager를 본다.
"""

# ── 재수출 (내부 호출 + 외부 역참조 모두 1경로) ──────────────────────────
from chzzktube.infra.po_client import (  # L0 leaf — 계층 역전 방지
    DEFAULT_HOST,
    DEFAULT_PORT,
    extract_video_id,
    fetch_po_token,
    probe_server,
    server_ping,
)
from chzzktube.infra.node_provider import (  # SRP: Node.js 런타임만 담당
    NODE_MIN_MAJOR,
    _NO_WINDOW,  # 하위 호환 별칭 — 실체는 platform.spawn_kwargs()
    _node_ver_cache,
    node_major_version,
    latest_lts_node_url,
    _platform_node_url,
    npm_exe,
    node_ok,
    node_exe,
    bundled_npm_ok,
    ensure_node_runtime,
)
from chzzktube.infra.paths import (  # 공통 경로 헬퍼
    get_writable_base,
    is_portable,
    bundle_root,
)
from chzzktube.infra.pot_server import (  # SRP: bgutil 서버 빌드/기동만 담당
    _SERVER_FALLBACK_VER,
    _TAG_ZIP,
    server_home,
    assign_to_job_object,
    read_server_log_tail,
    latest_server_ver,
    server_installed_ver,
    clean_stale_plugin,
    _wait_port,
    _kill,
    built_server_js,
    pot_readiness,
    acquire_prewarm_lock,
    release_prewarm_lock,
    _spawn_existing,
    download_and_install_source,
    _run_and_stream_log,
    ensure_node_server,
    kill_process_on_port,
)

__all__ = [
    "DEFAULT_HOST", "DEFAULT_PORT", "extract_video_id",
    "fetch_po_token", "probe_server", "server_ping",
    "NODE_MIN_MAJOR", "get_writable_base", "is_portable",
    "node_major_version", "latest_lts_node_url", "_platform_node_url",
    "npm_exe", "node_ok", "node_exe", "bundled_npm_ok", "ensure_node_runtime",
    "server_home", "assign_to_job_object", "read_server_log_tail",
    "latest_server_ver", "server_installed_ver", "clean_stale_plugin",
    "built_server_js", "pot_readiness", "acquire_prewarm_lock",
    "release_prewarm_lock", "_spawn_existing", "download_and_install_source",
    "ensure_node_server", "kill_process_on_port",
]

```

## File: chzzktube/infra/pot_server.py

```python
"""bgutil PO Token 서버 수명 주기 전용 모듈 (SRP: 서버 수급/빌드/기동만 담당).

- latest_server_ver / server_installed_ver : 버전 확인 (GitHub API + 로컬 마커)
- download_and_install_source : 지정 버전 소스 패치
- ensure_node_server : npm ci + tsc 빌드 파이프라인
- _spawn_node_server / _spawn_existing : Node.js HTTP 서버 기동
- _wait_port / _kill : 프로세스 생명주기 헬퍼
- _download_with_progress : 친절한 진행률 다운로드

Node.js 런타임 수급은 node_provider.py가 담당. 공유 경로 헬퍼는 infra.paths에서 import.
"""
import os
import sys
import time
import json
import shutil
import zipfile
import tarfile
import subprocess
import urllib.request
import tempfile

import chzzktube.core.config as config
from chzzktube.core.log_emitter import emit_component
from chzzktube.infra.po_client import DEFAULT_HOST, DEFAULT_PORT, probe_server
from chzzktube.infra.node_provider import NODE_MIN_MAJOR
from chzzktube.infra.paths import get_writable_base, is_portable, bundle_root
from chzzktube.infra.platform import (
    attach_to_parent_lifecycle,
    daemon_spawn_kwargs,
    is_windows,
)
from chzzktube.infra.platform import kill_tree as kill_tree_platform


_TAG_ZIP = (
    "https://github.com/Brainicism/bgutil-ytdlp-pot-provider/archive/refs/tags/{ver}.zip"
)
_SERVER_FALLBACK_VER = "1.3.2"

# [P3c] 빌드 단계 상한 (초) — npm ci/tsc가 무응답이면 프리웜 워커가 영구 점유되어
# is_busy()가 고정되고 POT 게이트 다운로드가 큐에서 풀리지 않는다.
_NPM_CI_TIMEOUT = 600
_TSC_TIMEOUT = 300


def server_home() -> str:
    """PO Token 서버 소스/빌드를 둘 위치 — SSOT 단일 경로 (v3.8.2).

    [SSOT 원칙] 오직 writable_base()/bgutil-ytdlp-pot-provider/ 하위만 사용.
    - frozen 번들(bundle_root), _MEIPASS 경로 탐색 완전 제거
    - 소스/빌드/런타임 모두 이 디렉토리에서 관리
    """
    writable_path = os.path.join(get_writable_base(), "bgutil-ytdlp-pot-provider")
    os.makedirs(writable_path, exist_ok=True)
    return writable_path


def assign_to_job_object(proc):
    """Windows: 프로세스를 Job Object에 할당해 부모 종료 시 자동 정리.

    실체는 platform.attach_to_parent_lifecycle — 여기는 하위 호환 재수출.
    """
    attach_to_parent_lifecycle(proc)
    # 레거시 계약: 성공 시 proc._ct_job 부착을 기대하는 코드가 있어 핸들 표식 유지.
    try:
        if is_windows() and proc is not None and getattr(proc, "_handle", None):
            proc._ct_job = True
    except Exception:
        pass


def read_server_log_tail(n=10):
    """bgutil_server.log의 마지막 n줄 반환 (디버깅용)."""
    log_file_path = os.path.join(get_writable_base(), "bgutil_server.log")
    if os.path.isfile(log_file_path):
        try:
            with open(log_file_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            return "".join(lines[-n:])
        except Exception:
            pass
    return ""


# ── 서버 버전·소스 관리 ─────────────────────────────────────────────
# [B4 정리] _TAG_ZIP·_SERVER_FALLBACK_VER는 상단(32~35행) 단일 정의만 유지 —
# 병합 잔재로 두 번 선언돼 있던 중복 상수는 제거했다.


def latest_server_ver(timeout=3):
    """bgutil 서버 최신 릴리즈 태그 (GitHub API). 실패 시 None — 호출부 폴백.

    [stale 감지용 경량 호출] timeout을 짧게(3초) 유지 — DEPS/프리웜 경로의
    블로킹 최소화. 네트워크 실패는 None으로 흡수해 판정 유지.
    """
    try:
        req = urllib.request.Request(
            "https://api.github.com/repos/Brainicism/bgutil-ytdlp-pot-provider/releases/latest",
            headers={"User-Agent": "ChzzkTube"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return (json.load(resp).get("tag_name") or "").strip() or None
    except Exception:
        return None


def server_installed_ver():
    """로컬에 전개된 bgutil 서버 버전 (.version 마커). 없으면 None."""
    try:
        with open(os.path.join(server_home(), ".version"), encoding="utf-8") as f:
            return f.read().strip() or None
    except OSError:
        return None


def clean_stale_plugin():
    """구버전에서 설치된 bgutil Python 플러그인 제거.

    yt_dlp_plugins/ 아래 getpot_bgutil이 남으면 yt-dlp 플러그인 로더가
    자동 로드해 fetch_po_token과 이중 주입 → 토큰 충돌 위험. 기동 시 1회.
    대상: <writable_base>/yt_dlp_plugins, <components>/yt-dlp/yt_dlp_plugins
    """
    import chzzktube.infra.components as components
    roots = [
        os.path.join(get_writable_base(), "yt_dlp_plugins"),
        os.path.join(components.components_root(), "yt-dlp", "yt_dlp_plugins"),
    ]
    removed = False
    for d in roots:
        if os.path.isdir(d):
            shutil.rmtree(d, ignore_errors=True)
            removed = True
    return removed


# ── 서버 기동/빌드/수명주기 ─────────────────────────────────────────
def _wait_port(seconds, log_full_func=None):
    """포트가 열릴 때까지 폴링. log_full_func가 있으면 5초마다 진척 로그 출력."""
    deadline = time.time() + seconds
    last_log = 0.0
    while time.time() < deadline:
        if probe_server()[0] == "ok":
            return True
        now = time.time()
        if log_full_func and now - last_log >= 5.0:
            log_full_func(
                f"[pot:spawn] waiting for server... "
                f"{int(seconds - (deadline - now))}s / {seconds}s"
            )
            last_log = now
        time.sleep(0.5)
    return False


def _kill(proc):
    """서버 프로세스 강제 종료 (침묵형)."""
    try:
        proc.kill()
    except Exception:
        pass


def kill_tree(proc):
    """프로세스 트리 종료 — 실체는 platform.kill_tree (하위 호환 재수출)."""
    kill_tree_platform(proc)
    try:
        if getattr(proc, "_ct_job", None):
            proc._ct_job = None
    except Exception:
        pass


def kill_process_on_port(port=DEFAULT_PORT, log_func=None):
    """지정된 포트를 점유한 프로세스 강제 종료 (크로스플랫폼).

    좀비 프로세스 정리용 — server_ping이 True인데 PID가 죽은 경우 호출.
    """
    killed = False
    try:
        if is_windows():
            # Windows: netstat로 PID 찾기 → taskkill
            import subprocess as _sub
            try:
                out = _sub.check_output(
                    ["netstat", "-ano"], text=True, stderr=_sub.DEVNULL
                )
                for line in out.splitlines():
                    if f":{port} " in line and "LISTENING" in line:
                        parts = line.split()
                        if parts:
                            pid = parts[-1]
                            if pid.isdigit():
                                _sub.run(
                                    ["taskkill", "/F", "/PID", pid],
                                    stdout=_sub.DEVNULL,
                                    stderr=_sub.DEVNULL,
                                )
                                if log_func:
                                    log_func(f"[pot:zombie] killed windows pid={pid} on port {port}")
                                killed = True
            except Exception:
                pass
        else:
            # macOS/Linux: lsof로 PID 찾기 → kill
            import subprocess as _sub
            try:
                out = _sub.check_output(
                    ["lsof", "-ti", f":{port}"], text=True, stderr=_sub.DEVNULL
                )
                for pid_str in out.strip().split():
                    if pid_str.isdigit():
                        pid = int(pid_str)
                        os.kill(pid, 9)  # SIGKILL
                        if log_func:
                            log_func(f"[pot:zombie] killed posix pid={pid} on port {port}")
                        killed = True
            except Exception:
                pass
    except Exception:
        pass
    return killed


def built_server_js():
    """컴파일된 main.js 경로 반환 (build/ 와 dist/ 모두 지원)."""
    base_dir = os.path.join(server_home(), "server")
    for out_dir in ("build", "dist"):
        js_path = os.path.join(base_dir, out_dir, "main.js")
        if os.path.isfile(js_path):
            return js_path
    return None


def pot_readiness(log_func=None, check_stale=False, want_refresh=False):
    """POT 서버 기동 가능성 경량 판정 — 파일시스템 스캔만 (L0, 네트워크·Popen 금지).

    [Lazy 2층 분리] DEPS 단계에서는 바이너리+빌드 산출물의 디스크 준비만
    확인하고 (RAM 0MB·포트 미점유), 실제 Popen은 분석 게이트까지 지연.
    - ready=True  → 게이트 히트 시 즉시 spawn 가능 (0.1~3초)
    - ready=False → reason에 부족분 명시 (node missing / no build / stale vX→vY)
    - stale + want_refresh=True → 자동 리프레시 유도 (reason은 여전히 stale)

    [성능] node_ok()의 subprocess 기동(수백ms)을 피하고 node_exe() 존재만으로
    판정 — UpdateWorker 스레드 블로킹 및 DEPS 1초 예산 초과 방지.
    정확한 버전 판별은 _do_upgrade의 ensure_node_runtime이 담당.
    log_func(msg): 판정 근거를 raw 스택으로 반환 (계층 역전 방지용 콜백).
    check_stale=True → GitHub 최신 태그와 로컬 .version 비교 (네트워크 3초).
    실패(None) 시 판정 유지 — stale 미확인을 FAIL로 승격 금지.
    want_refresh=True → stale 시 ready=True 복귀 + reason에 refresh 표기.
    "lazy는 언제든지 작동 가능한 데에서 의의가 있다"는 원칙에 따라,
    stale 빌드도 "준비 완료(staged/refresh pending)"로 간주.
    """
    from chzzktube.infra.node_provider import node_exe
    try:
        exe = node_exe()
        if not exe:
            if log_func:
                try:
                    log_func("[pot-readiness] not ready: node missing")
                except Exception:
                    pass
            return False, "node missing"
    except Exception:
        return False, "node missing"
    try:
        js = built_server_js()
        if not js:
            if log_func:
                try:
                    log_func("[pot-readiness] not ready: no build")
                except Exception:
                    pass
            return False, "no build"
    except Exception:
        return False, "no build"
    if check_stale:
        # [stale 감지] 로컬 .version vs GitHub 최신 — 불일치면 리프레시 유도.
        # 네트워크 실패(None) 시 판정 유지 (stale 미확인 ≠ FAIL).
        # [auto-refresh] want_refresh=True면 stale이어도 "작동 가능한 준비됨"으로
        # 간주 — 프리웜이 자동으로 리프레시 진행. "lazy는 언제든 작동 가능해야 함"
        # 원칙: stale 빌드를 fail로 닫지 않고 staged/refresh pending으로 열어야 한다.
        try:
            local = server_installed_ver()
            remote = latest_server_ver()
            stale = remote and local and remote != local
            if stale:
                if log_func:
                    try:
                        log_func(f"[pot-readiness] stale build (local {local} → remote {remote})")
                    except Exception:
                        pass
                if want_refresh:
                    return True, f"stale {local}→{remote} (refresh pending)"
                return False, f"stale {local}→{remote}"
        except Exception:
            pass
    if log_func:
        try:
            log_func(f"[pot-readiness] standby (node ok, build {js})")
        except Exception:
            pass
    return True, "standby"


def _spawn_node_server(log_full_func=None):
    """Node.js로 bgutil HTTP 서버 기동하고 45초 내에 /ping 응답 확인."""
    from chzzktube.infra.node_provider import node_exe

    js, node = built_server_js(), node_exe()
    if not js and log_full_func:
        log_full_func("server spawn reason: built main.js missing (server/build)")
    if not node and log_full_func:
        log_full_func(f"server spawn reason: Node.js >= {NODE_MIN_MAJOR} binary missing")
    if not (js and node):
        return None

    log_file_path = os.path.join(get_writable_base(), "bgutil_server.log")
    try:
        log_file = open(log_file_path, "w", encoding="utf-8", errors="replace")
    except Exception:
        log_file = subprocess.DEVNULL

    try:
        env = os.environ.copy()
        node_dir = os.path.dirname(os.path.abspath(node))
        env["PATH"] = node_dir + os.pathsep + env.get("PATH", "")

        kwargs = daemon_spawn_kwargs()
        proc = subprocess.Popen(
            [node, js],
            cwd=os.path.dirname(js),
            stdout=log_file,
            stderr=log_file,
            env=env,
            **kwargs,
        )
        assign_to_job_object(proc)
    except Exception as e:
        if log_full_func:
            log_full_func(f"server Popen failed: {e}")
        return None
    if _wait_port(20, log_full_func):
        return proc
    _kill(proc)
    if log_full_func:
        log_full_func(
            "server spawn reason: /ping not responding in 20s "
            "(crash after startup — see bgutil_server.log)"
        )
    return None


def _spawn_existing(log_full_func=None):
    """기존 빌드가 있으면 재사용, 없으면 _spawn_node_server 위임."""
    return _spawn_node_server(log_full_func)


def _download_with_progress(url, dest_path, log_func, desc):
    """청크 단위 분할 다운로드 및 콘솔에 친절한 진행률 출력."""
    temp_dest = dest_path + ".tmp"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ChzzkTube"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            total_size = int(resp.headers.get("content-length", 0))
            downloaded = 0
            with open(temp_dest, "wb") as f:
                while True:
                    chunk = resp.read(1024 * 1024)  # 1MB
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        pct = int(downloaded / total_size * 100)
                        log_func(f"{desc}... {pct}%", True, False)
            if os.path.exists(temp_dest):
                shutil.move(temp_dest, dest_path)
    finally:
        if os.path.exists(temp_dest):
            try:
                os.remove(temp_dest)
            except Exception:
                pass


def _prewarm_lock_path():
    """프리웜/게이트 npm 빌드 상호배제용 락 파일 경로."""
    return os.path.join(server_home(), ".prewarm.lock")


def _pid_alive(pid):
    """PID 생존 확인 — Windows OpenProcess / POSIX kill(pid, 0).

    [PID-liveness] mtime 단일 기준의 오판(크래시 후 30분 프리웜 양보)을
    막기 위해 프로세스 실존 여부를 직접 확인. 판별 실패(권한 등)는
    보수적으로 살아있음으로 간주 (성급한 회수 금지).
    """
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    try:
        import platform as _plat
        if _plat.system() == "Windows":
            import ctypes as _ct
            from ctypes import wintypes as _wt
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            try:
                _k32 = _ct.WinDLL("kernel32", use_last_error=True)
                _k32.OpenProcess.argtypes = [_wt.DWORD, _wt.BOOL, _wt.DWORD]
                _k32.OpenProcess.restype = _wt.HANDLE
                _k32.CloseHandle.argtypes = [_wt.HANDLE]
                _k32.CloseHandle.restype = _wt.BOOL
                h = _k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
                if not h:
                    return False  # 존재하지 않거나 접근 불가 → 죽음으로 간주
                try:
                    return True
                finally:
                    _k32.CloseHandle(h)
            except Exception:
                return True  # 판별 자체 실패 → 보수적 유지
        else:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return False
            except PermissionError:
                return True  # 존재하나 권한 없음 → 살아있음
            except Exception:
                return True
            return True
    except Exception:
        return True


def _read_lock_info(path):
    """락 파일에서 (pid:int|None, epoch:float|None) 판독."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            parts = f.read().strip().split()
        pid = int(parts[0]) if parts else None
        epoch = float(parts[1]) if len(parts) > 1 else None
        return pid, epoch
    except Exception:
        return None, None


def acquire_prewarm_lock(timeout=0, log_func=None):
    """원자적 락 획득 시도 — O_EXCL 생성으로 상호배제.

    [Zero-Base] msvcrt/filelock 외부 의존 없이 os.open(O_CREAT|O_EXCL)
    원자 생성으로 프로세스·스레드 경계를 모두 차단 (단일 앱 전제).
    stale 락 판정: PID 죽음 AND mtime 30분 초과 → 회수. PID 살아있으면
    mtime 무관하게 대기 (PID 재사용 레이스는 mtime 상한으로 차단).
    timeout=0 → 즉시 반환 (None이면 획득 실패). timeout>0 → 폴링 대기.
    반환: fd(int) 또는 None. 해제는 release_prewarm_lock(fd).
    log_func(msg): 획득/대기/양보/stale 회수 전 분기를 호출자 로그로 반환.
    """
    import time as _time
    path = _prewarm_lock_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
    except OSError:
        pass
    deadline = _time.monotonic() + max(0, timeout)
    waited_note = False
    while True:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            try:
                os.write(fd, f"{os.getpid()} {_time.time()}".encode("utf-8"))
            except OSError:
                pass
            if log_func:
                try:
                    log_func("[prewarm-lock] acquired")
                except Exception:
                    pass
            return fd
        except FileExistsError:
            pid, _epoch = _read_lock_info(path)
            alive = _pid_alive(pid) if pid else True
            try:
                age = _time.time() - os.path.getmtime(path)
            except OSError:
                age = 0
            if not alive and age > 1800:  # PID 죽음 + 30분 stale → 회수
                if log_func:
                    try:
                        log_func(f"[prewarm-lock] stale reclaimed (pid={pid} dead, age={int(age)}s)")
                    except Exception:
                        pass
                try:
                    os.remove(path)
                except OSError:
                    pass
                continue
            if log_func and not waited_note and timeout > 0:
                waited_note = True
                try:
                    log_func(f"[prewarm-lock] waiting (holder pid={pid}, alive={alive})")
                except Exception:
                    pass
        except OSError:
            return None
        if _time.monotonic() >= deadline:
            if log_func:
                try:
                    log_func("[prewarm-lock] busy — acquire timeout")
                except Exception:
                    pass
            return None
        _time.sleep(0.2)


def release_prewarm_lock(fd, log_func=None):
    """락 해제 — fd close + 파일 제거 (best-effort)."""
    try:
        os.close(fd)
    except OSError:
        pass
    try:
        os.remove(_prewarm_lock_path())
    except OSError:
        pass
    if log_func:
        try:
            log_func("[prewarm-lock] released")
        except Exception:
            pass


def download_and_install_source(want_ver, log_func=None):
    """지정된 버전의 bgutil 서버 소스를 다운로드하여 세팅한다."""
    dest_dir = server_home()
    tmp = tempfile.mkdtemp(prefix="chzzktube_bgutil_")
    zpath = os.path.join(tmp, "src.zip")
    try:
        url = _TAG_ZIP.format(ver=want_ver)
        if log_func:
            _download_with_progress(url, zpath, log_func, "bgutil source downloading")
        else:
            urllib.request.urlretrieve(url, zpath)

        with zipfile.ZipFile(zpath) as zf:
            names = zf.namelist()
            root = (names[0].split("/")[0] if names else "") or f"bgutil-ytdlp-pot-provider-{want_ver}"
            zf.extractall(tmp)

        inner = os.path.join(tmp, root)
        if not os.path.isfile(os.path.join(inner, "server", "package.json")):
            raise RuntimeError("downloaded source has no server/ directory")

        os.makedirs(dest_dir, exist_ok=True)
        shutil.copytree(inner, dest_dir, dirs_exist_ok=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _communicate_with_ticks(proc, timeout, tick_func, tick_interval):
    """communicate waiting loop that fires tick_func() periodically.

    [Followup-1] communicate() blocks without output, so a long npm ci/tsc run was
    indistinguishable from a stall — the P5 fallback extension never got a heartbeat
    during the POT build phase. Windows cannot select() on pipes, so we wait with a
    short timeout repeatedly and emit a heartbeat each round; the final timeout is
    still honored by re-raising TimeoutExpired.
    """
    if tick_func is None or not tick_interval or tick_interval <= 0:
        return proc.communicate(timeout=timeout)
    import time as _time
    deadline = None if timeout is None else _time.monotonic() + timeout
    while True:
        try:
            return proc.communicate(timeout=tick_interval)
        except subprocess.TimeoutExpired:
            if proc.poll() is not None:
                return proc.communicate(timeout=1)
            tick_func()
            if deadline is not None and _time.monotonic() >= deadline:
                raise


def _run_and_stream_log(cmd, cwd, log_full_func, env=None, use_no_window=True,
                        timeout=None, tick_func=None, tick_interval=5.0,
                        proc_registry=None):
    """서브프로세스 실행 + 출력 스트리밍.

    use_no_window=False로 설정하면 CREATE_NO_WINDOW 플래그를 적용하지 않음.
    tsc 등 콘솔 출력에 의존하는 도구는 이 옵션을 False로 설정해야 함.

    [P3c] timeout 초과 시 직접 자식만 강제 종료하고 -1을 반환한다. npm ci/tsc가
    무응답이면 프리웜 워커가 영구 점유되어 is_busy()가 고정되고 POT 게이트
    다운로드가 큐에서 풀리지 않는다 — 상한이 반드시 필요하다.
    [Followup-2] job-object(TerminateJobObject)/process-group kill_tree로 트리 전체를 정리한다.
    """
    try:
        kwargs = daemon_spawn_kwargs(use_no_window=use_no_window)
        proc = subprocess.Popen(
            cmd, cwd=cwd,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
            env=env, **kwargs,
        )
        assign_to_job_object(proc)  # [Followup-2] app-exit cleanup (kill-on-close)
        if proc_registry is not None:
            proc_registry.append(proc)
        try:
            stdout, _ = _communicate_with_ticks(proc, timeout, tick_func, tick_interval)
        except subprocess.TimeoutExpired:
            kill_tree(proc)  # [Followup-2] tree kill (job object / process group)
            if log_full_func:
                log_full_func(
                    f"subprocess timeout ({timeout}s) — killed: {' '.join(map(str, cmd))}"
                )
            return -1
        if proc_registry is not None:
            try:
                proc_registry.remove(proc)
            except ValueError:
                pass
        if stdout and log_full_func:
            for line in stdout.splitlines():
                stripped = line.strip()
                if stripped:
                    log_full_func(stripped)
        return proc.returncode
    except Exception as e:
        if log_full_func:
            log_full_func(f"subprocess Popen error: {e}")
        return -1


def _prune_outdated_node_dirs(node_dir):
    """요구 버전 미만의 구형 Node.js 캐시 폴더 정리 (디스크 낭비 방지)."""
    import re as _re
    try:
        for name in os.listdir(node_dir):
            m = _re.match(r"node-v(\d+)\.", name)
            if m and int(m.group(1)) < NODE_MIN_MAJOR:
                shutil.rmtree(os.path.join(node_dir, name), ignore_errors=True)
    except Exception:
        pass


def ensure_node_server(log, log_full, want_ver, rebuild=False,
                       tick_func=None, proc_registry=None):
    """Node.js HTTP 서버 및 빌드 소스 구성을 완료한다.

    [rebuild 플래그]
    - True: 기존 빌드가 있더라도 npm ci / tsc 강제 재실행 (서버 업데이트용)
    - False: 빌드 산출물 존재 시 재사용 (런타임만 확인)

    [흐름]
    1. 빌드 디렉터리(server/) 존재 여부로 분기
       - server/ 없음 → source fetch → npm ci → tsc
       - server/ 있음 + rebuild=False → 기존 빌드 재사용
    2. 빌드 성공 시 server_dir 반환 → 호출부에서 _spawn_existing 기동
    """
    from chzzktube.infra.node_provider import (
        node_exe, node_ok, node_major_version,
        ensure_node_runtime, bundled_npm_ok,
    )

    js = built_server_js()

    # [rebuild 모드] npm ci + tsc 강제 재실행
    if js is None or rebuild:
        server_src_dir = os.path.join(server_home(), "server")
        source_exists = os.path.isdir(server_src_dir) and os.path.isfile(
            os.path.join(server_src_dir, "package.json")
        )
        if not source_exists:
            ver = want_ver or latest_server_ver() or _SERVER_FALLBACK_VER
            log(emit_component("pot", "RUN", "pot", f"bgutil source fetching (v{ver})"))
            try:
                download_and_install_source(ver, log)
            except Exception as ds_ex:
                log_full(f"[pot] source fetch failed: {ds_ex}")
        else:
            log(emit_component("pot", "RUN", "pot", "bgutil source detected — building"))

        if not ensure_node_runtime(log):
            return None, f"Node.js runtime unavailable (>= {NODE_MIN_MAJOR} required)"
        curr_node = node_exe()
        if not curr_node:
            return None, "Node.js executable not found"

        npm_cli = None
        node_base_dir = os.path.dirname(curr_node)
        for root, dirs, files in os.walk(node_base_dir):
            if "npm-cli.js" in files:
                npm_cli = os.path.join(root, "npm-cli.js")
                break

        # [v3.8.0 격리] npm 해석은 격리 런타임 단일 경로 —
        # npm-cli.js(포터블 node 동봉) → npm_exe(포터블 스크립트) 순.
        # 시스템 PATH(shutil.which) 폴백은 철폐한다.
        if npm_cli:
            npm_cmd = [curr_node, npm_cli]
        else:
            from chzzktube.infra.node_provider import npm_exe
            npm_path = npm_exe()
            if not npm_path:
                return None, "npm not found in isolated Node.js runtime"
            npm_cmd = [npm_path]
        server_dir = os.path.join(server_home(), "server")

        try:
            log(emit_component("pot", "RUN", "pot", "npm install... (first run may take minutes)"))
            env = os.environ.copy()
            node_dir = os.path.dirname(os.path.abspath(curr_node))
            env["PATH"] = node_dir + os.pathsep + env.get("PATH", "")

            cmd_install = npm_cmd + ["ci", "--no-audit", "--no-fund"]
            ret = _run_and_stream_log(
                cmd_install, server_dir, log_full, env=env,
                timeout=_NPM_CI_TIMEOUT, tick_func=tick_func,
                proc_registry=proc_registry,
            )
            if ret != 0:
                return None, f"npm install failed (exit code {ret})"

            log(emit_component("pot", "RUN", "pot", "tsc compiling..."))
            # [tsc incremental 함정 수리]
            if built_server_js() is None:
                tsbi = os.path.join(server_dir, "tsconfig.tsbuildinfo")
                if os.path.isfile(tsbi):
                    try:
                        os.remove(tsbi)
                        log_full("[pot] stale tsbuildinfo purged — forcing full tsc compile")
                    except OSError as tsbi_ex:
                        log_full(f"[pot] tsbuildinfo purge failed: {tsbi_ex}")

            local_tsc = os.path.join(server_dir, "node_modules", "typescript", "bin", "tsc")
            if os.path.isfile(local_tsc):
                cmd_build = [curr_node, local_tsc]
            else:
                cmd_build = [curr_node, npm_cli, "execute", "tsc"] if npm_cli else ["npx", "tsc"]

            ret = _run_and_stream_log(
                cmd_build, server_dir, log_full, env=env,
                use_no_window=False, timeout=_TSC_TIMEOUT,
                tick_func=tick_func, proc_registry=proc_registry,
            )
            if ret != 0:
                return None, f"tsc failed (exit code {ret})"

            if built_server_js() is None:
                return None, "server/build/main.js (or dist/main.js) missing after compile"
            return server_dir, None
        except Exception as e:
            return None, f"{type(e).__name__}: {e}"

    # [재사용 모드] 기존 빌드가 있으면 런타임만 확인 → 즉시 반환
    if not ensure_node_runtime(log):
        return None, "Node.js runtime unavailable"
    if node_ok():
        return os.path.dirname(server_home()), None
    return None, "Node.js runtime check failed"

```

## File: chzzktube/infra/pylib_bootstrap.py

```python
"""프로젝트 로컬 pip 오버레이 부트스트랩 (<repo>/.pylib).

인앱 업데이터가 venv(site-packages, uv 소유)를 직접 수정하지 않고
프로젝트별 .pylib/ 디렉터리에만 whl을 해제하도록 한다. 이 모듈을 진입점
최상단에서 import하면 sys.path 선두에 .pylib/을 올려 오버레이 복사가
항상 venv보다 우선한다 (importlib.metadata 포함).

순환 import 금지: stdlib(os/sys) + config(경로 계산)만 의존.
로깅은 진입점 main()에서 1줄 진단으로 처리한다.
"""
import os
import sys

from chzzktube.core.config import pylib_overlay_path


def bootstrap(clear_caches=True):
    """sys.path 선두에 .pylib/ 삽입. 중복 호출 안전. 반환: 실제 삽입된 경로."""
    try:
        path = os.path.abspath(pylib_overlay_path())
    except Exception:
        return ""
    try:
        os.makedirs(path, exist_ok=True)
    except Exception:
        return ""
    if path not in sys.path:
        sys.path.insert(0, path)
    if clear_caches:
        try:
            import importlib

            importlib.invalidate_caches()
            # .venv 등에서 사전 로드된 구버전 모듈 캐시 제거
            for mod_name in list(sys.modules.keys()):
                if mod_name.startswith(("yt_dlp", "streamlink")):
                    del sys.modules[mod_name]
        except Exception:
            pass
    return path
```

## File: chzzktube/infra/updater.py

```python
##### updater.py - pip component (yt-dlp / streamlink) version check and update helper
"""PyPI metadata query for latest versions, optional pip upgrade on demand.
*  Version check: PyPI JSON API (lightweight, no pip needed)
*  Upgrade:
    - Stable channel: python -m pip install -U <pkg>
    - Nightly channel: python -m pip install -U yt-dlp-nightly (yt-dlp only)
*  frozen(PyInstaller) builds — pip이 없으므로 직접 다운로드:
    - yt-dlp: PyPI/GitHub release에서 yt-dlp.exe 다운로드 후 교체
    - streamlink: PyPI에서 whl 다운로드 후 importlib로 설치
    - 업데이트 실패 시 기존 버전 유지, 다음 실행 시 재시도
*  네트워크 의존은 이 앱에서 본질적이다 (웹 미디어 추출기). """
import concurrent.futures
import importlib.metadata as im
import json
import os
import shutil
import subprocess
import sys
import tempfile
import socket
import urllib.request
from chzzktube.infra.platform import spawn_kwargs

# (log_label, pypi_name, pypi_nightly) — log_label is shown in the DEPS PLATFORM column
# pypi_nightly: Nightly 채널 사용 시 설치할 PyPI 패키지명 (None이면 Stable only)
# [전환] bgutil-ytdlp-pot-provider 제외: 플러그인(pip)에서 독립 Node 서버로
# 이동 — 버전 관리 주체는 pot_provider(latest_server_ver)가 담당.
PACKAGES = [("ytdlp", "yt-dlp", "yt-dlp-nightly"), ("streamlink", "streamlink", None)]
# [주의] socket.setdefaulttimeout() 절대 사용 금지 — 프로세스 전체의 소켓 기본
# 타임아웃을 오염시켜 yt-dlp 미디어 스트림 재시도 루프(0.0% 스톨)를 유발.
# DNS hang 방어는 아래 latest_version의 ThreadPoolExecutor + urlopen(timeout)으로 충분.

_PYPI_API = "https://pypi.org/pypi/{pkg}/json"
_NIGHTLY_API = "https://github.com/yt-dlp/yt-dlp-nightly-builds/releases/latest/download/yt-dlp{_ext}"

def installed_version(pypi_name):
    """Installed version string from .pylib overlay only, or None if not installed.

    SSOT: 오직 .pylib 내부 dist-info만 스캔하여 버전 판정.
    .venv나 시스템 site-packages에 존재하더라도 무시한다.
    """
    import glob
    import os
    from chzzktube.core.config import pylib_overlay_path

    pylib_root = pylib_overlay_path()
    if not os.path.isdir(pylib_root):
        return None

    # 패키지명 정규화: yt-dlp -> yt_dlp, streamlink -> streamlink
    pkg_dir = pypi_name.replace("-", "_")
    dist_info_pattern = os.path.join(pylib_root, f"{pkg_dir}-*.dist-info")

    for dist_info in glob.glob(dist_info_pattern):
        metadata_path = os.path.join(dist_info, "METADATA")
        if os.path.isfile(metadata_path):
            try:
                with open(metadata_path, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.startswith("Version:"):
                            return line.split(":", 1)[1].strip()
            except Exception:
                continue
    return None

def latest_version(pypi_name, timeout=1.5):
    """Latest stable version from PyPI, or None on failure.

    [v3.1.0 변경] 타임아웃 2초→1.5초로 단축. DEPS 로그 표시 시간을
    줄이기 위해. PyPI JSON API는 충분히 빠르므로 1.5초면 충분.
    ThreadPoolExecutor는 DNS 레벨까지 카운트다운하므로 urlopen timeout
    보다 0.5초만 버퍼로 부여.

    [DNS hang defence] socket.setdefaulttimeout does not cover getaddrinfo;
    ThreadPoolExecutor + future.result cuts at DNS level too.
    """
    def _fetch():
        with urllib.request.urlopen(_PYPI_API.format(pkg=pypi_name), timeout=timeout) as resp:
            return json.load(resp)
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(_fetch)
            data = fut.result(timeout=timeout + 0.5)
            return (data.get("info") or {}).get("version")
    except Exception:
        return None

def _ver_tuple(version):
    """'2026.8.19' -> (2026, 8, 19) comparable tuple (non-digit chars dropped)."""
    parts = []
    for p in str(version).split("."):
        digits = "".join(ch for ch in p if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)

def is_outdated(current, latest):
    """True if latest > current (numeric tuple compare avoids string pitfalls)."""
    try:
        return _ver_tuple(latest) > _ver_tuple(current)
    except Exception:
        return False

def outdated_packages(channel="stable"):
    """List of (label, pypi_name, cur, latest) needing update or not installed.
    channel: stable / nightly (yt-dlp-nightly / GitHub builds).

    [downgrade support] stable channel with yt-dlp-nightly installed (user
    switched Nightly->Stable): force stale target=stable -- nightly version
    string compares higher so plain version check would be never-stale.
    """
    stale = []
    for label, pypi_name, pypi_nightly in PACKAGES:
        if channel == "nightly" and pypi_nightly:
            cur = installed_version(pypi_nightly) or installed_version(pypi_name)
            latest = latest_version(pypi_nightly)
            if not cur:
                stale.append((label, pypi_name, "not installed", latest or "unknown"))
            elif latest and is_outdated(cur, latest):
                stale.append((label, pypi_name, cur, latest))
            continue
        # stable channel: leftover nightly -> downgrade target
        if pypi_nightly and installed_version(pypi_nightly):
            stale.append((label, pypi_name, str(installed_version(pypi_nightly)) + " (nightly)", "stable"))
            continue
        cur = installed_version(pypi_name)
        latest = latest_version(pypi_name)
        if not cur:
            stale.append((label, pypi_name, "not installed", latest or "unknown"))
        elif latest and is_outdated(cur, latest):
            stale.append((label, pypi_name, cur, latest))
    return stale


def check_deps(log_func=None):
    """모든 의존성 체크 결과 리스트 반환.
    각 요소: (label, status, version_or_path)
    status: 표준 status (OK / FAIL 등) — `format_log_line`의 표준 사용.
    log_func(msg): POT readiness 판정 근거를 raw 스택으로 반환 (단일 호출).
    """
    import os
    import shutil
    results = []

    # 1. PyPI 패키지 (yt-dlp, streamlink) — nightly 채널 설치물 인지
    #    yt-dlp-nightly 는 dist 명이 달라 im.version("yt-dlp") 가 실패하므로
    #    nightly 설치물로 폴백 표기 (정상 설치 판정 유지)
    for label, pypi_name, pypi_nightly in PACKAGES:
        ver = installed_version(pypi_name)
        if not ver and pypi_nightly:
            nver = installed_version(pypi_nightly)
            if nver:
                ver = f"{nver} (nightly)"
        results.append((label, "OK" if ver else "FAIL", ver or "not installed"))

    # 2. 외부 실행 파일 (ffmpeg, node) — [v3.8.0 격리] 앱 전용 캐시 단일 참조.
    #    시스템 PATH(shutil.which) 탐색 철폐 — 격리 캐시 수급본만 DEPS 대상.
    for label in ("ffmpeg", "node"):
        path = None
        if label == "node":
            try:
                import chzzktube.infra.pot_provider as pot_provider
                path = pot_provider.node_exe()
                maj = pot_provider.node_major_version(path)
            except Exception:
                path, maj = None, None
            msg = f"v{maj}" if maj else (os.path.basename(path) if path else "not found")
        else:
            try:
                from chzzktube.infra.components import ffmpeg_exe
                path = ffmpeg_exe()
            except Exception:
                path = None
            msg = _ffmpeg_version(path) or "not found" if path else "not found"
        results.append((label, "OK" if path else "FAIL", msg))

    # 3. PO token 서버 — [Lazy 2층 분리] liveness가 아니라 readiness.
    # 바이너리+빌드 산출물의 디스크 준비만 판정 (RAM 0MB·포트 미점유).
    # Popen은 분석 게이트(_ensure_pot_for_info)까지 지연. FAIL 오경보 금지:
    # 미기동 정상 상태는 SKIP standby, 산출물 미비는 SKIP + 사유.
    # [단일 호출] log_func 콜백을 내부 pot_readiness에 직접 전달 — 판정+로그
    # 1회로 해결 (별도 _pot_readiness 호출 시 standby 2중 출력 결함).
    try:
        from chzzktube.infra.po_client import server_ping
        from chzzktube.infra.pot_server import pot_readiness
        if server_ping():
            results.append(("pot", "OK", "running"))
        else:
            ready, reason = pot_readiness(log_func=log_func)
            if ready:
                results.append(("pot", "SKIP", "standby"))
            else:
                results.append(("pot", "SKIP", reason))
    except Exception:
        results.append(("pot", "SKIP", "unknown"))

    return results


def verify_deps_integrity() -> tuple[bool, list[str]]:
    """런타임 의존성 무결성 검증 — 주요 deps 존재/실행 가능 여부 확인.

    Returns:
        (ok, missing_list): ok=True면 모든 필수 deps 정상, False면 누락/실패 목록 반환
    """
    from chzzktube.core import config
    import chzzktube.infra.components as components
    import chzzktube.infra.pot_provider as pot_provider
    import subprocess
    import sys

    missing = []

    # 1. Python packages (yt-dlp, streamlink) — .pylib overlay에서 import 시도
    try:
        import yt_dlp
    except ImportError:
        missing.append("yt-dlp (not importable from .pylib)")

    try:
        import streamlink
    except ImportError:
        missing.append("streamlink (not importable from .pylib)")

    # 2. ffmpeg — 격리 캐시에서 실행 가능 확인
    try:
        ffmpeg_path = components.ffmpeg_exe()
        if not ffmpeg_path:
            missing.append("ffmpeg (not found in cache)")
        else:
            # 실행 테스트
            result = subprocess.run(
                [ffmpeg_path, "-version"],
                capture_output=True,
                timeout=5,
                **{**{}, **__import__("chzzktube.infra.platform").spawn_kwargs()}
            )
            if result.returncode != 0:
                missing.append("ffmpeg (execution failed)")
    except Exception as e:
        missing.append(f"ffmpeg (check error: {e})")

    # 3. node — 격리 캐시에서 실행 가능 확인
    try:
        node_path = pot_provider.node_exe()
        if not node_path:
            missing.append("node (not found in cache)")
        else:
            result = subprocess.run(
                [node_path, "--version"],
                capture_output=True,
                timeout=5,
                **{**{}, **__import__("chzzktube.infra.platform").spawn_kwargs()}
            )
            if result.returncode != 0:
                missing.append("node (execution failed)")
    except Exception as e:
        missing.append(f"node (check error: {e})")

    # 4. POT server readiness — 디스크 준비 상태만 확인 (liveness 아님)
    try:
        from chzzktube.infra.pot_server import pot_readiness
        from chzzktube.infra.po_client import server_ping
        if not server_ping():
            ready, _ = pot_readiness()
            if not ready:
                missing.append("pot server (not ready)")
    except Exception:
        missing.append("pot server (check error)")

    return len(missing) == 0, missing


_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _cli_base(label):
    """라벨 → 실제 CLI 명령 배열 (없으면 None). F12 상세 로그용 원문 실행.

    [v3.8.0 격리] 실행체 해석은 앱 전용 저장소 단일 경로로 일원화:
    - ytdlp: dev/frozen 공통 — 앱이 실제로 사용하는 인터프리터 + .pylib
      오버레이(항상 sys.path 선두)를 타는 `python -m yt_dlp`. 시스템 PATH의
      yt-dlp는 절대 참조하지 않는다.
    - ffmpeg/node/npm: components.ffmpeg_exe / pot_provider.node_exe·npm_exe
      (writable_base 격리 캐시) 단일 참조 — shutil.which 폴백 철폐.
    """
    if label == "ytdlp":
        # dev/frozen 공통: 앱 런타임 인터프리터로 오버레이 모듈 실행 (PATH 무관)
        return [sys.executable, "-m", "yt_dlp"]
    if label == "streamlink":
        return [sys.executable, "-m", "streamlink"]
    if label == "ffmpeg":
        try:
            from chzzktube.infra.components import ffmpeg_exe
            p = ffmpeg_exe()
        except Exception:
            p = None
        return [p] if p else None
    if label == "node":
        try:
            import chzzktube.infra.pot_provider as pot_provider
            p = pot_provider.node_exe()
        except Exception:
            p = None
        return [p] if p else None
    if label == "npm":
        try:
            import chzzktube.infra.pot_provider as pot_provider
            p = pot_provider.npm_exe()
        except Exception:
            p = None
        return [p] if p else None
    return None


def _cli_env(label):
    """npm 시스 스크립트가 'env node'로 node를 찾도록 PATH 보강 (npm만)."""
    if label != "npm":
        return None
    try:
        import chzzktube.infra.pot_provider as pot_provider
        node = pot_provider.node_exe()
    except Exception:
        node = None
    if not node:
        return None
    env = os.environ.copy()
    ndir = os.path.dirname(node)
    env["PATH"] = ndir + os.pathsep + env.get("PATH", "")
    return env


def cli_raw(label, *args, timeout=15):
    """실제 CLI를 실행해 '터미널에서 친 것과 동일한 원문 출력'을 반환.

    반환: (cmdline, output) — 도구 없으면 (None, None), 실행 예외면
    (cmdline, "[Type] msg"). 출력은 stdout+stderr 합본 원문 전체.

    [레이어 원칙] 수집층은 절대 절단하지 않는다. 원문은 history에 전량
    기록되며, F12 적재 시점의 절취는 호출부(truncate_for_full_log)가 담당.
    수집에서 자르면 원본이 영구 소실되어 복원 불가.
    """
    cmd = _cli_base(label)
    if not cmd:
        return None, None
    full_cmd = cmd + list(args)
    env = _cli_env(label)
    try:
        proc = subprocess.run(
            full_cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=env,
            **spawn_kwargs(),
        )
    except Exception as e:
        return " ".join(full_cmd), f"[{type(e).__name__}] {e}"
    out = ((proc.stdout or "") + (proc.stderr or "")).strip()
    if not out:
        return " ".join(full_cmd), None
    return " ".join(full_cmd), out


def truncate_for_full_log(out, max_lines=6, max_width=160):
    """F12 적재 시점 절취 — history는 원문 전량을 이미 기록했으므로 뷰만 자른다.

    max_lines>0 → 앞 N줄만 + '… (M lines truncated)' 꼬리.
    over-long 단일 줄은 max_width로 절단 (ffmpeg configuration: 500자 대책).
    ffmpeg configuration: 라인 및 이어지는 빌드 설정 줄들은 제거.
    """
    import re
    text = str(out or "")
    if not text:
        return ""
    # ffmpeg -version의 configuration: 부터 끝까지 제거 (빌드 설정 10+줄 방지)
    text = re.sub(r"(?m)^configuration:.*\n(?:^ .*\n)*", "", text)
    lines = text.splitlines()
    if max_width and max_width > 0:
        lines = [l if len(l) <= max_width else l[:max_width] + "…" for l in lines]
    if max_lines and max_lines > 0 and len(lines) > max_lines:
        kept = lines[:max_lines]
        kept.append(f"… ({len(lines) - max_lines} lines truncated)")
        return "\n".join(kept)
    return "\n".join(lines)


def _ffmpeg_version(path, timeout=3):
    """`ffmpeg -version`에서 숫자 코어 버전(MAJOR.MINOR[.PATCH]) 추출. 실패 시 None.

    - 표준/홈브루: 'ffmpeg version 9.0.1' → 9.0.1
    - extra version/빌드 태그/일자(YYYMMDD) 접미는 정규식으로 절단:
      '9.0.1_1'·'7.1.1-20240815-g…' → 9.0.1 · 7.1.1
      (homebrew bottle Cellar/ffmpeg/9.0.1_1 처럼 configuration 줄에만
      extra version이 드러나는 경우도 그대로 대응)
    - 첫 줄 미매치(N-일자 빌드 등) 시 configuration 줄 폴백: '…/ffmpeg/9.0.1_1'
    """
    try:
        import re
        out = subprocess.run(
            [path, "-version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            **spawn_kwargs(),
        )
        text = (out.stdout or out.stderr or "")
        # 1) 표준 첫 줄 — 숫자 코어 3단만 (extra version 접미부 미포함)
        m = re.search(r"ffmpeg version\s+(\d+(?:\.\d+){1,2})", text)
        if not m:
            # 2) configuration 줄 폴백 — --prefix=…/ffmpeg/9.0.1_1
            m = re.search(r"ffmpeg[/\\\-](\d+(?:\.\d+){1,2})(?![0-9.])", text)
        return m.group(1) if m else None
    except Exception:
        return None

def _exe_suffix():
    return ".exe" if sys.platform == "win32" else ""

def _download_to(url, dest, timeout=120):
    """Download url to dest file. Returns True on success."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp, open(dest, "wb") as f:
            shutil.copyfileobj(resp, f)
        return True
    except Exception:
        return False

def _get_pypi_whl_url(pypi_name):
    """PyPI에서 최신 whl 다운로드 URL을 조회. 실패 시 None."""
    try:
        with urllib.request.urlopen(_PYPI_API.format(pkg=pypi_name), timeout=10) as resp:
            data = json.load(resp)
        urls = data.get("urls") or []
        # manylinux/macosx/windows whl 우선순호
        preferred = [f for f in urls if "whl" in f.get("filename", "")]
        if preferred:
            return preferred[0].get("url")
    except Exception:
        pass
    return None

def _extract_from_whl(whl_path, dest_dir):
    """whl 파일(zip)을 dest_dir에 압축 해제."""
    import zipfile
    try:
        with zipfile.ZipFile(whl_path) as zf:
            zf.extractall(dest_dir)
        return True
    except Exception:
        return False

def _frozen_upgrade_ytdlp(channel="stable"):
    """yt-dlp 직접 다운로드 → 프로젝트 오버레이(.pylib/)에 교체.

    dev/frozen 공통: venv(site-packages, uv 소유)는 절대 건드리지 않는다.
    Stable: PyPI release whl에서 yt-dlp 라이브러리 전체(yt_dlp/ 패키지 +
    yt_dlp-*.dist-info)를 오버레이에 해제 — 오버레이가 항상 우선한다.
    Nightly: GitHub nightly-builds release에서 yt-dlp 실행파일 다운로드
    → 오버레이 루트에 yt-dlp{.exe} 저장 (frozen에서 _cli_base가 PATH 찾기).
    """
    suffix = _exe_suffix()
    if channel == "nightly":
        url = _NIGHTLY_API.format(_ext=suffix)
        overlay = _overlay_root()
        if not overlay:
            return 1, "overlay dir unavailable"
        dest = os.path.join(overlay, f"yt-dlp{suffix}")
        if _download_to(url, dest):
            return 0, f"updated to {channel} (overlay)"
        return 1, "download failed"

    url = _get_pypi_whl_url("yt-dlp")
    if not url:
        return 1, "No whl found on PyPI"
    try:
        with tempfile.TemporaryDirectory() as tmp:
            whl_path = os.path.join(tmp, "yt-dlp.whl")
            if not _download_to(url, whl_path):
                return 1, "whl download failed"
            overlay = _overlay_root()
            if not overlay:
                return 1, "overlay dir unavailable"
            if _extract_pylib_whl(whl_path, overlay, "yt_dlp-"):
                _refresh_overlay_sys_path()
                return 0, f"updated to {channel} (overlay)"
        return 1, "whl extract failed"
    except Exception as e:
        return 1, f"whl extract failed: {e}"

def _extract_pylib_whl(whl_path, pylib_root, prefix):
    """프로젝트 오버레이(.pylib/)에 whl 해제 + 구 dist-info 정리 (순수·테스트 가능).

    venv(site-packages, uv 소유)는 절대 건드리지 않는다. 해제 후
    sys.path 선두(.pylib/)의 오버레이 복사가 venv보다 항상 우선한다.
    prefix: "streamlink-" 또는 "yt_dlp-" — 구 dist-info(glob) 스캔용.
    """
    import zipfile
    keep_dist = None
    try:
        with zipfile.ZipFile(whl_path) as zf:
            # [정확 판정] whl(zip)에는 디렉터리 엔트리가 없다 — 파일 경로의
            # 첫 세그먼트로 dist-info 이름을 얻어야 한다. (과거 "…/"
            # endswith 판정은 항상 None이 되어 구 dist-info 정리가
            # 통째로 스킵 → 버전 메타데이터가 옛 값으로 남아 무한 업데이트)
            for name in zf.namelist():
                if name.startswith(prefix) and ".dist-info/" in name:
                    keep_dist = name.split("/", 1)[0]
                    break
        if not _extract_from_whl(whl_path, pylib_root):
            return False
        if keep_dist:
            import glob
            for old in glob.glob(os.path.join(pylib_root, f"{prefix}*.dist-info")):
                if os.path.basename(old) != keep_dist:
                    shutil.rmtree(old, ignore_errors=True)
        return True
    except Exception:
        return False


def _extract_streamlink_whl(whl_path, site_root):
    """[레거시 shim] 구 호출부 호환 — 새 코드는 _extract_pylib_whl 사용."""
    return _extract_pylib_whl(whl_path, site_root, "streamlink-")


def _overlay_root():
    """인앱 업데이트 해제 대상 — 프로젝트 오버레이(.pylib/).

    venv는 uv 소유 → 손대지 않는다. 부트스트랩이 이 경로를 sys.path 선두에
    두므로 오버레이가 항상 우선 적용된다.
    """
    try:
        from chzzktube.core.config import pylib_overlay_path

        return os.path.abspath(pylib_overlay_path())
    except Exception:
        return ""


def _refresh_overlay_sys_path():
    try:
        path = _overlay_root()
        if not path:
            return
        if path not in sys.path:
            sys.path.insert(0, path)
        import importlib

        importlib.invalidate_caches()
    except Exception:
        pass


def _frozen_upgrade_streamlink():
    """streamlink 직접 다운로드 → 프로젝트 오버레이(.pylib/)에 교체.

    dev/frozen 공통: venv(site-packages, uv 소유)는 절대 건드리지 않는다.
    해제 후 sys.path 선두의 오버레이 복사가 항상 우선한다.
    """
    whl_url = _get_pypi_whl_url("streamlink")
    if not whl_url:
        return 1, "No whl found on PyPI"

    try:
        with tempfile.TemporaryDirectory() as tmp:
            whl_path = os.path.join(tmp, "streamlink.whl")
            if not _download_to(whl_url, whl_path):
                return 1, "whl download failed"
            overlay = _overlay_root()
            if not overlay:
                return 1, "overlay dir unavailable"
            if _extract_pylib_whl(whl_path, overlay, "streamlink-"):
                _refresh_overlay_sys_path()
                return 0, "updated to latest (overlay)"
        return 1, "whl extract failed"
    except Exception as e:
        return 1, f"streamlink update failed: {e}"

def upgrade_packages(packages, channel="stable"):
    """직접 다운로드 방식으로 패키지 업데이트 (Dev/Frozen 통합).

    [v3.4.0 변경] 해제 대상은 프로젝트 오버레이(.pylib/) — venv(site-packages,
    uv 소유)는 절대 건드리지 않는다. 요약 문자열에 "(overlay)" 표기.
    이유: 포터블 빌드와 Dev에서 동일한 코드 경로를 타야 디버깅이 가능.
    pip install은 빌드 시에만 사용 (PyInstaller 번들 시점).

    Returns (returncode, output tail). Worker thread only.
    """
    is_frozen = getattr(sys, "frozen", False)

    # yt-dlp: Dev/Frozen 통합 - 직접 다운로드
    if "yt-dlp" in packages:
        return _frozen_upgrade_ytdlp(channel)

    # streamlink: Dev/Frozen 통합 - whl 직접 다운로드
    if "streamlink" in packages:
        return _frozen_upgrade_streamlink()

```

## File: chzzktube/infra/provisioning/__init__.py

```python
"""Provisioning Package — 외부 라이브러리 수급/검증/매니페스트 단일 진실.

아키텍처:
- Resolver: 버전 해석 & 미러 선택
- Downloader: 병렬 다운로드 & 재시도/폴백
- Verifier: 다층 검증 (해시/실행/헬스체크)
- Manifest: JSON 매니페스트 (단일 진실 공급원)
- Manager: 오케스트레이터 파사드
- Bridge: 동기 컨텍스트 어댑터 (기존 동기 함수 지원)
"""
from chzzktube.infra.provisioning.resolver import (
    ComponentSpec,
    ComponentType,
    Mirror,
    MIRROR_REGISTRY,
)
from chzzktube.infra.provisioning.downloader import ParallelDownloader, DownloadTask, DownloadResult
from chzzktube.infra.provisioning.verifier import Verifier, VerifyResult
from chzzktube.infra.provisioning.manifest import ProvisionManifest, ComponentRecord
from chzzktube.infra.provisioning.manager import ProvisioningManager, ProvisionPlan, ProvisionResult
from chzzktube.infra.provisioning.bridge import (
    provision_component_sync,
    provision_all_sync,
    resolve_all_sync,
)

__all__ = [
    "ComponentSpec",
    "ComponentType",
    "Mirror",
    "MIRROR_REGISTRY",
    "ParallelDownloader",
    "DownloadTask",
    "DownloadResult",
    "Verifier",
    "VerifyResult",
    "ProvisionManifest",
    "ComponentRecord",
    "ProvisioningManager",
    "ProvisionPlan",
    "ProvisionResult",
    "provision_component_sync",
    "provision_all_sync",
    "resolve_all_sync",
]
```

## File: chzzktube/infra/provisioning/bridge.py

```python
"""Sync Bridge — 비동기 ProvisioningManager를 동기 컨텍스트에서 호출.

기존 동기 함수(components.ensure_ffmpeg, node_provider.ensure_node_runtime 등)가
ProvisioningManager(async)를 직접 호출할 수 있게 하는 어댑터.

로그 버스 정책: 모든 동작은 raw_log → LogEvent 단일 경로.
"""
import asyncio
from typing import Optional

from chzzktube.infra.provisioning.manager import ProvisioningManager, ProvisionResult


def provision_component_sync(
    component: str,
    log_func=None,
    channel: str = "stable",
    force: bool = False,
) -> Optional[ProvisionResult]:
    """단일 구성요소 동기 수급 — 기존 동기 코드에서 호출.

    Args:
        component: 구성요소명 (yt-dlp, streamlink, ffmpeg, node, bgutil)
        log_func: 로그 콜백 (LogEvent 수신)
        channel: stable / nightly
        force: 이미 최신이어도 강제 재수급

    Returns:
        ProvisionResult (성공/실패) 또는 None (수급 대상 없음 = 이미 최신)
    """
    async def _run():
        mgr = ProvisioningManager(log_func=log_func)
        plans = await mgr.resolve(stale_only=not force, channel=channel)
        target = [p for p in plans if p.component == component]
        if not target:
            return None  # 이미 최신
        results = await mgr.provision(target)
        await mgr.commit(target, results)
        return results[0] if results else None

    return asyncio.run(_run())


def provision_all_sync(
    log_func=None,
    channel: str = "stable",
    stale_only: bool = True,
) -> list[ProvisionResult]:
    """전체 구성요소 동기 수급."""
    async def _run():
        mgr = ProvisioningManager(log_func=log_func)
        return await mgr.ensure_all(stale_only=stale_only, channel=channel)

    return asyncio.run(_run())


def resolve_all_sync(
    channel: str = "stable",
    stale_only: bool = False,
) -> list:
    """전체 구성요소 플랜 조회 (다운로드 없이)."""
    async def _run():
        mgr = ProvisioningManager()
        return await mgr.resolve(stale_only=stale_only, channel=channel)

    return asyncio.run(_run())
```

## File: chzzktube/infra/provisioning/downloader.py

```python
"""Parallel Downloader — 병렬 다운로드 & 재시도/폴백.

- httpx + asyncio 기반
- 세마포어로 동시성 제어
- 지수 백오프 + 지터 재시도
- 진행률 하트비트 콜백
- .part 원자적 쓰기
"""
import asyncio
import hashlib
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Awaitable, Optional

import httpx


@dataclass(frozen=True)
class DownloadTask:
    component: str
    url: str
    dest: Path
    expected_sha256: Optional[str] = None
    mirror_name: str = ""


@dataclass(frozen=True)
class DownloadResult:
    task: DownloadTask
    success: bool
    error: Optional[str] = None
    bytes_downloaded: int = 0
    sha256: Optional[str] = None


ProgressCallback = Callable[[str, int, int], Awaitable[None]]


class ParallelDownloader:
    def __init__(
        self,
        max_concurrent: int = 3,
        max_retries: int = 3,
        base_timeout: float = 120.0,
        progress_cb: Optional[ProgressCallback] = None,
    ):
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.max_retries = max_retries
        self.base_timeout = base_timeout
        self.progress_cb = progress_cb

    async def download_all(self, tasks: list[DownloadTask]) -> list[DownloadResult]:
        """모든 태스크 병렬 다운로드."""
        # httpx 클라이언트 공유
        limits = httpx.Limits(max_connections=max_concurrent, max_keepalive_connections=max_concurrent)
        timeout = httpx.Timeout(self.base_timeout, connect=10.0)
        
        async with httpx.AsyncClient(
            limits=limits,
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": "ChzzkTube-Provisioner/1.0"},
        ) as client:
            async def _download_one(task: DownloadTask) -> DownloadResult:
                async with self.semaphore:
                    return await self._download_with_retry(client, task)
            
            return await asyncio.gather(*[_download_one(t) for t in tasks])

    async def _download_with_retry(self, client: httpx.AsyncClient, task: DownloadTask) -> DownloadResult:
        last_error = None
        
        for attempt in range(self.max_retries):
            try:
                async with client.stream("GET", task.url) as resp:
                    resp.raise_for_status()
                    total = int(resp.headers.get("content-length", 0))
                    
                    task.dest.parent.mkdir(parents=True, exist_ok=True)
                    part_path = task.dest.with_suffix(task.dest.suffix + ".part")
                    
                    downloaded = 0
                    sha256 = hashlib.sha256()
                    
                    async with part_path.open("wb") as f:
                        async for chunk in resp.aiter_bytes(1024 * 512):
                            f.write(chunk)
                            sha256.update(chunk)
                            downloaded += len(chunk)
                            if self.progress_cb and total > 0:
                                await self.progress_cb(task.component, downloaded, total)
                    
                    computed_sha256 = sha256.hexdigest()
                    
                    # 해시 검증
                    if task.expected_sha256:
                        if computed_sha256 != task.expected_sha256:
                            raise ValueError(f"SHA256 mismatch: {computed_sha256} != {task.expected_sha256}")
                    
                    # 원자적 이동
                    part_path.replace(task.dest)
                    
                    return DownloadResult(
                        task=task,
                        success=True,
                        bytes_downloaded=downloaded,
                        sha256=computed_sha256,
                    )
                    
            except Exception as e:
                last_error = e
                # part 파일 정리
                part_path = task.dest.with_suffix(task.dest.suffix + ".part")
                if part_path.exists():
                    try:
                        part_path.unlink()
                    except Exception:
                        pass
                
                if attempt < self.max_retries - 1:
                    # 지수 백오프 + 지터
                    wait_time = (2 ** attempt) + random.uniform(0, 1)
                    await asyncio.sleep(wait_time)
        
        return DownloadResult(
            task=task,
            success=False,
            error=str(last_error) if last_error else "Unknown error",
        )
```

## File: chzzktube/infra/provisioning/manager.py

```python
"""ProvisioningManager — 외부 라이브러리 수급/검증/커밋 단일 오케스트레이터.

로그 버스 정책 (HANDOVER §5-21):
- 모든 앱 동작은 raw_log.raw() → LogEvent 단일 경로
- Qt 시그널은 결과/제어/브리지에만 사용 (log_full/log_concise 시그널 금지)
- 발행자가 라벨과 to_tui 결정
- history ⊇ full ⊇ TUI (큐 2048, 버퍼 4096 유한)
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import asyncio
import time
import zipfile
import tarfile
import tempfile
import shutil

from chzzktube.core import config
from chzzktube.infra.provisioning.resolver import (
    ComponentSpec, ComponentType, MIRROR_REGISTRY, filter_assets,
)
from chzzktube.infra.provisioning.downloader import ParallelDownloader, DownloadTask
from chzzktube.infra.provisioning.verifier import Verifier
from chzzktube.infra.provisioning.manifest import ProvisionManifest, ComponentRecord
import chzzktube.core.raw_log as raw_log
from chzzktube.core.log_emitter import emit_component


@dataclass
class ProvisionPlan:
    component: str
    spec: ComponentSpec
    mirror_name: str
    version: str
    download_url: str
    expected_sha256: Optional[str]
    install_path: Path
    is_update: bool
    archive_type: str  # "whl", "zip", "tar.gz", "tar.xz", "server"


@dataclass
class ProvisionResult:
    component: str
    success: bool
    version: Optional[str] = None
    error: Optional[str] = None
    action: str = ""
    sha256: str = ""


class ProvisioningManager:
    """단일 파사드 — resolve → download → verify → commit."""
    
    def __init__(self, log_func=None):
        self.base_dir = Path(config.writable_base())
        self.overlay_root = Path(config.pylib_overlay_path())
        self.manifest = ProvisionManifest.load(self.base_dir)
        self.log = log_func
        self._downloader = ParallelDownloader(progress_cb=self._on_progress)

    def _emit(self, stage, status, scope, msg, is_status=False, is_error=False):
        """raw_log 버스 단일 경유."""
        evt = emit_component(stage, status, scope, msg, is_status=is_status, is_error=is_error)
        if self.log:
            self.log(evt)
        raw_log.raw("provisioning", evt, to_tui=is_status, is_error=is_error)

    async def _on_progress(self, component: str, downloaded: int, total: int):
        """다운로드 진행률 하트비트 (무페이로드 아님 — TUI 상태용)."""
        if total > 0:
            pct = int(downloaded / total * 100)
            mb = downloaded // (1024 * 1024)
            self._emit("DEPS", "RUN", component.upper(),
                       f"downloading... {mb}MB ({pct}%)", is_status=True)

    # ── 1. Resolve ──────────────────────────────────────────────
    async def resolve(self, stale_only: bool = False, channel: str = "stable") -> list[ProvisionPlan]:
        """모든 구성요소에 대해 최신 버전 확인 + 플랜 생성."""
        self.manifest.last_check = time.time()
        plans = []
        
        for name, spec in MIRROR_REGISTRY.items():
            if spec.channel != channel:
                continue
            
            latest_ver, latest_url, sha256, mirror_name, archive_type = await self._fetch_latest(spec)
            if not latest_ver or not latest_url:
                self._emit("DEPS", "WARN", name.upper(), f"no mirror resolved")
                continue
            
            if stale_only and not self.manifest.is_stale(name, latest_ver):
                continue
            
            if spec.type == ComponentType.PYTHON_PKG:
                install_path = self.overlay_root
            else:
                install_path = self.base_dir / spec.install_rel_path
            
            plans.append(ProvisionPlan(
                component=name,
                spec=spec,
                mirror_name=mirror_name,
                version=latest_ver,
                download_url=latest_url,
                expected_sha256=sha256,
                install_path=install_path,
                is_update=name in self.manifest.components,
                archive_type=archive_type,
            ))
        
        return plans

    async def _fetch_latest(self, spec: ComponentSpec):
        """미러 체인에서 최신 버전/URL/sha256/미러명/arch타입 조회."""
        for mirror in sorted(spec.mirrors, key=lambda m: m.priority):
            try:
                if mirror.name == "pypi":
                    return await self._fetch_from_pypi(spec, mirror)
                elif "github" in mirror.name:
                    return await self._fetch_from_github(spec, mirror)
                elif mirror.name == "nodejs.org":
                    return await self._fetch_from_nodejs(spec, mirror)
            except Exception:
                continue
        return None, None, None, None, None

    async def _fetch_from_pypi(self, spec, mirror):
        """PyPI JSON API에서 최신 버전 + whl URL."""
        import httpx
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(mirror.url_template.format(pkg=spec.name))
            data = resp.json()
            version = data["info"]["version"]
            sha256 = None
            
            for f in data.get("releases", {}).get(version, []):
                fn = f["filename"].lower()
                if "py3-none-any" in fn and "whl" in fn:
                    sha256 = f.get("digests", {}).get("sha256")
                    return version, f["url"], sha256, "pypi", "whl"
            
            for f in data.get("releases", {}).get(version, []):
                if "whl" in f["filename"].lower():
                    sha256 = f.get("digests", {}).get("sha256")
                    return version, f["url"], sha256, "pypi", "whl"
        
        return None, None, None, None, None

    async def _fetch_from_github(self, spec, mirror):
        """GitHub Releases API에서 최신 릴리스 asset 선택."""
        import httpx
        async with httpx.AsyncClient(timeout=15) as client:
            if spec.name == "bgutil-ytdlp-pot-provider":
                api_url = f"https://api.github.com/repos/Brainicism/{spec.name}/releases/latest"
                resp = await client.get(api_url)
                data = resp.json()
                tag_name = data["tag_name"]
                assets = filter_assets(data.get("assets", []), spec)
                if assets:
                    asset = assets[0]
                    return tag_name, asset["browser_download_url"], None, "github", "server"
            else:
                resp = await client.get(mirror.url_template)
                data = resp.json()
                tag_name = data["tag_name"]
                assets = filter_assets(data.get("assets", []), spec)
                if assets:
                    asset = assets[0]
                    return tag_name, asset["browser_download_url"], None, mirror.name, "zip"
        
        return None, None, None, None, None

    async def _fetch_from_nodejs(self, spec, mirror):
        """nodejs.org dist index에서 latest LTS."""
        import httpx
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(mirror.url_template)
            entries = resp.json()
            ver = next(
                (e.get("version") for e in entries
                 if str(e.get("version", "")).startswith("v22.")),
                None
            )
            if not ver:
                ver = entries[0]["version"]
            
            from chzzktube.infra.node_provider import _platform_node_url
            url = _platform_node_url(ver)
            archive_type = "tar.gz" if "darwin" in url else "zip"
            return ver, url, None, "nodejs.org", archive_type
        
        return None, None, None, None, None

    # ── 2. Provision ────────────────────────────────────────────
    async def provision(self, plans: list[ProvisionPlan]) -> list[ProvisionResult]:
        """플랜 실행: 다운로드 → 추출/설치 → 검증."""
        if not plans:
            return []

        tasks = []
        for plan in plans:
            dest = self.base_dir / "downloads" / plan.component
            dest.parent.mkdir(parents=True, exist_ok=True)
            tasks.append(DownloadTask(
                component=plan.component,
                url=plan.download_url,
                dest=dest,
                expected_sha256=plan.expected_sha256,
                mirror_name=plan.mirror_name,
            ))

        results = await self._downloader.download_all(tasks)

        final_results = []
        for plan, dl_result in zip(plans, results):
            if not dl_result.success:
                self._emit("DEPS", "FAIL", plan.component.upper(),
                           f"download failed: {dl_result.error[:100]}")
                final_results.append(ProvisionResult(
                    plan.component, False, error=f"download failed: {dl_result.error}"
                ))
                continue

            installed_path = await self._extract_and_install(plan, dl_result.task.dest, dl_result.sha256 or "")
            if isinstance(installed_path, str):
                self._emit("DEPS", "FAIL", plan.component.upper(),
                           f"install failed: {installed_path}")
                final_results.append(ProvisionResult(
                    plan.component, False, error=f"install failed: {installed_path}"
                ))
                continue

            verify_result = Verifier.verify(plan.spec, installed_path)
            if not verify_result.success:
                self._emit("DEPS", "FAIL", plan.component.upper(),
                           f"verification failed: {verify_result.error}")
                final_results.append(ProvisionResult(
                    plan.component, False, error=f"verification failed: {verify_result.error}"
                ))
                continue

            self._emit("DEPS", "OK", plan.component.upper(),
                       f"{plan.component} {'updated' if plan.is_update else 'installed'} → {verify_result.version}")
            final_results.append(ProvisionResult(
                plan.component, True, version=verify_result.version,
                action="updated" if plan.is_update else "installed",
                sha256=dl_result.sha256 or "",
            ))

        return final_results

    async def _extract_and_install(self, plan: ProvisionPlan, archive: Path, sha256: str) -> Path:
        """아카이브 추출/설치 수행."""
        try:
            if plan.archive_type == "whl":
                from chzzktube.infra.updater import _extract_pylib_whl
                prefix = plan.component + "-" if plan.component != "yt-dlp" else "yt_dlp-"
                with zipfile.ZipFile(archive) as z:
                    z.extractall(str(self.overlay_root))
                _extract_pylib_whl(str(archive), str(self.overlay_root), prefix)
                return self.overlay_root

            elif plan.archive_type in ("zip", "server"):
                with tempfile.TemporaryDirectory(prefix=f"cz_{plan.component}_") as td:
                    with zipfile.ZipFile(archive) as z:
                        z.extractall(td)
                    dest = self.base_dir / plan.component
                    if dest.exists():
                        shutil.rmtree(dest, ignore_errors=True)
                    shutil.move(td, str(dest))
                    return dest

            elif plan.archive_type == "tar.gz":
                with tempfile.TemporaryDirectory(prefix=f"cz_{plan.component}_") as td:
                    with tarfile.open(archive, "r:gz") as tar:
                        tar.extractall(td)
                    dest = self.base_dir / plan.component
                    if dest.exists():
                        shutil.rmtree(dest, ignore_errors=True)
                    shutil.move(td, str(dest))
                    return dest

            elif plan.archive_type == "tar.xz":
                with tempfile.TemporaryDirectory(prefix=f"cz_{plan.component}_") as td:
                    with tarfile.open(archive, "r:xz") as tar:
                        tar.extractall(td, filter="data")
                    dest = self.base_dir / plan.component
                    if dest.exists():
                        shutil.rmtree(dest, ignore_errors=True)
                    shutil.move(td, str(dest))
                    return dest

            return f"unknown archive type: {plan.archive_type}"

        except Exception as e:
            return f"{type(e).__name__}: {e}"

    # ── 3. Commit ───────────────────────────────────────────────
    async def commit(self, plans: list[ProvisionPlan], results: list[ProvisionResult]) -> None:
        """manifest 갱신 + 오버레이/환경변수 리로드."""
        now = time.time()
        
        for plan, result in zip(plans, results):
            if result.success:
                self.manifest.update_component(ComponentRecord(
                    name=plan.component,
                    version=result.version or plan.version,
                    source=plan.mirror_name,
                    mirror=plan.mirror_name,
                    install_path=plan.spec.install_rel_path,
                    verified_at=now,
                    verify_version=result.version or "",
                    sha256=result.sha256,
                ))
        
        self.manifest.last_full_update = now
        self.manifest.save(self.base_dir)
        
        self._refresh_overlay()
        self._refresh_path()
        
        downloads_dir = self.base_dir / "downloads"
        if downloads_dir.exists():
            shutil.rmtree(downloads_dir, ignore_errors=True)

    def _refresh_overlay(self):
        """.pylib overlay 리로드."""
        try:
            from chzzktube.infra.pylib_bootstrap import bootstrap
            path = bootstrap(clear_caches=True)
            self._emit("DEPS", "OK", "PY", f"overlay refreshed: {path}")
        except Exception as e:
            self._emit("DEPS", "WARN", "PY", f"overlay refresh failed: {e}")

    def _refresh_path(self):
        """PATH에 검증된 binary 디렉토리 추가."""
        try:
            import os
            for name, rec in self.manifest.components.items():
                if name in ("ffmpeg", "node"):
                    spec = MIRROR_REGISTRY.get(name)
                    if spec and spec.type == ComponentType.BINARY:
                        bin_path = self.base_dir / rec.install_path
                        bin_dir = bin_path.parent if bin_path.is_file() else bin_path
                        if bin_dir.is_dir():
                            path_env = os.environ.get("PATH", "")
                            parts = path_env.split(os.pathsep) if path_env else []
                            if str(bin_dir) not in parts:
                                os.environ["PATH"] = os.pathsep.join([str(bin_dir)] + parts)
        except Exception:
            pass

    async def ensure_all(self, stale_only: bool = True, channel: str = "stable") -> list[ProvisionResult]:
        """전체 프로비저닝: resolve → download → verify → commit."""
        plans = await self.resolve(stale_only=stale_only, channel=channel)
        if not plans:
            self._emit("DEPS", "SKIP", "DEPS", "all components up-to-date")
            return []
        
        results = await self.provision(plans)
        await self.commit(plans, results)
        
        ok_count = sum(1 for r in results if r.success)
        fail_count = len(results) - ok_count
        if fail_count == 0:
            self._emit("DEPS", "DONE", "DEPS", f"provisioned {ok_count} components")
        else:
            self._emit("DEPS", "WARN", "DEPS", f"{ok_count} ok, {fail_count} failed")
        
        return results

```

## File: chzzktube/infra/provisioning/manifest.py

```python
"""Provision Manifest — 단일 진실 공급원 (JSON).

writable_base()/provision_manifest.json에 저장.
모든 구성요소의 버전/출처/경로/검증시점 영구 기록.
"""
import json
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class ComponentRecord:
    name: str
    version: str
    source: str              # "pypi", "github", "nodejs.org", etc.
    mirror: str              # 실제 사용된 미러
    install_path: str        # writable_base 기준 상대 경로
    verified_at: float       # unix timestamp
    verify_version: str      # 검증 시 추출된 버전 문자열
    sha256: str = ""         # 다운로드 파일 해시


@dataclass
class ProvisionManifest:
    schema_version: int = 1
    components: dict[str, ComponentRecord] = field(default_factory=dict)
    last_check: float = 0
    last_full_update: float = 0

    MANIFEST_FILENAME = "provision_manifest.json"

    @classmethod
    def load(cls, base_dir: Path) -> "ProvisionManifest":
        path = base_dir / cls.MANIFEST_FILENAME
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                comps = {
                    k: ComponentRecord(**v) for k, v in data.get("components", {}).items()
                }
                return cls(
                    schema_version=data.get("schema_version", 1),
                    components=comps,
                    last_check=data.get("last_check", 0),
                    last_full_update=data.get("last_full_update", 0),
                )
            except Exception:
                pass
        return cls()

    def save(self, base_dir: Path) -> None:
        """원자적 쓰기 (.tmp → rename)."""
        path = base_dir / self.MANIFEST_FILENAME
        data = {
            "schema_version": self.schema_version,
            "components": {k: asdict(v) for k, v in self.components.items()},
            "last_check": self.last_check,
            "last_full_update": self.last_full_update,
        }
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)

    def is_stale(self, name: str, latest_version: str) -> bool:
        """manifest 버전 vs 최신 버전 비교."""
        rec = self.components.get(name)
        if not rec:
            return True
        return rec.version != latest_version

    def get_record(self, name: str) -> Optional[ComponentRecord]:
        return self.components.get(name)

    def update_component(self, record: ComponentRecord) -> None:
        self.components[record.name] = record

    def remove_component(self, name: str) -> None:
        self.components.pop(name, None)
```

## File: chzzktube/infra/provisioning/resolver.py

```python
"""Component Resolver — 버전 해석 & 미러 선택.

설계 원칙:
- 버전 하드코딩 없음: latest_stable/latest_lts/channel 전략으로 런타임 해석
- 미러 체인: 우선순위 기반 자동 폴백
- 플랫폼별 asset 필터링: resolver 내부에서 처리
"""
from dataclasses import dataclass
from enum import Enum
from typing import Literal
import sys


class ComponentType(Enum):
    PYTHON_PKG = "python_pkg"      # yt-dlp, streamlink → .pylib (whl)
    BINARY = "binary"              # ffmpeg, node → writable_base/bin (tar.gz/zip)
    SERVER = "server"              # bgutil → writable_base/bgutil (npm build)


@dataclass(frozen=True)
class Mirror:
    name: str                      # "pypi", "github", "nodejs.org", "ghcr.io"
    url_template: str              # "https://pypi.org/pypi/{pkg}/json"
    auth_required: bool = False
    priority: int = 0              # 낮을수록 우선


@dataclass(frozen=True)
class ComponentSpec:
    name: str
    type: ComponentType
    mirrors: tuple[Mirror, ...]
    verify_cmd: tuple[str, ...]    # ("ffmpeg", "-version")
    install_rel_path: str          # "ffmpeg/bin/ffmpeg", ".pylib/yt_dlp"
    # 버전 해석 전략
    version_strategy: Literal["latest_stable", "latest_lts", "pinned", "channel"] = "latest_stable"
    channel: str = "stable"        # "stable" | "nightly"
    # 플랫폼별 asset 필터 키워드
    asset_filters: tuple[str, ...] = ()


# 미러 레지스트리 — 외부 설정 파일로 분리 가능
MIRROR_REGISTRY: dict[str, ComponentSpec] = {
    "yt-dlp": ComponentSpec(
        name="yt-dlp",
        type=ComponentType.PYTHON_PKG,
        version_strategy="latest_stable",
        channel="stable",
        mirrors=(
            Mirror("pypi", "https://pypi.org/pypi/yt-dlp/json", priority=0),
            Mirror("github", "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest", priority=1),
        ),
        verify_cmd=("python", "-m", "yt_dlp", "--version"),
        install_rel_path=".pylib",
    ),
    "streamlink": ComponentSpec(
        name="streamlink",
        type=ComponentType.PYTHON_PKG,
        version_strategy="latest_stable",
        channel="stable",
        mirrors=(
            Mirror("pypi", "https://pypi.org/pypi/streamlink/json", priority=0),
            Mirror("github", "https://api.github.com/repos/streamlink/streamlink/releases/latest", priority=1),
        ),
        verify_cmd=("python", "-m", "streamlink", "--version"),
        install_rel_path=".pylib",
    ),
    "ffmpeg": ComponentSpec(
        name="ffmpeg",
        type=ComponentType.BINARY,
        version_strategy="latest_stable",
        mirrors=(
            Mirror("github_gyan", "https://api.github.com/repos/GyanD/codexffmpeg/releases/latest", priority=0),
            Mirror("github_btb", "https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/latest", priority=1),
            Mirror("evermeet", "https://evermeet.cx/ffmpeg/getrelease/zip", priority=2),
        ),
        verify_cmd=("ffmpeg", "-version"),
        install_rel_path="ffmpeg/bin/ffmpeg",
        asset_filters=("ffmpeg", "static"),
    ),
    "node": ComponentSpec(
        name="node",
        type=ComponentType.BINARY,
        version_strategy="latest_lts",
        mirrors=(
            Mirror("nodejs.org", "https://nodejs.org/dist/index.json", priority=0),
            Mirror("github_node", "https://api.github.com/repos/nodejs/node/releases/latest", priority=1),
        ),
        verify_cmd=("node", "--version"),
        install_rel_path="node/bin/node",
        asset_filters=("node",),
    ),
    "bgutil": ComponentSpec(
        name="bgutil-ytdlp-pot-provider",
        type=ComponentType.SERVER,
        version_strategy="latest_stable",
        mirrors=(
            Mirror("github", "https://api.github.com/repos/Brainicism/bgutil-ytdlp-pot-provider/releases/latest", priority=0),
        ),
        verify_cmd=("node", "server.js", "--health-check"),
        install_rel_path="bgutil-ytdlp-pot-provider",
    ),
}


def get_platform_asset_filters() -> tuple[str, ...]:
    """현재 플랫폼에 맞는 asset 필터 반환."""
    platform = sys.platform
    machine = ""
    try:
        import platform as _platform
        machine = _platform.machine().lower()
    except Exception:
        pass

    if platform == "darwin":
        if machine == "arm64":
            return ("arm64", "macos", "darwin", "apple")
        return ("x86_64", "macos", "darwin", "apple")
    elif platform == "win32":
        return ("win64", "windows", "x64")
    else:
        return ("linux", "x86_64", "amd64")


def filter_assets(assets: list[dict], spec: ComponentSpec) -> list[dict]:
    """플랫폼 및 스펙 필터에 맞는 asset만 선별."""
    platform_filters = get_platform_asset_filters()
    spec_filters = spec.asset_filters
    all_filters = platform_filters + spec_filters

    filtered = []
    for asset in assets:
        name = asset.get("name", "").lower()
        if any(f in name for f in all_filters):
            # 제외 키워드
            if any(x in name for x in ("debug", "symbols", "pdb", ".sig", ".asc")):
                continue
            filtered.append(asset)
    return filtered
```

## File: chzzktube/infra/provisioning/verifier.py

```python
"""Verifier — 다층 검증 (해시/실행 테스트/헬스체크)."""
import sys
import subprocess
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from chzzktube.infra.platform import spawn_kwargs
from chzzktube.infra.provisioning.resolver import ComponentSpec, ComponentType


@dataclass(frozen=True)
class VerifyResult:
    component: str
    success: bool
    error: Optional[str] = None
    version: Optional[str] = None
    installed_path: Optional[Path] = None


class Verifier:
    @staticmethod
    def verify_binary(spec: ComponentSpec, binary_path: Path) -> VerifyResult:
        """바이너리 실행 테스트 + 버전 추출."""
        if not binary_path.exists():
            return VerifyResult(spec.name, False, error="binary not found")
        
        if not binary_path.is_file():
            return VerifyResult(spec.name, False, error="not a file")
        
        try:
            # 실행 권한 확인/부여 (Unix)
            import os
            if not os.access(binary_path, os.X_OK):
                binary_path.chmod(0o755)
            
            # macOS: quarantine 속성 제거
            if sys.platform == "darwin":
                subprocess.run(
                    ["xattr", "-dr", "com.apple.quarantine", str(binary_path)],
                    capture_output=True, check=False
                )
            
            # 실행 테스트
            result = subprocess.run(
                [str(binary_path), *spec.verify_cmd[1:]],
                capture_output=True, text=True, timeout=15,
                **spawn_kwargs()
            )
            
            if result.returncode != 0:
                return VerifyResult(
                    spec.name, False,
                    error=f"exit code {result.returncode}: {result.stderr[:300]}",
                    installed_path=binary_path
                )
            
            # 버전 추출 (첫 줄에서)
            version_line = result.stdout.splitlines()[0] if result.stdout else ""
            return VerifyResult(
                spec.name, True,
                version=version_line.strip(),
                installed_path=binary_path
            )
            
        except subprocess.TimeoutExpired:
            return VerifyResult(spec.name, False, error="verification timeout", installed_path=binary_path)
        except Exception as e:
            return VerifyResult(spec.name, False, error=str(e), installed_path=binary_path)

    @staticmethod
    def verify_python_pkg(spec: ComponentSpec, overlay_root: Path) -> VerifyResult:
        """Python 패키지 검증: whl 해시 + import 테스트 + 버전 확인."""
        try:
            import glob
            
            pkg_dir = spec.name.replace("-", "_")
            dist_info_pattern = str(overlay_root / f"{pkg_dir}-*.dist-info")
            
            for dist_info in glob.glob(dist_info_pattern):
                meta_path = Path(dist_info) / "METADATA"
                if not meta_path.exists():
                    continue
                
                version = None
                for line in meta_path.read_text(encoding="utf-8").splitlines():
                    if line.startswith("Version:"):
                        version = line.split(":", 1)[1].strip()
                        break
                
                if not version:
                    continue
                
                # import 테스트
                try:
                    __import__(pkg_dir)
                    return VerifyResult(
                        spec.name, True,
                        version=version,
                        installed_path=overlay_root
                    )
                except ImportError as e:
                    return VerifyResult(
                        spec.name, False,
                        error=f"import failed: {e}",
                        installed_path=overlay_root
                    )
            
            return VerifyResult(spec.name, False, error="dist-info not found", installed_path=overlay_root)
            
        except Exception as e:
            return VerifyResult(spec.name, False, error=str(e), installed_path=overlay_root)

    @staticmethod
    def verify_bgutil(spec: ComponentSpec, server_dir: Path) -> VerifyResult:
        """bgutil 서버 검증: package.json 버전 + 빌드 산출물 확인."""
        try:
            # server/package.json 확인
            pkg_json = server_dir / "server" / "package.json"
            if not pkg_json.exists():
                return VerifyResult(spec.name, False, error="server/package.json missing", installed_path=server_dir)
            
            version = json.loads(pkg_json.read_text(encoding="utf-8")).get("version", "unknown")
            
            # 빌드 산출물 확인 (dist/main.js 등)
            dist_main = server_dir / "server" / "dist" / "main.js"
            if not dist_main.exists():
                # 구버전 경로도 확인
                alt = server_dir / "dist" / "main.js"
                if not alt.exists():
                    return VerifyResult(spec.name, False, error="built server.js not found", installed_path=server_dir)
            
            return VerifyResult(spec.name, True, version=version, installed_path=server_dir)
            
        except Exception as e:
            return VerifyResult(spec.name, False, error=str(e), installed_path=server_dir)

    @classmethod
    def verify(cls, spec: ComponentSpec, install_path: Path) -> VerifyResult:
        """스펙 타입에 따라 적절한 검증 메서드 디스패치."""
        if spec.type == ComponentType.PYTHON_PKG:
            return cls.verify_python_pkg(spec, install_path)
        elif spec.type == ComponentType.BINARY:
            # 바이너리 경로 계산
            binary_path = install_path
            if install_path.is_dir():
                binary_path = install_path / spec.name
            return cls.verify_binary(spec, binary_path)
        elif spec.type == ComponentType.SERVER:
            return cls.verify_bgutil(spec, install_path)
        else:
            return VerifyResult(spec.name, False, error=f"unknown component type: {spec.type}")
```

## File: chzzktube/core/__init__.py

```python

```

## File: chzzktube/core/chzzk_api.py

```python
### chzzk_api.py - 치지직 공개 API 통신 (클립/VOD/LIVE 메타데이터 + 스트림 목록)
import datetime
import json
import re
import urllib.error
from urllib.parse import urljoin
import urllib.request

from chzzktube.core.cookies import get_browser_cookies
from chzzktube.core.media import get_video_codec_rank


class ChzzkAuthError(Exception):
    """치지직 인증 실패(쿠키 만료/부재/권한 없음) — 상위에서 리커버리 유도용."""
    def __init__(self, message, status_code=None, response_body=None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


def _chzzk_headers():
    """치지직/네이버 API 공통 헤더 — 쿠키는 naver/chzzk 도메인만 평탄화.
    cookies.py 반환 구조는 {도메인: {이름: 값}} 중첩 딕셔너리다.
    치지직/네이버 API 인증에는 naver 계열 쿠키(NID_SEAUT, LDTID 등)가
    필요하므로 해당 도메인만 골라 Cookie 헤더를 구성한다.
    """
    flat_cookies = {}
    for host, names in get_browser_cookies().items():
        if "naver.com" not in host and "chzzk" not in host:
            continue
        flat_cookies.update(names)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://chzzk.naver.com/",
    }
    if flat_cookies:
        headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in flat_cookies.items())
    return headers

def _get_json(url, headers):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as res:
        return json.loads(res.read().decode("utf-8"))

def _get_json_with_auth_check(url, headers):
    """JSON GET + 인증 실패 시 ChzzkAuthError 발생."""
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as res:
            return json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace") if e.fp else ""
        if e.code in (401, 403):
            raise ChzzkAuthError(
                f"chzzk auth failed (HTTP {e.code}): cookie expired or missing",
                status_code=e.code,
                response_body=body,
            )
        raise


def analyze_chzzk_clip_api(target_url):
    """치지직 클립 — detail(제목/생성일/채널명) + play-info(rmcnmv MP4 목록)."""
    clean_url = target_url.split("?")[0].rstrip("/")
    clip_id = clean_url.split("/")[-1]
    headers = _chzzk_headers()

    clip_title = clip_id
    created_date = None
    channel_name = None

    detail_url = f"https://api.chzzk.naver.com/service/v1/clips/{clip_id}/detail"
    try:
        d_data = _get_json_with_auth_check(detail_url, headers).get("content", {})
        if d_data.get("clipTitle"):
            clip_title = d_data.get("clipTitle")
        if d_data.get("createdDate"):
            created_date = d_data.get("createdDate").split(" ")[0]
        # 채널명 파싱
        owner = d_data.get("ownerChannel") or {}
        channel_name = owner.get("channelName") or d_data.get("channelName")
    except Exception as e:
        # [증거 남김] 세부 정보 폴백(제목=ID 표기)으로 계속 진행 — 원인은 히스토리에.
        import chzzktube.core.raw_log as raw_log
        from chzzktube.core.log_event import LogEvent
        raw_log.raw(
            "chzzk",
            LogEvent(
                stage="ANAL", status="WARN", scope="CHZ",
                msg=f"chzzk clip detail api failed (clip {clip_id}): {type(e).__name__}: {e}",
                is_error=True,
            ),
            to_tui=False,
        )

    play_info_url = f"https://api.chzzk.naver.com/service/v1/play-info/clip/{clip_id}"
    video_formats = []
    try:
        data = _get_json_with_auth_check(play_info_url, headers)
        cnt = data.get("content", {})
        in_key, video_id = cnt.get("inKey"), cnt.get("videoId")

        if in_key and video_id:
            rmc_url = f"https://apis.naver.com/rmcnmv/rmcnmv/vod/play/v2.0/{video_id}?key={in_key}"
            rmc_data = _get_json_with_auth_check(rmc_url, headers)
            videos = rmc_data.get("videos", {}).get("list", [])
            for idx, v in enumerate(videos):
                enc = v.get("encodingOption", {}) or {}
                encoding_opt = enc.get("name", f"Stream_{idx}")
                height = int(enc.get("height") or 0)
                if not height:
                    h_match = re.search(r"(\d+)p", encoding_opt, re.IGNORECASE)
                    if h_match:
                        height = int(h_match.group(1))
                br = v.get("bitrate", {})
                bitrate_kbps = (
                    int(br.get("video", 0) or 0)
                    if isinstance(br, dict)
                    else int(br or 0)
                )
                source_url = v.get("source", "")
                v_codec = enc.get("vcodec", "H.264")
                a_codec = enc.get("acodec", "AAC")

                video_formats.append(
                    {
                        "id": source_url if source_url else f"chzzk_{idx}",
                        "res": encoding_opt,
                        "height": height,
                        "fps": int(float(enc.get("fps") or 0)),
                        "bitrate": bitrate_kbps,
                        "url": source_url,
                        "vcodec": v_codec,
                        "acodec": a_codec,
                    }
                )
    except Exception as e:
        # [증거 남김] play-info 실패 → formats 비어 상위에서 RuntimeError fail-fast.
        import chzzktube.core.raw_log as raw_log
        from chzzktube.core.log_event import LogEvent
        raw_log.raw(
            "chzzk",
            LogEvent(
                stage="ANAL", status="WARN", scope="CHZ",
                msg=f"chzzk clip play-info api failed (clip {clip_id}): {type(e).__name__}: {e}",
                is_error=True,
            ),
            to_tui=False,
        )

    video_formats.sort(
        key=lambda x: (x["height"], get_video_codec_rank(x["vcodec"]), x["bitrate"]),
        reverse=True,
    )
    return {
        "title": clip_title,
        "date": created_date,
        "clip_id": clip_id,
        "formats": video_formats,
        "channel_name": channel_name,
    }

def analyze_chzzk_vod_api(target_url):
    """치지직 VOD(다시보기) — 메타 + progressive MP4 포맷 목록."""
    m = re.search(r"chzzk\.naver\.com/(?:video|live)/(\d+)", target_url)
    if not m:
        return {"title": None, "date": None, "duration": None, "formats": [], "channel_name": None}
    video_no = m.group(1)
    headers = _chzzk_headers()

    title, date, duration = video_no, None, None
    channel_name = None
    video_formats = []
    try:
        meta = (
            _get_json_with_auth_check(
                f"https://api.chzzk.naver.com/service/v2/videos/{video_no}",
                headers,
            ).get("content")
            or {}
        )
        title = meta.get("videoTitle") or video_no
        title = re.sub(r"\.(mp4|mkv|ts|webm|mov)$", "", title, flags=re.IGNORECASE)
        date = (meta.get("publishDate") or "").split(" ")[0] or None
        duration = meta.get("duration")
        vid, inkey = meta.get("videoId"), meta.get("inKey")
        
        # 채널명 파싱
        channel = meta.get("channel") or {}
        channel_name = channel.get("channelName") or meta.get("channelName")

        if vid and inkey:
            pb = _get_json_with_auth_check(
                f"https://apis.naver.com/neonplayer/vodplay/v2/playback/{vid}"
                f"?key={inkey}&env=real&country=KR&platform=web",
                headers,
            )
            for period in pb.get("period") or []:
                for aset in period.get("adaptationSet") or []:
                    for rep in aset.get("representation") or []:
                        url = next(
                            (
                                b.get("value")
                                for b in (rep.get("baseURL") or [])
                                if isinstance(b, dict)
                                and ".mp4" in str(b.get("value")).split("?")[0]
                            ),
                            None,
                        )
                        if not url:
                            continue
                        codecs = [
                            c.strip()
                            for c in str(rep.get("codecs") or "").split(",")
                            if c.strip()
                        ]
                        h = int(rep.get("height") or 0)
                        video_formats.append(
                            {
                                "id": rep.get("id") or f"vod_{h}",
                                "res": f"{h}p",
                                "height": h,
                                "fps": int(float(rep.get("frameRate") or 0)),
                                "bitrate": int(rep.get("bandwidth") or 0) // 1000,
                                "url": url,
                                "vcodec": codecs[0] if codecs else "H.264",
                                "acodec": codecs[1] if len(codecs) > 1 else "AAC",
                            }
                        )
    except Exception as e:
        # [증거 남김] VOD API 실패 → formats 비어 상위에서 RuntimeError fail-fast.
        import chzzktube.core.raw_log as raw_log
        from chzzktube.core.log_event import LogEvent
        raw_log.raw(
            "chzzk",
            LogEvent(
                stage="ANAL", status="WARN", scope="CHZ",
                msg=f"chzzk vod api failed (video/{video_no}): {type(e).__name__}: {e}",
                is_error=True,
            ),
            to_tui=False,
        )

    video_formats.sort(
        key=lambda x: (x["height"], get_video_codec_rank(x["vcodec"]), x["bitrate"]),
        reverse=True,
    )
    return {
        "title": title,
        "date": date,
        "duration": duration,
        "video_no": video_no,
        "formats": video_formats,
        "channel_name": channel_name,
    }


def _fetch_m3u8_streams(m3u8_url, headers, timeout=15):
    """m3u8 HLS 매니페스트를 경량 조회 — 분석 단계에서 format 목록만 추출.

    yt-dlp의 'Downloading m3u8 information' 스텝은 매니페스트 전체를
    변형하며 (variants/iframe/subtitle 등) googlevideo 셔드 스로틀에서
    영구 HANG 위험이 있다. 여기서는 #EXT-X-STREAM-INF 라인만 빠르게
    스캔해 (resolution/bandwidth) 포맷 목록을 반환한다.
    """
    req = urllib.request.Request(m3u8_url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as res:
        content = res.read().decode("utf-8", errors="replace")

    fmt_by_res = {}
    cur_bw = 0
    cur_res = ""
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("#EXT-X-STREAM-INF"):
            attrs = {
                key: quoted or plain
                for key, quoted, plain in re.findall(
                    r'([\w-]+)=(?:"([^"]*)"|([^,\s]+))', line
                )
            }
            cur_bw = int(float(attrs.get("BANDWIDTH", 0) or 0)) // 1000
            cur_res = attrs.get("RESOLUTION", "")
        elif line and not line.startswith("#"):
            height = 0
            h_match = re.search(r"(\d+)x(\d+)", cur_res)
            if h_match:
                height = int(h_match.group(2))
            elif cur_res:
                h_match = re.search(r"(\d+)p", cur_res, re.IGNORECASE)
                if h_match:
                    height = int(h_match.group(1))
            if height and height not in fmt_by_res:
                fmt_by_res[height] = {
                    "id": line,
                    "res": cur_res,
                    "height": height,
                    "fps": 0,
                    "bitrate": cur_bw,
                    "url": urljoin(m3u8_url, line),
                    "vcodec": "H.264",
                    "acodec": "AAC",
                }
    return sorted(fmt_by_res.values(), key=lambda x: x["height"], reverse=True)


def _parse_live_playback_url(content):
    raw = content.get("livePlaybackJson") or ""
    try:
        playback = json.loads(raw) if isinstance(raw, str) else {}
    except Exception:
        return ""
    media = playback.get("media") if isinstance(playback, dict) else None
    if not isinstance(media, list):
        return ""
    hls = [m for m in media if isinstance(m, dict) and m.get("protocol") == "HLS" and m.get("path")]
    if not hls:
        return ""
    for m in hls:
        if m.get("mediaId") == "HLS":
            return m["path"]
    return hls[0]["path"]


def _parse_live_status(content):
    raw = content.get("livePlaybackJson") or ""
    live_state = ""
    try:
        playback = json.loads(raw) if isinstance(raw, str) else {}
        inner = (playback.get("live") or {}) if isinstance(playback, dict) else {}
        live_state = inner.get("status", "")
    except Exception:
        live_state = ""
    status = str(content.get("status") or "").upper()
    live_state = str(live_state or "").upper()
    if status == "OPEN" and live_state in ("", "STARTED"):
        return "PROGRESS"
    if status in ("CLOSE", "CLOSED", "ENDED") or live_state in ("STOPPED", "ENDED", "CLOSED"):
        return "CLOSE"
    return "UNKNOWN"


def _analyze_chzzk_live_v2(channel_id, headers):
    meta = (
        _get_json(
            f"https://api.chzzk.naver.com/service/v2/channels/{channel_id}/live-detail",
            headers,
        ).get("content", {})
        or {}
    )
    title = meta.get("liveTitle") or channel_id
    title = re.sub(r"\.(mp4|mkv|ts|webm|mov)$", "", title, flags=re.IGNORECASE)
    date = (meta.get("openDate") or "").split(" ")[0] or None
    channel = meta.get("channel") or {}
    channel_name = channel.get("channelName") or meta.get("channelName")
    live_status = _parse_live_status(meta)
    m3u8_url = _parse_live_playback_url(meta)
    formats = _fetch_m3u8_streams(m3u8_url, headers) if m3u8_url else []
    return {
        "title": title,
        "date": date,
        "duration": None,
        "live_id": str(meta.get("liveId") or channel_id),
        "live_status": live_status,
        "formats": formats,
        "channel_name": channel_name,
    }


def _analyze_chzzk_live_v1(live_id, headers):
    meta = (
        _get_json(
            f"https://api.chzzk.naver.com/service/v1/live/{live_id}",
            headers,
        ).get("content", {})
        or {}
    )
    title = meta.get("liveTitle") or live_id
    title = re.sub(r"\.(mp4|mkv|ts|webm|mov)$", "", title, flags=re.IGNORECASE)
    date = (meta.get("liveStartTime") or "").split(" ")[0] or None
    channel = meta.get("channel") or {}
    channel_name = channel.get("channelName") or meta.get("channelName")
    live_status = meta.get("liveStatus", "PROGRESS")
    stream_info = meta.get("liveStreamInfo", {})
    if isinstance(stream_info, dict):
        m3u8_url = (
            stream_info.get("serviceUrl")
            or stream_info.get("streamingUrl")
            or stream_info.get("sourceUrl")
            or ""
        )
    elif isinstance(stream_info, str):
        m3u8_url = stream_info
    else:
        m3u8_url = ""
    formats = _fetch_m3u8_streams(m3u8_url, headers) if m3u8_url else []
    return {
        "title": title,
        "date": date,
        "duration": None,
        "live_id": live_id,
        "live_status": live_status,
        "formats": formats,
        "channel_name": channel_name,
    }


def analyze_chzzk_live_api(target_url):
    """치지직 실시간 방송 — 메타 + HLS 포맷 목록 (m3u8 경량 스캔).

    live ID는 32자리 16진수 해시(a0e26a105c3b5ac212d5e0ca40c5c747)이므로
    기존 VOD API의 (\\d+) 정규식과 분리 필요.
    """
    m = re.search(r"chzzk\.naver\.com/live/([\w-]+)", target_url)
    if not m:
        return {"title": None, "date": None, "duration": None, "formats": [], "channel_name": None}
    live_id = m.group(1)
    headers = _chzzk_headers()

    title = live_id
    date = None
    duration = None
    channel_name = None
    video_formats = []
    live_status = "UNKNOWN"

    live_id_out = live_id

    try:
        if re.fullmatch(r"[0-9a-fA-F]{32}", live_id):
            info = _analyze_chzzk_live_v2(live_id, headers)
        elif live_id.isdigit():
            info = _analyze_chzzk_live_v1(live_id, headers)
        else:
            try:
                info = _analyze_chzzk_live_v2(live_id, headers)
            except Exception:
                info = _analyze_chzzk_live_v1(live_id, headers)
        title = info.get("title") or live_id
        date = info.get("date")
        duration = info.get("duration")
        channel_name = info.get("channel_name")
        live_status = info.get("live_status", "UNKNOWN")
        video_formats = info.get("formats") or []
        live_id_out = info.get("live_id") or live_id
    except Exception as e:
        # [증거 남김] live API 실패 → formats 비어 상위에서 fail-fast.
        import chzzktube.core.raw_log as raw_log
        from chzzktube.core.log_event import LogEvent
        raw_log.raw(
            "chzzk",
            LogEvent(
                stage="ANAL", status="WARN", scope="CHZ",
                msg=f"chzzk live api failed (live/{live_id}): {type(e).__name__}: {e}",
                is_error=True,
            ),
            to_tui=False,
        )

    if not video_formats:
        if live_status != "PROGRESS":
            import chzzktube.core.raw_log as raw_log
            from chzzktube.core.log_event import LogEvent
            raw_log.raw(
                "chzzk",
                LogEvent(
                    stage="ANAL", status="WARN", scope="CHZ",
                    msg=f"chzzk live offline ({live_status}) - live/{live_id_out}",
                    is_error=False,
                ),
                to_tui=False,
            )

    video_formats.sort(
        key=lambda x: (x["height"], get_video_codec_rank(x["vcodec"]), x["bitrate"]),
        reverse=True,
    )
    return {
        "title": title,
        "date": date,
        "duration": duration,
        "live_id": live_id_out,
        "live_status": live_status,
        "formats": video_formats,
        "channel_name": channel_name,
    }

```

## File: chzzktube/core/client_opts.py

```python
##### downloader_helpers/client_opts.py - yt-dlp 옵션 빌더
"""yt-dlp 옵션에 player_client/쿠키 설정을 주입하는 순수 헬퍼."""
import os


def _apply_ffmpeg_opts(opts):
    """ffmpeg 경로를 ydl_opts에 반영 (Windows/macOS/Linux 호환).

    [v3.8.0 격리] 시스템 PATH 탐색(shutil.which) 금지 — 앱 전용 캐시
    (writable_base()/ffmpeg)에서 수급된 바이너리만 단일 참조한다.
    """
    # 이미 ffmpeg_location이 설정되어 있으면 스킵
    if "ffmpeg_location" in opts:
        return opts
    try:
        from chzzktube.infra.components import ffmpeg_exe
        ffmpeg_path = ffmpeg_exe()
    except Exception:
        ffmpeg_path = None
    if ffmpeg_path:
        opts["ffmpeg_location"] = ffmpeg_path
    return opts


def _apply_post_opts(opts, cfg):
    """ffmpeg 후처리(postprocessors)를 cfg 가변 설정에 fit.

    [fit 규칙] 모든 후처리는 cfg 키가 유일한 스위치다. 하드코딩 금지.
    - embed_subtitles=True → writesubtitles + SRT 자동변환 병합
    - embed_thumbnail=True → 커버 썸네일 병합
    - embed_chapters(기본 True) → 챕터/메타데이터 병합
    - subtitle_langs: "all"이면 allsubtitles, 아니면 subtitleslangs 목록
    """
    cfg = cfg or {}
    pp = opts.setdefault("postprocessors", [])

    def _has(key):
        return any(isinstance(p, dict) and p.get("key") == key for p in pp)

    if cfg.get("embed_subtitles"):
        langs = str(cfg.get("subtitle_langs") or "all").strip() or "all"
        if langs.lower() == "all":
            opts["allsubtitles"] = True
        else:
            opts["subtitleslangs"] = [s.strip() for s in langs.split(",") if s.strip()]
        opts["writesubtitles"] = True
        if not _has("FFmpegSubtitlesConvertor"):
            pp.append({"key": "FFmpegSubtitlesConvertor", "format": "srt"})
        if not _has("FFmpegEmbedSubtitle"):
            pp.append({"key": "FFmpegEmbedSubtitle", "already_have_subtitle": False})

    if cfg.get("embed_thumbnail"):
        if not _has("EmbedThumbnail"):
            pp.append({"key": "EmbedThumbnail", "already_have_thumbnail": False})

    if cfg.get("embed_chapters", True):
        if not _has("FFmpegMetadata"):
            pp.append({"key": "FFmpegMetadata", "add_chapters": True, "add_metadata": True})

    return opts


def _concurrent_fragments(cfg):
    """병렬 조각 수 — fast_download on이면 cfg 값(기본 4), off면 1(순차)."""
    if not (cfg or {}).get("fast_download"):
        return 1
    try:
        n = int((cfg or {}).get("concurrent_fragments", 4) or 4)
    except (TypeError, ValueError):
        n = 4
    return max(1, min(n, 16))


def _apply_client_opts(opts, cfg, forced=None):
    """유튜브 player_client 수동 지정을 ydl_opts에 반영 (성인제한 대응).

    forced가 주어지면(분석 단계에서 실증·통과한 클라이언트) cfg 값보다
    우선한다. 다운로드가 분석과 같은 클라이언트를 쓰도록 해 PO 토큰/
    봇 게이트 경로 재진입(0% 스톨)을 막는다.

    [중요] yt-dlp 기본 _DEFAULT_CLIENTS는 ('visionos', 'web')인데,
    visionos는 연령제한 영상을 처리하지 못해 "No video formats found"로
    실패한다. 쿠키가 있어도 'auto'일 때는 yt-dlp 순정 클라이언트 체인
    (web_embedded, tv_downgraded 등)과 내장 EJS JS 솔버를 최우선 존중한다.
    """
    client = str(forced or cfg.get("yt_player_client", "auto") or "auto")
    if client == "auto":
        # [핵심 변경] 쿠키 유무와 무관하게 강제 client 지정 없이 yt-dlp 순정
        # 클라이언트 선택 로직과 EJS 솔버가 작동하도록 즉시 반환.
        # forced 인자가 있는 경우(분석/다운로드에서 검증된 클라이언트)만 적용.
        if forced is None:
            return opts
    opts.setdefault("extractor_args", {}).setdefault("youtube", {}) \
        .setdefault("player_client", []).append(client)
    return opts


def _apply_cookie_opts(opts, cfg):
    """브라우저 쿠키 설정을 ydl_opts에 반영 (4곳 중복 제거 공통 헬퍼)."""
    browser = cfg.get("browser_cookie", "none")
    if browser not in ["none", "auto", "cookie_file"]:
        opts["cookiesfrombrowser"] = (browser,)
    elif browser == "cookie_file" and os.path.exists(cfg.get("cookie_file_path", "")):
        opts["cookiefile"] = cfg["cookie_file_path"]
    return opts


def _apply_ejs_opts(opts):
    """YouTube JS 챌린지(n-sig) 솔버 실행 환경 구성.

    1) js_runtimes: node 명시 주입 — [근본 수정] yt-dlp의 기본 JS 런타임은
       'deno'뿐이고 PATH 탐색으로만 node를 찾는다. 이 앱은 node를
       writable_base()/node(포터블)에 자체 수급하므로 PATH에 없고,
       결과적으로 n-challenge solving이 실패해 web 계열 포맷이 증발했다
       ("No video formats found" → 회전 실패로 이어짐). node_exe()로
       탐색한 실행 파일을 js_runtimes={'node': {'path': ...}}로 명시 주입해
       해결한다. node가 없으면 기본값(deno) 유지.
    2) remote_components: ejs:github 허용 — GitHub에서 챌린지 솔버 스크립트
       자동 수급(yt-dlp-ejs PyPI 패키지 미설치 환경에서 필수).
    """
    try:
        from chzzktube.infra.node_provider import node_exe
        node = node_exe()
        if node:
            opts.setdefault("js_runtimes", {})
            if "node" not in opts["js_runtimes"]:
                opts["js_runtimes"]["node"] = {"path": node}
    except Exception:  # noqa: BLE001 — 탐색 실패 시 기본(deno) 폴백
        pass
    if "remote_components" not in opts:
        opts["remote_components"] = []
    if "ejs:github" not in opts["remote_components"]:
        opts["remote_components"].append("ejs:github")
    return opts


def _apply_light_analysis_opts(opts):
    """[경량 분석] YouTube HLS/DASH 매니페스트 열거 생략 — 분석 스톨 차단.

    yt-dlp youtube 추출기는 web 붕괴 시 tv/visionos 등 HLS 계열 클라이언트로
    폴백하며, 이때 'Downloading m3u8 information' 단계에서 매니페스트 전체
    변형을 내려받는다. 이 요청은 googlevideo 셔드 지연/스로틀 환경에서
    멈춰 분석이 'analyzing...'에 영원히 갇히는 원인이 된다.

    분석은 채널명/제목/포맷 개수 등 기본 정보만 필요하므로 매니페스트를
    열거하지 않고 플레이어 응답의 직접 URL 포맷만 취한다. 실제 데이터 수급
    (매니페스트 재열거 + JS 챌린지/PO 토큰 우회)은 DownloadWorker의 무거운
    경로가 담당한다 — 가벼운 동작(살펴보기)과 무거운 동작(내려받기) 분리.
    """
    ea = opts.setdefault("extractor_args", {}).setdefault("youtube", {})
    skip = ea.setdefault("skip", [])
    for manifest in ("hls", "dash"):
        if manifest not in skip:
            skip.append(manifest)
    return opts


def _apply_pot_opts(opts, video_id, client="web_embedded"):
    """bgutil 독립 서버에서 PO 토큰을 직접 패칭해 extractor_args로 주입.

    [변경] 기존 Python 플러그인(yt_dlp_plugins/getpot_bgutil) 자동 주입을
    제거하고, 앱이 bgutil HTTP 서버에 POST /get_pot를 직접 호출해
    `youtube:po_token=CLIENT.gvs+TOKEN` 형태로 명시 전달한다.
    - 플러그인 제거 → 토큰 생성이 블랙박스가 아니라 앱이 완전히 제어
    - 서버 미기동/오류 시 None → PO 없이 진행 (플러그인 실패와 달리 조용)
    - player_client가 이미 설정돼 있으면 병합 (덮어쓰지 않음)
    - [결함 2 수리] visitorData 함께 주입 → 세션 바인딩 유지
    """
    if not video_id:
        return opts
    from chzzktube.infra.po_client import fetch_po_token
    token, visitor_data = fetch_po_token(video_id)
    if not token:
        return opts
    ea = opts.setdefault("extractor_args", {}).setdefault("youtube", {})
    # po_token은 list[str] — 기존 값 유지하며 gvs 컨텍스트만 추가
    ea.setdefault("po_token", []).append(f"{client}.gvs+{token}")
    # [결함 2 수리] visitor_data 주입 — 세션 바인딩으로 403 방지
    if visitor_data:
        ea.setdefault("visitor_data", []).append(visitor_data)
    return opts


def _dedupe_by_label(formats):
    """표시 라벨이 동일한 포맷은 대표 1개만 남긴다 (라이브 HLS 중복 제거)."""
    seen, unique = set(), []
    for fmt in formats:
        if fmt["label"] not in seen:
            seen.add(fmt["label"])
            unique.append(fmt)
    return unique

```

## File: chzzktube/core/config.py

```python
import json
import os
import sys


def _repo_root():
    """저장소 루트 — chzzktube/core/config.py 기준 parents[2] 고정."""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def resolve_dirs():
    """실행 모드에 따라 소스/설정 Base 경로를 결정. (frozen 여부 기반)

    Dev: 저장소 루트 고정 — config.py가 chzzktube/core/로 이동해도
    dl_config.json·logs/ 생성 위치는 이전(루트)과 동일하다.
    frozen: sys._MEIPASS + exe 디렉터리 (기존 계약 유지).
    """
    if getattr(sys, "frozen", False):
        base_dir = sys._MEIPASS
        config_dir = os.path.dirname(sys.executable)
    else:
        base_dir = _repo_root()
        config_dir = base_dir
    assert os.path.isdir(base_dir), base_dir
    return base_dir, config_dir


def is_frozen() -> bool:
    """단일 진실: 실행 환경의 frozen 여부.

    호출부는 이 함수를 직접 쓰지 말 것 — 경로 리졸버가 캡슐화한다.
    """
    return getattr(sys, "frozen", False)


def writable_base():
    """쓰기 보장 런타임 캐시 루트 — node/PO 서버/플러그인/ffmpeg 등
    실행 시 수급하는 구성요소의 단일 경로 출처 (pot_provider·components 공용).
    """
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        return os.path.join(local_appdata, "ChzzkTube")
    return os.path.join(os.path.expanduser("~"), ".chzzktube")

_APP_NAME = "ChzzkTube"
_APP_VERSION = "v3.8.2"

BASE_DIR, CONFIG_DIR = resolve_dirs()
CONFIG_FILE = os.path.join(CONFIG_DIR, "dl_config.json")
ICON_PATH = os.path.join(BASE_DIR, "assets", "icon.ico")
FONT_PATH = os.path.join(BASE_DIR, "assets", "CascadiaMono-VariableFont_wght.ttf")
LOG_DIR = os.path.join(CONFIG_DIR, "logs")

def _pylib_root():
    """프로젝트 로컬 pip 오버레이 루트 (<repo>/.pylib).

    [DEPRECATED] 하위 호환용 별칭 — 새 코드는 pylib_overlay_path() 사용.
    호출부는 환경을 분기하지 않는다. pylib_overlay_path()가 SSOT다.
    """
    env = os.environ.get("CHZZKTUBE_PYLIB_DIR")
    if env:
        return os.path.abspath(env)
    # Dev 모드 기본값 (frozen이면 pylib_overlay_path()가 writable_base() 사용)
    return os.path.join(_repo_root(), ".pylib")


def pylib_overlay_path() -> str:
    """Python 오버레이 패키지(.pylib)의 단일 진실 공급원 (SSOT).

    호출부는 환경을 분기하지 않는다.
    우선순위 체인:
    1. 환경변수 강제 오버라이드 — CHZZKTUBE_PYLIB_DIR (CI/테스트/진단)
    2. Frozen 환경: writable_base()/.pylib (%LOCALAPPDATA%/ChzzkTube/.pylib 또는 ~/.chzzktube/.pylib)
    3. Dev 환경: <repo>/.pylib
    """
    env_override = os.environ.get("CHZZKTUBE_PYLIB_DIR")
    if env_override:
        return os.path.abspath(env_override)

    if is_frozen():
        base = writable_base()
    else:
        base = _repo_root()

    return os.path.join(base, ".pylib")


def default_config():
    """기본 설정 딕셔너리 생성. (download_path 는 현재 설정 디렉토리 기준)"""
    return {
        "download_path": CONFIG_DIR,
        "container": "mp4",
        "embed_subtitles": False,
        "audio_only": False,
        "fast_download": True,
        "remove_duplicates": True,
        "auto_open_folder": True,
        "completion_action": "none",
        "play_sound": True,
        "max_video_res": "none",
        "pick_format": False,
        "filename_prefix": "none",
        "filename_suffix": "id",
        "browser_cookie": "auto",
        "cookie_file_path": "",
        "yt_player_client": "auto",
        "update_channel": "stable",
        "auto_update_check": True,
        # [외부툴 가변 설정 — client_opts._apply_* 헬퍼가 yt-dlp/streamlink/ffmpeg
        #  옵션으로 배선한다. 새 키 추가 시 (1) 아래 기본값 (2) _apply_* 헬퍼
        #  (3) dialogs.py 체크박스/콤보 3점 세트를 함께 추가할 것.]
        "streamlink_quality": "best",      # streamlink 화질 선택 (best/1080p,720p/…)
        "embed_thumbnail": False,          # 커버 썸네일 병합 (ffmpeg -c copy + 썸네일 주입)
        "embed_chapters": True,            # 챕터/메타데이터 병합 (mp4/mkv)
        "subtitle_langs": "all",           # 자막 언어 (all/ko,en/ko 등, embed_subtitles와 연동)
        "concurrent_fragments": 4,         # 병렬 조각 수 (fast_download와 연동)
    }

def load_config():
    """기본 설정에 기존 config 파일을 병합(다운로드 경로 유효 시)."""
    cfg = default_config()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if loaded.get("download_path") and os.path.exists(
                    loaded["download_path"]
                ):
                    cfg.update(loaded)
        except Exception:
            pass
    return cfg

def save_config(cfg):
    """현재 설정을 config 파일로 저장."""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=4)

```

## File: chzzktube/core/cookies.py

```python
﻿### cookies.py - 브라우저 쿠키 추출 (yt-dlp 네이티브 위임)

"""
yt-dlp의 extract_cookies_from_browser를 위임하여 브라우저별 경로 탐색,
암호화 복호화(DPAPI/Keychain), SQLite 락 처리, 프로필 다중 선택을 모두 맡긴다.

지원 브라우저: chrome, chromium, edge, brave, vivaldi, firefox, opera, safari
"""

from __future__ import annotations

import platform
from typing import Dict, Optional

try:
    from yt_dlp.cookies import extract_cookies_from_browser
except ImportError:
    extract_cookies_from_browser = None  # yt-dlp 버전 미지원 시 None


# yt-dlp가 인식하는 브라우저 이름 매핑 (한글/별칭 → 표준 이름)
_BROWSER_ALIASES = {
    "chrome": "chrome",
    "크롬": "chrome",
    "google chrome": "chrome",
    "chromium": "chromium",
    "edge": "edge",
    "msedge": "edge",
    "microsoft edge": "edge",
    "brave": "brave",
    "vivaldi": "vivaldi",
    "opera": "opera",
    "opera gx": "opera",
    "firefox": "firefox",
    "ff": "firefox",
    "mozilla": "firefox",
    "safari": "safari",
}


def _normalize_browser_name(name: str) -> Optional[str]:
    """사용자 입력/설정값을 yt-dlp 표준 브라우저명으로 정규화."""
    if not name:
        return None
    key = name.strip().lower()
    return _BROWSER_ALIASES.get(key)


def get_browser_cookies(browser: Optional[str] = None) -> Dict[str, Dict[str, str]]:
    """
    yt-dlp 네이티브 쿠키 추출기로 브라우저 쿠키 획득.
    
    Args:
        browser: 브라우저 이름 (None이면 자동 탐색 시도)
        
    Returns:
        {domain: {name: value}} 형태의 쿠키 딕셔너리.
        실패/미지원 시 빈 딕셔너리 반환.
    """
    if extract_cookies_from_browser is None:
        return {}
    
    cookie_data: Dict[str, Dict[str, str]] = {}
    
    # 브라우저 지정 시 단일 시도
    if browser:
        norm = _normalize_browser_name(browser)
        if norm:
            try:
                cookies = extract_cookies_from_browser(norm)
                for c in cookies:
                    domain = c.get("domain", "")
                    if domain:
                        cookie_data.setdefault(domain, {})[c["name"]] = c["value"]
            except Exception:
                pass  # yt-dlp 내부에서 로깅/처리
        return cookie_data
    
    # 자동 탐색: 플랫폼별 우선순위대로 시도
    system = platform.system().lower()
    candidates = []
    if system == "windows":
        candidates = ["chrome", "edge", "brave", "vivaldi", "opera", "firefox"]
    elif system == "darwin":
        candidates = ["chrome", "edge", "brave", "vivaldi", "opera", "firefox", "safari"]
    else:  # linux
        candidates = ["chrome", "chromium", "edge", "brave", "vivaldi", "opera", "firefox"]
    
    for b in candidates:
        try:
            cookies = extract_cookies_from_browser(b)
            for c in cookies:
                domain = c.get("domain", "")
                if domain:
                    cookie_data.setdefault(domain, {})[c["name"]] = c["value"]
            if cookie_data:
                break  # 첫 성공 시 종료 (충돌 방지)
        except Exception:
            continue
    
    return cookie_data


def get_cookie_string_for_domain(domain: str, browser: Optional[str] = None) -> str:
    """
    특정 도메인의 쿠키를 'name=value; name=value' 문자열로 반환.
    yt-dlp의 cookiefile 포맷 또는 requests headers 용도.
    """
    cookies = get_browser_cookies(browser)
    domain_cookies = cookies.get(domain, {})
    return "; ".join(f"{k}={v}" for k, v in domain_cookies.items())

```

## File: chzzktube/core/dl_platform.py

```python
##### dl_platform.py - 다운로더 플랫폼/콘텐츠 타입 감별
"""URL 문자열에서 플랫폼(youtube/chzzk/streamlink 등)과 콘텐츠 타입을 판정한다.

표준 라이브러리 `platform`과의 이름 충돌을 피하기 위해 `dl_platform`으로
명명 — downloader.target_downloader / AnalyzeWorker 공용.

플랫폼 축약기호는 media.platform_short()를 사용한다.
"""
import re

# 도메인 → 플랫폼 추출기명 매핑 (동적 확장 가능)
# 우선순위: 위에서부터 매칭, 없으면 yt-dlp extractor에게 위임
_DOMAIN_EXTRACTORS = [
    # (도메인 패턴, extractor 이름)
    ("chzzk.naver.com", "chzzk"),
    ("twitch.tv", "twitch"),
    ("sooplive.co.kr", "sooplive"),
    ("soop.co.kr", "sooplive"),
    ("afreecatv.com", "afreecatv"),
    ("youtube.com", "youtube"),
    ("youtu.be", "youtube"),
    ("music.youtube.com", "youtube"),
    ("youtube-nocookie.com", "youtube"),
    ("instagram.com", "instagram"),
    ("tiktok.com", "tiktok"),
    ("facebook.com", "facebook"),
    ("twitter.com", "twitter"),
    ("x.com", "twitter"),
    ("bilibili.com", "bilibili"),
    ("dailymotion.com", "dailymotion"),
    ("vimeo.com", "vimeo"),
    ("soundcloud.com", "soundcloud"),
    ("naver.com", "naver"),
    ("kakao.com", "kakao"),
    ("fmkorea.com", "fmkorea"),
    ("theqoo.net", "theqoo"),
    ("clien.net", "clien"),
    ("dcinside.com", "dcinside"),
]


def _dl_platform(url):
    """URL 문자열에서 플랫폼 추출기명 추출.

    도메인 매핑 테이블에서 찾고, 없으면 'youtube'로 폴백
    (yt-dlp가 범용 처리하므로 대부분 동작).
    """
    if not url:
        return "youtube"
    u = str(url).lower()
    for pattern, extractor in _DOMAIN_EXTRACTORS:
        if pattern in u:
            return extractor
    return "youtube"  # 폴백: yt-dlp가 자동 감지


def _short_platform(p):
    """플랫폼 문자열을 TUI 컬럼 폭에 맞게 축약 (media.platform_short 위임)."""
    if not p or p == "-":
        return "-"
    try:
        from chzzktube.core.media import platform_short
        return platform_short(p)
    except ImportError:
        return str(p)[:8]


def detect_content_type(url, info=None):
    """콘텐츠 종류 판정.

    chzzk      → clip / vod / live / chzzk
    youtube url → playlist / live / video
    streamlink  → stream
    info(dict)에 is_live 가 있으면 live 우선.
    """
    if not url:
        return "video"
    u = str(url).lower()

    if "chzzk.naver.com" in u:
        if re.search(r"clips?/", u):
            return "clip"
        if re.search(r"video/\d+", u):
            return "vod"
        if "/live/" in u:
            return "live"
        return "chzzk"

    if (
        info
        and isinstance(info, dict)
        and info.get("is_live")
        and not info.get("is_playlist")
    ):
        return "live"

    if "youtube.com/playlist" in u or "playlist?list=" in u:
        return "playlist"
    if (
        "youtu.be" in u
        or "youtube.com/watch" in u
        or "youtube.com/shorts" in u
        or "youtube.com/live" in u
    ):
        if info and isinstance(info, dict) and info.get("is_live"):
            return "live"
        return "video"

    if "twitch.tv" in u or "sooplive.co.kr" in u or "afreecatv.com" in u:
        return "stream"

    return "video"
```

## File: chzzktube/core/log_emitter.py

```python
"""Pure log event builders and text formatting helpers (Qt-free).

pipeline/workers가 백그라운드·테스트 환경에서도 GUI 컨텍스트 없이
가져갈 수 있는 순수 함수만 둔다. Qt 위젯 렌더링은 ui/log_console 담당.
"""
import time
import unicodedata

from chzzktube.core.log_event import STAGES, STATUSES
from chzzktube.core.dl_platform import _short_platform


def display_width(text):
    """콘솔 표시 폭 계산 (한글 등 전각 문자는 2칸)."""
    return sum(
        2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
        for ch in str(text)
    )

def _wrap_by_width(text, max_width):
    """표시 폭 기준 단어 단위 줄바꿈. 단어 자체가 예산보다 길면 강제 분할."""
    lines, cur, cur_w = [], "", 0
    for word in str(text).split(" "):
        while display_width(word) > max_width:
            if cur:
                lines.append(cur)
            cur, cur_w = "", 0
            part, take = "", 0
            for ch in word:
                cw = display_width(ch)
                if take + cw > max_width:
                    break
                part += ch
                take += cw
            lines.append(part)
            word = word[len(part):]
        w = display_width(word)
        cand_w = cur_w + (1 if cur else 0) + w
        if cur and cand_w > max_width:
            lines.append(cur)
            cur, cur_w = word, w
        else:
            cur = word if not cur else cur + " " + word
            cur_w = cand_w
    if cur:
        lines.append(cur)
    return lines

### 트리 라벨 공통 폭 — 콜론(:) 위치를 모든 가지에서 세로로 일치시킨다.
TREE_LABEL_WIDTH = 9  # kv 라벨('저장 완료'·'실패 사유' 등 전각 4자+공백) 기준
TREE_TOTAL_WIDTH = 56  # 간결 로그 창의 실질 가로 예산 (폴백 — ui가 동적 갱신)


### 줄기 없는(' └─') 연속 줄의 선행 공백 폭 — cont_prefix는 prefix 폭(TREE_LABEL_WIDTH+6)만큼의 공백 나열
STEMLESS_CONT_WIDTH = TREE_LABEL_WIDTH + 6


### [v3.8.0 Hyper-Minimalist TUI] 분석 마감 정갈 명세
###   [ANAL RUN  analyzing complete!]
###   [ANAL OK   [제목] · [채널명]]
###   [ANAL OK   [public]]
###   [ANAL OK   [1080p60] [av01...] · [opus] ...]
_ANALYSIS_DONE_MSG = "analyzing complete!"


def analysis_done_msg():
    """ANAL RUN 마감 고정 문구 (main_window.stop_analysis_anim 유일 소비)."""
    return _ANALYSIS_DONE_MSG


def format_analysis_counts(v_count, a_count):
    """분석 완료 로그의 포맷 개수 요약 문자열."""
    if v_count and a_count:
        return f" (v:{v_count}, a:{a_count})"
    if v_count:
        return f" (v:{v_count})"
    if a_count:
        return f" (a:{a_count})"
    return ""


def _flow_lines(line, no_wrap=False):
    """라인 분할 규칙 — Single-Line TUI는 wrap하지 않는다.

    *  no_wrap=True(LogEvent 경유 컬럼/프리포맷 라인): 그대로 한 줄 —
       예산 초과분은 ConciseLogConsole._render_clamp가 '…'로 절단한다.
       (트리 조판 줄은 자식 줄 예산 산정용으로 내부 wrap 유지)
    *  no_wrap=False(큐 호환 bare 문자열·yt-dlp/pip 출력 등 비트리 일반
       라인): 예산 폭으로 wrap한다.
    발행자(raw → 구독자) 플래그가 유일한 분기 기준이며, 문자열 콘텐츠를
    다시 뜯어 판단하지 않는다(정규식 라우팅 제로).
    """
    if no_wrap:
        return [line]
    if line[:2] in (" ├", " └", " │"):
        return [line]
    if line.startswith(" " * STEMLESS_CONT_WIDTH):
        return [line]
    return _wrap_by_width(line, max(20, TREE_TOTAL_WIDTH))

def _pad_label(label, width):
    """라벨을 width칸까지 뒤에 공백을 붙여 확장한다."""
    return str(label) + " " * max(0, width - display_width(label))

def format_tree_item(label, value, branch="├─", indent=" "):
    """트리 가지 한 항목을 '라벨 정렬 + 콜론 정렬 + 값 줄바꿈 시 세로줄 연결'로 조판."""
    padded = _pad_label(label, TREE_LABEL_WIDTH)
    prefix = f"{indent}{branch} {padded}: "
    stem = "│" if branch.startswith("├") else " "
    cont_prefix = indent + stem + " " * (
        display_width(prefix) - display_width(indent) - 1
    )
    chunks = _wrap_by_width(value, TREE_TOTAL_WIDTH - display_width(prefix))
    out = prefix + (chunks[0] if chunks else "")
    for chunk in chunks[1:]:
        out += "\n" + cont_prefix + chunk
    return out

def format_kv_line(symbol, label, value):
    """'[!] 건너뜀   : 값' — 트리 가지와 같은 콜론 열에 정렬된 단일 kv 라인."""
    padded = _pad_label(label, TREE_LABEL_WIDTH)
    prefix = f"{symbol} {padded}: "
    chunks = _wrap_by_width(value, max(10, TREE_TOTAL_WIDTH - display_width(prefix)))
    out = prefix + (chunks[0] if chunks else "")
    cont = " " * display_width(prefix)
    for chunk in chunks[1:]:
        out += "\n" + cont + chunk
    return out

def format_target_url(url, max_len=50):
    """URL을 트리 가지 형태로 출력. 길면 '│' 세로줄로 이어지는 정렬된 줄바꿈."""
    return format_tree_item("대상", url, branch="└─")


def format_pick_menu(v_list, a_list, max_rows=40):
    """[포맷 직접 고르기] 비디오/오디오 목록을 번호 매긴 선택 메뉴로 변환.

    각 항목 라벨은 v/a 분석 워커가 만든 파이프 컬럼 식이므로
    앞에 1-based 인덱스만 붙여 출력한다. UX 규칙 — 빈 입력 = 최고 품질,
    'N' = 비디오 N, 'N.M' = 비디오 N + 오디오 M.
    """
    lines = []
    if v_list:
        lines.append("video formats")
        for idx, f in enumerate(v_list[:max_rows], 1):
            label = f.get("label") or f.get("id") or "?"
            lines.append(f"  {idx:>2}  {label}")
        if len(v_list) > max_rows:
            lines.append(f"  ... {len(v_list) - max_rows} more")
    if a_list:
        lines.append("audio formats")
        for idx, f in enumerate(a_list[:max_rows], 1):
            label = f.get("label") or f.get("id") or "?"
            lines.append(f"  {idx:>2}  {label}")
        if len(a_list) > max_rows:
            lines.append(f"  ... {len(a_list) - max_rows} more")
    return lines

### ──────────────────────────────────────────────────────────────
### 컬럼 로그 라인 — TUI 스타일 고정 칼럼 포맷 (v3.4.0 4칸 미니멀)
### ──────────────────────────────────────────────────────────────
# 포맷: [HH:MM:SS] STAGE │ STATUS │ SCOPE │ MSG
#   STAGE   : SYS / DEPS / ANAL / DL / LIVE / MERG / BATCH / POT (5폭)
#   STATUS  : READY / RUN / OK / DONE / SKIP / WARN / FAIL / ABORT / END (5폭)
#   SCOPE   : 발생지·대상 (엔진 YTDL/STRE/FFMP/NODE/POT, 플랫폼 YT/CHZ/TW/TIKT…,
#             시스템 MAIN — 5폭, media.platform_short 실측값)
#   MSG     : [tag] 전두 + 진행률 고정형(PCT 3폭우측 · SPEED 8폭우측 + GAUGE 10블록)

def _log_ts():
    """현재 시각 — [HH:MM:SS] 형식."""
    return time.strftime("[%H:%M:%S]")

def is_tui_line(msg):
    """[호환 shim] 구버전 콘텐츠 판정 — 렌더 레이어에서는 더 이상 사용하지 않는다.

    줄바꿈 결정은 발행자(raw → 구독자) 플래그(_flow_lines no_wrap)가 유일한
    기준이다. 외부 호출부 호환용으로만 남겨두며, 구조적(non-regex) 판정은 유지한다.
    """
    s = str(msg).strip()
    # [HH:MM:SS] : 위치/숫자 구조 검증 (regex 없음)
    if not (len(s) >= 12 and s[0] == "[" and s[3] == ":"
            and s[6] == ":" and s[9] == "]" and s[10] == " "
            and s[1:3].isdigit() and s[4:6].isdigit() and s[7:9].isdigit()):
        return False
    # 컬럼 구분자 │ : 타임스탬프 뒤에 1글자 이상, 뒤에 1글자 이상
    idx = s.find("│", 11)
    return idx > 11 and idx < len(s) - 1

def _log_pct(pct):
    """진행률 — None이면 빈 문자열, 아니면 3폭 우측 정렬 (' 65%', '100%').

    지터링 방지: 게이지 시작 인덱스 고정을 위해 항상 동일한 폭을 차지한다.
    """
    if pct is None:
        return ""
    try:
        return f"{min(max(float(pct), 0.0), 100.0):3.0f}%"
    except (TypeError, ValueError):
        return ""


def _log_speed(speed):
    """속도 — '-'·빈 값이면 빈 문자열, 아니면 8폭 우측 정렬 (' 12.4M/s').

    지터링 방지: '9.1M/s'와 '12.4M/s'가 같은 폭을 차지해 게이지가 흔들리지 않는다.
    """
    s = str(speed or "").strip()
    if not s or s == "-":
        return ""
    return s[-8:].rjust(8)


def _log_bar(bar_frac, width=10):
    """텍스트 진행 바 — None이면 빈 문자열, 아니면 고정 10블록 '[████░░░░░░]'."""
    if bar_frac is None:
        return ""
    try:
        frac = min(max(float(bar_frac), 0.0), 1.0)
    except (TypeError, ValueError):
        return ""
    filled = int(round(frac * width))
    return f"[{'█' * filled}{'░' * (width - filled)}]"

def format_log_line(stage, status, scope="", msg="", spec="", speed="", pct=None,
                    bar_frac=None):
    """TUI 스타일 컬럼 로그 라인 — v3.4.0 4칸 미니멀 고정 정렬.

    표준 포맷:
        [HH:MM:SS] STAGE │ STATUS │ SCOPE │ MSG

    특징:
    - 고정 4칸: STAGE(5) · STATUS(5) · SCOPE(5) · MSG(가변). SPEC 컬럼 폐지.
    - spec(deprecated): 비어 있지 않으면 MSG 전두부 태그로 흡수 — "[1080p30] msg".
      '-'·빈 값은 버린다. 새 발행점에서 spec= 전달 금지.
    - 진행률 고정형: "[tag]  65% ·  12.4M/s [██████░░░░] · msg" —
      PCT 3폭 우측 · SPEED 8폭 우측 · GAUGE 10블록 고정으로 지터링 방지.
      extra가 비어 있으면 구분자 '·'도 찍지 않는다.
    - Zero Redundancy: msg 비어 있으면 꼬리 구분자(│) 미출력.

    인자:
        stage    : SYS / DEPS / ANAL / DL / LIVE / MERG / BATCH / POT (8종)
        status   : READY / RUN / OK / DONE / SKIP / WARN / FAIL / ABORT / END (9종)
        scope    : 발생지·대상 (엔진/플랫폼/MAIN — 5폭, media.platform_short 실측값)
        msg      : 영문 소문자 CLI 태그 (제목 등 데이터 제외하고 영문화)
        spec     : deprecated — [tag] 흡수용으로만 사용, 신규 전달 금지
        speed    : 네트워크 속도 (예: 12.4M/s) — MSG 고정형으로 통합
        pct      : 진행률 (0~100, None 가능) — MSG 고정형으로 통합
        bar_frac : 진행 바 (0.0~1.0, None 가능) — MSG 고정형으로 통합
    """
    stage_s = str(stage).upper()[:5].ljust(5)
    status_s = str(status).upper()[:5].ljust(5)
    scope_raw = str(scope or "").strip()
    if scope_raw in ("", "-", "NONE"):
        scope_s = "     "
    else:
        scope_upper = scope_raw.upper()
        # v3.4.0 표준 약자(YTDL/FFMP/NODE/POT/YT/CHZ/TW/TIKT 등)는 재축약 금지.
        # 플랫폼 이름(youtube/chzzk 등)만 media.platform_short로 축약한다.
        scope_s = (scope_upper if scope_upper in STAGES or scope_upper in STATUSES or scope_upper in {
            "YTDL", "STRE", "FFMP", "NODE", "POT", "MAIN", "RAW", "QUEUE", "DISK"
        } else _short_platform(scope_raw))[:5].ljust(5)

    # [SPEC 흡수] deprecated spec → MSG 전두부 [tag]. '-'·빈 값은 버린다.
    tag = ""
    spec_clean = str(spec or "").strip()
    if spec_clean and spec_clean != "-":
        tag = f"[{spec_clean[:24]}]"

    # [진행률 고정형] PCT(3폭) · SPEED(8폭) + GAUGE(10블록) — 지터링 방지.
    gauge_parts = []
    pct_s = _log_pct(pct)
    speed_s = _log_speed(speed)
    bar_s = _log_bar(bar_frac)
    if pct_s:
        gauge_parts.append(pct_s)
    if speed_s:
        gauge_parts.append(speed_s)
    gauge = " · ".join(gauge_parts)
    if bar_s:
        gauge = f"{gauge} {bar_s}" if gauge else bar_s

    msg_clean = str(msg or "").strip()
    head_parts = [p for p in (tag, gauge, msg_clean) if p]
    head = _log_ts() + " " + stage_s
    fixed = head + " │ " + " │ ".join((status_s, scope_s))
    if not head_parts:
        return fixed
    return fixed + " │ " + " · ".join(head_parts)


def format_log_line_for_event(event):
    """구조화된 LogEvent → TUI 컬럼 문자열 (뷰 전용 컬럼화 — 정규식 판정 제로).

    렌더링 책임은 View(메인로그 모듈)에 있고, LogEvent는 모델이다.
    rendered=True면 msg가 이미 표시 완성형이므로 재포맷하지 않는다.
    scope는 event.scope를 그대로 사용한다 (v3.4.0).
    """
    from chzzktube.core.log_event import LogEvent  # lazy import (순환 참조 방지)
    if not isinstance(event, LogEvent):
        return str(event)
    if event.rendered:
        return event.msg
    scope = event.scope
    return format_log_line(
        stage=event.stage,
        status=event.status,
        scope=scope,
        msg=event.msg,
        spec=event.spec,
        speed=event.speed,
        pct=event.pct,
        bar_frac=event.bar_frac,
    )


def emit_event(stage, status, scope="-", msg="", is_status=False, is_error=False):
    """단순 이벤트 1건."""
    from chzzktube.core.log_event import LogEvent  # lazy import
    return LogEvent(
        stage=stage, status=status, scope=scope, platform=scope, msg=msg,
        is_status=is_status, is_error=is_error,
    )


def emit_dl(status, scope="", msg="", speed="", pct=None, bar_frac=None,
            stage="DL", is_status=False, is_error=False):
    """DL 진행률/완료 이벤트."""
    from chzzktube.core.log_event import LogEvent  # lazy import
    return LogEvent(
        stage=stage, status=status, scope=scope, platform=scope, msg=msg,
        speed=speed, pct=pct, bar_frac=bar_frac,
        is_status=is_status, is_error=is_error,
    )


def emit_err(msg):
    """에러 1건 — FAIL 상태, 스코프 빈칸."""
    from chzzktube.core.log_event import LogEvent  # lazy import (순환 참조 방지)
    return LogEvent(stage="DL", status="FAIL", msg=msg, is_error=True)


from chzzktube.core.log_event import LogEvent  # lazy import (순환 참조 방지)


def emit_progress(stage, status, scope="-", msg="", speed="", pct=None,
                  bar_frac=None, is_status=False, is_error=False):
    """진행률 표시 이벤트 — ANAL/DL/LIVE 단계."""
    return LogEvent(
        stage=stage, status=status, scope=scope, platform=scope, msg=msg,
        speed=speed, pct=pct, bar_frac=bar_frac,
        is_status=is_status, is_error=is_error,
    )


def emit_component(stage, status, scope, msg="", is_status=False, is_error=False):
    """컴포넌트/워커 결과 — DEPS / POT / READY 등."""
    from chzzktube.core.log_event import LogEvent  # lazy import (순환 참조 방지)
    return LogEvent(
        stage=stage, status=status, scope=scope, platform=scope, msg=msg,
        is_status=is_status, is_error=is_error,
    )


### [v3.8.0] 오류 로그 표준 헬퍼 — 규격 포맷 준수
# 포맷: [HH:MM:SS] STAGE │ STATUS │ SCOPE │ <간결 원인> → <진행/액션>
# MSG 최대 55자 (TUI 폭 예산), 초과 시 '…' 절단

# 허용된 원인 키워드 (TUI용 표준화)
_ERROR_CAUSES = {
    "binary incompatible": "binary incompatible",
    "all mirrors exhausted": "all mirrors exhausted",
    "checksum mismatch": "checksum mismatch",
    "permission denied": "permission denied",
    "network error": "network error",
    "not found": "not found",
    "setup failed": "setup failed",
    "build failed": "build failed",
    "port conflict": "port conflict",
    "unknown": "unknown error",
}

# 허용된 액션 키워드 (TUI용 표준화)
_ERROR_ACTIONS = {
    "retry mirror (1/3)": "retry mirror (1/3)",
    "retry mirror (2/3)": "retry mirror (2/3)",
    "retry mirror (3/3)": "retry mirror (3/3)",
    "check network (F12)": "check network (F12)",
    "check folder permissions": "check folder permissions",
    "check logs (F12)": "check logs (F12)",
    "try again": "try again",
    "none": "",
}

# 메시지 최대 길이 (TUI 컬럼 폭 보호)
_MAX_ERR_MSG_LEN = 55

def _normalize_cause(cause: str) -> str:
    """원인 문자열을 표준 키워드로 정규화."""
    cause_lower = cause.lower()
    for std_cause in _ERROR_CAUSES:
        if std_cause in cause_lower:
            return _ERROR_CAUSES[std_cause]
    return "unknown error"

def _normalize_action(action: str) -> str:
    """액션 문자열을 표준 키워드로 정규화."""
    action_lower = action.lower()
    for std_action, std_value in _ERROR_ACTIONS.items():
        if std_action.lower() in action_lower:
            return std_value
    # 알려진 액션이 없으면 빈 문자열 반환 (무시)
    return ""

def _truncate_msg(msg: str, max_len: int = _MAX_ERR_MSG_LEN) -> str:
    """메시지 길이 제한 (초과 시 '…' 절단)."""
    if len(msg) <= max_len:
        return msg
    return msg[:max_len - 1] + "…"

def emit_error_standard(stage: str, scope: str, cause: str, action: str = "",
                        status: str = "FAIL", is_error: bool = True) -> LogEvent:
    """
    [v3.8.0] 오류 로그 표준 헬퍼 — 규격 포맷 준수.
    
    TUI 포맷: [HH:MM:SS] STAGE │ STATUS │ SCOPE │ <간결 원인> → <진행/액션>
    - cause: 기술적 원인 키워드 (binary incompatible, all mirrors exhausted 등)
    - action: 진행 중 액션 또는 사용자 액션 (retry mirror (N/M), check network (F12) 등)
    - 반환: LogEvent (rendered=False로 포맷터가 컬럼화 수행)
    """
    from chzzktube.core.log_event import LogEvent  # lazy import
    
    # 원인/액션 정규화
    cause_std = _normalize_cause(cause)
    action_std = _normalize_action(action)
    
    # 메시지 조합: "원인 → 액션" (빈 액션이면 원인만)
    if action_std:
        msg = f"{cause_std} → {action_std}"
    else:
        msg = cause_std
    
    # 길이 제한
    msg = _truncate_msg(msg)
    
    return LogEvent(
        stage=stage,
        status=status,
        scope=scope,
        platform=scope,
        msg=msg,
        is_error=True,
    )


def emit_error_warn(stage: str, scope: str, cause: str, action: str = "",
                    status: str = "WARN") -> LogEvent:
    """WARN 레벨 표준 에러 (is_error=False)."""
    return emit_error_standard(stage, scope, cause, action, status=status, is_error=False)

```

## File: chzzktube/core/log_event.py

```python
##### log_event.py - 구조화된 로그 이벤트 (v3.4.0)
"""raw_log 버스의 단일 진실 데이터 구조.

[계약 v3.4.0 — 4칸 미니멀 포맷]
- 발행자는 행동 근원(raw() 호출점)에서 LogEvent를 동봉해 전송한다.
  라벨링(stage/status/scope)은 태어난 곳에서 결정된다.
- SPEC 컬럼 폐지: spec 필드는 deprecated — 렌더러가 [spec] 태그로 MSG에 흡수.
  새 발행점에서 spec= 전달 금지.
- 채널 포함관계: history=전량, F12(full)=전량(⊇TUI), TUI(concise)=to_tui 선택.
  → "F12가 안 받는 로그"는 존재하지 않는다.
- 콘텐츠 정규식(is_tui_line) 라우팅 제로 — 렌더링 책임은 구독자(View)에게.
"""
from dataclasses import dataclass, field
import time


# v3.4.0 허용 STAGE 8종 / STATUS 9종 — 이외 값 발행 금지.
STAGES = ("SYS", "DEPS", "ANAL", "DL", "LIVE", "MERG", "BATCH", "POT")
STATUSES = ("READY", "RUN", "OK", "DONE", "SKIP", "WARN", "FAIL", "ABORT", "END")


@dataclass(slots=True)
class LogEvent:
    """구조화된 로그 이벤트."""
    stage: str = "SYS"
    status: str = "OK"
    # v3.4.0: platform → scope 개명. platform은 호환 별칭(읽기 전용 X, 쓰기 허용).
    scope: str = "-"
    platform: str = field(default="-", repr=False, compare=False)  # deprecated
    # v3.4.0 deprecated: SPEC 컬럼 폐지. 전달 시 [spec] 태그로 MSG 흡수된다.
    spec: str = "-"
    speed: str = "-"
    pct: float = None
    bar_frac: float = None
    msg: str = ""
    is_status: bool = False
    is_error: bool = False
    # msg가 이미 표시 완성형(컬럼 포맷·원문)일 때 True — 뷰는 재포맷하지 않는다
    rendered: bool = False
    timestamp: str = field(default_factory=lambda: time.strftime("[%H:%M:%S]"))


def safe_log_msg(obj) -> str:
    """LogEvent 또는 임의 객체에서 안전하게 문자열 메시지 추출.

    중첩된 LogEvent(msg 필드가 또 다른 LogEvent인 경우) 방어를 포함한다.
    """
    if isinstance(obj, LogEvent):
        msg = obj.msg
        if isinstance(msg, LogEvent):
            return str(msg)
        return str(msg) if msg is not None else ""
    return str(obj)

```

## File: chzzktube/core/log_history.py

```python
### log_history.py - 기동·구성요소·PO 서버 로그의 영구 히스토리 기록기
"""매 실행마다 구성요소 확인/업데이트, PO Token 서버 기동, 다운로더 원본 로그를
날짜별 파일로 남겨 문제 재현·디버깅의 1차 증거로 삼는다.

*  위치 : config.LOG_DIR (frozen: <exe>/logs, source: <repo>/logs)
*  파일 : chzzktube_YYYY-MM-DD.log (하루 1파일, UTF-8, append)
*  세션 : session_begin / session_end 로 시작·종료 마커 기록
*  정리 : KEEP_DAYS 초과된 오래된 히스토리 파일은 세션 시작 시 자동 삭제
*  의존 : config(leaf)만 사용·비Qt — 워커 스레드에서 호출해도 안전(threading.Lock).
          기록 실패는 절대 앱 동작을 방해하지 않는다(모든 예외 흡수).
"""
import datetime
import os
import threading

KEEP_DAYS = 30
_LOCK = threading.Lock()

def _now():
    return datetime.datetime.now()

def _log_path(now):
    import chzzktube.core.config as config
    return os.path.join(config.LOG_DIR, f"chzzktube_{now:%Y-%m-%d}.log")

def log(msg, level="INFO", **kwargs):
    """한 건(다중 줄 허용)을 오늘 히스토리 파일에 타임스탬프로 기록."""
    try:
        now = _now()
        lines = [
            l.rstrip()
            for l in str(msg).replace("\r", "").split("\n")
            if l.strip()
        ] or [""]
        with _LOCK:
            path = _log_path(now)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                for l in lines:
                    f.write(
                        f"[{now:%Y-%m-%d %H:%M:%S}] [{level:<5}] {l}\n"
                    )
    except Exception:
        pass  # 히스토리 기록 실패가 앱을 죽이지 않도록 흡수

def session_begin(app_name, app_version):
    """실행 세션 시작 마커 기록 + 오래된 히스토리 파일 정리."""
    log(
        f"===== {app_name} {app_version} 시작 (PID {os.getpid()}) =====",
        "BOOT",
    )
    log(
        "[~] 이 파일에는 구성요소 확인/업데이트, PO Token 서버 기동, "
        "다운로더 원본 로그가 기록됩니다.",
        "BOOT",
    )
    _prune()

def session_end():
    """실행 세션 종료 마커 기록."""
    log("===== 세션 종료 =====", "BOOT")

def exception(tag, t=None, v=None, tb=None):
    """미처리 예외 전체 트레이스백 기록. 인자 없이 except 블록 내에서도 호출 가능."""
    import sys
    import traceback

    if t is None:
        t, v, tb = sys.exc_info()
    try:
        body = "".join(traceback.format_exception(t, v, tb) or []).strip()
    except Exception:
        body = f"{t}: {v}"
    log(f"[{tag}]\n{body}", "ERROR")

def _prune():
    """KEEP_DAYS 초과 히스토리 파일 삭제 (세션 시작 시 1회)."""
    try:
        import chzzktube.core.config as config
        d = config.LOG_DIR
        cutoff = (_now() - datetime.timedelta(days=KEEP_DAYS)).timestamp()
        with _LOCK:
            if not os.path.isdir(d):
                return
            for name in os.listdir(d):
                if not (name.startswith("chzzktube_") and name.endswith(".log")):
                    continue
                p = os.path.join(d, name)
                try:
                    if os.path.getmtime(p) < cutoff:
                        os.remove(p)
                except OSError:
                    pass
    except Exception:
        pass

```

## File: chzzktube/core/media.py

```python
﻿### media.py - 순수 미디어 처리 헬퍼 (해상도 라벨 / 임시파일 정리 / FFmpeg 리먹싱 / 코덱 랭킹)
import glob
import os
import re
import subprocess

# 침묵 실패(리먹싱 등)의 증거 기록용 — raw 버스 단일 경유로 이관됨(v3.3.0)

### 사이트 축약기호 매핑 (extractor → 3~4글자 약자)
# 공식 브랜드 축약 우선, 없으면 도메인 앞글자 추출
# 로그 PLATFORM 컬럼에 표시됨 (예: [DEPS] YT, [DL] CHZ)
_EXTRACTOR_SHORT_STATIC = {
    # 영상 플랫폼 (공식/통용 축약)
    "youtube": "YT",
    "twitch": "TW",
    "instagram": "IG",
    "tiktok": "TIKT",
    "facebook": "FB",
    "twitter": "X",
    "x": "X",
    "naver": "NAV",
    "afreecaTV": "AFTV",
    "chzzk": "CHZ",
    "bilibili": "BILI",
    "dailymotion": "DM",
    "vimeo": "VM",
    "rumble": "RM",
    "odysee": "ODY",
    "peertube": "PT",
    # 음악/오디오
    "soundcloud": "SC",
    "spotify": "SP",
    "bandcamp": "BC",
    "mixcloud": "MC",
    # 커뮤니티/포럼 (한국)
    "fmkorea": "FM",
    "theqoo": "TQ",
    "clien": "CL",
    "dcinside": "DC",
    "mlbpark": "MP",
    # 기타
    "reddit": "RD",
    "tumblr": "TB",
    "pornhub": "PH",
    "xvideos": "XV",
    "youku": "YK",
    "iqiyi": "IQ",
}

def platform_short(extractor):
    """yt-dlp extractor 이름 → 3~4글자 축약기호.

    규칙:
    1. 정적 매핑 테이블 우선 (공식 브랜드 축약)
    2. 없으면 추출기명에서 특수문자 제거 후 앞 3~4글자 대문자
    3. 2글자 이하면 그대로 대문자
    """
    if not extractor:
        return "???"
    ext = extractor.strip().lower()
    if ext in _EXTRACTOR_SHORT_STATIC:
        return _EXTRACTOR_SHORT_STATIC[ext]
    # 동적 생성: 언더스코어/하이픈 제거 후 앞 4글자
    clean = re.sub(r"[_\-\s]+", "", ext)
    if len(clean) <= 4:
        return clean.upper()
    return clean[:4].upper()

### 코덱 품질 랭킹 데이터 테이블 (높을수록 우선순위 높음)
_VIDEO_CODEC_RANKS = [
    (("av01", "av1"), 3),
    (("vp09", "vp9"), 2),
    (("avc", "h264", "h.264"), 1),
]
_AUDIO_CODEC_RANKS = [
    (("opus",), 30),
    (("mp4a", "aac", "m4a"), 20),
    (("vorbis",), 10),
]

def get_video_codec_rank(vcodec):
    v = str(vcodec).lower()
    return next(
        (rank for keywords, rank in _VIDEO_CODEC_RANKS if any(k in v for k in keywords)),
        0,
    )

def get_audio_codec_rank(acodec, fid=""):
    a = str(acodec).lower()
    f = str(fid).lower()
    rank = next(
        (rank for keywords, rank in _AUDIO_CODEC_RANKS if any(k in a for k in keywords)),
        0,
    )
    return rank - 1 if "drc" in f else rank

### 코덱 전체명 → 짧은 표기 매핑 (로그/배지용)
_CODEC_SHORT_NAMES = [
    (("av01", "av1"), "AV1"),
    (("vp09", "vp9"), "VP9"),
    (("avc", "h264", "h.264"), "H264"),
    (("opus",), "OPUS"),
    (("mp4a.40.2",), "AAC-LC"),
    (("mp4a.40.5",), "HE-AAC v1"),
    (("mp4a.40.29",), "HE-AAC v2"),
    (("mp4a", "aac", "m4a"), "AAC"),
    (("vorbis",), "VORBIS"),
]

def codec_detail(codec):
    """코덱 상세 문자열('mp4a.40.2', 'avc1.64002A') — 없으면 빈 값."""
    c = str(codec or "").strip()
    if not c or c.lower() == "none":
        return ""
    if short_codec(c) == c.upper():
        return ""  # 'AAC' 등 총칭 — 상세 없음
    return c

def audio_flat(acodec):
    """짧은 이름과 상세를 괄호 없이 결합('AAC-LC mp4a.40.2') — 헤더 가지·배지용."""
    s = short_codec(acodec)
    d = codec_detail(acodec)
    return f"{s} {d}".strip()

def audio_spec(acodec):
    """오디오 코덱 표기의 단일 출처 — 짧은 이름과 상세(mp4a.40.2 등) 결합."""
    s = short_codec(acodec)
    d = codec_detail(acodec)
    return f"{s} ({d})" if d else s

def short_codec(codec):
    raw = str(codec or "")
    c = raw.strip().lower()
    if not c:
        return "?"
    exact = next((name for keys, name in _CODEC_SHORT_NAMES if c in keys), None)
    if exact:
        return exact
    return next(
        (name for keywords, name in _CODEC_SHORT_NAMES if any(k in c for k in keywords)),
        raw.upper(),
    )

def cli_format_desc(f):
    """yt-dlp -F 표(CLI) 컬럼을 한 줄로 재현 — 모든 소스의 포맷 표기 단일 출처."""
    f = f or {}
    vc = f.get("vcodec")
    ac = f.get("acodec")
    has_v = str(vc or "none") not in ("none", "")
    has_a = str(ac or "none") not in ("none", "")
    br = int(f.get("tbr") or f.get("abr") or 0)
    proto = str(f.get("protocol") or "").strip()
    rate_proto = " ".join(x for x in ((f"{br}k" if br else ""), proto) if x)

    parts = [str(f.get("ext") or "?").lower()]
    if has_v or int(f.get("height") or 0):
        res = f.get("resolution") or (
            f"{f.get('height')}p" if f.get("height") else "?"
        )
        fps_s = f" {int(f['fps'])}fps" if f.get("fps") else ""
        parts.append(f"{res}{fps_s}".strip())
        if rate_proto:
            parts.append(rate_proto)
        parts.append(short_codec(vc) if has_v else "?")
        if has_a:
            parts.append(audio_spec(ac))
    else:
        parts.append(audio_spec(ac) if has_a else "?")
    return " | ".join(p for p in parts if p)


# 드롭다운 라벨용 콘텐츠 타입 상수
_CONTENT_TYPE_LIVE = "LIVE"
_CONTENT_TYPE_VOD = "VOD"
_CONTENT_TYPE_SHORTS = "SHORTS"
_CONTENT_TYPE_CLIP = "CLIP"


def _format_bitrate(br):
    """비트레이트를 읽기 좋은 단위로 변환 — 8.4M, 119k 등."""
    br = int(br or 0)
    if br >= 1000:
        val = br / 1000
        # 소수점 첫째 자리까지 표기 (8.4M, 1.2M 등)
        return f"{val:.1f}M" if val != int(val) else f"{int(val)}M"
    return f"{br}k" if br else "?k"


def _format_protocol(f):
    """프로토콜 정보를 'PROTOCOL : TYPE' 형식으로 포맷."""
    proto = str(f.get("protocol") or "").strip().upper()
    ext = str(f.get("ext") or "").strip().upper()
    note = str(f.get("format_note") or "").strip().upper()
    
    # format_note에서 DASH, HLS 등 키워드 추출
    dash = "DASH" if "DASH" in note else ""
    hls = "HLS" if "HLS" in note else ""
    
    parts = []
    if proto:
        parts.append(proto)
    # ext가 protocol과 다르면 추가 (예: HTTPS + M3U8)
    if ext and ext != proto and ext != "?":
        if dash and dash not in parts:
            parts.append(dash)
        elif hls and hls not in parts:
            parts.append(hls)
        elif ext not in parts:
            parts.append(ext)
    elif dash:
        parts.append(dash)
    elif hls:
        parts.append(hls)
    
    return " : ".join(p for p in parts if p) if parts else "?"


def format_dropdown_label(f, content_type=""):
    """Fixed-Column ASCII Pipe Style 드롭다운 라벨 — 모든 소스의 포맷 표기 단일 출처.
    
    포맷: [1080p60]  8.4M  │  HTTPS : DASH  │  LIVE
           [ AUDIO ]  119k  │  HTTPS : DASH  │  VOD
    
    콘텐츠 타입(content_type): LIVE, VOD, SHORTS, CLIP (또는 빈 문자열)
    f: yt-dlp format dict
    """
    f = f or {}
    vc = f.get("vcodec")
    ac = f.get("acodec")
    has_v = str(vc or "none").strip() not in ("none", "", "None")
    has_a = str(ac or "none").strip() not in ("none", "", "None")
    br = int(f.get("tbr") or f.get("abr") or 0)
    height = int(f.get("height") or 0)
    fps = int(f.get("fps") or 0)
    
    # Column 1: 해상도/오디오 표시
    if has_v or height:
        res_str = f"{height}p" if height else "?"
        if fps:
            res_str += str(fps)
        col1 = f"[{res_str}]"
    elif has_a:
        col1 = "[ AUDIO ]"
    else:
        col1 = "[ ? ]"
    
    # Column 2: 비트레이트
    col2 = _format_bitrate(br)
    
    # Column 3: 프로토콜 정보
    col3 = _format_protocol(f)
    
    # Column 4: 콘텐츠 타입 (선택)
    col4 = content_type.upper() if content_type else ""
    
    # 고정 칼럼 조립 (Column 1은 9칸, Column 2은 6칸으로 정렬)
    label = f"{col1:<9} {col2:>5}  │  {col3}"
    if col4:
        label += f"  │  {col4}"
    return label

def format_bytes(size):
    """바이트(Bytes) 수치를 KB, MB, GB 단위로 자동 환산"""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} PB"

def cleanup_temp_files(filepath):
    """작업 중단 시 .part, .ytdl, .f*** 스트림 조각 및 임시 썸네일 일괄 삭제.

    [cleanup.py 통합] .f251 등 yt-dlp 스트림 조각(f코드)과 mp4/webm 등
    출력 확장자를 정규식으로 먼저 벗겨 base 경로를 산정한다 — splitext만
    쓰는 구버전은 '제목.f251.mp4' 형태의 조각을 잡지 못했다.
    """
    if not filepath:
        return
    try:
        dir_name = os.path.dirname(filepath)
        file_name = os.path.basename(filepath)

        # f코드 검출 및 제거 (예: .f251, .f137, .f401)
        file_name_clean = re.sub(r"\.f\d+.*$", "", file_name)

        # 일반 확장자 제거 (예: .part, .ytdl, .webm, .mp4)
        file_name_clean = re.sub(
            r"\.(part|ytdl|temp|mp4|webm|mkv|3gp|flv|ts)$",
            "",
            file_name_clean,
            flags=re.IGNORECASE,
        )

        base_path = os.path.join(dir_name, file_name_clean)
        search_pattern = base_path + "*"

        for target in glob.glob(search_pattern):
            if target.endswith(
                (
                    ".part",
                    ".ytdl",
                    ".temp",
                    "_temp.ts",
                    "_temp_thumb.jpg",
                    ".webp",
                    ".jpg",
                    ".png",
                )
            ):
                if os.path.exists(target):
                    try:
                        os.remove(target)
                    except Exception:
                        pass
    except Exception:
        pass

def remux_live_to_container(ts_path, container_setting="mp4"):
    if not ts_path or not os.path.exists(ts_path):
        return None
    target_ext = container_setting.lower()
    if target_ext not in ["mp4", "mkv"]:
        target_ext = "mp4"

    out_path = os.path.splitext(ts_path)[0] + f".{target_ext}"
    cmd = ["ffmpeg", "-y", "-i", ts_path, "-c", "copy", out_path]

    try:
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
            os.remove(ts_path)
            return out_path
    except Exception as e:
        # [증거 남김] windowed 빌드에선 print가 소멸하므로 히스토리에 기록 —
        # 임시 ts는 실패 시 보존되므로 사용자가 재시도할 수 있다.
        import chzzktube.core.raw_log as raw_log
        from chzzktube.core.log_event import LogEvent
        raw_log.raw(
            "media",
            LogEvent(
                stage="MERG", status="FAIL", scope="FFMP",
                msg=f"live remux failed - ts kept ({os.path.basename(ts_path)}): "
                f"{type(e).__name__}: {e}",
                is_error=True,
            ),
            to_tui=False,
        )

    return ts_path

```

## File: chzzktube/core/playlist.py

```python
##### playlist.py - 유튜브 채널/재생목록 URL 정규화
"""채널 URL을 평탄화(expand_targets)에 적합한 형태로 정규화한다."""
import re


def normalize_youtube_channel_url(url):
    """채널 URL 정규화.

    - `/@handle`      → `/@handle/videos`  (채널 탭 평탄화 기준 탭으로 이동)
    - `/c/...` `/channel/...` → 상위 목록 접미 제거 후 `/videos` 부착
    - 일반 watch/playlist URL은 그대로 반환
    """
    if not url:
        return url
    u = url.strip()
    u_lower = u.lower()
    if "youtube.com" not in u_lower and "youtu.be" not in u_lower:
        return u

    # 채널 계열만 대상 — 일반 동영상/재생목록은 그대로
    if re.search(r"playlist\?list=", u_lower):
        return u
    if "/watch" in u_lower or "/shorts/" in u_lower or "youtu.be/" in u_lower:
        return u
    if "/live/" in u_lower:
        return u

    # 이미 /videos|streams|playlists|shorts|featured|about 탭이면 그대로
    if re.search(r"/(videos|streams|playlists|shorts|featured|about|releases|live|community|membership|podcasts)/?$", u_lower):
        return u

    # /@handle 또는 /channel/UC... — 뒤의 탭 잔여물 제거 후 /videos
    m = re.match(r"(https?://(?:www\.)?youtube\.com/(?:@[^/?#]+|channel/[^/?#]+))", u)
    if m:
        return m.group(1).rstrip("/") + "/videos"

    # 기타 (music.youtube 등) — 그대로
    return u
```

## File: chzzktube/core/raw_log.py

```python
﻿"""raw_log — 앱 전체 동작의 단일 진실 공급원 (raw 버스).

[계약 v3.3.0 — 포함관계 모델]
- 진입: raw(tag, msg) — msg는 LogEvent(문자열은 즉시 LogEvent로 정규화).
- 포함관계: history=전량, F12(full)=전량(⊇TUI), TUI(concise)=to_tui=True일 때만.
  → "F12가 안 받는 로그"는 존재하지 않는다.
- 라우팅: 채널은 발행자(raw() 호출점)가 결정한다 — 콘텐츠 정규식 판정 제로.
- 구독 전 호출도 history에 적재되므로 유실 없다.

[계층] 발행 스레드에서는 bounded queue 적재만 수행한다.
파일 I/O와 구독자 호출은 단일 dispatcher 스레드에서 순차 처리하며,
구독자 콜백은 dispatcher lock을 잡지 않은 상태에서 호출한다.
"""
from collections import deque
import queue
import threading
import time
from typing import Callable

from chzzktube.core.log_event import LogEvent


MAX_QUEUE = 2048
MAX_FULL_EVENTS = 4096
_HISTORY_SUMMARY = "raw_log queue overflow: UI mirror dropped"


class _RawDispatcher:
    """Single-consumer dispatcher; publishers only perform a non-blocking put."""

    def __init__(self) -> None:
        self._queue: queue.Queue[tuple] = queue.Queue(maxsize=MAX_QUEUE)
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._concise_subs: list[Callable] = []
        self._full_subs: list[Callable] = []
        self._full_events: deque[LogEvent] = deque(maxlen=MAX_FULL_EVENTS)
        self._overflowed = False
        self._thread = threading.Thread(target=self._run, name="raw-log-dispatcher", daemon=True)
        self._thread.start()

    def subscribe_concise(self, fn: Callable) -> None:
        with self._lock:
            if fn not in self._concise_subs:
                self._concise_subs.append(fn)

    def subscribe_full(self, fn: Callable) -> None:
        with self._lock:
            if fn not in self._full_subs:
                self._full_subs.append(fn)

    def publish(self, event: LogEvent, to_tui: bool) -> bool:
        try:
            self._queue.put_nowait((event, bool(to_tui)))
            return True
        except queue.Full:
            self._record_overflow()
            return False

    def _record_overflow(self) -> None:
        with self._lock:
            if self._overflowed:
                return
            self._overflowed = True
        try:
            from chzzktube.core import log_history
            log_history.log(f"[raw-log] {_HISTORY_SUMMARY}", level="WARN")
        except Exception:
            pass
        event = LogEvent(
            stage="SYS",
            status="WARN",
            scope="RAW",
            msg=_HISTORY_SUMMARY,
            is_error=True,
        )
        try:
            self._queue.put_nowait((event, True))
        except queue.Full:
            pass

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                event, to_tui = self._queue.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                self._dispatch(event, to_tui)
            except Exception:
                # A subscriber must never kill the log pipeline.
                pass
            finally:
                self._queue.task_done()

    def _dispatch(self, event: LogEvent, to_tui: bool) -> None:
        try:
            import chzzktube.core.log_history as log_history
            log_history.log(
                f"[{getattr(event, 'tag', 'raw')}] {event.msg}",
                level="ERROR" if event.is_error else "INFO",
            )
        except Exception:
            pass

        with self._lock:
            self._full_events.append(event)
            full_subs = tuple(self._full_subs)
            concise_subs = tuple(self._concise_subs) if to_tui else ()

        for fn in full_subs:
            try:
                fn(event, bool(event.is_status))
            except TypeError:
                try:
                    fn(event)
                except Exception:
                    pass
            except Exception:
                pass
        for fn in concise_subs:
            try:
                fn(event, bool(event.is_status), bool(event.is_error))
            except TypeError:
                try:
                    fn(event)
                except Exception:
                    pass
            except Exception:
                pass

    def shutdown(self, timeout: float = 1.0) -> None:
        self._stop.set()
        self._thread.join(timeout=timeout)

    def flush(self, timeout: float = 1.0) -> None:
        """현재 queue와 dispatcher가 처리 중인 이벤트를 순서대로 기다린다."""
        self._queue.join()
        deadline = time.monotonic() + timeout
        while self.pending and time.monotonic() < deadline:
            time.sleep(0.01)

    @property
    def pending(self) -> int:
        return self._queue.qsize()

    @property
    def overflowed(self) -> bool:
        with self._lock:
            return self._overflowed


_dispatcher = _RawDispatcher()


def subscribe_concise(fn):
    """메인로그(TUI) 구독 등록 (중복 방지)."""
    _dispatcher.subscribe_concise(fn)


def subscribe_full(fn):
    """F12 상세로그 구독 등록 (중복 방지)."""
    _dispatcher.subscribe_full(fn)


def raw(tag, msg, is_status=False, is_error=False, to_tui=False):
    """단일 진입점 — 앱의 모든 행동은 여기로 수신된다."""
    if not isinstance(msg, LogEvent):
        msg = LogEvent(
            stage="SYS",
            status="FAIL" if is_error else "OK",
            scope="-",
            msg=str(msg),
            is_status=is_status,
            is_error=is_error,
            rendered=True,
        )
    else:
        if is_status:
            msg.is_status = True
        if is_error:
            msg.is_error = True
    _dispatcher.publish(msg, to_tui)


def flush(timeout: float = 1.0) -> None:
    """테스트/종료용: 현재 queue가 처리될 때까지 기다린다."""
    _dispatcher.flush(timeout)


def shutdown(timeout: float = 1.0) -> None:
    _dispatcher.shutdown(timeout)


```

## File: chzzktube/core/speed_window.py

```python
##### speed_window.py - 10초 이동평균 속도계
"""네트워크에서 실제 흐른 바이트만 샘플로 누적해 평균 속도를 계산한다.

라이브=릴레이 파이프 계수, VOD=yt-dlp downloaded_bytes 를 add()에 넘기며,
스트림 전환(비디오→오디오)·타겟 전환 시 reset()으로 윈도우를 비운다.
"""
import time


class SpeedWindow:
    """10초 이동평균 속도계.

    add(총 바이트 누적값)를 계속 공급하면 speed()가 초당 바이트를 반환.
    내부적으로 (타임스탬프, 누적바이트) 표본을 10초 윈도우로 유지한다.
    """

    def __init__(self, window=10.0):
        self._window = float(window)
        self._samples = []
        self._last_total = 0
        self._last_t = 0.0

    def reset(self):
        """윈도우 초기화 — 스트림 전환·타겟 전환 시 호출."""
        self._samples.clear()
        self._last_total = 0
        self._last_t = 0.0

    def add(self, total_bytes, t=None):
        """누적 바이트를 샘플로 추가 (t는 monotonic 초, 기본 now)."""
        now = t if t is not None else time.monotonic()
        self._last_total = total_bytes
        self._last_t = now
        self._samples.append((now, float(total_bytes)))
        cutoff = now - self._window
        if cutoff > 0:
            self._samples = [(tt, b) for tt, b in self._samples if tt >= cutoff]

    def speed(self):
        """초당 바이트. 표본 2개 미만 또는 시간차 없으면 0.0."""
        if len(self._samples) < 2:
            return 0.0
        t0, b0 = self._samples[0]
        t1, b1 = self._samples[-1]
        dt = t1 - t0
        if dt <= 0:
            return 0.0
        return (b1 - b0) / dt
```

## File: chzzktube/core/tool_log.py

```python
"""tool_log — 외부툴 출력 흡수 단일 래퍼 (v3.3.2).

[원칙] 새 기능이 외부툴(yt-dlp/streamlink/ffmpeg/bgutil)을 호출할 때는
이 모듈 경유만 허용한다. 직접 subprocess 파싱·로거 세팅 코드의 중복 작성을
금지한다 — 파싱 로직은 여기서 한 번만, 기능은 호출만.

[채널]
- yt-dlp Python API   : logger=YtLoggerBridge 주입 (Injection) — 기존 브리지 재사용
- subprocess(stderr)  : pump() — reader 스레드로 라인 흡수 → LogEvent(rendered=True)
                        원문 보존 → raw 버스. TUI 요약 1줄(상태 틱)은 progress_tick.
- CLI 일괄 실행       : run_cli() — updater.cli_raw 래핑 + F12 절취 분리 계약 유지.

[프로토콜] 무거운 추상화 없이 얇은 Protocol 3종만 선언한다.
새 어댑터는 아래 형상만 만족하면 된다 (덕타이핑 + 정적 검사 양립).
"""
import subprocess
import threading
from typing import Iterable, Optional, Protocol


class ToolLogger(Protocol):
    """yt-dlp logger 형상 — debug/info/warning/error 4메서드."""

    def debug(self, msg: str) -> None: ...
    def info(self, msg: str) -> None: ...
    def warning(self, msg: str) -> None: ...
    def error(self, msg: str) -> None: ...


class LineRunner(Protocol):
    """subprocess 라인 펌프 형상 — cmd 실행 → stdout+stderr 원문 라인 스트림."""

    def run(self, cmd: list, **kw) -> Iterable[str]: ...


class TokenProvider(Protocol):
    """PO 토큰 공급 형상 — video_id → 토큰 또는 None."""

    def fetch(self, video_id: str) -> Optional[str]: ...


def make_ytdlp_logger():
    """yt-dlp Python API 주입용 로거 — YtLoggerBridge 단일 출처.

    새 기능에서 yt-dlp logger 파라미터가 필요하면 이 팩토리만 호출할 것.
    YtLoggerBridge 클래스 직접 import·인스턴스화의 산발을 금지한다.
    """
    from chzzktube.core.yt_logger_bridge import YtLoggerBridge

    return YtLoggerBridge()


def pump(cmd, tag, stage, scope="-", to_tui=False, cancel=None,
         line_budget=4096, encoding="utf-8"):
    """subprocess stderr 실시간 흡수 — ffmpeg/streamlink/bgutil 공용.

    - reader 스레드로 stderr를 라인 단위 흡수, LogEvent(rendered=True) 원문
      보존으로 raw 버스에 적재한다 (F12+history, to_tui면 TUI도).
    - stdout은 호출부가 소비(파이프/파일)하도록 proc을 반환한다.
    - cancel(): 호출 시 True면 자식을 kill하고 drain한다.
    - 종료 코드가 0이 아니면 FAIL 1줄을 TUI에 남긴다.

    반환: (proc, stderr_thread) — 호출부는 stdout 처리 후 proc.wait() +
    stderr_thread.join()으로 마감할 것.
    """
    import chzzktube.core.raw_log as raw_log
    from chzzktube.core.log_event import LogEvent
    from chzzktube.infra.platform import spawn_kwargs

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        **spawn_kwargs(),
    )

    def _drain():

        try:

            for raw in iter(proc.stderr.readline, b""):

                if not raw:

                    break

                try:

                    line = raw.decode(encoding, "replace").strip()

                except Exception:

                    continue

                if not line:

                    continue

                if len(line) > line_budget:

                    line = line[:line_budget] + "…"

                try:

                    raw_log.raw(

                        tag,

                        LogEvent(stage=stage, status="OK", scope=scope,

                                 msg=line, rendered=True),

                        to_tui=bool(to_tui),

                    )

                except Exception:

                    pass

                if cancel is not None:

                    try:

                        if cancel():

                            break

                    except Exception:

                        pass

        except Exception:

            pass
    t = threading.Thread(target=_drain, daemon=True)
    t.start()
    return proc, t


def run_cli(label, *args, timeout=15):
    """CLI 일괄 실행 — updater.cli_raw 래핑 (수집 원문 전량 반환).

    절취는 호출부가 updater.truncate_for_full_log로 적재 시점에 수행할 것.
    """
    import chzzktube.infra.updater as updater
    return updater.cli_raw(label, *args, timeout=timeout)
```

## File: chzzktube/core/utils.py

```python
### 유틸리티 및 코어 로직
import os
import re
import subprocess

# Python 3.11+의 FutureWarning (nested set) 방지를 위해 대괄호 이스케이프 정밀화 적용
ANSI_ESCAPE_RE = re.compile(r"\x1B(?:[@-Z\-_]|\[[0-?]*[ -/]*[@-~])")


def clean_ansi(text):
    return ANSI_ESCAPE_RE.sub("", text)


def get_filename_template(cfg):
    prefix_key = cfg.get("filename_prefix", "none")
    suffix_key = cfg.get("filename_suffix", "id")

    prefix_map = {
        "none": "",
        "uploader": "[%(uploader)s] ",
        "date_dash_uploader": "%(upload_date>%Y-%m-%d)s [%(uploader)s] ",
        "date_compact_uploader": "%(upload_date>%Y%m%d)s [%(uploader)s] ",
        "date_dash": "%(upload_date>%Y-%m-%d)s ",
        "date_compact": "%(upload_date>%Y%m%d)s ",
    }

    suffix_map = {
        "id_res_fps": " [%(id)s] [%(height)sp] [%(fps)sfps]",
        "id_res": " [%(id)s] [%(height)sp]",
        "id": " [%(id)s]",
    }
    prefix = prefix_map.get(prefix_key, "")
    suffix = suffix_map.get(suffix_key, "")
    return f"{prefix}%(title)s{suffix}.%(ext)s"


def _open_windows_explorer(path):
    from chzzktube.infra.platform import reveal_in_file_manager
    reveal_in_file_manager(path)


def parse_sec(time_str):
    """시간 문자열(HH:MM:SS, MM:SS, SS)을 초(초 단위 float)로 변환"""
    if not time_str or str(time_str).strip().lower() == "inf":
        return float("inf")
    try:
        parts = [float(p) for p in str(time_str).strip().split(":")]
        multipliers = [3600, 60, 1]
        return sum(p * m for p, m in zip(parts, multipliers[-len(parts) :]))
    except (ValueError, TypeError):
        pass
    return 0.0

```

## File: chzzktube/core/watchdog.py

```python
"""chzzktube/core/watchdog.py - 단일 진실 시간(monotonic) 기반 구독형 워치독.

모든 타임아웃 상수와 하트비트 판정을 이 모듈로 집중해
15초 폴백/45초 분석/120초 게이트 등 산재한 매직 넘버를 단일 출처로 관리한다.

[설계]
- time.monotonic() 단일 진실 (시스템 시계 변경 영향 없음)
- 스레드 안전: Lock으로 _last_heartbeat / _grace_used 보호
- 주입 가능한 clock 파라미터로 단위 테스트에서 시간 조작 가능
- 워커는 heartbeat() 호출, 감시자는 check_timeout() 폴링
- QObject 상속으로 Qt 시그널/슬롯 연결 지원 (MainWindow 워치독 연동)
"""
import threading
import time
from typing import Callable

from PySide6.QtCore import QObject, Slot


# ── 상수 단일 출처 (HANDOVER §3 표와 동기화) ───────────────────────────
FALLBACK_TIMEOUT_SEC = 15.0   # 기동 폴백 (READY 강제 개방)
FALLBACK_GRACE_SEC = 3.0      # 폴백 유예 1회 (Followup-4)
GATE_TIMEOUT_SEC = 900.0      # [결함 4 수리] POT 빌드 최대 15분(900초) 고려 상향
ANALYSIS_TIMEOUT_SEC = 45.0   # AnalyzeWorker 타임아웃


class LivenessWatchdog(QObject):
    """단일 진실 시간 기반 워치독 — 워커 하트비트로 수명 연장, Grace 1회 지원.

    QObject 상속으로 Qt 시그널/슬롯 직접 연결 가능.
    스레드 안전: Lock으로 _last_heartbeat / _grace_used 보호.
    """

    __slots__ = ("timeout_sec", "grace_sec", "_clock", "_lock", "_last_heartbeat", "_grace_used")

    def __init__(
        self,
        timeout_sec: float,
        grace_sec: float = 0.0,
        clock: Callable[[], float] | None = None,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self.timeout_sec = float(timeout_sec)
        self.grace_sec = float(grace_sec)
        self._clock = clock or time.monotonic
        self._lock = threading.Lock()
        self._last_heartbeat = self._clock()
        self._grace_used = False

    @Slot()
    def heartbeat(self) -> None:
        """워커 진행 틱(yt-dlp 콜백, download 진행 등)에서 호출해 수명을 연장한다.

        Qt 슬롯으로 호출 가능 — 워커 스레드에서 시그널로 안전하게 연결됨.
        """
        with self._lock:
            self._last_heartbeat = self._clock()
            self._grace_used = False

    def check_timeout(self) -> bool:
        """타임아웃 만료 여부 판정. Grace 1회 적용 시 False 반환 후 grace 소진."""
        now = self._clock()
        with self._lock:
            elapsed = now - self._last_heartbeat
            if elapsed <= self.timeout_sec:
                return False
            if self.grace_sec > 0 and not self._grace_used:
                # 1회 유예: last_heartbeat를 'timeout - grace' 시점으로 이동
                self._last_heartbeat = now - self.timeout_sec + self.grace_sec
                self._grace_used = True
                return False
            return True

    def elapsed(self) -> float:
        """마지막 하트비트 이후 경과 시간 (조회용)."""
        with self._lock:
            return self._clock() - self._last_heartbeat

    def remaining(self) -> float:
        """타임아웃까지 남은 시간 (음수면 이미 만료)."""
        with self._lock:
            return self.timeout_sec - (self._clock() - self._last_heartbeat)

    def reset(self) -> None:
        """하트비트와 동일 — last_heartbeat=now, grace 복구."""
        self.heartbeat()
```

## File: chzzktube/core/yt_logger_bridge.py

```python
### yt_logger_bridge.py - yt-dlp 로거 어댑터 (Analyze/Download 공용)
"""yt-dlp logger 콜백을 raw_log 버스로 연결하는 공용 어댑터.

- ANSI 제거는 utils.clean_ansi()만 사용한다.
- \r progress tick은 한 청크로 조립해 최신 meaningful tick만 발행한다.
- 일반 info/warning/error는 원문을 F12/history에 보존한다.
"""
import os
import re
import threading
import time

from chzzktube.core.utils import clean_ansi


_PROGRESS_RE = re.compile(r"^\s*\[download\].*?(\d+(?:\.\d+)?)%(?:\s|$)")
_MERGE_TEXT = "Merging formats into"
_ALREADY_DOWNLOADED = "has already been downloaded"


class YtLoggerBridge:
    """yt-dlp logger → raw_log bus adapter."""

    _MAX_CARRIAGE_CHARS = 4096

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._carriage_buffer = ""
        self._last_progress = None
        self._last_progress_at = 0.0

    @staticmethod
    def _is_progress(msg: str) -> bool:
        return bool(_PROGRESS_RE.match(msg))

    def _emit_progress(self, msg: str) -> None:
        now = time.monotonic()
        with self._lock:
            # yt-dlp progress callbacks are often far faster than 2 Hz.
            if self._last_progress is not None and now - self._last_progress_at < 0.5:
                return
            self._last_progress = msg
            self._last_progress_at = now
        import chzzktube.core.raw_log as raw_log
        from chzzktube.core.log_event import LogEvent
        raw_log.raw(
            "ytdlp",
            LogEvent(
                stage="DL",
                status="RUN",
                scope="YTDL",
                msg=msg,
                is_status=True,
            ),
            to_tui=True,
        )

    def _emit_non_progress(self, clean_msg: str, level: str) -> None:
        import chzzktube.core.raw_log as raw_log
        from chzzktube.core.log_event import LogEvent
        status = {
            "warning": "WARN",
            "error": "FAIL",
            "info": "OK",
            "debug": "OK",
        }.get(level, "OK")
        raw_log.raw(
            "ytdlp",
            LogEvent(
                stage="DL",
                status=status,
                scope="YTDL",
                msg=clean_msg,
                is_error=level == "error",
            ),
        )
        if _MERGE_TEXT in clean_msg:
            raw_log.raw(
                "dl",
                LogEvent(stage="MERG", status="RUN", scope="FFMP", msg="merging"),
                to_tui=True,
            )
        if _ALREADY_DOWNLOADED in clean_msg:
            fname = (
                clean_msg.replace("[download]", "")
                .replace(_ALREADY_DOWNLOADED, "")
                .strip()
            )
            raw_log.raw(
                "dl",
                LogEvent(
                    stage="DL",
                    status="OK",
                    scope="YTDL",
                    msg=f"skip - exists ({os.path.basename(fname)})",
                ),
                to_tui=True,
            )

    def _flush_carriage(self, msg: str, level: str) -> None:
        clean_msg = clean_ansi(msg)
        if not clean_msg:
            return

        # warning/error는 progress buffer에 갇히지 않고 즉시 보존한다.
        if level in {"warning", "error"}:
            clean_msg = clean_msg.replace("\r", " ").replace("\n", " ").strip()
            if clean_msg:
                self._emit_non_progress(clean_msg, level)
            return

        with self._lock:
            parts = clean_msg.replace("\n", "\r").split("\r")
            if len(parts) > 1:
                # 같은 콜백 안 \r 반복 = 같은 줄 덮어쓰기 스냅샷 → 마지막이 최신.
                candidate = parts[-1] or (parts[-2] if len(parts) > 1 else "")
                if clean_msg.endswith("\r"):
                    # 줄이 아직 진행 중 → 다음 청크와 연결하기 위해 이월 보류.
                    self._carriage_buffer = candidate[-self._MAX_CARRIAGE_CHARS:]
                    return
                self._carriage_buffer = ""
                clean_msg = candidate
            elif self._carriage_buffer:
                # \r 없는 청크 = 직전 이월 조각의 이어짐 → 합쳐 한 줄로 재구성.
                clean_msg = (
                    self._carriage_buffer + parts[-1]
                )[-self._MAX_CARRIAGE_CHARS:]
                self._carriage_buffer = ""
            else:
                clean_msg = parts[-1]

        clean_msg = clean_msg.strip()
        if not clean_msg:
            return
        if self._is_progress(clean_msg):
            self._emit_progress(clean_msg)
            return
        self._emit_non_progress(clean_msg, level)

    def debug(self, msg):
        self._flush_carriage(msg, "debug")

    def info(self, msg):
        self._flush_carriage(msg, "info")

    def warning(self, msg):
        self._flush_carriage(msg, "warning")

    def error(self, msg):
        self._flush_carriage(msg, "error")

```

## File: chzzktube/workers/__init__.py

```python

```

## File: chzzktube/workers/analyze_worker.py

```python
### analyze_worker.py - URL 분석 백그라운드 스레드
"""yt-dlp URL 분석 전용 워커 (AnalyzeWorker).

- 경량(매니페스트 미열거)/딥(매니페스트 열거) 분석 모드 지원.
- tv → web_safari 플레이어 클라이언트 순차 폴백 등 추출 우회 로직 보유.
- [계층] L1 Worker Thread — controller에서 직접 생성, log_full 시그널은
  log_console 경유로 View에 전달.
"""
import os
import re
import subprocess
import sys
import time
import urllib.request
import yt_dlp

# 네임스페이스 패키지 대응: yt_dlp.YoutubeDL 또는 yt_dlp.main.YoutubeDL에서 import
# conftest.py의 .pylib 부트스트랩으로 실제 yt_dlp가 sys.path[0]에 있음
try:
    from yt_dlp import YoutubeDL
except ImportError:
    try:
        YoutubeDL = yt_dlp.YoutubeDL
    except AttributeError:
        from yt_dlp.main import YoutubeDL

# [플러그인 기생 차단] 구 getpot bgutil 플러그인(venv pip + %APPDATA% 잔재)이
# 모든 yt-dlp 추출에 자동 로딩되어 자체 deno PO 생성(generate_once.ts — 첫 실행
# 시 TS 컴파일+FFI로 수십 초, 15~20초 타임아웃 반복)을 돌려 분석 스톨과
# "page needs to be reloaded" 실패를 유발했다. 앱의 PO 공급은 자체 Node 서버
# (pot_provider)로 완전 이전했으므로 외부 플러그인을 전면 차단한다.
# 반드시 첫 YoutubeDL 생성 전에 설정 (plugins 로딩은 1회성 lazy init).
try:
    yt_dlp.plugins.plugin_dirs.value = []
except AttributeError:
    # 구버전 yt-dlp나 네임스페이스 패키지 형태에서는 plugins 모듈이 없을 수 있음
    pass

from PySide6.QtCore import QThread, Signal

from chzzktube.core.watchdog import ANALYSIS_TIMEOUT_SEC
from chzzktube.core.chzzk_api import analyze_chzzk_clip_api, analyze_chzzk_vod_api, analyze_chzzk_live_api, ChzzkAuthError
from chzzktube.core.log_emitter import format_kv_line, format_tree_item
from chzzktube.core.media import (
    audio_spec,
    cli_format_desc,
    format_bytes,
    format_dropdown_label,
    get_audio_codec_rank,
    get_video_codec_rank,
    short_codec,
    codec_detail,
)
from chzzktube.core.utils import clean_ansi, get_filename_template
from chzzktube.core.dl_platform import detect_content_type
from chzzktube.core.playlist import normalize_youtube_channel_url
from chzzktube.core.client_opts import (
    _apply_client_opts,
    _apply_cookie_opts,
    _apply_ejs_opts,
    _apply_ffmpeg_opts,
    _apply_light_analysis_opts,
    _apply_pot_opts,
    _dedupe_by_label,
)
from chzzktube.infra.po_client import extract_video_id
from chzzktube.core.yt_logger_bridge import YtLoggerBridge

class AnalyzeWorker(QThread):
    # [v3.3.0] 로그는 raw 버스 단일 경유 — log_full 시그널 폐기.
    result_ready = Signal(dict)
    error_occurred = Signal(str)
    # [Watchdog] 무페이로드 진행 하트비트. 뷰가 소유한 분석 워치독 수명 연장 전용.
    # §5-21에 따라 문자열을 싣지 않으며, 만료 판정·복구는 뷰가 단독 수행한다.
    activity = Signal()

    def __init__(self, target_url, cfg, deep=False):
        super().__init__()
        self.target_url = target_url
        self.cfg = cfg
        self.deep = bool(deep)  # True → 매니페스트 열거 포함(포맷 직접 고르기). False → 경량(기본)
        self.logger = YtLoggerBridge()
        # [다운로드 일관성] 분석에서 통과한 클라이언트 기록 — 다운로드가
        # 봇 게이트/PO 토큰 경로를 재진입해 0%에 머무는 것을 방지.
        self.client_used = "auto"

    # [순정 위임] yt-dlp 순정 클라이언트 로테이션 완전 위임 (web_embedded → tv_downgraded → web_safari → mweb → tv...)
    # 앱 레벨 수동 로테이션 제거 — 단일 auto 호출로 순정이 알아서 최적 클라 선택 + EJS 솔버 작동
    # PO token 필요 시(age-gate/봇체크) 동일 호출에 token만 주입
    _RETRY_CLIENTS = []  # 사용 안 함 — 순정 위임

    @staticmethod
    def _is_bot_block(ex):
        """YouTube 봇 체크/JS 챌린지 실패 판별 — 클라이언트 회전 대상 여부.

        [주의] 회전 중간 클라이언트(ios 등 쿠키 미지원 스킵)의 2차 오류인
        "No video formats found" / "Requested format is not available"도
        bot-block에서 파생된 것이므로 회전을 계속해야 한다. 이를 포함하지
        않으면 회전이 중간에 끊겨 마지막 폴백이 시도조차 되지 않는다.
        """
        s = str(ex).lower()
        return (
            "the page needs to be reloaded" in s
            or "n challenge solving failed" in s
            or "challenge solving failed" in s
            or "no video formats found" in s
            or "requested format is not available" in s
        )

    def _extract_youtube(self, url, flat):
        # yt-dlp progress_hook → 무페이로드 하트비트 (뷰 워치독 수명 연장)
        def _progress_hook(d):
            if d.get("status"):
                self.activity.emit()

        # ydl_opts에 훅 추가할 예정이므로 flat 분기 전에 준비
        """yt-dlp 추출 — bot-check 실패 시 ios→tv 클라이언트 회전.

        [회전 정책] 사용자가 특정 클라이언트를 지정했으면 그 값 하나만
        시도하고 자동 회전하지 않는다(auto일 때만 ios→tv). 회전 흔적은
        상세 로그(F12)에만 남기고 간결 로그는 조용히 유지한다.
        """
        configured = str(self.cfg.get("yt_player_client", "auto") or "auto")
        base = {
            "logger": self.logger,
            "skip_download": True,
            # [가드] updater.py의 socket.setdefaulttimeout(2) 전역값이 새 소켓에
            # 적용되는 것 대비 — 명시 타임아웃으로 안전하게 오버라이드.
            "socket_timeout": 30,
        }
        if flat:
            base["extract_flat"] = True
        else:
            base["noplaylist"] = True
            base["extract_flat"] = False

        # [순정 위임] 단일 auto 호출 — yt-dlp 순정 클라 로테이션 + EJS 솔버 완전 위임
        # client="auto" 전달 시 _apply_client_opts가 강제 지정 없이 순정 기본값 사용
        self.activity.emit()
        ydl_opts = dict(base)
        ydl_opts["progress_hooks"] = [_progress_hook]
        _apply_cookie_opts(ydl_opts, self.cfg)
        _apply_client_opts(ydl_opts, self.cfg, forced=None)  # auto → 순정 위임
        if not self.deep:
            _apply_light_analysis_opts(ydl_opts)
        _apply_ffmpeg_opts(ydl_opts)
        _apply_ejs_opts(ydl_opts)

        # PO token 주입 (age-gate/봇체크용) — 순정 호출에 token만 추가
        video_id = extract_video_id(url)
        if video_id:
            # client="auto" 시 순정이 최종 선택할 클라와 일치하도록 web_embedded 기준 주입
            # (순정은 쿠키 있으면 web/web_embedded 우선, 없으면 visionos→web_embedded)
            from chzzktube.pipeline.target_downloader import _has_configured_cookies
            pot_client = "web" if _has_configured_cookies(self.cfg) else "web_embedded"
            _apply_pot_opts(ydl_opts, video_id, client=pot_client)

        try:
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
            # 순정이 실제 사용한 클라는 extractor_args에 기록되지 않으므로
            # client_used는 "auto"로 남김 — 다운로드 단계도 auto로 위임
            self.client_used = "auto"
            return info
        except Exception as e:
            raise e

    def run(self):
        import chzzktube.core.raw_log as raw_log
        raw_log.raw("analyze", f"--- [format analysis start] {self.target_url} ---")
        # 분석 시작 통보 — 뷰 워치독 수명 연장
        self.activity.emit()

        try:
            m_clip = re.search(r"chzzk\.naver\.com/clips?/", self.target_url)
            m_vod = re.search(r"chzzk\.naver\.com/video/(\d+)", self.target_url)
            m_live = re.search(r"chzzk\.naver\.com/live/", self.target_url)
            if m_clip or m_vod or m_live:
                # 콘텐츠 타입 감지
                content_type = "CLIP" if m_clip else ("LIVE" if m_live else "VOD")
                
                ch_info = (
                    analyze_chzzk_clip_api(self.target_url)
                    if m_clip
                    else (analyze_chzzk_live_api(self.target_url) if m_live
                          else analyze_chzzk_vod_api(self.target_url))
                )
                v_list = []
                a_list = []
                for fmt in ch_info.get("formats", []):
                    vcodec = fmt.get("vcodec", "")
                    acodec = fmt.get("acodec", "")
                    has_v = bool(vcodec)
                    has_a = bool(acodec)
                    base = {
                        "id": fmt["id"],
                        "height": fmt["height"],
                        "fps": fmt.get("fps", 0),
                        "vcodec": vcodec,
                        "acodec": acodec,
                        "bitrate": fmt["bitrate"],
                        "tbr": fmt["bitrate"],
                    }
                    if has_v:
                        v_list.append({
                            **base,
                            "label": format_dropdown_label(
                                {
                                    "ext": "mp4",
                                    "height": fmt.get("height"),
                                    "fps": fmt.get("fps") or None,
                                    "tbr": fmt.get("bitrate"),
                                    "protocol": "https",
                                    "vcodec": vcodec,
                                    "acodec": "",
                                },
                                content_type,
                            ),
                        })
                    elif has_a:
                        a_list.append({
                            **base,
                            "abr": fmt.get("bitrate", 0),
                            "label": format_dropdown_label(
                                {
                                    "ext": "m4a",
                                    "tbr": fmt.get("bitrate"),
                                    "protocol": "https",
                                    "vcodec": "none",
                                    "acodec": acodec,
                                },
                                content_type,
                            ),
                        })
                if not v_list and not a_list:
                    self.error_occurred.emit(
                        "chzzk stream fail (cookie)"
                    )
                    return
                self.result_ready.emit(
                    {"info": ch_info, "v_list": v_list, "a_list": [], "is_chzzk": True}
                )
            else:
                is_playlist = ("playlist?list=" in self.target_url) or ("list=" in self.target_url)
                is_channel = any(k in self.target_url for k in ["/@", "/channel/", "/c/", "/user/"])
                
                if is_playlist or is_channel:
                    info = self._extract_youtube(
                        normalize_youtube_channel_url(self.target_url), flat=True
                    )
                    
                    entries = info.get("entries") or []
                    video_count = len(entries)
                    title = info.get("title") or "playlist/channel"
                    
                    self.result_ready.emit({
                        "is_playlist": True,
                        "title": title,
                        "count": video_count,
                        "v_list": [],
                        "a_list": [],
                    })
                    return

                info = self._extract_youtube(self.target_url, flat=False)

                if info:
                    if "entries" in info:
                        info = info["entries"][0]
                    
                    # 콘텐츠 타입 감지 (URL + 메타데이터)
                    content_type = detect_content_type(self.target_url, info)
                    
                    v_list, a_list = [], []
                    for f in info.get("formats", []):
                        fid, ext = f.get("format_id", "?"), f.get("ext", "?")
                        vcodec, acodec = f.get("vcodec", "none"), f.get("acodec", "none")
                        tbr, fps, height = (
                            int(f.get("tbr") or 0),
                            f.get("fps") or 0,
                            f.get("height") or 0,
                        )
                        proto = f.get("protocol") or ""
                        has_v = str(vcodec or "").strip() not in ("none", "", "None")
                        has_a = str(acodec or "").strip() not in (
                            "none",
                            "",
                            "None",
                        )

                        if has_v:
                            # 비디오 드롭다운: 비디오 정보만 (오디오 코덱 생략)
                            v_list.append(
                                {
                                    "id": fid,
                                    "height": height,
                                    "fps": fps,
                                    "tbr": tbr,
                                    "vcodec": vcodec,
                                    "acodec": acodec,
                                    "proto": proto,
                                    "ext": ext,
                                    "label": format_dropdown_label(
                                        {**f, "acodec": ""}, content_type
                                    ),
                                }
                            )
                        if has_a and not has_v:
                            a_list.append(
                                {
                                    "id": fid,
                                    "abr": int(f.get("abr") or tbr or 0),
                                    "acodec": acodec,
                                    "ext": ext,
                                    "proto": proto,
                                    "label": format_dropdown_label(f, content_type),
                                }
                            )

                    v_list.sort(
                        key=lambda x: (
                            x["height"],
                            x["fps"],
                            get_video_codec_rank(x["vcodec"]),
                            x["tbr"],
                        ),
                        reverse=True,
                    )
                    a_list.sort(
                        key=lambda x: (
                            x["abr"],
                            get_audio_codec_rank(x["acodec"], x["id"]),
                        ),
                        reverse=True,
                    )

                    v_list = _dedupe_by_label(v_list)
                    a_list = _dedupe_by_label(a_list)

                    self.result_ready.emit(
                        {
                            "info": info,
                            "v_list": v_list,
                            "a_list": a_list,
                            "is_chzzk": False,
                            "yt_client": getattr(self, "client_used", "auto") or "auto",
                        }
                    )
                else:
                    self.error_occurred.emit("media info fail")
        except Exception as ex:
            ex_str = str(ex).lower()
            if (
                "sign in to confirm your age" in ex_str
                or "age-restricted" in ex_str
                or "age-gated" in ex_str
                or "members-only" in ex_str
            ):
                self.error_occurred.emit(
                    "age/membership restricted"
                )
            # [결함 3 수리] 치지직 인증 에러(쿠키 만료/부재) 명시적 처리
            elif isinstance(ex, ChzzkAuthError):
                self.error_occurred.emit(
                    "chzzk cookie expired — please reconfigure cookies"
                )
            elif "the page needs to be reloaded" in ex_str or "challenge solving failed" in ex_str:
                # [봇 체크] EJS 솔버 + 클라이언트 회전까지 실패하면 남은 수단은
                # 브라우저에서 영상 재생(세션 갱신) — 미니멀 영문 매핑.
                self.error_occurred.emit("bot check — reload browser")
            else:
                # [TUI 규격] yt-dlp 원문은 보일러플레이트("please report this
                # issue...")가 메시지를 초과한다. 첫 ERROR 행의 핵심 구문만
                # 추출해 60자로 절단 — 상세 원문은 F12 로그에 이미 기록됨.
                msg = clean_ansi(str(ex))
                m = re.search(r"ERROR:\s*\[[^\]]+\]\s*[^:]+:\s*(.+)", msg)
                if m:
                    msg = m.group(1).strip()
                msg = re.split(r";\s*please report|;\s*filling out|\.\s*[Uu]se --list-formats", msg)[0]
                self.error_occurred.emit(f"analysis error: {msg[:60]}")


```

## File: chzzktube/workers/downloader.py

```python
##### downloader.py - 다운로드 백그라운드 스레드
"""배치 다운로드 실행 워커 (DownloadWorker).

- 대상 평탄화·개별 분기(_td), 진행 틱(_pe), 배치 마감(_fin)을 worker 인자
  방식으로 호출하는 껍데기 오케스트레이션.
- [분리] YtLoggerBridge·AnalyzeWorker → analyze_worker.py / yt_logger_bridge.py.
  라우팅·종속 헬퍼는 각각의 전용 모듈에서만 import한다 (미사용 임포트 금지).
"""
import yt_dlp
from PySide6.QtCore import QThread, Signal

import chzzktube.pipeline.finalizer as _fin
import chzzktube.pipeline.progress_emitter as _pe
import chzzktube.pipeline.target_downloader as _td
from chzzktube.core import raw_log
from chzzktube.core.dl_platform import _dl_platform
from chzzktube.core.speed_window import SpeedWindow
from chzzktube.core.watchdog import GATE_TIMEOUT_SEC, LivenessWatchdog
from chzzktube.core.yt_logger_bridge import YtLoggerBridge
from chzzktube.core.log_emitter import emit_error_standard, emit_error_warn

# [플러그인 기생 차단] analyze_worker.py와 동일 사유. 값 대입은 idempotent라
# 모듈 로딩 순서와 무관하게 안전 (첫 YoutubeDL 생성 전 1회 유효하면 된다).
# 모든 최상단 import가 끝난 직후, 클래스 정의 전에 배치하여 E402를 원천 차단한다.
try:
    yt_dlp.plugins.plugin_dirs.value = []
except AttributeError:
    # 구버전 yt-dlp나 네임스페이스 패키지 형태에서는 plugins 모듈이 없을 수 있음
    pass

class DownloadWorker(QThread):
    # [v3.3.0] 로그는 raw 버스(raw_log.raw) 단일 경유 — log_concise/log_full 시그널 폐기.
    finished_all = Signal(int, int)

    def __init__(
        self,
        targets,
        cfg,
        state_dict=None,  # 호환용: dict 또는 SessionState 또는 None
        v_sel="auto",
        a_sel="auto",
        is_live_hint=False,
        v_spec=None,
        audio_desc="",
        yt_client="auto",
        canceled_signal=None,  # Signal(bool) — 취소 신호 수신용
        skip_signal=None,      # Signal(bool) — 스킵 신호 수신용
    ):
        super().__init__()
        self.targets = targets
        self.cfg = cfg
        self._state_dict = state_dict
        self.v_sel = v_sel
        self.a_sel = a_sel
        self.audio_desc = str(audio_desc or "")
        self.v_spec = v_spec or {}
        self.is_live_hint = bool(is_live_hint)
        # [다운로드 일관성] 분석 단계에서 실증·통과한 클라이언트 (auto면 yt-dlp 기본)
        self.yt_client = str(yt_client or "auto")
        self.current_file = None
        self._meta_logged = False
        self._last_tick_t = 0.0
        self._speed_win = SpeedWindow()
        self._tick_file = None
        self._tick_last = 0
        self.live_partially_saved = False
        self.logger = YtLoggerBridge()  # [v3.3.0] 버스 직행 — 시그널 인자 폐기
        self.total_count = len(targets)
        self.current_idx = 1
        self.current_url = None
        self._live_proc = None  # 라이브 녹화 프로세스 핸들 (앱 종료 시 정리용)
        self._ctx = None  # [A4] DownloadContext 참조 — 라이브 proc는 ctx에 부착된다
        # [Watchdog] 다운로드 진행용 워치독 — 게이트/분석 타임아웃 연장
        self._download_watchdog = LivenessWatchdog(GATE_TIMEOUT_SEC, 0.0)
        
        # 신호 기반 상태 수신 (SessionState 패턴)
        self._canceled = False
        self._skip = False
        if canceled_signal:
            canceled_signal.connect(self._on_canceled)
        if skip_signal:
            skip_signal.connect(self._on_skip)

    @property
    def state(self):
        """하위 호환: state_dict 또는 SessionState 모두 지원."""
        if self._state_dict is not None:
            return self._state_dict
        # SessionState 호환 dict 반환
        return {"canceled": self._canceled, "skip": self._skip, "running": True, "analyzing": False, "picking": False}

    def _on_canceled(self, val: bool):
        self._canceled = val

    def _on_skip(self, val: bool):
        self._skip = val

    def extract(self):
        """파이프라인 모듈에 넘길 DownloadContext를 생성한다 (D: 명시적 계약)."""
        from chzzktube.pipeline.dl_context import DownloadContext

        return DownloadContext(
            cfg=self.cfg,
            v_sel=self.v_sel,
            a_sel=self.a_sel,
            v_spec=self.v_spec,
            audio_desc=self.audio_desc,
            logger=self.logger,
            current_url=self.current_url or "",
            current_file=self.current_file,
            state=self.state,
            speed_win=self._speed_win,
            total_count=self.total_count,
            current_idx=self.current_idx,
            is_live_hint=self.is_live_hint,
            live_partially_saved=self.live_partially_saved,
            yt_client=self.yt_client,
            targets=self.targets,
            finished_all=self.finished_all,
            _download_watchdog=self._download_watchdog,
            _gate_watchdog=self._download_watchdog,
            _live_watchdog=self._download_watchdog,
            _analysis_watchdog=self._download_watchdog,
        )

    def _reset_loop_state(self):
        """매 타겟마다 필요한 상태 변수들을 한 번에 초기화 (worker 내부용)."""
        self._last_tick_t = 0.0
        self._tick_file = None
        self._tick_last = 0

    def run(self):
        """DownloadWorker 메인 스레드 — 세션 종료 통지는 반드시 정확히 한 번."""
        ctx = None
        failed_targets = []
        success_count = 0
        def report_error(message):
            # 로그 장애가 제어용 종료 통지를 막아서는 안 된다.
            try:
                # [v3.8.1] 표준 에러 헬퍼로 변환
                from chzzktube.core.log_emitter import emit_error_standard
                raw_log.raw("dl", emit_error_standard("DL", _dl_platform(""), "download failed", message), to_tui=True)
            except Exception:
                pass

        try:
            # [Watchdog] 다운로드 시작 시 게이트 워치독 리셋
            self._download_watchdog.reset()
            ctx = self.extract()
            self._ctx = ctx
            ctx.targets = _td.expand_targets(ctx)
            self.targets = ctx.targets
            self.total_count = len(self.targets)
            ctx.total_count = self.total_count

            failed_targets = []
            skip_targets = []
            success_count = 0

            for idx, item in enumerate(self.targets, 1):
                # ClassifiedTarget에서 URL 추출
                url = item.url if hasattr(item, 'url') else (item.get("url") if isinstance(item, dict) else str(item))
                ctx.advance_target(idx, url)
                self.current_idx = ctx.current_idx
                self.current_url = ctx.current_url

                if self.state["canceled"]:
                    break
                if self.state["skip"]:
                    self.state["skip"] = False
                    raw_log.raw(
                        "dl",
                        _pe.emit_dl("SKIP", scope=_dl_platform(url), msg=f"skipped ({idx}/{self.total_count})"),
                        to_tui=True,
                    )
                    skip_targets.append((url, "user skip"))
                    continue

                # [Watchdog] 실제 대상 진입 전 하트비트
                self._download_watchdog.heartbeat()
                result = _td.download_target(ctx, item, failed_targets, skip_targets)
                if result is True:
                    success_count += 1
                elif result == "skip":
                    # download_target 내부에서 skip 로그 출력 및 skip_targets 수집 완료
                    pass
                # [Watchdog] 대상 완료 후 하트비트
                self._download_watchdog.heartbeat()
        except Exception as ex:  # noqa: BLE001
            if "CANCELED_BY_USER" not in str(ex) and "중지되었습니다" not in str(ex) and not self.state["canceled"]:
                failed_targets.append((self.current_url or "", str(ex)))
                report_error(str(ex))
        finally:
            try:
                if ctx is not None:
                    _fin.finalize(ctx, self.total_count, failed_targets, success_count, skip_targets=skip_targets, notify=False)
            except Exception as ex:  # noqa: BLE001
                report_error(f"finalization error: {ex}")
            finally:
                self.finished_all.emit(success_count, len(failed_targets))

    def kill_live_process(self):
        """[A4] 라이브 녹화 프로세스 정리 — worker·ctx 양쪽 핸들을 모두 킬."""
        handles = (self._live_proc, getattr(getattr(self, "_ctx", None), "_live_proc", None))
        for proc in handles:
            if proc is None:
                continue
            try:
                proc.kill()
                raw_log.raw(
                    "dl",
                    emit_error_warn("DL", "FFMP", "live recorder killed", "worker terminated"),
                    to_tui=True,
                )
            except OSError:
                # 프로세스가 이미 종료되었거나 권한 부족일 때만 안전하게 무시
                pass
        self._live_proc = None

    def terminate(self):
        """스레드 강제 종료 시 라이브 녹화 프로세스도 함께 정리."""
        self.kill_live_process()
        super().terminate()


```

## File: chzzktube/workers/update_worker.py

```python
### update_worker.py - DEPS 체크/자동 업그레이드 워커
"""시작 시퀀스의 의존성 확인·수급을 담당하는 백그라운드 워커 (UpdateWorker).

- _do_check : updater.check_deps() 결과를 DEPS 이벤트로(TUI 5줄), CLI 원문을
  raw 문자열로(F12) 버스 단일 경유 전송. stale 패키지는 check_done(list)으로 반환.
- _do_upgrade: ProvisioningManager를 통해 yt-dlp/streamlink/ffmpeg/node/bgutil 일괄 수급.
  각 수급의 실제 진행 여부를 _had_action 판별해 '요약 결론' 1줄만 남긴다.
- [분리] dialogs.py에서 추출 — 대화상자 컬렉션과 워커의 수명·계층이 다르다.
- [시그널 계약] check_done(list) → main._on_update_check_done,
  upgrade_done(bool,str) → StartupCoordinator.report_upgrade.
- [v3.3.0] 로그는 raw 버스(raw_log.raw) 단일 경유 — line/full 시그널 폐기.
"""
import os
import traceback

import chzzktube.infra.updater as updater
import chzzktube.core.raw_log as raw_log
from chzzktube.core.log_event import LogEvent
from PySide6.QtCore import QThread, Signal
from chzzktube.core.log_emitter import emit_component, emit_error_standard, emit_error_warn

# CLI 원문 캡처 대상 — (label, args). _do_check에서 updater.cli_raw로 실행된다.
_RAW_VERSION_CMDS = (
    ("ytdlp", ("--version",)),
    ("streamlink", ("--version",)),
    ("ffmpeg", ("-version",)),
    ("node", ("--version",)),
    ("npm", ("--version",)),
)


class UpdateWorker(QThread):
    check_done = Signal(list)
    upgrade_done = Signal(bool, str)
    work_tick = Signal()
    deps_failed = Signal(list)

    def __init__(self, parent=None, upgrade=False, stale_updates=None, channel='stable', check_updates=True):
        super().__init__(parent)
        self.upgrade = upgrade
        self.stale_updates = stale_updates or []
        self.channel = channel
        self.check_updates = check_updates
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            if self.upgrade:
                self._do_upgrade(self.stale_updates)
            else:
                self._do_check()
        except Exception as e:
            traceback.print_exc()
            raw_log.raw("deps", LogEvent(stage="DEPS", status="FAIL", scope="DEPS",
                                         msg=f"worker crash: {e}", is_error=True), to_tui=True)
            if self.upgrade:
                self.upgrade_done.emit(False, "worker crash")
            else:
                self.check_done.emit([])

    def _do_check(self):
        stale = []
        results = list(updater.check_deps(
            log_func=lambda m: raw_log.raw(
                "pot-readiness",
                LogEvent(stage="POT", status="RUN", scope="POT", msg=str(m)),
            )
        ))
        for label, status, ver in results:
            raw_log.raw("deps", emit_component("DEPS", status, {"ytdlp": "YTDL", "streamlink": "STRE", "ffmpeg": "FFMP", "node": "NODE", "pot": "POT"}.get(label, label), ver), to_tui=True)
        for label, args in _RAW_VERSION_CMDS:
            cmdline, out = updater.cli_raw(label, *args)
            if cmdline and out:
                raw_log.raw("deps-cli", f"$ {cmdline}")
                for line in updater.truncate_for_full_log(out).splitlines():
                    raw_log.raw("deps-cli", line)
        if self.check_updates:
            for label, pypi_name, cur, latest in updater.outdated_packages(channel=self.channel):
                stale.append((label, pypi_name, cur, latest))
                raw_log.raw("pypi", f"[stale] {label} {cur} -> {latest}")
        else:
            raw_log.raw("pypi", "pypi update check: disabled (auto_update_check=off)")
        self.deps_failed.emit([label for label, status, _ in results if status == "FAIL"])
        self.check_done.emit(stale)

    def _provision_cb(self, msg, is_status=False, is_error=False):
        if isinstance(msg, LogEvent):
            event = msg
            if is_status:
                event.is_status = True
            if is_error:
                event.is_error = True
        else:
            event = LogEvent(
                stage="DEPS",
                status="FAIL" if is_error else ("RUN" if is_status else "OK"),
                scope="DEPS", msg=str(msg),
                is_status=is_status, is_error=is_error,
            )
        show = bool(event.is_status or event.is_error
                    or event.status in ("FAIL", "WARN", "ABORT"))
        self._tick(event)
        raw_log.raw("deps", event, to_tui=show)

    @staticmethod
    def _had_action(tui_line):
        from chzzktube.core.log_event import LogEvent, safe_log_msg
        text = safe_log_msg(tui_line)
        verb = ("downloading", "fetching", "installing", "extracting",
                "reinstalling", "reconfiguring", "brew install")
        return any(v in text.lower() for v in verb)

    def _tick(self, tui_line):
        if self._had_action(tui_line):
            self.work_tick.emit()

    def _do_upgrade(self, stale_updates=None):
        import asyncio
        from chzzktube.infra.provisioning import ProvisioningManager

        mgr = ProvisioningManager(log_func=lambda evt: self._provision_cb(evt,
            is_status=getattr(evt, 'is_status', False),
            is_error=getattr(evt, 'is_error', False)))

        try:
            results = asyncio.run(mgr.ensure_all(stale_only=False, channel=self.channel))
        except Exception as e:
            self.upgrade_done.emit(False, f"provisioning error: {e}")
            return

        ok = [r for r in results if r.success]
        failed = [r for r in results if not r.success]

        if ok:
            raw_log.raw("deps", f"{', '.join(r.component for r in ok)} {'updated' if ok else 'installed'}")
        if failed:
            for r in failed:
                raw_log.raw("deps", emit_error_standard("DEPS", r.component.upper(), r.error or "unknown", "check logs (F12)"), to_tui=True)

        ok_overall = len(failed) == 0
        summary = f"{len(ok)} ok, {len(failed)} failed" if failed else f"{len(ok)} components provisioned"
        self.upgrade_done.emit(ok_overall, summary)
```

## File: chzzktube/control/__init__.py

```python

```

## File: chzzktube/control/controller.py

```python
### controller.py - 다운로드 세션의 상태 머신 및 DownloadWorker 생명주기 관리
import os
import re
import urllib.parse
from dataclasses import dataclass, replace
from typing import Optional

from PySide6.QtCore import QObject, Signal, QThread

from chzzktube.core.dl_platform import _DOMAIN_EXTRACTORS
from chzzktube.workers.analyze_worker import AnalyzeWorker
from chzzktube.workers.downloader import DownloadWorker


# ── [v3.8.0] URL Validation Gate — 순수 함수 (컨트롤러/뷰 공용) ──────────────
# 알려진 도메인 추출기 테이블을 단일 진실 공급원으로 재사용
# (dl_platform._DOMAIN_EXTRACTORS: chzzk/youtube/twitch/instagram 등)
_KNOWN_DOMAINS = tuple(p for p, _ in _DOMAIN_EXTRACTORS)


def _is_valid_url(url) -> bool:
    """입력 문자열이 다운로드 가능한 URL 규격인지 사전 검증 (v3.8.0).

    `afqweqasd` 같은 임의 문자열이 DownloadWorker까지 유입되어
    [generic] Extracting URL → DL FAIL 다중 로그를 남기는 것을 원천 차단.

    규칙:
    - 스킴 필수: http:// 또는 https:// 로 시작
    - 도메인 필수: 파싱 성공 + '.' 포함 + 알려진 도메인 계열(suffix 매치)
    - 실패 예시: 'afqweqasd', 'https://afqweqasd.com'(미지원 도메인)
    - 통과 예시: 'https://youtu.be/xxx', 'https://chzzk.naver.com/...'
    """
    s = str(url or "").strip()
    if not s.startswith(("http://", "https://")):
        return False
    try:
        host = urllib.parse.urlparse(s).netloc.lower()
    except ValueError:
        return False
    if not host or "." not in host:
        return False
    return any(host == d or host.endswith("." + d) for d in _KNOWN_DOMAINS)


@dataclass(frozen=True)
class SessionState:
    """불변 세션 상태 — 스레드 간 안전한 전달을 위해 불변 객체로 관리."""
    running: bool = False
    canceled: bool = False
    skip: bool = False
    analyzing: bool = False
    picking: bool = False  # 포맷 직접 고르기 대기 (UI pick 입력 수신 중)


class MediaController(QObject):
    """다운로드 + 분석 세션의 상태 머신과 생명주기를 통치하는 완벽한 컨트롤러.

    계약:
    *  SessionState 불변 객체로 상태 관리 — 스레드 간 공유 시 replace()로 새 인스턴스 생성
    *  상태 변경은 시그널(canceled_changed, skip_changed, analyzing_changed)로만 전달
    *  워커 → UI 통보는 Qt 시그널(finished_all/result_ready/error_occurred)로만
    *  분석 워커 종료 시 quit() + wait()로 정상 종료 보장 (좀비 패턴 제거) """

    # ── 분석 워커 시그널 포워딩 (View 바인딩용) ──
    # [v3.3.0] 로그는 raw 버스 단일 경유 — analyze_log_full 포워딩 폐기.
    analyze_result_ready = Signal(dict)
    analyze_error_occurred = Signal(str)
    # [Watchdog] 분석 진행 하트비트 포워딩. 뷰가 소유한 분석 워치독 수명을 연장한다.
    analyze_activity = Signal()
    # ── 상태 변경 시그널 (UI 스레드에서만 emit, 워커는 읽기 전용) ──
    canceled_changed = Signal(bool)
    skip_changed = Signal(bool)
    analyzing_changed = Signal(bool)

    def __init__(self, view):
        super().__init__()
        self.view = view
        self._state = SessionState()
        self.worker_dl: Optional[DownloadWorker] = None
        self.worker_analyze: Optional[AnalyzeWorker] = None

    # ── 상태 읽기 전용 프로퍼티 ──
    @property
    def state(self) -> SessionState:
        return self._state

    @property
    def running(self) -> bool:
        return self._state.running

    @property
    def analyzing(self) -> bool:
        return self._state.analyzing

    @property
    def picking(self) -> bool:
        return self._state.picking

    # ── 상태 변경 메서드 (불변 객체 교체 + 시그널 emit) ──
    def _set_running(self, val: bool):
        if self._state.running != val:
            self._state = replace(self._state, running=val)

    def _set_canceled(self, val: bool):
        if self._state.canceled != val:
            self._state = replace(self._state, canceled=val)
            self.canceled_changed.emit(val)

    def _set_skip(self, val: bool):
        if self._state.skip != val:
            self._state = replace(self._state, skip=val)
            self.skip_changed.emit(val)

    def _set_analyzing(self, val: bool):
        if self._state.analyzing != val:
            self._state = replace(self._state, analyzing=val)
            self.analyzing_changed.emit(val)

    def _set_picking(self, val: bool):
        if self._state.picking != val:
            self._state = replace(self._state, picking=val)

    # ── 분석 워커 생명주기 ──
    def spawn_analyzer(self, url, cfg, deep=False):
        """URL 분석 워커 생성 및 관리 (기존 분석 정상 종료 후 교체)."""
        self._terminate_analyzer()

        self._set_analyzing(True)
        self.worker_analyze = AnalyzeWorker(url, cfg, deep=deep)
        # View 시그널로 포워딩 (Controller가 중개)
        self.worker_analyze.result_ready.connect(self.analyze_result_ready)
        self.worker_analyze.error_occurred.connect(self.analyze_error_occurred)
        self.worker_analyze.activity.connect(self.analyze_activity)
        self.worker_analyze.finished.connect(self._on_analyzer_finished)
        self.worker_analyze.start()

    def _terminate_analyzer(self):
        """분석 워커 정상 종료 (quit + wait). QThread 및 mock 모두 대응."""
        w = self.worker_analyze
        if not w:
            return
        if w.isRunning():
            # 시그널 연결 해제
            for sig in (w.result_ready, w.error_occurred, w.activity, w.finished):
                try:
                    sig.disconnect()
                except TypeError:
                    pass
            # 이벤트 루프 종료 요청 후 대기 (QThread 및 mock 대응)
            quit_method = getattr(w, "quit", None)
            if callable(quit_method):
                quit_method()
            wait_method = getattr(w, "wait", None)
            if callable(wait_method):
                if not wait_method(2000):  # 2초 대기
                    terminate_method = getattr(w, "terminate", None)
                    if callable(terminate_method):
                        terminate_method()
                    wait_method(500)
        self.worker_analyze = None
        self._set_analyzing(False)

    def abandon_analysis(self):
        """분석 중단 — 워커 정상 종료."""
        self._terminate_analyzer()

    def _on_analyzer_finished(self):
        """워커 정상 종료 시 호출."""
        self.worker_analyze = None
        self._set_analyzing(False)

    ### ── 순수 로직: 타겟 파싱 ──────────────────────────────────
    @staticmethod
    def parse_targets(raw_text, dedup=False):
        """URL/TXT 입력을 다운로드 타겟 목록으로 파싱.
        *  TXT 파일 경로면 줄 단위로 읽는다 (# 주석 제외). 실패 시 ValueError.
        *  www. 로 시작하는 항목은 https:// 접두사를 보정한다.
        *  watch?v= 단일 영상 주소 뒤 &list= / &index= / &start_radio= 플레이리스트 파라미터를 강제 제거한다.
        *  [v3.8.0] URL 규격 검증 게이트 — 비URL 임의 문자열은 즉시 ValueError.
        *  dedup=True 이면 중복 타겟을 제거한다. """
        targets = []
        if os.path.isfile(raw_text) and raw_text.lower().endswith(".txt"):
            try:
                with open(raw_text, "r", encoding="utf-8") as f:
                    for l in f:
                        t = l.strip()
                        if t and not t.startswith("#"):
                            targets.append(
                                "https://" + t if t.startswith("www.") else t
                            )
            except Exception as e:
                raise ValueError(f"TXT read fail: {e}") from e
        else:
            for l in raw_text.splitlines():
                t = l.strip()
                if t:
                    targets.append("https://" + t if t.startswith("www.") else t)

        # [v3.8.0 게이트] 검증 실패 항목 전수 수집 — 한 줄이라도 비URL이면
        # 전체 배치를 시작하지 않는다 (무검증 억지 다운로드 차단).
        invalid = [t for t in targets if not _is_valid_url(t)]
        if invalid:
            bad = invalid[0][:40] + ("..." if len(invalid[0]) > 40 else "")
            raise ValueError(f"Invalid URL format: {bad}")

        # [핵심] watch?v= 단일 영상 뒤에 붙은 플레이리스트 파라미터 강제 제거!
        cleaned_targets = []
        for u in targets:
            if "watch?v=" in u and "&list=" in u:
                u = re.sub(r"&list=[^&]+", "", u)
                u = re.sub(r"&index=[^&]+", "", u)
                u = re.sub(r"&start_radio=[^&]+", "", u)
            cleaned_targets.append(u)
        targets = cleaned_targets

        if dedup:
            targets = list(dict.fromkeys(targets))
        return targets

    ### ── 세션 상태 머신 ────────────────────────────────────────
    def begin_download(self):
        self.state.update(
            {"running": True, "canceled": False, "skip": False}
        )

    def end_download(self):
        self.state.update(
            {"running": False, "canceled": False, "skip": False}
        )

    def on_download_finished(self, success_count, fail_count):
        """다운로드 완료 후 상태 정리 (View → Controller 이관).

        View는 이 메서드를 호출만 하고, 실제 상태 초기화와 후처리는
        Controller가 담당한다. 사운드 재생/폴더 열기는 UI 전용 로직이므로
        View에서 유지한다.
        """
        self.end_download()

        if success_count > 0:
            # 분석 데이터 초기화 — 다음 URL 입력 시 깨끗한 상태로 시작
            self.view.extracted_data = {"info": None, "v_list": [], "a_list": []}

    def request_cancel(self):
        if self.running:
            self.state["canceled"] = True
        elif self.analyzing:
            self._abandon_analyzer()

    def request_skip(self):
        if self.running:
            self.state["skip"] = True

    ### ── 다운로드 워커 생명주기 ─────────────────────────────────
    def spawn_worker(
        self,
        targets,
        cfg,
        video_id,
        audio_id,
        is_live_hint=False,
        v_spec=None,
        audio_desc="",
        yt_client="auto",
    ):
        """DownloadWorker 생성 + 시그널 연결 + 구동.

        yt_client: 분석 단계에서 실증·통과한 YouTube player_client.
        다운로드가 분석과 같은 클라이언트를 쓰도록 강제 (0% 스톨 방지).
        """
        v = self.view
        w = DownloadWorker(
            targets,
            cfg,
            state_dict=None,  # 새 신호 기반 상태 사용
            v_sel=video_id,
            a_sel=audio_id,
            is_live_hint=is_live_hint,
            v_spec=v_spec,
            audio_desc=audio_desc,
            yt_client=yt_client,
            canceled_signal=self.canceled_changed,
            skip_signal=self.skip_changed,
        )
        w.finished_all.connect(v.on_download_finished)
        self.worker_dl = w
        w.start()

    def begin_download(self):
        self._set_running(True)
        self._set_canceled(False)
        self._set_skip(False)

    def end_download(self):
        self._set_running(False)
        self._set_canceled(False)
        self._set_skip(False)

    def on_download_finished(self, success_count, fail_count):
        """다운로드 완료 후 상태 정리 (View → Controller 이관)."""
        self.end_download()

        if success_count > 0:
            # 분석 데이터 초기화 — 다음 URL 입력 시 깨끗한 상태로 시작
            self.view.extracted_data = {"info": None, "v_list": [], "a_list": []}

    def request_cancel(self):
        if self.running:
            self._set_canceled(True)
        elif self.analyzing:
            self._terminate_analyzer()

    def request_skip(self):
        if self.running:
            self._set_skip(True)

    def shutdown(self, wait_ms=1000):
        """앱 종료 시 활성 스레드 안전 중단 (closeEvent용)."""
        if self.worker_dl and self.worker_dl.isRunning():
            self._set_canceled(True)
            self.worker_dl.wait(wait_ms)

        # POT 서버 워커 정리는 POTManager.cancel()이 담당 (MainWindow.closeEvent에서 호출)


# ── 하위 호환성 유지 (기존 코드에서 DownloadController로 참조 가능) ──
DownloadController = MediaController

```

## File: chzzktube/control/pot_manager.py

```python
# POTManager
from PySide6.QtCore import QObject, QThread, QTimer, Signal
import threading
import subprocess
import os
from chzzktube.core.log_event import LogEvent
import chzzktube.core.raw_log as raw_log
from chzzktube.core.log_emitter import emit_error_standard, emit_error_warn


class _POTWorker(QThread):
    # [v3.3.0] 로그는 raw 버스 단일 경유 — log_full 시그널 폐기.
    finished_signal = Signal(bool, str)
    # [Followup-1] 빌드 수급 진행 하트비트 — 문자열 없는 무페이로드 신호.
    # MainWindow가 기동 폴백 타이머 연장(defer_fallback_timer)에 사용한다.
    heartbeat = Signal()
    
    def __init__(self, parent=None, mode="prewarm"):
        super().__init__()
        self.mode = mode
        self._abort = False
        self._child_procs = []
        self._server_proc = None
        self.outcome = (False, "")
    
    def request_interruption(self):
        self._abort = True
        # [Followup-2] 자식 트리를 통째로 정리한다 — 종전 loop는 _child_procs가
        # 항상 빈 목록이라(append 0건) 아무것도 죽이지 못했다.
        from chzzktube.infra.pot_server import kill_tree
        for proc in list(self._child_procs):
            kill_tree(proc)
    
    def _tick(self):
        """[Followup-1] 빌드 수급 진행 하트비트 — 폴백 타이머 연장용 무페이로드 신호."""
        self.heartbeat.emit()

    def run(self):
        try:
            self._run()
        except Exception as e:
            self.outcome = (False, f"crash: {e}")
        finally:
            self._cleanup()
            self.finished_signal.emit(self.outcome[0], self.outcome[1])
    
    def _cleanup(self):
        # [Followup-2] 자식 트리도 kill_tree로 정리 — 고아 프로세스 잔존 방지.
        from chzzktube.infra.pot_server import kill_tree
        for proc in list(self._child_procs):
            kill_tree(proc)
        self._child_procs.clear()
        if self._server_proc:
            try:
                kill_tree(self._server_proc)
            except Exception:
                pass
            self._server_proc = None
    
    def _note(self, msg, is_status=False, is_error=False):
        """raw 버스 단일 경유 — 라벨링은 근원에서 LogEvent로 동봉.

        [채널 분기 — 발행자 결정]
        - prewarm 모드: to_tui=False → F12+history 전용 (TUI 오염 방지)
        - gate 모드: to_tui=True → TUI + F12 + history 전부 기록
        """
        if self.mode == "prewarm":
            raw_log.raw("POT", str(msg), is_status=is_status, is_error=is_error)
            return
        stage = "SYS" if is_error else "POT"
        status = "FAIL" if is_error else ("RUN" if is_status else "OK")
        event = LogEvent(stage=stage, status=status, scope="POT",
                         msg=str(msg),
                         is_status=is_status, is_error=is_error)
        raw_log.raw("POT", event, to_tui=True)

    def _dbg(self, msg):
        """raw 버스 단일 경유 — 직접 log_full.emit 금지 (F12 이중 적재 방지).

        [채널 분기 — 발행자 결정]
        - prewarm 모드: to_tui=False → F12+history 전용
        - gate 모드: to_tui=True → TUI + F12 + history 전부 기록
        """
        if self.mode == "prewarm":
            raw_log.raw("POT-DEBUG", str(msg))
        else:
            event = LogEvent(stage="POT", status="RUN", scope="POT",
                             msg=str(msg))
            raw_log.raw("POT", event, to_tui=True)
    
    def _run(self):
        from chzzktube.infra.pot_server import probe_server, latest_server_ver, server_installed_ver
        from chzzktube.infra.pot_server import built_server_js, DEFAULT_HOST, DEFAULT_PORT
        self._dbg(f"POTWorker starting (mode={self.mode})")
        if self.mode == "gate":
            try:
                import chzzktube.infra.components as components
                self._dbg("entering ffmpeg ensure phase")
                ff_err = components.ensure_ffmpeg(self._note)
                if ff_err:
                    # [v3.8.1] 표준 에러 헬퍼로 변환
                    if "binary incompatible" in ff_err.lower() or "not runnable" in ff_err.lower():
                        cause = "binary incompatible"
                        action = "retry mirror (1/3)"
                    elif "all mirrors exhausted" in ff_err.lower():
                        cause = "all mirrors exhausted"
                        action = "check network (F12)"
                    elif "checksum mismatch" in ff_err.lower() or "hash mismatch" in ff_err.lower():
                        cause = "checksum mismatch"
                        action = "retry mirror (1/3)"
                    elif "network" in ff_err.lower() or "timeout" in ff_err.lower() or "connection" in ff_err.lower():
                        cause = "network error"
                        action = "check network (F12)"
                    else:
                        cause = "setup failed"
                        action = "check logs (F12)"
                    self._note(emit_error_standard("DEPS", "FFMP", cause, action), False, True)
                else:
                    self._dbg("ffmpeg fetch done")
            except Exception as ff_ex:
                self._note(emit_error_standard("DEPS", "FFMP", "setup failed", "check logs (F12)", is_error=True), False, True)
        else:
            self._dbg("ffmpeg ensure skipped (prewarm)")
        try:
            from chzzktube.infra.pot_server import clean_stale_plugin
            if clean_stale_plugin():
                self._dbg("stale removed")
        except Exception as cp_ex:
            self._dbg(f"cleanup failed: {cp_ex}")
        self._note("probing server...", True)
        state, detail = probe_server()
        self._dbg(f"probe: state={state!r}")
        if state == "ok":
            self.outcome = (True, f"pot server bound ({DEFAULT_HOST}:{DEFAULT_PORT})")
            return
        remote = latest_server_ver()
        local = server_installed_ver()
        if self.mode == "prewarm":
            self._dbg("prewarm mode — staging to disk, no spawn")
            from chzzktube.infra.pot_server import acquire_prewarm_lock, release_prewarm_lock
            fd = acquire_prewarm_lock(timeout=0, log_func=self._dbg)
            if fd is None:
                self.outcome = (False, "prewarm skipped — build busy")
                return
            try:
                self._note("pot prewarm staging...", True)
                from chzzktube.infra.pot_server import ensure_node_server, server_home, _SERVER_FALLBACK_VER
                ver = remote or local or _SERVER_FALLBACK_VER
                # [A3 수리] "빌드 존재=재빌드" 반전 로직 교정 — 기존 rebuild=have_build는
                # 매 기동마다 npm ci+tsc를 강제했다(HANDOVER §1.3 경량 prewarm 위반).
                # remote·local 버전이 실제 어긋난 스테일일 때만 재빌드한다.
                stale = bool(remote and local and remote != local)
                _, err = ensure_node_server(
                    self._note, self._dbg, ver, rebuild=stale,
                    tick_func=self._tick, proc_registry=self._child_procs,
                )
                if err is None and built_server_js():
                    self.outcome = (True, "prewarm staged")
                else:
                    # [v3.8.1] 표준 에러 헬퍼로 변환
                    if "binary incompatible" in err.lower() or "not runnable" in err.lower():
                        cause = "binary incompatible"
                        action = "retry mirror (1/3)"
                    elif "all mirrors exhausted" in err.lower():
                        cause = "all mirrors exhausted"
                        action = "check network (F12)"
                    elif "checksum mismatch" in err.lower() or "hash mismatch" in err.lower():
                        cause = "checksum mismatch"
                        action = "retry mirror (1/3)"
                    elif "network" in err.lower() or "timeout" in err.lower() or "connection" in err.lower():
                        cause = "network error"
                        action = "check network (F12)"
                    else:
                        cause = "setup failed"
                        action = "check logs (F12)"
                    self._note(emit_error_standard("DEPS", "FFMP", cause, action), is_status=False, is_error=True)
                    self.outcome = (False, f"prewarm fail: {err}")
            finally:
                release_prewarm_lock(fd, log_func=self._dbg)
            return
        if built_server_js():
            self._note("pot server starting...", True)
            from chzzktube.infra.pot_server import _spawn_existing
            proc = _spawn_existing(self._dbg)
            if proc is not None:
                self._server_proc = proc
                self.outcome = (True, f"pot server bound ({DEFAULT_HOST}:{DEFAULT_PORT})")
                return
        # [v3.8.1] 표준 에러 헬퍼로 변환
        self._note(emit_error_standard("DEPS", "FFMP", "bind fail", "check logs (F12)"), is_status=False, is_error=True)
        self.outcome = (False, "bind fail — age-only")
    
    def terminate(self):
        self.request_interruption()
        super().terminate()

class POTManager(QObject):
    # [v3.3.0] 로그는 raw 버스 단일 경유 — log_full 릴레이 시그널 폐기.
    pot_status_changed = Signal(str)
    pot_finished = Signal(bool, str)
    # [Followup-1] 빌드 수급 진행 하트비트 릴레이 — 문자열 없는 무페이로드 신호.
    pot_work_tick = Signal()

    def __init__(self):
        super().__init__()
        self._worker = None
        self._mode = "idle"
        self._pending_gate = False
        self._lock = threading.Lock()
        # [수명 보증] finished_signal(큐잉)은 run()이 아직 반환 전에 도착할 수
        # 있다. 이 시점에 마지막 참조를 끊으면 워커 스레드 자신이 QThread 객체를
        # 파괴하며 Qt qFatal("QThread: Destroyed while thread is still running")
        # → SIGABRT 크래시가 발생한다(2026-09-15 실측). run()이 완전히 반환된
        # 뒤(Qt 내장 finished 발화)까지 참조를 보관하는 대피소.
        self._retiring: list = []

    def _retire(self, worker) -> None:
        """워커를 finished(run() 완전 반환)까지 보관 후 deleteLater로 정리.

        Qt 시그널이 없는 테스트 더블(SimpleNamespace 등)은 보관 대상에서
        제외한다 — 실제 QThread만 수명 보증 대상이다.
        """
        if worker is None:
            return
        is_finished = getattr(worker, "isFinished", None)
        if callable(is_finished) and is_finished():
            return
        finished = getattr(worker, "finished", None)
        if finished is None:
            return
        finished.connect(worker.deleteLater)
        finished.connect(lambda w=worker: self._drop_retired(w))
        self._retiring.append(worker)

    def _drop_retired(self, worker) -> None:
        try:
            self._retiring.remove(worker)
        except ValueError:
            pass

    def ensure_ready(self, mode="gate"):
        if mode not in {"prewarm", "gate"}:
            raise ValueError(f"unknown POT mode: {mode}")
        with self._lock:
            worker = self._worker
            if worker is not None and worker.isRunning():
                if mode == "gate" and self._mode == "prewarm":
                    self._pending_gate = True
                return
            self._start_worker_locked(mode)

    def _start_worker_locked(self, mode: str) -> None:
        self._mode = mode
        worker = _POTWorker(mode=mode)
        self._worker = worker
        worker.finished_signal.connect(self._on_worker_finished)
        # [Followup-1] 빌드 수급 하트비트를 View로 릴레이 — 폴백 타이머 연장에 사용
        worker.heartbeat.connect(self.pot_work_tick)
        worker.start()
        # [모드별 토큰] gate="starting" / prewarm="prewarm" — Coordinator가
        # 이 토큰을 raw 버스에 로그로 남긴다 (의미 왜곡 방지).
        self.pot_status_changed.emit("starting" if mode == "gate" else "prewarm")

    def _on_worker_finished(self, ok: bool, msg: str):
        # Qt may deliver this callback after cancel(); ignore stale workers.
        with self._lock:
            worker = self._worker
            mode = self._mode
            if worker is None or worker is not self._worker:
                return
            if mode == "prewarm":
                if ok and self._pending_gate:
                    self._pending_gate = False
                    self._worker = None
                    self._mode = "staged"
                    self._retire(worker)  # [수명 보증] 조기 반환 경로도 동일
                    QTimer.singleShot(0, self._start_pending_gate)
                    return
                self._worker = None
                self._mode = "staged" if ok else "failed"
            elif mode == "gate":
                self._worker = None
                self._mode = "ready" if ok else "failed"
            else:
                return

        # [토큰 정합] 상태 토큰은 실제 _mode("staged"/"ready")를 그대로 emit —
        # gate 성공을 "staged"로 잘못 보고하던 잠재 버그 수리.
        self.pot_status_changed.emit(self._mode if ok else "failed")
        # [수명 보증] 참조 해제는 run() 완전 반환 이후로 연기 — 워커 스레드가
        # 자기 자신을 파괴하는 SIGABRT 방지.
        self._retire(worker)
        # [READY 게이트 계약] pot_finished의 msg는 상태 토큰("staged"/"ready"/"failed")으로만
        # 발행한다 — StartupCoordinator.report_pot이 정확 일치로 READY를 판정한다.
        # 사람이 읽는 상세 메시지("prewarm staged", "pot server bound ...")는
        # 워커가 이미 로그 버스로 남겼으므로 여기서 중복 전달하지 않는다.
        self.pot_finished.emit(ok, self._mode if ok else "failed")

    def _start_pending_gate(self):
        """완료된 prewarm 워커의 Signal 처리 후 gate 워커를 시작한다."""
        with self._lock:
            if self._mode != "staged" or self._worker is not None:
                return
            self._start_worker_locked("gate")

    @property
    def mode(self):
        return self._mode

    def is_ready(self):
        with self._lock:
            return self._mode == "ready" and self._worker is None

    def use_existing(self):
        """외부/기존 POT 서버가 이미 /ping에 응답 중일 때 ready 상태로 승격.

        이 경로로는 gate 워커가 스폰되지 않으므로 pot_finished가 발행되지
        않는다 — _pending_download가 영구 큐잉되는 것을 막기 위해 즉시 ready로
        표시해야 한다 (Main._wait_pot_if_needed → toggle_download가 확인).
        """
        with self._lock:
            self._worker = None
            self._mode = "ready"

    def is_busy(self):
        return self._worker is not None and self._worker.isRunning()

    def cancel(self):
        with self._lock:
            worker = self._worker
            self._worker = None
            self._mode = "idle"
        if worker and worker.isRunning():
            worker.request_interruption()
            if not worker.wait(2000):
                worker.terminate()
                worker.wait(1000)
        # [수명 보증] wait 타임아웃으로 스레드가 살아있을 수 있다 — 종료 보장 후 해제
        self._retire(worker)
```

## File: chzzktube/control/startup_coordinator.py

```python
"""시작 시퀀스 단일 책임자 — Signal 경유, POTManager + raw 버스 연동."""

from __future__ import annotations

import threading
from PySide6.QtCore import QObject, Signal

from chzzktube.control.startup_state import StartupState
from chzzktube.control.pot_manager import POTManager
from chzzktube.core.log_emitter import emit_error_standard, emit_error_warn


class StartupCoordinator(QObject):
    """기동 시퀀스 게이트.

    [Signal 기반]
    - Worker → Coordinator: report_*() (thread-safe)
    - Coordinator → View: ready_emitted / pot_status_changed / ui_unlocked (Qt Signal)
    - Coordinator → raw 버스: raw() (TUI=to_tui + F12 + history 전량)

    [구성 요소]
    - StartupState: 단일 상태 (thread-safe)
    - POTManager: POT 서버 수명주기 (prewarm + gate)
    - raw_log: 로그 라우팅 (라벨링은 여기서 LogEvent로 동봉)
    """

    # ── View로의 Signal ──────────────────────────────────────
    ready_emitted = Signal(str, bool, str)  # (stage, is_status, msg)
    pot_status_changed = Signal(str)
    ui_unlocked = Signal()

    def __init__(self, pot_manager: POTManager, parent=None):
        super().__init__()
        self._pot = pot_manager
        self._state = StartupState()
        self._lock = threading.RLock()

        # POTManager 시그널 연결
        self._pot.pot_status_changed.connect(self._on_pot_status)
        self._pot.pot_finished.connect(self._on_pot_finished)

    # ── 버스 발행 (근원 라벨링 단일 경유) ─────────────────────

    def _emit(self, stage, status, msg, is_status=False, is_error=False):
        """READY/READY 경고 등 기동 라인을 LogEvent로 동봉해 버스로 발행."""
        import chzzktube.core.raw_log as raw_log
        from chzzktube.core.log_event import LogEvent
        raw_log.raw(
            "startup",
            LogEvent(stage=stage, status=status, scope="MAIN", msg=msg,
                     is_status=is_status, is_error=is_error),
            to_tui=True,
        )

    # ── Worker → Coordinator 보고 ────────────────────────────

    # ── Worker → Coordinator 보고 ────────────────────────────

    def report_deps(self, ok: bool, msg: str = ""):
        with self._lock:
            # [v3.8.1] deps 실패 시 영구 실패 고정 — 한 번 실패면 끝 (최소값 원칙)
            if not ok and not self._state.deps_error_msg:
                self._state.deps_error_msg = msg
                self._state.deps_ok = False
            elif ok and not self._state.deps_error_msg:
                # 실패 기록이 없을 때만 성공으로 갱신
                self._state.deps_ok = True
            self._try_emit_ready()

    def report_upgrade(self, ok: bool, summary: str):
        with self._lock:
            self._state.set_upgrade(True)
            if summary:
                if ok:
                    self._emit("SYS", "OK", f"update {summary}")
                else:
                    # [v3.8.1] 업그레이드 실패 시 표준 에러 헬퍼 사용
                    from chzzktube.core.log_emitter import emit_error_standard
                    raw_log.raw(
                        "startup",
                        emit_error_standard("SYS", "MAIN", "update failed", "check logs (F12)"),
                        to_tui=True,
                    )
            self._try_emit_ready()

    def report_pot(self, ok: bool, msg: str):
        with self._lock:
            status = msg if ok else "failed"
            # [v3.8.1] staged ≠ ready — gate 완료(ready)만 pot_ready=True
            # staged = prewarm 완료, gate 미시작 상태이므로 토큰 서빙 불가
            ready = ok and status == "ready"
            self._state.set_pot(status, ready=ready)
            if not ok:
                # [v3.8.1] POT 실패 시 표준 에러 헬퍼 사용
                from chzzktube.core.log_emitter import emit_error_standard
                raw_log.raw(
                    "startup",
                    emit_error_standard("SYS", "POT", "server failed", "check logs (F12)"),
                    to_tui=True,
                )
            self._try_emit_ready()

    def report_ready(self, ok: bool = True, msg: str = "ready — input unlocked"):
        with self._lock:
            if self._state.ready_emitted:
                return
            self._state.mark_ready_emitted()
            self._emit("SYS", "READY" if ok else "WARN", msg)
            self.ready_emitted.emit("SYS", False, msg)
            self.ui_unlocked.emit()

    # ── POTManager 시그널 핸들러 ──────────────────────────────

    def _on_pot_status(self, status: str):
        # View로만 포워드하던 것을 raw 버스에도 태워 TUI/F12/history에 남긴다.
        # [토글 계약] 시동 → 가동 → lazy 대기 전환이 메인/풀 로그에 모두 기록된다
        # (앱 동작 전량 기록 원칙 — HANDOVER §9).
        self.pot_status_changed.emit(status)
        from chzzktube.core.raw_log import raw
        from chzzktube.core.log_emitter import emit_event
        _POT_TOGGLE = {
            "prewarm":  ("RUN",  "server staging..."),
            "starting": ("RUN",  "server starting..."),
            "staged":   ("OK",   "server staged — lazy standby"),
            "ready":    ("OK",   "server running"),
            "failed":   ("FAIL", "server failed"),
        }
        st, msg = _POT_TOGGLE.get(status, ("RUN", str(status)))
        raw(
            "startup",
            emit_event("POT", st, "POT", msg, is_error=(st == "FAIL")),
            to_tui=True,
        )

    def _on_pot_finished(self, ok: bool, msg: str):
        self.report_pot(ok, msg)

    # ── READY 발산 게이트 ────────────────────────────────────

    def _try_emit_ready(self):
        with self._lock:
            if self._state.can_emit_ready():
                self._state.mark_ready_emitted()
                self._emit("SYS", "READY", "ready — input unlocked")
                self.ready_emitted.emit("SYS", False, "ready — input unlocked")
                self.ui_unlocked.emit()

    # ── 테스트 호환 프로퍼티 ──────────────────────────────────

    @property
    def _ready_emitted(self):
        return self._state.ready_emitted

    @_ready_emitted.setter
    def _ready_emitted(self, value):
        self._state.ready_emitted = value
```

## File: chzzktube/control/startup_state.py

```python
"""startup_state.py — 앱 시작 시퀀스 상태 단일 공급원 (SRP: 상태만 관리)

[구조] StartupCoordinator, POTManager, MainWindow가 공유하는 불변 상태 컨테이너.
스레드 안전성을 위해 RLock으로 보호하며, 상태 전이 메서드만 제공.
단계별 순차 비교(phase.value >) 대신 플래그 조합으로 동시성 안전성 확보.
"""
import threading
from dataclasses import dataclass, field


@dataclass(slots=True)
class StartupState:
    """앱 시작 시퀀스 상태 단일 공급원."""
    
    # 단계별 완료 플래그
    deps_ok: bool = False
    upgrade_done: bool = False
    pot_status: str = "unknown"   # unknown/running/standby/staged/failed
    pot_ready: bool = False
    ready_emitted: bool = False
    # [v3.8.1] deps 수급 실패 시 원본 에러 메시지 보관 — 폴백 제거로 에러 상태 영구 보관
    deps_error_msg: str = ""
    
    # 내부 동기화
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    # ── 상태 변경 메서드 (RLock 보호) ──────────────────────────
    
    def set_deps(self, ok: bool) -> None:
        with self._lock:
            self.deps_ok = ok

    def set_upgrade(self, done: bool) -> None:
        with self._lock:
            self.upgrade_done = done

    def set_pot(self, status: str, ready: bool | None = None) -> None:
        with self._lock:
            self.pot_status = status
            if ready is not None:
                self.pot_ready = ready

    def mark_ready_emitted(self) -> None:
        with self._lock:
            self.ready_emitted = True

    # ── 판정 메서드 ────────────────────────────────────────
    
    def can_emit_ready(self) -> bool:
        """READY 발산 조건 충족 여부."""
        with self._lock:
            return (
                self.deps_ok
                and self.upgrade_done
                and self.pot_ready
                and not self.ready_emitted
                and not self.deps_error_msg  # [v3.8.1] deps 에러 있으면 READY 차단
            )

    def is_ready(self) -> bool:
        with self._lock:
            return self.ready_emitted

    def snapshot(self) -> dict:
        """디버깅용 상태 스냅샷."""
        with self._lock:
            return {
                "deps_ok": self.deps_ok,
                "upgrade_done": self.upgrade_done,
                "pot_status": self.pot_status,
                "pot_ready": self.pot_ready,
                "ready_emitted": self.ready_emitted,
                "deps_error_msg": self.deps_error_msg,
            }
```

## File: .skills/understand-anything/understand-knowledge/merge-knowledge-graph.py

```python
#!/usr/bin/env python3
"""
Merge script for Karpathy-pattern knowledge graphs.

Combines the deterministic scan-manifest.json with LLM analysis batches
(analysis-batch-*.json) into a final assembled knowledge graph.

Handles: entity deduplication, edge normalization, layer building from
index.md categories, tour generation from index.md section ordering.

Usage:
    python merge-knowledge-graph.py <wiki-directory>

Output:
    Writes assembled-graph.json to <wiki-directory>/<ua-dir>/intermediate/, where
    <ua-dir> is `.ua/` (or legacy `.understand-anything/` when that directory
    already exists).
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


def resolve_ua_dir(root: Path) -> Path:
    """Mirror core resolveUaDir: legacy .understand-anything/ wins if present."""
    legacy = root / ".understand-anything"
    return legacy if legacy.is_dir() else root / ".ua"


def _find_markdown_case_insensitive(parent: Path, name: str) -> Path:
    """Resolve a known markdown filename case-insensitively within one directory.

    Mirrors find_markdown_case_insensitive in parse-knowledge-base.py (the
    scripts are standalone, so the helper is duplicated): an exact match
    always wins; otherwise the first case-insensitive sibling is returned.
    """
    candidate = parent / name
    if candidate.is_file():
        return candidate
    if not parent.is_dir():
        return candidate
    wanted = name.lower()
    for child in sorted(parent.iterdir()):
        if child.is_file() and child.name.lower() == wanted:
            return child
    return candidate


# ---------------------------------------------------------------------------
# Canonical type sets (must match core/src/types.ts)
# ---------------------------------------------------------------------------

VALID_NODE_TYPES = {
    "article", "entity", "topic", "claim", "source",
    # Codebase types (for cross-compatibility)
    "file", "function", "class", "module", "concept",
    "config", "document", "service", "table", "endpoint",
    "pipeline", "schema", "resource", "domain", "flow", "step",
}

VALID_EDGE_TYPES = {
    "cites", "contradicts", "builds_on", "exemplifies",
    "categorized_under", "authored_by", "related", "similar_to",
    # Codebase types
    "imports", "exports", "contains", "inherits", "implements",
    "calls", "subscribes", "publishes", "middleware",
    "reads_from", "writes_to", "transforms", "validates",
    "depends_on", "tested_by", "configures",
    "deploys", "serves", "provisions", "triggers",
    "migrates", "documents", "routes", "defines_schema",
    "contains_flow", "flow_step", "cross_domain",
}

NODE_TYPE_ALIASES = {
    "note": "article", "page": "article", "wiki_page": "article",
    "person": "entity", "actor": "entity", "organization": "entity",
    "tag": "topic", "category": "topic", "theme": "topic",
    "assertion": "claim", "decision": "claim", "thesis": "claim",
    "reference": "source", "raw": "source", "paper": "source",
}

EDGE_TYPE_ALIASES = {
    "references": "cites", "cites_source": "cites",
    "conflicts_with": "contradicts", "disagrees_with": "contradicts",
    "refines": "builds_on", "elaborates": "builds_on",
    "illustrates": "exemplifies", "instance_of": "exemplifies", "example_of": "exemplifies",
    "belongs_to": "categorized_under", "tagged_with": "categorized_under",
    "written_by": "authored_by", "created_by": "authored_by",
    "relates_to": "related", "related_to": "related",
}


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

def normalize_node_type(t: str) -> str:
    t = t.lower().strip()
    return NODE_TYPE_ALIASES.get(t, t)


def normalize_edge_type(t: str) -> str:
    t = t.lower().strip()
    return EDGE_TYPE_ALIASES.get(t, t)


def normalize_entity_name(name: str) -> str:
    """Normalize entity names for deduplication."""
    return re.sub(r'\s+', ' ', name.strip().lower())


# ---------------------------------------------------------------------------
# Merge pipeline
# ---------------------------------------------------------------------------

def merge(root: Path) -> dict:
    intermediate = resolve_ua_dir(root) / "intermediate"
    manifest_path = intermediate / "scan-manifest.json"

    if not manifest_path.is_file():
        print(f"Error: {manifest_path} not found. Run parse-knowledge-base.py first.",
              file=sys.stderr)
        sys.exit(1)

    # Load scan manifest (deterministic base)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    nodes = {n["id"]: n for n in manifest["nodes"]}
    edges = list(manifest["edges"])

    report = {"base_nodes": len(nodes), "base_edges": len(edges),
              "batches": 0, "new_entities": 0, "new_claims": 0,
              "new_edges": 0, "deduped_entities": 0, "dropped_edges": 0}

    # Load analysis batches
    batch_files = sorted(intermediate.glob("analysis-batch-*.json"))
    entity_name_map: dict[str, str] = {}  # normalized_name → entity_id
    dedup_remap: dict[str, str] = {}  # duplicate_id → canonical_id

    for bf in batch_files:
        report["batches"] += 1
        try:
            batch = json.loads(bf.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            print(f"[merge] Warning: Failed to load {bf.name}: {e}", file=sys.stderr)
            continue

        # Process new nodes from LLM analysis
        for node in batch.get("nodes", []):
            node_type = normalize_node_type(node.get("type", ""))
            if node_type not in VALID_NODE_TYPES:
                print(f"[merge] Warning: Unknown node type '{node.get('type')}' — skipping",
                      file=sys.stderr)
                continue

            node["type"] = node_type
            node_id = node.get("id", "")

            # Entity deduplication — track remapping for edge fixup
            if node_type == "entity":
                norm_name = normalize_entity_name(node.get("name", ""))
                if norm_name in entity_name_map:
                    # Map duplicate ID → canonical ID for edge remapping
                    dedup_remap[node_id] = entity_name_map[norm_name]
                    report["deduped_entities"] += 1
                    continue
                entity_name_map[norm_name] = node_id
                report["new_entities"] += 1
            elif node_type == "claim":
                report["new_claims"] += 1

            # Ensure required fields
            node.setdefault("summary", node.get("name", ""))
            node.setdefault("tags", [])
            node.setdefault("complexity", "simple")

            nodes[node_id] = node

        # Process new edges from LLM analysis
        for edge in batch.get("edges", []):
            edge_type = normalize_edge_type(edge.get("type", ""))
            if edge_type not in VALID_EDGE_TYPES:
                print(f"[merge] Warning: Unknown edge type '{edge.get('type')}' — "
                      f"mapped to 'related'", file=sys.stderr)
                edge_type = "related"

            edge["type"] = edge_type
            edge.setdefault("direction", "forward")
            edge.setdefault("weight", 0.5)

            # Remap deduped entity IDs, then validate source/target exist
            src = dedup_remap.get(edge.get("source", ""), edge.get("source", ""))
            tgt = dedup_remap.get(edge.get("target", ""), edge.get("target", ""))
            edge["source"] = src
            edge["target"] = tgt
            if src in nodes and tgt in nodes:
                edges.append(edge)
                report["new_edges"] += 1
            else:
                report["dropped_edges"] += 1

    # --- Deduplicate edges ---
    seen: set[tuple[str, str, str]] = set()
    final_edges = []
    for edge in edges:
        key = (edge["source"], edge["target"], edge["type"])
        if key not in seen:
            seen.add(key)
            final_edges.append(edge)

    # --- Build article→layer map from categories ---
    categories = manifest.get("categories", [])
    article_layer_map: dict[str, str] = {}  # article_id → layer_id
    layer_members: dict[str, list[str]] = {}  # layer_id → [node_ids]

    for cat in categories:
        cat_name = cat["name"]
        cat_slug = cat_name.lower().replace(" ", "-")
        layer_id = f"layer:{cat_slug}"
        topic_id = f"topic:{cat_slug}"
        members = [e["source"] for e in final_edges
                   if e["type"] == "categorized_under" and e["target"] == topic_id]
        if topic_id in nodes:
            members.append(topic_id)
        layer_members[layer_id] = members
        for mid in members:
            article_layer_map[mid] = layer_id

    # --- Assign entity/claim nodes to their parent article's layer ---
    # Step 1: Build entity/claim → article mapping from edges
    child_to_article: dict[str, str] = {}
    for edge in final_edges:
        src_type = nodes.get(edge["source"], {}).get("type", "")
        tgt_type = nodes.get(edge["target"], {}).get("type", "")
        # If an article connects to an entity/claim, map the child to the article
        if src_type == "article" and tgt_type in ("entity", "claim"):
            child_to_article.setdefault(edge["target"], edge["source"])
        elif tgt_type == "article" and src_type in ("entity", "claim"):
            child_to_article.setdefault(edge["source"], edge["target"])

    # Step 2: For orphan entities/claims, try to match by ID prefix
    # Build a reverse lookup: bare article name → full article ID
    # e.g., "concept-aaak-compression" → "article:concepts/concept-aaak-compression"
    bare_to_article: dict[str, str] = {}
    for nid in nodes:
        if nid.startswith("article:"):
            # Extract the bare filename from paths like "article:concepts/concept-foo"
            bare = nid.split("/")[-1] if "/" in nid else nid.replace("article:", "")
            bare_to_article[bare] = nid

    for nid, node in nodes.items():
        if node["type"] in ("entity", "claim") and nid not in child_to_article:
            # e.g., "claim:concept-aaak-compression:not-zero-loss" → stem "concept-aaak-compression"
            # e.g., "entity:brain" → stem "brain"
            raw = nid.split(":", 1)[1] if ":" in nid else nid  # "concept-aaak-compression:not-zero-loss"
            stem = raw.split(":")[0]  # "concept-aaak-compression"

            # Try exact bare name match first
            if stem in bare_to_article:
                child_to_article[nid] = bare_to_article[stem]
            else:
                # Try suffix/substring match against bare names
                # e.g., entity:brain → segment-brain, entity:mempalace → tool-mempalace
                matched = False
                for bare, aid in bare_to_article.items():
                    if stem in bare or bare in stem:
                        child_to_article[nid] = aid
                        matched = True
                        break
                    # Also try: bare ends with -stem (e.g., "segment-brain" ends with "-brain")
                    if bare.endswith(f"-{stem}") or bare.endswith(f"/{stem}"):
                        child_to_article[nid] = aid
                        matched = True
                        break
                # Last resort: check if the node's name appears in any article's
                # name OR content (knowledgeMeta.content)
                if not matched and node.get("name"):
                    node_name_lower = node["name"].lower()
                    for aid, anode in nodes.items():
                        if not aid.startswith("article:"):
                            continue
                        # Match against article name
                        if node_name_lower in anode.get("name", "").lower():
                            child_to_article[nid] = aid
                            matched = True
                            break
                        # Match against article content (wikilinks or text)
                        meta = anode.get("knowledgeMeta", {})
                        content = (meta.get("content") or "").lower()
                        if len(node_name_lower) >= 3 and node_name_lower in content:
                            child_to_article[nid] = aid
                            matched = True
                            break

    # Step 3: Place children into their parent article's layer
    for child_id, article_id in child_to_article.items():
        layer_id = article_layer_map.get(article_id)
        if layer_id and layer_id in layer_members:
            layer_members[layer_id].append(child_id)
            article_layer_map[child_id] = layer_id

    # --- Build layers ---
    layers = []
    for cat in categories:
        cat_name = cat["name"]
        cat_slug = cat_name.lower().replace(" ", "-")
        layer_id = f"layer:{cat_slug}"
        members = list(dict.fromkeys(layer_members.get(layer_id, [])))  # Deduplicate preserving order
        layers.append({
            "id": layer_id,
            "name": cat_name,
            "description": f"{cat_name} ({len(members)} nodes)",
            "nodeIds": members,
        })

    # Assign uncategorized nodes to an "Other" layer
    categorized_ids = set()
    for layer in layers:
        categorized_ids.update(layer["nodeIds"])
    uncategorized = [nid for nid in nodes if nid not in categorized_ids]
    if uncategorized:
        layers.append({
            "id": "layer:other",
            "name": "Other",
            "description": f"Uncategorized nodes ({len(uncategorized)})",
            "nodeIds": uncategorized,
        })

    # --- Build tour from index.md category ordering ---
    tour = []
    for i, cat in enumerate(categories):
        cat_slug = cat["name"].lower().replace(" ", "-")
        topic_id = f"topic:{cat_slug}"
        # Pick representative articles (up to 3 per category)
        members = [e["source"] for e in final_edges
                   if e["type"] == "categorized_under" and e["target"] == topic_id][:3]
        if not members and topic_id in nodes:
            members = [topic_id]
        if members:
            tour.append({
                "order": i + 1,
                "title": cat["name"],
                "description": f"Explore the {cat['name']} section ({cat['count']} articles)",
                "nodeIds": members,
            })

    # --- Detect project name ---
    project_name = root.name
    # Try to find a better name from index.md H1 (case-insensitively —
    # Index.md is a reasonable convention; exact lowercase wins if both exist)
    index_path = _find_markdown_case_insensitive(root / "wiki", "index.md")
    if not index_path.is_file():
        index_path = _find_markdown_case_insensitive(root, "index.md")
    if index_path.is_file():
        text = index_path.read_text(encoding="utf-8", errors="replace")
        h1_match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
        if h1_match:
            project_name = h1_match.group(1).strip()

    # --- Assemble final graph ---
    graph = {
        "version": "1.0.0",
        "kind": "knowledge",
        "project": {
            "name": project_name,
            "languages": ["markdown"],
            "frameworks": ["karpathy-wiki"],
            "description": f"Knowledge graph for {project_name}",
            "analyzedAt": datetime.now(timezone.utc).isoformat(),
            "gitCommitHash": "",
        },
        "nodes": list(nodes.values()),
        "edges": final_edges,
        "layers": layers,
        "tour": tour,
    }

    # Try to get git commit hash
    try:
        import subprocess
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, cwd=str(root), timeout=5
        )
        if result.returncode == 0:
            graph["project"]["gitCommitHash"] = result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass

    # Write output
    out_path = intermediate / "assembled-graph.json"
    out_path.write_text(json.dumps(graph, indent=2), encoding="utf-8")

    # Report
    print(f"[merge] Input: {report['base_nodes']} scan nodes, "
          f"{report['base_edges']} scan edges, {report['batches']} analysis batches",
          file=sys.stderr)
    print(f"[merge] Added: {report['new_entities']} entities, "
          f"{report['new_claims']} claims, {report['new_edges']} edges "
          f"({report['deduped_entities']} deduped entities, "
          f"{report['dropped_edges']} dropped dangling edges)", file=sys.stderr)
    print(f"[merge] Output: {len(graph['nodes'])} nodes, {len(final_edges)} edges, "
          f"{len(layers)} layers, {len(tour)} tour steps", file=sys.stderr)
    print(f"[merge] Written: {out_path}", file=sys.stderr)

    return graph


def main():
    if len(sys.argv) < 2:
        print("Usage: merge-knowledge-graph.py <wiki-directory>", file=sys.stderr)
        sys.exit(1)

    root = Path(sys.argv[1]).resolve()
    if not root.is_dir():
        print(f"Error: {root} is not a directory", file=sys.stderr)
        sys.exit(1)

    merge(root)


if __name__ == "__main__":
    main()

```

## File: .skills/understand-anything/understand-knowledge/parse-knowledge-base.py

```python
#!/usr/bin/env python3
"""
Deterministic parser for Karpathy-pattern LLM wikis.

Detects the three-layer pattern (raw sources + wiki markdown + schema),
extracts structure from markdown files, resolves wikilinks, and derives
categories from index.md section headings.

Usage:
    python parse-knowledge-base.py <wiki-directory>

Output:
    Writes scan-manifest.json to <wiki-directory>/<ua-dir>/intermediate/, where
    <ua-dir> is `.ua/` (or legacy `.understand-anything/` when that directory
    already exists).
"""

import json
import os
import re
import sys
from pathlib import Path


def resolve_ua_dir(root: Path) -> Path:
    """Mirror core resolveUaDir: legacy .understand-anything/ wins if present."""
    legacy = root / ".understand-anything"
    return legacy if legacy.is_dir() else root / ".ua"

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------
WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
CODE_BLOCK_RE = re.compile(r"```(\w*)")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
INDEX_SECTION_RE = re.compile(r"^##\s+(.+)$", re.MULTILINE)

# Files that are part of wiki infrastructure, not content articles
INFRA_FILES = {"index.md", "log.md", "claude.md", "agents.md", "soul.md"}


def find_markdown_case_insensitive(parent: Path, name: str) -> Path:
    """Resolve a known markdown filename case-insensitively within one directory.

    An exact match always wins (so `index.md` beats `Index.md` when both
    exist); otherwise the first case-insensitive sibling is returned. The
    unmatched candidate comes back as-is so callers can keep using
    `.is_file()` checks. Deliberately single-directory — no recursive fuzzy
    matching (see #342 non-goals).
    """
    candidate = parent / name
    if candidate.is_file():
        return candidate
    if not parent.is_dir():
        return candidate
    wanted = name.lower()
    for child in sorted(parent.iterdir()):
        if child.is_file() and child.name.lower() == wanted:
            return child
    return candidate

# ---------------------------------------------------------------------------
# Detection: is this a Karpathy-pattern wiki?
# ---------------------------------------------------------------------------

def detect_format(root: Path) -> dict:
    """Detect if directory follows the Karpathy LLM wiki three-layer pattern."""
    signals = {
        "has_index": find_markdown_case_insensitive(root, "index.md").is_file()
        or find_markdown_case_insensitive(root / "wiki", "index.md").is_file(),
        "has_log": find_markdown_case_insensitive(root, "log.md").is_file()
        or find_markdown_case_insensitive(root / "wiki", "log.md").is_file(),
        "has_raw": (root / "raw").is_dir(),
        "has_schema": any(
            (root / f).is_file() or (root / "wiki" / f).is_file()
            for f in ["CLAUDE.md", "AGENTS.md"]
        ),
    }

    # Find the wiki root — could be the directory itself or a wiki/ subdirectory
    if (root / "wiki").is_dir():
        wiki_root = root / "wiki"
    else:
        wiki_root = root

    # Count markdown files in the wiki root
    md_files = list(wiki_root.rglob("*.md"))
    signals["md_count"] = len(md_files)
    signals["wiki_root"] = str(wiki_root)

    # Primary signal: has index.md + meaningful number of markdown files
    if signals["has_index"] and signals["md_count"] >= 3:
        signals["detected"] = True
        signals["format"] = "karpathy"
    else:
        signals["detected"] = False
        signals["format"] = "unknown"

    return signals


# ---------------------------------------------------------------------------
# Markdown extraction helpers
# ---------------------------------------------------------------------------

def extract_frontmatter(text: str) -> dict:
    """Extract YAML frontmatter as a simple key-value dict."""
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}
    fm = {}
    for line in m.group(1).split("\n"):
        if ":" in line:
            key, _, val = line.partition(":")
            fm[key.strip()] = val.strip().strip('"').strip("'")
    return fm


def extract_wikilinks(text: str) -> list[dict]:
    """Extract all [[target]] and [[target|display]] wikilinks."""
    links = []
    for m in WIKILINK_RE.finditer(text):
        links.append({
            "target": m.group(1).strip(),
            "display": m.group(2).strip() if m.group(2) else None,
        })
    return links


def extract_headings(text: str) -> list[dict]:
    """Extract all markdown headings with level and text."""
    return [
        {"level": len(m.group(1)), "text": m.group(2).strip()}
        for m in HEADING_RE.finditer(text)
    ]


def extract_code_blocks(text: str) -> list[str]:
    """Extract languages from fenced code blocks."""
    return [m.group(1) for m in CODE_BLOCK_RE.finditer(text) if m.group(1)]


def extract_first_paragraph(text: str) -> str:
    """Extract the first non-empty paragraph after frontmatter and H1."""
    # Strip frontmatter
    stripped = FRONTMATTER_RE.sub("", text).strip()
    if not stripped:
        return ""
    lines = stripped.split("\n")

    def _collect_paragraph(start_lines: list[str]) -> str:
        """Collect the first paragraph from the given lines."""
        para: list[str] = []
        for s_raw in start_lines:
            s = s_raw.strip()
            if not s and not para:
                continue  # Skip leading blank lines
            if not s and para:
                break  # End of paragraph
            if s.startswith(">"):
                continue  # Skip blockquotes
            if re.match(r"^[-*_]{3,}\s*$", s):
                continue  # Skip horizontal rules
            if s.startswith("#"):
                if para:
                    break  # End paragraph at next heading
                continue  # Skip headings before paragraph
            para.append(s)
        return " ".join(para)

    # Try: find first paragraph after H1
    for i, line in enumerate(lines):
        if line.strip().startswith("# "):
            result = _collect_paragraph(lines[i + 1:])
            if result:
                if len(result) > 200:
                    return result[:197] + "..."
                return result

    # Fallback: no H1 found, take first paragraph from start
    result = _collect_paragraph(lines)
    if len(result) > 200:
        result = result[:197] + "..."
    return result or ""


def extract_h1(text: str) -> str:
    """Extract the first H1 heading."""
    for m in HEADING_RE.finditer(text):
        if len(m.group(1)) == 1:
            # Strip trailing wiki-style decorations like " — subtitle"
            return m.group(2).strip()
    return ""


# ---------------------------------------------------------------------------
# Index.md parsing — categories come from section headings
# ---------------------------------------------------------------------------

def parse_index(index_path: Path) -> list[dict]:
    """Parse index.md to extract categories from ## headings and their wikilinks."""
    if not index_path.is_file():
        return []
    text = index_path.read_text(encoding="utf-8", errors="replace")
    categories = []
    current_category = None

    for line in text.split("\n"):
        # Detect ## section heading
        sec_match = re.match(r"^##\s+(.+)$", line)
        if sec_match:
            current_category = {
                "name": sec_match.group(1).strip(),
                "articles": [],
            }
            categories.append(current_category)
            continue

        # Collect wikilinks under current section
        if current_category:
            for wl in WIKILINK_RE.finditer(line):
                current_category["articles"].append(wl.group(1).strip())

    return categories


# ---------------------------------------------------------------------------
# Log.md parsing — extract operation timeline
# ---------------------------------------------------------------------------

def parse_log(log_path: Path) -> list[dict]:
    """Parse log.md to extract chronological entries."""
    if not log_path.is_file():
        return []
    text = log_path.read_text(encoding="utf-8", errors="replace")
    entries = []
    log_entry_re = re.compile(
        r"^##\s+\[(\d{4}-\d{2}-\d{2})\]\s+(\w+)\s*\|\s*(.+)$", re.MULTILINE
    )
    for m in log_entry_re.finditer(text):
        entries.append({
            "date": m.group(1),
            "operation": m.group(2),
            "title": m.group(3).strip(),
        })
    return entries


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def build_name_to_stem_map(wiki_root: Path) -> dict[str, str]:
    """Build a case-insensitive map from filename stem to relative stem path.

    Full relative paths always map uniquely. Bare basenames map only when
    unambiguous — duplicate basenames are removed so they don't silently
    resolve to the wrong page.
    """
    name_map: dict[str, str] = {}
    # Track which bare basenames appear more than once
    basename_counts: dict[str, int] = {}
    for md_file in wiki_root.rglob("*.md"):
        rel = md_file.relative_to(wiki_root)
        stem = rel.with_suffix("").as_posix()  # e.g., "decisions/decision-foo"
        basename = md_file.stem            # e.g., "decision-foo"
        # Full relative path always maps uniquely
        name_map[stem.lower()] = stem
        # Track basename for ambiguity detection
        key = basename.lower()
        basename_counts[key] = basename_counts.get(key, 0) + 1
        name_map[key] = stem

    # Remove ambiguous basename entries (appear more than once)
    for key, count in basename_counts.items():
        if count > 1 and key in name_map:
            del name_map[key]

    return name_map


def resolve_wikilink(
    target: str,
    name_map: dict[str, str],
    node_ids: set[str] | None = None,
    root_prefix: str | None = None,
) -> str | None:
    """Resolve a wikilink target to an article node ID.

    If node_ids is provided, only resolve to IDs that exist in the set.
    root_prefix is the article-root directory name (e.g. "wiki") — links
    written from the repository root include it ([[wiki/concepts/Index]])
    while name_map keys are relative to the article root, so such targets
    are tried both as written and with the prefix stripped.
    """
    key = target.lower().strip()
    # Skip targets that are clearly not page names (shell flags, etc.)
    if key.startswith("-"):
        return None
    keys = [key]
    if root_prefix and key.startswith(root_prefix + "/"):
        keys.append(key[len(root_prefix) + 1:])
    for k in keys:
        stem = name_map.get(k)
        if stem:
            candidate = f"article:{stem}"
            # If we have a node set, verify the target exists
            if node_ids is not None and candidate not in node_ids:
                return None
            return candidate
    # Try without directory prefix
    for k in keys:
        for stored_key, stored_stem in name_map.items():
            if stored_key.endswith("/" + k) or stored_key == k:
                candidate = f"article:{stored_stem}"
                if node_ids is not None and candidate not in node_ids:
                    return None
                return candidate
    return None


def parse_wiki(root: Path) -> dict:
    """Parse a Karpathy-pattern wiki and produce the scan manifest."""
    detection = detect_format(root)
    if not detection["detected"]:
        print(json.dumps({"error": "Not a Karpathy-pattern wiki", "detection": detection}),
              file=sys.stderr)
        sys.exit(1)

    wiki_root = Path(detection["wiki_root"])
    raw_root = root / "raw"

    # Build name resolution map
    name_map = build_name_to_stem_map(wiki_root)

    # Find index.md and log.md (case-insensitively — Index.md/Log.md are a
    # reasonable convention on case-sensitive filesystems)
    index_path = find_markdown_case_insensitive(wiki_root, "index.md")
    if not index_path.is_file():
        index_path = find_markdown_case_insensitive(root, "index.md")
    log_path = find_markdown_case_insensitive(wiki_root, "log.md")
    if not log_path.is_file():
        log_path = find_markdown_case_insensitive(root, "log.md")

    # Parse index for categories
    categories = parse_index(index_path)
    log_entries = parse_log(log_path)

    # Article ids are relative to wiki_root, but a root index.md commonly
    # links with the article-root prefix included ([[wiki/concepts/Index]]).
    # Register/resolve such targets both as written and prefix-stripped.
    root_prefix = wiki_root.name.lower() if wiki_root != root else None

    # Build category lookup: wikilink target → category name
    category_lookup: dict[str, str] = {}
    for cat in categories:
        for article_target in cat["articles"]:
            t = article_target.lower()
            category_lookup[t] = cat["name"]
            if root_prefix and t.startswith(root_prefix + "/"):
                category_lookup[t[len(root_prefix) + 1:]] = cat["name"]

    # --- Pre-compute article IDs (for edge resolution validation) ---
    # Only skip infra files at the wiki root level, not in subdirectories
    # (e.g., wiki/index.md is infra, but wiki/concepts/index.md is content)
    article_ids: set[str] = set()
    for md_file in sorted(wiki_root.rglob("*.md")):
        rel = md_file.relative_to(wiki_root)
        stem = rel.with_suffix("").as_posix()
        # Only filter infra files at root level (no parent directory)
        if rel.parent == Path(".") and rel.name.lower() in INFRA_FILES:
            continue
        article_ids.add(f"article:{stem}")

    # --- Build article nodes ---
    nodes = []
    edges = []
    warnings = []
    stats = {"articles": 0, "sources": 0, "topics": 0, "wikilinks": 0, "unresolved": 0}

    for md_file in sorted(wiki_root.rglob("*.md")):
        rel = md_file.relative_to(wiki_root)
        stem = rel.with_suffix("").as_posix()
        basename = md_file.stem

        # Skip infrastructure files only at wiki root level
        if rel.parent == Path(".") and rel.name.lower() in INFRA_FILES:
            continue

        text = md_file.read_text(encoding="utf-8", errors="replace")
        h1 = extract_h1(text)
        frontmatter = extract_frontmatter(text)
        wikilinks = extract_wikilinks(text)
        headings = extract_headings(text)
        code_langs = extract_code_blocks(text)
        summary = extract_first_paragraph(text)
        line_count = text.count("\n") + 1
        word_count = len(text.split())

        # Derive category from index.md lookup
        category = category_lookup.get(basename.lower(), "")
        if not category:
            # Try stem match
            category = category_lookup.get(stem.lower(), "")

        # Derive tags (deduplicated)
        tag_set: set[str] = set()
        if category:
            tag_set.add(category.lower())
        if rel.parent != Path("."):
            tag_set.add(str(rel.parent))
        fm_tags = frontmatter.get("tags", "")
        if fm_tags:
            tag_set.update(t.strip() for t in fm_tags.split(",") if t.strip())
        tags = sorted(tag_set)

        # Complexity from wikilink density
        wl_count = len(wikilinks)
        if wl_count > 15:
            complexity = "complex"
        elif wl_count > 5:
            complexity = "moderate"
        else:
            complexity = "simple"

        node_id = f"article:{stem}"
        nodes.append({
            "id": node_id,
            "type": "article",
            "name": h1 or basename,
            "filePath": str(rel),
            "summary": summary or f"Wiki article: {h1 or basename}",
            "tags": tags,
            "complexity": complexity,
            "knowledgeMeta": {
                "wikilinks": [wl["target"] for wl in wikilinks],
                **({"category": category} if category else {}),
                "content": text[:3000],  # First 3000 chars for LLM analysis
            },
        })
        stats["articles"] += 1
        stats["wikilinks"] += wl_count

        # Build edges from wikilinks (resolve against known article IDs)
        for wl in wikilinks:
            target_id = resolve_wikilink(wl["target"], name_map, article_ids, root_prefix)
            if target_id and target_id != node_id:
                edges.append({
                    "source": node_id,
                    "target": target_id,
                    "type": "related",
                    "direction": "forward",
                    "weight": 0.7,
                })
            elif not target_id:
                warnings.append(f"Unresolved wikilink: [[{wl['target']}]] in {rel}")
                stats["unresolved"] += 1

    # --- Build topic nodes from index.md categories ---
    for cat in categories:
        topic_id = f"topic:{cat['name'].lower().replace(' ', '-')}"
        nodes.append({
            "id": topic_id,
            "type": "topic",
            "name": cat["name"],
            "summary": f"Category from index: {cat['name']} ({len(cat['articles'])} articles)",
            "tags": ["category"],
            "complexity": "simple",
        })
        stats["topics"] += 1

        # categorized_under edges (only resolve to known article nodes)
        for article_target in cat["articles"]:
            article_id = resolve_wikilink(article_target, name_map, article_ids, root_prefix)
            if article_id:
                edges.append({
                    "source": article_id,
                    "target": topic_id,
                    "type": "categorized_under",
                    "direction": "forward",
                    "weight": 0.6,
                })

    # --- Build source nodes from raw/ ---
    if raw_root.is_dir():
        for raw_file in sorted(raw_root.rglob("*")):
            if raw_file.is_file() and not raw_file.name.startswith("."):
                rel_raw = raw_file.relative_to(root)
                ext = raw_file.suffix.lower()
                size_kb = raw_file.stat().st_size / 1024
                source_id = f"source:{raw_file.relative_to(raw_root).with_suffix('')}"
                nodes.append({
                    "id": source_id,
                    "type": "source",
                    "name": raw_file.name,
                    "filePath": str(rel_raw),
                    "summary": f"Raw source ({ext or 'unknown'}, {size_kb:.0f} KB)",
                    "tags": ["raw", ext.lstrip(".") or "unknown"],
                    "complexity": "simple",
                })
                stats["sources"] += 1

    # --- Compute backlinks ---
    backlink_map: dict[str, list[str]] = {}
    for edge in edges:
        if edge["type"] == "related":
            target = edge["target"]
            source = edge["source"]
            backlink_map.setdefault(target, []).append(source)
    for node in nodes:
        if node["type"] == "article" and "knowledgeMeta" in node:
            bl = backlink_map.get(node["id"], [])
            node["knowledgeMeta"]["backlinks"] = bl

    # --- Deduplicate edges ---
    seen_edges: set[tuple[str, str, str]] = set()
    deduped_edges = []
    for edge in edges:
        key = (edge["source"], edge["target"], edge["type"])
        if key not in seen_edges:
            seen_edges.add(key)
            deduped_edges.append(edge)

    return {
        "format": "karpathy",
        "stats": stats,
        "categories": [{"name": c["name"], "count": len(c["articles"])} for c in categories],
        "logEntries": len(log_entries),
        "nodes": nodes,
        "edges": deduped_edges,
        "warnings": warnings[:50],  # Cap warnings
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: parse-knowledge-base.py <wiki-directory>", file=sys.stderr)
        sys.exit(1)

    root = Path(sys.argv[1]).resolve()
    if not root.is_dir():
        print(f"Error: {root} is not a directory", file=sys.stderr)
        sys.exit(1)

    manifest = parse_wiki(root)

    # Write output
    out_dir = resolve_ua_dir(root) / "intermediate"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "scan-manifest.json"
    out_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    # Report to stderr
    s = manifest["stats"]
    print(f"[parse] Karpathy wiki: {s['articles']} articles, {s['sources']} sources, "
          f"{s['topics']} topics, {s['wikilinks']} wikilinks "
          f"({s['unresolved']} unresolved)", file=sys.stderr)
    print(f"[parse] Output: {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()

```

## File: .skills/understand-anything/understand/merge-batch-graphs.py

```python
#!/usr/bin/env python3
"""
merge-batch-graphs.py — Merge and normalize batch analysis results.

Combines batch-*.json files from the intermediate directory into a single
assembled graph with normalized IDs, complexity values, and cleaned edges.

Called at the end of Phase 2 of /understand. Phase 3 (ASSEMBLE REVIEW)
then reviews the output for semantic issues the script cannot catch.

Usage:
    python merge-batch-graphs.py <project-root>

Input/output live under the project's data dir (`.ua/`, or legacy
`.understand-anything/` when that directory already exists):
    Input:  <ua-dir>/intermediate/batch-*.json
    Output: <ua-dir>/intermediate/assembled-graph.json
"""

import json
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any


def resolve_ua_dir(root: Path) -> Path:
    """Mirror core resolveUaDir: legacy .understand-anything/ wins if present."""
    legacy = root / ".understand-anything"
    return legacy if legacy.is_dir() else root / ".ua"


# ── Configuration ─────────────────────────────────────────────────────────

VALID_NODE_PREFIXES = {
    "file", "func", "function", "class", "module", "concept",
    "config", "document", "service", "table", "endpoint",
    "pipeline", "schema", "resource",
    "domain", "flow", "step",
    # Knowledge-base node types (schema.ts NodeType enum)
    "article", "entity", "topic", "claim", "source",
}

# Precompiled once at import time. The previous inline form rebuilt and
# re-escaped this 24-alternative pattern *string* on every node (the regex
# cache keys on the final string, so only the compile was cached — the
# join + re.escape work was not). Benchmarked ~15x faster on large graphs.
# The `:`-delimited group + anchoring makes alternation order (and hence the
# unordered-set iteration order) irrelevant to matching, so hoisting is
# byte-for-byte equivalent.
_PROJECT_PREFIX_RE = re.compile(
    r"^[^:]+:(" + "|".join(re.escape(p) for p in VALID_NODE_PREFIXES) + r"):(.+)$"
)

# node.type → canonical ID prefix
TYPE_TO_PREFIX: dict[str, str] = {
    "file": "file",
    "function": "function",
    "func": "function",
    "class": "class",
    "module": "module",
    "concept": "concept",
    "config": "config",
    "document": "document",
    "service": "service",
    "table": "table",
    "endpoint": "endpoint",
    "pipeline": "pipeline",
    "schema": "schema",
    "resource": "resource",
    "domain": "domain",
    "flow": "flow",
    "step": "step",
    # Knowledge-base node types
    "article": "article",
    "entity": "entity",
    "topic": "topic",
    "claim": "claim",
    "source": "source",
}

COMPLEXITY_MAP: dict[str, str] = {
    "low": "simple",
    "easy": "simple",
    "medium": "moderate",
    "intermediate": "moderate",
    "high": "complex",
    "hard": "complex",
    "difficult": "complex",
}

VALID_COMPLEXITY = {"simple", "moderate", "complex"}


# ── tested_by linker configuration ────────────────────────────────────────

# JS/TS family: a `.test.ts` file may be testing a `.ts`, `.tsx`, `.js`, etc.
# We try each candidate extension in priority order.
_JS_TS_EXTS: tuple[str, ...] = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".vue")
_JS_TS_TEST_EXTS: frozenset[str] = frozenset(_JS_TS_EXTS)

# Mirrored production roots — when a test sits under `tests/`, it might be
# mirroring `src/`, `app/`, `lib/`, or the project root.
_MIRROR_PRODUCTION_ROOTS: tuple[str, ...] = ("src", "app", "lib", "")

# Per-extension test-name patterns: ext → (prefix_patterns, suffix_patterns).
# A basename qualifies as a test if its stem starts with any prefix or ends
# with any suffix listed for its extension. JS/TS family is handled separately
# because its `.test`/`.spec` infix sits on the *stem* of a double-extension
# basename (e.g. `foo.test.ts` has ext `.ts`, stem `foo.test`).
_TEST_NAME_PATTERNS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    ".go": ((), ("_test",)),
    ".py": (("test_",), ("_test",)),
    ".java": ((), ("Test", "Tests", "IT")),
    ".kt": ((), ("Test", "Tests")),
    ".scala": ((), ("Spec", "Suite", "Test", "Tests")),
    ".cs": ((), ("Test", "Tests")),
    ".swift": ((), ("Tests", "Test", "Spec")),
    ".rs": (("test_",), ("_test",)),
    ".rb": (("test_",), ("_test", "_spec")),
    ".php": ((), ("Test",)),
    ".c": (("test_",), ("_test",)),
    ".cpp": (("test_",), ("_test",)),
    ".cc": (("test_",), ("_test",)),
}

# These language configs treat every source file below `tests/` as part of a
# test target, even when the basename itself has no test marker.  JS/TS is
# intentionally absent: files such as `__tests__/helpers.ts` remain helpers.
_TEST_DIRECTORY_EXTENSIONS: frozenset[str] = frozenset({".swift", ".rs", ".php"})

_EXACT_TEST_STEMS: dict[str, frozenset[str]] = {
    ".rb": frozenset({"spec_helper"}),
}


# Mirrors packages/core/src/schema.ts so the dashboard validator has nothing
# left to auto-correct for the `direction` field on merged graphs.
_DIRECTION_ALIASES: dict[str, str] = {"both": "bidirectional", "mutual": "bidirectional"}
_VALID_DIRECTIONS: frozenset[str] = frozenset({"forward", "backward", "bidirectional"})


def normalize_direction(value: Any) -> str:
    """Canonicalize an edge `direction` value to one of the schema enum members."""
    candidate = value.lower() if isinstance(value, str) else ""
    candidate = _DIRECTION_ALIASES.get(candidate, candidate)
    if candidate not in _VALID_DIRECTIONS:
        return "forward"
    return candidate


def _num(v: Any) -> float:
    """Coerce a value to float for safe comparison (handles string weights)."""
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def parse_batch_filename(name: str) -> tuple[int, int | None] | None:
    """Return the logical batch index and optional part number for a batch file.

    Incremental updates write the pruned baseline graph as `batch-existing.json`;
    treat it as a real batch that sorts before freshly analyzed numeric batches.
    """
    if name == "batch-existing.json":
        return (-1, None)

    match = re.match(r"batch-(\d+)(?:-part-(\d+))?\.json", name)
    if match is None:
        return None
    return (int(match.group(1)), int(match.group(2)) if match.group(2) else None)


def batch_sort_key(path: Path) -> tuple[int, int, str]:
    parsed = parse_batch_filename(path.name)
    if parsed is None:
        return (sys.maxsize, sys.maxsize, path.name)

    batch_index, part_number = parsed
    return (batch_index, part_number or 0, path.name)


# ── Batch loading ─────────────────────────────────────────────────────────

def load_batch(path: Path) -> dict[str, Any] | None:
    """Load a batch JSON file, tolerating malformed files."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"  Warning: skipping {path.name}: {e}", file=sys.stderr)
        return None

    if not isinstance(data.get("nodes"), list):
        print(f"  Warning: skipping {path.name}: missing or invalid 'nodes' array", file=sys.stderr)
        return None
    if not isinstance(data.get("edges"), list):
        print(f"  Warning: skipping {path.name}: missing or invalid 'edges' array", file=sys.stderr)
        return None

    return data


# ── ID normalization ──────────────────────────────────────────────────────

def classify_id_fix(original: str, corrected: str) -> str:
    """Return a human-readable pattern label for an ID correction."""
    # Double prefix: "file:file:..." → "file:..."
    for prefix in VALID_NODE_PREFIXES:
        if original.startswith(f"{prefix}:{prefix}:"):
            return f"{prefix}:{prefix}: → {prefix}: (double prefix)"

    # Project-name prefix: "my-project:file:..." → "file:..."
    parts = original.split(":")
    if len(parts) >= 3 and parts[0] not in VALID_NODE_PREFIXES and parts[1] in VALID_NODE_PREFIXES:
        return f"<project>:{parts[1]}: → {parts[1]}: (project-name prefix)"

    # Legacy func: → function:
    if original.startswith("func:") and corrected.startswith("function:"):
        return "func: → function: (prefix canonicalization)"

    # Bare path → prefixed
    if not any(original.startswith(f"{p}:") for p in VALID_NODE_PREFIXES):
        prefix = corrected.split(":")[0]
        return f"bare path → {prefix}: (missing prefix)"

    return f"{original} → {corrected}"


def normalize_node_id(node_id: str, node: dict[str, Any]) -> str:
    """Normalize a node ID, returning the corrected version."""
    nid = node_id

    # Strip double prefix: "file:file:src/foo.ts" → "file:src/foo.ts"
    for prefix in VALID_NODE_PREFIXES:
        double = f"{prefix}:{prefix}:"
        if nid.startswith(double):
            nid = nid[len(prefix) + 1:]
            break

    # Strip project-name prefix: "my-project:file:src/foo.ts" → "file:src/foo.ts"
    # Pattern: <word>:<valid-prefix>:<path>
    match = _PROJECT_PREFIX_RE.match(nid)
    if match:
        # Only strip if the first segment is NOT a valid prefix itself
        first_seg = nid.split(":")[0]
        if first_seg not in VALID_NODE_PREFIXES:
            nid = f"{match.group(1)}:{match.group(2)}"

    # Canonicalize legacy prefix: func: → function:
    if nid.startswith("func:") and not nid.startswith("function:"):
        nid = "function:" + nid[5:]

    # Add missing prefix for bare file paths
    has_prefix = any(nid.startswith(f"{p}:") for p in VALID_NODE_PREFIXES)
    if not has_prefix:
        node_type = node.get("type", "file")
        prefix = TYPE_TO_PREFIX.get(node_type, "file")
        if node_type in ("function", "class"):
            file_path = node.get("filePath", "")
            name = node.get("name", nid)
            if file_path:
                nid = f"{prefix}:{file_path}:{name}"
            else:
                # Without filePath, function:<name> collides with every other
                # function of the same name across the project. Prefix with a
                # placeholder so the collision is at least detectable in the
                # report instead of silently merging unrelated nodes.
                nid = f"{prefix}:__nofilepath__:{name}"
        else:
            nid = f"{prefix}:{nid}"

    return nid


def normalize_complexity(value: Any) -> tuple[str, str]:
    """Normalize a complexity value. Returns (normalized, status).

    status is one of:
      "valid"    — already a valid value, no change needed
      "mapped"   — known alias, confidently mapped (goes to Fixed report)
      "unknown"  — unrecognized value, defaulted to moderate (goes to Could-not-fix report)
    """
    if isinstance(value, str):
        lower = value.strip().lower()
        if lower in VALID_COMPLEXITY:
            return lower, "valid"
        if lower in COMPLEXITY_MAP:
            return COMPLEXITY_MAP[lower], "mapped"
        # Unknown string — default but flag it
        return "moderate", "unknown"
    elif isinstance(value, (int, float)):
        n = int(value)
        if n <= 3:
            return "simple", "mapped"
        elif n <= 6:
            return "moderate", "mapped"
        else:
            return "complex", "mapped"
    # None or other type — default but flag it
    return "moderate", "unknown"


# ── Deterministic tested_by linker ────────────────────────────────────────
#
# Two-pass linker. Both passes produce canonical `production → test` edges.
#
# Pass 1 — preserve LLM semantics, fix direction.
#   The LLM sees the relationship only when analyzing a *test* file
#   (production files don't import their tests), so its emitted direction
#   is systematically wrong: source = the file it was analyzing = a test.
#   We do NOT strip these edges — the *pairing* is real evidence (the LLM
#   saw an import / using / same-package call). We just flip direction
#   when source is test + target is production. Edges that are
#   semantically broken (test↔test, production↔production, orphan endpoints)
#   are dropped.
#
# Pass 2 — supplement with path-convention pairings.
#   For test files the LLM didn't link to anything, fall back to filename
#   conventions (sibling `_test.go`, JS/TS `__tests__/`, Maven `src/test/`,
#   etc.) to find a production counterpart. Pairs already covered by
#   Pass 1 are skipped.
#
# Why this beats strip-and-rederive: real projects often violate the
# linker's naming conventions (one Go `_test.go` covering several `.go`
# files in the same package, .NET `<svc>/tests/X.cs` against
# `<svc>/src/Y/X.cs`). Stripping LLM edges drops that real-world coverage
# signal entirely. Swapping preserves it.

def _path_segments(path: str) -> list[str]:
    """Split a relative POSIX-style path into segments (ignoring empties)."""
    return [seg for seg in path.split("/") if seg]


def _basename(path: str) -> str:
    return path.rsplit("/", 1)[-1] if "/" in path else path


def is_test_path(path: str) -> bool:
    """Return True if `path` looks like a test file by language convention.

    Most languages use basename markers. Swift, Rust, and PHP additionally
    make `tests/` a test-source root. JS/TS files still require `.test` or
    `.spec`, so `__tests__/helpers.ts` remains a non-test helper.
    """
    stem, ext = os.path.splitext(_basename(path))
    ext = ext.lower()

    # JS/TS family: the test marker is an infix on the stem (foo.test.ts has
    # stem "foo.test", ext ".ts"), not a prefix/suffix on the stem itself.
    if ext in _JS_TS_TEST_EXTS:
        return stem.endswith(".test") or stem.endswith(".spec")

    if ext in _TEST_DIRECTORY_EXTENSIONS and any(
        segment.lower() == "tests" for segment in _path_segments(path)[:-1]
    ):
        return True

    exact_stems = _EXACT_TEST_STEMS.get(ext)
    if exact_stems is not None and stem in exact_stems:
        return True

    patterns = _TEST_NAME_PATTERNS.get(ext)
    if patterns is None:
        return False
    prefixes, suffixes = patterns
    return any(stem.startswith(p) for p in prefixes) or any(
        stem.endswith(s) for s in suffixes
    )


def _strip_test_infix(stem: str) -> str | None:
    """For a JS/TS-family stem like `foo.test` or `foo.spec`, strip the
    trailing `.test` / `.spec`. Returns None if no infix is present."""
    for infix in (".test", ".spec"):
        if stem.endswith(infix):
            return stem[: -len(infix)]
    return None


def _join(dir_path: str, name: str) -> str:
    """Join a (possibly empty) directory path to a basename with a single
    slash, dropping the slash entirely when there is no directory."""
    return f"{dir_path}/{name}" if dir_path else name


def _add_unique(out: list[str], path: str) -> None:
    """Append `path` to `out` unless it is empty or already present."""
    if path and path not in out:
        out.append(path)


def _js_ts_sibling_candidates(dir_path: str, base_stem: str) -> list[str]:
    """Build sibling candidates for a JS/TS family base stem.

    `dir_path` is the parent dir (no trailing slash, may be empty).
    `base_stem` is the stem with the test infix already stripped.
    """
    return [_join(dir_path, f"{base_stem}{e}") for e in _JS_TS_EXTS]


def production_candidates(test_path: str) -> list[str]:
    """For a test file path, return ordered candidate production paths.

    The returned list is in priority order (sibling first, then `__tests__`
    walk-out, then mirrored-tree variants). Duplicates are removed while
    preserving order. Caller should pick the first candidate that resolves
    to a known production node.
    """
    stem, ext = os.path.splitext(_basename(test_path))
    segs = _path_segments(test_path)
    dir_segs = segs[:-1]
    dir_path = "/".join(dir_segs)

    candidates: list[str] = []

    # ── JS/TS family ──────────────────────────────────────────────────
    if ext in _JS_TS_TEST_EXTS:
        base_stem = _strip_test_infix(stem)
        if base_stem is not None:
            # 1. Sibling de-infix: prefer the same extension as the test, then
            # the rest of the family.
            _add_unique(candidates, _join(dir_path, f"{base_stem}{ext}"))
            for c in _js_ts_sibling_candidates(dir_path, base_stem):
                _add_unique(candidates, c)

            # 2. Walk out of test-segregating subdir — drop the trailing
            # __tests__/test/spec/tests segment. Some JS/TS projects use
            # `<dir>/test/foo.spec.ts` or `<dir>/spec/foo.spec.ts` instead of
            # the more idiomatic `__tests__/`; treat them the same.
            if dir_segs and dir_segs[-1] in ("__tests__", "test", "spec", "tests"):
                parent_dir = "/".join(dir_segs[:-1])
                _add_unique(candidates, _join(parent_dir, f"{base_stem}{ext}"))
                for c in _js_ts_sibling_candidates(parent_dir, base_stem):
                    _add_unique(candidates, c)

            # 3. Mirrored tree: tests/foo/X.test.ts → src/foo/X.ts (and
            # variants for app/lib/<root>).
            if dir_segs and dir_segs[0] in ("tests", "test", "__tests__"):
                tail_path = "/".join(dir_segs[1:])
                for root in _MIRROR_PRODUCTION_ROOTS:
                    new_dir = "/".join(p for p in (root, tail_path) if p)
                    _add_unique(candidates, _join(new_dir, f"{base_stem}{ext}"))
                    for c in _js_ts_sibling_candidates(new_dir, base_stem):
                        _add_unique(candidates, c)

    # ── Go ────────────────────────────────────────────────────────────
    elif ext == ".go" and stem.endswith("_test"):
        base_stem = stem[: -len("_test")]
        _add_unique(candidates, _join(dir_path, f"{base_stem}.go"))

    # ── Python ────────────────────────────────────────────────────────
    elif ext == ".py" and (stem.startswith("test_") or stem.endswith("_test")):
        if stem.startswith("test_"):
            base_stem = stem[len("test_"):]
        else:
            base_stem = stem[: -len("_test")]

        # Sibling
        _add_unique(candidates, _join(dir_path, f"{base_stem}.py"))

        # Walk out of an in-package tests/ or test/ directory:
        # `mypkg/tests/test_bar.py` → `mypkg/bar.py`. Common in Django apps
        # and any project that colocates tests with the package they cover.
        if dir_segs and dir_segs[-1] in ("tests", "test"):
            parent_dir = "/".join(dir_segs[:-1])
            _add_unique(candidates, _join(parent_dir, f"{base_stem}.py"))

        # Mirrored: tests/foo/test_bar.py → src/foo/bar.py (and variants)
        if dir_segs and dir_segs[0] in ("tests", "test"):
            tail_path = "/".join(dir_segs[1:])
            for root in _MIRROR_PRODUCTION_ROOTS:
                new_dir = "/".join(p for p in (root, tail_path) if p)
                _add_unique(candidates, _join(new_dir, f"{base_stem}.py"))

    # ── Java ──────────────────────────────────────────────────────────
    elif ext == ".java":
        for suffix in ("Tests", "Test", "IT"):
            if stem.endswith(suffix):
                base_stem = stem[: -len(suffix)]
                # Maven/Gradle layout: swap src/test/java/... → src/main/java/...
                if (
                    len(dir_segs) >= 3
                    and dir_segs[0] == "src"
                    and dir_segs[1] == "test"
                    and dir_segs[2] == "java"
                ):
                    new_dir = "/".join(["src", "main", "java"] + list(dir_segs[3:]))
                    _add_unique(candidates, f"{new_dir}/{base_stem}.java")
                # Sibling fallback
                _add_unique(candidates, _join(dir_path, f"{base_stem}.java"))
                break

    # ── Kotlin ────────────────────────────────────────────────────────
    elif ext == ".kt":
        for suffix in ("Tests", "Test"):
            if stem.endswith(suffix):
                base_stem = stem[: -len(suffix)]
                if (
                    len(dir_segs) >= 3
                    and dir_segs[0] == "src"
                    and dir_segs[1] == "test"
                    and dir_segs[2] == "kotlin"
                ):
                    new_dir = "/".join(["src", "main", "kotlin"] + list(dir_segs[3:]))
                    _add_unique(candidates, f"{new_dir}/{base_stem}.kt")
                _add_unique(candidates, _join(dir_path, f"{base_stem}.kt"))
                break

    # ── Scala ─────────────────────────────────────────────────────────
    elif ext == ".scala":
        for suffix in ("Spec", "Suite", "Tests", "Test"):
            if stem.endswith(suffix):
                base_stem = stem[: -len(suffix)]
                # sbt layout: swap any .../src/test/scala/... segment while
                # preserving a module prefix such as modules/core/.
                for i in range(0, max(len(dir_segs) - 2, 0)):
                    if list(dir_segs[i : i + 3]) == ["src", "test", "scala"]:
                        new_dir = "/".join(
                            list(dir_segs[:i])
                            + ["src", "main", "scala"]
                            + list(dir_segs[i + 3 :])
                        )
                        _add_unique(candidates, f"{new_dir}/{base_stem}.scala")
                        break
                _add_unique(candidates, _join(dir_path, f"{base_stem}.scala"))
                break

    # ── C# ────────────────────────────────────────────────────────────
    elif ext == ".cs":
        for suffix in ("Tests", "Test"):
            if stem.endswith(suffix):
                base_stem = stem[: -len(suffix)]
                # Sibling fallback (e.g. `Foo.Tests/BarTests.cs` ↔ same dir
                # is rare but cheap to try).
                _add_unique(candidates, _join(dir_path, f"{base_stem}.cs"))

                # Walk out of an in-service `tests/` directory and search
                # the sibling `src/` subtree. Handles layouts like
                # `src/<svc>/tests/BarTests.cs` ↔ `src/<svc>/src/.../Bar.cs`
                # (microservices-demo cartservice) and bare
                # `<proj>/tests/BarTests.cs` ↔ `<proj>/src/Bar.cs`.
                tests_idx = None
                for i in range(len(dir_segs) - 1, -1, -1):
                    if dir_segs[i].lower() in ("tests", "test"):
                        tests_idx = i
                        break
                if tests_idx is not None:
                    parent_segs = dir_segs[:tests_idx]
                    tail_segs = dir_segs[tests_idx + 1 :]
                    parent_dir = "/".join(parent_segs)
                    # `<parent>/<base_stem>.cs` (drop `tests/` entirely).
                    _add_unique(
                        candidates,
                        _join(parent_dir, f"{base_stem}.cs"),
                    )
                    # `<parent>/src/<tail>/<base_stem>.cs` (mirror through src/).
                    src_dir = "/".join([*parent_segs, "src", *tail_segs])
                    _add_unique(candidates, _join(src_dir, f"{base_stem}.cs"))

                # `.NET`-style sibling-project mirror: `My.App.Tests/...` ↔
                # `My.App/...`. The test project's top dir typically ends in
                # `.Tests`. Strip it and try the same tail under the sibling.
                if dir_segs:
                    top = dir_segs[0]
                    if top.endswith(".Tests") or top.endswith(".Test"):
                        sibling = top[: -len(".Tests")] if top.endswith(".Tests") else top[: -len(".Test")]
                        if sibling:
                            mirror_dir = "/".join([sibling, *dir_segs[1:]])
                            _add_unique(
                                candidates,
                                _join(mirror_dir, f"{base_stem}.cs"),
                            )
                break

    # ── C/C++ ─────────────────────────────────────────────────────────
    elif ext in {".c", ".cpp", ".cc"}:
        if stem.startswith("test_"):
            base_stem = stem[len("test_"):]
        elif stem.endswith("_test"):
            base_stem = stem[: -len("_test")]
        else:
            base_stem = None
        if base_stem is not None:
            _add_unique(candidates, _join(dir_path, f"{base_stem}{ext}"))

    return candidates


def _file_node_path(node: dict[str, Any]) -> str | None:
    """Return the relative project path for a `file:`-prefixed node, else None."""
    nid = node.get("id", "")
    if not isinstance(nid, str) or not nid.startswith("file:"):
        return None
    fp = node.get("filePath")
    if isinstance(fp, str) and fp:
        return fp
    return nid[len("file:"):]


def _swap_tested_by_in_place(
    edge: dict[str, Any], original_src: str, original_tgt: str
) -> None:
    """Flip an inverted `tested_by` edge so source becomes production and
    target becomes the test file. Mutates `edge` in place; appends a
    `[direction corrected]` audit marker to `description`.
    """
    edge["source"] = original_tgt
    edge["target"] = original_src
    edge["direction"] = "forward"
    prev = edge.get("description")
    edge["description"] = (
        "Direction corrected (was test → production)"
        if not prev
        else f"{prev} [direction corrected]"
    )


def _ensure_tested_tag(node: dict[str, Any]) -> bool:
    """Append "tested" to `node["tags"]`, coercing malformed `tags` to a
    fresh list. Returns True if the tag was newly added.

    `tags` from raw LLM batch JSON may be missing, None, a string, or
    another non-list value — the TypeScript autoFixGraph normalizer that
    handles this runs downstream of this script, so we defend here.
    """
    tags = node.get("tags")
    if not isinstance(tags, list):
        tags = []
        node["tags"] = tags
    if "tested" in tags:
        return False
    tags.append("tested")
    return True


def link_tests(
    nodes_by_id: dict[str, dict[str, Any]],
    edges: list[dict[str, Any]],
) -> tuple[int, int, int, int]:
    """Canonicalize `tested_by` edges and link unmatched test files.

    Two passes (see module-level "Deterministic tested_by linker" comment
    for the rationale):

      1. Walk every existing `tested_by` edge. Keep canonical
         (production → test) edges as-is. Flip inverted (test → production)
         edges so the swap preserves the LLM's pairing evidence with the
         right direction. Drop edges that don't classify cleanly as
         file ↔ file or where one endpoint is missing — they have no
         recoverable meaning.
      2. For every test file not yet paired by Pass 1, walk path-convention
         candidates and emit a fresh `production → test` edge for the first
         match.

    Tagging happens once per production node that ends up on the source
    side of any `tested_by` edge (canonical, swapped, or supplemented).

    Mutates `nodes_by_id` (adds "tested" tag) and `edges` (rewrites
    in place: drops semantically broken edges, swaps inverted ones, appends
    supplements).

    Returns (added, dropped, tagged, swapped):
      added:   path-convention supplemental edges appended in Pass 2
      dropped: pre-existing `tested_by` edges removed (unsalvageable)
      tagged:  production nodes newly tagged "tested"
      swapped: pre-existing `tested_by` edges flipped (test → production
               became production → test)
    """
    # ── Index file nodes by relative path; classify each as test/production.
    # `is_prod` here means "is a known file node AND is not a test by
    # path convention" — used both to validate edge endpoints and to drive
    # path-convention candidate matching.
    file_paths_to_nodes: dict[str, dict[str, Any]] = {}
    node_id_to_classification: dict[str, str] = {}  # id → "test" | "prod"
    test_nodes: list[tuple[str, dict[str, Any]]] = []
    for node in nodes_by_id.values():
        path = _file_node_path(node)
        if path is None:
            continue
        file_paths_to_nodes[path] = node
        if is_test_path(path):
            node_id_to_classification[node["id"]] = "test"
            test_nodes.append((path, node))
        else:
            node_id_to_classification[node["id"]] = "prod"

    # ── Pass 1: walk existing tested_by edges, canonicalize or drop.
    # `covered` tracks (production_id, test_id) pairs that have a kept edge
    # after this pass — used both to deduplicate within Pass 1 and to
    # suppress duplicate supplements in Pass 2.
    # `pair_to_idx` maps each kept pair to its slot in the compacted edges
    # list, so a duplicate that arrives later with a higher weight can
    # replace the earlier slot in place (mirrors Step 6's
    # `weight > existing.weight` rule — without this, a 0.3-weight edge
    # from batch 1 would silently outrank a 0.9-weight edge from batch 2
    # because Step 6 only ever sees one of them).
    # `swapped_pairs` records which surviving pairs came from a flipped
    # edge, so the `swapped` counter reflects the FINAL output and
    # doesn't double-count work done on edges that were later replaced.
    covered: set[tuple[str, str]] = set()
    pair_to_idx: dict[tuple[str, str], int] = {}
    swapped_pairs: set[tuple[str, str]] = set()
    dropped = 0
    write_idx = 0
    for edge in edges:
        if edge.get("type") != "tested_by":
            edges[write_idx] = edge
            write_idx += 1
            continue

        src = edge.get("source", "")
        tgt = edge.get("target", "")
        src_class = node_id_to_classification.get(src)
        tgt_class = node_id_to_classification.get(tgt)

        # Both endpoints must be known file nodes; one test, one production.
        # Anything else (orphan, test↔test, prod↔prod, non-file endpoint)
        # has no recoverable meaning — drop it.
        if (src_class, tgt_class) == ("prod", "test"):
            pair = (src, tgt)
            needs_swap = False
        elif (src_class, tgt_class) == ("test", "prod"):
            pair = (tgt, src)
            needs_swap = True
        else:
            dropped += 1
            continue

        if pair in covered:
            # Duplicate pair: keep the heavier-weight edge (mirrors the
            # weight-aware dedup in Step 6, which can't help here because
            # only one of the duplicates would reach it).
            existing_idx = pair_to_idx[pair]
            existing = edges[existing_idx]
            if _num(edge.get("weight", 0)) > _num(existing.get("weight", 0)):
                # Heavier — replace existing slot. Apply the swap (or not)
                # only on the survivor, so we never spend cycles canonicalizing
                # an edge we're about to drop.
                if needs_swap:
                    _swap_tested_by_in_place(edge, src, tgt)
                    swapped_pairs.add(pair)
                else:
                    # Replacement is canonical — if the previous winner came
                    # from a swap, the surviving slot is no longer a swap.
                    swapped_pairs.discard(pair)
                edges[existing_idx] = edge
            # else: existing is heavier or equal — keep it, drop the new edge.
            dropped += 1
            continue

        if needs_swap:
            _swap_tested_by_in_place(edge, src, tgt)
            swapped_pairs.add(pair)
        covered.add(pair)
        pair_to_idx[pair] = write_idx
        edges[write_idx] = edge
        write_idx += 1
    del edges[write_idx:]
    swapped = len(swapped_pairs)

    # ── Pass 2: path-convention supplement for tests not yet paired.
    paired_test_ids = {test_id for (_prod_id, test_id) in covered}
    added = 0
    for test_path, test_node in test_nodes:
        if test_node["id"] in paired_test_ids:
            continue
        for cand_path in production_candidates(test_path):
            prod_node = file_paths_to_nodes.get(cand_path)
            if prod_node is None:
                continue
            if is_test_path(cand_path):
                # Don't link a test to another test even if naming aligns.
                continue
            pair = (prod_node["id"], test_node["id"])
            if pair in covered:
                continue
            edges.append({
                "source": prod_node["id"],
                "target": test_node["id"],
                "type": "tested_by",
                "direction": "forward",
                "weight": 0.5,
                "description": "Path-based pairing (deterministic)",
            })
            covered.add(pair)
            added += 1
            break

    # ── Tag every production node that ended up sourcing a tested_by edge
    # (covers Pass 1 canonical + swapped + Pass 2 supplements in one place).
    tagged = 0
    for prod_id, _test_id in covered:
        prod_node = nodes_by_id.get(prod_id)
        if prod_node is None:
            continue
        if _ensure_tested_tag(prod_node):
            tagged += 1

    return added, dropped, tagged, swapped


# ── Main merge + normalize ────────────────────────────────────────────────

def merge_and_normalize(
    batches: list[dict[str, Any]],
    *,
    current_edge_ids: set[int] | None = None,
    dangling_candidates: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Merge batch results and normalize. Returns (assembled_graph, report_lines)."""

    # ── Pattern counters for "Fixed" report ──────────────────────────
    id_fix_patterns: Counter[str] = Counter()
    complexity_fix_patterns: Counter[str] = Counter()

    # ── Detail lists for "Could not fix" report ──────────────────────
    unfixable: list[str] = []

    # ── Step 1: Combine all nodes and edges ──────────────────────────
    all_nodes: list[dict] = []
    all_edges: list[dict] = []
    for batch in batches:
        all_nodes.extend(batch.get("nodes", []))
        all_edges.extend(batch.get("edges", []))

    total_input_nodes = len(all_nodes)
    total_input_edges = len(all_edges)

    # ── Step 2: Normalize node IDs and build ID mapping ──────────────
    id_mapping: dict[str, str] = {}  # original → corrected
    nodes_with_ids: list[dict] = []
    unknown_node_types: Counter[str] = Counter()

    for i, node in enumerate(all_nodes):
        original_id = node.get("id")
        if not original_id:
            unfixable.append(f"Node[{i}] has no 'id' field (name={node.get('name', '?')}, type={node.get('type', '?')})")
            continue

        # Flag unknown node types
        node_type = node.get("type", "")
        if node_type and node_type not in TYPE_TO_PREFIX:
            unknown_node_types[node_type] += 1

        nodes_with_ids.append(node)
        corrected_id = normalize_node_id(original_id, node)
        if corrected_id != original_id:
            pattern = classify_id_fix(original_id, corrected_id)
            id_fix_patterns[pattern] += 1
            id_mapping[original_id] = corrected_id
            node["id"] = corrected_id

    # ── Step 3: Normalize complexity ─────────────────────────────────
    complexity_unknown_patterns: Counter[str] = Counter()

    for node in nodes_with_ids:
        original = node.get("complexity")
        normalized, status = normalize_complexity(original)

        if status == "mapped":
            orig_repr = repr(original) if not isinstance(original, str) else f'"{original}"'
            complexity_fix_patterns[f"{orig_repr} → \"{normalized}\""] += 1
        elif status == "unknown":
            orig_repr = repr(original) if not isinstance(original, str) else f'"{original}"'
            complexity_unknown_patterns[f"complexity {orig_repr} → defaulted to \"moderate\""] += 1

        node["complexity"] = normalized

    # ── Step 4: Rewrite edge references ──────────────────────────────
    edges_rewritten = 0
    for edge in all_edges:
        src = edge.get("source", "")
        tgt = edge.get("target", "")
        new_src = id_mapping.get(src, src)
        new_tgt = id_mapping.get(tgt, tgt)
        if new_src != src or new_tgt != tgt:
            edges_rewritten += 1
            edge["source"] = new_src
            edge["target"] = new_tgt

    # ── Step 5: Deduplicate nodes by ID (keep last) ─────────────────
    duplicate_count = 0
    nodes_by_id: dict[str, dict] = {}
    for node in nodes_with_ids:
        nid = node.get("id", "")
        if nid in nodes_by_id:
            duplicate_count += 1
        nodes_by_id[nid] = node

    # ── Step 5b: Deterministic tested_by linker ──────────────────────
    # See module-level "Deterministic tested_by linker" section above.
    tested_by_added, tested_by_dropped, tested_by_tagged, tested_by_swapped = link_tests(
        nodes_by_id, all_edges
    )

    # ── Step 6: Deduplicate edges, drop dangling ─────────────────────
    node_ids = set(nodes_by_id.keys())
    # Direction is part of the dedup key so a `forward` edge does not silently
    # overwrite a `bidirectional` one (or vice versa); they're different
    # semantic relationships that the dashboard renders distinctly.
    edges_by_key: dict[tuple[str, str, str, str], dict] = {}
    dangling_by_key: dict[tuple[str, str, str, str], dict] = {}
    for edge in all_edges:
        src = edge.get("source", "")
        tgt = edge.get("target", "")
        etype = edge.get("type", "")
        direction = normalize_direction(edge.get("direction"))
        edge["direction"] = direction
        key = (src, tgt, etype, direction)

        if src not in node_ids or tgt not in node_ids:
            # Preserve normalized CURRENT analyzer evidence before unresolved
            # endpoints are discarded. Never collect edges from batch-existing.
            if (
                dangling_candidates is not None
                and current_edge_ids is not None
                and id(edge) in current_edge_ids
            ):
                previous = dangling_by_key.get(key)
                if previous is None or _num(edge.get("weight", 0)) > _num(previous.get("weight", 0)):
                    dangling_by_key[key] = dict(edge)
            missing = []
            if src not in node_ids:
                missing.append(f"source '{src}'")
            if tgt not in node_ids:
                missing.append(f"target '{tgt}'")
            unfixable.append(f"Edge {src} → {tgt} ({etype}): dropped, missing {', '.join(missing)}")
            continue

        existing = edges_by_key.get(key)
        if existing is None or _num(edge.get("weight", 0)) > _num(existing.get("weight", 0)):
            edges_by_key[key] = edge

    if dangling_candidates is not None:
        dangling_candidates.extend(dangling_by_key.values())

    # ── Build report ─────────────────────────────────────────────────
    report: list[str] = []
    report.append(f"Input: {total_input_nodes} nodes, {total_input_edges} edges")

    # Fixed section — grouped by pattern
    fixed_lines: list[str] = []
    if id_fix_patterns:
        for pattern, count in id_fix_patterns.most_common():
            fixed_lines.append(f"  {count:>4} × {pattern}")
    if complexity_fix_patterns:
        for pattern, count in complexity_fix_patterns.most_common():
            fixed_lines.append(f"  {count:>4} × complexity {pattern}")
    if edges_rewritten:
        fixed_lines.append(f"  {edges_rewritten:>4} × edge references rewritten after ID normalization")
    if duplicate_count:
        fixed_lines.append(f"  {duplicate_count:>4} × duplicate node IDs removed (kept last)")
    if tested_by_swapped:
        fixed_lines.append(f"  {tested_by_swapped:>4} × tested_by edges flipped (test → production became production → test)")
    if tested_by_dropped:
        fixed_lines.append(f"  {tested_by_dropped:>4} × tested_by edges dropped (orphan endpoint or test↔test / prod↔prod pair)")

    if fixed_lines:
        report.append("")
        total_fixes = (
            sum(id_fix_patterns.values())
            + sum(complexity_fix_patterns.values())
            + edges_rewritten
            + duplicate_count
            + tested_by_swapped
            + tested_by_dropped
        )
        report.append(f"Fixed ({total_fixes} corrections):")
        report.extend(fixed_lines)

    # Tested-by linker section — separate from Fixed since these are net-new
    # additions, not corrections.
    if tested_by_added or tested_by_tagged:
        report.append("")
        report.append("Tested-by linker:")
        report.append(f"  {tested_by_added:>4} × tested_by edges produced (path-convention supplement, production → test)")
        report.append(f"  {tested_by_tagged:>4} × production nodes tagged \"tested\"")

    # Could not fix section — unknown patterns (grouped) + individual details
    unfixable_total = (
        len(unfixable)
        + sum(complexity_unknown_patterns.values())
        + sum(unknown_node_types.values())
    )
    if unfixable_total:
        report.append("")
        report.append(f"Could not fix ({unfixable_total} issues — needs agent review):")
        # Unknown node types (grouped by count)
        for ntype, count in unknown_node_types.most_common():
            report.append(f"  {count:>4} × unknown node type \"{ntype}\" (not in schema, kept as-is)")
        # Unknown complexity patterns (grouped by count)
        for pattern, count in complexity_unknown_patterns.most_common():
            report.append(f"  {count:>4} × {pattern}")
        # Individual unfixable items
        for detail in unfixable:
            report.append(f"  - {detail}")

    # Output stats
    report.append("")
    report.append(f"Output: {len(nodes_by_id)} nodes, {len(edges_by_key)} edges")

    assembled = {
        "nodes": list(nodes_by_id.values()),
        "edges": list(edges_by_key.values()),
    }

    return assembled, report


# ── Imports-edge recovery from importMap ──────────────────────────────────

WHOLE_FILE_NODE_TYPES: frozenset[str] = frozenset(
    {"file", "config", "document", "service", "pipeline", "schema", "resource"}
)


def build_whole_file_node_index(
    nodes: list[dict[str, Any]],
) -> tuple[dict[str, str], list[str]]:
    """Map each filePath to its canonical whole-file node id.

    Only exact ``<type>:<filePath>`` IDs qualify. This intentionally excludes
    child constructs such as tables and endpoints, even when they carry the
    same ``filePath``. If an analyzer emitted more than one whole-file node for
    a path, ``file:`` wins; otherwise the first stable graph occurrence wins.
    """
    index: dict[str, str] = {}
    selected_types: dict[str, str] = {}
    warnings: list[str] = []

    for node in nodes:
        node_type = node.get("type")
        file_path = node.get("filePath")
        node_id = node.get("id")
        if (
            node_type not in WHOLE_FILE_NODE_TYPES
            or not isinstance(file_path, str)
            or not file_path
            or node_id != f"{node_type}:{file_path}"
        ):
            continue

        existing_id = index.get(file_path)
        if existing_id is None:
            index[file_path] = node_id
            selected_types[file_path] = node_type
            continue

        existing_type = selected_types[file_path]
        if node_type == "file" and existing_type != "file":
            index[file_path] = node_id
            selected_types[file_path] = node_type
            selected = node_id
        else:
            selected = existing_id
        warnings.append(
            f"  Warning: multiple whole-file nodes for {file_path}; selected {selected}"
        )

    return index, warnings

def recover_imports_from_scan(
    assembled: dict[str, Any],
    scan_result_path: Path,
) -> tuple[int, list[str]]:
    """Re-emit any `imports` edges that exist in `scan-result.json#importMap`
    but never made it into a batch's output. The project-scanner's importMap
    is the deterministic source of truth for resolved internal imports;
    file-analyzer agents are expected to transcribe those into edges 1:1
    but in practice drop ~25% of them on real projects (orchestrator-side
    batch construction loses entries, agent-side enumeration drops more).

    Returns (recovered_count, report_lines).
    """
    if not scan_result_path.is_file():
        return 0, [f"  importMap recovery skipped — {scan_result_path.name} not found"]

    try:
        scan = json.loads(scan_result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return 0, [f"  importMap recovery skipped — could not parse {scan_result_path.name}: {e}"]

    import_map = scan.get("importMap")
    if not isinstance(import_map, dict):
        return 0, [f"  importMap recovery skipped — no importMap field in {scan_result_path.name}"]

    file_path_to_node_id, conflict_warnings = build_whole_file_node_index(
        assembled["nodes"]
    )

    # Build the set of (source, target) imports edges already present.
    existing: set[tuple[str, str]] = set()
    for edge in assembled["edges"]:
        if edge.get("type") == "imports":
            existing.add((edge.get("source", ""), edge.get("target", "")))

    recovered = 0
    skipped_no_src_node = 0
    skipped_no_tgt_node = 0
    for src_path, targets in import_map.items():
        if not isinstance(targets, list):
            continue
        src_id = file_path_to_node_id.get(src_path)
        if src_id is None:
            if targets:
                skipped_no_src_node += 1
            continue
        for tgt_path in targets:
            if not isinstance(tgt_path, str) or not tgt_path:
                continue
            tgt_id = file_path_to_node_id.get(tgt_path)
            if tgt_id is None:
                skipped_no_tgt_node += 1
                continue
            if src_id == tgt_id:
                continue
            if (src_id, tgt_id) in existing:
                continue
            assembled["edges"].append({
                "source": src_id,
                "target": tgt_id,
                "type": "imports",
                "direction": "forward",
                "weight": 0.7,
                "recoveredFromImportMap": True,
            })
            existing.add((src_id, tgt_id))
            recovered += 1

    lines: list[str] = list(conflict_warnings)
    lines.append(
        f"  Recovered {recovered} `imports` edges from importMap "
        f"({len(import_map)} entries scanned)"
    )
    if skipped_no_src_node:
        lines.append(
            f"  Skipped {skipped_no_src_node} importMap source files "
            f"with no whole-file node in graph"
        )
    if skipped_no_tgt_node:
        lines.append(
            f"  Skipped {skipped_no_tgt_node} importMap target paths "
            f"with no whole-file node in graph"
        )
    return recovered, lines


# ── Main ──────────────────────────────────────────────────────────────────

def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python merge-batch-graphs.py <project-root>", file=sys.stderr)
        sys.exit(1)

    project_root = Path(sys.argv[1]).resolve()
    intermediate_dir = resolve_ua_dir(project_root) / "intermediate"
    plan_path = intermediate_dir / "incremental-plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8")) if plan_path.exists() else {}
    incremental = plan.get("action") in ("PARTIAL_UPDATE", "ARCHITECTURE_UPDATE")

    if not intermediate_dir.is_dir():
        print(f"Error: {intermediate_dir} does not exist", file=sys.stderr)
        sys.exit(1)

    # Discover batch files, sorted by numeric index (not lexicographic).
    # `batch-existing.json` is the documented incremental baseline and must
    # sort before fresh batches so fresh duplicate nodes/edges win later.
    batch_files = sorted(
        intermediate_dir.glob("batch-*.json"),
        key=batch_sort_key,
    )
    if not batch_files:
        print("Error: no batch-*.json files found in intermediate/", file=sys.stderr)
        sys.exit(1)

    # Group by logical batch index so the report distinguishes single-batch
    # files from multi-part file-analyzer outputs. Files that don't match the
    # `batch-existing.json` / `batch-<N>.json` / `batch-<N>-part-<K>.json`
    # pattern (e.g. fused `batch-fused-8-13.json`, range `batch-8-13.json`)
    # would otherwise be silently dropped during load — flag them loudly
    # instead so the user can fix the file-analyzer agent.
    from collections import defaultdict as _dd
    by_batch = _dd(list)
    unrecognized_batch_files: list[str] = []
    for f in batch_files:
        parsed = parse_batch_filename(f.name)
        if parsed is None:
            unrecognized_batch_files.append(f.name)
        else:
            batch_index, part_number = parsed
            by_batch[batch_index].append((f.name, part_number))

    if unrecognized_batch_files:
        preview = ", ".join(unrecognized_batch_files[:5])
        suffix = (
            f" (+{len(unrecognized_batch_files) - 5} more)"
            if len(unrecognized_batch_files) > 5
            else ""
        )
        print(
            f"Warning: merge-batch-graphs: {len(unrecognized_batch_files)} "
            f"batch file(s) with unrecognized filenames will be DROPPED — "
            f"files: {preview}{suffix} — fix the file-analyzer agent to use "
            f"only batch-<N>.json or batch-<N>-part-<K>.json patterns",
            file=sys.stderr,
        )

    logical_count = len(by_batch)
    multi_part = sum(1 for entries in by_batch.values() if len(entries) > 1)
    print(
        f"Found {len(batch_files)} batch files "
        f"({logical_count} logical batches, {multi_part} multi-part):",
        file=sys.stderr,
    )

    # Missing-part detection: for any logical batch with parts (len > 1), the
    # set of part numbers MUST be contiguous starting at 1. Gaps suggest a
    # truncated write — emit a visible warning so the user can investigate.
    # Collect into `missing_part_warnings` so they also surface in the final
    # phase report; stderr alone gets buried under the per-batch load lines.
    missing_part_warnings: list[str] = []
    for idx, entries in by_batch.items():
        part_nums = [p for (_n, p) in entries if p is not None]
        if not part_nums:
            continue
        present = set(part_nums)
        expected = set(range(1, max(part_nums) + 1))
        missing = sorted(expected - present)
        if missing:
            msg = (
                f"batch {idx} has parts {sorted(present)} but "
                f"missing part {missing} — possible truncated write — "
                f"affected nodes/edges may be lost"
            )
            print(f"Warning: merge: {msg}", file=sys.stderr)
            missing_part_warnings.append(msg)

    # Load batches — skip unrecognized filenames so they don't pollute the
    # merged graph with content the agent labeled incorrectly.
    unrecognized_set = set(unrecognized_batch_files)
    batches: list[dict[str, Any]] = []
    current_edge_ids: set[int] = set()
    empty_batch_warnings: list[str] = []
    for f in batch_files:
        if f.name in unrecognized_set:
            continue
        batch = load_batch(f)
        if batch is not None:
            batches.append(batch)
            if incremental and f.name != "batch-existing.json":
                current_edge_ids.update(id(edge) for edge in batch.get("edges", []))
            n = len(batch.get("nodes", []))
            e = len(batch.get("edges", []))
            print(f"  {f.name}: {n} nodes, {e} edges", file=sys.stderr)
            # A file that parses but contributes nothing is how a silent
            # partial merge looks from the outside (see #484) — flag it
            # loudly instead of relying on a downstream reviewer to notice.
            if n == 0 and e == 0:
                msg = (
                    f"{f.name} loaded but contributed 0 nodes and 0 edges — "
                    f"either the analyzer wrote an empty batch or the file "
                    f"was read mid-write; inspect it directly"
                )
                print(f"  Warning: {msg}", file=sys.stderr)
                empty_batch_warnings.append(msg)

    if not batches:
        print("Error: no valid batch files loaded", file=sys.stderr)
        sys.exit(1)

    # Merge and normalize
    dangling_candidates: list[dict[str, Any]] = []
    assembled, report = merge_and_normalize(
        batches, current_edge_ids=current_edge_ids if incremental else None,
        dangling_candidates=dangling_candidates if incremental else None,
    )

    # Surface missing multi-part files to the phase report (parallel to
    # unrecognized-filename handling below). Stderr lines emitted during
    # batch discovery get buried under per-batch load output — re-emitting
    # via the report list ensures the Phase 4 review and final summary see
    # the data-loss signal.
    if missing_part_warnings:
        report.append("")
        report.append(
            f"Warning: {len(missing_part_warnings)} batch(es) with missing parts "
            f"— some nodes/edges silently dropped:"
        )
        for w in missing_part_warnings:
            report.append(f"  - {w}")

    # Surface empty-contribution batches to the phase report (same rationale
    # as missing_part_warnings above — stderr alone gets buried).
    if empty_batch_warnings:
        report.append("")
        report.append(
            f"Warning: {len(empty_batch_warnings)} batch file(s) loaded but "
            f"contributed no nodes or edges:"
        )
        for w in empty_batch_warnings:
            report.append(f"  - {w}")

    # Surface unrecognized-filename drops to the phase report so the
    # downstream review step sees them, not just stderr.
    if unrecognized_batch_files:
        preview = ", ".join(unrecognized_batch_files[:5])
        suffix = (
            f" (+{len(unrecognized_batch_files) - 5} more)"
            if len(unrecognized_batch_files) > 5
            else ""
        )
        report.append("")
        report.append(
            f"Warning: dropped {len(unrecognized_batch_files)} batch file(s) "
            f"with unrecognized filenames — files: {preview}{suffix} — "
            f"fix the file-analyzer agent to use only batch-<N>.json or "
            f"batch-<N>-part-<K>.json patterns (every node/edge in these "
            f"files was excluded from the final graph)"
        )

    # Recover any imports edges file-analyzer batches dropped despite
    # `batchImportData` containing them. The project-scanner's importMap
    # is the deterministic source of truth.
    scan_result_path = intermediate_dir / "scan-result.json"
    recovered, recovery_report = recover_imports_from_scan(assembled, scan_result_path)
    if recovery_report:
        report.append("")
        report.append("Imports edge recovery:")
        report.extend(recovery_report)

    # Print report
    print("", file=sys.stderr)
    for line in report:
        print(line, file=sys.stderr)

    # Write output
    output_path = intermediate_dir / "assembled-graph.json"
    output_path.write_text(json.dumps(assembled, indent=2, ensure_ascii=False), encoding="utf-8")

    size_kb = output_path.stat().st_size / 1024
    print(f"\nWritten to {output_path} ({size_kb:.0f} KB)", file=sys.stderr)

    # The old symbols live outside batch-existing.json, which intentionally
    # excludes reanalyzed files. Keep failed output as a diagnostic artifact,
    # but return failure so the orchestrator repairs it before publication.
    plan_path = intermediate_dir / "incremental-plan.json"
    if plan_path.exists():
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        if plan.get("action") in ("PARTIAL_UPDATE", "ARCHITECTURE_UPDATE"):
            candidate_path = intermediate_dir / "incremental-edge-candidates.json"
            candidate_temp = candidate_path.with_name(f"{candidate_path.name}.tmp-{os.getpid()}")
            candidate_temp.write_text(json.dumps({
                "baseCommit": plan["baseCommit"],
                "headCommit": plan["headCommit"],
                "edges": dangling_candidates,
            }, indent=2, ensure_ascii=False), encoding="utf-8")
            candidate_temp.replace(candidate_path)
            validator = Path(__file__).resolve().with_name("validate-incremental-symbols.mjs")
            result = subprocess.run(["node", str(validator), str(project_root)], check=False)
            if result.returncode != 0:
                sys.exit(result.returncode)


if __name__ == "__main__":
    main()

```

## File: .skills/understand-anything/understand/merge-subdomain-graphs.py

```python
#!/usr/bin/env python3
"""
merge-subdomain-graphs.py — Merge subdomain knowledge-graph files into one.

Auto-discovers *knowledge-graph*.json files in the project's data dir
(`.ua/`, or legacy `.understand-anything/` when that directory already exists)
excluding knowledge-graph.json itself, loads the existing
knowledge-graph.json as a base if present, and merges everything
into a single knowledge-graph.json.

Usage:
    python merge-subdomain-graphs.py <project-root> [file1.json file2.json ...]

If no files are specified, auto-discovers subdomain graphs. The main
knowledge-graph.json is loaded as a base but never as a discovery input
(prevents self-merging on repeated runs).

Output:
    <ua-dir>/knowledge-graph.json
"""

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


def resolve_ua_dir(root: Path) -> Path:
    """Mirror core resolveUaDir: legacy .understand-anything/ wins if present."""
    legacy = root / ".understand-anything"
    return legacy if legacy.is_dir() else root / ".ua"

# Edge types that carry the domain hierarchy. Dropping one of these changes
# downstream graph traversal (unlike a routine `related` edge), so they are
# warned about loudly and re-tried on later runs via merge-report.json —
# subdomain graph files are cleaned up after assembly, so a drop would
# otherwise be permanent even once the missing endpoint's subdomain arrives.
STRUCTURAL_EDGE_TYPES = {"contains_flow", "flow_step", "cross_domain"}


def _num(v: Any) -> float:
    """Coerce a value to float for safe comparison (handles string weights)."""
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def load_graph(path: Path) -> dict[str, Any] | None:
    """Load and minimally validate a knowledge graph JSON file."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"  Skipping {path.name}: {e}", file=sys.stderr)
        return None

    # Must have at minimum nodes and edges arrays
    if not isinstance(data.get("nodes"), list) or not isinstance(data.get("edges"), list):
        print(f"  Skipping {path.name}: missing nodes or edges array", file=sys.stderr)
        return None

    return data


def merge_graphs(graphs: list[dict[str, Any]]) -> tuple[dict[str, Any], list[str], list[dict[str, Any]]]:
    """Merge multiple knowledge graph dicts into one.

    Returns (merged, report_lines, dropped_edges) — dropped_edges holds the
    full edge dicts that were removed for missing endpoints, each with an
    extra "missing" key naming which endpoint(s) were absent.
    """

    # ── Pattern counters for "Fixed" report ──────────────────────────
    node_dedup_by_type: Counter[str] = Counter()

    # ── Detail lists for "Could not fix" report ──────────────────────
    unfixable: list[str] = []

    total_input_nodes = sum(len(g.get("nodes", [])) for g in graphs)
    total_input_edges = sum(len(g.get("edges", [])) for g in graphs)

    # ── Nodes: deduplicate by id, later occurrence wins ───────────────
    nodes_by_id: dict[str, dict] = {}
    for g in graphs:
        for node in g.get("nodes", []):
            nid = node.get("id")
            if not nid:
                unfixable.append(f"Node with no 'id' (name={node.get('name', '?')}, type={node.get('type', '?')})")
                continue
            if nid in nodes_by_id:
                node_type = node.get("type", "?")
                node_dedup_by_type[node_type] += 1
            nodes_by_id[nid] = node

    # ── Edges: deduplicate by (source, target, type), higher weight wins
    edge_dedup_count = 0
    edges_by_key: dict[tuple[str, str, str], dict] = {}
    for g in graphs:
        for edge in g.get("edges", []):
            key = (edge.get("source", ""), edge.get("target", ""), edge.get("type", ""))
            existing = edges_by_key.get(key)
            if existing is None:
                edges_by_key[key] = edge
            else:
                edge_dedup_count += 1
                if _num(edge.get("weight", 0)) > _num(existing.get("weight", 0)):
                    edges_by_key[key] = edge

    # Drop edges referencing missing nodes
    node_ids = set(nodes_by_id.keys())
    valid_edges: list[dict] = []
    dropped_edges: list[dict[str, Any]] = []
    structural_warnings: list[str] = []
    for e in edges_by_key.values():
        src, tgt = e.get("source", ""), e.get("target", "")
        if src in node_ids and tgt in node_ids:
            valid_edges.append(e)
        else:
            missing = []
            if src not in node_ids:
                missing.append(f"source '{src}'")
            if tgt not in node_ids:
                missing.append(f"target '{tgt}'")
            etype = e.get("type", "?")
            dropped_edges.append({**e, "missing": missing})
            if etype in STRUCTURAL_EDGE_TYPES:
                structural_warnings.append(
                    f"Warning: dropped structural edge {src} → {tgt} ({etype}), "
                    f"missing {', '.join(missing)} — will retry on the next merge run"
                )
            else:
                unfixable.append(f"Edge {src} → {tgt} ({etype}): dropped, missing {', '.join(missing)}")

    # ── Layers: merge by id, union nodeIds ────────────────────────────
    layers_by_id: dict[str, dict] = {}
    for g in graphs:
        for layer in g.get("layers", []):
            lid = layer.get("id", "")
            if lid in layers_by_id:
                existing_ids = set(layers_by_id[lid].get("nodeIds", []))
                existing_ids.update(layer.get("nodeIds", []))
                layers_by_id[lid]["nodeIds"] = list(existing_ids)
            else:
                layers_by_id[lid] = {**layer}

    # Drop dangling layer nodeIds
    dropped_layer_refs = 0
    for layer in layers_by_id.values():
        before = len(layer.get("nodeIds", []))
        layer["nodeIds"] = [nid for nid in layer.get("nodeIds", []) if nid in node_ids]
        diff = before - len(layer["nodeIds"])
        if diff:
            dropped_layer_refs += diff

    # ── Tour: concatenate, merge steps with same title ─────────────────
    all_tour_steps: list[dict] = []
    title_to_step: dict[str, dict] = {}
    for g in graphs:
        for step in g.get("tour", []):
            title = step.get("title", "")
            if title in title_to_step:
                # Merge nodeIds from duplicate-titled steps (e.g. both
                # subdomains produce a "Project Overview" step 1)
                existing = title_to_step[title]
                for nid in step.get("nodeIds", []):
                    if nid not in existing.get("nodeIds", []):
                        existing.setdefault("nodeIds", []).append(nid)
                # Keep the longer description
                if len(step.get("description", "")) > len(existing.get("description", "")):
                    existing["description"] = step["description"]
            else:
                new_step = {**step}
                title_to_step[title] = new_step
                all_tour_steps.append(new_step)

    # Drop dangling tour nodeIds and re-number
    dropped_tour_refs = 0
    for i, step in enumerate(all_tour_steps, start=1):
        step["order"] = i
        before = len(step.get("nodeIds", []))
        step["nodeIds"] = [nid for nid in step.get("nodeIds", []) if nid in node_ids]
        diff = before - len(step["nodeIds"])
        if diff:
            dropped_tour_refs += diff

    # ── Project metadata: merge ───────────────────────────────────────
    languages: list[str] = []
    frameworks: list[str] = []
    descriptions: list[str] = []
    latest_at = ""
    latest_hash = ""
    project_name = ""

    for g in graphs:
        proj = g.get("project", {})
        project_name = proj.get("name", "") or project_name
        for lang in proj.get("languages", []):
            if lang not in languages:
                languages.append(lang)
        for fw in proj.get("frameworks", []):
            if fw not in frameworks:
                frameworks.append(fw)
        desc = proj.get("description", "")
        if desc and desc not in descriptions:
            descriptions.append(desc)
        analyzed = proj.get("analyzedAt", "")
        if analyzed > latest_at:
            latest_at = analyzed
            latest_hash = proj.get("gitCommitHash", latest_hash)

    # ── Build report ─────────────────────────────────────────────────
    report: list[str] = []
    report.append(f"Input: {total_input_nodes} nodes, {total_input_edges} edges (from {len(graphs)} graphs)")

    # Fixed section
    fixed_lines: list[str] = []
    if node_dedup_by_type:
        for ntype, count in node_dedup_by_type.most_common():
            fixed_lines.append(f"  {count:>4} × duplicate '{ntype}' nodes removed (kept later)")
    if edge_dedup_count:
        fixed_lines.append(f"  {edge_dedup_count:>4} × duplicate edges removed (kept higher weight)")
    if dropped_layer_refs:
        fixed_lines.append(f"  {dropped_layer_refs:>4} × dangling layer nodeId refs removed")
    if dropped_tour_refs:
        fixed_lines.append(f"  {dropped_tour_refs:>4} × dangling tour nodeId refs removed")

    if fixed_lines:
        total_fixed = sum(node_dedup_by_type.values()) + edge_dedup_count + dropped_layer_refs + dropped_tour_refs
        report.append("")
        report.append(f"Fixed ({total_fixed} corrections):")
        report.extend(fixed_lines)

    # Structural drops surface as loud warnings, not buried counters —
    # losing hierarchy/cross-domain edges changes downstream traversal.
    if structural_warnings:
        report.append("")
        report.extend(structural_warnings)

    # Could not fix section
    if unfixable:
        report.append("")
        report.append(f"Could not fix ({len(unfixable)} issues — needs agent review):")
        for detail in unfixable:
            report.append(f"  - {detail}")

    # Output stats
    report.append("")
    report.append(f"Output: {len(nodes_by_id)} nodes, {len(valid_edges)} edges, {len(layers_by_id)} layers, {len(all_tour_steps)} tour steps")

    merged: dict[str, Any] = {
        "version": "1.0.0",
        "project": {
            "name": project_name,
            "languages": languages,
            "frameworks": frameworks,
            "description": " | ".join(descriptions) if len(descriptions) > 1 else (descriptions[0] if descriptions else ""),
            "analyzedAt": latest_at,
            "gitCommitHash": latest_hash,
        },
        "nodes": list(nodes_by_id.values()),
        "edges": valid_edges,
        "layers": list(layers_by_id.values()),
        "tour": all_tour_steps,
    }

    return merged, report, dropped_edges


def load_pending_structural_edges(report_path: Path) -> list[dict[str, Any]]:
    """Read structural edges dropped by a previous run from merge-report.json.

    Subdomain graph files are cleaned up after assembly, so these edges only
    survive in the report — re-injecting them lets a later run resolve them
    once the missing endpoint's subdomain graph has been merged.
    """
    if not report_path.exists():
        return []
    try:
        data = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"Warning: could not read {report_path.name}: {e}", file=sys.stderr)
        return []
    pending = []
    for entry in data.get("droppedEdges", []):
        if isinstance(entry, dict) and entry.get("type") in STRUCTURAL_EDGE_TYPES:
            pending.append({k: v for k, v in entry.items() if k != "missing"})
    return pending


def write_merge_report(
    report_path: Path,
    merged: dict[str, Any],
    dropped_edges: list[dict[str, Any]],
    recovered_count: int,
) -> None:
    """Persist the dropped-edge report so investigations don't require re-instrumenting the script."""
    report = {
        "generatedBy": "merge-subdomain-graphs.py",
        "output": {
            "nodes": len(merged.get("nodes", [])),
            "edges": len(merged.get("edges", [])),
            "layers": len(merged.get("layers", [])),
            "tourSteps": len(merged.get("tour", [])),
        },
        "recoveredStructuralEdges": recovered_count,
        "droppedEdges": dropped_edges,
    }
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python merge-subdomain-graphs.py <project-root> [file1.json file2.json ...]", file=sys.stderr)
        sys.exit(1)

    project_root = Path(sys.argv[1]).resolve()
    ua_dir = resolve_ua_dir(project_root)

    if not ua_dir.is_dir():
        print(f"Error: {ua_dir} does not exist", file=sys.stderr)
        sys.exit(1)

    output_path = ua_dir / "knowledge-graph.json"

    # Determine which files to merge
    if len(sys.argv) > 2:
        # Explicit file list
        graph_files = [Path(f).resolve() for f in sys.argv[2:]]
    else:
        # Auto-discover subdomain graphs — exclude the main output file
        # to avoid self-merging on repeated runs
        graph_files = sorted(
            p for p in ua_dir.glob("*knowledge-graph*.json")
            if p.name != "knowledge-graph.json"
        )

    if not graph_files:
        print("No subdomain graphs found to merge", file=sys.stderr)
        sys.exit(0)

    print(f"Found {len(graph_files)} subdomain graphs:", file=sys.stderr)
    for f in graph_files:
        print(f"  - {f.name}", file=sys.stderr)

    # Load subdomain graphs
    graphs: list[dict[str, Any]] = []
    for f in graph_files:
        g = load_graph(f)
        if g is not None:
            graphs.append(g)
            node_count = len(g.get("nodes", []))
            edge_count = len(g.get("edges", []))
            print(f"    Loaded {f.name}: {node_count} nodes, {edge_count} edges", file=sys.stderr)

    if not graphs:
        print("Error: no valid subdomain graphs loaded", file=sys.stderr)
        sys.exit(1)

    # Load the existing main graph as base (if it exists)
    if output_path.exists():
        base = load_graph(output_path)
        if base:
            node_count = len(base.get("nodes", []))
            edge_count = len(base.get("edges", []))
            print(f"    Loaded base knowledge-graph.json: {node_count} nodes, {edge_count} edges", file=sys.stderr)
            graphs.insert(0, base)  # Base first — subdomain data wins on conflict

    # Re-inject structural edges a previous run had to drop; if their missing
    # endpoints have arrived in the meantime, this run resolves them.
    report_path = ua_dir / "merge-report.json"
    pending_edges = load_pending_structural_edges(report_path)
    if pending_edges:
        print(f"    Retrying {len(pending_edges)} structural edges dropped by a previous run", file=sys.stderr)
        graphs.append({"nodes": [], "edges": pending_edges})

    # Merge
    merged, report, dropped_edges = merge_graphs(graphs)

    # Print report
    print("", file=sys.stderr)
    for line in report:
        print(line, file=sys.stderr)

    # Count how many previously-dropped structural edges made it in this time
    merged_edge_keys = {(e.get("source", ""), e.get("target", ""), e.get("type", "")) for e in merged["edges"]}
    recovered = sum(
        1 for e in pending_edges
        if (e.get("source", ""), e.get("target", ""), e.get("type", "")) in merged_edge_keys
    )
    if recovered:
        print(f"Recovered {recovered} structural edges dropped by a previous run", file=sys.stderr)

    # Write output
    output_path.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")
    write_merge_report(report_path, merged, dropped_edges, recovered)
    print(f"Merge report written to {report_path}", file=sys.stderr)

    size_kb = output_path.stat().st_size / 1024
    print(f"\nWritten to {output_path} ({size_kb:.0f} KB)", file=sys.stderr)


if __name__ == "__main__":
    main()

```

## File: .skills/understand-anything/understand-domain/extract-domain-context.py

```python
#!/usr/bin/env python3
"""
extract-domain-context.py — Lightweight codebase scanner for domain knowledge extraction.

Scans a project directory and produces a structured JSON context file that the
domain-analyzer agent uses to identify business domains, flows, and steps.

Usage:
    python extract-domain-context.py <project-root>

Output:
    <ua-dir>/intermediate/domain-context.json, where <ua-dir> is `.ua/` (or
    legacy `.understand-anything/` when that directory already exists).
"""

import json
import os
import re
import sys
from pathlib import Path
from typing import Any


def resolve_ua_dir(root: Path) -> Path:
    """Mirror core resolveUaDir: legacy .understand-anything/ wins if present."""
    legacy = root / ".understand-anything"
    return legacy if legacy.is_dir() else root / ".ua"

# ── Configuration ──────────────────────────────────────────────────────────

MAX_FILE_TREE_DEPTH = 6
MAX_FILES_PER_DIR = 50
MAX_FILES_TOTAL = 5000
MAX_SAMPLED_FILES = 40
MAX_LINES_PER_FILE = 80
MAX_ENTRY_POINTS = 200
MAX_OUTPUT_BYTES = 512 * 1024  # 512 KB — keeps output within agent context limits

# File extensions we care about for domain analysis
SOURCE_EXTENSIONS = {
    ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
    ".py", ".pyi",
    ".go",
    ".rs",
    ".java", ".kt", ".scala",
    ".rb",
    ".cs",
    ".php",
    ".swift",
    ".c", ".cpp", ".h", ".hpp",
    ".ex", ".exs",
    ".hs",
    ".lua",
    ".r", ".R",
}

# Directories to always skip
SKIP_DIRS = {
    "node_modules", ".git", ".svn", ".hg", "__pycache__", ".tox",
    "venv", ".venv", "env", ".env", "dist", "build", "out", ".next",
    ".nuxt", "target", "vendor", ".idea", ".vscode", "coverage",
    ".understand-anything", ".ua", ".pytest_cache", ".mypy_cache",
    "Pods", "DerivedData", ".gradle", "bin", "obj",
}

# Files that reveal project metadata
METADATA_FILES = [
    "package.json", "Cargo.toml", "go.mod", "pyproject.toml",
    "setup.py", "setup.cfg", "pom.xml", "build.gradle",
    "Gemfile", "composer.json", "mix.exs", "Makefile",
    "docker-compose.yml", "docker-compose.yaml",
    "README.md", "README.rst", "README.txt", "README",
]

# ── Entry point detection patterns ─────────────────────────────────────────

ENTRY_POINT_PATTERNS: list[tuple[str, str, re.Pattern[str]]] = [
    # HTTP routes
    ("http", "Express/Koa route", re.compile(
        r"""(?:app|router|server)\s*\.\s*(?:get|post|put|patch|delete|all|use)\s*\(\s*['"](/[^'"]*?)['"]""",
        re.IGNORECASE,
    )),
    ("http", "Decorator route (Flask/FastAPI/NestJS)", re.compile(
        r"""@(?:app\.)?(?:route|get|post|put|patch|delete|api_view|RequestMapping|GetMapping|PostMapping)\s*\(\s*['"](/[^'"]*?)['"]""",
        re.IGNORECASE,
    )),
    ("http", "Next.js/Remix route handler", re.compile(
        r"""export\s+(?:async\s+)?function\s+(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\b""",
    )),
    # CLI
    ("cli", "CLI command", re.compile(
        r"""\.command\s*\(\s*['"]([\w\-:]+)['"]""",
    )),
    ("cli", "argparse subparser", re.compile(
        r"""add_parser\s*\(\s*['"]([\w\-]+)['"]""",
    )),
    # Event handlers
    ("event", "Event listener", re.compile(
        r"""\.on\s*\(\s*['"]([\w\-:.]+)['"]""",
    )),
    ("event", "Event subscriber decorator", re.compile(
        r"""@(?:EventHandler|Subscribe|Listener|on_event)\s*\(\s*['"]([\w\-:.]+)['"]""",
    )),
    # Cron / scheduled
    ("cron", "Cron schedule", re.compile(
        r"""@?(?:Cron|Schedule|Scheduled|crontab)\s*\(\s*['"]([^'"]+)['"]""",
        re.IGNORECASE,
    )),
    # GraphQL
    ("http", "GraphQL resolver", re.compile(
        r"""@(?:Query|Mutation|Subscription|Resolver)\s*\(""",
    )),
    # gRPC (only in .proto files — handled by file extension check below)
    ("http", "gRPC service", re.compile(
        r"""^service\s+(\w+)\s*\{""", re.MULTILINE,
    )),
    # Exported handlers (generic)
    ("manual", "Exported handler", re.compile(
        r"""export\s+(?:async\s+)?function\s+(handle\w+|process\w+|on\w+)\b""",
    )),
]


# ── Gitignore support ──────────────────────────────────────────────────────

def parse_gitignore(project_root: Path) -> list[re.Pattern[str]]:
    """Parse .gitignore into a list of compiled regex patterns."""
    gitignore = project_root / ".gitignore"
    patterns: list[re.Pattern[str]] = []
    if not gitignore.exists():
        return patterns

    for line in gitignore.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Convert glob to regex (simplified)
        regex = line.replace(".", r"\.").replace("**/", "(.*/)?").replace("*", "[^/]*").replace("?", "[^/]")
        if line.endswith("/"):
            regex = regex.rstrip("/") + "(/|$)"
        try:
            patterns.append(re.compile(regex))
        except re.error as e:
            print(f"Warning: skipping invalid gitignore pattern '{line}': {e}", file=sys.stderr)
    return patterns


def is_ignored(rel_path: str, gitignore_patterns: list[re.Pattern[str]]) -> bool:
    """Check if a relative path matches any gitignore pattern."""
    for pattern in gitignore_patterns:
        if pattern.search(rel_path):
            return True
    return False


# ── File tree scanner ──────────────────────────────────────────────────────

def scan_file_tree(
    root: Path,
    gitignore_patterns: list[re.Pattern[str]],
    max_depth: int = MAX_FILE_TREE_DEPTH,
) -> list[str]:
    """Return a flat list of relative file paths (source files only)."""
    result: list[str] = []

    def _walk(dir_path: Path, depth: int) -> None:
        if depth > max_depth or len(result) >= MAX_FILES_TOTAL:
            return
        try:
            entries = sorted(dir_path.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
        except PermissionError:
            return

        file_count = 0
        for entry in entries:
            if len(result) >= MAX_FILES_TOTAL:
                break
            # Skip symlinks to avoid infinite loops
            if entry.is_symlink():
                continue
            rel = str(entry.relative_to(root))
            if entry.is_dir():
                if entry.name in SKIP_DIRS:
                    continue
                if is_ignored(rel + "/", gitignore_patterns):
                    continue
                _walk(entry, depth + 1)
            elif entry.is_file():
                if file_count >= MAX_FILES_PER_DIR:
                    break
                if entry.suffix not in SOURCE_EXTENSIONS:
                    continue
                if is_ignored(rel, gitignore_patterns):
                    continue
                result.append(rel)
                file_count += 1

    _walk(root, 0)
    return result


# ── Entry point detection ──────────────────────────────────────────────────

def detect_entry_points(root: Path, file_paths: list[str]) -> list[dict[str, Any]]:
    """Scan source files for entry point patterns."""
    entry_points: list[dict[str, Any]] = []

    # Skip test files and the extraction script itself
    test_patterns = re.compile(r"(?:\.test\.|\.spec\.|__tests__|_test\.py|test_\w+\.py|extract-domain-context\.py)")

    for rel_path in file_paths:
        if len(entry_points) >= MAX_ENTRY_POINTS:
            break
        if test_patterns.search(rel_path):
            continue
        full_path = root / rel_path
        try:
            content = full_path.read_text(encoding="utf-8", errors="replace")
        except (OSError, UnicodeDecodeError):
            continue

        lines = content.splitlines()
        for entry_type, description, pattern in ENTRY_POINT_PATTERNS:
            for match in pattern.finditer(content):
                # Find line number
                line_no = content[:match.start()].count("\n") + 1
                # Extract a snippet (signature + a few lines)
                start = max(0, line_no - 1)
                end = min(len(lines), start + 5)
                snippet = "\n".join(lines[start:end])

                entry_points.append({
                    "file": rel_path,
                    "line": line_no,
                    "type": entry_type,
                    "description": description,
                    "match": match.group(0)[:120],
                    "snippet": snippet[:300],
                })

                if len(entry_points) >= MAX_ENTRY_POINTS:
                    break
            if len(entry_points) >= MAX_ENTRY_POINTS:
                break

    return entry_points


# ── File signatures ────────────────────────────────────────────────────────

def extract_file_signatures(root: Path, file_paths: list[str]) -> list[dict[str, Any]]:
    """Extract exports and imports from each file (lightweight)."""
    signatures: list[dict[str, Any]] = []

    # Prioritize files likely to contain business logic
    priority_keywords = [
        "controller", "service", "handler", "router", "route", "api",
        "model", "entity", "repository", "usecase", "use_case",
        "command", "query", "event", "subscriber", "listener",
        "middleware", "guard", "interceptor", "resolver",
        "workflow", "flow", "process", "pipeline", "job", "task",
    ]

    def priority_score(path: str) -> int:
        lower = path.lower()
        score = 0
        for kw in priority_keywords:
            if kw in lower:
                score += 1
        return score

    sorted_paths = sorted(file_paths, key=priority_score, reverse=True)

    for rel_path in sorted_paths[:MAX_SAMPLED_FILES]:
        full_path = root / rel_path
        try:
            content = full_path.read_text(encoding="utf-8", errors="replace")
        except (OSError, UnicodeDecodeError):
            continue

        lines = content.splitlines()[:MAX_LINES_PER_FILE]
        truncated = "\n".join(lines)

        # Extract exports (JS/TS)
        exports = re.findall(
            r"export\s+(?:default\s+)?(?:async\s+)?(?:function|class|const|let|var|interface|type|enum)\s+(\w+)",
            truncated,
        )
        # Extract exports (Python)
        if not exports:
            exports = re.findall(r"^(?:def|class)\s+(\w+)", truncated, re.MULTILINE)

        # Extract imports (first 20)
        imports = re.findall(
            r"""(?:import\s+.*?from\s+['"]([^'"]+)['"]|from\s+([\w.]+)\s+import)""",
            truncated,
        )
        import_list = [m[0] or m[1] for m in imports][:20]

        signatures.append({
            "file": rel_path,
            "exports": exports[:20],
            "imports": import_list,
            "lines": len(content.splitlines()),
            "preview": truncated[:500],
        })

    return signatures


# ── Metadata extraction ────────────────────────────────────────────────────

def extract_metadata(root: Path) -> dict[str, Any]:
    """Read project metadata files."""
    metadata: dict[str, Any] = {}

    for filename in METADATA_FILES:
        filepath = root / filename
        if not filepath.exists():
            continue
        try:
            content = filepath.read_text(encoding="utf-8", errors="replace")
        except (OSError, UnicodeDecodeError):
            continue

        if filename == "package.json":
            try:
                pkg = json.loads(content)
                metadata["package.json"] = {
                    "name": pkg.get("name"),
                    "description": pkg.get("description"),
                    "scripts": list((pkg.get("scripts") or {}).keys()),
                    "dependencies": list((pkg.get("dependencies") or {}).keys()),
                    "devDependencies": list((pkg.get("devDependencies") or {}).keys()),
                }
            except json.JSONDecodeError:
                metadata["package.json"] = content[:500]
        elif filename.endswith((".md", ".rst", ".txt")) or filename == "README":
            metadata[filename] = content[:2000]
        elif filename.endswith((".toml", ".cfg", ".mod")):
            metadata[filename] = content[:1000]
        elif filename.endswith((".json", ".yml", ".yaml", ".xml", ".gradle")):
            metadata[filename] = content[:1000]

    return metadata


# ── Main ───────────────────────────────────────────────────────────────────

def _truncate_to_fit(context: dict[str, Any]) -> dict[str, Any]:
    """Progressively trim context sections to stay under MAX_OUTPUT_BYTES."""
    output = json.dumps(context, indent=2)
    if len(output.encode()) <= MAX_OUTPUT_BYTES:
        return context

    # 1. Trim file tree to just a count
    context["fileTree"] = context["fileTree"][:200]
    output = json.dumps(context, indent=2)
    if len(output.encode()) <= MAX_OUTPUT_BYTES:
        return context

    # 2. Trim previews in signatures
    for sig in context.get("fileSignatures", []):
        sig["preview"] = sig["preview"][:200]
    output = json.dumps(context, indent=2)
    if len(output.encode()) <= MAX_OUTPUT_BYTES:
        return context

    # 3. Trim snippets in entry points
    for ep in context.get("entryPoints", []):
        ep["snippet"] = ep["snippet"][:100]
    output = json.dumps(context, indent=2)
    if len(output.encode()) <= MAX_OUTPUT_BYTES:
        return context

    # 4. Reduce number of signatures and entry points
    context["fileSignatures"] = context["fileSignatures"][:20]
    context["entryPoints"] = context["entryPoints"][:100]

    return context


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python extract-domain-context.py <project-root>", file=sys.stderr)
        sys.exit(1)

    project_root = Path(sys.argv[1]).resolve()
    if not project_root.is_dir():
        print(f"Error: {project_root} is not a directory", file=sys.stderr)
        sys.exit(1)

    try:
        # Ensure output directory exists
        output_dir = resolve_ua_dir(project_root) / "intermediate"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "domain-context.json"

        print(f"Scanning {project_root} ...", file=sys.stderr)

        gitignore_patterns = parse_gitignore(project_root)
        file_tree = scan_file_tree(project_root, gitignore_patterns)
        print(f"  Found {len(file_tree)} source files", file=sys.stderr)

        entry_points = detect_entry_points(project_root, file_tree)
        print(f"  Detected {len(entry_points)} entry points", file=sys.stderr)

        signatures = extract_file_signatures(project_root, file_tree)
        print(f"  Extracted {len(signatures)} file signatures", file=sys.stderr)

        metadata = extract_metadata(project_root)
        print(f"  Read {len(metadata)} metadata files", file=sys.stderr)

        context = {
            "projectRoot": str(project_root),
            "fileCount": len(file_tree),
            "fileTree": file_tree,
            "entryPoints": entry_points,
            "fileSignatures": signatures,
            "metadata": metadata,
        }

        context = _truncate_to_fit(context)
        output = json.dumps(context, indent=2)
        output_path.write_text(output, encoding="utf-8")
        size_kb = len(output.encode()) / 1024
        print(f"  Wrote {output_path} ({size_kb:.0f} KB)", file=sys.stderr)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

```
