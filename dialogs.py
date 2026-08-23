# 팝업 다이얼로그 모음

import os
import json
import platform
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QFileDialog, QMessageBox, QCheckBox, QLineEdit, QFrame, QTextEdit
)
from PyQt6.QtCore import Qt, QTimer
from ui_components import CustomComboBox

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
        
    msg_box.setStyleSheet("""
        QMessageBox {
            background-color: #121212;
        }
        QLabel {
            color: #e3e3e3;
            font-size: 13px;
            font-family: 'Segoe UI', sans-serif;
            padding: 12px 20px;
        }
        QPushButton {
            background-color: #2b2b2b;
            color: #e3e3e3;
            border: 1px solid #3d3d3d;
            border-radius: 6px;
            padding: 6px 16px;
            font-weight: bold;
            min-width: 75px;
        }
        QPushButton:hover {
            background-color: #353535;
            border-color: #4a4a4a;
        }
        QPushButton:pressed {
            background-color: #1c1c1c;
        }
        QTextEdit {
            background-color: #0d0d0d;
            color: #d4d4d4;
            border: 1px solid #2d2d2d;
            border-radius: 6px;
            font-family: 'Consolas', monospace;
            font-size: 11px;
            padding: 5px;
        }
    """)
    msg_box.addButton("확인" if not is_error else "닫기", QMessageBox.ButtonRole.AcceptRole)
    
    # Programmatic text alignment centering for success / left alignment for error
    label = msg_box.findChild(QLabel)
    if label:
        if is_error:
            label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        else:
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            
    msg_box.exec()



class ExitConfirmDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        if winsound:
            try:
                winsound.PlaySound("SystemExclamation", winsound.SND_ALIAS | winsound.SND_ASYNC)
            except Exception:
                pass

        self.setWindowTitle("ChzzkTube")
        self.setFixedSize(320, 125)
        self.setStyleSheet("background-color: #121212; color: #ffffff; font-family: 'Segoe UI', sans-serif;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        msg_layout = QHBoxLayout()
        msg_layout.setSpacing(10)
        msg_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        icon_lbl = QLabel("⚠\uFE0E")
        icon_lbl.setStyleSheet("font-size: 20px; color: #888888; border: none; background: transparent;")
        msg_layout.addWidget(icon_lbl)

        text_lbl = QLabel("정말 종료하시겠습니까?")
        text_lbl.setStyleSheet("font-size: 13px; font-weight: bold; border: none; background: transparent;")
        msg_layout.addWidget(text_lbl)
        
        layout.addLayout(msg_layout)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        btn_save_exit = QPushButton("저장&&종료")
        btn_save_exit.setStyleSheet("QPushButton { background-color: #02b275; color: white; font-weight: bold; padding: 6px 12px; border-radius: 6px; border: none; } QPushButton:hover { background-color: #03cb85; } QPushButton:pressed { background-color: #018f5d; }")
        btn_save_exit.clicked.connect(lambda: self.done(1))

        btn_exit = QPushButton("종료")
        btn_exit.setStyleSheet("QPushButton { background-color: #2b2b2b; color: #e3e3e3; padding: 6px 16px; border-radius: 6px; border: 1px solid #3d3d3d; } QPushButton:hover { background-color: #353535; border-color: #4a4a4a; }")
        btn_exit.clicked.connect(lambda: self.done(2))

        btn_cancel = QPushButton("취소")
        btn_cancel.setStyleSheet("QPushButton { background-color: #2b2b2b; color: #e3e3e3; padding: 6px 16px; border-radius: 6px; border: 1px solid #3d3d3d; } QPushButton:hover { background-color: #353535; border-color: #4a4a4a; }")
        btn_cancel.clicked.connect(lambda: self.done(0))

        btn_layout.addWidget(btn_save_exit)
        btn_layout.addWidget(btn_exit)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)


class CookieSelectDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.selected_type = None
        self.selected_path = ""
        
        self.setWindowTitle("쿠키 불러오기...")
        self.setFixedSize(300, 380)
        self.setStyleSheet("background-color: #121212; color: #ffffff; font-family: 'Segoe UI', sans-serif;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(8)

        buttons = [
            ("Cookies.txt", "file"), ("Chrome", "chrome"), ("Firefox", "firefox"),
            ("Edge", "edge"), ("Opera", "opera"), ("Brave", "brave"),
            ("Vivaldi", "vivaldi"), ("Chromium", "chromium"), ("Whale", "whale")
        ]

        for text, b_type in buttons:
            btn = QPushButton(text)
            btn.setStyleSheet("QPushButton { background-color: #2b2b2b; color: #e3e3e3; border: 1px solid #3d3d3d; border-radius: 6px; padding: 8px; font-size: 12px; font-weight: bold; } QPushButton:hover { background-color: #353535; border-color: #4a4a4a; } QPushButton:pressed { background-color: #1c1c1c; }")
            btn.clicked.connect(lambda checked, t=b_type: self.on_select(t))
            layout.addWidget(btn)

    def on_select(self, b_type):
        if b_type == "file":
            path, _ = QFileDialog.getOpenFileName(self, "Netscape HTTP Cookie Files", "", "Text Files (*.txt);;All Files (*.*)")
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
                        self, "오류", 
                        f"브라우저({b_type}) 쿠키를 불러오는 데 실패했습니다.\n\n해당 브라우저가 실행 중이거나\n보안 정책(권한 거부)으로 인해 접근할 수 없습니다.", 
                        detail=str(ex), is_error=True
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
            "exit_app": "프로그램 종료"
        }
        self.action_name = action_names.get(action_type, "설정된 작업")

        self.setWindowTitle("작업 완료 후 동작 안내")
        self.setFixedSize(380, 160)
        self.setStyleSheet("background-color: #121212; color: #ffffff;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        self.lbl_msg = QLabel(f"다운로드가 완료되었습니다.\n<b>{self.remaining_seconds}초</b> 후 [<b>{self.action_name}</b>]이(가) 실행됩니다.")
        self.lbl_msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_msg.setStyleSheet("font-size: 13px; color: #e0e0e0;")
        layout.addWidget(self.lbl_msg)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.btn_now = QPushButton("지금 실행")
        self.btn_now.setStyleSheet("QPushButton { background-color: #c62828; color: white; font-weight: bold; padding: 6px; border-radius: 6px; border: none; } QPushButton:hover { background-color: #e53935; } QPushButton:pressed { background-color: #b71c1c; }")
        self.btn_now.clicked.connect(self.execute_now)

        self.btn_cancel = QPushButton("취소")
        self.btn_cancel.setStyleSheet("QPushButton { background-color: #2b2b2b; color: #e3e3e3; border: 1px solid #3d3d3d; font-weight: bold; padding: 6px; border-radius: 6px; } QPushButton:hover { background-color: #353535; border-color: #4a4a4a; }")
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
            self.lbl_msg.setText(f"다운로드가 완료되었습니다.\n<b>{self.remaining_seconds}초</b> 후 [<b>{self.action_name}</b>]이(가) 실행됩니다.")

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
        self.setStyleSheet("background-color: #121212; color: #ffffff; font-family: 'Segoe UI', sans-serif;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        self.te_content = QTextEdit(self)
        self.te_content.setReadOnly(True)
        self.te_content.setPlainText(content_text)
        self.te_content.setStyleSheet("""
            QTextEdit {
                background-color: #0d0d0d;
                color: #d4d4d4;
                border: 1px solid #2d2d2d;
                border-radius: 6px;
                font-family: 'Consolas', monospace;
                font-size: 11px;
                padding: 8px;
            }
        """)
        layout.addWidget(self.te_content)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        btn_close = QPushButton("닫기")
        btn_close.setFixedWidth(90)
        btn_close.setStyleSheet("""
            QPushButton {
                background-color: #2b2b2b; color: #e3e3e3; border: 1px solid #3d3d3d;
                border-radius: 6px; padding: 6px 16px; font-weight: bold;
            }
            QPushButton:hover { background-color: #353535; border-color: #4a4a4a; }
        """)
        btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)


class SettingsDialog(QDialog):
    def __init__(self, parent=None, is_running=False):
        super().__init__(parent)
        self.parent_win = parent
        self.cfg = json.loads(json.dumps(parent.cfg))
        self.is_running = is_running
        self.saved = False
        self.setWindowTitle("설정")
        self.setFixedSize(460, 550)
        self.setStyleSheet("QDialog { background-color: #121212; color: #ffffff; }")
        self.init_ui()
        self.load_settings()

    def closeEvent(self, event):
        if not self.is_running and not self.saved:
            self.accept_settings()
            return
        event.accept()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)
        
        def make_combo(options, width):
            cb = CustomComboBox()
            cb.setFixedWidth(width)
            cb.setEnabled(not self.is_running)
            for k, v in options: cb.addItem(v, k)
            return cb

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("포맷 컨테이너"))
        row1.addStretch()
        self.cb_container = make_combo([
            ("mkv", "mkv (일반 비디오 / 자막 완벽 호환)"),
            ("mp4", "mp4 (모바일 및 범용 플레이어 최적화)"),
            ("webm", "webm (웹 업로드 및 고효율 압축 최적화)")
        ], 250)
        row1.addWidget(self.cb_container)
        layout.addLayout(row1)

        cookie_box = QFrame()
        cookie_box.setObjectName("cookie_box")
        cookie_box.setStyleSheet("QFrame#cookie_box { border: 1px solid #3d3d3d; border-radius: 6px; background-color: #1e1e1e; }")
        cookie_layout = QVBoxLayout(cookie_box)
        cookie_layout.setContentsMargins(12, 10, 12, 10)
        cookie_layout.setSpacing(8)

        cookie_lbl = QLabel("🔒\uFE0E 쿠키 설정 (연령제한/멤버십)")
        cookie_lbl.setStyleSheet("font-weight: bold; font-size: 12px; border: none; background: transparent; font-family: 'MS Gothic', 'Segoe UI', sans-serif;")
        cookie_layout.addWidget(cookie_lbl)
        
        c_hlay = QHBoxLayout()
        c_hlay.setSpacing(8)
        self.cookie_buttons = []
        for text, func in [("보기...", self.view_cookie), ("불러오기...", self.load_cookie), ("초기화", self.reset_cookie)]:
            btn = QPushButton(text)
            btn.setEnabled(not self.is_running)
            btn.setStyleSheet("QPushButton { background-color: #2b2b2b; border: 1px solid #3d3d3d; padding: 4px 10px; border-radius: 6px; min-height: 22px; font-size: 11px; color: #e3e3e3; } QPushButton:hover { background-color: #353535; border-color: #4a4a4a; } QPushButton:disabled { background-color: #181818; color: #5a5a5a; border-color: #2d2d2d; }")
            btn.clicked.connect(func)
            c_hlay.addWidget(btn)
            self.cookie_buttons.append(btn)
        cookie_layout.addLayout(c_hlay)
        layout.addWidget(cookie_box)

        self.chk_sub = QCheckBox()
        self.chk_audio = QCheckBox()
        self.chk_dedup = QCheckBox()
        self.chk_fast = QCheckBox()
        self.chk_auto_open = QCheckBox()
        self.chk_sound = QCheckBox()

        chk_items = [
            (self.chk_sub, "한국어 자막 포함 (SRT 자동 변환 병합)"),
            (self.chk_audio, "음원만 추출 (MP3)"),
            (self.chk_dedup, "중복 URL 자동 제거"),
            (self.chk_fast, "고속 분할 다운로드 (5스레드 병렬)"),
            (self.chk_auto_open, "완료 시 폴더 열기"),
            (self.chk_sound, "완료 알림음 재생")
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
            chk.setEnabled(not self.is_running)
            chk.setStyleSheet(chk_style)
            chk.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            chk.setProperty("custom_hover", False)
            chk.setProperty("suppress_hover", False)

            lbl = QLabel(text)
            lbl.setStyleSheet("color: #d4d4d4; background: transparent; font-size: 12px;")
            lbl.setCursor(Qt.CursorShape.PointingHandCursor)
            lbl.mousePressEvent = lambda event, c=chk: c.toggle() if c.isEnabled() else None

            chk.toggled.connect(lambda checked, c=chk: (
                c.setProperty("suppress_hover", True),
                c.setProperty("custom_hover", False),
                update_chk_style(c)
            ) if not checked else None)

            row_widget = QFrame()
            row_widget.setStyleSheet("QFrame { background: transparent; border: none; }")
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
        self.cb_completion = make_combo([
            ("none", "사용 안 함"), ("sleep", "절전 모드 진입"),
            ("shutdown", "PC 자동 종료"), ("exit_app", "프로그램 종료")
        ], 250)
        row2.addWidget(self.cb_completion)
        layout.addLayout(row2)

        format_layout = QHBoxLayout()
        format_layout.addWidget(QLabel("파일명 형식"))
        format_layout.addStretch()
        self.cb_prefix = make_combo([
            ("none", "(없음)"), ("uploader", "[채널명]"),
            ("date_dash_uploader", "YYYY-MM-DD [채널명]"),
            ("date_compact_uploader", "YYYYMMDD [채널명]"), ("date_dash", "YYYY-MM-DD"),
            ("date_compact", "YYYYMMDD")
        ], 140)
        format_layout.addWidget(self.cb_prefix)
        
        lbl_title = QLabel("제목")
        lbl_title.setFixedWidth(45)
        lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_title.setStyleSheet("font-weight: bold; background: transparent; border: none;")
        format_layout.addWidget(lbl_title)
        
        self.cb_suffix = make_combo([
            ("id_res_fps", "[ID] [해상도] [fps]"), ("id_res", "[ID] [해상도]"), ("id", "[ID]")
        ], 130)
        format_layout.addWidget(self.cb_suffix)
        layout.addLayout(format_layout)

        self.lbl_filename_preview = QLabel("미리보기  :  동영상제목.mp4")
        self.lbl_filename_preview.setStyleSheet("color: #64b5f6; font-size: 11px; padding-left: 2px;")
        layout.addWidget(self.lbl_filename_preview)

        self.cb_prefix.currentIndexChanged.connect(self.update_filename_preview)
        self.cb_suffix.currentIndexChanged.connect(self.update_filename_preview)
        self.cb_container.currentIndexChanged.connect(self.update_filename_preview)
        self.update_filename_preview()

        layout.addStretch()
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        btn_cancel = QPushButton("취소")
        btn_cancel.setStyleSheet("QPushButton { background-color: #2b2b2b; color: #e3e3e3; border: 1px solid #3d3d3d; border-radius: 6px; padding: 6px 16px; font-weight: bold; } QPushButton:hover { background-color: #353535; border-color: #4a4a4a; }")
        btn_cancel.clicked.connect(self.reject)

        btn_save = QPushButton("완료")
        btn_save.setStyleSheet("QPushButton { background-color: #02b275; color: white; border: none; border-radius: 6px; padding: 6px 16px; font-weight: bold; } QPushButton:hover { background-color: #03cb85; } QPushButton:pressed { background-color: #018f5d; }")
        btn_save.clicked.connect(self.accept_settings)

        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_save)
        layout.addLayout(btn_layout)

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
            "date_compact": f"{date_compact} "
        }
        suffix_map = {
            "id_res_fps": " [PLCAxEuddBvAs] [1080p] [60fps]",
            "id_res": " [PLCAxEuddBvAs] [1080p]",
            "id": " [PLCAxEuddBvAs]"
        }
        p_text = prefix_map.get(self.cb_prefix.currentData(), "")
        s_text = suffix_map.get(self.cb_suffix.currentData(), "")
        ext = self.cb_container.currentData()
        preview_str = f"미리보기  :  {p_text}동영상제목{s_text}.{ext}"
        self.lbl_filename_preview.setText(preview_str)

    def load_settings(self):
        def set_combo(cb, val):
            idx = cb.findData(val)
            if idx >= 0: cb.setCurrentIndex(idx)
        
        set_combo(self.cb_container, self.cfg.get("container", "mkv"))
        set_combo(self.cb_completion, self.cfg.get("completion_action", "none"))
        set_combo(self.cb_prefix, self.cfg.get("filename_prefix", "none"))
        set_combo(self.cb_suffix, self.cfg.get("filename_suffix", "id"))
        
        self.chk_sub.setChecked(self.cfg.get("embed_subtitles", False))
        self.chk_audio.setChecked(self.cfg.get("audio_only", False))
        self.chk_dedup.setChecked(self.cfg.get("remove_duplicates", True))
        self.chk_fast.setChecked(self.cfg.get("fast_download", True))
        self.chk_auto_open.setChecked(self.cfg.get("auto_open_folder", True))
        self.chk_sound.setChecked(self.cfg.get("play_sound", True))

    def view_cookie(self):
        cookie_src = self.cfg.get("browser_cookie", "none")
        content = "로드된 쿠키가 없습니다."
        if cookie_src == "cookie_file" and os.path.exists(self.cfg.get("cookie_file_path", "")):
            try:
                with open(self.cfg["cookie_file_path"], 'r', encoding='utf-8') as f:
                    content = f.read(5000) + ("\n... (생략)" if os.path.getsize(self.cfg["cookie_file_path"]) > 5000 else "")
            except Exception as ex: content = f"파일 읽기 오류: {ex}"
        elif cookie_src not in ["none", "auto"]:
            try:
                from utils import get_browser_cookies
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
            show_info_message(self, "성공", f"쿠키 설정이 완료되었습니다.\n({dlg.selected_type})")

    def reset_cookie(self):
        self.cfg["browser_cookie"] = "none"
        self.cfg["cookie_file_path"] = ""
        self.parent_win.save_cfg()
        show_info_message(self, "초기화", "쿠키가 초기화되었습니다.")

    def accept_settings(self):
        if not self.is_running:
            self.saved = True
            self.cfg["container"] = self.cb_container.currentData()
            self.cfg["completion_action"] = self.cb_completion.currentData()
            self.cfg["filename_prefix"] = self.cb_prefix.currentData()
            self.cfg["filename_suffix"] = self.cb_suffix.currentData()
            self.cfg["embed_subtitles"] = self.chk_sub.isChecked()
            self.cfg["audio_only"] = self.chk_audio.isChecked()
            self.cfg["remove_duplicates"] = self.chk_dedup.isChecked()
            self.cfg["fast_download"] = self.chk_fast.isChecked()
            self.cfg["auto_open_folder"] = self.chk_auto_open.isChecked()
            self.cfg["play_sound"] = self.chk_sound.isChecked()
            
            self.parent_win.cfg.update(self.cfg)
            self.parent_win.save_cfg()
            self.parent_win.update_ui_state()
        self.accept()