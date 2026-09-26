"""상단 경로, 설정, 로그 제어 위젯 (HeaderBarWidget).

MainWindow Layer 1을 단일 책임 위젯으로 분리하고 Qt Signal을 통해 느슨하게 결합한다.
"""
import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QWidget,
)

from chzzktube.core.utils import _open_windows_explorer
from chzzktube.ui import theme


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

    def __init__(self, cfg: dict | None = None, parent: QWidget | None = None):
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
