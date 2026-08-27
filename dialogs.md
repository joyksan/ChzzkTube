### 팝업 다이얼로그 모음
import os
import sys

import updater
from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ui_components import CustomComboBox
import theme

try:
    import winsound
except ImportError:
    winsound = None

def show_info_message(parent, title, text, detail=None, is_error=False):
    msg_box = QMessageBox(parent)
    msg_box.setIcon(QMessageBox.Icon.NoIcon)
    msg_box.setWindowTitle(title)
    # Prepend monochrome icon
    prefix = "▲  " if is_error else "✓  "
    msg_box.setText(prefix + text)
    if detail:
        msg_box.setDetailedText(detail)

    msg_box.setStyleSheet(theme.MSGBOX_QSS)
    msg_box.addButton(
        "확인" if not is_error else "닫기", QMessageBox.ButtonRole.AcceptRole
    )

    # Programmatic text alignment centering for success / left alignment for error
    label = msg_box.findChild(QLabel)
    if label:
        if is_error:
            label.setAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )
        else:
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)

    msg_box.exec()

class ExitConfirmDialog(QDialog):
    def __init__(self, parent=None, is_running=False):
        super().__init__(parent)
        self.is_running = is_running
        self.setWindowTitle("ChzzkTube")
        self.setFixedSize(360, 130)
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint
        )

        vbox = QVBoxLayout(self)
        vbox.setSpacing(15)
        vbox.setContentsMargins(20, 20, 20, 20)

        # 1. 상태별 문구 직관화 (따옴표 제거 및 명확한 의도 전달)
        if self.is_running:
            msg = "⚠️ 현재 다운로드가 진행 중입니다.\n진행 중인 작업을 중단하고 프로그램을 종료하시겠습니까?"
        else:
            msg = "정말 프로그램을 종료하시겠습니까?"

        lbl = QLabel(msg)
        lbl.setWordWrap(True)
        lbl.setStyleSheet("font-size: 12px; color: #e3e3e3; line-height: 1.4;")
        vbox.addWidget(lbl)

        btn_box = QHBoxLayout()
        btn_box.setSpacing(10)

        btn_exit = QPushButton("종료")
        btn_exit.setStyleSheet(theme.BTN_EXIT_DANGER_QSS)
        btn_exit.clicked.connect(lambda: self.done(1))

        btn_cancel = QPushButton("취소")
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
        self.setFixedSize(300, 380)
        self.setStyleSheet(theme.DIALOG_BG_QSS)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(8)

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

        for text, b_type in buttons:
            btn = QPushButton(text)
            btn.setStyleSheet(theme.BTN_GRID_QSS)
            btn.clicked.connect(lambda checked, t=b_type: self.on_select(t))
            layout.addWidget(btn)

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
        else:
            if b_type in ["chrome", "edge", "whale", "chromium", "brave", "vivaldi"]:
                try:
                    import yt_dlp.cookies
                    yt_dlp.cookies.extract_cookies_from_browser(b_type)
                except Exception as ex:
                    show_info_message(
                        self,
                        "오류",
                        f"브라우저({b_type}) 쿠키를 불러오는 데 실패했습니다.\n\n해당 브라우저가 실행 중이거나\n보안 정책(권한 거부)으로 인해 접근할 수 없습니다.",
                        detail=str(ex),
                        is_error=True,
                    )
                    return

            self.selected_type = b_type
            self.selected_path = ""
            self.accept()

class ActionCountdownDialog(QDialog):
    def __init__(self, action_type, parent=None):
        super().__init__(parent)
        self.action_type = action_type
        self.remaining_seconds = 60
        action_names = {
            "sleep": "절전 모드 진입",
            "shutdown": "PC 자동 종료",
            "exit_app": "프로그램 종료",
        }
        self.action_name = action_names.get(action_type, "설정된 작업")

        self.setWindowTitle("작업 완료 후 동작 안내")
        self.setFixedSize(380, 160)
        self.setStyleSheet("background-color: #121212; color: #ffffff;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        self.lbl_msg = QLabel(
            f"다운로드가 완료되었습니다.\n<b>{self.remaining_seconds}초</b> 후 [<b>{self.action_name}</b>]이(가) 실행됩니다."
        )
        self.lbl_msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_msg.setStyleSheet("font-size: 13px; color: #e0e0e0;")
        layout.addWidget(self.lbl_msg)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.btn_now = QPushButton("지금 실행")
        self.btn_now.setStyleSheet(
            "QPushButton { background-color: #c62828; color: white; font-weight: bold; padding: 6px; border-radius: 6px; border: none; } QPushButton:hover { background-color: #e53935; } QPushButton:pressed { background-color: #b71c1c; }"
        )
        self.btn_now.clicked.connect(self.execute_now)

        self.btn_cancel = QPushButton("취소")
        self.btn_cancel.setStyleSheet(
            "QPushButton { background-color: #2b2b2b; color: #e3e3e3; border: 1px solid #3d3d3d; font-weight: bold; padding: 6px; border-radius: 6px; } QPushButton:hover { background-color: #353535; border-color: #4a4a4a; }"
        )
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
                f"다운로드가 완료되었습니다.\n<b>{self.remaining_seconds}초</b> 후 [<b>{self.action_name}</b>]이(가) 실행됩니다."
            )

    def execute_now(self):
        self.timer.stop()
        self.accept()

    def cancel_action(self):
        self.timer.stop()
        self.reject()

class CookieViewerDialog(QDialog):
    def __init__(self, title_text, content_text, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title_text)
        self.setFixedSize(650, 500)
        self.setStyleSheet(theme.DIALOG_BG_QSS)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        self.te_content = QTextEdit(self)
        self.te_content.setReadOnly(True)
        self.te_content.setPlainText(content_text)
        self.te_content.setStyleSheet(theme.TE_CONTENT_QSS)
        layout.addWidget(self.te_content)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        btn_close = QPushButton("닫기")
        btn_close.setFixedWidth(90)
        btn_close.setStyleSheet(theme.BTN_CLOSE_QSS)
        btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)

class UpdateWorker(QThread):
    """구성요소(yt-dlp / streamlink / bgutil) 확인·업데이트 워커 — UI 비블로킹용.
    시그널 계약:
        line(str)               : 진행 로그 한 줄 (메인 간결 로그로 중계)
        check_done(list)        : 버전 확인 완료 — 업데이트 있는 목록 [(pkg, cur, latest)]
        upgrade_done(bool, str) : 업데이트 완료 — (성공 여부, 요약)
    """

    line = pyqtSignal(str)
    check_done = pyqtSignal(list)
    upgrade_done = pyqtSignal(bool, str)

    def __init__(self, parent=None, upgrade=False):
        super().__init__(parent)
        self.upgrade = upgrade

    def run(self):
        if self.upgrade:
            self._do_upgrade()
        else:
            self._do_check()

    def _do_check(self):
        stale = []
        for pkg in updater.PACKAGES:
            cur = updater.installed_version(pkg)
            latest = updater.latest_version(pkg)
            if not latest:
                self.line.emit(f"[?] {pkg} 버전 확인 실패")
                continue
            if not cur:
                # 미설치 감지 시 자동 설치 대상으로 스케줄링
                stale.append((pkg, "미설치", latest))
                self.line.emit(f"[~] {pkg} 미설치 감지 → 백그라운드 자동 설치를 시작합니다")
            elif updater.is_outdated(cur, latest):
                stale.append((pkg, cur, latest))
                self.line.emit(f"[~] {pkg} {cur} → {latest} 업데이트 있음")
            else:
                self.line.emit(f"[v] {pkg} {cur} 최신 버전입니다.")
        self.check_done.emit(stale)

    def _do_upgrade(self):
        code, tail = updater.upgrade_packages(updater.PACKAGES)
        # 들여쓰기 없이 그대로 중계
        for l in tail.splitlines():
            if l.strip():
                self.line.emit(l.strip())
        ok = code == 0
        summary = (
            "완료 — 적용에는 앱 재시작이 필요합니다."
            if ok
            else f"실패 (exit code {code})"
        )
        self.upgrade_done.emit(ok, summary)

class SettingsDialog(QDialog):
    def __init__(self, parent=None, is_running=False):
        super().__init__(parent)
        self.parent_win = parent
        self.cfg = parent.cfg
        self.is_running = is_running
        self._loading = True  # 초기 값 주입 중에는 저장 스킵
        self.setWindowTitle("설정")
        self.setFixedSize(480, 640)
        self.setStyleSheet("QDialog { background-color: #121212; color: #ffffff; }")
        self.init_ui()
        self.load_settings()
        self._loading = False

    def closeEvent(self, event):
        event.accept()

    def init_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(theme.SETTINGS_SCROLL_QSS)
        body = QWidget()
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        layout = QVBoxLayout(body)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 18, 20, 18)

        def make_combo(options, width):
            cb = CustomComboBox()
            cb.setFixedWidth(width)
            for k, v in options:
                cb.addItem(v, k)
            return cb

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("포맷 컨테이너"))
        row1.addStretch()
        self.cb_container = make_combo(
            [
                ("mkv", "mkv (일반 비디오 / 자막 완벽 호환)"),
                ("mp4", "mp4 (모바일 및 범용 플레이어 최적화)"),
                ("webm", "webm (웹 업로드 및 고효율 압축 최적화)"),
            ],
            250,
        )
        self.cb_container.currentIndexChanged.connect(
            lambda: self._apply_change("container", self.cb_container.currentData())
        )
        row1.addWidget(self.cb_container)
        layout.addLayout(row1)

        cookie_box = QFrame()
        cookie_box.setObjectName("cookie_box")
        cookie_box.setStyleSheet(
            "QFrame#cookie_box { border: 1px solid #3d3d3d; border-radius: 6px; background-color: #1e1e1e; }"
        )
        cookie_layout = QVBoxLayout(cookie_box)
        cookie_layout.setContentsMargins(12, 10, 12, 10)
        cookie_layout.setSpacing(8)

        cookie_lbl = QLabel("🔒\ufe0e 쿠키 설정 (연령제한/멤버십)")
        cookie_lbl.setStyleSheet(theme.DLG_SECTION_TITLE_QSS)
        cookie_layout.addWidget(cookie_lbl)

        self.lbl_cookie_status = QLabel(self._cookie_status_text())
        self.lbl_cookie_status.setStyleSheet(theme.DLG_STATUS_QSS)
        cookie_layout.addWidget(self.lbl_cookie_status)

        c_hlay = QHBoxLayout()
        c_hlay.setSpacing(8)
        self.cookie_buttons = []
        for text, func in [
            ("보기...", self.view_cookie),
            ("불러오기...", self.load_cookie),
            ("초기화", self.reset_cookie),
        ]:
            btn = self._ghost_btn(text, func)
            self.cookie_buttons.append(btn)
            c_hlay.addWidget(btn, 1)
        cookie_layout.addLayout(c_hlay)

        yt_hlay = QHBoxLayout()
        yt_hlay.setSpacing(8)
        yt_hlay.addWidget(QLabel("유튜브 클라이언트"))
        yt_hlay.addStretch()
        self.cb_yt_client = make_combo(
            [
                ("auto", "자동 (기본)"),
                ("tv", "tv (성인제한 우회 시 권장)"),
                ("web_safari", "web_safari (세션 무효화 시)"),
                ("tv_simply", "tv_simply"),
                ("mweb", "mweb"),
            ],
            210,
        )
        self.cb_yt_client.currentIndexChanged.connect(
            lambda: self._apply_change(
                "yt_player_client", self.cb_yt_client.currentData()
            )
        )
        yt_hlay.addWidget(self.cb_yt_client)
        cookie_layout.addLayout(yt_hlay)
        layout.addWidget(cookie_box)

        opt_lbl = QLabel("다운로드 옵션")
        opt_lbl.setStyleSheet(theme.DLG_SECTION_TITLE_QSS)
        layout.addWidget(opt_lbl)

        self.chk_sub = QCheckBox()
        self.chk_audio = QCheckBox()
        self.chk_dedup = QCheckBox()
        self.chk_fast = QCheckBox()
        self.chk_auto_open = QCheckBox()
        self.chk_sound = QCheckBox()

        self.chk_sub.toggled.connect(
            lambda v: self._apply_change("embed_subtitles", v)
        )
        self.chk_audio.toggled.connect(self._on_audio_only_toggled)
        self.chk_dedup.toggled.connect(
            lambda v: self._apply_change("remove_duplicates", v)
        )
        self.chk_fast.toggled.connect(lambda v: self._apply_change("fast_download", v))
        self.chk_auto_open.toggled.connect(
            lambda v: self._apply_change("auto_open_folder", v)
        )
        self.chk_sound.toggled.connect(lambda v: self._apply_change("play_sound", v))

        chk_items = [
            (self.chk_sub, "한국어 자막 포함 (SRT 자동 변환 병합)"),
            (self.chk_audio, "음원만 추출 (MP3)"),
            (self.chk_dedup, "중복 URL 자동 제거"),
            (self.chk_fast, "고속 분할 다운로드 (5스레드 병렬)"),
            (self.chk_auto_open, "완료 시 폴더 열기"),
            (self.chk_sound, "완료 알림음 재생"),
        ]

        chk_style = """
            QCheckBox {
                background: transparent;
                border: none;
                outline: none;
            }
            QCheckBox::indicator:unchecked {
                width: 14px;
                height: 14px;
                border: 1.5px solid #888888;
                border-radius: 3px;
                background-color: #1e1e1e;
                image: none;
            }
            QCheckBox[custom_hover="true"]::indicator:unchecked {
                width: 14px;
                height: 14px;
                border: 1.5px solid #d4d4d4;
                border-radius: 3px;
                background-color: #d4d4d4;
                image: none;
            }
            QCheckBox::indicator:checked {
                width: 14px;
                height: 14px;
                border: 1.5px solid #d4d4d4;
                border-radius: 3px;
                background-color: #d4d4d4;
                image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='14' height='14' viewBox='0 0 24 24' fill='none' stroke='%231e1e1e' stroke-width='3.5' stroke-linecap='round' stroke-linejoin='round'><polyline points='20 6 9 17 4 12'/></svg>");
            }
            QCheckBox[custom_hover="true"]::indicator:checked {
                width: 14px;
                height: 14px;
                border: 1.5px solid #ffffff;
                border-radius: 3px;
                background-color: #ffffff;
                image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='14' height='14' viewBox='0 0 24 24' fill='none' stroke='%231e1e1e' stroke-width='3.5' stroke-linecap='round' stroke-linejoin='round'><polyline points='20 6 9 17 4 12'/></svg>");
            }
        """

        def update_chk_style(c):
            c.style().unpolish(c)
            c.style().polish(c)

        for chk, text in chk_items:
            chk.setStyleSheet(chk_style)
            chk.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            chk.setProperty("custom_hover", False)
            chk.setProperty("suppress_hover", False)

            lbl = QLabel(text)
            lbl.setStyleSheet(
                "color: #d4d4d4; background: transparent; font-size: 12px;"
            )
            lbl.setCursor(Qt.CursorShape.PointingHandCursor)
            lbl.mousePressEvent = lambda event, c=chk: (
                c.toggle() if c.isEnabled() else None
            )

            chk.toggled.connect(
                lambda checked, c=chk: (
                    (
                        c.setProperty("suppress_hover", True),
                        c.setProperty("custom_hover", False),
                        update_chk_style(c),
                    )
                    if not checked
                    else None
                )
            )

            row_widget = QFrame()
            row_widget.setStyleSheet(
                "QFrame { background: transparent; border: none; }"
            )
            row_chk = QHBoxLayout(row_widget)
            row_chk.setSpacing(8)
            row_chk.setContentsMargins(0, 2, 0, 2)
            row_chk.addWidget(chk)
            row_chk.addWidget(lbl)
            row_chk.addStretch()

            def on_enter(e, c=chk):
                if not c.property("suppress_hover"):
                    c.setProperty("custom_hover", True)
                    update_chk_style(c)

            def on_leave(e, c=chk):
                c.setProperty("suppress_hover", False)
                c.setProperty("custom_hover", False)
                update_chk_style(c)

            row_widget.enterEvent = on_enter
            row_widget.leaveEvent = on_leave

            layout.addWidget(row_widget)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("작업 완료 후 동작"))
        row2.addStretch()
        self.cb_completion = make_combo(
            [
                ("none", "사용 안 함"),
                ("sleep", "절전 모드 진입"),
                ("shutdown", "PC 자동 종료"),
                ("exit_app", "프로그램 종료"),
            ],
            250,
        )
        self.cb_completion.currentIndexChanged.connect(
            lambda: self._apply_change(
                "completion_action", self.cb_completion.currentData()
            )
        )
        row2.addWidget(self.cb_completion)
        layout.addLayout(row2)

        format_layout = QHBoxLayout()
        format_layout.addWidget(QLabel("파일명 형식"))
        format_layout.addStretch()
        self.cb_prefix = make_combo(
            [
                ("none", "(없음)"),
                ("uploader", "[채널명]"),
                ("date_dash_uploader", "YYYY-MM-DD [채널명]"),
                ("date_compact_uploader", "YYYYMMDD [채널명]"),
                ("date_dash", "YYYY-MM-DD"),
                ("date_compact", "YYYYMMDD"),
            ],
            140,
        )
        self.cb_prefix.currentIndexChanged.connect(
            lambda: self._apply_change("filename_prefix", self.cb_prefix.currentData())
        )
        format_layout.addWidget(self.cb_prefix)

        lbl_title = QLabel("제목")
        lbl_title.setFixedWidth(45)
        lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_title.setStyleSheet(
            "font-weight: bold; background: transparent; border: none;"
        )
        format_layout.addWidget(lbl_title)

        self.cb_suffix = make_combo(
            [
                ("id_res_fps", "[ID] [해상도] [fps]"),
                ("id_res", "[ID] [해상도]"),
                ("id", "[ID]"),
            ],
            130,
        )
        self.cb_suffix.currentIndexChanged.connect(
            lambda: self._apply_change("filename_suffix", self.cb_suffix.currentData())
        )
        format_layout.addWidget(self.cb_suffix)
        layout.addLayout(format_layout)

        self.lbl_filename_preview = QLabel("미리보기  :  동영상제목.mp4")
        self.lbl_filename_preview.setStyleSheet(
            "color: #64b5f6; font-size: 11px; padding-left: 2px;"
        )
        layout.addWidget(self.lbl_filename_preview)

        self.cb_prefix.currentIndexChanged.connect(self.update_filename_preview)
        self.cb_suffix.currentIndexChanged.connect(self.update_filename_preview)
        self.cb_container.currentIndexChanged.connect(self.update_filename_preview)
        self.update_filename_preview()

        layout.addStretch()

    def update_filename_preview(self):
        import datetime
        today = datetime.datetime.now()
        date_dash = today.strftime("%Y-%m-%d")
        date_compact = today.strftime("%Y%m%d")

        prefix_map = {
            "none": "",
            "uploader": "[채널명] ",
            "date_dash_uploader": f"{date_dash} [채널명] ",
            "date_compact_uploader": f"{date_compact} [채널명] ",
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
        ext = self.cb_container.currentData()
        preview_str = f"미리보기  :  {p_text}동영상제목{s_text}.{ext}"
        self.lbl_filename_preview.setText(preview_str)

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

        self.chk_sub.setChecked(self.cfg.get("embed_subtitles", False))
        self.chk_audio.setChecked(self.cfg.get("audio_only", False))
        self.chk_dedup.setChecked(self.cfg.get("remove_duplicates", True))
        self.chk_fast.setChecked(self.cfg.get("fast_download", True))
        self.chk_auto_open.setChecked(self.cfg.get("auto_open_folder", True))
        self.chk_sound.setChecked(self.cfg.get("play_sound", True))

    def view_cookie(self):
        cookie_src = self.cfg.get("browser_cookie", "none")
        content = "로드된 쿠키가 없습니다."
        if cookie_src == "cookie_file" and os.path.exists(
            self.cfg.get("cookie_file_path", "")
        ):
            try:
                with open(self.cfg["cookie_file_path"], "r", encoding="utf-8") as f:
                    content = f.read(5000) + (
                        "\n... (생략)"
                        if os.path.getsize(self.cfg["cookie_file_path"]) > 5000
                        else ""
                    )
            except Exception as ex:
                content = f"파일 읽기 오류: {ex}"
        elif cookie_src not in ["none", "auto"]:
            try:
                from cookies import get_browser_cookies
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
            except Exception as ex:
                content = f"쿠키 조회 중 오류 발생: {ex}"
        viewer = CookieViewerDialog("쿠키 뷰어 (상세)", content, self)
        viewer.exec()

    def load_cookie(self):
        dlg = CookieSelectDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.cfg["browser_cookie"] = dlg.selected_type
            self.cfg["cookie_file_path"] = dlg.selected_path
            self.parent_win.save_cfg()
            self._refresh_cookie_status()
            show_info_message(
                self, "성공", f"쿠키 설정이 완료되었습니다.\n({dlg.selected_type})"
            )

    def reset_cookie(self):
        self.cfg["browser_cookie"] = "none"
        self.cfg["cookie_file_path"] = ""
        self.parent_win.save_cfg()
        self._refresh_cookie_status()
        show_info_message(self, "초기화", "쿠키가 초기화되었습니다.")

    def _ghost_btn(self, text, handler):
        btn = QPushButton(text)
        btn.setEnabled(not self.is_running)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedHeight(28)
        btn.setStyleSheet(theme.DLG_GHOST_BTN_QSS)
        btn.clicked.connect(handler)
        return btn

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
        self.parent_win.save_cfg()

    def _on_audio_only_toggled(self, on):
        self._apply_change("audio_only", on)
        self.parent_win.update_ui_state()
