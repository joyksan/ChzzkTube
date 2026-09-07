##### 팝업 다이얼로그 모음
import os
import updater
from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
import theme
import log_console
from log_console import emit_component

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
        "OK" if not is_error else "Close", QMessageBox.ButtonRole.AcceptRole
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
            msg = "⚠️ A download is in progress.\nStop and exit ChzzkTube?"
        else:
            msg = "Exit ChzzkTube?"

        lbl = QLabel(msg)
        lbl.setWordWrap(True)
        lbl.setStyleSheet("font-size: 12px; color: #e3e3e3; line-height: 1.4;")
        vbox.addWidget(lbl)

        btn_box = QHBoxLayout()
        btn_box.setSpacing(10)

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
                        "Error",
                        f"Failed to read browser ({b_type}) cookies.\n\nThe browser may be running, or\nsecurity policy (permission denied) blocks access.",
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
            "sleep": "sleep",
            "shutdown": "PC shutdown",
            "exit_app": "exit",
        }
        self.action_name = action_names.get(action_type, "unknown action")
        self.setWindowTitle("Post-Download Action")
        self.setFixedSize(380, 160)
        self.setStyleSheet("background-color: #121212; color: #ffffff;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        self.lbl_msg = QLabel(
            f"Download complete.\n<b>{self.remaining_seconds}s</b> until [<b>{self.action_name}</b>] runs."
        )
        self.lbl_msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_msg.setStyleSheet("font-size: 13px; color: #e0e0e0;")
        layout.addWidget(self.lbl_msg)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.btn_now = QPushButton("Run Now")
        self.btn_now.setStyleSheet(
            "QPushButton { background-color: #c62828; color: white; font-weight: bold; padding: 6px; border-radius: 6px; border: none; } QPushButton:hover { background-color: #e53935; } QPushButton:pressed { background-color: #b71c1c; }"
        )
        self.btn_now.clicked.connect(self.execute_now)

        self.btn_cancel = QPushButton("Cancel")
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
                f"Download complete.\n<b>{self.remaining_seconds}s</b> until [<b>{self.action_name}</b>] runs."
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

        btn_close = QPushButton("Close")
        btn_close.setFixedWidth(90)
        btn_close.setStyleSheet(theme.BTN_CLOSE_QSS)
        btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)


# [raw 상세 로그] DEPS 확인 시 실제 CLI를 실행해 셸에서 친 것과 동일한 원문을
# F12 상세 로그에 기록한다. yt-dlp --version → '2026.08.19', streamlink
# --version → 'streamlink 8.5.0' 식의 터미널 출력 그대로.
_RAW_VERSION_CMDS = (
    ("ytdlp", ("--version",)),
    ("streamlink", ("--version",)),
    ("ffmpeg", ("-version",)),
    ("node", ("--version",)),
    ("npm", ("--version",)),
)


class UpdateWorker(QThread):
    # line = (msg, is_status, is_error) — POTProviderWorker와 동일 시그널 계약.
    # 진행률/상태 로그는 is_status=True로 emit해야 ConciseLogConsole이 같은 줄을
    # 덮어쓴다(갱신형). raw 상세(pip/다운로드 출력)는 full → F12(상세 로그)로만 흘러간다.
    line = Signal(str, bool, bool)
    full = Signal(str, bool)  # (raw 원문, is_status) — True면 F12에서 마지막 줄 갱신(진행률 덮어쓰기)

    check_done = Signal(list)
    upgrade_done = Signal(bool, str)

    def __init__(self, parent=None, upgrade=False, stale_updates=None, channel='stable', check_updates=True):
        super().__init__(parent)
        self.upgrade = upgrade
        self.stale_updates = stale_updates or []
        self.channel = channel
        self.check_updates = check_updates

    def run(self):
        try:
            if self.upgrade:
                self._do_upgrade(self.stale_updates)
            else:
                self._do_check()
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.full.emit(f"UpdateWorker crash: {traceback.format_exc()}", False)
            self.line.emit(emit_component("SYS", "FAIL", "deps", f"worker crash: {e}"), False, True)
            self.check_done.emit([])

    def _do_check(self):
        """버전 확인 — 메인 콘솔(deps 상태 5줄) + F12(CLI 원문).

        [min profile] 메인 콘솔에는 상태 라인 5개 — fzf/lazygit 톤은 공백이 곧 정보.
        F12에는 실제 CLI를 실행해 셸에서 칠 때 보이는 원문 출력 그대로를
        적재한다. TUI 상태와 CLI 원문을 겹쳐 띄우지 않는다(교체 원칙).
        """
        stale = []
        for label, status, ver in updater.check_deps():
            self.line.emit(emit_component("DEPS", status, label, ver), False, False)
        # [raw] 실제 CLI 실행 — 터미널에서 직접 친 것과 동일한 원문을 F12에 기록
        for label, args in _RAW_VERSION_CMDS:
            cmdline, out = updater.cli_raw(label, *args)
            if cmdline and out:
                self.full.emit(f"$ {cmdline}", False)
                for line in out.splitlines():
                    self.full.emit(line, False)
        # 수동 체크용 stale 생성 (outdated_packages) — 사용자 채널 반영.
        # auto_update_check off 면 PyPI 폴링 스킵 (stale 미생성 → upgrade 워커는 수급만)
        if self.check_updates:
            for label, pypi_name, cur, latest in updater.outdated_packages(channel=self.channel):
                stale.append((label, pypi_name, cur, latest))
                self.full.emit(f"[stale] {label} {cur} → {latest}", False)
        else:
            self.full.emit("pypi update check: disabled (auto_update_check=off)", False)
        self.check_done.emit(stale)

    def _provision_cb(self, tui_line, is_status=False, is_error=False):
        """설치/수급 진행 로그 — 메인은 TUI(갱신형), F12는 raw 원문.

        [2분기 원칙] F12에는 TUI 규격을 그대로 베끼지 않는다. 지금 줄의
        마지막 메시지부만 떼어 원문으로 적재 — is_status=True면 F12에서도
        마지막 줄을 덮어써서 설치 진행률이 한 줄로 갱신된다(사용자 요구).
        """
        raw = tui_line.rsplit("│", 1)[-1].strip() if "│" in tui_line else tui_line.strip()
        if raw:
            self.full.emit(raw, bool(is_status))
        status = tui_line.split("│")[1].strip() if "│" in tui_line else ""
        if is_error or status in ("FAIL", "WARN", "ABORT"):
            self.line.emit(tui_line, is_status, is_error)
        elif is_status:
            self.line.emit(tui_line, True, False)


    @staticmethod
    def _had_action(tui_line):
        """실제 수급 작업(다운로드/설치/추출 등)이 있었는지 — RUN 진행 동사 판별."""
        verb = ("downloading", "fetching", "installing", "extracting",
                "reinstalling", "reconfiguring", "brew install")
        return any(v in tui_line.lower() for v in verb)

    def _do_upgrade(self, stale_updates=None):
        from log_console import emit_component
        import components
        import pot_provider
        ok_overall = True
        summaries = []

        # 1. PyPI packages (yt-dlp, streamlink) — stale로 확인된 것만
        stale_updates = stale_updates or []
        if stale_updates:
            for _label, name, cur, latest in stale_updates:
                self.full.emit(f"[stale] {name}: {cur} → {latest}", False)
            pypi_names = [p[1] for p in stale_updates]
            code, tail = updater.upgrade_packages(pypi_names, channel=self.channel)
            for l in tail.splitlines():
                if l.strip():
                    # raw 출력(pip/다운로드)은 상세 로그(F12)로만 — TUI 콘솔 오염 방지
                    self.full.emit(l.strip(), False)
            if code != 0:
                ok_overall = False
                summaries.append(f"pypi ({', '.join(pypi_names)}) failed")
            else:
                summaries.append(f"{', '.join(pypi_names)} updated")
        else:
            self.full.emit("pypi: all up-to-date", False)

        # 2. ffmpeg auto-provisioning — 실제 수급이 없으면 간결 무표기
        ffmpeg_acted = [False]
        def _ffmpeg_cb(msg, is_status=False, is_error=False, *a):
            if self._had_action(msg):
                ffmpeg_acted[0] = True
            self._provision_cb(msg, is_status, is_error)

        ff_err = components.ensure_ffmpeg(_ffmpeg_cb)
        if ff_err:
            ok_overall = False
            summaries.append(f"ffmpeg: {ff_err}")
            self.line.emit(emit_component("DEPS", "FAIL", "ffmpeg", ff_err), False, True)
        elif ffmpeg_acted[0]:
            summaries.append("ffmpeg provisioned")
        else:
            self.full.emit("ffmpeg: ok (no action needed)", False)

        # 3. node auto-provisioning (POT server runtime)
        node_acted = [False]
        def _node_cb(msg, is_status=True, is_error=False):
            if self._had_action(msg):
                node_acted[0] = True
            # pot_provider log_func 계약 (msg, is_status, is_error)
            self._provision_cb(emit_component("DEPS", "RUN", "node", msg), is_status, is_error)

        try:
            node_ok = pot_provider.ensure_node_runtime(_node_cb)
            if node_ok:
                if node_acted[0]:
                    summaries.append("node provisioned")
                else:
                    self.full.emit("node: ok (no action needed)", False)
            else:
                ok_overall = False
                summaries.append("node setup failed")
                self.line.emit(emit_component("DEPS", "FAIL", "node", "setup failed"), False, True)
        except Exception as e:
            ok_overall = False
            summaries.append(f"node: {e}")
            self.line.emit(emit_component("DEPS", "FAIL", "node", str(e)), False, True)

        summary = "; ".join(summaries) if summaries else ""
        self.upgrade_done.emit(ok_overall, summary)


class SettingsDialog(QDialog):
    def __init__(self, parent=None, is_running=False):
        super().__init__(parent)
        self.parent_win = parent
        self.cfg = parent.cfg
        self.is_running = is_running
        self._loading = True  # 초기 값 주입 중에는 저장 스킵
        self.setWindowTitle("설정")
        self.setFixedSize(480, 640)
        self.setStyleSheet( "QDialog { background-color: #0d0d0d; color: #d4d4d4; }" "QLabel { color: #cccccc; font-size: 11px; }" "QLabel[role=\"key\"] { color: #4ec9b0; font-weight: bold; }" "QCheckBox { color: #d4d4d4; spacing: 6px; }" "QCheckBox::indicator { width: 14px; height: 14px; border: 1px solid #2a2a2a; background: #161616; border-radius: 2px; }" "QCheckBox::indicator:checked { background: #4ec9b0; border-color: #4ec9b0; }" "QPushButton { background: #161616; color: #d4d4d4; border: 1px solid #2a2a2a; padding: 4px 12px; font-size: 11px; }" "QPushButton:hover { border-color: #4ec9b0; color: #4ec9b0; }" "QPushButton:disabled { color: #555555; border-color: #1a1a1a; }" "QComboBox { background: #161616; color: #d4d4d4; border: 1px solid #2a2a2a; padding: 4px 8px; font-size: 11px; }" "QComboBox:hover { border-color: #4ec9b0; }" "QComboBox::drop-down { border: none; width: 18px; }" "QComboBox QAbstractItemView { background: #161616; color: #d4d4d4; border: 1px solid #2a2a2a; selection-background-color: #264f78; outline: none; }" )
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
        layout.setSpacing(10)
        layout.setContentsMargins(16, 14, 16, 14)
        # TUI 패널 일체화 — 다크 콘솔 + 민트 액센트

        def make_combo(options, width):
            cb = CustomComboBox()
            cb.setFixedWidth(width)
            for k, v in options:
                cb.addItem(v, k)
            return cb

        row1 = QHBoxLayout()
        _sec1 = QGroupBox("Container")
        _sec1.setProperty("class", "tui-panel")
        _sec1.setLayout(row1)
        row1.addWidget(QLabel("Container"))
        row1.addStretch()
        self.cb_container = make_combo(
            [
                ("mkv", "mkv (general / full subtitle support)"),
                ("mp4", "mp4 (mobile & universal player)"),
                ("webm", "webm (web upload & efficient)"),
            ],
            250,
        )
        self.cb_container.currentIndexChanged.connect(
            lambda: self._apply_change("container", self.cb_container.currentData())
        )
        row1.addWidget(self.cb_container)
        layout.addWidget(_sec1)

        cookie_box = QFrame()
        cookie_box.setObjectName("cookie_section")
        cookie_box.setProperty("class", "tui-panel")
        try:
            cookie_box.setTitle("Cookie")
        except Exception:
            pass
        cookie_box.setObjectName("cookie_box")
        cookie_box.setStyleSheet(
            "QFrame#cookie_box { border: 1px solid #3d3d3d; border-radius: 6px; background-color: #1e1e1e; }"
        )
        cookie_layout = QVBoxLayout(cookie_box)
        cookie_layout.setContentsMargins(12, 10, 12, 10)
        cookie_layout.setSpacing(8)

        cookie_lbl = QLabel("Cookie (age / membership)")
        cookie_lbl.setStyleSheet(theme.DLG_SECTION_TITLE_QSS)
        cookie_layout.addWidget(cookie_lbl)

        self.lbl_cookie_status = QLabel(self._cookie_status_text())
        self.lbl_cookie_status.setStyleSheet(theme.DLG_STATUS_QSS)
        cookie_layout.addWidget(self.lbl_cookie_status)

        c_hlay = QHBoxLayout()
        c_hlay.setSpacing(8)
        self.cookie_buttons = []
        for text, func in [
            ("View...", self.view_cookie),
            ("Load...", self.load_cookie),
            ("Reset", self.reset_cookie),
        ]:
            btn = self._ghost_btn(text, func)
            self.cookie_buttons.append(btn)
            c_hlay.addWidget(btn, 1)
        cookie_layout.addLayout(c_hlay)

        yt_hlay = QHBoxLayout()
        yt_hlay.setSpacing(8)
        yt_hlay.addWidget(QLabel("YouTube Client"))
        yt_hlay.addStretch()
        self.cb_yt_client = make_combo(
            [
                ("auto", "auto (default)"),
                ("tv", "tv (age-gated recommended)"),
                ("web_safari", "web_safari (session invalid)"),
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

        opt_lbl = QLabel("Download Options")
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
            (self.chk_sub, "Embed subtitles (SRT auto-convert + merge)"),
            (self.chk_audio, "Audio only (MP3)"),
            (self.chk_dedup, "Auto-remove duplicate URLs"),
            (self.chk_fast, "Fast segmented download (5 threads)"),
            (self.chk_auto_open, "Open folder on finish"),
            (self.chk_sound, "Play completion sound"),
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
        _sec2 = QGroupBox("Video Quality")
        _sec2.setProperty("class", "tui-panel")
        _sec2.setLayout(row2)
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
        layout.addWidget(_sec2)

        row3 = QHBoxLayout()
        _sec3 = QGroupBox("Format Picker")
        _sec3.setProperty("class", "tui-panel")
        _sec3.setLayout(row3)
        row3.addWidget(QLabel("해상도 제한"))
        row3.addStretch()
        self.cb_max_res = make_combo(
            [
                ("none", "(무제한)"),
                ("2160", "4K (2160p)"),
                ("1440", "2K (1440p)"),
                ("1080", "1080p"),
                ("720", "720p"),
                ("480", "480p"),
                ("360", "360p"),
            ],
            140,
        )
        self.cb_max_res.currentIndexChanged.connect(
            lambda: self._apply_change("max_video_res", self.cb_max_res.currentData())
        )
        row3.addWidget(self.cb_max_res)
        row3.addSpacing(12)
        self.chk_pick = QCheckBox("포맷 직접 고르기 (최고 품질 off)")
        self.chk_pick.toggled.connect(lambda on: self._apply_change("pick_format", on))
        row3.addWidget(self.chk_pick)
        layout.addWidget(_sec3)

        format_layout = QHBoxLayout()
        _sec_filename = QGroupBox("Filename")
        _sec_filename.setProperty("class", "tui-panel")
        _flay = QVBoxLayout(_sec_filename)
        _flay.setContentsMargins(10, 6, 10, 6)
        _flay.setSpacing(6)
        _flay.addWidget(QLabel("파일명 형식"))
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
        _flay.addLayout(format_layout)

        self.lbl_filename_preview = QLabel("미리보기  :  동영상제목.mp4")
        self.lbl_filename_preview.setStyleSheet(
            "color: #64b5f6; font-size: 11px; padding-left: 2px;"
        )
        _flay.addWidget(self.lbl_filename_preview)
        layout.addWidget(_sec_filename)

        self.cb_prefix.currentIndexChanged.connect(self.update_filename_preview)
        self.cb_suffix.currentIndexChanged.connect(self.update_filename_preview)
        self.cb_container.currentIndexChanged.connect(self.update_filename_preview)
        self.update_filename_preview()

        # ── Update Channel 섹션 ──
        update_row = QHBoxLayout()
        _sec_update = QGroupBox("Update Channel")
        _sec_update.setProperty("class", "tui-panel")
        _sec_update.setLayout(update_row)
        update_row.addWidget(QLabel("채널"))
        update_row.addStretch()
        self.cb_update_channel = make_combo(
            [
                ("stable", "Stable (안정)"),
                ("nightly", "Nightly (최신 우회)"),
            ],
            140,
        )
        self.cb_update_channel.currentIndexChanged.connect(
            lambda: self._apply_change("update_channel", self.cb_update_channel.currentData())
        )
        update_row.addWidget(self.cb_update_channel)
        update_row.addSpacing(12)
        self.chk_auto_update = QCheckBox("시작 시 자동 확인")
        self.chk_auto_update.toggled.connect(lambda on: self._apply_change("auto_update_check", on))
        update_row.addWidget(self.chk_auto_update)
        layout.addWidget(_sec_update)

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
        set_combo(self.cb_update_channel, self.cfg.get("update_channel", "stable"))
        set_combo(self.cb_max_res, self.cfg.get("max_video_res", "none"))
        self.chk_pick.setChecked(self.cfg.get("pick_format", False))

        self.chk_sub.setChecked(self.cfg.get("embed_subtitles", False))
        self.chk_audio.setChecked(self.cfg.get("audio_only", False))
        self.chk_dedup.setChecked(self.cfg.get("remove_duplicates", True))
        self.chk_fast.setChecked(self.cfg.get("fast_download", True))
        self.chk_auto_open.setChecked(self.cfg.get("auto_open_folder", True))
        self.chk_sound.setChecked(self.cfg.get("play_sound", True))
        self.chk_auto_update.setChecked(self.cfg.get("auto_update_check", True))

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
class VerboseLogWindow(QDialog):
    """상세(Full Detailed) 로그 전용 서브 윈도우 — 메인 뷰에서 상세 로그 탭을
    분리해 접근한다(F12). MainWindow가 외부로 유출하는 상세 로그를 그대로
    미러링하며, 항상 하단(최신)을 팔로우한다."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Full Log (F12)")
        self.resize(760, 480)

        self.te = QTextEdit(self)
        self.te.setReadOnly(True)
        self.te.setStyleSheet(theme.TE_CONTENT_QSS)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(self.te)

        btn_row = QHBoxLayout()
        self.lbl_info = QLabel("")
        self.lbl_info.setStyleSheet(theme.DLG_STATUS_QSS)
        btn_close = QPushButton("Close")
        btn_close.setStyleSheet(theme.BTN_NEUTRAL_QSS)
        btn_close.clicked.connect(self.close)
        btn_row.addWidget(self.lbl_info)
        btn_row.addStretch(1)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

    def append(self, msg, is_status=False):
        """Mirror raw text — timestamps pre-applied by _mirror_full_log."""
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
        """Replace all content at once (initial display)."""
        self.te.setPlainText(text)
        self.lbl_info.setText(f"buffer — {self.te.document().blockCount()} lines")
