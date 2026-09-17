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


class CookieSelectDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.selected_type = None
        self.selected_path = ""
        self.setWindowTitle("쿠키 불러오기...")
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
        content = "로드된 쿠키가 없습니다."
        if cookie_src == "cookie_file" and os.path.exists(self.cfg.get("cookie_file_path", "")):
            try:
                with open(self.cfg["cookie_file_path"], "r", encoding="utf-8") as f:
                    file_size = os.path.getsize(self.cfg["cookie_file_path"])
                    content = f.read(5000) + ("\n... (생략)" if file_size > 5000 else "")
            except Exception as ex:  # noqa: BLE001
                content = f"파일 읽기 오류: {ex}"
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
                    content = f"[{cookie_src}] 브라우저 추출 전체 쿠키 목록:\n\n" + "\n".join(lines)
                else:
                    content = f"[{cookie_src}] 브라우저에서 쿠키를 가져오지 못했습니다. (브라우저 실행 중 또는 권한 문제)"
            except Exception as ex:  # noqa: BLE001
                content = f"쿠키 조회 중 오류 발생: {ex}"

        viewer = CookieViewerDialog("쿠키 뷰어 (상세)", content, self)
        viewer.exec()

    def load_cookie(self):
        dlg = CookieSelectDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.cfg["browser_cookie"] = dlg.selected_type
            self.cfg["cookie_file_path"] = dlg.selected_path
            self.save_cfg()
            self._refresh_cookie_status()
            # [교정] QMessageBox 대신 TUI 규격 확인창 — View/OK 2버튼.
            # View 선택 시 확인창이 닫힌 뒤 쿠키 뷰어를 팝업한다.
            names = {"cookie_file": "Cookies.txt 파일"}
            src_name = names.get(dlg.selected_type, dlg.selected_type)
            notice = TuiNoticeDialog(
                self,
                title="ChzzkTube",
                text=f"✓ 쿠키 설정이 완료되었습니다.\n({src_name})",
                alt_label="View",
            )
            if notice.exec() == TuiNoticeDialog.RESULT_ALT:
                self.view_cookie()

    def reset_cookie(self):
        self.cfg["browser_cookie"] = "none"
        self.cfg["cookie_file_path"] = ""
        self.save_cfg()
        self._refresh_cookie_status()
        show_info_message(self, "초기화", "쿠키가 초기화되었습니다.")

    def _cookie_status_text(self):
        src = self.cfg.get("browser_cookie", "none")
        names = {
            "none": "사용 안 함",
            "auto": "자동 (브라우저 탐색)",
            "cookie_file": "Cookies.txt 파일",
        }
        label = names.get(src, f"브라우저 직접 추출 ({src})")
        if src == "cookie_file" and self.cfg.get("cookie_file_path"):
            label += f" — {os.path.basename(self.cfg['cookie_file_path'])}"
        return f"현재: {label}"

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
