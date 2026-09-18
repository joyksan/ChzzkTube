"""실제 창 표시, 첫 워치독 폴링, 로그 렌더링 회귀 검증."""
from unittest.mock import patch
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from chzzktube.core.log_emitter import emit_event
from chzzktube.ui.main_window import MainWindow


def test_window_opens_and_renders_log():
    app = QApplication.instance() or QApplication([])
    with patch.object(MainWindow, "_start_update_check", lambda self: None):
        win = MainWindow()
        try:
            win.show()
            QTest.qWait(1100)
            assert win.isVisible() and win.centralWidget() is not None
            win._render_concise(emit_event("SYS", "OK", "MAIN", "startup probe"))
            assert "startup probe" in win.te_concise.toPlainText()
        finally:
            win.hide()
            win.deleteLater()
            app.processEvents()
