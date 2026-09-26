# ChzzkTube Project Full Codebase


## File: app_pilot_hook.py

```python
import json
from PySide6.QtCore import QObject, Qt
from PySide6.QtNetwork import QTcpServer, QHostAddress
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

class QtPilotHook(QObject):
    def __init__(self, main_window: QWidget, port: int = 49152):
        super().__init__()
        self.window = main_window
        self.server = QTcpServer(self)
        self.server.newConnection.connect(self._handle_connection)
        self.server.listen(QHostAddress.LocalHost, port)

    def _handle_connection(self):
        socket = self.server.nextPendingConnection()
        socket.readyRead.connect(lambda: self._process_command(socket))

    def _process_command(self, socket):
        raw_data = socket.readAll().data().decode("utf-8")
        try:
            cmd = json.loads(raw_data)
        except json.JSONDecodeError:
            return

        action = cmd.get("action")
        response = {"status": "ok"}

        if action == "dump_tree":
            response["widgets"] = [
                {"name": w.objectName(), "class": w.metaObject().className(), "visible": w.isVisible()}
                for w in self.window.findChildren(QWidget) if w.objectName()
            ]

        elif action == "capture":
            target_name = cmd.get("target")
            target = self.window.findChild(QWidget, target_name) if target_name else self.window
            if target:
                pixmap = target.grab()
                save_path = cmd.get("path", "ui_debug.png")
                pixmap.save(save_path)
                response["path"] = save_path
            else:
                response = {"status": "error", "message": "Widget not found"}

        elif action == "click":
            target = self.window.findChild(QWidget, cmd.get("target"))
            if target:
                QTest.mouseClick(target, Qt.MouseButton.LeftButton)
            else:
                response = {"status": "error", "message": "Widget not found"}

        elif action == "type":
            target = self.window.findChild(QWidget, cmd.get("target"))
            text = cmd.get("text", "")
            if target:
                target.setFocus()
                QTest.keyClicks(target, text)
            else:
                response = {"status": "error", "message": "Widget not found"}

        socket.write(json.dumps(response).encode("utf-8"))
        socket.flush()
        socket.disconnectFromHost()


```

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

## File: find_exceptions.py

```python
import os
import sys

results = []
for r, _, fs in os.walk('chzzktube'):
    for f in fs:
        if f.endswith('.py'):
            path = os.path.join(r, f)
            try:
                with open(path, 'r', encoding='utf-8') as fp:
                    for i, line in enumerate(fp, 1):
                        stripped = line.strip()
                        if stripped == 'except Exception:' or stripped == 'except:' or (stripped.startswith('except Exception as') and 'pass' in stripped):
                            results.append(f'{path}:{i}: {stripped}')
            except:
                pass

print('\n'.join(results[:100]))
```

## File: fix_indent.py

```python
import re

with open('chzzktube/pipeline/live_recorder.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix 1: Remove the extra .strip(), and closing parens after the exception handler
old = '''raw_log.raw("LIVE", f"_drain_stderr error: {type(e).__name__}: {e}", is_error=True, to_tui=False).strip(),
                                      ),
'''

new = ''

if old in content:
    content = content.replace(old, new)
    with open('chzzktube/pipeline/live_recorder.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Fixed indentation!')
else:
    print('Old text not found, searching...')
    idx = content.find('raw_log.raw("LIVE", f"_drain_stderr error:')
    if idx >= 0:
        print(repr(content[idx:idx+150]))
```

## File: fix_indent2.py

```python
with open('chzzktube/pipeline/live_recorder.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the specific indentation issue
old = 'raw_log.raw("LIVE", f"_drain_stderr error: {type(e).__name__}: {e}", is_error=True, to_tui=False).strip(),\n                                      ),'

new = ''

if old in content:
    content = content.replace(old, new)
    with open('chzzktube/pipeline/live_recorder.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Fixed!')
else:
    print('Not found - searching with regex...')
    # Try regex
    pattern = r'raw_log\.raw\("LIVE", f"_drain_stderr error: \{type\(e\)\.__name__\}: \{e\}", is_error=True, to_tui=False\)\.strip\(\),\n\s+\),'
    match = re.search(old.replace('{', r'\{').replace('}', r'\}'), content, re.DOTALL)
    if match:
        print('Regex match found')
        content = re.sub(pattern, '', content, flags=re.DOTALL)
        with open('chzzktube/pipeline/live_recorder.py', 'w', encoding='utf-8') as f:
            f.write(content)
        print('Fixed via regex!')
    else:
        print('Regex not found')
        idx = content.find('raw_log.raw("LIVE", f"_drain_stderr error:')
        if idx >= 0:
            print(repr(content[idx:idx+150]))
```

## File: fix_indent3.py

```python
import re

with open('chzzktube/pipeline/live_recorder.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the specific indentation issue - there's a trailing .strip(), and extra )
old = 'raw_log.raw("LIVE", f"_drain_stderr error: {type(e).__name__}: {e}", is_error=True, to_tui=False).strip(),\n                                      ),'

new = ''

if old in content:
    content = content.replace(old, new)
    with open('chzzktube/pipeline/live_recorder.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Fixed!')
else:
    print('Old text not found, searching...')
    idx = content.find('raw_log.raw("LIVE", f"_drain_stderr error:')
    if idx >= 0:
        print(repr(content[idx:idx+150]))
        # Fix with regex
        pattern = r'raw_log\.raw\("LIVE", f"_drain_stderr error: \{type\(e\)\.__name__\}: \{e\}", is_error=True, to_tui=False\)\.strip\(\),\n\s+\),'
        new_content = re.sub(pattern, '', content, flags=re.DOTALL)
        if new_content != content:
            with open('chzzktube/pipeline/live_recorder.py', 'w', encoding='utf-8') as f:
                f.write(new_content)
            print('Fixed via regex!')
        else:
            print('Regex not matched')
```

## File: fix_lr_final.py

```python
import re

with open('chzzktube/pipeline/live_recorder.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the extra closing parenthesis and blank line in the except block
old = '''                except Exception as e:

                )'''

new = '''                except Exception as e:
                    import chzzktube.core.raw_log as raw_log
                    raw_log.raw("LIVE", f"_drain_stderr error: {type(e).__name__}: {e}", is_error=True, to_tui=False)'''

if old in content:
    content = content.replace(old, new)
    with open('chzzktube/pipeline/live_recorder.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Fixed!')
else:
    print('Not found')
    idx = content.find('except Exception as e:')
    if idx >= 0:
        print('Found at:', idx)
        print(repr(content[idx:idx+100]))
```

## File: fix_lr_line.py

```python
with open('chzzktube/pipeline/live_recorder.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Fix lines 241-244
new_lines = []
for i, line in enumerate(lines):
    # Fix the except block (lines 241-244 in 1-indexed)
    if i == 240:  # "                except Exception as e:" (0-indexed)
        new_lines.append(line)
    elif i == 241:  # blank line after except
        continue  # Skip blank line
    elif i == 242:  # the extra )
        continue  # Skip extra )
    else:
        new_lines.append(line)

with open('chzzktube/pipeline/live_recorder.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print('Fixed!')
```

## File: fix_paren.py

```python
with open('chzzktube/pipeline/live_recorder.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find and fix the problematic lines
new_lines = []
i = 0
while i < len(lines):
    line = lines[i]
    # Check for the problematic pattern: blank line followed by single )
    if (i > 0 and lines[i-1].strip() == '' and 
        line.strip() == ')' and 
        i > 1 and 'except Exception as e:' in lines[i-2]):
        print(f'Fixing line {i+1}: removing extra )')
        i += 1  # Skip this line
        continue
    new_lines.append(line)
    i += 1

with open('chzzktube/pipeline/live_recorder.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print('Fixed extra closing parenthesis!')
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
with open('tests/test_provisioning_stdlib.py', 'r') as f:
    content = f.read()

old = '''class TestProvisioningManagerStdlib:
    @pytest.mark.parametrize(
        ("method_name", "payload", "expected"),
        [
            (
                "_fetch_from_pypi",
                {
                    "info": {"version": "1.2.3"},
                    "releases": {
                        "1.2.3": [
                            {"filename": "demo-1.2.3-py3-none-any.whl", "url": "https://packages.invalid/demo.whl", "digests": {"sha256": "a" * 64}},
                        ]
                    },
                },
                (
                    "1.2.3",
                    "https://packages.invalid/demo.whl",
                    "a" * 64,
                    "pypi",
                    "whl",
                ),
            ),
            (
                "_fetch_from_github",
                {
                                       ",
                    "assets": [
                        {"name": "demo-1.2.3-darwin-arm64.zip", "browser_download_url": "https://releases.invalid/demo.zip"},
                    ],
                },
                (
                    "v1.2.3",
                    "https://releases.invalid/demo.zip",
                    None,
                    "github",
                    "zip",
                ),
            ),
            (
                "_fetch_from_nodejs",
                [{"version": "v22.1.0"}],
                (
                    "v22.1.0",
                    "https://nodejs.org/dist/v22.1.0/node-v22.1.0-darwin-arm64.tar.gz",
                    "93904abf2b6afd0dc2a7c2947a83e10ed65cc39171db17663edb6f763aaa5a57",
                    "nodejs.org",
                    "tar.gz",
                ),
            ),
        ],
    )
    def test_metadata_fetchers_work_without_httpx(
        self, method_name, payload, expected
    ):
        manager_module = _import_without_httpx(
            "chzzktube.infra.provisioning.manager"
        )
        manager = manager_module.ProvisioningManager.__new__(
            manager_module.ProvisioningManager
        )
        method = getattr(manager, method_name)
        spec = SimpleNamespace(name="demo", asset_filters=())
        mirror = SimpleNamespace(
            name="github" if method_name == "_fetch_from_github" else (
                "nodejs.org" if method_name == "_fetch_from_nodejs" else "pypi"
            ),
            url_template="https://metadata.invalid/{pkg}.json",
        )

        async def run_fetch():
            manager._fetch_json = AsyncMock(return_value=payload)
            manager._fetch_text = AsyncMock(return_value="93904abf2b6afd0dc2a7c2947a83e10ed65cc39171db17663edb6f763aaa5a57  node-v22.1.0-darwin-arm64.tar.gz")
            return await method(spec, mirror)

        assert asyncio.run(run_fetch()) == expected

    def test_fetch_latest_falls_back_to_next_mirror(self):
        manager_module = _import_without_httpx(
            "chzzktube.infra.provisioning.manager"
        )
        manager = manager_module.ProvisioningManager.__new__(
            manager_module.ProvisioningManager
        )
        mirrors = (
            Mirror(
                name="pypi",
                url_template="https://metadata.invalid/{pkg}.json",
                priority=0,
            ),
            Mirror(
                name="github",
                url_template="https://metadata.invalid/releases/latest",
                priority=1,
            ),
        )
        spec = ComponentSpec(
            name="demo",
            type=ComponentType.PYTHON_PKG,
            mirrors=mirrors,
            verify_cmd=(),
            install_rel_path=".pylib",
            asset_filters=(),
        )

        async def run_resolve():
            async def fetch_from_pypi(spec, mirror):
                assert mirror is mirrors[0]
                return None

            async def fetch_from_github(spec, mirror):
                assert mirror is mirrors[1]
                return (
                    "1.2.3",
                    "https://packages.invalid/demo.whl",
                    None,
                    "github",
                    "zip",
                )

            manager._fetch_from_pypi = fetch_from_pypi
            manager._fetch_from_github = fetch_from_github
            return await manager._fetch_latest(spec)

        assert asyncio.run(run_resolve()) == (
            "1.2.3",
            "https://packages.invalid/demo.whl",
            None,
            "github",
            "zip",
        )'''

new = '''class TestProvisioningManagerStdlib:
    def test_manager_imports_without_httpx(self):
        manager_module = _import_without_httpx(
            "chzzktube.infra.provisioning.manager"
        )
        assert hasattr(manager_module, "ProvisioningManager")

    @pytest.mark.parametrize(
        ("method_name", "payload", "expected"),
        [
            (
                "_fetch_from_pypi",
                {
                    "info": {"version": "1.2.3"},
                    "releases": {
                        "1.2.3": [
                            {"filename": "demo-1.2.3-py3-none-any.whl", "url": "https://packages.invalid/demo.whl", "digests": {"sha256": "a" * 64}},
                        ]
                    },
                },
                (
                    "1.2.3",
                    "https://packages.invalid/demo.whl",
                    "a" * 64,
                    "pypi",
                    "whl",
                ),
            ),
            (
                "_fetch_from_github",
                {
                    "tag_name": "v1.2.3",
                    "assets": [
                        {"name": "demo-1.2.3-darwin-arm64.zip", "browser_download_url": "https://releases.invalid/demo.zip"},
                    ],
                },
                (
                    "v1.2.3",
                    "https://releases.invalid/demo.zip",
                    None,
                    "github",
                    "zip",
                ),
            ),
            (
                "_fetch_from_nodejs",
                [{"version": "v22.1.0"}],
                (
                    "v22.1.0",
                    "https://nodejs.org/dist/v22.1.0/node-v22.1.0-darwin-arm64.tar.gz",
                    "93904abf2b6afd0dc2a7c2947a83e10ed65cc39171db17663edb6f763aaa5a57",
                    "nodejs.org",
                    "tar.gz",
                ),
            ),
        ],
    )
    def test_metadata_fetchers_work_without_httpx(
        self, method_name, payload, expected
    ):
        # 이제 Planner 클래스에서 테스트 (리팩토링 후)
        planner_module = _import_without_httpx(
            "chzzktube.infra.provisioning.planner"
        )
        planner = planner_module.Planner.__new__(planner_module.Planner)
        from pathlib import Path
        planner.base_dir = Path("/tmp")
        from chzzktube.infra.provisioning.manifest import ProvisionManifest
        planner.manifest = ProvisionManifest()
        planner.overlay_root = Path("/tmp/.pylib")
        method = getattr(planner, method_name)
        spec = SimpleNamespace(name="demo", asset_filters=())
        mirror = SimpleNamespace(
            name="github" if method_name == "_fetch_from_github" else (
                "nodejs.org" if method_name == "_fetch_from_nodejs" else "pypi"
            ),
            url_template="https://metadata.invalid/{pkg}.json",
        )

        async def run_fetch():
            planner._fetch_json = AsyncMock(return_value=payload)
            planner._fetch_text = AsyncMock(return_value="93904abf2b6afd0dc2a7c2947a83e10ed65cc39171db17663edb6f763aaa5a57  node-v22.1.0-darwin-arm64.tar.gz")
            return await method(spec, mirror)

        assert asyncio.run(run_fetch()) == expected

    def test_fetch_latest_falls_back_to_next_mirror(self):
        # Planner.resolve() 메서드 테스트 (리팩토링 후)
        planner_module = _import_without_httpx(
            "chzzktube.infra.provisioning.planner"
        )
        planner = planner_module.Planner.__new__(planner_module.Planner)
        from pathlib import Path
        planner.base_dir = Path("/tmp")
        from chzzktube.infra.provisioning.manifest import ProvisionManifest
        planner.manifest = ProvisionManifest()
        planner.overlay_root = Path("/tmp/.pylib")
        mirrors = (
            Mirror(
                name="pypi",
                url_template="https://metadata.invalid/{pkg}.json",
                priority=0,
            ),
            Mirror(
                name="github",
                url_template="https://metadata.invalid/releases/latest",
                priority=1,
            ),
        )
        spec = ComponentSpec(
            name="demo",
            type=ComponentType.PYTHON_PKG,
            mirrors=mirrors,
            verify_cmd=(),
            install_rel_path=".pylib",
            asset_filters=(),
        )

        async def run_resolve():
            async def fetch_from_pypi(spec, mirror):
                assert mirror is mirrors[0]
                return None

            async def fetch_from_github(spec, mirror):
                assert mirror is mirrors[1]
                return (
                    "1.2.3",
                    "https://packages.invalid/demo.whl",
                    None,
                    "github",
                    "zip",
                )

            planner._fetch_from_pypi = fetch_from_pypi
            planner._fetch_from_github = fetch_from_github
            return await planner._fetch_latest(spec)

        assert asyncio.run(run_resolve()) == (
            "1.2.3",
            "https://packages.invalid/demo.whl",
            None,
            "github",
            "zip",
        )'''

if old in content:
    content = content.replace(old, new)
    with open('tests/test_provisioning_stdlib.py', 'w') as f:
        f.write(content)
    print('Fixed')
else:
    print('NOT FOUND - trying alternative')
    # Try with slightly different spacing
    import re
    # Find the class definition
    match = re.search(r'class TestProvisioningManagerStdlib:.*?(?=\nclass |\Z)', content, re.DOTALL)
    if match:
        print(f'Found at position {match.start()}')
        print(content[match.start():match.start()+200])
    else:
        print('Class not found with regex')

```

## File: fix_updater.py

```python
import pathlib

content = pathlib.Path('chzzktube/infra/updater.py').read_text(encoding='utf-8')

# _frozen_upgrade_streamlink 함수 전체 제거
start = content.find('def _frozen_upgrade_streamlink():')
if start >= 0:
    next_def = content.find('\ndef ', start + 1)
    if next_def < 0:
        next_def = len(content)
    content = content[:start] + content[next_def:]

# upgrade_packages 함수가 _refresh_overlay_sys_path 함수 이후에 올바르게 위치하도록 추가
insert_pos = content.find('def _refresh_overlay_sys_path():')
if insert_pos >= 0:
    next_def = content.find('\ndef ', insert_pos + 1)
    if next_def < 0:
        next_def = len(content)
    upgrade_func = '''

def upgrade_packages(packages, channel="stable"):
    """직접 다운로드 방식으로 패키지 업데이트 (Dev/Frozen 통합).

    [v3.4.0 변경] 해제 대상은 프로젝트 오버레이(.pylib/) -- venv(site-packages,
    uv 소유)는 절대 건드리지 않는다. 요약 문자열에 "(overlay)" 표기.
    이유: 포터블 빌드와 Dev에서 동일한 코드 경로를 타야 디버깅이 가능.
    pip install은 빌드 시에만 사용 (PyInstaller 번들 시점).

    Returns (returncode, output tail). Worker thread only.
    """
    # yt-dlp: Dev/Frozen 통합 - 직접 다운로드 (yt_dlp_binary 위임)
    if "yt-dlp" in packages:
        return _frozen_upgrade_ytdlp(channel)
'''
    content = content[:next_def] + upgrade_func + content[next_def:]

pathlib.Path('chzzktube/infra/updater.py').write_text(content, encoding='utf-8')
print('Done')
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
import chzzktube.infra.cleanup as _cleanup
import chzzktube.infra.pylib_bootstrap as _pylib_bootstrap

_PYLIB_PATH = _pylib_bootstrap.bootstrap()

# 앱 기동 시 이전 세션 잔재 정리
_cleanup.cleanup_on_startup()

from chzzktube.ui.main_window import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())

```

## File: qt_pilot_server.py

```python
import json
import socket
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("qt-pilot")

import time

def send_ipc(command: dict, wait_seconds: float = 8.0) -> dict:
    start = time.time()
    last_err = None
    while time.time() - start < wait_seconds:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
                client.settimeout(4.0)
                client.connect(("127.0.0.1", 49152))
                client.sendall(json.dumps(command).encode("utf-8"))
                res = client.recv(65536)
                return json.loads(res.decode("utf-8"))
        except (ConnectionRefusedError, socket.timeout, OSError) as e:
            last_err = e
            time.sleep(0.3)
    raise ConnectionError(f"Cannot connect to PySide6 QtPilotHook on port 49152: {last_err}")

@mcp.tool()
def get_widget_tree() -> str:
    """현재 화면에 활성화된 위젯의 objectName, 클래스, 가시성 목록을 조회합니다."""
    res = send_ipc({"action": "dump_tree"})
    return json.dumps(res.get("widgets", []), indent=2)

@mcp.tool()
def capture_ui(target_object_name: str = "", output_path: str = "debug_screenshot.png") -> str:
    """전체 창 또는 특정 위젯을 캡처하여 로컬 이미지 파일로 저장합니다."""
    res = send_ipc({"action": "capture", "target": target_object_name, "path": output_path})
    return f"Screenshot saved to {res.get('path')}"

@mcp.tool()
def click_widget(target_object_name: str) -> str:
    """지정된 objectName을 가진 위젯(버튼, 탭 등)을 클릭합니다."""
    res = send_ipc({"action": "click", "target": target_object_name})
    return res.get("status", "error")

# qt_pilot_server.py 하단에 추가
@mcp.tool()
def type_text(target_object_name: str, text: str) -> str:
    """지정된 objectName을 가진 입력창(QLineEdit 등)에 텍스트를 입력합니다."""
    res = send_ipc({"action": "type", "target": target_object_name, "text": text})
    return res.get("status")


@mcp.tool()
def capture_sequence(count: int = 3, interval: float = 1.0, prefix: str = "startup") -> str:
    """기동 과정 중 여러 시점의 화면을 연속으로 캡처합니다."""
    paths = []
    for i in range(count):
        path = f"{prefix}_{i+1}.png"
        res = send_ipc({"action": "capture", "target": "", "path": path}, wait_seconds=8.0 if i == 0 else 2.0)
        paths.append(res.get("path", path))
        if i < count - 1:
            time.sleep(interval)
    return f"Sequence saved: {', '.join(paths)}"

if __name__ == "__main__":
    mcp.run()


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
    "chzzktube.ui.log_mirror",
    "chzzktube.ui.main_window",
    "chzzktube.ui.theme",
    # chzzktube.ui.components
    "chzzktube.ui.components.action_bar",
    "chzzktube.ui.components.header_bar",
    # chzzktube.control
    "chzzktube.control.controller",
    "chzzktube.control.gate_state",
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
    # chzzktube.pipeline.target_downloader (package)
    "chzzktube.pipeline.target_downloader.__init__",
    "chzzktube.pipeline.target_downloader.chzzk",
    "chzzktube.pipeline.target_downloader.dispatch",
    "chzzktube.pipeline.target_downloader.flatten",
    "chzzktube.pipeline.target_downloader.options",
    "chzzktube.pipeline.target_downloader.utils",
    "chzzktube.pipeline.target_downloader.youtube_live",
    "chzzktube.pipeline.target_downloader.youtube_vod",
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
    # chzzktube.infra.provisioning (flat basename 충돌 회피: provisioning_<name>.md)
    "chzzktube.infra.provisioning.bridge",
    "chzzktube.infra.provisioning.committer",
    "chzzktube.infra.provisioning.downloader",
    "chzzktube.infra.provisioning.executor",
    "chzzktube.infra.provisioning.manager",
    "chzzktube.infra.provisioning.manifest",
    "chzzktube.infra.provisioning.planner",
    "chzzktube.infra.provisioning.resolver",
    "chzzktube.infra.provisioning.verifier",
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

    # 미러 파일명 결정:
    # - chzzktube.<leaf> (단일 세그먼트, e.g. core/config.py) → <leaf>.md (기존 flat 규칙 유지)
    # - chzzktube.infra.provisioning.<leaf> (프리미티브 충돌 회피) → provisioning_<leaf>.md
    #   (e.g. chzzktube.workers.downloader ↔ chzzktube.infra.provisioning.downloader
    #    같은 basename 충돌을 방지하기 위함)
    basename = clean_name.split(".")[-1]
    if clean_name.startswith("chzzktube.infra.provisioning."):
        dst = MIRRORS_DIR / f"provisioning_{basename}.md"
    elif clean_name == "chzzktube.pipeline.target_downloader.utils":
        dst = MIRRORS_DIR / "target_downloader_utils.md"
    else:
        dst = MIRRORS_DIR / f"{basename}.md"

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
    parts = ["# ChzzkTube Project Full Codebase\n\n"]
    for root, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for file in sorted(files):
            if file.endswith(".py"):
                rel = os.path.relpath(os.path.join(root, file), ROOT)
                with open(
                    os.path.join(root, file), "r", encoding="utf-8",
                    errors="ignore"
                ) as infile:
                    parts.append(f"\n## File: {rel}\n\n```python\n")
                    parts.append(infile.read())
                    parts.append("\n```\n")
    bundle_text = "".join(parts)
    # git diff --check passes: strip trailing whitespace from blank lines (bundle artifact)
    bundle_text = "\n".join(
        line.rstrip() if line.rstrip() == "" else line
        for line in bundle_text.split("\n")
    ).rstrip() + "\n"
    bundle_path.write_text(bundle_text, encoding="utf-8")
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

## File: .skills\understand-anything\understand\merge-batch-graphs.py

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

## File: .skills\understand-anything\understand\merge-subdomain-graphs.py

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

## File: .skills\understand-anything\understand-domain\extract-domain-context.py

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

## File: .skills\understand-anything\understand-knowledge\merge-knowledge-graph.py

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

## File: .skills\understand-anything\understand-knowledge\parse-knowledge-base.py

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

## File: chzzktube\__init__.py

```python

```

## File: chzzktube\control\__init__.py

```python

```

## File: chzzktube\control\controller.py

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

## File: chzzktube\control\gate_state.py

```python
"""gate_state — MainWindow에서 추출한 게이트·분석 워치독 무장/해제·POT 재시도 상태.

[Task 4-2] MainWindow(1667행)의 게이트/분석 워치독 플래그 + POT 재시도 상태를
통합 컨테이너로 이전 — 상태 변수 개별 초기화 금지(§6) 준수.

Thin Wrapper 금지(§6) 준수: MainWindow 메서드는 이 모듈 함수에 위임하는
호환 바인딩만 유지하며, 무장/해제 판정 로직의 실체는 여기에 존재한다.

Qt 무의존 — LivenessWatchdog 인스턴스는 MainWindow.__init__에서 생성해
주입받는다 (테스트 주입 가능).
"""
from __future__ import annotations

from typing import Any, Optional, Set


class GateState:
    """POT 게이트 + 분석 워치독 무장/해제 + POT 재시도 상태 컨테이너."""

    def __init__(self, gate_watchdog: Any, analysis_watchdog: Any):
        # 게이트 워치독 — POT gate 대기 시간 초과 판정
        self.gate_watchdog = gate_watchdog
        self.gate_active = False
        # 분석 워치독 — AnalyzeWorker 무페이로드 하트비트 연장
        self.analysis_watchdog = analysis_watchdog
        self.analysis_active = False
        # POT 봇 체크 재시도 상태 (URL당 1회 계약)
        self.pot_retry_pending: bool = False
        self.pot_retry_url: Optional[str] = None
        self.pot_retry_done: Set[str] = set()


# ── 게이트 무장/해제 ──────────────────────────────────────────────────

def start_gate(gate_state: GateState) -> None:
    """게이트 워치독 무장 — reset + active 플래그 설정."""
    gate_state.gate_watchdog.reset()
    gate_state.gate_active = True


def stop_gate(gate_state: GateState) -> None:
    """게이트 워치독 해제 — active 플래그 해제 (watchdog 인스턴스는 보존)."""
    gate_state.gate_active = False


def on_pot_work_tick(gate_state: GateState) -> None:
    """실제 POT 진행만 활성 게이트를 연장한다. 완료 후에는 재무장하지 않는다."""
    if gate_state.gate_active:
        gate_state.gate_watchdog.heartbeat()


# ── 분석 워치독 무장/해제 ────────────────────────────────────────────

def arm_analysis(gate_state: GateState) -> None:
    """분석 워치독 무장 — reset + active 플래그 설정."""
    gate_state.analysis_watchdog.reset()
    gate_state.analysis_active = True


def disarm_analysis(gate_state: GateState) -> None:
    """분석 워치독 해제 — active 플래그 해제 (성공·실패·취소·만료 시)."""
    gate_state.analysis_active = False


# ── POT 재시도 상태 ─────────────────────────────────────────────────

def clear_retry(gate_state: GateState) -> None:
    """POT 재시도 상태 초기화 — gate timeout/cancel 시 호출."""
    gate_state.pot_retry_pending = False
    gate_state.pot_retry_url = None


def schedule_retry(gate_state: GateState, url: str) -> bool:
    """봇 체크 재시도 스케줄 — URL당 1회 계약. 이미 스케줄됐으면 False."""
    if gate_state.pot_retry_pending:
        return False
    if not url or url in gate_state.pot_retry_done:
        return False
    gate_state.pot_retry_done.add(url)
    gate_state.pot_retry_url = url
    gate_state.pot_retry_pending = True
    return True


def consume_retry(gate_state: GateState) -> Optional[str]:
    """재시도 대기 URL 회수 — pending 해제 후 URL 반환, 없으면 None."""
    url = gate_state.pot_retry_url
    gate_state.pot_retry_pending = False
    gate_state.pot_retry_url = None
    return url

```

## File: chzzktube\control\pot_manager.py

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

    def _note(self, msg, is_status=False, is_error=False, component_id=None, is_progress=False):
        """raw 버스 단일 경유 — 라벨링은 근원에서 LogEvent로 동봉."""
        if isinstance(msg, LogEvent):
            event = msg
        else:
            stage = "SYS" if is_error else "POT"
            status = "FAIL" if is_error else ("RUN" if is_status else "OK")
            event = LogEvent(stage=stage, status=status, scope="POT",
                             msg=str(msg),
                             is_status=is_status, is_error=is_error)
        if component_id:
            event.component_id = component_id
        if is_progress:
            event.is_progress = True

        if self.mode == "prewarm":
            raw_log.raw("POT", event, to_tui=False)
            return
        raw_log.raw("POT", event, to_tui=True)

    def _dbg(self, msg):
        """raw 버스 단일 경유 — 직접 log_full.emit 금지 (F12 이중 적재 방지)."""
        text = msg.msg if isinstance(msg, LogEvent) else str(msg)
        if self.mode == "prewarm":
            raw_log.raw("POT-DEBUG", text)
        else:
            event = LogEvent(stage="POT", status="RUN", scope="POT", msg=text)
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
                res = ensure_node_server(
                    self._note, self._dbg, ver, rebuild=stale,
                    tick_func=self._tick, proc_registry=self._child_procs,
                )
                err = res.error if not res.success else None
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
                    self._note(emit_error_standard("POT", "POT", cause, action), is_status=False, is_error=True)
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

## File: chzzktube\control\startup_coordinator.py

```python
"""시작 시퀀스 단일 책임자 — Signal 경유, POTManager + raw 버스 연동."""

from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Signal

from chzzktube.control.pot_manager import POTManager
from chzzktube.control.startup_state import StartupState
from chzzktube.core import raw_log
from chzzktube.core.log_emitter import emit_error_standard


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
        from chzzktube.core import raw_log
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
            if ok:
                # 업그레이드 성공 시 초기 미설치로 인한 deps 에러 리셋 및 정상화
                self._state.set_deps(True)
                self._state.deps_error_msg = ""
                if summary:
                    self._emit("SYS", "OK", f"update {summary}")
            else:
                self._state.set_deps(False)
                if not self._state.deps_error_msg:
                    self._state.deps_error_msg = summary or "update failed"
                raw_log.raw(
                    "startup",
                    emit_error_standard("SYS", "MAIN", "update failed", "check logs (F12)"),
                    to_tui=True,
                )
            self._try_emit_ready()

    def report_pot(self, ok: bool, msg: str):
        with self._lock:
            status = msg if ok else "failed"
            # [HANDOVER §9.4] prewarm 완료(staged) 및 gate 완료(ready) 시 pot_ready=True 승격
            ready = ok and status in ("ready", "staged")
            self._state.set_pot(status, ready=ready)
            if not ok:
                # [v3.8.1] POT 실패 시 표준 에러 헬퍼 사용
                from chzzktube.core.log_emitter import emit_error_standard
                raw_log.raw(
                    "startup",
                    emit_error_standard("POT", "POT", "server failed", "check logs (F12)"),
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
        from chzzktube.core.log_emitter import emit_event
        from chzzktube.core.raw_log import raw
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

## File: chzzktube\control\startup_state.py

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

## File: chzzktube\core\__init__.py

```python
##### core/__init__.py - 공통 상수 및 유틸리티
"""chzzktube.core 패키지 공통 상수 및 유틸리티."""

# ─── 네트워크 타임아웃 상수 (초) ────────────────────────────────────────────
# 일관된 타임아웃 정책: 연결 10초, 읽기 30초, 대용량 다운로드 60초
CONNECT_TIMEOUT = 10.0      # TCP 연결 수립 대기
READ_TIMEOUT = 30.0         # HTTP 응답 헤더/바디 읽기 대기
DOWNLOAD_TIMEOUT = 60.0     # 대용량 파일 다운로드 (streaming read)

# ghcr.io 토큰 등 짧은 API 호출
SHORT_API_TIMEOUT = 15.0

# POT 서버 핑 등 매우 짧은 호출
PING_TIMEOUT = 1.5

# FFmpeg 버전 확인 등 로컬 프로세스
LOCAL_PROC_TIMEOUT = 10.0

# ─── 파일 권한 상수 ──────────────────────────────────────────────────────
# 임시 파일은 소유자만 읽기/쓰기 (0o600)
TEMP_FILE_MODE = 0o600
# 실행 파일은 소유자 실행 + 그룹/타자 읽기/실행 (0o755)
EXECUTABLE_FILE_MODE = 0o755

```

## File: chzzktube\core\chzzk_api.py

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
from chzzktube.core import SHORT_API_TIMEOUT


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
    with urllib.request.urlopen(req, timeout=SHORT_API_TIMEOUT) as res:
        return json.loads(res.read().decode("utf-8"))


def _get_json_with_auth_check(url, headers):
    """JSON GET + 인증 실패 시 ChzzkAuthError 발생."""
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=SHORT_API_TIMEOUT) as res:
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


def _fetch_m3u8_streams(m3u8_url, headers, timeout=SHORT_API_TIMEOUT):
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

## File: chzzktube\core\client_opts.py

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

## File: chzzktube\core\config.py

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
_APP_VERSION = "v3.12.2"

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
        # [외부툴 가변 설정 — client_opts._apply_* 헬퍼가 yt-dlp/ffmpeg
        #  옵션으로 배선한다. 새 키 추가 시 (1) 아래 기본값 (2) _apply_* 헬퍼
        #  (3) dialogs.py 체크박스/콤보 3점 세트를 함께 추가할 것.]
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

## File: chzzktube\core\cookies.py

```python
### cookies.py - 브라우저 쿠키 추출 (yt-dlp 네이티브 위임)

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

## File: chzzktube\core\dl_platform.py

```python
##### dl_platform.py - 다운로더 플랫폼/콘텐츠 타입 감별
"""URL 문자열에서 플랫폼(youtube/chzzk/twitch 등)과 콘텐츠 타입을 판정한다.

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
    youtube live/기타 스트림 → live
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

## File: chzzktube\core\log_emitter.py

```python
"""Pure log event builders and text formatting helpers (Qt-free).

pipeline/workers가 백그라운드·테스트 환경에서도 GUI 컨텍스트 없이
가져갈 수 있는 순수 함수만 둔다. Qt 위젯 렌더링은 ui/log_console 담당.
"""
import time
import unicodedata
from typing import TYPE_CHECKING

from chzzktube.core.log_event import STAGES, STATUSES
from chzzktube.core.dl_platform import _short_platform

if TYPE_CHECKING:  # 타입 힌트 전용 — 런타임 순환 참조 방지
    from chzzktube.core.log_event import LogEvent


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
#   SCOPE   : 발생지·대상 (엔진 YTDL/FFMP/NODE/POT, 플랫폼 YT/CHZ/TW/TIKT…,
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
            "YTDL", "FFMP", "NODE", "POT", "MAIN", "RAW", "QUEUE", "DISK"
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

    msg_clean = str(msg or "").rstrip("\r\n ")
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
        spec="",
        speed=event.speed,
        pct=event.pct,
        bar_frac=event.bar_frac,
    )


def emit_event(stage, status, scope="-", msg="", is_status=False, is_error=False):
    """단순 이벤트 1건."""
    from chzzktube.core.log_event import LogEvent  # lazy import
    return LogEvent(
        stage=stage, status=status, scope=scope, msg=msg,
        is_status=is_status, is_error=is_error,
    )


def emit_dl(status, scope="", msg="", speed="", pct=None, bar_frac=None,
            stage="DL", is_status=False, is_error=False):
    """DL 진행률/완료 이벤트."""
    from chzzktube.core.log_event import LogEvent  # lazy import
    return LogEvent(
        stage=stage, status=status, scope=scope, msg=msg,
        speed=speed, pct=pct, bar_frac=bar_frac,
        is_status=is_status, is_error=is_error,
    )


def emit_err(msg):
    """에러 1건 — FAIL 상태, 스코프 빈칸."""
    from chzzktube.core.log_event import LogEvent  # lazy import (순환 참조 방지)
    return LogEvent(stage="DL", status="FAIL", msg=msg, is_error=True)


def emit_progress(stage, status, scope="-", msg="", speed="", pct=None,
                  bar_frac=None, is_status=False, is_error=False,
                  component_id: str | None = None, is_progress: bool = False):
    """진행률 표시 이벤트 — ANAL/DL/LIVE 단계."""
    from chzzktube.core.log_event import LogEvent  # lazy import (순환 참조 방지)
    return LogEvent(
        stage=stage, status=status, scope=scope, msg=msg,
        speed=speed, pct=pct, bar_frac=bar_frac,
        is_status=is_status, is_error=is_error,
        component_id=component_id, is_progress=is_progress,
    )


def emit_component(stage, status, scope, msg="", is_status=False, is_error=False,
                   component_id=None, is_progress=False):
    """컴포넌트/워커 결과 — DEPS / POT / READY 등.

    component_id/is_progress는 갱신형 진행 로그(§3.7-5)의 필수 페이로드다.
    브리지(TUI/F12)가 이 두 필드로 동일 라인 제자리 덮어쓰기를 수행한다.
    """
    from chzzktube.core.log_event import LogEvent  # lazy import (순환 참조 방지)
    return LogEvent(
        stage=stage, status=status, scope=scope, msg=msg,
        is_status=is_status, is_error=is_error,
        component_id=component_id, is_progress=is_progress,
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
    """원인 문자열을 표준 키워드로 정규화 (알려지지 않은 원인도 보존)."""
    cause_lower = cause.lower()
    for std_cause in _ERROR_CAUSES:
        if std_cause in cause_lower:
            return _ERROR_CAUSES[std_cause]
    return cause.strip() if cause else "unknown error"

def _normalize_action(action: str) -> str:
    """액션 문자열을 표준 키워드로 정규화 (알려지지 않은 액션도 보존)."""
    action_lower = action.lower()
    for std_action, std_value in _ERROR_ACTIONS.items():
        if std_action.lower() in action_lower:
            return std_value
    return action.strip()

def _truncate_msg(msg: str, max_len: int = _MAX_ERR_MSG_LEN) -> str:
    """메시지 길이 제한 (초과 시 '…' 절단)."""
    if len(msg) <= max_len:
        return msg
    return msg[:max_len - 1] + "…"

def emit_error_standard(stage: str, scope: str, cause: str, action: str = "",
                        status: str = "FAIL", is_error: bool = True) -> "LogEvent":
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
                msg=msg,
        is_error=True,
    )


def emit_error_warn(stage: str, scope: str, cause: str, action: str = "",
                    status: str = "WARN") -> "LogEvent":
    """WARN 레벨 표준 에러 (is_error=False)."""
    return emit_error_standard(stage, scope, cause, action, status=status, is_error=False)

```

## File: chzzktube\core\log_event.py

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
    scope: str = "-"
    speed: str = "-"
    pct: float = None
    bar_frac: float = None
    msg: str = ""
    is_status: bool = False
    is_error: bool = False
    # msg가 이미 표시 완성형(컬럼 포맷·원문)일 때 True — 뷰는 재포맷하지 않는다
    rendered: bool = False
    timestamp: str = field(default_factory=lambda: time.strftime("[%H:%M:%S]"))
    # 갱신형 로그의 소유 컴포넌트와 진행 중/마감 상태를 운반한다.
    component_id: str | None = None
    is_progress: bool = False


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

## File: chzzktube\core\log_history.py

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

## File: chzzktube\core\media.py

```python
### media.py - 순수 미디어 처리 헬퍼 (해상도 라벨 / 임시파일 정리 / FFmpeg 리먹싱 / 코덱 랭킹)
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

## File: chzzktube\core\playlist.py

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

## File: chzzktube\core\raw_log.py

```python
"""raw_log — 앱 전체 동작의 단일 진실 공급원 (raw 버스).

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


def raw(tag, msg, is_status=False, is_error=False, to_tui=False,
        component_id: str | None = None, is_progress: bool = False):
    """단일 진입점 — 앱의 모든 행동과 갱신형 메타데이터는 여기로 수신된다."""
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
    if component_id is not None:
        msg.component_id = component_id
    if is_progress:
        msg.is_progress = True
    _dispatcher.publish(msg, to_tui)


def flush(timeout: float = 1.0) -> None:
    """테스트/종료용: 현재 queue가 처리될 때까지 기다린다."""
    _dispatcher.flush(timeout)


def shutdown(timeout: float = 1.0) -> None:
    _dispatcher.shutdown(timeout)

def log_f12_cli(cmd: str, output: str = None, is_error: bool = False, tag: str = "deps-cli"):
    """F12 상세로그 전용 CLI 실행 결과 발행 ($ cmdline + 원문 출력).

    - to_tui=False 강제: 메인 TUI 콘솔 오염을 완벽히 차단
    - truncate_for_full_log 적용: 최대 6줄, 160자 제한
    """
    if not cmd:
        return
    raw(
        tag,
        LogEvent(stage="DEPS", status="RUN", scope="CLI", msg=f"$ {cmd}", is_error=is_error, rendered=True),
        to_tui=False,
    )
    if output:
        from chzzktube.infra.updater import truncate_for_full_log
        clean_out = truncate_for_full_log(output, max_lines=6, max_width=160)
        for line in clean_out.splitlines():
            raw(
                tag,
                LogEvent(
                    stage="DEPS",
                    status="FAIL" if is_error else "OK",
                    scope="CLI",
                    msg=line,
                    is_error=is_error,
                    rendered=True,
                ),
                to_tui=False,
            )


def log_f12_net(msg: str, is_error: bool = False, tag: str = "deps-net"):
    """F12 상세로그 전용 네트워크/시스템 원문 로그 발행.

    - to_tui=False 강제: 메인 콘솔 오염 절대 차단
    """
    if not msg:
        return
    raw(
        tag,
        LogEvent(
            stage="DEPS",
            status="FAIL" if is_error else "RUN",
            scope="NET",
            msg=str(msg),
            is_error=is_error,
            rendered=True,
        ),
        to_tui=False,
    )


```

## File: chzzktube\core\speed_window.py

```python
##### speed_window.py - 10초 이동평균 속도계
"""네트워크에서 실제 흐른 바이트만 샘플로 누적해 평균 속도를 계산한다.

라이브=릴레이 파이프 계수, VOD=yt-dlp downloaded_bytes 를 add()에 넘기며,
스트림 전환(비디오→오디오)·타겟 전환 시 reset()으로 윈도우를 비운다.
"""
import time
from collections import deque


class SpeedWindow:
    """10초 이동평균 속도계.

    add(총 바이트 누적값)를 계속 공급하면 speed()가 초당 바이트를 반환.
    내부적으로 (타임스탬프, 누적바이트) 표본을 10초 윈도우로 유지한다.
    [v3.9.0] 리스트 재구성 → deque popleft O(1) 상각.
    """

    def __init__(self, window=10.0):
        self._window = float(window)
        self._samples = deque()
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
            while self._samples and self._samples[0][0] < cutoff:
                self._samples.popleft()

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

## File: chzzktube\core\tool_log.py

```python
"""tool_log — 외부툴 출력 흡수 단일 래퍼 (v3.3.2).

[원칙] 새 기능이 외부툴(yt-dlp/ffmpeg/bgutil)을 호출할 때는
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
    """subprocess stderr 실시간 흡수 — ffmpeg/bgutil 공용.

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

## File: chzzktube\core\utils.py

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

## File: chzzktube\core\watchdog.py

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

## File: chzzktube\core\yt_logger_bridge.py

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

## File: chzzktube\infra\__init__.py

```python

```

## File: chzzktube\infra\cleanup.py

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

    # 6. cz_* 임시 디렉터리 정리 (base 및 base 하위 디렉터리)
    for cz_dir in glob.glob(os.path.join(base, "cz_*")):
        try:
            if os.path.isdir(cz_dir):
                shutil.rmtree(cz_dir, ignore_errors=True)
        except Exception:
            pass
    for cz_dir in glob.glob(os.path.join(base, "*", "cz_*")):
        try:
            if os.path.isdir(cz_dir):
                shutil.rmtree(cz_dir, ignore_errors=True)
        except Exception:
            pass


def cleanup_on_startup():
    """앱 기동 시 호출 — 이전 세션 잔재 정리."""
    cleanup_provisioning_artifacts()


def cleanup_on_shutdown():
    """앱 종료 시 호출 — 현재 세션 잔재 정리."""
    cleanup_provisioning_artifacts()
```

## File: chzzktube\infra\components.py

```python
### components.py - ffmpeg runtime manager
"""ffmpeg 자동 수급/관리 전용 모듈 — 앱 전용 격리 캐시 (v3.8.0).

*  [격리 원칙] 시스템 PATH 탐색(shutil.which)·OS 패키지 매니저(brew install,
   apt-get 등) 서브프로세스 호출 완전 철폐. 오직 writable_base()/ffmpeg/
   단일 캐시만 검사하고, 없으면 아카이브를 직접 수급한다.
*  [stdlib 순수성] 의존성 수급 모듈은 순수 파이썬 기반이다. 7z 모듈을 추가로
   끌어오지 않기 위해 zip/tar만 타겟팅한다 (.7z 자산은 후보에서 제외).
*  [동적 버전] 동적 모듈은 생명주기 갱신을 위해 항상 최신 릴리스를 받는다.
   버전 하드코딩 금지 — GitHub API latest + checksums.sha256로 재해석.
*  Windows/Linux: BtbN/FFmpeg-Builds GitHub Release (zip / tar.xz, SHA-256 필수)
*  macOS: Homebrew formulae API (bottle tar.gz, SHA-256 필수 + _verify_ffmpeg 실측 판정)

[전수조사 정리 2026-09-04] 구 설계(Hitomi Downloader style 전체 구성요소
자동수급: yt-dlp 휠 / bgutil 플러그인 / pot-pack / 라이브팩)는
main.py에 연결된 적이 없는 죽은 코드였음 — 실제 의존 흐름은
앱 전용 캐시(yt-dlp 바이너리 / ffmpeg) + pot_provider(bgutil 서버 빌드) + 본 모듈.
"""
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

import chzzktube.core.config as config
from chzzktube.core import (
    CONNECT_TIMEOUT,
    READ_TIMEOUT,
    DOWNLOAD_TIMEOUT,
    SHORT_API_TIMEOUT,
    TEMP_FILE_MODE,
    EXECUTABLE_FILE_MODE,
)
from chzzktube.core.log_emitter import emit_component, emit_error_standard, emit_error_warn
from chzzktube.core.raw_log import log_f12_cli, log_f12_net
from chzzktube.infra.platform import strip_macos_quarantine
from chzzktube.ui import ProgressBar

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


def _http_get(url, timeout=READ_TIMEOUT):
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
    with urllib.request.urlopen(url, timeout=SHORT_API_TIMEOUT) as resp:
        data = json.load(resp)
    return data.get("token")


def _download(url, dest, log=None, label="", expected_sha256=None):
    """파일 다운로드(진행 바 포함). 성공 시 dest 경로 반환.

    ProgressBar를 사용하여 raw_log 히스토리에 진행 바를 기록 (상태 줄 덮어쓰기 방지).
    """
    # log 함수가 없으면 기본 raw_log 사용
    log_func = log if callable(log) else None

    with ProgressBar(component=label or os.path.basename(url), log_func=log_func) as bar:
        bar.start()
        tmp = dest + ".part"
        req = urllib.request.Request(url, headers={"User-Agent": _UA})

        # ghcr.io 토큰 처리
        if "ghcr.io" in url:
            try:
                token = _ghcr_token("repository:homebrew/core/ffmpeg:pull")
                req.headers["Authorization"] = f"Bearer {token}"
            except Exception:
                pass

        hasher = hashlib.sha256() if expected_sha256 else None
        try:
            # 임시 파일을 0o600 권한으로 생성 (소유자만 읽기/쓰기)
            with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT) as resp:
                # Set per-read timeout
                try:
                    sock = resp.fp.raw._sock
                    if sock is not None:
                        sock.settimeout(READ_TIMEOUT)
                except AttributeError:
                    pass

                total = int(resp.headers.get("Content-Length", 0))
                downloaded = 0

                with open(tmp, "wb", opener=lambda p, f: os.open(p, f, TEMP_FILE_MODE)) as f:
                    while True:
                        chunk = resp.read(1024 * 512)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if hasher is not None:
                            hasher.update(chunk)
                        bar.update(downloaded, total)

            # SHA-256 검증
            if hasher is not None:
                computed_sha256 = hasher.hexdigest()
                if computed_sha256 != expected_sha256:
                    raise ValueError(f"SHA256 mismatch: {computed_sha256} != {expected_sha256}")

            os.replace(tmp, dest)
            bar.finish("completed")
            return dest

        except BaseException:
            # 정리
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise



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
    import zipfile

    # 사전 검증: zip 파일 무결성 확인
    try:
        with zipfile.ZipFile(zip_path) as zf:
            bad_file = zf.testzip()
            if bad_file is not None:
                raise zipfile.BadZipFile(f"Corrupted zip entry: {bad_file}")
    except zipfile.BadZipFile as e:
        log(emit_component("DEPS", "FAIL", "DEPS", f"{label} zip validation failed: {e}"))
        raise

    tmp = dest_dir + ".tmp"
    _rmtree(tmp)
    os.makedirs(os.path.dirname(tmp) or ".", exist_ok=True)
    try:
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(tmp)
    except zipfile.BadZipFile as e:
        _rmtree(tmp)
        log(emit_component("DEPS", "FAIL", "DEPS", f"{label} zip extraction failed: {e}"))
        raise

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
# [v3.8.4 동적 수급] 하드코딩 릴리스 URL 전면 폐기.
# Windows/Linux: BtbN/FFmpeg-Builds GitHub Release API + checksums.sha256
# macOS: Homebrew formulae API (bottle tar.gz) — cellar 메타데이터로 스킵하지 않고 실측으로 판정
BTBN_RELEASE_API = "https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/latest"
BTBN_CHECKSUM_ASSET = "checksums.sha256"
BTBN_UA = "ChzzkTube-Provisioner/1.0"
_SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")


def _normalize_arch(machine=None):
    """platform.machine() → canonical arch token ('amd64' | 'arm64').

    [stdlib 전용] 미지원 아키텍처는 조용히 추측하지 않고 ValueError로 중단한다.
    """
    mach = (machine or platform.machine() or "").lower()
    if mach in ("amd64", "x86_64", "x64"):
        return "amd64"
    if mach in ("arm64", "aarch64"):
        return "arm64"
    raise ValueError(f"unsupported architecture: {mach or 'unknown'}")


def _parse_btbn_checksums(manifest_text, asset_name):
    """checksums.sha256 텍스트에서 asset_name의 SHA-256을 추출.

    [실측 계약] GitHub REST API의 release asset 응답에는 개별 파일의 SHA-256
    digest 필드가 존재하지 않는다. 따라서 BtbN 릴리스가 함께 게시하는
    `checksums.sha256` 텍스트 자산을 받아 정확한 basename 매칭으로만 검증한다.
    """
    if not manifest_text or not asset_name:
        raise ValueError("checksum manifest or asset name missing")
    for raw in manifest_text.splitlines():
        parts = raw.strip().split()
        if len(parts) < 2:
            continue
        digest, name = parts[0].strip().lower(), parts[-1].strip().lstrip("*")
        if name == asset_name and _SHA256_HEX_RE.match(digest):
            return digest
    raise ValueError(f"valid SHA-256 for {asset_name} not found in manifest")


def _fetch_btbn_checksums(url, timeout=SHORT_API_TIMEOUT):
    """checksums.sha256 자산 텍스트 다운로드 (stdlib only)."""
    req = urllib.request.Request(url, headers={"User-Agent": BTBN_UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _select_btbn_asset(assets, arch_token, ext):
    """BtbN 릴리스 자산 목록에서 정적 GPL 아카이브 1개를 선택.

    [실측 명명 규칙] BtbN 자산은 `ffmpeg-<build>-win64-gpl.zip` 또는
    `ffmpeg-<build>-linux64-gpl.tar.xz` 형태로, `-gpl.`/`-gpl-`가 모두 나온다.
    따라서 `gpl` 토큰만 확인하고 `shared`를 배제한다.

    제외 규칙: shared(dylib 동반), debug/symbols/pdb, .7z(7z 의존성 회피),
    이외 아키텍처 토큰.
    """
    for asset in assets:
        name = asset.get("name", "")
        low = name.lower()
        if "gpl" not in low or not low.endswith(ext):
            continue
        if "shared" in low or arch_token not in low:
            continue
        if any(tok in low for tok in ("debug", "symbols", "pdb")):
            continue
        return asset
    return None


def _resolve_btbn_ffmpeg(timeout=SHORT_API_TIMEOUT):
    """BtbN 최신 릴리스에서 (에셋 + 체크섬) 단일 트랜잭션 해석.

    반환: component/version/asset_name/url/sha256/archive_type/platform/architecture
    """
    system = platform.system().lower()
    arch = _normalize_arch()
    if system == "windows":
        arch_token = "win64" if arch == "amd64" else "winarm64"
        ext, archive_type = ".zip", "zip"
    elif system == "linux":
        arch_token = "linux64" if arch == "amd64" else "linuxarm64"
        ext, archive_type = ".tar.xz", "tar.xz"
    else:
        raise ValueError(f"BtbN does not provide builds for: {system}")

    req = urllib.request.Request(BTBN_RELEASE_API, headers={"User-Agent": BTBN_UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        release = json.load(resp)

    assets = release.get("assets", []) or []
    target = _select_btbn_asset(assets, arch_token, ext)
    if target is None:
        raise RuntimeError(f"no BtbN {arch_token} gpl asset for {system}")

    checksum_asset = next(
        (a for a in assets if a.get("name") == BTBN_CHECKSUM_ASSET), None
    )
    if checksum_asset is None:
        raise RuntimeError("BtbN checksums.sha256 manifest missing from release")

    manifest = _fetch_btbn_checksums(
        checksum_asset.get("browser_download_url", ""), timeout=timeout
    )
    digest = _parse_btbn_checksums(manifest, target.get("name", ""))

    return {
        "component": "ffmpeg",
        "version": release.get("tag_name") or "latest",
        "asset_name": target.get("name", ""),
        "url": target.get("browser_download_url", ""),
        "sha256": digest,
        "archive_type": archive_type,
        "platform": system,
        "architecture": arch,
    }


def _safe_extract(archive_path, archive_type, dest_dir):
    """stdlib 전용 안전 압축 해제 — Zip Slip / tar traversal 차단.

    * zip:  멤버 경로 정규화 후 dest_dir 밖으로 벗어나면 ValueError
    * tar*: Python 3.12+ `filter="data"` 로 절대경로/상위경로/링크 이탈 차단
    """
    dest = Path(dest_dir).resolve()
    dest.mkdir(parents=True, exist_ok=True)
    if archive_type == "zip":
        with zipfile.ZipFile(archive_path) as zf:
            for member in zf.infolist():
                target = (dest / member.filename).resolve()
                if target != dest and dest not in target.parents:
                    raise ValueError(f"path traversal in zip: {member.filename}")
            zf.extractall(dest)
        return dest
    if archive_type in ("tar.xz", "tar.gz", "tar"):
        mode = {"tar.xz": "r:xz", "tar.gz": "r:gz", "tar": "r:"}[archive_type]
        with tarfile.open(archive_path, mode) as tf:
            try:
                # Python 3.12+ : filter="data" 가 절대경로/상위경로/링크 이탈을
                # tarfile.InsideDestinationError 등 FilterError로 차단한다.
                # 호출자 계약은 ValueError 단일 예외이므로 정규화해 올린다.
                tf.extractall(dest, filter="data")
            except TypeError:  # Python < 3.12 — filter 파라미터 부재
                for member in tf.getmembers():
                    target = (dest / member.name).resolve()
                    if target != dest and dest not in target.parents:
                        raise ValueError(f"path traversal in tar: {member.name}")
                tf.extractall(dest)
            except tarfile.TarError as e:
                raise ValueError(f"unsafe tar archive: {e}") from e
        return dest
    raise ValueError(f"unsupported archive type: {archive_type}")


def _locate_binaries(root):
    """추출 트리에서 ffmpeg/ffprobe 실행 파일 탐색 (중첩 Cellar/bin 대응)."""
    found = {}
    for path in Path(root).rglob("*"):
        if not path.is_file():
            continue
        stem = path.stem.lower()
        if stem in ("ffmpeg", "ffprobe") and stem not in found:
            found[stem] = path
    return found


def _atomic_install(binaries, dest_dir):
    """추출 바이너리를 dest_dir/bin 으로 원자 교체 (기존 버전 보존).

    Windows는 기존 디렉터리 rename 시 PermissionError/FileExistsError가
    나므로 incoming → backup → 교체 순서를 쓰고, 실패 시 backup을 되돌린다.
    """
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    bin_dir = dest / "bin"
    incoming = dest / "bin_incoming"
    backup = dest / "bin_backup"
    suffix = _exe_suffix()

    _rmtree(str(incoming))
    _rmtree(str(backup))
    incoming.mkdir(parents=True, exist_ok=True)

    for stem, src in binaries.items():
        target = incoming / f"{stem}{suffix}"
        shutil.copy2(src, target)
        if os.name != "nt":
            target.chmod(target.stat().st_mode | 0o755)
            strip_macos_quarantine(str(target))

    if bin_dir.exists():
        try:
            os.replace(str(bin_dir), str(backup))
        except OSError:
            _rmtree(str(bin_dir))
    installed = False
    try:
        os.replace(str(incoming), str(bin_dir))
        installed = True
    finally:
        if not installed and backup.exists():
            try:
                os.replace(str(backup), str(bin_dir))
            except OSError:
                pass
    _rmtree(str(backup))
    return bin_dir
_FFMPEG_BREW_API = "https://formulae.brew.sh/api/formula/ffmpeg.json"
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
_FFMPEG_BREW_API = "https://formulae.brew.sh/api/formula/ffmpeg.json"


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
    - Windows: 캐시 → BtbN GitHub latest (win64/winarm64 static gpl zip)
    - macOS: 캐시 → Homebrew formulae bottle (tar.gz, _verify_ffmpeg 실측 판정)
    - Linux: 캐시 → BtbN GitHub latest (linux64/linuxarm64 static gpl tar.xz)
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

def _record_provision_plan(plan, install_path):
    """수급 결과를 provisioning manifest에 기록 (감사 가능성 확보).

    [실측 계약] manifest에는 `record_install` 같은 헬퍼가 없다.
    `ProvisionManifest.load/save` + `ComponentRecord` + `update_component`가
    유일한 공식 API이므로 이를 그대로 사용한다. 기록 실패는 본 수급 흐름을
    깨뜨리지 않는다 — best-effort.
    """
    try:
        from chzzktube.infra.provisioning.manifest import (
            ComponentRecord, ProvisionManifest,
        )

        base = Path(config.writable_base())
        manifest = ProvisionManifest.load(base)
        manifest.update_component(ComponentRecord(
            name=plan.get("component", "ffmpeg"),
            version=plan.get("version", "latest"),
            source=plan.get("platform", "github"),
            mirror=plan.get("asset_name", ""),
            install_path=os.path.relpath(install_path, base),
            verified_at=time.time(),
            verify_version=plan.get("architecture", ""),
            sha256=plan.get("sha256", ""),
        ))
        manifest.save(base)
    except Exception:
        pass


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
    """Windows용 ffmpeg 자동 수급 — BtbN 최신 릴리스 동적 해석 (v3.8.4).

    [동적 버전] 하드코딩 릴리스 태그 없음. GitHub API latest + checksums.sha256
    으로 에셋·해시를 매 트랜잭션 재해석한다. .7z 자산은 7z 의존성 회피를 위해
    후보에서 제외하고 static(비 shared) GPL zip만 채택한다.

    [v3.8.0 격리] 시스템 PATH 참조 없음 — 캐시는 ensure_ffmpeg 선검.
    """
    dest = Path(config.writable_base()) / FFMPEG_DIRNAME
    exe_name = "ffmpeg.exe"

    max_retries = 3
    last_err = None
    for attempt in range(max_retries):
        if attempt > 0:
            log(emit_component("DEPS", "WARN", "FFMP", f"retry {attempt}/{max_retries}"))
            time.sleep(2 ** attempt)

        try:
            log_f12_net("resolving BtbN ffmpeg release via GitHub API")
            log(emit_component("DEPS", "RUN", "FFMP", "resolving latest (github)..."))
            plan = _resolve_btbn_ffmpeg()
            log_f12_net(f"resolved BtbN asset: {plan['asset_name']} (sha256: {plan['sha256'][:16]}...)")
            log_f12_net(f"HTTP GET {plan['url']}")
            log(emit_component("DEPS", "RUN", "FFMP", f"downloading {plan['version']}..."))

            os.makedirs(dest, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix="cz_ffmpeg_") as td:
                archive = _download(
                    plan["url"], os.path.join(td, plan["asset_name"]),
                    log, "ffmpeg", expected_sha256=plan["sha256"],
                )
                log_f12_net(f"extracting {plan['asset_name']} ({plan['archive_type']}) -> {td}/x")
                staging = _safe_extract(archive, plan["archive_type"], Path(td) / "x")
                binaries = _locate_binaries(staging)

            if "ffmpeg" not in binaries:
                last_err = f"ffmpeg binary not found in {plan['asset_name']}"
                log_f12_net(last_err, is_error=True)
                log(emit_error_warn("DEPS", "FFMP", "binary missing", "retry mirror (1/3)"))
                continue

            bin_dir = _atomic_install(binaries, dest)
            exe_path = bin_dir / exe_name
            if not exe_path.is_file():
                last_err = "ffmpeg.exe not installed"
                log_f12_net(last_err, is_error=True)
                continue
            if not _verify_ffmpeg(str(exe_path)):
                last_err = "ffmpeg.exe install verification failed"
                log_f12_net(last_err, is_error=True)
                continue

            _wire_ffmpeg_path(str(bin_dir))
            log_f12_net(f"verified ffmpeg binary -> {exe_path}")
            log(emit_component("DEPS", "OK", "FFMP", f"ok ({plan['version']})"))
            _record_provision_plan(plan, str(exe_path))
            return None
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
            log_f12_net(f"ffmpeg windows install error: {e}", is_error=True)
            log(emit_error_warn("DEPS", "FFMP", "download failed", f"{type(e).__name__} (F12)"))

    return f"ffmpeg install failed after {max_retries} attempts: {last_err}"


def _normalize_bottle_binaries(extracted_dir, cache_dir):
    """Homebrew Bottle의 중첩 bin 디렉터리를 앱 격리 캐시로 정규화.

    [v3.8.4] _locate_binaries/_atomic_install로 대체되었지만, 외부 호출/계약
    테스트 호환을 위해 얇은 래퍼로 유지한다. ffmpeg·ffprobe 둘 다 있어야 한다.
    """
    found = _locate_binaries(extracted_dir)
    if "ffmpeg" not in found:
        return None
    try:
        bin_dir = _atomic_install(found, cache_dir)
    except OSError:
        return None
    return bin_dir / "ffmpeg"


def _ffmpeg_progress_event(text):
    """Bottle 진행 틱 → 진행형 LogEvent (component_id=ffmpeg, is_progress=True).

    TUI/F12 브리지가 동일 라인 제자리 갱신을 수행하도록 진행 메타데이터를
    반드시 실어 보낸다 (§3.7-5 다중 컴포넌트 갱신형).
    """
    return emit_component(
        "DEPS", "RUN", "FFMP", text, component_id="ffmpeg", is_progress=True
    )


def _ffmpeg_done_event(text):
    """Bottle 진행 종료 → 히스토리 확정 로그 (is_progress=False)."""
    return emit_component(
        "DEPS", "OK", "FFMP", text, component_id="ffmpeg", is_progress=False
    )


def _write_bottle_payload(url, dest_path, expected_sha256):
    """Homebrew bottle 페이로드 기록 + SHA-256 강제 검증.

    [v3.9.0] 기존 생략 주석 구간의 누락된 다운로드 단계를 복원.
    ghcr.io 토큰 인증이 필요하므로 _http_get 경유. SHA 없으면 채택 금지
    (무검증 수급 차단, §5-28). 해시 불일치는 ValueError로 호출자에게 전달.
    """
    hasher = hashlib.sha256()
    with _http_get(url, timeout=DOWNLOAD_TIMEOUT) as resp, open(dest_path, "wb") as f:
        while True:
            chunk = resp.read(1024 * 512)
            if not chunk:
                break
            f.write(chunk)
            hasher.update(chunk)
    if hasher.hexdigest() != (expected_sha256 or "").lower():
        raise ValueError(f"SHA256 mismatch for bottle: {url}")


def _ensure_ffmpeg_macos(log, force):
    """맥용 ffmpeg 자동 수급 — Bottle 내부 라이브러리 경로 바인딩 및 호스트 승격 안전망."""
    dest = os.path.join(config.writable_base(), FFMPEG_DIRNAME)

    try:
        log_f12_net(f"HTTP GET {_FFMPEG_BREW_API}")
        log(emit_component("DEPS", "RUN", "FFMP", "resolving (homebrew formula)..."))
        with urllib.request.urlopen(_FFMPEG_BREW_API, timeout=SHORT_API_TIMEOUT) as resp:
            data = json.load(resp)

        bottle = data.get("bottle", {}).get("stable", {})
        files = bottle.get("files", {})
        keys = _macos_bottle_keys(files)

        last_err = None
        for key in keys:
            entry = files.get(key) or {}
            url = entry.get("url")
            sha256 = entry.get("sha256")
            if not url or not sha256:
                continue

            log_f12_net(f"resolved bottle: {key} (sha256: {sha256})")
            log_f12_net(f"HTTP GET {url}")

            try:
                with tempfile.TemporaryDirectory(prefix="cz_ffmpeg_") as td:
                    tar_path = os.path.join(td, "ffmpeg.tar.gz")
                    _write_bottle_payload(url, tar_path, sha256)

                    staging = _safe_extract(tar_path, "tar.gz", Path(td) / "x")
                    log_f12_net(f"tar -xzf ffmpeg.tar.gz -C {td}/x")
                    binaries = _locate_binaries(staging)
                    if "ffmpeg" not in binaries or "ffprobe" not in binaries:
                        continue

                    staged = str(binaries["ffmpeg"])
                    os.chmod(staged, 0o755)
                    strip_macos_quarantine(staged)

                    # [핵심 교정 1] Bottle 내부의 lib 디렉터리를 찾아 dyld 경로로 주입!
                    # 임시 폴더에 풀린 libavcodec 등을 바이너리가 인식할 수 있도록 길을 열어줍니다.
                    lib_dirs = [str(p) for p in Path(staging).rglob("lib") if p.is_dir()]
                    env_extra = {"DYLD_FALLBACK_LIBRARY_PATH": ":".join(lib_dirs)} if lib_dirs else {}

                    try:
                        verified = _verify_ffmpeg(staged, env_extra=env_extra)
                    except TypeError:
                        verified = _verify_ffmpeg(staged)

                    if not verified:
                        last_err = f"ffmpeg [{key}] execution test failed (dyld incompatible)"
                        log_f12_net(f"ffmpeg [{key}] execution test failed (dyld incompatible)", is_error=True)
                        log(emit_error_warn("DEPS", "FFMP", "binary incompatible", "trying next bottle (F12)"))
                        continue

                    # 검증 성공 시 원자 교체 및 라이브러리 동반 복사
                    bin_dir = _atomic_install(binaries, Path(dest))
                    _wire_ffmpeg_path(str(bin_dir))
                    log_f12_net(f"verified ffmpeg binary -> {bin_dir}/ffmpeg")
                    log(_ffmpeg_done_event(f"bottle [{key}] verified"))
                    return None

            except Exception as e:
                last_err = str(e)
                continue

        # [핵심 교정 2: 호스트 승격 구출책]
        # 모든 Bottle이 순정 상태에서 dylib 부재로 전멸했을 경우,
        # 시스템(/opt/homebrew 등)에 이미 존재하는 유효한 ffmpeg를 격리 캐시로 승격 복사!
        log(emit_error_warn("DEPS", "FFMP", "binary incompatible", "check logs (F12)"))
        host_candidates = [Path("/opt/homebrew/bin/ffmpeg"), Path("/usr/local/bin/ffmpeg")]
        for host_bin in host_candidates:
            if host_bin.is_file() and _verify_ffmpeg(host_bin):
                bin_dir = Path(dest) / "bin"
                bin_dir.mkdir(parents=True, exist_ok=True)
                target_ffmpeg = bin_dir / "ffmpeg"
                shutil.copy2(host_bin, target_ffmpeg)
                target_ffmpeg.chmod(0o755)

                host_probe = host_bin.parent / "ffprobe"
                if host_probe.is_file():
                    shutil.copy2(host_probe, bin_dir / "ffprobe")
                    (bin_dir / "ffprobe").chmod(0o755)

                _wire_ffmpeg_path(str(bin_dir))
                log(_ffmpeg_done_event(f"bootstrapped from host ({host_bin.parent})"))
                return None

        log(emit_error_standard("DEPS", "FFMP", "binary incompatible", "check logs (F12)"))
        return last_err or "no runnable bottle found"

    except Exception as e:
        return f"Homebrew formula resolve failed: {e}"


def _fetch_url(url, dest_path, timeout=60):
    """단일 파일 다운로드 — 302 redirector 추적 지원 (범용 helper).

    _http_get(단일 GET, 리다이렉트 미추적)과 달리 표준 opener로 리다이렉트를
    따라간다. 현재는 예비 유틸리티이며 수급 경로는 _download를 사용한다.
    """
    opener = urllib.request.build_opener(urllib.request.HTTPRedirectHandler())
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with opener.open(req, timeout=timeout) as resp, open(dest_path, "wb") as f:
        while True:
            chunk = resp.read(1024 * 512)
            if not chunk:
                break
            f.write(chunk)


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
    """리눅스용 ffmpeg 자동 수급 — BtbN 최신 릴리스 동적 해석 (v3.8.4).

    [동적 버전] johnvansickle 고정 amd64 URL을 폐기. GitHub API latest +
    checksums.sha256으로 linux64/linuxarm64 static GPL tar.xz를 해석한다.

    [격리] 시스템 패키지 매니저(apt/dnf/pacman) 서브프로세스 철폐 유지.
    """
    dest = Path(config.writable_base()) / FFMPEG_DIRNAME

    max_retries = 3
    last_err = None
    for attempt in range(max_retries):
        if attempt > 0:
            log(emit_component("DEPS", "WARN", "FFMP", f"retry {attempt}/{max_retries}"))
            time.sleep(2 ** attempt)

        try:
            log(emit_component("DEPS", "RUN", "FFMP", "resolving latest (github)..."))
            plan = _resolve_btbn_ffmpeg()
            log(emit_component("DEPS", "RUN", "FFMP", f"downloading {plan['version']}..."))

            os.makedirs(dest, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix="cz_ffmpeg_") as td:
                archive = _download(
                    plan["url"], os.path.join(td, plan["asset_name"]),
                    log, "ffmpeg", expected_sha256=plan["sha256"],
                )
                staging = _safe_extract(archive, plan["archive_type"], Path(td) / "x")
                binaries = _locate_binaries(staging)

            if "ffmpeg" not in binaries:
                last_err = f"ffmpeg binary not found in {plan['asset_name']}"
                log(emit_error_warn("DEPS", "FFMP", "binary missing", "retry mirror (1/3)"))
                continue

            bin_dir = _atomic_install(binaries, dest)
            exe_path = bin_dir / "ffmpeg"
            if not exe_path.is_file() or not _verify_ffmpeg(str(exe_path)):
                last_err = "ffmpeg install verification failed"
                continue

            _wire_ffmpeg_path(str(bin_dir))
            log(emit_component("DEPS", "OK", "FFMP", f"ok ({plan['version']})"))
            _record_provision_plan(plan, str(exe_path))
            return None
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
            log(emit_error_warn("DEPS", "FFMP", "download failed", f"{type(e).__name__} (F12)"))

    return f"linux ffmpeg install failed after {max_retries} attempts: {last_err}"


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

def _verify_ffmpeg(ffmpeg_path, env_extra=None):
    """ffmpeg 실행 가능 여부 검증 (dyld 에러 원인 보존).

    [F12] 실행 원문(`$ ffmpeg -version` + 출력/오류)은 log_f12_cli로만 발행한다 —
    to_tui=False 강제이므로 메인 콘솔은 오염되지 않는다.
    """
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    try:
        result = subprocess.run(
            [str(ffmpeg_path), "-version"],
            capture_output=True,
            timeout=10,
            env=env,
        )
        out = (result.stdout or b"").decode("utf-8", errors="replace")
        err = (result.stderr or b"").decode("utf-8", errors="replace")
        log_f12_cli(
            f"{ffmpeg_path} -version",
            (out + err).strip(),
            is_error=(result.returncode != 0),
        )
        return result.returncode == 0
    except Exception as e:
        log_f12_cli(f"{ffmpeg_path} -version", f"[{type(e).__name__}] {e}", is_error=True)
        return False



```

## File: chzzktube\infra\node_provider.py

```python
"""Node.js 런타임 수급 전용 모듈 (SSOT: writable_base()/node 단일 경로).

- node_exe / node_major_version / npm_exe : node 실행 파일 탐색
- node_ok / ensure_node_runtime : bgutil 요구 버전 충족 검증·자동 수급
- bundled_npm_ok : 포터블 npm 무결성 검사

[SSOT 원칙 v3.10.0]
- 오직 writable_base()/node/ 단일 경로만 읽기/쓰기
- 시스템 PATH / frozen 번들(_MEIPASS, _internal) / bundle_root 탐색 완전 제거
- 수급은 ProvisioningManager(bridge) 위임 — 이 모듈은 경로 판정만 담당
- 앱 전용 경로에 없으면 정직하게 None 반환 (FAIL FAST, silent fallback 없음)

서버 기동/빌드/소스 수급은 pot_server.py가 담당.
"""
import json
import os
import platform
import re
import subprocess
import urllib.request

import chzzktube.core.config as config
from chzzktube.core.raw_log import log_f12_cli
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
        version_out = (out.stdout or "").strip()
        log_f12_cli(f"{node_path} --version", version_out)
        m = re.match(r"v?(\d+)", version_out)
        if m:
            major = int(m.group(1))
    except Exception as e:
        major = None
        # [Silent fallback 제거] 버전 판별 실패 로그
        log_f12_cli(f"{node_path} --version", f"Exception: {e}", is_error=True)
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
        direct_bin = os.path.join(local_node_dir, exe_name)
        if os.path.isfile(direct_bin):
            cands.append(direct_bin)
        direct_subbin = os.path.join(local_node_dir, "bin", exe_name)
        if os.path.isfile(direct_subbin):
            cands.append(direct_subbin)
        for root, dirs, files in os.walk(local_node_dir):
            dirs[:] = [d for d in dirs if not d.startswith(("cz_", ".tmp", "temp"))]
            if exe_name in files:
                p = os.path.join(root, exe_name)
                if p not in cands:
                    cands.append(p)

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
        os.path.join(get_writable_base(), "node", "lib", "node_modules", "npm", "package.json"),
        os.path.join(get_writable_base(), "node", "node_modules", "npm", "package.json"),
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

        def _bridge_log(evt, **kwargs):
            is_status = kwargs.get("is_status", getattr(evt, "is_status", False))
            is_error = kwargs.get("is_error", getattr(evt, "is_error", False))
            component_id = kwargs.get("component_id", getattr(evt, "component_id", "deps_node"))
            is_progress = kwargs.get("is_progress", getattr(evt, "is_progress", False))
            msg = evt if isinstance(evt, str) else getattr(evt, "msg", str(evt))
            try:
                log_func(msg, is_status=is_status, is_error=is_error,
                         component_id=component_id, is_progress=is_progress)
            except TypeError:
                try:
                    log_func(msg, is_status=is_status, is_error=is_error)
                except TypeError:
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

## File: chzzktube\infra\paths.py

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

## File: chzzktube\infra\platform.py

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
import asyncio
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


def strip_macos_quarantine(path: str) -> None:
    """macOS quarantine xattr 제거 (동기). 비-macOS 및 xattr 부재 시 무해한 no-op."""
    if not is_macos() or not path:
        return
    try:
        subprocess.run(
            ["xattr", "-dr", "com.apple.quarantine", str(path)],
            capture_output=True, check=False,
        )
    except Exception:
        pass


async def astrip_macos_quarantine(path: str) -> None:
    """`strip_macos_quarantine`의 async 래퍼 — worker thread 위임.

    async 함수에서 `subprocess.run`을 직접 호출하면 이벤트 루프가 블로킹되므로
    (ruff ASYNC221) 반드시 이 헬퍼를 경유한다. 비-macOS에서는 thread 생성 없이 즉시 반환.
    """
    if not is_macos() or not path:
        return
    await asyncio.to_thread(strip_macos_quarantine, path)


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

## File: chzzktube\infra\po_client.py

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
    except Exception as e:
        # [Silent fallback 제거] 예외를 삼키지 않고 로그 후 down 반환
        import chzzktube.core.raw_log as raw_log
        raw_log.raw("POT", f"probe_server error: {type(e).__name__}: {e}", is_error=True, to_tui=False)
        return "down", f"error: {type(e).__name__}"

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
    except Exception as e:
        # [Silent fallback 제거] 예외를 삼키지 않고 로그
        import chzzktube.core.raw_log as raw_log
        raw_log.raw("POT", f"fetch_po_token error: {type(e).__name__}: {e}", is_error=True, to_tui=False)
    return None, None


def extract_video_id(url):
    """YouTube URL에서 11자리 video ID 추출 (실패 시 None)."""
    m = re.search(
        r"(?:v=|/shorts/|/embed/|youtu\.be/)([a-zA-Z0-9_-]{11})", str(url or "")
    )
    return m.group(1) if m else None
```

## File: chzzktube\infra\pot_provider.py

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

## File: chzzktube\infra\pot_server.py

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
from chzzktube.core import DOWNLOAD_TIMEOUT, READ_TIMEOUT
from chzzktube.core.log_emitter import emit_component
from chzzktube.core.raw_log import log_f12_cli, log_f12_net
from chzzktube.infra.po_client import DEFAULT_HOST, DEFAULT_PORT, probe_server
from chzzktube.infra.node_provider import NODE_MIN_MAJOR
from chzzktube.infra.paths import get_writable_base, is_portable, bundle_root
from chzzktube.ui import ProgressBar
from chzzktube.infra.platform import (
    attach_to_parent_lifecycle,
    daemon_spawn_kwargs,
    is_windows,
)
from chzzktube.infra.platform import kill_tree as kill_tree_platform
from dataclasses import dataclass
from typing import Optional


@dataclass
class Result:
    """표준화된 성공/실패 결과 (예외 대신 명시적 반환)."""
    success: bool
    value: Optional[object] = None
    error: Optional[str] = None


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
    except Exception as e:
        import chzzktube.core.raw_log as raw_log
        raw_log.raw("POT", f"assign_to_job_object error: {type(e).__name__}: {e}", is_error=True, to_tui=False)


def read_server_log_tail(n=10):
    """bgutil_server.log의 마지막 n줄 반환 (디버깅용)."""
    log_file_path = os.path.join(get_writable_base(), "bgutil_server.log")
    if os.path.isfile(log_file_path):
        try:
            with open(log_file_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            return "".join(lines[-n:])
        except Exception as e:
            import chzzktube.core.raw_log as raw_log
            raw_log.raw("POT", f"read_server_log_tail error: {type(e).__name__}: {e}", is_error=True, to_tui=False)
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
    except Exception as e:
        import chzzktube.core.raw_log as raw_log
        raw_log.raw("POT", f"latest_server_ver error: {type(e).__name__}: {e}", is_error=True, to_tui=False)
        return None


def server_installed_ver():
    """로컬에 전개된 bgutil 서버 버전 (.version 마커 또는 package.json). 없으면 None."""
    for cand in (
        os.path.join(server_home(), ".version"),
        os.path.join(server_home(), "server", ".version"),
    ):
        try:
            if os.path.isfile(cand):
                with open(cand, encoding="utf-8") as f:
                    v = f.read().strip()
                    if v:
                        return v
        except OSError:
            pass
    # 폴백: server/package.json
    try:
        pkg_json = os.path.join(server_home(), "server", "package.json")
        if os.path.isfile(pkg_json):
            with open(pkg_json, encoding="utf-8") as f:
                return json.load(f).get("version")
    except Exception:
        pass
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
    except Exception as e:
        import chzzktube.core.raw_log as raw_log
        raw_log.raw("POT", f"_kill error: {type(e).__name__}: {e}", is_error=True, to_tui=False)


def kill_tree(proc):
    """프로세스 트리 종료 — 실체는 platform.kill_tree (하위 호환 재수출)."""
    kill_tree_platform(proc)
    try:
        if getattr(proc, "_ct_job", None):
            proc._ct_job = None
    except Exception as e:
        import chzzktube.core.raw_log as raw_log
        raw_log.raw("POT", f"kill_tree error: {type(e).__name__}: {e}", is_error=True, to_tui=False)


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
            except Exception as e:
                import chzzktube.core.raw_log as raw_log
                raw_log.raw("POT", f"kill_process_on_port windows error: {type(e).__name__}: {e}", is_error=True, to_tui=False)
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
            except Exception as e:
                import chzzktube.core.raw_log as raw_log
                raw_log.raw("POT", f"kill_process_on_port posix error: {type(e).__name__}: {e}", is_error=True, to_tui=False)
    except Exception as e:
        import chzzktube.core.raw_log as raw_log
        raw_log.raw("POT", f"kill_process_on_port error: {type(e).__name__}: {e}", is_error=True, to_tui=False)
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
                except Exception as e:
                    import chzzktube.core.raw_log as raw_log
                    raw_log.raw("POT", f"log_func error: {type(e).__name__}: {e}", is_error=True, to_tui=False)
            return False, "node missing"
    except Exception as e:
        import chzzktube.core.raw_log as raw_log
        raw_log.raw("POT", f"node check error: {type(e).__name__}: {e}", is_error=True, to_tui=False)
        return False, "node missing"
    try:
        js = built_server_js()
        if not js:
            if log_func:
                try:
                    log_func("[pot-readiness] not ready: no build")
                except Exception as e:
                    import chzzktube.core.raw_log as raw_log
                    raw_log.raw("POT", f"log_func error: {type(e).__name__}: {e}", is_error=True, to_tui=False)
            return False, "no build"
    except Exception as e:
        import chzzktube.core.raw_log as raw_log
        raw_log.raw("POT", f"built_server_js error: {type(e).__name__}: {e}", is_error=True, to_tui=False)
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
                    except Exception as e:
                        import chzzktube.core.raw_log as raw_log
                        raw_log.raw("POT", f"log_func error: {type(e).__name__}: {e}", is_error=True, to_tui=False)
                if want_refresh:
                    return True, f"stale {local}→{remote} (refresh pending)"
                return False, f"stale {local}→{remote}"
        except Exception as e:
            import chzzktube.core.raw_log as raw_log
            raw_log.raw("POT", f"stale check error: {type(e).__name__}: {e}", is_error=True, to_tui=False)
    if log_func:
        try:
            log_func(f"[pot-readiness] standby (node ok, build {js})")
        except Exception as e:
            import chzzktube.core.raw_log as raw_log
            raw_log.raw("POT", f"log_func error: {type(e).__name__}: {e}", is_error=True, to_tui=False)
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
    except Exception as e:
        import chzzktube.core.raw_log as raw_log
        raw_log.raw("POT", f"open server log error: {type(e).__name__}: {e}", is_error=True, to_tui=False)
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


def _download_with_progress(url, dest_path, log_func=None, desc="downloading", timeout=DOWNLOAD_TIMEOUT):
    """청크 단위 분할 다운로드 및 콘솔에 친절한 진행률 출력.

    ProgressBar를 사용하여 TUI 상태 줄 갱신형 + F12 갱신형으로 진행률 기록.
    """
    with ProgressBar(component=desc, log_func=log_func) as bar:
        bar.start()
        temp_dest = dest_path + ".tmp"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ChzzkTube"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                # Set per-read timeout
                try:
                    sock = resp.fp.raw._sock
                    if sock is not None:
                        sock.settimeout(READ_TIMEOUT)
                except AttributeError:
                    pass

                total_size = int(resp.headers.get("content-length", 0))
                downloaded = 0
                with open(temp_dest, "wb") as f:
                    while True:
                        chunk = resp.read(1024 * 1024)  # 1MB
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        bar.update(downloaded, total_size)

                if os.path.exists(temp_dest):
                    shutil.move(temp_dest, dest_path)
                bar.finish("completed")
        finally:
            if os.path.exists(temp_dest):
                try:
                    os.remove(temp_dest)
                except Exception as e:
                    import chzzktube.core.raw_log as raw_log
                    raw_log.raw("POT", f"temp file cleanup error: {type(e).__name__}: {e}", is_error=True, to_tui=False)


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
            except Exception as e:
                import chzzktube.core.raw_log as raw_log
                raw_log.raw("POT", f"_pid_alive windows error: {type(e).__name__}: {e}", is_error=True, to_tui=False)
                return True  # 판별 자체 실패 → 보수적 유지
        else:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return False
            except PermissionError:
                return True  # 존재하나 권한 없음 → 살아있음
            except Exception as e:
                import chzzktube.core.raw_log as raw_log
                raw_log.raw("POT", f"_pid_alive posix error: {type(e).__name__}: {e}", is_error=True, to_tui=False)
                return True
            return True
    except Exception as e:
        import chzzktube.core.raw_log as raw_log
        raw_log.raw("POT", f"_pid_alive error: {type(e).__name__}: {e}", is_error=True, to_tui=False)
        return True


def _read_lock_info(path):
    """락 파일에서 (pid:int|None, epoch:float|None) 판독."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            parts = f.read().strip().split()
        pid = int(parts[0]) if parts else None
        epoch = float(parts[1]) if len(parts) > 1 else None
        return pid, epoch
    except Exception as e:
        import chzzktube.core.raw_log as raw_log
        raw_log.raw("POT", f"_read_lock_info error: {type(e).__name__}: {e}", is_error=True, to_tui=False)
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
                except Exception as e:
                    import chzzktube.core.raw_log as raw_log
                    raw_log.raw("POT", f"log_func error: {type(e).__name__}: {e}", is_error=True, to_tui=False)
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
                    except Exception as e:
                        import chzzktube.core.raw_log as raw_log
                        raw_log.raw("POT", f"log_func error: {type(e).__name__}: {e}", is_error=True, to_tui=False)
                try:
                    os.remove(path)
                except OSError:
                    pass
                continue
            if log_func and not waited_note and timeout > 0:
                waited_note = True
                try:
                    log_func(f"[prewarm-lock] waiting (holder pid={pid}, alive={alive})")
                except Exception as e:
                    import chzzktube.core.raw_log as raw_log
                    raw_log.raw("POT", f"log_func error: {type(e).__name__}: {e}", is_error=True, to_tui=False)
        except OSError:
            return None
        if _time.monotonic() >= deadline:
            if log_func:
                try:
                    log_func("[prewarm-lock] busy — acquire timeout")
                except Exception as e:
                    import chzzktube.core.raw_log as raw_log
                    raw_log.raw("POT", f"log_func error: {type(e).__name__}: {e}", is_error=True, to_tui=False)
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
        except Exception as e:
            import chzzktube.core.raw_log as raw_log
            raw_log.raw("POT", f"log_func error: {type(e).__name__}: {e}", is_error=True, to_tui=False)


def download_and_install_source(want_ver, log_func=None):
    """지정된 버전의 bgutil 서버 소스를 다운로드하여 세팅한다."""
    dest_dir = server_home()
    tmp = tempfile.mkdtemp(prefix="chzzktube_bgutil_")
    zpath = os.path.join(tmp, "src.zip")
    try:
        url = _TAG_ZIP.format(ver=want_ver)
        log_f12_net(f"GET {url} -> {zpath}")
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
        try:
            with open(os.path.join(dest_dir, ".version"), "w", encoding="utf-8") as vf:
                vf.write(str(want_ver))
            with open(os.path.join(dest_dir, "server", ".version"), "w", encoding="utf-8") as vf:
                vf.write(str(want_ver))
        except Exception:
            pass
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
    [F12] 실행 원문(`$ cmdline` + stdout/stderr)은 log_f12_cli로만 발행한다 —
    to_tui=False 강제이므로 메인 TUI 콘솔은 오염되지 않는다.
    """
    cmd_line = " ".join(map(str, cmd))
    log_f12_cli(cmd_line, None)
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
            log_f12_cli(cmd_line, f"timeout ({timeout}s) — killed", is_error=True)
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
        if stdout:
            log_f12_cli(cmd_line, stdout, is_error=(proc.returncode != 0))
            if log_full_func:
                for line in stdout.splitlines():
                    stripped = line.strip()
                    if stripped:
                        log_full_func(stripped)
        return proc.returncode
    except Exception as e:
        log_f12_cli(cmd_line, f"[{type(e).__name__}] {e}", is_error=True)
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
    except Exception as e:
        import chzzktube.core.raw_log as raw_log
        raw_log.raw("POT", f"_prune_outdated_node_dirs error: {type(e).__name__}: {e}", is_error=True, to_tui=False)


def _ensure_node_runtime(log) -> Result:
    """Node.js 런타임 가용성 확인."""
    from chzzktube.infra.node_provider import ensure_node_runtime, node_exe
    if not ensure_node_runtime(log):
        return Result(success=False, error=f"Node.js runtime unavailable (>= {NODE_MIN_MAJOR} required)")
    curr_node = node_exe()
    if not curr_node:
        return Result(success=False, error="Node.js executable not found")
    return Result(success=True, value=curr_node)


def _resolve_npm_command(curr_node) -> Result:
    """npm 명령어 결정 (npm-cli.js → npm_exe 우선순위)."""
    npm_cli = None
    node_base_dir = os.path.dirname(curr_node)
    search_dirs = [node_base_dir]
    if os.path.basename(node_base_dir) == "bin":
        search_dirs.append(os.path.dirname(node_base_dir))
    for s_dir in search_dirs:
        for root, dirs, files in os.walk(s_dir):
            if "npm-cli.js" in files:
                npm_cli = os.path.join(root, "npm-cli.js")
                break
        if npm_cli:
            break
    if npm_cli:
        return Result(success=True, value=[curr_node, npm_cli])
    from chzzktube.infra.node_provider import npm_exe
    npm_path = npm_exe()
    if not npm_path:
        return Result(success=False, error="npm not found in isolated Node.js runtime")
    return Result(success=True, value=[npm_path])


def _ensure_source_fetched(ver, log, log_full):
    """소스 코드 존재 확인 및 필요 시 다운로드."""
    server_src_dir = os.path.join(server_home(), "server")
    source_exists = os.path.isdir(server_src_dir) and os.path.isfile(
        os.path.join(server_src_dir, "package.json")
    )
    if not source_exists:
        log(emit_component("pot", "RUN", "pot", f"bgutil source fetching (v{ver})"))
        try:
            download_and_install_source(ver, log)
        except Exception as ds_ex:
            log_full(f"[pot] source fetch failed: {ds_ex}")
    else:
        log(emit_component("pot", "RUN", "pot", "bgutil source detected — building"))


def _run_npm_install(server_dir, npm_cmd, curr_node, log, log_full, tick_func, proc_registry) -> Result:
    """npm ci 실행."""
    log(emit_component("pot", "RUN", "pot", "npm install... (first run may take minutes)"))
    env = os.environ.copy()
    node_dir = os.path.dirname(os.path.abspath(curr_node))
    env["PATH"] = node_dir + os.pathsep + env.get("PATH", "")
    ret = _run_and_stream_log(
        npm_cmd + ["ci", "--no-audit", "--no-fund"], server_dir, log_full, env=env,
        timeout=_NPM_CI_TIMEOUT, tick_func=tick_func, proc_registry=proc_registry,
    )
    if ret != 0:
        return Result(success=False, error=f"npm install failed (exit code {ret})")
    return Result(success=True)


def _run_tsc_compile(server_dir, curr_node, npm_cmd, log, log_full, tick_func, proc_registry) -> Result:
    """tsc 컴파일 실행."""
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
        cmd_build = [*npm_cmd, "exec", "tsc"] if npm_cmd else ["npx", "tsc"]

    # env 구성 (npm install과 동일하게)
    env = os.environ.copy()
    node_dir = os.path.dirname(os.path.abspath(curr_node))
    env["PATH"] = node_dir + os.pathsep + env.get("PATH", "")

    ret = _run_and_stream_log(
        cmd_build, server_dir, log_full, env=env,
        use_no_window=False, timeout=_TSC_TIMEOUT,
        tick_func=tick_func, proc_registry=proc_registry,
    )
    if ret != 0:
        return Result(success=False, error=f"tsc failed (exit code {ret})")
    return Result(success=True)


def _verify_build_output() -> Result:
    """빌드 산출물 검증."""
    if built_server_js() is None:
        return Result(success=False, error="server/build/main.js (or dist/main.js) missing after compile")
    return Result(success=True)


def ensure_node_server(log, log_full, want_ver, rebuild=False,
                       tick_func=None, proc_registry=None) -> Result:
    """Node.js HTTP 서버 및 빌드 소스 구성을 완료한다.

    [rebuild 플래그]
    - True: 기존 빌드가 있더라도 npm ci / tsc 강제 재실행 (서버 업데이트용)
    - False: 빌드 산출물 존재 시 재사용 (런타임만 확인)

    [흐름]
    1. 빌드 디렉터리(server/) 존재 여부로 분기
       - server/ 없음 → source fetch → npm ci → tsc
       - server/ 있음 + rebuild=False → 기존 빌드 재사용
    2. 빌드 성공 시 server_dir 반환 → 호출부에서 _spawn_existing 기동

    반환: Result(success=True, value=server_dir) 또는 Result(success=False, error=str)
    """
    from chzzktube.infra.node_provider import (
        node_exe, node_ok, node_major_version,
        ensure_node_runtime, bundled_npm_ok,
    )

    js = built_server_js()

    # [rebuild 모드] npm ci + tsc 강제 재실행
    if js is None or rebuild:
        ver = want_ver or latest_server_ver() or _SERVER_FALLBACK_VER
        # 1단계: 소스 확보
        _ensure_source_fetched(ver, log, log_full)

        # 2단계: Node.js 런타임 확인
        node_result = _ensure_node_runtime(log)
        if not node_result.success:
            return Result(success=False, error=node_result.error)
        curr_node = node_result.value

        # 3단계: npm 명령 결정
        npm_result = _resolve_npm_command(curr_node)
        if not npm_result.success:
            return Result(success=False, error=npm_result.error)
        npm_cmd = npm_result.value

        server_dir = os.path.join(server_home(), "server")

        # 4단계: npm install
        install_result = _run_npm_install(server_dir, npm_cmd, curr_node, log, log_full, tick_func, proc_registry)
        if not install_result.success:
            return Result(success=False, error=install_result.error)

        # 5단계: tsc 컴파일
        tsc_result = _run_tsc_compile(server_dir, curr_node, npm_cmd, log, log_full, tick_func, proc_registry)
        if not tsc_result.success:
            return Result(success=False, error=tsc_result.error)

        # 6단계: 빌드 산출물 검증
        verify_result = _verify_build_output()
        if not verify_result.success:
            return Result(success=False, error=verify_result.error)

        try:
            with open(os.path.join(server_home(), ".version"), "w", encoding="utf-8") as vf:
                vf.write(str(ver))
            with open(os.path.join(server_home(), "server", ".version"), "w", encoding="utf-8") as vf:
                vf.write(str(ver))
        except Exception:
            pass

        return Result(success=True, value=server_dir)

    # [재사용 모드] 기존 빌드가 있으면 런타임만 확인 → 즉시 반환
    if not ensure_node_runtime(log):
        return Result(success=False, error="Node.js runtime unavailable")
    if node_ok():
        return Result(success=True, value=os.path.dirname(server_home()))
    return Result(success=False, error="Node.js runtime check failed")

```

## File: chzzktube\infra\pylib_bootstrap.py

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
                if mod_name.startswith("yt_dlp"):
                    del sys.modules[mod_name]
        except Exception:
            pass
    return path
```

## File: chzzktube\infra\updater.py

```python
##### updater.py - pip component (yt-dlp) version check and update helper
"""PyPI metadata query for latest versions, optional pip upgrade on demand.
*  Version check: PyPI JSON API (lightweight, no pip needed)
*  Upgrade:
    - Stable channel: python -m pip install -U <pkg>
    - Nightly channel: python -m pip install -U yt-dlp-nightly (yt-dlp only)
*  frozen(PyInstaller) builds — pip이 없으므로 직접 다운로드:
    - yt-dlp: GitHub release에서 yt-dlp 바이너리 직접 다운로드 후 교체 (yt_dlp_binary 위임, .pylib 미사용)
    - 업데이트 실패 시 기존 버전 유지, 다음 실행 시 재시도
*  네트워크 의존은 이 앱에서 본질적이다 (웹 미디어 추출기). """
import concurrent.futures
import json
import os
import shutil
import subprocess
import sys
import tempfile
import socket
import urllib.request
from chzzktube.infra.platform import spawn_kwargs
from chzzktube.core.raw_log import log_f12_cli, log_f12_net

# (log_label, pypi_name, pypi_nightly) — log_label is shown in the DEPS PLATFORM column
# pypi_nightly: Nightly 채널 사용 시 설치할 PyPI 패키지명 (None이면 Stable only)
# [v3.10.0] streamlink 제거 — 라이브 녹화는 yt-dlp 단일 경로로 통합.
# [전환] bgutil-ytdlp-pot-provider 제외: 플러그인(pip)에서 독립 Node 서버로
# 이동 — 버전 관리 주체는 pot_provider(latest_server_ver)가 담당.
PACKAGES = [("ytdlp", "yt-dlp", "yt-dlp-nightly")]
# [주의] socket.setdefaulttimeout() 절대 사용 금지 — 프로세스 전체의 소켓 기본
# 타임아웃을 오염시켜 yt-dlp 미디어 스트림 재시도 루프(0.0% 스톨)를 유발.
# DNS hang 방어는 아래 latest_version의 ThreadPoolExecutor + urlopen(timeout)으로 충분.

_PYPI_API = "https://pypi.org/pypi/{pkg}/json"

def installed_version(pypi_name):
    """Installed version string from binary (yt-dlp) or .pylib overlay (others).

    SSOT: yt-dlp는 yt_dlp_binary.yt_dlp_version() 사용 (바이너리 전용), 나머지는 .pylib 내부 dist-info만 스캔.
    .venv나 시스템 site-packages에 존재하더라도 무시한다.
    """
    # yt-dlp는 독립 실행형 바이너리 사용
    if pypi_name == "yt-dlp":
        from chzzktube.infra.yt_dlp_binary import yt_dlp_version, yt_dlp_path
        exe = yt_dlp_path()
        if exe:
            ver = yt_dlp_version(exe)
            if ver:
                return ".".join(map(str, ver))
        return None

    import glob
    import os
    from chzzktube.core.config import pylib_overlay_path

    pylib_root = pylib_overlay_path()
    if not os.path.isdir(pylib_root):
        return None

    # 패키지명 정규화: yt-dlp -> yt_dlp
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
            except Exception as e:
                import chzzktube.core.raw_log as raw_log
                raw_log.raw("DEPS", f"installed_version metadata read error: {type(e).__name__}: {e}", is_error=True, to_tui=False)
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
    except Exception as e:
        import chzzktube.core.raw_log as raw_log
        raw_log.raw("DEPS", f"latest_version PyPI fetch error: {type(e).__name__}: {e}", is_error=True, to_tui=False)
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
    except Exception as e:
        import chzzktube.core.raw_log as raw_log
        raw_log.raw("DEPS", f"is_outdated version compare error: {type(e).__name__}: {e}", is_error=True, to_tui=False)
        return False

def outdated_packages(channel="stable"):
    """List of (label, pypi_name, cur, latest) needing update.
    channel: stable / nightly (yt-dlp-nightly / GitHub builds).
    미설치 상태는 check_deps가 FAIL로 처리하므로 stale 목록에 포함하지 않는다.
    """
    stale = []
    for label, pypi_name, pypi_nightly in PACKAGES:
        if channel == "nightly" and pypi_nightly:
            cur = installed_version(pypi_nightly) or installed_version(pypi_name)
            latest = latest_version(pypi_nightly)
            if cur and latest and is_outdated(cur, latest):
                stale.append((label, pypi_name, cur, latest))
            continue
        # stable channel: leftover nightly -> downgrade target
        if pypi_nightly and installed_version(pypi_nightly):
            stale.append((label, pypi_name, str(installed_version(pypi_nightly)) + " (nightly)", "stable"))
            continue
        cur = installed_version(pypi_name)
        latest = latest_version(pypi_name)
        if cur and latest and is_outdated(cur, latest):
            stale.append((label, pypi_name, cur, latest))
    return stale


def check_deps(log_func=None):
    """모든 의존성 체크 결과 리스트 반환.
    각 요소: (label, status, msg)
    label: "ytdlp" | "ffmpeg" | "node" | "pot"
    status: "OK" | "FAIL" | "SKIP"
    msg: "vX.Y.Z at <path>" | "not installed" | "<reason>"
    log_func(msg): POT readiness 판정 근거를 raw 스택으로 반환 (단일 호출).
    """
    import os
    results = []

    # 1. yt-dlp (독립 실행형 바이너리) — 앱 전용 경로 확인
    # yt-dlp-nightly는 dist 명이 달라 .pylib 체크가 실패하므로
    # nightly 설치물로 폴백 표기 (정상 설치 판정 유지)
    label = "ytdlp"
    pypi_name = "yt-dlp"
    pypi_nightly = "yt-dlp-nightly"

    # yt-dlp는 독립 실행형 바이너리 사용 (yt_dlp_binary 모듈)
    from chzzktube.infra.yt_dlp_binary import yt_dlp_version, yt_dlp_path
    exe = yt_dlp_path()
    if exe:
        ver_tuple = yt_dlp_version(exe)
        if ver_tuple:
            ver = ".".join(map(str, ver_tuple))
        else:
            ver = None
    else:
        ver = None

    # nightly 채널 설치물 인지 (pypi overlay 체크)
    if not ver and pypi_nightly:
        nver = installed_version(pypi_nightly)
        if nver:
            ver = f"{nver} (nightly)"

    if ver:
        results.append((label, "OK", f"{ver} at {exe}"))
        log_f12_cli(f"{exe} --version", ver)
    else:
        results.append((label, "FAIL", "not installed"))
        log_f12_net("yt-dlp binary not found", is_error=True)

    # 2. ffmpeg — 앱 전용 캐시 단일 참조 (시스템 PATH 탐색 철폐)
    try:
        from chzzktube.infra.components import ffmpeg_exe
        path = ffmpeg_exe()
    except Exception:
        path = None
    if path:
        ver_str = _ffmpeg_version(path)
        if ver_str:
            results.append(("ffmpeg", "OK", f"{ver_str} at {path}"))
            log_f12_cli(f"{path} -version", ver_str)
        else:
            results.append(("ffmpeg", "FAIL", f"verification failed at {path}"))
            log_f12_cli(f"{path} -version", "execution test failed", is_error=True)
    else:
        results.append(("ffmpeg", "FAIL", "not installed"))
        log_f12_net("ffmpeg binary not found in cache", is_error=True)

    # 3. node — 앱 전용 포터블 런타임 단일 참조
    try:
        import chzzktube.infra.pot_provider as pot_provider
        path = pot_provider.node_exe()
        maj = pot_provider.node_major_version(path)
    except Exception:
        path, maj = None, None
    if path and maj:
        results.append(("node", "OK", f"v{maj} at {path}"))
        log_f12_cli(f"{path} --version", f"v{maj}")
    else:
        results.append(("node", "FAIL", "not installed"))
        log_f12_net("node runtime not found in app path", is_error=True)

    # 4. bgutil 소스코드 무결성 검증
    try:
        from chzzktube.infra.pot_server import server_installed_ver, server_home
        ver = server_installed_ver()
        if ver:
            results.append(("bgutil", "OK", f"v{ver} at {server_home()}"))
            log_f12_net(f"bgutil provider version: v{ver} at {server_home()}")
        else:
            results.append(("bgutil", "FAIL", "not installed"))
            log_f12_net("bgutil provider source not installed", is_error=True)
    except Exception as e:
        results.append(("bgutil", "FAIL", "unknown"))
        log_f12_net(f"bgutil check failed: {e}", is_error=True)

    # 5. PO token 서버 — liveness가 아니라 readiness 판정
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
                results.append(("pot", "SKIP", reason or "not ready"))
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
    from chzzktube.infra.platform import spawn_kwargs

    missing = []

    # 1. yt-dlp (독립 실행형 바이너리) — 앱 전용 경로에서 실행 확인
    from chzzktube.infra.yt_dlp_binary import yt_dlp_path, yt_dlp_version
    exe = yt_dlp_path()
    if not exe:
        missing.append("yt-dlp (not found in app binary path)")
    else:
        # 실행 테스트
        result = subprocess.run(
            [exe, "--version"],
            capture_output=True,
            timeout=5,
            **spawn_kwargs(),
        )
        if result.returncode != 0:
            missing.append("yt-dlp (execution failed)")

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

    # 4. bgutil 소스코드 무결성 검증
    try:
        from chzzktube.infra.pot_server import server_installed_ver
        if not server_installed_ver():
            missing.append("bgutil (not installed)")
    except Exception:
        missing.append("bgutil (check error)")

    return len(missing) == 0, missing


_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _cli_base(label):
    """라벨 → 실제 CLI 명령 배열 (없으면 None). F12 상세 로그용 원문 실행.

    [v3.8.0 격리] 실행체 해석은 앱 전용 저장소 단일 경로로 일원화:
    - ytdlp: dev/frozen 공통 — OS 표준 경로(%LOCALAPPDATA%/ChzzkTube/bin/ 등)에
      설치된 yt-dlp 바이너리 직접 실행. 시스템 PATH의 yt-dlp는 절대 참조하지 않는다.
    - ffmpeg/node/npm: components.ffmpeg_exe / pot_provider.node_exe·npm_exe
      (writable_base 격리 캐시) 단일 참조 — shutil.which 폴백 철폐.
    """
    if label == "ytdlp":
        # dev/frozen 공통: OS 표준 경로에 설치된 yt-dlp 바이너리 직접 실행
        from chzzktube.infra.yt_dlp_binary import yt_dlp_path
        p = yt_dlp_path()
        return [p] if p else None
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


def _parse_ffmpeg_version_text(text: str):
    """ffmpeg 버전 출력 텍스트에서 버전 문자열 추출 (표준 버전 또는 git snapshot N-xxx 등)."""
    if not text:
        return None
    import re
    # 1) 표준 첫 줄 — 숫자 코어
    m = re.search(r"ffmpeg version\s+(\d+(?:\.\d+)+)", text)
    if m:
        return m.group(1)
    # 2) git snapshot 첫 줄 (예: ffmpeg version N-126826-gc0e8b139fd-20260924 ...)
    m = re.search(r"ffmpeg version\s+([^\s,]+)", text)
    if m:
        return m.group(1)
    # 3) configuration 줄 폴백 — --prefix=…/ffmpeg/9.0.1_1
    m = re.search(r"ffmpeg[/\\\-](\d+(?:\.\d+){1,2})(?![0-9.])", text)
    return m.group(1) if m else None


def _ffmpeg_version(path, timeout=3):
    """`ffmpeg -version`에서 버전 추출. 실패 시 None."""
    if not path:
        return None
    path_str = str(path)
    if "\n" in path_str or path_str.startswith("ffmpeg version"):
        return _parse_ffmpeg_version_text(path_str)

    try:
        out = subprocess.run(
            [path, "-version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            **spawn_kwargs(),
        )
        if out.returncode != 0:
            return None
        text = (out.stdout or out.stderr or "")
        return _parse_ffmpeg_version_text(text)
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
    """yt-dlp 업그레이드: yt_dlp_binary.upgrade_yt_dlp()에 위임.

    dev/frozen 공통: venv(site-packages, uv 소유)는 절대 건드리지 않는다.
    yt-dlp 바이너리는 OS 표준 경로(%LOCALAPPDATA%/ChzzkTube/bin/ 등)에 직접 교체.
    """
    from chzzktube.infra.yt_dlp_binary import upgrade_yt_dlp
    return upgrade_yt_dlp(channel)

def _extract_pylib_whl(whl_path, pylib_root, prefix):
    """프로젝트 오버레이(.pylib/)에 whl 해제 + 구 dist-info 정리 (순수·테스트 가능).

    venv(site-packages, uv 소유)는 절대 건드리지 않는다. 해제 후
    sys.path 선두(.pylib/)의 오버레이 복사가 venv보다 항상 우선한다.
    prefix: "yt_dlp-" — 구 dist-info(glob) 스캔용.
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




def upgrade_packages(packages, channel="stable"):
    """직접 다운로드 방식으로 패키지 업데이트 (Dev/Frozen 통합).

    [v3.4.0 변경] 해제 대상은 프로젝트 오버레이(.pylib/) -- venv(site-packages,
    uv 소유)는 절대 건드리지 않는다. 요약 문자열에 "(overlay)" 표기.
    이유: 포터블 빌드와 Dev에서 동일한 코드 경로를 타야 디버깅이 가능.
    pip install은 빌드 시에만 사용 (PyInstaller 번들 시점).

    Returns (returncode, output tail). Worker thread only.
    """
    # yt-dlp: Dev/Frozen 통합 - 직접 다운로드 (yt_dlp_binary 위임)
    if "yt-dlp" in packages:
        return _frozen_upgrade_ytdlp(channel)

```

## File: chzzktube\infra\yt_dlp_binary.py

```python
"""yt-dlp 바이너리 경로 관리 모듈 (SRP: yt-dlp 실행 파일 탐색·수급·갱신만 담당).

- system PATH의 yt-dlp 최우선 사용
- 없으면 OS 표준 경로(%LOCALAPPDATA%\\ChzzkTube\\bin\\ 또는 ~/.local/bin/)에서 탐색
- 없으면 GitHub releases에서 yt-dlp 바이너리 직접 다운로드
- 업데이트는 동일 경로에 덮어쓰기
"""
import os
import sys
import platform
import shutil
import subprocess
import tempfile
import urllib.request
import json
import stat
import re
from pathlib import Path

import chzzktube.core.config as config
from chzzktube.core.log_emitter import emit_component
from chzzktube.core.raw_log import log_f12_cli, log_f12_net
from chzzktube.infra.paths import get_writable_base, is_portable, bundle_root


# ── 상수 ──────────────────────────────────────────────────────────────
YTDLP_MIN_VERSION = (2024, 1, 1)  # 최소 요구 버전
_YTDLP_FALLBACK_VER = "2024.12.19"  # GitHub API 조회 실패 시 폴백

# GitHub releases URL 템플릿
_YTDLP_RELEASE_API = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"
# Nightly builds: 플랫폼별 asset 이름 사용 (stable과 동일 패턴)
_YTDLP_NIGHTLY_BASE = "https://github.com/yt-dlp/yt-dlp-nightly-builds/releases/latest/download"


def _exe_suffix() -> str:
    """현재 OS의 실행 파일 확장자 반환."""
    return ".exe" if sys.platform == "win32" else ""


def _bin_dir() -> Path:
    """yt-dlp 바이너리가 설치될 표준 디렉터리 반환.

    Dev/Frozen 공통: get_writable_base()/bin/
    Windows: %LOCALAPPDATA%/ChzzkTube/bin/
    Unix: ~/.local/bin/
    """
    base = get_writable_base()
    return Path(base) / "bin"


def _platform_asset_name(ver: str) -> str:
    """플랫폼별 yt-dlp 배포 에셋 이름 생성."""
    system = platform.system().lower()
    machine = platform.machine().lower()
    suffix = _exe_suffix()

    if system == "windows":
        # Windows는 x86_64만 공식 지원 (arm64는 별도 빌드 필요)
        return f"yt-dlp{suffix}"
    elif system == "darwin":
        # macOS: 유니버설 바이너리(arm64+x86_64)
        return f"yt-dlp_macos{suffix}"
    else:
        # Linux: x86_64 static 빌드
        return f"yt-dlp_linux{suffix}"


def _platform_asset_url(ver: str) -> str:
    """플랫폼별 yt-dlp 배포 URL 생성."""
    asset = _platform_asset_name(ver)
    return f"https://github.com/yt-dlp/yt-dlp/releases/download/{ver}/{asset}"


def _latest_stable_version() -> str:
    """GitHub API에서 최신 안정 버전 조회 (실패 시 폴백)."""
    try:
        req = urllib.request.Request(
            _YTDLP_RELEASE_API,
            headers={"User-Agent": "ChzzkTube", "Accept": "application/vnd.github.v3+json"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.load(resp)
            tag = data.get("tag_name", "").lstrip("v")
            if tag:
                return tag
    except Exception as e:
        log_f12_net(f"GitHub API failed for latest yt-dlp version: {e}")
    return _YTDLP_FALLBACK_VER


def _download_with_progress(url: str, dest: Path, log_func=None, label: str = "") -> bool:
    """진행 로그 포함 파일 다운로드. 성공 시 True 반환."""
    log_f12_net(f"GET {url} -> {dest}")
    if log_func:
        log_func(emit_component("DEPS", "RUN", "YTDL", f"{label or os.path.basename(url)} downloading..."))

    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ChzzkTube"})
        with urllib.request.urlopen(req, timeout=60) as resp, open(tmp, "wb") as f:
            total = int(resp.headers.get("Content-Length", 0))
            done = 0
            last_pct = -1
            while True:
                chunk = resp.read(1024 * 512)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if total:
                    pct = done * 100 // total
                    if pct != last_pct and pct % 5 == 0:
                        last_pct = pct
                        if log_func:
                            log_func(emit_component("DEPS", "RUN", "YTDL", f"{label} {pct}%"))
        os.replace(tmp, dest)
        log_f12_net(f"Saved {dest} ({dest.stat().st_size / 1048576:.1f} MB)")
        if log_func:
            log_func(emit_component("DEPS", "OK", "YTDL", f"{label} done ({dest.stat().st_size / 1048576:.1f} MB)"))
        return True
    except Exception as e:
        log_f12_net(f"Download failed: {url} ({e})", is_error=True)
        if log_func:
            log_func(emit_component("DEPS", "FAIL", "YTDL", f"{label} download failed: {e}", is_error=True))
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        return False


# ── yt-dlp 실행 파일 탐색 ─────────────────────────────────────────────
def yt_dlp_path() -> str | None:
    """현재 사용 가능한 yt-dlp 실행 파일 경로 반환 (없으면 None).

    우선순위 (앱 전용 경로만):
    1. OS 표준 경로 (get_writable_base()/bin/yt-dlp) — 앱 전용 설치 위치
    2. frozen 빌드 번들 (_MEIPASS) — 포터블 빌드
    3. .pylib 오버레이 (레거시 호환)
    4. system PATH (shutil.which) — 최후 수단으로만 폴백
    """
    suffix = _exe_suffix()
    candidates = []

    # 1. OS 표준 경로 (앱 전용 설치 위치) — 최우선
    local_bin = _bin_dir() / f"yt-dlp{suffix}"
    if local_bin.is_file():
        candidates.append(str(local_bin))

    # 2. frozen 빌드 번들 (_MEIPASS) — 포터블 빌드
    if is_portable():
        bundle = bundle_root()
        if bundle:
            bundled = Path(bundle) / f"yt-dlp{suffix}"
            if bundled.is_file():
                candidates.insert(0, str(bundled))  # 번들을 최우선

    # 3. .pylib 오버레이 (레거시 호환 - 점점 사용 안 함)
    try:
        overlay = config.pylib_overlay_path()
        overlay_bin = Path(overlay) / f"yt-dlp{suffix}"
        if overlay_bin.is_file():
            candidates.append(str(overlay_bin))
    except Exception:
        pass


    # 실행 가능 여부 확인 후 첫 번째 유효한 것 반환
    # 시스템 PATH 폴백 없음 — 앱 전용 경로에 없으면 None 반환 (FAIL)
    for c in candidates:
        if Path(c).is_file() and os.access(c, os.X_OK):
            return c
    return None


def yt_dlp_version(exe_path: str | None = None) -> tuple[int, int, int] | None:
    """yt-dlp --version 출력에서 (major, minor, patch) 튜플 반환."""
    exe = exe_path or yt_dlp_path()
    if not exe:
        return None
    try:
        result = subprocess.run(
            [exe, "--version"],
            capture_output=True, text=True, timeout=10, encoding="utf-8", errors="replace",
        )
        cmd_str = f"{exe} --version"
        output_str = result.stdout or result.stderr or ""
        log_f12_cli(cmd_str, output_str.strip())
        if result.returncode == 0:
            m = re.match(r"(\d+)\.(\d+)\.(\d+)", output_str.strip())
            if m:
                return tuple(map(int, m.groups()))
    except Exception as e:
        log_f12_cli(f"{exe} --version", f"Exception: {e}", is_error=True)
    return None


def yt_dlp_ok(exe_path: str | None = None, min_version: tuple[int, int, int] = YTDLP_MIN_VERSION) -> bool:
    """지정된 버전 이상인지 확인."""
    ver = yt_dlp_version(exe_path)
    return ver is not None and ver >= min_version


# ── yt-dlp 자동 수급/설치 ─────────────────────────────────────────────
def ensure_yt_dlp(log_func=None, channel: str = "stable") -> bool:
    """yt-dlp 실행 파일 확보 (없으면 자동 다운로드/설치)."""
    # 이미 유효한 버전이 있으면 스킵
    if yt_dlp_ok():
        if log_func:
            log_func(emit_component("DEPS", "OK", "YTDL", f"yt-dlp already available"))
        return True

    if log_func:
        log_func(emit_component("DEPS", "RUN", "YTDL", "yt-dlp missing or outdated — downloading..."))

    # 설치 대상 디렉터리
    bin_dir = _bin_dir()
    bin_dir.mkdir(parents=True, exist_ok=True)
    suffix = _exe_suffix()
    dest = bin_dir / f"yt-dlp{suffix}"

    # 채널별 다운로드 URL 결정
    if channel == "nightly":
        # Nightly도 플랫폼별 asset 이름 사용 (macOS는 _macos 접미사 필요)
        asset = _platform_asset_name("nightly")
        url = f"{_YTDLP_NIGHTLY_BASE}/{asset}"
    else:
        ver = _latest_stable_version()
        url = _platform_asset_url(ver)

    try:
        if not _download_with_progress(url, dest, log_func, "yt-dlp binary downloading"):
            return False

        # 실행 권한 부여
        if suffix == ".exe":
            # Windows에서는 확장자로 충분
            pass
        else:
            dest.chmod(dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

        # 버전 검증
        if yt_dlp_ok(str(dest)):
            if log_func:
                log_func(emit_component("DEPS", "OK", "YTDL", f"yt-dlp installed at {dest}"))
            return True
        else:
            if log_func:
                log_func(emit_component("DEPS", "FAIL", "YTDL", "installed binary version check failed", is_error=True))
            return False
    except Exception as e:
        if log_func:
            log_func(emit_component("DEPS", "FAIL", "YTDL", f"install failed: {e}", is_error=True))
        return False

    return False


# ── yt-dlp 업데이트 ───────────────────────────────────────────────────
def upgrade_yt_dlp(channel: str = "stable", log_func=None) -> tuple[int, str]:
    """yt-dlp 바이너리 업데이트 (OS 표준 경로에 직접 교체)."""
    if not ensure_yt_dlp(log_func, channel):
        return 1, "ensure_yt_dlp failed"

    # 현재 버전 확인
    current = yt_dlp_version()
    # 최신 버전 확인
    if channel == "nightly":
        # nightly는 항상 최신으로 간주 (버전 번호 없음)
        return 0, f"updated to nightly"
    else:
        latest = _latest_stable_version()
        if current:
            cur_ver = ".".join(map(str, current))
            if cur_ver == latest:
                return 0, f"already up to date ({cur_ver})"
        return 0, f"updated to {latest}"
```

## File: chzzktube\infra\provisioning\__init__.py

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

## File: chzzktube\infra\provisioning\bridge.py

```python
"""Sync Bridge - 비동기 ProvisioningManager를 동기 컨텍스트에서 호출.

기존 동기 함수(components.ensure_ffmpeg, node_provider.ensure_node_runtime 등)가
ProvisioningManager(async)를 직접 호출할 수 있게 하는 어댑터.

로그 버스 정책: 모든 동작은 raw_log -> LogEvent 단일 경로.

[v3.11.0] 이벤트 루프 재사용: asyncio.run() 대신 기존 루프가 있으면 재사용,
없으면 새로 생성. 중첩 호출 시 안전하게 동작. 생성한 루프는 사용 후 close로 정리.
"""
import asyncio
from typing import Optional

from chzzktube.infra.provisioning.manager import ProvisioningManager, ProvisionResult


_created_loops: set[int] = set()


def _get_or_create_event_loop() -> asyncio.AbstractEventLoop:
    """기존 이벤트 루프를 가져오거나 새로 생성.

    asyncio.run()은 매번 새 루프를 만드는데, 중첩 호출 시 RuntimeError 발생.
    이미 실행 중인 루프가 있으면 그것을 재사용한다. 새로 생성한 루프는
    추적하여 나중에 정리한다.
    """
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        # 실행 중인 루프가 없음 - 새로 생성
        loop = asyncio.new_event_loop()
        _created_loops.add(id(loop))
        return loop


def _run_sync(coro) -> object:
    """코루틴을 동기적으로 실행하며 루프 생명주기 관리.

    - 실행 중인 루프가 있으면 ThreadPoolExecutor를 통해 격리된 스레드에서 asyncio.run 실행
    - 없으면 asyncio.run으로 안전하게 단독 실행
    """
    try:
        running_loop = asyncio.get_running_loop()
    except RuntimeError:
        running_loop = None

    if running_loop and running_loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    else:
        return asyncio.run(coro)


def provision_component_sync(
    component: str,
    log_func=None,
    channel: str = "stable",
    force: bool = False,
) -> Optional[ProvisionResult]:
    """단일 구성요소 동기 수급 - 기존 동기 코드에서 호출.

    Args:
        component: 구성요소명 (yt-dlp, ffmpeg, node, bgutil)
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

    return _run_sync(_run())


def provision_all_sync(
    log_func=None,
    channel: str = "stable",
    stale_only: bool = True,
) -> list[ProvisionResult]:
    """전체 구성요소 동기 수급."""
    async def _run():
        mgr = ProvisioningManager(log_func=log_func)
        return await mgr.ensure_all(stale_only=stale_only, channel=channel)

    return _run_sync(_run())


def resolve_all_sync(
    channel: str = "stable",
    stale_only: bool = False,
) -> list:
    """전체 구성요소 플랜 조회 (다운로드 없이)."""
    async def _run():
        mgr = ProvisioningManager()
        return await mgr.resolve(stale_only=stale_only, channel=channel)

    return _run_sync(_run())

```

## File: chzzktube\infra\provisioning\committer.py

```python
"""Committer — 프로비저닝 결과 커밋 (manifest 저장, overlay/PATH 갱신).

Executor가 완료한 결과를 받아 manifest 업데이트, .pylib overlay 리로드, PATH 추가 수행.
"""
from pathlib import Path
from typing import Optional
import os
import time
import shutil

from chzzktube.core import config
from chzzktube.infra.provisioning.manifest import ProvisionManifest, ComponentRecord
import chzzktube.core.raw_log as raw_log
from chzzktube.core.log_emitter import emit_component
from chzzktube.core.log_event import LogEvent


class Committer:
    """commit 단계만 담당 — manifest 저장 + overlay/PATH 갱신."""

    def __init__(self, base_dir: Path, log_func=None):
        self.base_dir = base_dir
        self.log = log_func
        self.manifest = ProvisionManifest.load(base_dir)
        self.overlay_root = Path(config.pylib_overlay_path())

    def _emit(self, stage, status, scope, msg, is_status=False, is_error=False,
              component_id: str | None = None, is_progress: bool = False):
        """raw_log 버스 단일 경유."""
        evt = emit_component(stage, status, scope, msg, is_status=is_status, is_error=is_error)
        evt.component_id = component_id
        evt.is_progress = is_progress
        raw_log.raw(
            "provisioning", evt, to_tui=is_status, is_error=is_error,
            component_id=component_id, is_progress=is_progress,
        )

    def _emit_via_log(self, event: LogEvent) -> bool:
        """Progress event를 기존 log_func 계약으로 한 번만 중계한다."""
        if self.log is None:
            return False
        try:
            self.log(
                event,
                is_status=event.is_status,
                is_error=event.is_error,
                component_id=event.component_id,
                is_progress=event.is_progress,
            )
        except TypeError:
            self.log(event)
        return True

    def commit(self, plans: list, results: list) -> None:
        """manifest 갱신 + 오버레이/환경변수 리로드."""
        now = time.time()

        for plan, result in zip(plans, results):
            if result.success:
                self.manifest.update_component(ComponentRecord(
                    name=plan.component,
                    version=plan.version,
                    source=plan.mirror_name,
                    mirror=plan.mirror_name,
                    install_path=plan.spec.install_rel_path,
                    verified_at=now,
                    verify_version=result.version or plan.version,
                    sha256=getattr(result, "sha256", "") or (plan.expected_sha256 or ""),
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
            self._emit(
                "DEPS", "OK", "PY", f"overlay refreshed: {path}",
                component_id="deps_PY", is_progress=False,
            )
        except Exception as e:
            self._emit(
                "DEPS", "WARN", "PY", f"overlay refresh failed: {e}",
                component_id="deps_PY", is_progress=False,
            )

    def _refresh_path(self):
        """PATH에 검증된 binary 디렉토리 추가 (SSOT)."""
        try:
            for name, rec in self.manifest.components.items():
                if name in ("ffmpeg", "node"):
                    target_path = self.base_dir / rec.install_path
                    bin_dir = target_path.parent if target_path.suffix or target_path.name in ("ffmpeg", "node") else target_path

                    if bin_dir.is_dir():
                        path_env = os.environ.get("PATH", "")
                        parts = path_env.split(os.pathsep) if path_env else []
                        bin_str = str(bin_dir)
                        if bin_str not in parts:
                            os.environ["PATH"] = os.pathsep.join([bin_str] + parts)
        except Exception as e:
            self._emit(
                "DEPS", "WARN", "PATH", f"PATH refresh failed: {e}",
                component_id="deps_PATH", is_progress=False,
            )
```

## File: chzzktube\infra\provisioning\downloader.py

```python
"""Parallel Downloader — stdlib-only async parallel download & retry."""
import asyncio
import hashlib
import random
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable, Optional

from chzzktube.core.raw_log import log_f12_net


_CHUNK_SIZE = 64 * 1024
_USER_AGENT = "ChzzkTube-Provisioner/1.0"
_READ_TIMEOUT = 30.0  # per-read timeout in seconds


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


ProgressCallback = Callable[[str, int, int, float, float], Awaitable[None]]


def _format_network_error(exc: BaseException) -> str:
    """네트워크/수급 에러를 사용자가 쉽게 파악할 수 있는 안내 문구로 변환."""
    if isinstance(exc, urllib.error.HTTPError):
        if exc.code == 404:
            return f"HTTP 404 Not Found (asset removed or unavailable at mirror) — check update/mirror"
        if exc.code == 403 or exc.code == 429:
            return f"HTTP {exc.code} Rate Limited by host — please try again in a few minutes"
        if exc.code >= 500:
            return f"HTTP {exc.code} Server Error (mirror domain down) — try again later or restart app"
        return f"HTTP {exc.code} {exc.reason} — mirror request failed"
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return "download timed out (connection stalled) — check internet speed and restart app"
    if isinstance(exc, urllib.error.URLError):
        reason = getattr(exc, "reason", str(exc))
        return f"network connection failed ({reason}) — check internet connection and restart app"
    if isinstance(exc, ConnectionError):
        return f"connection dropped ({exc}) — check network stability and restart app"
    if isinstance(exc, ValueError) and "SHA256 mismatch" in str(exc):
        return f"{exc} — corrupted download file removed, retry recommended"
    return f"{type(exc).__name__}: {exc}"


class ParallelDownloader:
    """urllib 요청을 worker thread로 위임하는 비동기 다운로더."""

    def __init__(
        self,
        max_concurrent: int = 5,
        max_retries: int = 3,
        base_timeout: float = 120.0,
        progress_cb: Optional[ProgressCallback] = None,
    ):
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.max_retries = max_retries
        self.base_timeout = base_timeout
        self.progress_cb = progress_cb

    async def download_all(self, tasks: list[DownloadTask]) -> list[DownloadResult]:
        """모든 태스크를 세마포어 제한 아래 병렬 다운로드한다."""

        async def _download_one(task: DownloadTask) -> DownloadResult:
            async with self.semaphore:
                return await self._download_with_retry(task)

        return await asyncio.gather(*[_download_one(task) for task in tasks])

    async def _download_with_retry(self, task: DownloadTask) -> DownloadResult:
        last_error: Optional[BaseException] = None

        for attempt in range(self.max_retries):
            try:
                return await self._download_once(task)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                last_error = exc
                self._remove_part_file(task)
                log_f12_net(
                    f"download attempt {attempt + 1}/{self.max_retries} failed for {task.component}: {exc}",
                    is_error=True,
                )
                if attempt < self.max_retries - 1:
                    wait_time = (2**attempt) + random.uniform(0, 1)
                    await asyncio.sleep(wait_time)

        err_msg = _format_network_error(last_error) if last_error else "Unknown error"
        return DownloadResult(
            task=task,
            success=False,
            error=err_msg,
        )

    @staticmethod
    def _fetch_ghcr_token(url: str) -> str | None:
        """ghcr.io 익명 pull 토큰 조회 (동기 — 반드시 worker thread에서 호출)."""
        try:
            import json as _json
            repo = "homebrew/core/ffmpeg"
            if "/v2/" in url and "/blobs/" in url:
                repo = url.split("/v2/")[1].split("/blobs/")[0]
            tok_url = f"https://ghcr.io/token?scope=repository:{repo}:pull"
            tok_req = urllib.request.Request(tok_url, headers={"User-Agent": _USER_AGENT})
            with urllib.request.urlopen(tok_req, timeout=10.0) as tok_resp:
                return _json.load(tok_resp).get("token")
        except Exception:
            return None

    async def _download_once(self, task: DownloadTask) -> DownloadResult:
        """Worker thread에서 urllib/file I/O를 수행하고 progress를 회수한다."""
        task.dest.parent.mkdir(parents=True, exist_ok=True)
        part_path = task.dest.with_suffix(task.dest.suffix + ".part")
        headers = {"User-Agent": _USER_AGENT}
        if "ghcr.io" in task.url:
            # 블로킹 토큰 조회는 worker thread로 위임 (이벤트 루프 블로킹 금지)
            tok = await asyncio.to_thread(self._fetch_ghcr_token, task.url)
            if tok:
                headers["Authorization"] = f"Bearer {tok}"
        loop = asyncio.get_running_loop()
        request = urllib.request.Request(task.url, headers=headers)
        log_f12_net(f"HTTP GET {task.url}")

        def sync_download() -> DownloadResult:
            hasher = hashlib.sha256() if task.expected_sha256 else None
            try:
                with urllib.request.urlopen(
                    request, timeout=self.base_timeout
                ) as response, part_path.open("wb") as output:
                    # Set per-read timeout on the underlying socket
                    try:
                        sock = response.fp.raw._sock
                        if sock is not None:
                            sock.settimeout(_READ_TIMEOUT)
                    except AttributeError:
                        pass  # socket not accessible, continue without per-read timeout

                    total = int(response.headers.get("Content-Length", 0))
                    status_code = getattr(response, "status", 200)
                    log_f12_net(f"HTTP {status_code} for {task.component} (Content-Length: {total} bytes)")
                    downloaded = 0
                    start_time = time.monotonic()
                    last_cb_time = 0.0
                    last_cb_pct = -1

                    def report(d_bytes: int, t_bytes: int, is_final: bool = False):
                        nonlocal last_cb_time, last_cb_pct
                        if self.progress_cb is None:
                            return
                        now = time.monotonic()
                        pct = int(d_bytes * 100 / t_bytes) if t_bytes > 0 else 0
                        if not is_final:
                            # 0.15초 이내이면서 퍼센트 변화도 없으면 스킵
                            if (now - last_cb_time < 0.15) and (pct == last_cb_pct):
                                return
                        elapsed = now - start_time
                        speed_bps = d_bytes / elapsed if elapsed > 0 else 0.0
                        eta_sec = (t_bytes - d_bytes) / speed_bps if (speed_bps > 0 and t_bytes > d_bytes) else 0.0
                        last_cb_time = now
                        last_cb_pct = pct
                        if asyncio.iscoroutinefunction(self.progress_cb):
                            asyncio.run_coroutine_threadsafe(
                                self.progress_cb(task.component, d_bytes, t_bytes, speed_bps, eta_sec),
                                loop,
                            )
                        else:
                            self.progress_cb(task.component, d_bytes, t_bytes, speed_bps, eta_sec)

                    while True:
                        chunk = response.read(_CHUNK_SIZE)
                        if not chunk:
                            break
                        output.write(chunk)
                        downloaded += len(chunk)
                        if hasher is not None:
                            hasher.update(chunk)
                        report(downloaded, total)

                    report(downloaded, total, is_final=True)

                computed_sha256 = hasher.hexdigest() if hasher is not None else None
                if hasher is not None and computed_sha256 != task.expected_sha256:
                    log_f12_net(
                        f"SHA256 mismatch for {task.component}: got {computed_sha256}, expected {task.expected_sha256}",
                        is_error=True,
                    )
                    raise ValueError(
                        f"SHA256 mismatch: {computed_sha256} != {task.expected_sha256}"
                    )
                part_path.replace(task.dest)
                log_f12_net(
                    f"downloaded {task.component} -> {task.dest} "
                    f"({downloaded / (1024 * 1024):.1f} MB, sha256: {computed_sha256[:16] if computed_sha256 else 'none'}...)"
                )
                return DownloadResult(
                    task=task,
                    success=True,
                    bytes_downloaded=downloaded,
                    sha256=computed_sha256,
                )
            except BaseException as e:
                self._remove_part_file(task)
                log_f12_net(f"download stream error for {task.component}: {e}", is_error=True)
                raise

        return await asyncio.to_thread(sync_download)

    @staticmethod
    def _remove_part_file(task: DownloadTask) -> None:
        part_path = task.dest.with_suffix(task.dest.suffix + ".part")
        try:
            part_path.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass

```

## File: chzzktube\infra\provisioning\executor.py

```python
"""Executor — 프로비저닝 실행 (download → verify 단계 담당).

Planner가 생성한 플랜을 받아 다운로드, 추출/설치, 검증을 수행.
"""
import shutil
import sys
import tarfile
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

from chzzktube.core import raw_log
from chzzktube.core.log_emitter import emit_component
from chzzktube.core.log_event import LogEvent
from chzzktube.core.raw_log import log_f12_cli, log_f12_net
from chzzktube.infra.platform import astrip_macos_quarantine, strip_macos_quarantine
from chzzktube.infra.provisioning.downloader import DownloadTask, ParallelDownloader
from chzzktube.infra.provisioning.planner import ProvisionPlan
from chzzktube.infra.provisioning.verifier import Verifier


@dataclass
class ProvisionResult:
    component: str
    success: bool
    version: str | None = None
    error: str | None = None
    action: str = ""
    sha256: str = ""


_SCOPE_MAP = {"ytdlp": "YTDL", "ffmpeg": "FFMP", "node": "NODE", "bgutil": "BGUT", "pot": "POT"}

def _to_scope(comp: str) -> str:
    return _SCOPE_MAP.get(str(comp).lower(), str(comp).upper()[:5])


def _promote_extracted_binaries(temp_dir: str, target_dest: Path, component_name: str) -> Path:
    """아카이브 추출 산출물을 target_dest로 배치 (node 레이아웃 보존, ffmpeg 검증/호스트 폴백, bgutil 서버 전개)."""
    td_path = Path(temp_dir)
    target_dest.mkdir(parents=True, exist_ok=True)

    # 1. node: npm 실행에 필요한 lib/node_modules/npm 구조 전체 보존
    if component_name == "node":
        entries = [e for e in td_path.iterdir() if e.is_dir()]
        src_dir = entries[0] if len(entries) == 1 else td_path
        for item in src_dir.iterdir():
            dest_item = target_dest / item.name
            if dest_item.exists():
                if dest_item.is_dir():
                    shutil.rmtree(dest_item, ignore_errors=True)
                else:
                    dest_item.unlink()
            shutil.move(str(item), str(dest_item))
        if sys.platform != "win32":
            for b in ("node", "npm", "npx"):
                bp = target_dest / "bin" / b
                if bp.exists():
                    bp.chmod(0o755)
                    strip_macos_quarantine(str(bp))
        return target_dest

    # 2. bgutil 서버: 소스 트리 전개 + .version 기록
    if component_name in ("bgutil", "bgutil-ytdlp-pot-provider"):
        entries = [e for e in td_path.iterdir() if e.is_dir()]
        src_dir = entries[0] if len(entries) == 1 else td_path
        for item in src_dir.iterdir():
            dest_item = target_dest / item.name
            if dest_item.exists():
                if dest_item.is_dir():
                    shutil.rmtree(dest_item, ignore_errors=True)
                else:
                    dest_item.unlink()
            shutil.move(str(item), str(dest_item))
        return target_dest

    # 3. ffmpeg: ffmpeg/ffprobe 바이너리 색출 및 배치
    target_bin_dir = target_dest / "bin"
    target_bin_dir.mkdir(parents=True, exist_ok=True)

    # macOS: 아카이브 내 미서명 바이너리의 AMFI 커널 트랩 방지를 위해 호스트 ffmpeg 우선 승격
    if sys.platform == "darwin":
        for host_bin in (Path("/opt/homebrew/bin/ffmpeg"), Path("/usr/local/bin/ffmpeg")):
            if host_bin.is_file():
                dest_ffmpeg = target_bin_dir / "ffmpeg"
                shutil.copy2(host_bin, dest_ffmpeg)
                dest_ffmpeg.chmod(0o755)
                strip_macos_quarantine(str(dest_ffmpeg))
                host_probe = host_bin.parent / "ffprobe"
                if host_probe.is_file():
                    dest_probe = target_bin_dir / "ffprobe"
                    shutil.copy2(host_probe, dest_probe)
                    dest_probe.chmod(0o755)
                    strip_macos_quarantine(str(dest_probe))
                return target_dest

    targets = ("ffmpeg", "ffprobe")
    found_bins = {}

    for p in td_path.rglob("*"):
        if p.is_file() and p.name.lower() in [t + (".exe" if sys.platform == "win32" else "") for t in targets]:
            stem = p.name.replace(".exe", "").lower()
            if stem not in found_bins:
                found_bins[stem] = p

    for stem, src_path in found_bins.items():
        dest_file = target_bin_dir / src_path.name
        if dest_file.exists():
            dest_file.unlink()
        shutil.copy2(src_path, dest_file)
        if sys.platform != "win32":
            dest_file.chmod(dest_file.stat().st_mode | 0o755)
            strip_macos_quarantine(str(dest_file))

    # Windows: DLL 동반 수급 — 아카이브 내 동반 DLL을 target_bin_dir로 복사
    if sys.platform == "win32":
        for dll_file in td_path.rglob("*.dll"):
            dest_dll = target_bin_dir / dll_file.name
            if not dest_dll.exists():
                shutil.copy2(dll_file, dest_dll)
                log_f12_net(f"copied companion DLL: {dll_file.name} -> {dest_dll}")

    return target_dest


class Executor:
    """download → verify 단계 담당."""

    def __init__(self, base_dir: Path, log_func=None):
        self.base_dir = base_dir
        self.log = log_func
        self._active_progress: dict[str, dict] = {}
        self._downloader = ParallelDownloader(progress_cb=self._on_progress)

    def _on_progress(self, component: str, downloaded: int, total: int, speed_bps: float = 0.0, eta_sec: float = 0.0):
        """다운로드 진행률 하트비트 — TUI: 컴포넌트별 개별 갱신형 라인, F12: 개별 누적."""
        if total <= 0:
            return

        pct = int(downloaded / total * 100)
        downloaded_mb = downloaded / (1024 * 1024)
        total_mb = total / (1024 * 1024)

        speed_str = self._format_speed(speed_bps)
        nm_str = f"{downloaded_mb:.1f}/{total_mb:.1f} MB"

        # 개별 진행 저장 (100% 완료 및 추출/실패 후에도 bar, pct, speed, n/m 유지)
        self._active_progress[component] = {
            "pct": pct,
            "speed": speed_str,
            "nm": nm_str,
            "downloaded_mb": downloaded_mb,
            "total_mb": total_mb,
        }

        # 다운로드 중에는 msg는 공백 (bar, pct, speed, n/m만 배치)
        line = self._fmt_progress(pct, speed_str, nm_str, msg="")

        event = emit_component(
            "DEPS", "RUN", _to_scope(component),
            line,
            is_status=True,
            is_error=False,
        )
        event.component_id = f"deps_{component}"
        event.is_progress = True
        if not self._emit_via_log(event):
            raw_log.raw(
                "provisioning", event, to_tui=True,
                component_id=event.component_id, is_progress=True,
            )

    def _emit(self, stage, status, scope, msg, is_status=False, is_error=False,
              component_id: str | None = None, is_progress: bool = False, to_tui: bool | None = None):
        """raw_log 버스 단일 경유."""
        evt = emit_component(stage, status, scope, msg, is_status=is_status, is_error=is_error)
        evt.component_id = component_id
        evt.is_progress = is_progress
        if to_tui is None:
            to_tui = is_status or is_progress or is_error or (status in ("OK", "DONE", "FAIL", "READY", "WARN"))
        raw_log.raw(
            "provisioning", evt, to_tui=to_tui, is_error=is_error,
            component_id=component_id, is_progress=is_progress,
        )

    def _emit_via_log(self, event: LogEvent) -> bool:
        """Progress event를 기존 log_func 계약으로 한 번만 중계한다."""
        if self.log is None:
            return False
        try:
            self.log(
                event,
                is_status=event.is_status,
                is_error=event.is_error,
                component_id=event.component_id,
                is_progress=event.is_progress,
            )
        except TypeError:
            # 기존 동기 브리지처럼 LogEvent 하나만 받는 콜백과 호환
            self.log(event)
        return True

    @staticmethod
    def _format_speed(bps: float) -> str:
        """GB/s 승격으로 자릿수 폭주를 원천 차단"""
        if bps >= 1024 * 1024 * 1024:
            return f"{bps / (1024 * 1024 * 1024):.1f} GB/s"
        if bps >= 1024 * 1024:
            return f"{bps / (1024 * 1024):.1f} MB/s"
        if bps >= 1024:
            return f"{bps / 1024:.1f} KB/s"
        if bps > 0:
            return f"{bps:.0f} B/s"
        return ""

    @staticmethod
    def _fmt_progress(pct: int, speed: str = "", nm: str = "", msg: str = "") -> str:
        """TUI 규격: bar, pct, speed, n/m, msg 순으로 배치 (ETA 삭제)."""
        pct_val = min(max(pct, 0), 100)
        bar = "█" * (pct_val // 10) + "░" * (10 - pct_val // 10)
        pct_str = f"{pct_val:3d}%"
        speed_padded = f"{speed:>10}" if speed else " " * 10

        line = f"[{bar}] {pct_str} · {speed_padded}"
        if nm:
            line += f" · {nm}"
        if msg:
            line += f" · {msg}"
        return line

    async def provision(self, plans: list[ProvisionPlan]) -> list[ProvisionResult]:
        """플랜 실행: 다운로드 → 추출/설치 → 검증."""
        if not plans:
            return []

        self._plan_versions = {plan.component: plan.version for plan in plans}

        tasks = []
        for plan in plans:
            dest = self.base_dir / "downloads" / plan.component
            dest.parent.mkdir(parents=True, exist_ok=True)
            tasks.append(DownloadTask(
                url=plan.download_url,
                dest=dest,
                component=plan.component,
            ))
            log_f12_net(f"queue download: {plan.component} -> {plan.download_url}")

        dl_results = await self._downloader.download_all(tasks)

        final_results = []
        for plan in plans:
            comp_id = f"deps_{plan.component}"
            scope = _to_scope(plan.component)
            dl_result = next((r for r in dl_results if r.task.component == plan.component), None)

            prog = self._active_progress.get(plan.component, {})
            pct = prog.get("pct", 100)
            speed = prog.get("speed", "")
            nm = prog.get("nm", "")

            if not dl_result or not dl_result.success:
                error_msg = dl_result.error if dl_result else "download task vanished"
                fail_line = self._fmt_progress(pct, speed, nm, f"download failed: {error_msg}")
                self._emit("DEPS", "FAIL", scope, fail_line, component_id=comp_id, is_progress=False, is_error=True)
                log_f12_net(f"download failed for {plan.component}: {error_msg}", is_error=True)
                final_results.append(ProvisionResult(
                    plan.component, False, error=error_msg, action="fail"
                ))
                continue

            # 1. 추출 단계: bar, pct, speed, n/m 유지 + msg='extracting...'
            extract_line = self._fmt_progress(100, speed, nm, "extracting...")
            self._emit("DEPS", "RUN", scope, extract_line, component_id=comp_id, is_progress=True, is_status=True)
            log_f12_net(f"extracting {plan.component} ({plan.archive_type}) -> {plan.install_path}")

            installed_path = await self._extract_and_install(plan, dl_result.task.dest)

            if isinstance(installed_path, str):  # str means error message
                fail_line = self._fmt_progress(100, speed, nm, f"install failed: {installed_path}")
                self._emit("DEPS", "FAIL", scope, fail_line, component_id=comp_id, is_progress=False, is_error=True)
                log_f12_net(f"install failed for {plan.component}: {installed_path}", is_error=True)
                final_results.append(ProvisionResult(
                    plan.component, False, error=f"install failed: {installed_path}", action="fail"
                ))
                continue

            # 2. 검증 단계
            if plan.spec.verify_cmd:
                v_res = Verifier.verify(plan.spec, installed_path)
                cmd_str = f"{installed_path} {' '.join(plan.spec.verify_cmd[1:])}"
                log_f12_cli(cmd_str, v_res.version if v_res.success else v_res.error, is_error=not v_res.success)
                if not v_res.success:
                    fail_line = self._fmt_progress(100, speed, nm, f"verification failed: {v_res.error}")
                    self._emit("DEPS", "FAIL", scope, fail_line, component_id=comp_id, is_progress=False, is_error=True)
                    log_f12_net(f"verification failed for {plan.component}: {v_res.error}", is_error=True)
                    final_results.append(ProvisionResult(
                        plan.component, False, error=f"verification failed: {v_res.error}", action="fail"
                    ))
                    continue
                log_f12_net(f"verified {plan.component} binary -> {v_res.version or plan.version}")

            # 3. 마감 확정 (Commit): bar, pct, speed, n/m 유지 + msg='{component} installed' / '{component} updated'
            action_desc = "updated" if plan.is_update else "installed"
            status_text = f"{plan.component} {action_desc}"
            done_line = self._fmt_progress(100, speed, nm, status_text)
            self._emit("DEPS", "OK", scope, done_line, component_id=comp_id, is_progress=False, is_status=False)
            log_f12_net(f"provision complete: {plan.component} ({action_desc}) -> {plan.version}")
            final_results.append(ProvisionResult(
                plan.component, True, version=plan.version, sha256=plan.expected_sha256 or "", action="update" if plan.is_update else "install"
            ))

        return final_results

    async def _extract_and_install(self, plan: ProvisionPlan, archive: Path) -> Path | str:
        """아카이브 추출/설치 수행."""
        try:
            if plan.archive_type == "whl":
                from chzzktube.infra.updater import _extract_pylib_whl
                overlay_root = self.base_dir / ".pylib"
                prefix = plan.component + "-" if plan.component != "yt-dlp" else "yt_dlp-"
                with zipfile.ZipFile(archive) as z:
                    z.extractall(str(overlay_root))
                _extract_pylib_whl(str(archive), str(overlay_root), prefix)
                return overlay_root

            elif plan.archive_type in ("zip", "server"):
                with tempfile.TemporaryDirectory(prefix=f"cz_{plan.component}_") as td:
                    with zipfile.ZipFile(archive) as z:
                        z.extractall(td)
                    dest = plan.install_path
                    promoted = _promote_extracted_binaries(td, dest, plan.component)
                    if plan.archive_type == "server" and plan.version:
                        try:
                            (dest / ".version").write_text(str(plan.version), encoding="utf-8")
                            if (dest / "server").is_dir():
                                (dest / "server" / ".version").write_text(str(plan.version), encoding="utf-8")
                        except OSError as e:
                            # .version 마커 기록 실패는 설치를 막지 않는다 (F12 진단 기록만)
                            log_f12_net(
                                "failed to write .version marker for "
                                f"{plan.component}: {type(e).__name__}: {e}",
                                is_error=True,
                            )
                    return promoted

            elif plan.archive_type == "tar.gz":
                with tempfile.TemporaryDirectory(prefix=f"cz_{plan.component}_") as td:
                    with tarfile.open(archive, "r:gz") as tar:
                        tar.extractall(td)
                    dest = plan.install_path
                    return _promote_extracted_binaries(td, dest, plan.component)

            elif plan.archive_type == "tar.xz":
                with tempfile.TemporaryDirectory(prefix=f"cz_{plan.component}_") as td:
                    with tarfile.open(archive, "r:xz") as tar:
                        tar.extractall(td, filter="data")
                    dest = plan.install_path
                    return _promote_extracted_binaries(td, dest, plan.component)

            elif plan.archive_type == "binary":
                dest = plan.install_path
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(archive, dest)
                if sys.platform != "win32":
                    dest.chmod(0o755)
                    # async 컨텍스트 — xattr 프로세스는 worker thread에서 실행 (블로킹 금지)
                    await astrip_macos_quarantine(str(dest))
                return dest

            return f"unknown archive type: {plan.archive_type}"

        except PermissionError as e:
            return f"PermissionError: file locked or access denied ({e}) — close conflicting programs and restart app"
        except FileNotFoundError as e:
            return f"FileNotFoundError: required file missing ({e})"
        except OSError as e:
            if getattr(e, "winerror", None) == 32:
                return "file in use by another process (WinError 32) — close background processes and restart app"
            return f"{type(e).__name__}: {e}"

```

## File: chzzktube\infra\provisioning\manager.py

```python
"""ProvisioningManager — 외부 라이브러리 수급/검증/커밋 단일 오케스트레이터.

로그 버스 정책 (HANDOVER §5-21):
- 모든 앱 동작은 raw_log.raw() → LogEvent 단일 경로
- Qt 시그널은 결과/제어/브리지에만 사용 (log_full/log_concise 시그널 금지)
- 발행자가 라벨과 to_tui 결정
- history ⊇ full ⊇ TUI (큐 2048, 버퍼 4096 유한)

리팩토링(v3.11.0): Planner/Executor/Committer로 책임 분리
- Planner: resolve 단계 (최신 버전/URL/sha256 조회 → 플랜 생성)
- Executor: provision 단계 (다운로드 → 추출/설치 → 검증)
- Committer: commit 단계 (manifest 저장 + overlay/PATH 갱신)
"""
from pathlib import Path

from chzzktube.core import config
import chzzktube.core.raw_log as raw_log
from chzzktube.core.log_emitter import emit_component
from chzzktube.infra.provisioning.planner import Planner, ProvisionPlan
from chzzktube.infra.provisioning.executor import Executor, ProvisionResult
from chzzktube.infra.provisioning.committer import Committer


class ProvisioningManager:
    """단일 파사드 — Planner/Executor/Committer를 조합하여 resolve → download → verify → commit 수행."""

    def __init__(self, log_func=None):
        self.base_dir = Path(config.writable_base())
        self.log = log_func
        self.planner = Planner(self.base_dir, log_func)
        self.executor = Executor(self.base_dir, log_func)
        self.committer = Committer(self.base_dir, log_func)

    async def resolve(self, stale_only: bool = False, channel: str = "stable") -> list[ProvisionPlan]:
        """모든 구성요소에 대해 최신 버전 확인 + 플랜 생성 (Planner 위임)."""
        return await self.planner.resolve(stale_only=stale_only, channel=channel)

    async def provision(self, plans: list[ProvisionPlan]) -> list[ProvisionResult]:
        """플랜 실행: 다운로드 → 추출/설치 → 검증 (Executor 위임)."""
        return await self.executor.provision(plans)

    async def commit(self, plans: list[ProvisionPlan], results: list[ProvisionResult]) -> None:
        """manifest 갱신 + 오버레이/환경변수 리로드 (Committer 위임)."""
        self.committer.commit(plans, results)

    async def ensure_all(self, stale_only: bool = True, channel: str = "stable") -> list[ProvisionResult]:
        """전체 프로비저닝: resolve → download → verify → commit."""
        plans = await self.resolve(stale_only=stale_only, channel=channel)
        if not plans:
            self._emit(
                "DEPS", "SKIP", "DEPS", "all components up-to-date",
                component_id="deps_SUMMARY", is_progress=False,
            )
            return []

        update_comps = [p.component for p in plans if p.is_update]
        install_comps = [p.component for p in plans if not p.is_update]
        if update_comps and install_comps:
            action_summary = f"updating {', '.join(update_comps)}, installing {', '.join(install_comps)}"
        elif update_comps:
            action_summary = f"updating {', '.join(update_comps)}"
        else:
            action_summary = f"installing {', '.join(install_comps)}"

        self._emit(
            "DEPS", "RUN", "DEPS", f"provisioning {len(plans)} components ({action_summary})",
            component_id="deps_SUMMARY", is_progress=False,
        )

        results = await self.provision(plans)
        await self.commit(plans, results)

        ok_count = sum(1 for r in results if r.success)
        fail_count = len(results) - ok_count
        if fail_count == 0:
            self._emit(
                "DEPS", "DONE", "DEPS", f"provisioned {ok_count} components ready",
                component_id="deps_SUMMARY", is_progress=False,
            )
        else:
            fail_names = [r.component for r in results if not r.success]
            self._emit(
                "DEPS", "FAIL", "MAIN",
                f"deps fail ({', '.join(fail_names)}) → check network/F12 logs and restart app",
                component_id="deps_SUMMARY", is_progress=False, is_error=True,
            )

        return results

    def _emit(self, stage, status, scope, msg, is_status=False, is_error=False,
              component_id: str | None = None, is_progress: bool = False, to_tui: bool | None = None):
        """raw_log 버스 단일 경유 — 발행자만 raw_log.raw() 호출 (이중 적재 방지)."""
        evt = emit_component(stage, status, scope, msg, is_status=is_status, is_error=is_error)
        evt.component_id = component_id
        evt.is_progress = is_progress
        if to_tui is None:
            to_tui = is_status or is_progress or is_error or (status in ("OK", "DONE", "FAIL", "READY", "WARN", "SKIP"))
        raw_log.raw(
            "provisioning", evt, to_tui=to_tui, is_error=is_error,
            component_id=component_id, is_progress=is_progress,
        )

    async def _on_progress(self, component: str, downloaded: int, total: int, speed_bps: float = 0.0, eta_sec: float = 0.0):
        """Executor의 진행률 콜백 위임 — 테스트/브리지 호환용."""
        self.executor._on_progress(component, downloaded, total, speed_bps, eta_sec)

```

## File: chzzktube\infra\provisioning\manifest.py

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
            except Exception as e:
                import chzzktube.core.raw_log as raw_log
                raw_log.raw("DEPS", f"manifest load error: {type(e).__name__}: {e}", is_error=True, to_tui=False)
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

    def is_stale(self, name: str, latest_version: str, base_dir: Optional[Path] = None) -> bool:
        """manifest 버전 vs 최신 버전 비교 및 디스크 실존 확인."""
        rec = self.components.get(name)
        if not rec:
            return True
        if rec.version != latest_version:
            return True
        if base_dir is not None and rec.install_path:
            full_path = base_dir / rec.install_path
            if not full_path.exists():
                return True
        return False

    def get_record(self, name: str) -> Optional[ComponentRecord]:
        return self.components.get(name)

    def update_component(self, record: ComponentRecord) -> None:
        self.components[record.name] = record

    def remove_component(self, name: str) -> None:
        self.components.pop(name, None)
```

## File: chzzktube\infra\provisioning\planner.py

```python
"""Planner — 프로비저닝 플랜 생성 (resolve 단계만 담당).

ProvisioningManager에서 resolve 로직을 분리한 순수 플래너.
미러 체인에서 최신 버전/URL/sha256 조회 → ProvisionPlan 리스트 생성.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import asyncio
import json
import sys
import time
import urllib.error
import urllib.request

from chzzktube.core import config
from chzzktube.infra.provisioning.resolver import (
    ComponentSpec, ComponentType, MIRROR_REGISTRY, filter_assets,
)
from chzzktube.infra.provisioning.manifest import ProvisionManifest
import chzzktube.core.raw_log as raw_log
from chzzktube.core.raw_log import log_f12_net
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


class Planner:
    """resolve 단계만 담당 — 플랜 생성."""

    def __init__(self, base_dir: Path, log_func=None):
        self.base_dir = base_dir
        self.manifest = ProvisionManifest.load(base_dir)
        self.log = log_func
        self.overlay_root = Path(config.pylib_overlay_path())

    def _emit(self, stage, status, scope, msg, is_status=False, is_error=False,
              component_id: str | None = None, is_progress: bool = False, to_tui: bool | None = None):
        """raw_log 버스 단일 경유."""
        evt = emit_component(stage, status, scope, msg, is_status=is_status, is_error=is_error)
        evt.component_id = component_id
        evt.is_progress = is_progress
        if to_tui is None:
            to_tui = is_status or is_progress or is_error or (status in ("OK", "DONE", "FAIL", "READY", "WARN"))
        raw_log.raw(
            "provisioning", evt, to_tui=to_tui, is_error=is_error,
            component_id=component_id, is_progress=is_progress,
        )

    async def _fetch_json(self, url: str, *, headers: Optional[dict[str, str]] = None):
        """Worker thread에서 동기 urllib JSON 요청을 수행한다."""
        return await asyncio.to_thread(self._fetch_json_sync, url, headers)

    @staticmethod
    def _fetch_json_sync(
        url: str, headers: Optional[dict[str, str]] = None
    ) -> Optional[dict | list]:
        log_f12_net(f"HTTP GET {url}")
        request = urllib.request.Request(url, headers=headers or {})
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                return json.loads(response.read().decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, urllib.error.HTTPError) as e:
            log_f12_net(f"HTTP GET failed ({url}): {e}", is_error=True)
            return None

    async def _fetch_text(self, url: str) -> Optional[str]:
        """Worker thread에서 동기 urllib 텍스트 요청을 수행한다."""
        return await asyncio.to_thread(self._fetch_text_sync, url)

    @staticmethod
    def _fetch_text_sync(url: str) -> Optional[str]:
        log_f12_net(f"HTTP GET {url}")
        request = urllib.request.Request(url, headers={"User-Agent": "ChzzkTube-Provisioner/1.0"})
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                return response.read().decode("utf-8")
        except (OSError, UnicodeDecodeError, urllib.error.HTTPError) as e:
            log_f12_net(f"HTTP GET failed ({url}): {e}", is_error=True)
            return None

    async def _fetch_latest(self, spec: ComponentSpec):
        """미러 체인에서 최신 버전/URL/sha256/미러명/arch타입 조회."""
        for mirror in sorted(spec.mirrors, key=lambda m: m.priority):
            try:
                # macOS에서 BtbN mirror는 darwin 바이너리가 없으므로 skip
                if sys.platform == "darwin" and mirror.name == "github_btb":
                    continue

                if mirror.name == "pypi":
                    result = await self._fetch_from_pypi(spec, mirror)
                elif mirror.name == "homebrew":
                    result = await self._fetch_from_homebrew(spec, mirror)
                elif "github" in mirror.name:
                    result = await self._fetch_from_github(spec, mirror)
                elif mirror.name == "nodejs.org":
                    result = await self._fetch_from_nodejs(spec, mirror)
                else:
                    result = None

                if result and result[0] and result[1]:
                    log_f12_net(f"resolved {spec.name}: v{result[0]} via {result[3]} -> {result[1]}")
                    return result
            except Exception as e:
                import chzzktube.core.raw_log as raw_log
                raw_log.raw("DEPS", f"_fetch_latest mirror {mirror.name} error: {type(e).__name__}: {e}", is_error=True, to_tui=False)
                log_f12_net(f"mirror {mirror.name} query error for {spec.name}: {e}", is_error=True)
                pass
        return None, None, None, None, None

    async def _fetch_from_homebrew(self, spec, mirror):
        """Homebrew formulae API에서 최신 버전 + bottle URL 조회 (macOS 전용)."""
        import platform as _platform
        if sys.platform != "darwin":
            return None, None, None, None, None

        data = await self._fetch_json(mirror.url_template)
        if not data:
            return None, None, None, None, None

        version = data.get("versions", {}).get("stable")
        if not version:
            return None, None, None, None, None

        files = data.get("bottle", {}).get("stable", {}).get("files", {})
        arch = _platform.machine().lower()
        prefix = "arm64_" if arch in ("arm64", "aarch64") else "x86_64_"
        candidates = [k for k in files if k.startswith(prefix) and "linux" not in k]

        try:
            darwin_major = int(_platform.release().split(".")[0])
        except Exception:
            darwin_major = 24

        _BUILD_ORDERS = (
            ("sequoia", 24),
            ("sonoma", 23),
            ("ventura", 22),
            ("monterey", 21),
            ("big_sur", 20),
            ("catalina", 19),
        )
        chosen_key = None
        for name, bnum in _BUILD_ORDERS:
            k = prefix + name
            if k in files and bnum <= darwin_major:
                chosen_key = k
                break
        if not chosen_key and candidates:
            chosen_key = candidates[0]
        if not chosen_key:
            return None, None, None, None, None

        entry = files[chosen_key]
        url = entry.get("url")
        sha256 = entry.get("sha256")
        return version, url, sha256, mirror.name, "tar.gz"

    @staticmethod
    def _archive_type_from(filename: str, spec: ComponentSpec) -> str:
        """아카이브 파일명 확장자로 해제 방법 판정 (하드코딩 금지).

        bgutil 서버는 npm 소스 구조이므로 항상 server로 간주하고(해제 후 npm 빌드),
        그 외는 .zip / .tar.gz / .tar.xz 확장자를 그대로 반환한다.
        """
        if spec.name == "bgutil-ytdlp-pot-provider":
            return "server"

        fn = filename.lower()
        if fn.endswith(".whl"):
            return "whl"
        if fn.endswith(".tar.xz"):
            return "tar.xz"
        if fn.endswith(".tar.gz"):
            return "tar.gz"
        if fn.endswith(".zip"):
            return "zip"
        return "binary"

    async def _fetch_from_pypi(self, spec, mirror):
        """PyPI JSON API에서 최신 버전 + whl URL."""
        data = await self._fetch_json(
            mirror.url_template.format(pkg=spec.name)
        )
        if not data:
            return None, None, None, None, None
        version = data.get("info", {}).get("version")
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
        """GitHub Releases API에서 최신 버전 + asset URL."""
        data = await self._fetch_json(mirror.url_template)
        if not data:
            return None, None, None, None, None
        version = (data.get("tag_name") or "").lstrip("v")
        if not version:
            return None, None, None, None, None

        if getattr(spec, "type", None) == ComponentType.SERVER:
            tag = data.get("tag_name") or version
            url = data.get("zipball_url") or f"https://github.com/Brainicism/bgutil-ytdlp-pot-provider/archive/refs/tags/{tag}.zip"
            return version, url, None, mirror.name, "server"

        assets = data.get("assets") or []
        if spec.name in ("yt-dlp", "ytdlp"):
            from chzzktube.infra.yt_dlp_binary import _platform_asset_name
            target_asset_name = _platform_asset_name(version)
            for a in assets:
                if a.get("name") == target_asset_name:
                    return version, a.get("browser_download_url"), None, mirror.name, "binary"

        candidates = filter_assets(assets, spec)
        if not candidates:
            return None, None, None, None, None

        asset = candidates[0]
        archive_type = self._archive_type_from(asset["name"], spec)
        return version, asset["browser_download_url"], None, mirror.name, archive_type

    async def _fetch_from_nodejs(self, spec, mirror):
        """nodejs.org dist index에서 latest LTS + SHA256 체크섬 조회."""
        data = await self._fetch_json(mirror.url_template)
        if not data:
            return None, None, None, None, None
        entries = data
        ver = next(
            (e.get("version") for e in entries if str(e.get("version", "")).startswith("v22.")),
            None,
        )
        if not ver:
            ver = entries[0]["version"]

        from chzzktube.infra.node_provider import _platform_node_url
        url = _platform_node_url(ver)
        archive_type = "tar.gz" if "darwin" in url else "zip"

        # SHA256 체크섬 조회 (SHASUMS256.txt에서 해당 파일 해시 추출)
        sha256 = await self._fetch_nodejs_sha256(ver, url)
        return ver, url, sha256, "nodejs.org", archive_type

    async def _fetch_nodejs_sha256(self, version: str, download_url: str) -> Optional[str]:
        """nodejs.org SHASUMS256.txt에서 특정 버전/플랫폼 파일의 SHA256 조회."""
        # SHASUMS256.txt URL 구성
        shasums_url = f"https://nodejs.org/dist/{version}/SHASUMS256.txt"
        try:
            shasums_text = await self._fetch_text(shasums_url)
            if not shasums_text:
                return None
            # 파일명 추출 (URL에서)
            filename = download_url.split("/")[-1]
            # SHASUMS256.txt에서 해당 파일명 찾기
            for line in shasums_text.splitlines():
                line = line.strip()
                if not line:
                    continue
                # 형식: "sha256_hash  filename"
                parts = line.split()
                if len(parts) >= 2 and parts[1] == filename:
                    return parts[0]
        except Exception as e:
            import chzzktube.core.raw_log as raw_log
            raw_log.raw("DEPS", f"_fetch_nodejs_sha256 error: {type(e).__name__}: {e}", is_error=True, to_tui=False)
        return None

    async def resolve(self, stale_only: bool = False, channel: str = "stable") -> list[ProvisionPlan]:
        """모든 구성요소에 대해 최신 버전 확인 + 플랜 생성."""
        self.manifest.last_check = time.time()
        plans = []

        for name, spec in MIRROR_REGISTRY.items():
            if spec.channel != channel:
                continue

            latest_ver, latest_url, sha256, mirror_name, archive_type = await self._fetch_latest(spec)
            if not latest_ver or not latest_url:
                self._emit(
                    "DEPS", "WARN", name.upper(), "no mirror resolved",
                    component_id=f"deps_{name}", is_progress=False,
                )
                continue

            if stale_only and not self.manifest.is_stale(name, latest_ver, base_dir=self.base_dir):
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
```

## File: chzzktube\infra\provisioning\resolver.py

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
    PYTHON_PKG = "python_pkg"      # yt-dlp → .pylib (whl)
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
    "ytdlp": ComponentSpec(
        name="yt-dlp",
        type=ComponentType.BINARY,
        version_strategy="latest_stable",
        mirrors=(
            Mirror("github_ytdl", "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest", priority=0),
        ),
        verify_cmd=("yt-dlp", "--version"),
        install_rel_path="bin/yt-dlp.exe" if sys.platform == "win32" else "bin/yt-dlp",
        asset_filters=("yt-dlp",),
    ),
    "ffmpeg": ComponentSpec(
        name="ffmpeg",
        type=ComponentType.BINARY,
        version_strategy="latest_stable",
        mirrors=(
            # macOS는 Homebrew formulae bottle(SHA-256 + 실행 검증) 또는 호스트 부트스트랩,
            # Windows/Linux는 BtbN 정적 GPL 아카이브
            Mirror("github_btb", "https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/latest", priority=0),
            Mirror("homebrew", "https://formulae.brew.sh/api/formula/ffmpeg.json", priority=1),
        ),
        verify_cmd=("ffmpeg", "-version"),
        install_rel_path="ffmpeg",
        asset_filters=("ffmpeg", "gpl"),
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
        install_rel_path="node",
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
    except Exception as e:
        import chzzktube.core.raw_log as raw_log
        raw_log.raw("DEPS", f"get_platform_asset_filters error: {type(e).__name__}: {e}", is_error=True, to_tui=False)

    if platform == "darwin":
        # 'arm64' 단독 키워드는 winarm64, linuxarm64에도 매칭되므로 배제
        return ("macos", "darwin", "apple", "osx")
    elif platform == "win32":
        if machine in ("arm64", "aarch64"):
            return ("winarm64", "win-arm64", "windows-arm64")
        # 'x64' 단독 키워드는 linux64에도 매칭되므로 win 접두가 있는 키워드만 사용
        return ("win64", "windows", "win-x64", "win_x64")
    else:
        if machine in ("arm64", "aarch64"):
            return ("linuxarm64", "linux-arm64", "aarch64")
        return ("linux64", "linux-x64", "linux_x64", "linux")


# [stdlib-only] 표준 라이브러리로 해제 불가능한 아카이브 — 수급 후보에서 배제.
# py7zr 등 외부 의존성을 수급 계층(L0)에 들이지 않기 위한 명시적 경계.
# .tar.xz/.tar.gz는 tarfile로 해제 가능하므로 배제 대상이 아니다.
ARCHIVE_UNSUPPORTED_EXT = (".7z", ".rar", ".tar.zst", ".zst")
# 선호 순위: 앞일수록 우선. .zip/.tar.xz 최우선, 확장자 없음(원시 바이너리) 차선.
ARCHIVE_PREFERRED_EXT = (".zip", ".tar.xz", ".tar.gz", "")


def filter_assets(assets: list[dict], spec: ComponentSpec) -> list[dict]:
    """플랫폼·스펙 필터 + 아카이브 확장자 선호 정렬로 asset 선별."""
    platform_filters = get_platform_asset_filters()
    spec_filters = spec.asset_filters
    cur_platform = sys.platform

    candidates = []
    for asset in assets:
        name = asset.get("name", "").lower()

        # SERVER 타입은 크로스플랫폼 순수 JS/TS이므로 플랫폼 필터 적용 생략
        if getattr(spec, "type", None) != ComponentType.SERVER:
            # 타 OS 키워드 명시적 차단 (크로스 플랫폼 유출 방지)
            if cur_platform == "win32" and any(p in name for p in ("linux", "darwin", "macos", "osx")):
                continue
            if cur_platform == "darwin" and any(p in name for p in ("windows", "win32", "win64", "win-", "linux")):
                continue
            if cur_platform.startswith("linux") and any(p in name for p in ("windows", "win32", "win64", "win-", "darwin", "macos", "osx")):
                continue

            if platform_filters and not any(p in name for p in platform_filters):
                continue

        if spec_filters and not all(s in name for s in spec_filters):
            continue

        # 제외 키워드: shared(동적 라이브러리 미포함 바이너리 방지), lgpl(GPL 정적 빌드 선호)
        if any(x in name for x in ("debug", "symbols", "pdb", ".sig", ".asc", "shared", "lgpl")):
            continue
        if any(name.endswith(ext) for ext in ARCHIVE_UNSUPPORTED_EXT):
            continue

        rank = next(
            (i for i, ext in enumerate(ARCHIVE_PREFERRED_EXT) if name.endswith(ext)),
            len(ARCHIVE_PREFERRED_EXT),
        )
        candidates.append((rank, asset))

    candidates.sort(key=lambda pair: pair[0])
    return [asset for _, asset in candidates]

```

## File: chzzktube\infra\provisioning\verifier.py

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

            # 실행 테스트 (바이너리 경로를 PATH 및 cwd에 주입하여 companion DLL 탐색 보장)
            env = os.environ.copy()
            bin_dir = str(binary_path.parent)
            env["PATH"] = bin_dir + os.pathsep + env.get("PATH", "")

            result = subprocess.run(
                [str(binary_path), *spec.verify_cmd[1:]],
                capture_output=True, text=True, timeout=15,
                cwd=bin_dir,
                env=env,
                encoding="utf-8",
                errors="replace",
                **spawn_kwargs()
            )

            if result.returncode != 0:
                err_detail = (result.stderr or result.stdout or "").strip()
                if result.returncode in (3221225781, -1073741515, 0xC0000135):
                    err_msg = f"exit code {result.returncode} (STATUS_DLL_NOT_FOUND: required DLL missing): {err_detail[:300]}"
                else:
                    err_msg = f"exit code {result.returncode}: {err_detail[:300]}"
                return VerifyResult(
                    spec.name, False,
                    error=err_msg,
                    installed_path=binary_path
                )

            # 버전 추출
            version_line = ""
            stdout_text = result.stdout or ""
            if spec.name == "ffmpeg":
                import re
                m = re.search(r"ffmpeg version\s+([^\s,]+)", stdout_text)
                if m:
                    version_line = m.group(1)
            if not version_line:
                version_line = stdout_text.splitlines()[0] if stdout_text else ""
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
            return VerifyResult(spec.name, True, version=version, installed_path=server_dir)

        except Exception as e:
            return VerifyResult(spec.name, False, error=str(e), installed_path=server_dir)

    @classmethod
    def verify(cls, spec: ComponentSpec, install_path: Path) -> VerifyResult:
        """스펙 타입에 따라 적절한 검증 메서드 디스패치."""
        if spec.type == ComponentType.PYTHON_PKG:
            return cls.verify_python_pkg(spec, install_path)

        elif spec.type == ComponentType.BINARY:
            # [지능형 리졸버] 단일 수식의 환상을 버리고 실측 다중 후보를 검증
            binary_path = install_path

            if install_path.is_dir():
                target_name = spec.name + (".exe" if sys.platform == "win32" else "")

                # 1. 우선순위 후보군 구성 (승격된 bin/ 우선, 루트 폴백, 상대경로 조합)
                candidates = [
                    install_path / "bin" / target_name,
                    install_path / target_name,
                ]
                if spec.install_rel_path:
                    candidates.append(install_path.parent / spec.install_rel_path)
                    candidates.append(install_path / spec.install_rel_path)

                # 존재하는 첫 번째 정규 파일 채택
                found = None
                for cand in candidates:
                    if cand.is_file():
                        found = cand
                        break

                # 2. 최후의 보루: 디렉터리 내부 재귀 탐색 (Homebrew Bottle 심층 격리 대응)
                if not found:
                    for p in install_path.rglob(target_name):
                        if p.is_file():
                            found = p
                            break

                binary_path = found if found else (install_path / "bin" / target_name)

            return cls.verify_binary(spec, binary_path)

        elif spec.type == ComponentType.SERVER:
            return cls.verify_bgutil(spec, install_path)
        else:
            return VerifyResult(spec.name, False, error=f"unknown component type: {spec.type}")
```

## File: chzzktube\pipeline\__init__.py

```python

```

## File: chzzktube\pipeline\classifier.py

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

## File: chzzktube\pipeline\dl_context.py

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

## File: chzzktube\pipeline\finalizer.py

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

## File: chzzktube\pipeline\live_recorder.py

```python
##### live_recorder.py - 라이브 녹화 파이프라인 (yt-dlp + ffmpeg)
"""유튜브·치지직 라이브를 ffmpeg 자식 프로세스로 녹화한다.

- yt-dlp로 포맷 URL만 추출하고, 실제 수신은 ffmpeg로 위임
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


def record_live_stream(ctx, cmd, out_file, log_tag="FFmpeg"):
    """ffmpeg 자식 프로세스 녹화 — 릴레이 계측 + stderr 로그 + 취소 처리.

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
        except Exception as e:
            # [Silent fallback 제거] reader 스레드 예외 로그 후 EOF sentinel 주입
            import chzzktube.core.raw_log as raw_log
            raw_log.raw("LIVE", f"_read_stdout error: {type(e).__name__}: {e}", is_error=True, to_tui=False)
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
                try:
                    raw_log.raw("ffmpeg",
                                LogEvent(stage="LIVE", status="RUN",
                                         scope="FFMP",
                                         msg=raw.decode("utf-8", "replace").strip(),
                                      ),
                                )
                except Exception as e:
                    import chzzktube.core.raw_log as raw_log
                    raw_log.raw("LIVE", f"_drain_stderr error: {type(e).__name__}: {e}", is_error=True, to_tui=False)

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
            except Exception as e:
                import chzzktube.core.raw_log as raw_log
                raw_log.raw("LIVE", f"_try_watchdog_heartbeat error: {type(e).__name__}: {e}", is_error=True, to_tui=False)
            break

```

## File: chzzktube\pipeline\progress_emitter.py

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

## File: chzzktube\pipeline\target_downloader\__init__.py

```python
##### target_downloader/__init__.py - 패키지 공개 API 재내보내기
"""DownloadWorker의 다운로드 실행부 분할 모듈 패키지.

- expand_targets : 재생목록/채널 URL을 개별 동영상 URL로 평탄화
- download_target : 개별 URL을 타입별로 분기해 실제 다운로드
  chzzk(clip/vod) → 직접 HTTP 스트림, youtube VOD → yt-dlp,
  youtube live → _download_youtube_live(yt-dlp + ffmpeg 릴레이)

하위 모듈:
- utils: 공통 상수/유틸리티/에러 분류
- options: yt-dlp 옵션 빌더
- flatten: 재생목록/채널 평탄화
- chzzk: 치지직 VOD/클립/라이브 다운로드
- youtube_vod: 유튜브 VOD 다운로드 (yt-dlp)
- youtube_live: 유튜브 라이브 다운로드
- dispatch: 메인 디스패처 (download_target)
"""

# 공통 유틸리티/상수
from .utils import (
    _RETRYABLE_BOT_MARKERS,
    _TERMINAL_FAIL_MARKERS,
    _WATCHDOG_HEARTBEAT_INTERVAL,
    _FormatQualityLoss,
    _is_retryable_bot_error,
    _has_configured_cookies,
    _chzzk_filename,
    _extract_yt_id,
    _emit_error_log,
    _emit_skip_log,
    _is_youtube_live_url,
)

# yt-dlp 옵션
from .options import _make_ytdl_opts, _format_selector

# 평탄화
from .flatten import _flatten, _classify_item, _normalize_single_item, expand_targets

# 치지직
from .chzzk import _download_chzzk, _download_chzzk_live, _http_download

# 라이브 레코더 (기존 td._lr 호환용)
import chzzktube.pipeline.live_recorder as _lr

# 유튜브 VOD
from .youtube_vod import (
    _download_vod,
    _ensure_pot_server_ready,
    _emit_vod_success,
    _max_requested_height,
    _needs_pot_promotion,
    _QUALITY_CLIENT_CHAIN,
    _POT_CLIENTS,
    YtDownloadError,
)
import yt_dlp
import chzzktube.core.raw_log as raw_log

# 유튜브 라이브
from .youtube_live import _download_youtube_live

# 메인 디스패처
from .dispatch import download_target

# ── 공개 API (기존 import 호환) ────────────────────────────────────────────
__all__ = [
    # 상수
    "_RETRYABLE_BOT_MARKERS",
    "_TERMINAL_FAIL_MARKERS",
    "_WATCHDOG_HEARTBEAT_INTERVAL",
    "_QUALITY_CLIENT_CHAIN",
    "_POT_CLIENTS",
    # 예외
    "_FormatQualityLoss",
    "YtDownloadError",
    # 모듈
    "yt_dlp",
    "_lr",
    "raw_log",
    # 유틸리티
    "_is_retryable_bot_error",
    "_has_configured_cookies",
    "_chzzk_filename",
    "_extract_yt_id",
    "_emit_error_log",
    "_emit_skip_log",
    "_is_youtube_live_url",
    # 옵션
    "_make_ytdl_opts",
    "_format_selector",
    # 평탄화
    "_flatten",
    "_classify_item",
    "_normalize_single_item",
    "expand_targets",
    # 치지직
    "_http_download",
    "_download_chzzk",
    "_download_chzzk_live",
    # 유튜브 VOD
    "_download_vod",
    "_ensure_pot_server_ready",
    "_emit_vod_success",
    "_max_requested_height",
    "_needs_pot_promotion",
    # 유튜브 라이브
    "_download_youtube_live",
    # 디스패처
    "download_target",
]
```

## File: chzzktube\pipeline\target_downloader\chzzk.py

```python
##### target_downloader/chzzk.py - 치지직 VOD/클립/라이브 다운로드
"""치지직 VOD/클립/라이브 직접 HTTP 스트림 다운로드."""
import os
import time
import urllib.request

import chzzktube.core.chzzk_api as chzzk_api
from chzzktube.core.chzzk_api import analyze_chzzk_clip_api, analyze_chzzk_vod_api
from chzzktube.pipeline.target_downloader import utils as td_utils
from chzzktube.pipeline.classifier import ContentKind
import chzzktube.core.raw_log as raw_log
from chzzktube.core.log_emitter import emit_event
from chzzktube.core.dl_platform import _dl_platform


def _http_download(ctx, url: str, out_path: str) -> bool:
    """HTTP 스트림 직접 다운로드 — ffmpeg 없이 순수 urllib로 청크 기록.

    - ctx.speed_win에 수신 바이트 누적으로 속도 측정
    - 워치독 하트비트 5초 주기 발행 (원본 로직: 다중 워치독 속성 순회)
    """
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp, open(out_path, "wb") as f:
            last_heartbeat = time.monotonic()
            while True:
                chunk = resp.read(256 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                ctx.speed_win.add(len(chunk))

                # [결함 5 수리] 워치독 하트비트 5초 주기 — 다중 워치독 속성 순회
                now = time.monotonic()
                if now - last_heartbeat >= td_utils._WATCHDOG_HEARTBEAT_INTERVAL:
                    last_heartbeat = now
                    for attr in ("_download_watchdog", "_gate_watchdog", "_live_watchdog", "_analysis_watchdog"):
                        wd = getattr(ctx, attr, None)
                        if wd and hasattr(wd, "heartbeat"):
                            try:
                                wd.heartbeat()
                            except Exception:
                                pass
                            break
        return True
    except Exception as ex:  # noqa: BLE001
        raw_log.raw(emit_event("DL", "FAIL", "CHZZK", f"HTTP 다운로드 실패: {ex}"), to_tui=False)
        return False


def _download_chzzk(ctx, url: str, content_type: str) -> bool | str:
    """치지직 VOD/클립 다운로드 — API 분석 후 HTTP 스트림 직접 수신."""
    # 1. API로 메타데이터 + 스트림 URL 획득
    try:
        if content_type == "clip":
            ch_info = analyze_chzzk_clip_api(url)
        else:
            ch_info = analyze_chzzk_vod_api(url)
    except Exception as ex:  # noqa: BLE001
        td_utils._emit_error_log(ctx, url, f"Chzzk API 분석 실패: {ex}", ctx.failed_targets)
        return False

    # 2. 스트림 URL이 없으면 스킵
    if not ch_info.get("stream_url"):
        td_utils._emit_skip_log(ctx, ctx.current_item, "스트림 URL 없음")
        return "skip"

    # 3. 출력 경로 생성
    fmt = {"ext": "mp4"}  # 치지직은 기본 mp4
    out_path = td_utils._chzzk_filename(ch_info, fmt, ctx.cfg)

    # 4. HTTP 다운로드 실행
    if _http_download(ctx, ch_info["stream_url"], out_path):
        raw_log.raw(
            emit_event("DL", "OK", "CHZZK", f"완료: {os.path.basename(out_path)}", url=url),
            to_tui=True,
        )
        return True
    else:
        td_utils._emit_error_log(ctx, url, "HTTP 다운로드 실패", ctx.failed_targets)
        return False


def _download_chzzk_live(ctx, url: str) -> bool:
    """치지직 API의 HLS 포맷을 FFmpeg stdout 릴레이로 녹화한다."""
    import os
    import chzzktube.pipeline.live_recorder as _lr
    import chzzktube.core.chzzk_api as chzzk_api
    import chzzktube.pipeline.progress_emitter as _pe

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
    out_file = os.path.join(ctx.cfg["download_path"], td_utils._chzzk_filename(info, fmt, ctx.cfg))
    temp_ts, _, _ = _lr.prepare_live_paths(ctx, out_file)
    cmd = ["ffmpeg", "-y", "-i", fmt["url"]]
    if ctx.cfg.get("audio_only"):
        cmd.append("-vn")
    cmd.extend(["-c", "copy", "-f", "mpegts", "pipe:1"])
    ok = _lr.record_live_stream(ctx, cmd, temp_ts, log_tag="FFmpeg")
    if not ok and not ctx.state.get("canceled"):
        raise RuntimeError("chzzk live recording failed")
    return ok
```

## File: chzzktube\pipeline\target_downloader\dispatch.py

```python
##### target_downloader/dispatch.py - 다운로드 디스패처 (메인 엔트리포인트)
"""개별 항목 다운로드 — 사전 분류 스킵 및 정적 디스패치 테이블 실행."""
from chzzktube.pipeline.classifier import ContentKind, ClassifiedTarget
from chzzktube.pipeline.target_downloader.chzzk import _download_chzzk, _download_chzzk_live
from chzzktube.pipeline.target_downloader.youtube_vod import _download_vod
from chzzktube.pipeline.target_downloader.youtube_live import _download_youtube_live
from chzzktube.pipeline.target_downloader.utils import _emit_error_log
import chzzktube.core.raw_log as raw_log
from chzzktube.core.log_emitter import emit_event
from chzzktube.core.dl_platform import _dl_platform


# ── 정적 디스패치 테이블 ───────────────────────────────────────────────────
# ContentKind -> 다운로드 함수 매핑 (확장 용이)
_DISPATCH_TABLE = {
    ContentKind.CLIP: _download_chzzk,           # CHZZK_CLIP
    ContentKind.VOD: _download_chzzk,            # CHZZK_VOD + YOUTUBE_VOD (구분은 handler 내부에서)
    ContentKind.LIVE_CHZZK: _download_chzzk_live,
    ContentKind.LIVE_YOUTUBE: _download_youtube_live,
}


def download_target(ctx, item, failed_targets, skip_targets=None) -> bool | str:
    """개별 항목 다운로드 — 사전 분류 스킵 및 정적 디스패치 테이블 실행.

    Args:
        ctx: DownloadContext (logger, cfg, speed_win, classifier, current_item 등 포함)
        item: ClassifiedTarget 또는 dict/str (내부에서 _classify_item으로 승격)
        failed_targets: list[(url, reason)] — 실패 항목 누적용
        skip_targets: list[(url, reason)] — 스킵 항목 누적용 (None이면 무시)

    Returns:
        True  - 다운로드 성공
        "skip" - 스킵 (연령 제한, 라이브 미지원 등)
        False - 다운로드 실패 (에러 로그는 이미 기록됨)
    """
    from chzzktube.pipeline.target_downloader.flatten import _classify_item
    from chzzktube.pipeline.target_downloader.utils import _emit_skip_log

    # 1. ClassifiedTarget으로 승격 (이미 승격된 경우 통과)
    item = _classify_item(ctx, item)
    ctx.current_item = item

    # 2. 다운로드 불가 사전 필터링
    if not item.downloadable:
        reason = item.skip_reason or "다운로드 불가"
        _emit_skip_log(ctx, item, reason)
        if skip_targets is not None:
            skip_targets.append((item.url, reason))
        return "skip"

    # 3. 디스패치 테이블에서 핸들러 조회
    handler = _DISPATCH_TABLE.get(item.kind)
    if not handler:
        _emit_error_log(ctx, item.url, f"지원하지 않는 콘텐츠 종류: {item.kind}", failed_targets)
        return False

    # 4. 핸들러 실행 (예외는 핸들러 내부에서 처리 후 False 반환)
    try:
        # VOD는 플랫폼 태그로 분기 (CHZZK vs YouTube)
        if item.kind == ContentKind.VOD:
            if item.platform_tag == "chzzk":
                return _download_chzzk(ctx, item.url, "vod")
            else:
                return _download_vod(ctx, item.url)
        elif item.kind == ContentKind.CLIP:
            return _download_chzzk(ctx, item.url, "clip")
        else:
            return handler(ctx, item.url)
    except Exception as ex:  # noqa: BLE001
        _emit_error_log(ctx, item.url, f"디스패치 예외: {ex}", failed_targets)
        return False
```

## File: chzzktube\pipeline\target_downloader\flatten.py

```python
##### target_downloader/flatten.py - 재생목록/채널 평탄화
"""재생목록/채널 URL을 개별 동영상 ClassifiedTarget 리스트로 평탄화."""
import yt_dlp

from chzzktube.core.playlist import normalize_youtube_channel_url
from chzzktube.pipeline.classifier import ClassifiedTarget, ContentKind, ItemClassifier
from chzzktube.pipeline.target_downloader.utils import _has_configured_cookies


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


def _classify_item(ctx, raw_target: ClassifiedTarget | str | dict) -> ClassifiedTarget:
    """원시 대상을 ClassifiedTarget으로 승격 — 다운로드 가능성/인증 요구 검증 포함."""
    if isinstance(raw_target, ClassifiedTarget):
        item = raw_target
    elif isinstance(raw_target, str):
        item = ItemClassifier.classify(raw_target, raw_info=None)
    elif isinstance(raw_target, dict):
        # dict 형태로 들어온 경우 (레거시 호환)
        item = ItemClassifier.classify(raw_target.get("url", ""), raw_info=raw_target)
    else:
        raise TypeError(f"지원하지 않는 대상 타입: {type(raw_target)}")

    # 1. 다운로드 불가 (이미지 전용 등) 조기 반환
    if not item.downloadable:
        return item

    # 2. 인증 요구사항 교차 검증 (도메인 정책 vs 현재 런타임 cfg)
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


def _normalize_single_item(url: str) -> ClassifiedTarget:
    """단일 영상 URL을 ClassifiedTarget으로 정규화 (메타는 다운로드 단계에서 채움)."""
    return ItemClassifier.classify(url, raw_info=None)


def expand_targets(ctx) -> list[ClassifiedTarget]:
    """재생목록/채널 URL을 개별 동영상 항목 객체로 펼친다.

    반환: List[ClassifiedTarget] - 파이프라인 전체가 공유하는 단일 계약
    """
    from chzzktube.core.dl_platform import detect_content_type
    from chzzktube.pipeline.target_downloader.utils import _emit_error_log

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


# 지연 import로 순환 의존성 방지
def _apply_cookie_opts(opts, cfg):
    from chzzktube.core.client_opts import _apply_cookie_opts as _aco
    _aco(opts, cfg)


def _apply_client_opts(opts, cfg, forced):
    from chzzktube.core.client_opts import _apply_client_opts as _acl
    _acl(opts, cfg, forced=forced)


def _apply_light_analysis_opts(opts):
    from chzzktube.core.client_opts import _apply_light_analysis_opts as _ala
    _ala(opts)


def _apply_ejs_opts(opts):
    from chzzktube.core.client_opts import _apply_ejs_opts as _ae
    _ae(opts)
```

## File: chzzktube\pipeline\target_downloader\options.py

```python
##### target_downloader/options.py - yt-dlp 옵션 빌더
"""yt-dlp 다운로드 옵션 생성 — 포맷 선택/병합/쿠키/PO 토큰 주입."""
import functools
import os

import chzzktube.pipeline.progress_emitter as _pe
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
from chzzktube.core.dl_platform import _dl_platform
from chzzktube.core.utils import get_filename_template
from chzzktube.infra.po_client import extract_video_id
from chzzktube.pipeline.target_downloader.utils import _extract_yt_id, _has_configured_cookies


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
            ctx.cfg.get("download_path", ""),
            get_filename_template(cfg=ctx.cfg),
        ),
        "format": _format_selector(ctx),
        "merge_output_format": ctx.cfg.get("container", "mp4"),
        "socket_timeout": 30,
        "retries": ctx.cfg.get("retries", 10),
        "fragment_retries": ctx.cfg.get("fragment_retries", 10),
        "concurrent_fragment_downloads": _concurrent_fragments(ctx.cfg),
    }

    _apply_cookie_opts(opts, ctx.cfg)
    _apply_client_opts(opts, ctx.cfg, forced=forced_client)
    _apply_ffmpeg_opts(opts)
    _apply_post_opts(opts, ctx.cfg)
    _apply_ejs_opts(opts)

    # PO 토큰 강제 주입 (POT 서버 재시도 시)
    if inject_pot:
        video_id = _extract_yt_id(url)
        if video_id:
            _apply_pot_opts(opts, video_id, client=forced_client or "auto")

    return opts
```

## File: chzzktube\pipeline\target_downloader\utils.py

```python
##### target_downloader/utils.py - 공통 유틸리티/상수/분류 헬퍼
"""target_downloader 패키지 공통 유틸리티.

- 에러 마커 상수 (봇 재시도 가능 vs 터미널 실패)
- 워치독 하트비트 간격
- 쿠키 설정 확인
- 치지직 파일명 생성
- YouTube ID 추출
"""
import os
import re

import chzzktube.core.raw_log as raw_log
from chzzktube.core.dl_platform import _dl_platform
from chzzktube.core.log_emitter import emit_event
from chzzktube.core.utils import get_filename_template
from chzzktube.pipeline.classifier import ClassifiedTarget


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


def _has_configured_cookies(cfg: dict) -> bool:
    """현재 설정에서 쿠키가 구성되어 있는지 확인."""
    return bool(cfg.get("cookies") or cfg.get("cookies_file"))


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


def _extract_yt_id(url: str) -> str | None:
    """YouTube URL에서 video_id 추출."""
    patterns = [
        r"(?:v=|/)([0-9A-Za-z_-]{11})(?:[&?#]|$)",
        r"youtu\.be/([0-9A-Za-z_-]{11})",
        r"youtube\.com/shorts/([0-9A-Za-z_-]{11})",
    ]
    for pat in patterns:
        m = re.search(pat, url)
        if m:
            return m.group(1)
    return None


def _emit_error_log(ctx, url: str, reason: str, failed_targets: list) -> None:
    """에러 로그 기록만 수행 (즉시 TUI 발행 금지 — finalizer에서 단일 출력).

    raw 버스에도 즉시 발행하지 않고, failed_targets에만 누적한다.
    finalize 단계에서 한 번에 출력한다.
    """
    failed_targets.append((url, reason))


def _is_youtube_live_url(ctx, url: str) -> bool:
    """현재 항목이 YouTube 라이브 URL인지 확인."""
    try:
        return ctx.classifier.is_youtube_live(url)
    except AttributeError:
        # classifier 미주입 시 폴백
        return "youtube.com/live" in url or "youtu.be/" in url and "live" in url


def _emit_skip_log(ctx, item: ClassifiedTarget, reason: str) -> None:
    """스킵 로그 기록 (to_tui=True — 사용자 알림 필요)."""
    raw_log.raw(
        emit_event("DL", "SKIP", _dl_platform(item.url), reason, url=item.url),
        to_tui=True,
    )
```

## File: chzzktube\pipeline\target_downloader\youtube_live.py

```python
##### target_downloader/youtube_live.py - 유튜브 라이브 다운로드
"""YouTube 라이브 녹화 — yt-dlp/ffmpeg 파이프 단일 경로.

[v3.10.0] Streamlink 경로 완전 제거 — 모든 라이브 녹화는
`live_recorder.download_youtube_live()`(yt-dlp 포맷 추출 → ffmpeg 릴레이)로 통합.
"""


def _get_lr():
    """live_recorder 모듈 동적 조회 (테스트 패치 지원)."""
    import chzzktube.pipeline.target_downloader as td
    return getattr(td, "_lr", None) or __import__("chzzktube.pipeline.live_recorder", fromlist=[""])


def _download_youtube_live(ctx, url: str) -> bool | str:
    """유튜브 라이브 — yt-dlp로 포맷 URL만 추출 후 live_recorder로 위임."""
    return _get_lr().download_youtube_live(ctx, url)
```

## File: chzzktube\pipeline\target_downloader\youtube_vod.py

```python
##### target_downloader/youtube_vod.py - 유튜브 VOD 다운로드 (yt-dlp)
"""YouTube VOD 다운로드 — yt-dlp 기반, 품질 우선 폴백 + PO 토큰 주입."""
import os
import time

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

from chzzktube.pipeline.target_downloader.utils import (
    _WATCHDOG_HEARTBEAT_INTERVAL,
    _FormatQualityLoss,
    _emit_error_log,
    _emit_skip_log,
    _extract_yt_id,
    _is_retryable_bot_error,
    _has_configured_cookies,
)
from chzzktube.pipeline.target_downloader.options import _make_ytdl_opts, _format_selector
import chzzktube.core.raw_log as raw_log
from chzzktube.core.log_emitter import emit_event
from chzzktube.core.dl_platform import _dl_platform
from chzzktube.core.log_emitter import emit_event
from chzzktube.core.dl_platform import _dl_platform


# 품질 우선 폴백 체인 (v3.8.0): web → web_safari → ios → tv
_QUALITY_CLIENT_CHAIN = ("web", "web_safari", "ios", "tv")

# PO 토큰 주입 대상 클라이언트 (web/web_safari만)
_POT_CLIENTS = ("web", "web_safari")


def _ensure_pot_server_ready(ctx, timeout=60.0) -> bool:
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
    import chzzktube.pipeline.progress_emitter as _pe

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
            ensure_node_server(log_func=_log)
        finally:
            release_prewarm_lock(fd)

    # 스폰 또는 기존 프로세스 재사용
    proc = _spawn_existing(log_func=_log)
    if proc is None:
        _log("pot spawn failed")
        return False

    # /ping 준비까지 폴링
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _alive():
            _log("pot server ready")
            return True
        _heartbeat()
        time.sleep(0.5)

    _log("pot server timeout")
    return False


def _emit_vod_success(ctx, info: dict) -> None:
    """VOD 다운로드 성공 로그 — 제목/포맷/파일 크기."""
    title = info.get("title", "unknown")
    fmt = _format_selector(ctx) if hasattr(ctx, "v_spec") else "best"
    raw_log.raw(
        emit_event("DL", "OK", "YT", f"{title} [{fmt}]", url=ctx.current_url),
        to_tui=True,
    )


def _max_requested_height(info: dict) -> int:
    """요청된 최대 해상도 높이 반환 (포맷 선택 검증용)."""
    v_spec = info.get("v_spec") or {}
    return v_spec.get("height") or 0


def _needs_pot_promotion(ctx, info: dict) -> bool:
    """1차 다운로드 성공했지만 고화질(1080p+) 분리 포맷 누락 시 POT 승격 필요 여부."""
    requested = _max_requested_height(info)
    if requested < 1080:
        return False

    # 실제 획득한 포맷 확인
    formats = info.get("formats") or []
    has_high = any(
        f.get("height", 0) >= 1080 and f.get("vcodec") != "none"
        for f in formats
    )
    return not has_high


def _try_download_with_client(ctx, url: str, client: str, inject_pot: bool) -> tuple[bool, dict | None]:
    """지정된 client로 다운로드 시도 — 성공 시 (True, info), 실패 시 (False, err)."""
    opts = _make_ytdl_opts(ctx, {}, url, forced_client=client, inject_pot=inject_pot)

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            return True, info
    except yt_dlp.utils.DownloadError as ex:
        return False, ex
    except Exception as ex:  # noqa: BLE001
        return False, ex


def _download_vod(ctx, url: str) -> bool | str:
    """YouTube VOD 다운로드 — 품질 우선 폴백 + PO 토큰 재시도.

    반환:
        True  - 성공
        "skip" - 스킵 (연령 제한 등)
        False - 실패 (상위에서 재시도/에러 처리)
    """
    # 1. 연령 제한 등 스킵 사전 확인
    item = ctx.current_item
    if item.capability.requires_auth and not _has_configured_cookies(ctx.cfg):
        _emit_skip_log(ctx, item, "age/member gated")
        return "skip"

    # 2. 품질 우선 폴백 체인 시도
    last_err = None
    for i, client in enumerate(_QUALITY_CLIENT_CHAIN):
        inject_pot = client in _POT_CLIENTS and _ensure_pot_server_ready(ctx)
        success, result = _try_download_with_client(ctx, url, client, inject_pot)

        if success:
            info = result
            # 고화질(1080p+) 누락 시 POT 승격 필요 체크
            if _needs_pot_promotion(ctx, info):
                raise _FormatQualityLoss("1080p+ 분리 포맷 누락 — POT 재시도 필요")
            _emit_vod_success(ctx, info)
            return True

        last_err = result
        err = result if isinstance(result, Exception) else Exception(str(result))

        # 봇 차단 감지 → 다음 클라이언트로 폴백
        if _is_retryable_bot_error(err):
            raw_log.raw(
                emit_event("DL", "WARN", "YT", f"{client} 봇 차단 — 다음 클라이언트 시도"),
                to_tui=False,
            )
            continue

        # 터미널 에러 → 즉시 전파 (상위에서 처리)
        raise err

    # 3. 모든 클라이언트 실패 → 마지막 에러 기록
    _emit_error_log(ctx, url, f"전체 클라이언트 체인 실패: {last_err}", ctx.failed_targets)
    return False
```

## File: chzzktube\ui\__init__.py

```python
"""UI 모듈 - TUI 컴포넌트들."""
from chzzktube.ui.progress_bar import ProgressBar, ProgressManager

__all__ = ["ProgressBar", "ProgressManager"]

```

## File: chzzktube\ui\dialogs.py

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

        btn_stop = QPushButton("Stop && Exit")
        btn_stop.setStyleSheet(theme.BTN_EXIT_DANGER_QSS)
        btn_stop.clicked.connect(lambda: self.done(1))

        btn_continue = QPushButton("Continue")
        btn_continue.setStyleSheet(theme.BTN_NEUTRAL_QSS)
        btn_continue.clicked.connect(lambda: self.done(0))

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
# F12 상세 로그에 기록한다. yt-dlp --version → '2026.08.19',
# ffmpeg -version → 'ffmpeg version 9.0' 식의 터미널 출력 그대로.
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
        r_sl.addWidget(self._key_label("Subtitles"))

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

        # 갱신형 라인 추적: component_id -> block number
        self._status_lines: dict[str, int] = {}

    def append(self, msg, is_status=False, component_id: str = None):
        if not msg:
            return
        if is_status and component_id:
            # 갱신형: component_id로 기존 라인 찾기/생성
            doc = self.te.document()
            cursor = self.te.textCursor()

            if component_id in self._status_lines:
                # 기존 블록 찾아서 내용 교체
                block_num = self._status_lines[component_id]
                block = doc.findBlockByNumber(block_num)
                if block.isValid():
                    cursor.setPosition(block.position())
                    cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
                    cursor.removeSelectedText()
                    cursor.insertText(str(msg))
                else:
                    # 블록이 없으면 새로 추가
                    cursor.movePosition(QTextCursor.MoveOperation.End)
                    cursor.insertBlock()
                    cursor.insertText(str(msg))
                    self._status_lines[component_id] = doc.blockCount() - 1
            else:
                # 새로 추가
                cursor.movePosition(QTextCursor.MoveOperation.End)
                cursor.insertBlock()
                cursor.insertText(str(msg))
                self._status_lines[component_id] = doc.blockCount() - 1
        elif is_status and not component_id:
            # 기존 방식: 마지막 줄만 갱신 (하위 호환)
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
        self._status_lines.clear()
        self.lbl_info.setText(f"buffer — {self.te.document().blockCount()} lines")

```

## File: chzzktube\ui\log_console.py

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
        # list[dict] = {msg, is_status, is_error, fg_color, no_wrap, component_id, is_progress}
        self._buffer = deque(maxlen=4096)
        # 진행률 갱신형 라인 추적: component_id -> buffer index
        self._progress_lines: dict[str, int] = {}

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

    def append(self, msg, is_status=False, is_error=False, fg_color=None, no_wrap=False, 
           component_id: str = None, is_progress: bool = False):
        """빈 줄 생성 차단 및 정밀 문단 삭제 파이프라인.

        [진행률 갱신형 계약] 진행률/진행 중 상태 로그는 반드시 is_status=True로
        호출할 것 — ConciseLogConsole이 직전 상태 블록을 같은 줄에 덮어쓴다
        (Single-Line In-Place Status, HANDOVER §6). is_status=False로 emit하면
        매 틱 새 줄이 쌓여 '한 행 = 한 정보' 규칙을 위반한다. DL/LIVE 틱,
        DEPS 다운로드 %, PO 서버 진행 등 모든 반복 로그가 해당.

        [다중 컴포넌트 진행률 갱신형] component_id와 is_progress=True로 호출하면
        해당 컴포넌트의 기존 진행 라인을 갱신한다 (여러 컴포넌트 동시 갱신형 지원).
        이 라인은 is_status 로그에 의해 지워지지 않으며, 완료 시 is_progress=False로
        호출하면 히스토리로 확정된다.

        [줄바꿈 계약] 줄바꿈 결정은 발행자(raw() 경유 LogEvent → 구독자) 측의
        no_wrap 플래그를 그대로 따르며, 렌더 레이어에서 문자열 내용을 다시
        뜯어 판단하지 않는다(정규식 라우팅 제로). LogEvent 경유분(컬럼 포맷·
        프리포맷)은 True, 큐 호환용 bare 문자열은 False다.
        """
        self._sync_budget()  # 현재 뷰포트/폰트 기준 예산 보장 — 자동랩 침범 방지
        clean_msg = str(msg)     # 인자로 들어온 msg를 함수 진입 즉시 안전한 문자열로 바인딩

        # 진행률 갱신형: 기존 라인 갱신
        if component_id and is_progress:
            self._update_progress_line(component_id, clean_msg, is_error, fg_color, no_wrap)
            return

        # 진행률 완료: 진행 중이던 기존 버퍼 엔트리의 is_progress를 False로 잠그고 제자리 확정
        if component_id and not is_progress and component_id in self._progress_lines:
            idx = self._progress_lines.pop(component_id)
            if 0 <= idx < len(self._buffer):
                self._buffer[idx]["msg"] = clean_msg
                self._buffer[idx]["is_progress"] = False
                self._buffer[idx]["is_status"] = False
                self._buffer[idx]["is_error"] = is_error
            # 버퍼 제자리 라인을 완료 메시지로 갱신한 뒤 즉시 화면에 확정 박제!
            self.reflow()
            return

        # [리플로우 대비] 원본 로그를 버퍼에 보관
        self._buffer.append(
            {"msg": clean_msg, "is_status": is_status, "is_error": is_error,
             "fg_color": fg_color, "no_wrap": bool(no_wrap),
             "component_id": component_id, "is_progress": is_progress}
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

    def _update_progress_line(self, component_id: str, msg: str, is_error: bool, fg_color: str, no_wrap: bool):
        """특정 컴포넌트의 진행률 라인을 갱신 (buffer 교체 + reflow)."""
        idx = self._progress_lines.get(component_id)
        if idx is not None and 0 <= idx < len(self._buffer):
            # 기존 버퍼 엔트리 갱신
            self._buffer[idx] = {
                "msg": msg,
                "is_status": False,
                "is_error": is_error,
                "fg_color": fg_color,
                "no_wrap": bool(no_wrap),
                "component_id": component_id,
                "is_progress": True,
            }
        else:
            # 새 진행 라인 추가
            self._buffer.append({
                "msg": msg,
                "is_status": False,
                "is_error": is_error,
                "fg_color": fg_color,
                "no_wrap": bool(no_wrap),
                "component_id": component_id,
                "is_progress": True,
            })
            self._progress_lines[component_id] = len(self._buffer) - 1

        # 전체 reflow로 갱신 반영
        self.reflow()

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
        진행률 라인(is_progress=True)은 모두 보존한다.
        """
        buf = self._buffer
        if not buf:
            return
        self.te.clear()
        self.last_log_was_status = False
        self.last_status_block_count = 1
        self._pending_blank = False
        self._just_removed_status = False

        # 상태 로그 연속 그룹의 마지막만, 진행률 라인은 모두 렌더링 대상으로 추려낸다
        entries = []
        i = 0
        while i < len(buf):
            e = buf[i]
            if e.get("is_status"):
                j = i
                while j + 1 < len(buf) and buf[j + 1].get("is_status"):
                    j += 1
                entries.append(buf[j])
                i = j + 1
            elif e.get("is_progress"):
                # 진행률 라인은 모두 포함
                entries.append(e)
                i += 1
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
                cursor, e["msg"], e.get("is_status", False), e.get("is_error", False), e.get("fg_color"),
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

## File: chzzktube\ui\log_mirror.py

```python
"""v3.9.0 로그 미러 — MainWindow에서 추출한 TUI/F12 미러 전담 모듈.

HANDOVER §5-33 직교 분리 + §6 Thin Wrapper 금지:
로직 통째 이전 (위임 껍데기 아님). MainWindow는 이 모듈 함수에
(fake-self 호환) 바인딩으로 위임한다.
"""
from chzzktube.core.log_event import LogEvent
from chzzktube.core import log_emitter


def finalize_concise_progress(self, line, is_status, is_error, component_id):
    """component_id로 추적 중인 TUI 진행 라인을 마감 이벤트로 확정한다."""
    if not component_id:
        return False
    console = getattr(self, "console", None)
    progress_lines = getattr(console, "_progress_lines", None)
    buffer = getattr(console, "_buffer", None)
    if not isinstance(progress_lines, dict) or buffer is None:
        return False

    index = progress_lines.get(component_id)
    if not isinstance(index, int) or not (0 <= index < len(buffer)):
        progress_lines.pop(component_id, None)
        return False

    entry = dict(buffer[index])
    entry.update({
        "msg": line,
        "is_status": bool(is_status),
        "is_error": bool(is_error),
        "component_id": component_id,
        "is_progress": False,
    })
    buffer[index] = entry
    progress_lines.pop(component_id, None)
    reflow = getattr(console, "reflow", None)
    if callable(reflow):
        reflow()
    return True


def render_concise(self, event, is_status=False, is_error=False):
    if isinstance(event, LogEvent):
        line = log_emitter.format_log_line_for_event(event)
        no_wrap = True
        component_id = getattr(event, "component_id", None)
        is_progress = bool(getattr(event, "is_progress", False))
    else:
        line = str(event)
        no_wrap = False
        component_id = None
        is_progress = False
    if len(line) > 4096:
        line = line[:4096] + "…"
    if component_id and not is_progress and finalize_concise_progress(
        self, line, is_status, is_error, component_id
    ):
        return
    try:
        self.console.append(
            line, is_status, is_error, no_wrap=no_wrap,
            component_id=component_id, is_progress=is_progress,
        )
    except TypeError:
        self.console.append(line, is_status, is_error, no_wrap=no_wrap)


def mirror_event_full(self, event, is_status=False):
    if isinstance(event, LogEvent):
        line = event.msg if event.msg else ""
        self._last_full_event = event
        component_id = getattr(event, "component_id", None)
        is_progress = bool(getattr(event, "is_progress", False))
    else:
        line = str(event)
        component_id = None
        is_progress = False
    f12_is_status = bool(is_status or is_progress)
    if f12_is_status:
        self._last_status_line = line
    try:
        mirror_full_log(self, line, f12_is_status, component_id=component_id)
    except TypeError:
        mirror_full_log(self, line, f12_is_status)


def mirror_full_log(self, line, is_status=False, component_id: str = None):
    """F12 전체 로그 버퍼 적재 및 활성 다이얼로그 제자리 갱신 관통 (SSOT).

    [v3.9.0 선택지 B] 진행 틱(is_status/component_id)은 버퍼 스냅샷 치환.
    전량 보존은 raw_log history + full_events ring이 담당 (직교 분리).
    """
    import time
    from collections import deque

    msg = str(line)
    if len(msg) > 4096:
        msg = msg[:4096] + "…"
    ts = time.strftime("%H:%M:%S")
    stamped = "\n".join(f"[{ts}] {line}" if line else f"[{ts}]" for line in msg.split("\n"))

    buf = getattr(self, "_full_log_buf", None)
    if buf is None:
        # 테스트 대역 등 버퍼 미보유 호출자: 다이얼로그 미러 경로로 폴백.
        _mirror_to_window_only(self, stamped, is_status, component_id)
        return
    if not isinstance(buf, deque):
        buf = deque(buf, maxlen=4096)
        self._full_log_buf = buf

    if is_status or component_id:
        if getattr(self, "_last_full_was_status", False) and buf:
            buf[-1] = stamped
        else:
            buf.append(stamped)
        self._last_full_was_status = True
    else:
        buf.append(stamped)
        self._last_full_was_status = False

    win = getattr(self, "verbose_win", None)
    win_visible = win is not None and win.isVisible()
    if win_visible:
        self._full_log_win_n = len(buf)
        try:
            win.append(stamped, is_status, component_id)
        except (AttributeError, RuntimeError, TypeError):
            try:
                win.append(stamped, is_status)
            except (AttributeError, RuntimeError):
                pass
    # 버퍼 미보유 대역(_FakeMain 등) 호환: 기존 _mirror_full_log 오버라이드 경유.
    _mirror_compat = getattr(type(self), "_mirror_full_log", None)
    if buf is None and callable(_mirror_compat):
        pass  # 위 폴백에서 이미 처리


def _mirror_to_window_only(self, stamped, is_status, component_id):
    """버퍼 없이 다이얼로그 미러만 수행 (테스트 대역 호환).

    레거시 _FakeMain._mirror_full_log(line, is_status) 오버라이드가 있으면
    그것을 호출해 rendered 수집을 유지한다.
    """
    override = getattr(self, "_mirror_full_log", None)
    # 무한 재귀 방지: 바인딩된 메서드가 log_mirror.mirror_full_log 자체면 스킵.
    if callable(override) and getattr(override, "__func__", None) is not mirror_full_log:
        try:
            return override(stamped.split("] ", 1)[-1] if "] " in stamped else stamped,
                            is_status)
        except TypeError:
            pass
    win = getattr(self, "verbose_win", None)
    if win is not None and win.isVisible():
        try:
            win.append(stamped, is_status, component_id)
        except (AttributeError, RuntimeError, TypeError):
            pass

```

## File: chzzktube\ui\main_window.py

```python
##### main.py - 메인 윈도우 및 앱 실행 진입점
import os
import platform
import re
import sys
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
    QDialog,
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
from chzzktube.control.gate_state import GateState
import chzzktube.control.gate_state as gate_state
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

        # 워치독 폴링용 타이머 (1초 주기)
        self._watchdog_poll_timer = QTimer(self)
        self._watchdog_poll_timer.setInterval(1000)
        self._watchdog_poll_timer.timeout.connect(self._poll_watchdogs)

        self.init_ui()

        # 구성요소(yt-dlp/ffmpeg/node) 자동 업데이트 확인 — 기동 직후 비동기 1회
        QTimer.singleShot(500, self._start_update_check)

        # [v3.8.1] 폴백 타이머 제거 — deps 수급 실패 시 영구 잠금, 사용자 재시도(ENTER) 대기
        # self._fallback_timer = QTimer(self)
        # self._fallback_timer.setSingleShot(True)
        # self._fallback_timer.timeout.connect(self._force_unlock_input)
        # self._fallback_timer.start(int(FALLBACK_TIMEOUT_SEC * 1000))
        # [정리] 기동 폴백 만료의 단일 기준 — 이 타이머가 유일한 판정자다(폴링
        # 워치독이 같은 만료를 따로 판정해 유예를 끊던 이중 구조 제거).
        # [v3.8.1] 폴백 완전 제거 — deps 수급 완료까지 입력 잠금 유지

        # [Task 4-2] 게이트·분석 워치독 무장/해제 + POT 재시도 상태를
        # GateState 컨테이너로 통합 — 상태 변수 개별 초기화 금지(§6) 준수.
        self._gate_state = GateState(self._gate_watchdog, self._analysis_watchdog)

        # [Followup-5] DEPS 검사의 실제 FAIL(미설치 등)은 게이트 사유로 승격한다.
        self._deps_failed = []
        self._watchdog_poll_timer.start()

    # ── GateState 호환 property ──────────────────────────────────────────
    # 판정 로직 실체는 gate_state 모듈 함수. 여기는 데이터 위임 층만 담당.
    @property
    def _gate_watchdog_active(self) -> bool:
        gs = getattr(self, "_gate_state", None)
        if gs is not None:
            return gs.gate_active
        # fallback: old attribute (tests/mocks)
        return bool(getattr(self, "_gate_watchdog_active_fallback", False))

    @_gate_watchdog_active.setter
    def _gate_watchdog_active(self, val: bool) -> None:
        gs = getattr(self, "_gate_state", None)
        if gs is not None:
            gs.gate_active = val
        else:
            # fallback: old attribute (tests/mocks)
            self._gate_watchdog_active_fallback = val

    @property
    def _analysis_watchdog_active(self) -> bool:
        gs = getattr(self, "_gate_state", None)
        if gs is not None:
            return gs.analysis_active
        return bool(getattr(self, "_analysis_watchdog_active_fallback", False))

    @_analysis_watchdog_active.setter
    def _analysis_watchdog_active(self, val: bool) -> None:
        gs = getattr(self, "_gate_state", None)
        if gs is not None:
            gs.analysis_active = val
        else:
            self._analysis_watchdog_active_fallback = val

    @property
    def _pot_retry_pending(self) -> bool:
        gs = getattr(self, "_gate_state", None)
        if gs is not None:
            return gs.pot_retry_pending
        return bool(getattr(self, "_pot_retry_pending_fallback", False))

    @_pot_retry_pending.setter
    def _pot_retry_pending(self, val: bool) -> None:
        gs = getattr(self, "_gate_state", None)
        if gs is not None:
            gs.pot_retry_pending = val
        else:
            self._pot_retry_pending_fallback = val

    @property
    def _pot_retry_url(self):
        gs = getattr(self, "_gate_state", None)
        if gs is not None:
            return gs.pot_retry_url
        return getattr(self, "_pot_retry_url_fallback", None)

    @_pot_retry_url.setter
    def _pot_retry_url(self, val) -> None:
        gs = getattr(self, "_gate_state", None)
        if gs is not None:
            gs.pot_retry_url = val
        else:
            self._pot_retry_url_fallback = val

    @property
    def _pot_retry_done(self):
        gs = getattr(self, "_gate_state", None)
        if gs is not None:
            return gs.pot_retry_done
        return getattr(self, "_pot_retry_done_fallback", set())

    @_pot_retry_done.setter
    def _pot_retry_done(self, val) -> None:
        gs = getattr(self, "_gate_state", None)
        if gs is not None:
            gs.pot_retry_done = val
        else:
            self._pot_retry_done_fallback = val

    @property
    def _gate_watchdog(self):
        gs = getattr(self, "_gate_state", None)
        if gs is not None:
            return gs.gate_watchdog
        return getattr(self, "_gate_watchdog_fallback", None)

    @_gate_watchdog.setter
    def _gate_watchdog(self, val) -> None:
        gs = getattr(self, "_gate_state", None)
        if gs is not None:
            gs.gate_watchdog = val
        else:
            self._gate_watchdog_fallback = val

    @property
    def _analysis_watchdog(self):
        gs = getattr(self, "_gate_state", None)
        if gs is not None:
            return gs.analysis_watchdog
        return getattr(self, "_analysis_watchdog_fallback", None)

    @_analysis_watchdog.setter
    def _analysis_watchdog(self, val) -> None:
        gs = getattr(self, "_gate_state", None)
        if gs is not None:
            gs.analysis_watchdog = val
        else:
            self._analysis_watchdog_fallback = val

    # ── 게이트·분석 워치독·재시도 메서드 (Thin Wrapper 금지: 실체는 gate_state) ──
    def _start_gate_watchdog(self):
        """[Followup-3] POT gate 대기 2차 워치독 기동."""
        gate_state.start_gate(self._ensure_gate_state())

    def _stop_gate_watchdog(self):
        gate_state.stop_gate(self._ensure_gate_state())

    def _on_pot_work_tick(self):
        """실제 POT 진행만 활성 게이트를 연장한다. 완료 후에는 재무장하지 않는다."""
        gate_state.on_pot_work_tick(self._ensure_gate_state())

    def _on_gate_timeout(self):
        """[Followup-3] gate hang — POT 작업을 트리 종료하고 대기 큐를 해제한다."""
        gs = self._ensure_gate_state()
        if not gs.gate_active:
            return
        self._stop_gate_watchdog()
        if not self._pot_manager.is_busy():
            return
        # cancel()에서 pot_finished가 즉시 발행되어도 보류 요청은 재실행되지 않는다.
        self._pending_download = None
        gate_state.clear_retry(gs)
        self._pot_manager.cancel()
        self.append_concise_log(
            log_emitter.emit_event("SYS", "WARN", "POT", "gate timeout — pot abandoned"),
            is_status=False,
            is_error=False,
        )
        self.update_ui_state()

    def _arm_analysis_watchdog(self):
        """[Watchdog] 분석 스폰 1회 무장 — 이후 만료 판정은 폴링이 담당한다."""
        gs = self._ensure_gate_state()
        gate_state.arm_analysis(gs)

    def _disarm_analysis_watchdog(self):
        """[Watchdog] 분석 마감(성공/실패/만료) 해제 — 만료의 영속 재판정을 끊는다."""
        gs = self._ensure_gate_state()
        gate_state.disarm_analysis(gs)

    def _poll_watchdogs(self):
        """1초마다 워치독 타임아웃을 폴링해 발화 조건 충족 시 처리.

        기동 폴백은 여기서 판정하지 않는다 — 만료의 단일 기준은 _fallback_timer며,
        이중 판정은 Followup-4 유예(재무장 직후 폴링이 유예를 끊는 결함)를 낳았다.
        """
        gs = self._ensure_gate_state()
        # 1) 게이트 워치독
        if gs.gate_active and gs.gate_watchdog.check_timeout():
            self._on_gate_timeout()
            return

        # 2) 분석 워치독 — 워커의 activity 신호가 수명을 연장하고,
        #    만료 시 여기서 복구(워커 유기 + FAIL 마감)를 단독 수행한다.
        if gs.analysis_active and gs.analysis_watchdog.check_timeout():
            self._on_analysis_timeout()
            return

    def _on_analysis_timeout(self):
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

        is_running = getattr(self.ctrl, "running", False)

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
                lines = [raw.strip() for raw in f if raw.strip() and not raw.strip().startswith("#")]
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
        real_stale = [s for s in (stale or []) if s[2] and s[2] != "not installed"]
        if real_stale:
            for label, _, cur, latest in real_stale:
                self.append_concise_log(
                    log_emitter.emit_event("DEPS", "WARN", label.upper(), f"update {cur}→{latest}"),
                    is_status=False,
                    is_error=False,
                )
            self._stale_updates = True
        else:
            self._stale_updates = False
            if not getattr(self, "_deps_failed", []):
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
        self.update_worker.upgrade_done.connect(self._on_upgrade_done)
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

    def _on_upgrade_done(self, ok: bool, summary: str):
        """업그레이드 완료 수신 — 실패 목록 리셋 및 POT prewarm/READY 게이트 진행."""
        if ok:
            self._deps_failed = []
        self._startup_coord.report_upgrade(ok, summary)
        if ok:
            self._pot_manager.ensure_ready("prewarm")
        self.update_ui_state()

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
        if ok and self._ensure_gate_state().pot_retry_pending:
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

    def _ensure_gate_state(self):
        """[Task 4-2] GateState 보장 — 기존 테스트 대역(SimpleNamespace)이
        직접 플래그만 가질 때 자동으로 GateState를 구성해 호환성을 유지한다.
        Thin Wrapper 금지(§6) 준수: gate_state 모듈 함수가 판정 로직의
        단일 진실이며, 여기는 호출부 컨테이너 생성만 담당한다.
        """
        if getattr(self, "_gate_state", None) is not None:
            return self._gate_state
        # watchdog 인스턴스는 property일 수 있지만, 재귀 루프를 막기 위해
        # property 내부가 또 _ensure_gate_state를 호출하기 전에 종료해야 한다.
        # _gate_watchdog/_analysis_watchdog property는 자신의 _gate_state를
        # 먼저 조회하므로, _gate_state가 없을 때만 인스턴스 dict로 폴백한다.
        # _analysis_watchdog_raw 키도 함께 확인한다 (테스트 대역 Raw 저장용).
        gs = GateState(
            self.__dict__.get("_gate_watchdog", None),
            self.__dict__.get("_analysis_watchdog",
                              self.__dict__.get("_analysis_watchdog_raw", None)),
        )
        # 기존 플래그 값 마이그레이션 (설정자 우선, 없으면 기본 False)
        # __dict__ 직접 조회 대신 getattr 사용 — 테스트 대역의 property getter가
        # 다시 _ensure_gate_state()를 호출하는 순환(RecursionError)을 원천 차단한다.
        # watchdog 인스턴스는 property일 수 있으므로 getattr 유지 (재귀 없음).
        gs.gate_active = bool(getattr(self, "_gate_watchdog_active", False))
        gs.analysis_active = bool(getattr(self, "_analysis_watchdog_active", False))
        gs.pot_retry_pending = bool(getattr(self, "_pot_retry_pending", False))
        gs.pot_retry_url = getattr(self, "_pot_retry_url", None)
        gs.pot_retry_done = getattr(self, "_pot_retry_done", set())
        self._gate_state = gs
        return gs

    def get_current_app_state(self) -> str:
        """[P3b] POT 백그라운드 작업(is_busy)은 입력 잠금 사유가 아니다 — 그 역할은
        toggle_download의 큐잉(_pending_download)이 맡는다. is_busy를 STARTUP 사유로
        두면 프리웜 진행 중 ENTER가 큐잉 분기에 도달하지 못하고 무반응으로 끝났다.
        """
        if not getattr(self, "_startup_completed", False):
            return "STARTUP"
        if self.ctrl.running:
            return "RUNNING"
        if self.ctrl.analyzing:
            return "ANALYZING"
        if self.ctrl.picking:
            return "PICKING"
        return "IDLE"

    def _start_gate_watchdog(self):
        """[Followup-3] POT gate 대기 2차 워치독 기동."""
        gate_state.start_gate(self._ensure_gate_state())

    def _stop_gate_watchdog(self):
        gate_state.stop_gate(self._ensure_gate_state())

    def _on_pot_work_tick(self):
        """실제 POT 진행만 활성 게이트를 연장한다. 완료 후에는 재무장하지 않는다."""
        gate_state.on_pot_work_tick(self._ensure_gate_state())

    def _on_gate_timeout(self):
        """[Followup-3] gate hang — POT 작업을 트리 종료하고 대기 큐를 해제한다."""
        gs = self._ensure_gate_state()
        if not gs.gate_active:
            return
        self._stop_gate_watchdog()
        if not self._pot_manager.is_busy():
            return
        # cancel()에서 pot_finished가 즉시 발행되어도 보류 요청은 재실행되지 않는다.
        self._pending_download = None
        gate_state.clear_retry(gs)
        self._pot_manager.cancel()
        self.append_concise_log(
            log_emitter.emit_event("SYS", "WARN", "POT", "gate timeout — pot abandoned"),
            is_status=False,
            is_error=False,
        )
        self.update_ui_state()

    def _arm_analysis_watchdog(self):
        """[Watchdog] 분석 스폰 1회 무장 — 이후 만료 판정은 폴링이 담당한다."""
        gate_state.arm_analysis(self._ensure_gate_state())

    def _disarm_analysis_watchdog(self):
        """[Watchdog] 분석 마감(성공/실패/만료) 해제 — 만료의 영속 재판정을 끊는다."""
        gate_state.disarm_analysis(self._ensure_gate_state())

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
        gs = self._ensure_gate_state()
        if gs.pot_retry_pending:
            return False
        url = self.url_input.text().strip()
        if not gate_state.schedule_retry(gs, url):
            return False
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
        url = gate_state.consume_retry(self._ensure_gate_state())
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

    def _finalize_concise_progress(self, line, is_status, is_error, component_id):
        """component_id로 추적 중인 TUI 진행 라인을 마감 이벤트로 확정한다."""
        if not component_id:
            return False
        console = getattr(self, "console", None)
        progress_lines = getattr(console, "_progress_lines", None)
        buffer = getattr(console, "_buffer", None)
        if not isinstance(progress_lines, dict) or buffer is None:
            return False

        index = progress_lines.get(component_id)
        if not isinstance(index, int) or not (0 <= index < len(buffer)):
            progress_lines.pop(component_id, None)
            return False

        entry = dict(buffer[index])
        entry.update({
            "msg": line,
            "is_status": bool(is_status),
            "is_error": bool(is_error),
            "component_id": component_id,
            "is_progress": False,
        })
        buffer[index] = entry
        progress_lines.pop(component_id, None)
        reflow = getattr(console, "reflow", None)
        if callable(reflow):
            reflow()
        return True

    # [v3.9.0] 로그 미러는 ui/log_mirror.py로 이전 — 아래 4종은 호환 바인딩.
    def _finalize_concise_progress(self, line, is_status, is_error, component_id):
        from chzzktube.ui import log_mirror as _lm

        return _lm.finalize_concise_progress(self, line, is_status, is_error, component_id)

    def _render_concise(self, event, is_status=False, is_error=False):
        from chzzktube.ui import log_mirror as _lm

        return _lm.render_concise(self, event, is_status, is_error)

    def _mirror_event_full(self, event, is_status=False):
        from chzzktube.ui import log_mirror as _lm

        return _lm.mirror_event_full(self, event, is_status)

    def _mirror_full_log(self, line, is_status=False, component_id: str = None):
        from chzzktube.ui import log_mirror as _lm

        return _lm.mirror_full_log(self, line, is_status, component_id)

    def append_concise_log(self, msg, is_status=False, is_error=False, fg_color=None):
        if isinstance(msg, LogEvent):
            msg.is_status = is_status
            msg.is_error = is_error
            raw_log.raw("ui", msg, to_tui=True)
        else:
            raw_log.raw("ui", msg, is_status=is_status, is_error=is_error, to_tui=True)

    def toggle_verbose_log(self):
        """F12 상세 로그 창 토글 — 정돈된 버퍼만 표시."""
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
                # [초천재의 무결점 렌더링] 지연 동기화 시에도 임의로 False를 박지 않고 상태 플래그를 정직하게 반영!
                is_stat = getattr(self, "_last_full_was_status", False)
                self.verbose_win.append(line, is_stat)
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

    # Qt-Pilot 수신 대기 시작
    try:
        from app_pilot_hook import QtPilotHook
        win._pilot_hook = QtPilotHook(win)
    except ImportError:
        pass

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
```

## File: chzzktube\ui\progress_bar.py

```python
"""ProgressBar — 시각적 다운로드 진행률 표시 (stdlib-only).

raw_log 버스에 진행률 이벤트(pct, bar_frac, speed)를 발행한다.
is_status=False로 히스토리에만 쌓이게 하여 TUI 상태 줄 덮어쓰기 방지.
"""
import time
from typing import Callable, Optional

class ProgressBar:
    """다운로드 진행률을 추적하고 raw_log에 시각적 진행 바를 발행한다.

    사용 예:
        bar = ProgressBar(component="yt-dlp", log_func=my_log_func)
        async with bar:
            # 다운로드 루프에서
            bar.update(downloaded, total)
        bar.finish("completed")
    """

    BAR_WIDTH = 10
    MIN_UPDATE_INTERVAL = 2.0
    MIN_PCT_DELTA = 5

    def __init__(
        self,
        component: str,
        log_func: Optional[Callable] = None,
        *,
        total: Optional[int] = None,
        label: str = "",
    ):
        self.component = component
        self.log_func = log_func
        self.total = total
        self.label = label or component
        self._start_time: Optional[float] = None
        self._last_update: float = 0
        self._last_downloaded: int = 0
        self._finished = False

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if not self._finished:
            self.finish("completed" if exc_type is None else "failed")
        return False

    def start(self):
        self._start_time = time.monotonic()
        self._last_update = 0
        self._last_downloaded = 0
        self._finished = False
        self._emit(0, 0.0, "starting", speed="")

    def update(self, downloaded: int, total: int):
        if self._finished:
            return

        now = time.monotonic()
        if self.total is None:
            self.total = total
        elif total != self.total:
            self.total = total

        # Rate limit: minimum time interval OR minimum percentage delta
        pct = 0
        if self.total and self.total > 0:
            pct = int(downloaded * 100 / self.total)

        if (now - self._last_update < self.MIN_UPDATE_INTERVAL and 
            pct - getattr(self, '_last_pct', 0) < self.MIN_PCT_DELTA and
            downloaded < self.total):
            return

        self._last_update = now
        self._last_pct = pct

        elapsed = now - self._start_time if self._start_time else 1.0
        speed_bps = downloaded / elapsed if elapsed > 0 else 0.0
        speed_str = self._format_speed(speed_bps)

        if self.total and self.total > 0:
            pct = int(downloaded * 100 / self.total)
            bar_frac = min(downloaded / self.total, 1.0)
        else:
            pct = 0
            bar_frac = 0.0

        # Minimal MSG for TUI: just "downloading"
        msg = "downloading"
        self._emit(pct, bar_frac, msg, speed=speed_str)

    def finish(self, status: str = "completed"):
        if self._finished:
            return
        self._finished = True

        if self.total and self.total > 0:
            pct = 100
            bar_frac = 1.0
        else:
            pct = 0
            bar_frac = 0.0

        elapsed = time.monotonic() - (self._start_time or time.monotonic())
        speed_bps = self.total / elapsed if self.total and elapsed > 0 else 0
        speed_str = self._format_speed(speed_bps)

        # Minimal MSG for TUI
        msg = status  # "completed" | "failed" | "verifying"
        # 완료 로그는 is_status=False (히스토리만, 상태 줄 덮어쓰기 방지)
        self._emit(pct, bar_frac, msg, speed=speed_str, status="OK", is_status=False)

    def _emit(self, pct: int, bar_frac: float, msg: str, speed: str = "", status: str = "RUN", is_status: bool = True):
        event = emit_progress(
            stage="DEPS",
            status=status,
            scope=self.component.upper(),
            msg=msg,
            speed=speed,
            pct=pct,
            bar_frac=bar_frac,
            is_status=is_status,  # 진행중=True(갱신형), 완료=False(히스토리만)
            is_error=False,
        )
        raw_log.raw("provisioning", event, to_tui=is_status, is_error=False)
        if self.log_func:
            self.log_func(event)

    @staticmethod
    def _format_speed(bps: float) -> str:
        if bps >= 1024 * 1024:
            return f"{bps / (1024 * 1024):.1f} MB/s"
        elif bps >= 1024:
            return f"{bps / 1024:.1f} KB/s"
        elif bps > 0:
            return f"{bps:.0f} B/s"
        return ""

    @staticmethod
    def _format_eta(seconds: float) -> str:
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            return f"{int(seconds // 60)}m {int(seconds % 60)}s"
        else:
            return f"{int(seconds // 3600)}h {int((seconds % 3600) // 60)}m"
import chzzktube.core.raw_log as raw_log
from chzzktube.core.log_emitter import emit_progress
class ProgressManager:
    """다중 ProgressBar를 관리하는 컨텍스트 매니저.

    여러 동시 다운로드의 진행 바를 각각 독립적으로 관리한다.
    """

    def __init__(self, log_func: Optional[Callable] = None):
        self.log_func = log_func
        self._bars: dict[str, ProgressBar] = {}

    def create(self, component: str, *, total: Optional[int] = None, label: str = "") -> ProgressBar:
        bar = ProgressBar(component, log_func=self.log_func, total=total, label=label)
        self._bars[component] = bar
        return bar

    def get(self, component: str) -> Optional[ProgressBar]:
        return self._bars.get(component)

    def remove(self, component: str):
        self._bars.pop(component, None)

    def finish_all(self, status: str = "completed"):
        for bar in self._bars.values():
            if not bar._finished:
                bar.finish(status)
        self._bars.clear()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.finish_all("completed" if exc_type is None else "failed")
        return False
```

## File: chzzktube\ui\theme.py

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

## File: chzzktube\ui\components\__init__.py

```python
"""UI 컴포넌트 패키지."""
from chzzktube.ui.components.action_bar import ActionBarWidget
from chzzktube.ui.components.header_bar import HeaderBarWidget

__all__ = ["ActionBarWidget", "HeaderBarWidget"]

```

## File: chzzktube\ui\components\action_bar.py

```python
"""URL 입력 및 동작 제어 위젯 (ActionBarWidget).

MainWindow Layer 2(URL 입력, 프롬프트, 디바운스 타이머, TXT 로드, ENTER/ESC 액션)를
단일 책임 위젯으로 캡슐화한다.
"""
import os
import re
from typing import Optional

from PySide6.QtCore import Qt, Signal, QTimer, QEvent
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QFileDialog,
    QWidget,
)

from chzzktube.ui import theme
from chzzktube.control.gate_state import AppState

_ANALYZE_DEBOUNCE_MS = 300
_BULK_INPUT_DELAY_MS = 600


def _create_tui_tag(text: str, tooltip: str, slot=None) -> QPushButton:
    """TUI 스타일 태그 버튼 생성 헬퍼."""
    b = QPushButton(text)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    if slot:
        b.clicked.connect(slot)
    b.setToolTip(tooltip)
    b.setProperty("class", "tui-tag")
    b.style().unpolish(b)
    b.style().polish(b)
    return b


def _create_tui_sep() -> QLabel:
    """힌트 버튼 사이 딤 '│' 구분자."""
    sep = QLabel("│")
    sep.setStyleSheet(
        f"color: {theme.FG_DIM}; border: none; background: transparent; padding: 0px;"
    )
    return sep


class ActionBarWidget(QGroupBox):
    """URL 입력, 디바운스 분석 트리거, 다운로드 및 취소 제어 바."""

    url_changed = Signal(str)
    analyze_triggered = Signal(str, bool)  # (url, is_bulk)
    download_requested = Signal()
    esc_requested = Signal()
    load_txt_requested = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__("", parent)
        self.setObjectName("input_group")
        self.setProperty("class", "tui-panel")
        self.style().unpolish(self)
        self.style().polish(self)

        self._last_input_len = 0
        self._analyze_timer = QTimer(self)
        self._analyze_timer.setSingleShot(True)
        self._analyze_timer.timeout.connect(self._on_debounce_timeout)

        self._setup_ui()

    def _setup_ui(self) -> None:
        ilay = QHBoxLayout(self)
        ilay.setContentsMargins(0, 0, 0, 0)
        ilay.setSpacing(6)

        # 프롬프트 `>` 기호
        self.prompt_label = QLabel(">")
        self.prompt_label.setStyleSheet(
            f"color: {theme.ACCENT}; font-weight: bold; border: none; background: transparent; padding: 0px;"
        )
        ilay.addWidget(self.prompt_label)

        # URL 입력창
        self.url_input = QLineEdit()
        self.url_input.setObjectName("url_input")
        self.url_input.setPlaceholderText("URL, playlist, or channel URL...")
        self.url_input.setClearButtonEnabled(False)
        self.url_input.installEventFilter(self)
        self.url_input.textChanged.connect(self._on_text_changed)
        self.url_input.setDragEnabled(True)
        self.url_input.acceptDrops()
        self.url_input.dropEvent = lambda e: self._on_url_drop(e.mimeData())
        self.url_input.returnPressed.connect(self.download_requested.emit)
        ilay.addWidget(self.url_input, 1)

        # 버튼들
        self.btn_txt = _create_tui_tag(
            "[ F4: Load .txt ]",
            "Load URL list from TXT (F4)",
            self._on_pick_txt,
        )
        ilay.addWidget(self.btn_txt)
        ilay.addWidget(_create_tui_sep())

        self.btn_esc = _create_tui_tag(
            "[ ESC: Clear ]",
            "Clear input (Esc) — abort when running",
            self.esc_requested.emit,
        )
        ilay.addWidget(self.btn_esc)
        ilay.addWidget(_create_tui_sep())

        self.btn_enter = _create_tui_tag(
            "[ ENTER: Start ]",
            "Start download (Enter)",
            self.download_requested.emit,
        )
        ilay.addWidget(self.btn_enter)

    def eventFilter(self, obj, event):
        if (
            obj is self.url_input
            and event.type() == QEvent.Type.KeyPress
            and event.key() == Qt.Key.Key_Escape
        ):
            self.esc_requested.emit()
            return True
        return super().eventFilter(obj, event)

    def text(self) -> str:
        return self.url_input.text()

    def setText(self, text: str) -> None:
        self.url_input.setText(text)

    def clear(self) -> None:
        self.url_input.clear()

    def _set_validation_style(self, status: Optional[str]) -> None:
        """입력값 유효성에 따른 시각적 피드백 (Soft Warning / Normal)."""
        if status == "invalid":
            self.url_input.setStyleSheet(f"border-bottom: 2px solid {theme.WARN};")
        elif status == "valid":
            self.url_input.setStyleSheet(f"border-bottom: 1px solid {theme.ACCENT};")
        else:
            self.url_input.setStyleSheet("")

    def _on_text_changed(self, text: str) -> None:
        clean = text.strip()
        self.url_changed.emit(clean)
        self._analyze_timer.stop()

        if not clean:
            self._last_input_len = 0
            self._set_validation_style(None)
            return

        prev_len = self._last_input_len
        self._last_input_len = len(clean)
        is_bulk = (len(clean) - prev_len) > 1

        is_url = bool(re.match(r"^(https?://|www\.)\S+", clean)) or clean.lower().endswith(".txt")
        is_partial = "://" in clean or bool(re.search(r"\S\.\S", clean))

        if is_url:
            self._set_validation_style("valid")
            delay = _BULK_INPUT_DELAY_MS if is_bulk else _ANALYZE_DEBOUNCE_MS
            self._analyze_timer.start(delay)
        elif is_partial:
            self._set_validation_style("partial")
            self._analyze_timer.start(_ANALYZE_DEBOUNCE_MS * 2)
        else:
            self._set_validation_style("invalid")
            self._analyze_timer.stop()

    def _on_debounce_timeout(self) -> None:
        text = self.url_input.text().strip()
        if text:
            self.analyze_triggered.emit(text, False)

    def _on_pick_txt(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select TXT File",
            "",
            "Text Files (*.txt);;All Files (*.*)",
        )
        if path:
            norm_path = os.path.normpath(path)
            self.url_input.setText(norm_path)
            self.load_txt_requested.emit(norm_path)

    def _on_url_drop(self, mime_data) -> None:
        """드래그앤드롭 이벤트 처리 (.txt 파일 또는 URL)."""
        if not mime_data.hasUrls():
            return
        for url in mime_data.urls():
            path = url.toLocalFile()
            if path.lower().endswith(".txt"):
                self.url_input.setText(os.path.normpath(path))
                self.load_txt_requested.emit(os.path.normpath(path))
                return
            remote = url.toString()
            if remote.startswith(("http://", "https://")):
                self.url_input.setText(remote)
                return

    def update_state(self, state: str, has_deps_error: bool = False) -> None:
        """상태 전이에 따라 버튼 라벨 및 활성화 상태 갱신."""
        is_idle_or_picking = state in (AppState.IDLE, AppState.PICKING, "IDLE", "PICKING")
        self.url_input.setEnabled(is_idle_or_picking)
        self.btn_txt.setEnabled(state in (AppState.IDLE, "IDLE"))

        # ESC 버튼 상태
        if state in (AppState.STARTUP, "STARTUP"):
            self.btn_esc.setEnabled(False)
            self.btn_esc.setText("[ ESC: Clear ]")
        elif state in (AppState.RUNNING, "RUNNING"):
            self.btn_esc.setEnabled(True)
            self.btn_esc.setText("[ ESC: Abort ]")
        elif state in (AppState.ANALYZING, AppState.PICKING, "ANALYZING", "PICKING"):
            self.btn_esc.setEnabled(True)
            self.btn_esc.setText("[ ESC: Cancel ]")
        else:
            self.btn_esc.setEnabled(True)
            self.btn_esc.setText("[ ESC: Clear ]")

        # ENTER 버튼 상태
        if state in (AppState.IDLE, "IDLE"):
            self.btn_enter.setEnabled(True)
            self.btn_enter.setText("[ ENTER: Start ]")
        elif state in (AppState.PICKING, "PICKING"):
            self.btn_enter.setEnabled(True)
            self.btn_enter.setText("[ ENTER: Select ]")
        elif state in (AppState.STARTUP, "STARTUP") and has_deps_error:
            self.btn_enter.setEnabled(True)
            self.btn_enter.setText("[ ENTER: Retry Setup ]")
        else:
            self.btn_enter.setEnabled(False)
            self.btn_enter.setText("[ ENTER: Start ]")

```

## File: chzzktube\ui\components\header_bar.py

```python
"""상단 경로, 설정, 로그 제어 위젯 (HeaderBarWidget).

MainWindow Layer 1을 단일 책임 위젯으로 분리하고 Qt Signal을 통해 느슨하게 결합한다.
"""
import os
from typing import Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFileDialog,
    QSizePolicy,
    QWidget,
)

from chzzktube.ui import theme
from chzzktube.core.utils import _open_windows_explorer


def _create_tui_tag(text: str, tooltip: str, slot=None) -> QPushButton:
    """TUI 스타일 태그 버튼 생성 헬퍼."""
    b = QPushButton(text)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    if slot:
        b.clicked.connect(slot)
    b.setToolTip(tooltip)
    b.setProperty("class", "tui-tag")
    b.style().unpolish(b)
    b.style().polish(b)
    return b


class HeaderBarWidget(QGroupBox):
    """다운로드 경로 표시 및 제어, 전체 로그/설정 버튼 그룹."""

    path_changed = Signal(str)
    change_folder_requested = Signal()
    open_folder_requested = Signal()
    toggle_log_requested = Signal()
    open_settings_requested = Signal()

    def __init__(self, cfg: Optional[dict] = None, parent: Optional[QWidget] = None):
        super().__init__("", parent)
        self.cfg = cfg if cfg is not None else {}
        self.setObjectName("header_group")
        self.setProperty("class", "tui-panel")
        self.style().unpolish(self)
        self.style().polish(self)

        self._setup_ui()

    def _setup_ui(self) -> None:
        hlay = QHBoxLayout(self)
        hlay.setContentsMargins(0, 0, 0, 0)
        hlay.setSpacing(6)

        self.path_label = QLabel()
        self.path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.path_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.update_path(self.cfg.get("download_path", ""))
        hlay.addWidget(self.path_label, 1)

        self.btn_change = _create_tui_tag(
            "[ F1: Change ]",
            "Change download folder (F1)",
            self._on_change_clicked,
        )
        self.btn_open = _create_tui_tag(
            "[ F2: Open ]",
            "Open download folder (F2)",
            self._on_open_clicked,
        )
        hlay.addWidget(self.btn_change)
        hlay.addWidget(self.btn_open)

        # v_line: Change/Open과 Full Log/Settings 그룹 사이 시각 구분
        self.v_line = QLabel("\u2502")
        self.v_line.setProperty("class", "tui-sep")
        hlay.addWidget(self.v_line)

        self.btn_full_log = _create_tui_tag(
            "[ F12: Full Log ]",
            "Toggle full log window (F12)",
            self.toggle_log_requested.emit,
        )
        self.btn_settings = _create_tui_tag(
            "[ F3: Settings ]",
            "Open settings (F3)",
            self.open_settings_requested.emit,
        )
        hlay.addWidget(self.btn_full_log)
        hlay.addWidget(self.btn_settings)

    def update_path(self, path: str) -> None:
        """다운로드 경로 라벨 업데이트."""
        normalized = os.path.normpath(path) if path else ""
        self.path_label.setText(
            f"<span style='color:{theme.ACCENT}; font-weight:bold;'>Path</span> {normalized}"
        )
        self.path_label.setToolTip(normalized)

    def _on_change_clicked(self) -> None:
        """폴더 변경 다이얼로그 호출 후 시그널 발행."""
        current_path = self.cfg.get("download_path", "")
        folder = QFileDialog.getExistingDirectory(
            self, "Select Download Folder", current_path
        )
        if folder:
            norm_folder = os.path.normpath(folder)
            self.cfg["download_path"] = norm_folder
            self.update_path(norm_folder)
            self.path_changed.emit(norm_folder)
            self.change_folder_requested.emit()

    def _on_open_clicked(self) -> None:
        """다운로드 폴더 열기."""
        current_path = self.cfg.get("download_path", "")
        if current_path:
            _open_windows_explorer(current_path)
        self.open_folder_requested.emit()

```

## File: chzzktube\workers\__init__.py

```python

```

## File: chzzktube\workers\analyze_worker.py

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

## File: chzzktube\workers\downloader.py

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

## File: chzzktube\workers\update_worker.py

```python
### update_worker.py - DEPS 체크/자동 업그레이드 워커
"""시작 시퀀스의 의존성 확인·수급을 담당하는 백그라운드 워커 (UpdateWorker).

- _do_check : updater.check_deps() 결과를 DEPS 이벤트로(TUI 5줄), CLI 원문을
  raw 문자열로(F12) 버스 단일 경유 전송. stale 패키지는 check_done(list)으로 반환.
- _do_upgrade: ProvisioningManager를 통해 yt-dlp/ffmpeg/node/bgutil 일괄 수급.
  각 수급의 실제 진행 여부를 _had_action 판별해 '요약 결론' 1줄만 남긴다.
- [분리] dialogs.py에서 추출 — 대화상자 컬렉션과 워커의 수명·계층이 다르다.
- [시그널 계약] check_done(list) → main._on_update_check_done,
  upgrade_done(bool,str) → StartupCoordinator.report_upgrade.
- [v3.3.0] 로그는 raw 버스(raw_log.raw) 단일 경유 — line/full 시그널 폐기.
"""
import traceback

import chzzktube.infra.updater as updater
import chzzktube.core.raw_log as raw_log
from chzzktube.core.log_event import LogEvent
from PySide6.QtCore import QThread, Signal
from chzzktube.core.log_emitter import emit_component, emit_error_standard

# CLI 원문 캡처 대상 — (label, args). _do_check에서 updater.cli_raw로 실행된다.
_RAW_VERSION_CMDS = (
    ("ytdlp", ("--version",)),
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
                self._do_upgrade()
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
            scope_map = {"ytdlp": "YTDL", "ffmpeg": "FFMP", "node": "NODE", "pot": "POT", "bgutil": "BGUT"}
            raw_log.raw("deps", emit_component("DEPS", status, scope_map.get(label, label), ver), to_tui=True)
        for label, args in _RAW_VERSION_CMDS:
            cmdline, out = updater.cli_raw(label, *args)
            if cmdline and out:
                raw_log.log_f12_cli(cmdline, out)
        if self.check_updates:
            for label, pypi_name, cur, latest in updater.outdated_packages(channel=self.channel):
                stale.append((label, pypi_name, cur, latest))
                raw_log.raw("pypi", f"[stale] {label} {cur} -> {latest}")
        else:
            raw_log.raw("pypi", "pypi update check: disabled (auto_update_check=off)")
        self.deps_failed.emit([label for label, status, _ in results if status == "FAIL"])
        self.check_done.emit(stale)

    def _provision_cb(self, msg, is_status=False, is_error=False,
                      component_id=None, is_progress=False):
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
        if component_id is not None:
            event.component_id = component_id
        if is_progress:
            event.is_progress = True

        component_id = getattr(event, "component_id", component_id)
        is_progress = bool(getattr(event, "is_progress", is_progress))

        # [게이트 개방] OK와 DONE 상태를 버리지 않고 TUI로 반드시 통과
        show = bool(
            event.is_status
            or event.is_error
            or is_progress
            or event.status in ("OK", "DONE", "FAIL", "WARN", "ABORT")
        )
        self._tick(event)
        raw_log.raw(
            "deps", event, to_tui=show,
            component_id=component_id, is_progress=is_progress,
        )

    @staticmethod
    def _had_action(tui_line):
        from chzzktube.core.log_event import safe_log_msg
        text = safe_log_msg(tui_line)
        verb = ("downloading", "fetching", "installing", "extracting",
                "reinstalling", "reconfiguring", "brew install")
        return any(v in text.lower() for v in verb)

    def _tick(self, tui_line):
        if self._had_action(tui_line):
            self.work_tick.emit()

    def _do_upgrade(self):
        import asyncio
        from chzzktube.infra.provisioning import ProvisioningManager

        # ProvisioningManager 단일 파이프라인으로 ytdlp, ffmpeg, node, bgutil 4개 컴포넌트 일괄 병렬 수급
        mgr = ProvisioningManager(log_func=lambda evt, **kwargs: self._provision_cb(
            evt,
            is_status=kwargs.get("is_status", getattr(evt, "is_status", False)),
            is_error=kwargs.get("is_error", getattr(evt, "is_error", False)),
            component_id=kwargs.get("component_id", getattr(evt, "component_id", None)),
            is_progress=kwargs.get("is_progress", getattr(evt, "is_progress", False)),
        ))

        try:
            # [대역폭 수호] stale_only=True로 이미 정상인 의존성의 불필요한 재수급 차단
            results = asyncio.run(mgr.ensure_all(stale_only=True, channel=self.channel))
        except Exception as e:
            import traceback
            raw_log.raw("deps", f"provisioning error: {e}\n{traceback.format_exc()}", is_error=True)
            self.upgrade_done.emit(False, f"provisioning error: {e}")
            return

        ok = [r for r in results if r.success]
        failed = [r for r in results if not r.success]

        if ok:
            raw_log.raw("deps", f"{len(ok)} provisioned components ready", to_tui=False)
        if failed:
            for r in failed:
                raw_log.raw("deps", emit_error_standard("DEPS", r.component.upper(), r.error or "unknown", "check logs (F12)"), to_tui=True)

        ok_overall = (len(failed) == 0) and (len(ok) > 0 or len(results) == 0)
        summary = f"{len(ok)} ok, {len(failed)} failed" if failed else f"{len(ok)} components provisioned"
        self.upgrade_done.emit(ok_overall, summary)
```
