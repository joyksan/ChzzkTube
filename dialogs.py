import os
import json
import platform
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QFileDialog, QMessageBox, QCheckBox, QLineEdit, QFrame
)
from PyQt6.QtCore import Qt, QTimer
from ui_components import CustomComboBox

try:
    import winsound
except ImportError:
    winsound = None

class ExitConfirmDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        if winsound:
            try:
                winsound.PlaySound("SystemExclamation", winsound.SND_ALIAS | winsound.SND_ASYNC)
            except Exception:
                pass

        self.setWindowTitle("ChzzkTube")
        self.setFixedSize(360, 155)
        self.setStyleSheet("background-color: #1e1e1e; color: #ffffff; font-family: 'Segoe UI', sans-serif;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        msg_layout = QHBoxLayout()
        msg_layout.setSpacing(15)
        
        icon_lbl = QLabel("⚠️")
        icon_lbl.setStyleSheet("font-size: 26px; border: none; background: transparent;")
        msg_layout.addWidget(icon_lbl, alignment=Qt.AlignmentFlag.AlignTop)

        text_lbl = QLabel("정말 종료하시겠습니까?")
        text_lbl.setStyleSheet("font-size: 13px; font-weight: bold; border: none; background: transparent;")
        msg_layout.addWidget(text_lbl, alignment=Qt.AlignmentFlag.AlignVCenter)
        
        layout.addLayout(msg_layout)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        btn_save_exit = QPushButton("저장 & 종료")
        btn_save_exit.setStyleSheet("QPushButton { background-color: #3b5998; color: white; font-weight: bold; padding: 6px 12px; border-radius: 4px; border: none; } QPushButton:hover { background-color: #4c6ef5; }")
        btn_save_exit.clicked.connect(lambda: self.done(1))

        btn_exit = QPushButton("종료")
        btn_exit.setStyleSheet("QPushButton { background-color: #333; color: #ddd; padding: 6px 16px; border-radius: 4px; border: 1px solid #444; } QPushButton:hover { background-color: #444; }")
        btn_exit.clicked.connect(lambda: self.done(2))

        btn_cancel = QPushButton("취소")
        btn_cancel.setStyleSheet("QPushButton { background-color: #333; color: #ddd; padding: 6px 16px; border-radius: 4px; border: 1px solid #444; } QPushButton:hover { background-color: #444; }")
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
        self.setStyleSheet("background-color: #1e1e1e; color: #ffffff; font-family: 'Segoe UI', sans-serif;")

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
            btn.setStyleSheet("QPushButton { background-color: #2b2b2b; color: #d4d4d4; border: 1px solid #3c3c3c; border-radius: 4px; padding: 8px; font-size: 12px; font-weight: bold; } QPushButton:hover { background-color: #383838; border-color: #555; }")
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
                    msg_box = QMessageBox(self)
                    msg_box.setIcon(QMessageBox.Icon.Critical)
                    msg_box.setWindowTitle("오류")
                    msg_box.setText(f"브라우저({b_type}) 쿠키를 불러오는 데 실패했습니다.\n\n해당 브라우저가 실행 중이거나 보안 정책(권한 거부)으로 인해 접근할 수 없습니다.")
                    msg_box.setDetailedText(str(ex))
                    
                    btn_close = msg_box.addButton("닫기", QMessageBox.ButtonRole.RejectRole)
                    msg_box.exec()
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
        self.setStyleSheet("background-color: #1e1e1e; color: #ffffff;")

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
        self.btn_now.setStyleSheet("background-color: #d32f2f; color: white; font-weight: bold; padding: 6px; border-radius: 4px;")
        self.btn_now.clicked.connect(self.execute_now)

        self.btn_cancel = QPushButton("취소")
        self.btn_cancel.setStyleSheet("background-color: #444; color: white; font-weight: bold; padding: 6px; border-radius: 4px;")
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


class SettingsDialog(QDialog):
    def __init__(self, parent=None, is_running=False):
        super().__init__(parent)
        self.parent_win = parent
        self.cfg = json.loads(json.dumps(parent.cfg))
        self.is_running = is_running
        self.saved = False
        self.setWindowTitle("설정")
        self.setFixedSize(460, 530)
        self.setStyleSheet("background-color: #1e1e1e; color: #ffffff;")
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
            cb.setStyleSheet("QComboBox { background-color: #1e1e1e; border: 1px solid #444; border-radius: 4px; padding: 0px 6px; font-size: 11px; min-height: 24px; max-height: 24px; } QComboBox:disabled { background-color: #161616; color: #555; border-color: #333; } QComboBox QAbstractItemView { background-color: #1e1e1e; color: #ffffff; selection-background-color: #1976d2; border: 1px solid #444; }")
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
        cookie_box.setStyleSheet("QFrame { border: 1px solid #444; border-radius: 6px; background-color: #242424; }")
        cookie_layout = QVBoxLayout(cookie_box)
        cookie_layout.setContentsMargins(12, 10, 12, 10)
        cookie_layout.setSpacing(8)

        cookie_lbl = QLabel("🍪 쿠키 설정 (연령제한/멤버십)")
        cookie_lbl.setStyleSheet("font-weight: bold; font-size: 12px; border: none; background: transparent;")
        cookie_layout.addWidget(cookie_lbl)
        
        c_hlay = QHBoxLayout()
        c_hlay.setSpacing(8)
        self.cookie_buttons = []
        for text, func in [("보기...", self.view_cookie), ("불러오기...", self.load_cookie), ("초기화", self.reset_cookie)]:
            btn = QPushButton(text)
            btn.setEnabled(not self.is_running)
            btn.setStyleSheet("QPushButton { background-color: #1e1e1e; border: 1px solid #444; padding: 0px; border-radius: 4px; min-height: 24px; max-height: 24px; font-size: 11px; } QPushButton:hover { background-color: #2a2a2a; } QPushButton:disabled { background-color: #161616; color: #555; border-color: #333; }")
            btn.clicked.connect(func)
            c_hlay.addWidget(btn)
            self.cookie_buttons.append(btn)
        cookie_layout.addLayout(c_hlay)
        layout.addWidget(cookie_box)

        self.chk_sub = QCheckBox("한국어 자막 포함 (SRT 자동 변환 병합)")
        self.chk_audio = QCheckBox("음원만 추출 (MP3)")
        self.chk_dedup = QCheckBox("중복 URL 자동 제거")
        self.chk_fast = QCheckBox("고속 분할 다운로드 (5스레드 병렬)")
        self.chk_auto_open = QCheckBox("완료 시 폴더 열기")
        self.chk_sound = QCheckBox("완료 알림음 재생")
        for chk in [self.chk_sub, self.chk_audio, self.chk_dedup, self.chk_fast, self.chk_auto_open, self.chk_sound]:
            chk.setEnabled(not self.is_running)
            layout.addWidget(chk)

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
        lbl_title.setStyleSheet("font-weight: bold;")
        format_layout.addWidget(lbl_title)
        
        self.cb_suffix = make_combo([
            ("id_res_fps", "[ID] [해상도] [fps]"), ("id_res", "[ID] [해상도]"), ("id", "[ID]")
        ], 130)
        format_layout.addWidget(self.cb_suffix)
        layout.addLayout(format_layout)

        self.lbl_filename_preview = QLabel("미리보기  :  동영상제목.mp4")
        self.lbl_filename_preview.setStyleSheet("color: #64b5f6; font-size: 11px; padding-left: 2px;")
        layout.addWidget(self.lbl_filename_preview)

        cut_layout = QHBoxLayout()
        self.chk_cut = QCheckBox("구간 추출 (Cut)")
        self.chk_cut.setEnabled(not self.is_running)
        cut_layout.addWidget(self.chk_cut)
        cut_layout.addStretch()
        
        line_edit_style = "QLineEdit { background-color: #2d2d2d; border: 1px solid #444; border-radius: 4px; font-size: 11px; padding: 0px 4px; margin: 0px; min-height: 24px; max-height: 24px; } QLineEdit:disabled { background-color: #1a1a1a; color: #555; border-color: #333; }"

        lbl_start = QLabel("시작")
        lbl_start.setStyleSheet("color: #aaa; font-size: 11px;")
        self.le_cut_start = QLineEdit()
        self.le_cut_start.setPlaceholderText("00:00:00")
        self.le_cut_start.setFixedSize(85, 24)
        self.le_cut_start.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.le_cut_start.setStyleSheet(line_edit_style)
        self.le_cut_start.setEnabled(not self.is_running)

        lbl_end = QLabel("종료")
        lbl_end.setStyleSheet("color: #aaa; font-size: 11px;")
        self.le_cut_end = QLineEdit()
        self.le_cut_end.setPlaceholderText("00:00:00")
        self.le_cut_end.setFixedSize(85, 24)
        self.le_cut_end.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.le_cut_end.setStyleSheet(line_edit_style)
        self.le_cut_end.setEnabled(not self.is_running)

        cut_layout.addWidget(lbl_start)
        cut_layout.addWidget(self.le_cut_start)
        cut_layout.addSpacing(6)
        cut_layout.addWidget(lbl_end)
        cut_layout.addWidget(self.le_cut_end)
        layout.addLayout(cut_layout)

        self.cb_prefix.currentIndexChanged.connect(self.update_filename_preview)
        self.cb_suffix.currentIndexChanged.connect(self.update_filename_preview)
        self.cb_container.currentIndexChanged.connect(self.update_filename_preview)
        self.update_filename_preview()

        layout.addStretch()
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        btn_cancel = QPushButton("변경 취소")
        btn_cancel.setStyleSheet("QPushButton { background-color: #333; color: #ddd; border: 1px solid #444; border-radius: 4px; padding: 6px 16px; font-weight: bold; } QPushButton:hover { background-color: #444; }")
        btn_cancel.clicked.connect(self.reject)

        btn_save = QPushButton("설정 완료")
        btn_save.setStyleSheet("background-color: #1976d2; border-radius: 4px; padding: 6px 16px; font-weight: bold;")
        btn_save.clicked.connect(self.accept_settings)

        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_save)
        layout.addLayout(btn_layout)

        self.chk_cut.toggled.connect(self.update_cut_state)

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
        
        self.chk_cut.setChecked(self.cfg.get("use_cut", False))
        self.le_cut_start.setText(self.cfg.get("cut_start", ""))
        self.le_cut_end.setText(self.cfg.get("cut_end", ""))
        self.update_cut_state()

    def update_cut_state(self):
        if self.is_running: return
        checked = self.chk_cut.isChecked()
        self.le_cut_start.setEnabled(checked)
        self.le_cut_end.setEnabled(checked)

    def update_filename_preview(self):
        prefix_map = {
            "none": "",
            "uploader": "[채널명] ",
            "date_dash_uploader": "2026-06-07 [채널명] ",
            "date_compact_uploader": "20260607 [채널명] ",
            "date_dash": "2026-06-07 ",
            "date_compact": "20260607 "
        }
        suffix_map = {
            "id_res_fps": " [abc1234] [1080p] [60fps]",
            "id_res": " [abc1234] [1080p]",
            "id": " [abc1234]"
        }
        p_text = prefix_map.get(self.cb_prefix.currentData(), "")
        s_text = suffix_map.get(self.cb_suffix.currentData(), "")
        ext = self.cb_container.currentData()
        preview_str = f"미리보기  :  {p_text}동영상제목{s_text}.{ext}"
        self.lbl_filename_preview.setText(preview_str)

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
            self.cfg["use_cut"] = self.chk_cut.isChecked()
            self.cfg["cut_start"] = self.le_cut_start.text().strip()
            self.cfg["cut_end"] = self.le_cut_end.text().strip()
            
            self.parent_win.cfg.update(self.cfg)
            self.parent_win.save_cfg()
            self.parent_win.update_ui_state()
        self.accept()

    def view_cookie(self):
        cookie_src = self.cfg.get("browser_cookie", "none")
        content = "로드된 쿠키가 없습니다."
        if cookie_src == "cookie_file" and os.path.exists(self.cfg.get("cookie_file_path", "")):
            try:
                with open(self.cfg["cookie_file_path"], 'r', encoding='utf-8') as f:
                    content = f.read(2000) + ("\n... (생략)" if os.path.getsize(self.cfg["cookie_file_path"]) > 2000 else "")
            except Exception as ex: content = f"파일 읽기 오류: {ex}"
        elif cookie_src not in ["none", "auto"]:
            content = f"[{cookie_src}] 브라우저의 쿠키를 사용 중입니다.\n\n보안상 전체 텍스트 표시는 생략됩니다."
        QMessageBox.information(self, "쿠키 뷰어", content)

    def load_cookie(self):
        dlg = CookieSelectDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.cfg["browser_cookie"] = dlg.selected_type
            self.cfg["cookie_file_path"] = dlg.selected_path
            self.parent_win.save_cfg()
            QMessageBox.information(self, "성공", f"쿠키 설정이 완료되었습니다. ({dlg.selected_type})")

    def reset_cookie(self):
        self.cfg["browser_cookie"] = "none"
        self.cfg["cookie_file_path"] = ""
        self.parent_win.save_cfg()
        QMessageBox.information(self, "초기화", "쿠키가 초기화되었습니다.")