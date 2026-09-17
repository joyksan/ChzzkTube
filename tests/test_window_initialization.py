"""기동 초기화는 생성자에서 1회, 워치독 폴링은 기존 상태를 보존한다.

[배경] `_poll_watchdogs()`가 `init_ui()`, 폴백/게이트 QTimer 생성,
`QTimer.singleShot(500, _start_update_check)`, 재시도 상태 초기화를 함께
수행하고 있었다. 폴링은 1초 주기이므로 위젯·타이머가 매초 교체되고
업데이트 확인이 반복 예약되며 `_pot_retry_done`(URL당 1회 계약)이
날아간다. 초기화를 생성자로 옮기고 폴링은 판정만 남긴다.

GUI 검증은 자식 프로세스에서 수행한다 — 다른 테스트가 QCoreApplication을
선점하므로 같은 프로세스에서 QApplication을 만들 수 없다.
"""
import os
from pathlib import Path
import subprocess
import sys


_PROBE = '''
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from chzzktube.ui.main_window import MainWindow


class ProbeWindow(MainWindow):
    """실제 위젯을 만들되 기동 부수효과(업데이트 확인)만 계수한다."""

    init_calls = 0
    update_calls = 0

    def init_ui(self):
        ProbeWindow.init_calls += 1
        super().init_ui()

    def _start_update_check(self):
        ProbeWindow.update_calls += 1


app = QApplication([])
window = ProbeWindow()

assert ProbeWindow.init_calls == 1, ProbeWindow.init_calls
assert window._watchdog_poll_timer.isActive()
assert window._fallback_timer.isActive()
assert not window._gate_watchdog_timer.isActive()

widgets = (window.url_input, window._fallback_timer, window._gate_watchdog_timer)
window._pot_retry_done.add("retained-url")
window._pot_retry_pending = True
window._pot_retry_url = "retained-url"

for _ in range(3):
    window._poll_watchdogs()

assert ProbeWindow.init_calls == 1, ProbeWindow.init_calls
assert (window.url_input, window._fallback_timer, window._gate_watchdog_timer) == widgets
assert window._pot_retry_done == {"retained-url"}, window._pot_retry_done
assert window._pot_retry_pending is True
assert window._pot_retry_url == "retained-url"

QTimer.singleShot(700, app.quit)
app.exec()
assert ProbeWindow.update_calls == 1, ProbeWindow.update_calls

for timer in (
    window._watchdog_poll_timer,
    window._fallback_timer,
    window._gate_watchdog_timer,
):
    timer.stop()
print("initialization and polling contract verified")
'''


def test_polling_preserves_initialized_window():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-c", _PROBE],
        cwd=root,
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "initialization and polling contract verified" in result.stdout
