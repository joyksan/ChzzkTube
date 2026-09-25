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
