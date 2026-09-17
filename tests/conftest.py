"""Shared pytest setup: exactly one QApplication for the whole session.

Why this file exists
--------------------
Qt allows only one application object per process, and the class matters:
a bare ``QCoreApplication`` is NOT a GUI application.

``QApplication.instance()`` is inherited from ``QCoreApplication``, so it
returns whatever application already exists. A test module that created a
``QCoreApplication`` first therefore made later widget tests believe an
application was ready; constructing ``QTextEdit`` without a real
``QApplication`` aborts the interpreter (SIGABRT / EXC_BAD_ACCESS, see the
note in tests/test_log_console.py).

Creating the GUI application session-wide - before any test body runs -
removes the ordering dependency: widget tests reuse it, and Qt-only tests
that call ``QCoreApplication.instance() or QCoreApplication([])`` receive
it as well. Headless runs stay headless through QT_QPA_PLATFORM=offscreen.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402  (env must be set before Qt import)


@pytest.fixture(scope="session", autouse=True)
def qt_application():
    """세션 전체가 공유하는 QApplication (offscreen)."""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app
    app.processEvents()
