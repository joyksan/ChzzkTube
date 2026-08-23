import sys
import os
import json
import platform

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QLineEdit, QPushButton, QProgressBar, QFileDialog, QTextEdit
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QTextCursor, QIcon

from utils import _open_windows_explorer
from ui_components import CustomComboBox
from dialogs import ExitConfirmDialog, ActionCountdownDialog, SettingsDialog
from downloader import AnalyzeWorker, DownloadWorker

APP_NAME = "ChzzkTube"
APP_VERSION = "v2.0.0 (PyQt6)"

if getattr(sys, 'frozen', False):
    BASE_DIR = sys._MEIPASS
    CONFIG_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    CONFIG_DIR = BASE_DIR

CONFIG_FILE = os.path.join(CONFIG_DIR, "dl_config.json")
ICON_PATH = os.path.join(BASE_DIR, "icon.ico")

DEFAULT_CONFIG = {
    "download_path": CONFIG_DIR,    
    "container": "mp4",
    "embed_subtitles": False,
    "audio_only": False,
    "fast_download": True,
    "remove_duplicates": True,
    "auto_open_folder": True,
    "completion_action": "none",
    "play_sound": True,
    "max_video_res": "none",
    "filename_prefix": "none",
    "filename_suffix": "id",
    "browser_cookie": "auto",
    "cookie_file_path": "",
    "use_cut": False,
    "cut_start": "",
    "cut_end": ""
}

try:
    import winsound
except ImportError:
    winsound = None


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        self.setMinimumSize(1000, 680)
        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))

        self.setStyleSheet("""
            QMainWindow, QWidget { background-color: #121212; color: #d4d4d4; font-family: 'Segoe UI', sans-serif; font-size: 12px; }
            QPushButton { background-color: #333; border: 1px solid #555; border-radius: 5px; padding: 6px 12px; font-weight: bold; }
            QPushButton:hover { background-color: #444; }
            QPushButton:disabled { background-color: #222; color: #666; border-color: #333; }
            QLineEdit { background-color: #1e1e1e; border: 1px solid #444; border-radius: 5px; padding: 8px; font-size: 13px; }
            QTextEdit { background-color: #000; border: 1px solid #333; border-radius: 5px; font-family: 'Consolas', monospace; padding: 5px; }
            QComboBox { background-color: #1e1e1e; border: 1px solid #444; border-radius: 4px; padding: 4px 8px; min-height: 24px; max-height: 24px; }
            QProgressBar { text-align: center; border: 1px solid #444; border-radius: 4px; background-color: #111; height: 10px; }
            QProgressBar::chunk { background-color: #1976d2; border-radius: 3px; }
        """)

        self.cfg = DEFAULT_CONFIG.copy()
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    if loaded.get("download_path") and os.path.exists(loaded["download_path"]):
                        self.cfg.update(loaded)
            except Exception: pass

        self.dl_state = {"running": False, "paused": False, "canceled": False, "skip": False}
        self.extracted_data = {"info": None, "v_list": [], "a_list": []}
        
        self.analyze_timer = QTimer()
        self.analyze_timer.setSingleShot(True)
        self.analyze_timer.timeout.connect(self.run_analysis)

        self.init_ui()

    def closeEvent(self, event):
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized | Qt.WindowState.WindowActive)
        self.activateWindow()
        
        parent_dlg = self.settings_dlg if (hasattr(self, 'settings_dlg') and self.settings_dlg and self.settings_dlg.isVisible()) else self
        dlg = ExitConfirmDialog(parent_dlg)
        dlg.setWindowFlags(dlg.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)

        if platform.system() == "Windows":
            try:
                import ctypes
                class FLASHWINFO(ctypes.Structure):
                    _fields_ = [("cbSize", ctypes.c_uint), ("hwnd", ctypes.c_void_p), ("dwFlags", ctypes.c_uint), ("uCount", ctypes.c_uint), ("dwTimeout", ctypes.c_uint)]
                hwnd = int(dlg.winId())
                info = FLASHWINFO(ctypes.sizeof(FLASHWINFO), hwnd, 3, 3, 0)
                ctypes.windll.user32.FlashWindowEx(ctypes.byref(info))
            except Exception:
                pass

        result = dlg.exec()
        if result == 1:
            if hasattr(self, 'settings_dlg') and self.settings_dlg: self.settings_dlg.close()
            event.accept()
        elif result == 2:
            if hasattr(self, 'settings_dlg') and self.settings_dlg: self.settings_dlg.close()
            event.accept()
        else:
            event.ignore()

    def save_cfg(self):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self.cfg, f, ensure_ascii=False, indent=4)

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        vbox = QVBoxLayout(main_widget)
        vbox.setSpacing(15)
        vbox.setContentsMargins(15, 15, 15, 15)

        top_bar = QWidget()
        top_bar.setStyleSheet("background-color: #1e1e1e; border-radius: 8px;")
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(15, 10, 15, 10)
        
        self.lbl_path = QLabel(f"<span style='font-size: 13px; font-weight: bold;'>저장 위치</span> &nbsp;&nbsp;&nbsp;|&nbsp;&nbsp;&nbsp; <span style='font-size: 13px; color: #aaa; font-style: italic;'>{self.cfg['download_path']}</span>")
        self.lbl_path.setTextFormat(Qt.TextFormat.RichText)
        top_layout.addWidget(self.lbl_path, 1)

        self.btn_open = QPushButton("폴더 열기")
        self.btn_open.clicked.connect(lambda: _open_windows_explorer(self.cfg['download_path']))
        self.btn_change = QPushButton("폴더 변경")
        self.btn_change.clicked.connect(self.change_folder)
        self.btn_settings = QPushButton("⚙ 설정")
        self.btn_settings.clicked.connect(self.open_settings)
        
        for b in [self.btn_open, self.btn_change, self.btn_settings]: top_layout.addWidget(b)
        vbox.addWidget(top_bar)

        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet("color: #64b5f6; font-weight: bold; font-size: 11px;")
        self.lbl_status.hide()
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.hide()
        vbox.addWidget(self.lbl_status)
        vbox.addWidget(self.progress_bar)

        input_layout = QHBoxLayout()
        self.btn_txt = QPushButton(".txt 선택")
        self.btn_txt.setFixedSize(80, 36)
        self.btn_txt.clicked.connect(self.pick_txt)
        input_layout.addWidget(self.btn_txt)

        self.le_url = QLineEdit()
        self.le_url.setPlaceholderText("URL, 재생목록, 채널주소, TXT파일 경로 입력...")
        self.le_url.setFixedHeight(36)
        self.le_url.textChanged.connect(self.on_url_changed)
        input_layout.addWidget(self.le_url, 1)

        self.btn_download = QPushButton("다운로드 시작")
        self.btn_download.setFixedSize(110, 36)
        self.btn_download.setStyleSheet("QPushButton { background-color: #2e7d32; color: white; } QPushButton:disabled { background-color: #1b451d; color: #777; }")
        self.btn_download.clicked.connect(self.toggle_download)
        self.btn_download.setEnabled(False)
        input_layout.addWidget(self.btn_download)

        self.btn_pause = QPushButton("일시중지")
        self.btn_pause.setFixedSize(90, 36)
        self.btn_pause.setStyleSheet("QPushButton { background-color: #f57c00; color: white; } QPushButton:disabled { background-color: #5c3002; color: #777; }")
        self.btn_pause.clicked.connect(self.toggle_pause)
        self.btn_pause.setEnabled(False)
        input_layout.addWidget(self.btn_pause)

        self.btn_skip = QPushButton("건너뛰기")
        self.btn_skip.setFixedSize(90, 36)
        self.btn_skip.setStyleSheet("QPushButton { background-color: #1565c0; color: white; } QPushButton:disabled { background-color: #0b315c; color: #777; }")
        self.btn_skip.clicked.connect(self.skip_current)
        self.btn_skip.setEnabled(False)
        input_layout.addWidget(self.btn_skip)

        vbox.addLayout(input_layout)

        stream_bar = QWidget()
        stream_bar.setStyleSheet("background-color: #1e1e1e; border-radius: 8px;")
        stream_lay = QHBoxLayout(stream_bar)
        stream_lay.setContentsMargins(15, 10, 15, 10)
        
        def make_stream_col(title, cb):
            lay = QVBoxLayout()
            lay.setSpacing(2)
            lbl = QLabel(title)
            lbl.setStyleSheet("color: #aaa; font-size: 11px;")
            lay.addWidget(lbl)
            cb.setFixedWidth(170)
            lay.addWidget(cb)
            return lay

        self.cb_video = CustomComboBox()
        self.cb_video.addItem("최고 품질 자동 선택", "auto")
        self.cb_video.currentIndexChanged.connect(self.update_meta_badge)
        
        self.cb_max_res = CustomComboBox()
        for k, v in [("none", "제한 없음"), ("2160", "2160p (4K) 이하"), ("1440", "1440p (QHD) 이하"), ("1080", "1080p (FHD) 이하"), ("720", "720p (HD) 이하")]:
            self.cb_max_res.addItem(v, k)
        idx = self.cb_max_res.findData(self.cfg.get("max_video_res", "none"))
        if idx >= 0: self.cb_max_res.setCurrentIndex(idx)
        self.cb_max_res.currentIndexChanged.connect(self.on_max_res_changed)

        self.cb_audio = CustomComboBox()
        self.cb_audio.addItem("최고 품질 자동 선택", "auto")
        self.cb_audio.currentIndexChanged.connect(self.update_meta_badge)

        stream_lay.addLayout(make_stream_col("비디오 스트림 선택", self.cb_video))
        stream_lay.addLayout(make_stream_col("최고 해상도 제한", self.cb_max_res))
        stream_lay.addLayout(make_stream_col("오디오 스트림 선택", self.cb_audio))
        
        self.lbl_meta = QLabel("")
        self.lbl_meta.setStyleSheet("color: #64b5f6; font-weight: bold;")
        stream_lay.addStretch()
        stream_lay.addWidget(self.lbl_meta, alignment=Qt.AlignmentFlag.AlignBottom)
        vbox.addWidget(stream_bar)

        log_lay = QHBoxLayout()
        c_lay = QVBoxLayout()
        c_lay.addWidget(QLabel("간결 로그 (진행 상태)"))
        self.te_concise = QTextEdit()
        self.te_concise.setReadOnly(True)
        self.te_concise.setStyleSheet("color: #4caf50; font-size: 12px;")
        self.te_concise.append(f"[{APP_NAME} {APP_VERSION}] 준비 완료.")
        c_lay.addWidget(self.te_concise)
        
        f_lay = QVBoxLayout()
        f_lay.addWidget(QLabel("전체 상세 로그 (시스템)"))
        self.te_full = QTextEdit()
        self.te_full.setReadOnly(True)
        self.te_full.setStyleSheet("color: #9e9e9e; font-size: 11px;")
        self.te_full.append(f"[{APP_NAME}] 시스템 로그 활성화됨.")
        f_lay.addWidget(self.te_full)
        
        log_lay.addLayout(c_lay, 1)
        log_lay.addLayout(f_lay, 1)
        vbox.addLayout(log_lay, 1)

        self.update_ui_state()

    def change_folder(self):
        if self.dl_state["running"]: return
        folder = QFileDialog.getExistingDirectory(self, "저장 폴더 선택", self.cfg["download_path"])
        if folder:
            self.cfg["download_path"] = os.path.normpath(folder)
            self.lbl_path.setText(f"<span style='font-size: 13px; font-weight: bold;'>저장 위치</span> &nbsp;&nbsp;&nbsp;|&nbsp;&nbsp;&nbsp; <span style='font-size: 13px; color: #aaa; font-style: italic;'>{self.cfg['download_path']}</span>")
            self.save_cfg()
            self.append_concise_log(f"[+] 저장 경로 변경됨: {self.cfg['download_path']}", False, False)

    def open_settings(self):
        if hasattr(self, 'settings_dlg') and self.settings_dlg and self.settings_dlg.isVisible():
            self.settings_dlg.activateWindow()
            return
        self.settings_dlg = SettingsDialog(self, is_running=self.dl_state["running"])
        self.settings_dlg.show()

    def pick_txt(self):
        if self.dl_state["running"]: return
        path, _ = QFileDialog.getOpenFileName(self, "TXT 파일 선택", self.cfg["download_path"], "Text Files (*.txt);;All Files (*.*)")
        if path: self.le_url.setText(os.path.normpath(path))

    def on_url_changed(self):
        self.analyze_timer.stop()
        if not self.le_url.text().strip():
            self.extracted_data = {"info": None, "v_list": [], "a_list": []}
            self.update_stream_dropdowns()
            self.btn_download.setEnabled(False)
            return
        if not self.dl_state["running"]:
            self.btn_download.setText("분석 대기...")
            self.btn_download.setEnabled(False)
            self.analyze_timer.start(500)

    def run_analysis(self):
        url = self.le_url.text().strip()
        if not url: return
        self.btn_download.setText("분석 중...")
        
        self.worker_analyze = AnalyzeWorker(url, self.cfg)
        self.worker_analyze.result_ready.connect(self.on_analyze_success)
        self.worker_analyze.error_occurred.connect(self.on_analyze_error)
        self.worker_analyze.log_concise.connect(self.append_concise_log)
        self.worker_analyze.log_full.connect(self.append_full_log)
        self.worker_analyze.start()

    def on_analyze_success(self, data):
        self.extracted_data = data
        self.update_stream_dropdowns()
        self.btn_download.setText("다운로드 시작")
        self.btn_download.setEnabled(True)

    def on_analyze_error(self, err_msg):
        self.append_concise_log(f"[X] {err_msg}", False, True)
        self.btn_download.setText("다운로드 시작")
        self.btn_download.setEnabled(False)

    def on_max_res_changed(self):
        self.cfg["max_video_res"] = self.cb_max_res.currentData()
        self.save_cfg()
        self.update_stream_dropdowns()

    def update_stream_dropdowns(self):
        self.cb_video.blockSignals(True)
        self.cb_video.clear()
        self.cb_video.addItem("최고 품질 자동 선택", "auto")
        limit_res = self.cfg.get("max_video_res", "none")
        limit_val = int(limit_res) if limit_res != "none" else 999999
        
        for v in self.extracted_data.get("v_list", []):
            if v["height"] > limit_val: continue
            self.cb_video.addItem(v["label"], v["id"])
        self.cb_video.blockSignals(False)

        self.cb_audio.blockSignals(True)
        self.cb_audio.clear()
        self.cb_audio.addItem("자동 선택 (치지직 통합)" if self.extracted_data.get("is_chzzk") else "자동 선택 (최고 품질)", "auto")
        for a in self.extracted_data.get("a_list", []):
            self.cb_audio.addItem(a["label"], a["id"])
        self.cb_audio.blockSignals(False)
        self.update_meta_badge()

    def update_meta_badge(self):
        v_list = self.extracted_data.get("v_list", [])
        if not v_list:
            self.lbl_meta.setText("")
            return
        if self.cfg.get("audio_only", False):
            self.lbl_meta.setText("192kbps | OPUS")
        else:
            self.lbl_meta.setText("1080 | AV01 | OPUS (예상)")

    def update_ui_state(self):
        is_audio = self.cfg.get("audio_only", False)
        self.cb_video.setEnabled(not is_audio and not self.dl_state["running"])
        self.cb_max_res.setEnabled(not is_audio and not self.dl_state["running"])
        self.cb_audio.setEnabled(not self.dl_state["running"])
        self.update_meta_badge()

    def append_concise_log(self, msg, is_status, is_error):
        cursor = self.te_concise.textCursor()
        if is_status:
            cursor.movePosition(QTextCursor.MoveOperation.End)
            cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
            txt = cursor.selectedText()
            if txt.startswith("[다운로드 중]"):
                cursor.removeSelectedText()
                cursor.deletePreviousChar()
        
        self.te_concise.moveCursor(QTextCursor.MoveOperation.End)
        color = "#ff5252" if is_error else ("#64b5f6" if is_status else "#4caf50")
        self.te_concise.insertHtml(f'<span style="color: {color};">{msg}</span><br>')
        self.te_concise.moveCursor(QTextCursor.MoveOperation.End)

    def append_full_log(self, msg):
        self.te_full.append(msg)

    def on_progress_update(self, val, msg):
        self.progress_bar.setValue(int(val * 100))

    def on_status_update(self, current, total, url):
        self.lbl_status.setText(f"전체 진행률: [{current}/{total}] | 처리중: {url[:40]}...")

    def toggle_download(self):
        if not self.dl_state["running"]:
            raw_target = self.le_url.text().strip()
            targets = []
            if os.path.isfile(raw_target) and raw_target.lower().endswith(".txt"):
                try:
                    with open(raw_target, "r", encoding="utf-8") as f:
                        for l in f:
                            t = l.strip()
                            if t and not t.startswith("#"): targets.append("https://" + t if t.startswith("www.") else t)
                except Exception as e:
                    self.append_concise_log(f"TXT 읽기 실패: {e}", False, True); return
            else:
                for l in raw_target.splitlines():
                    t = l.strip()
                    if t: targets.append("https://" + t if t.startswith("www.") else t)

            if self.cfg.get("remove_duplicates"): targets = list(dict.fromkeys(targets))
            if not targets: return

            self.dl_state.update({"running": True, "paused": False, "canceled": False, "skip": False})
            self.btn_download.setText("다운로드 중")
            self.btn_download.setEnabled(False)
            self.btn_pause.setText("일시중지")
            self.btn_pause.setEnabled(True)
            self.btn_skip.setEnabled(True)
            self.le_url.setEnabled(False)
            self.btn_txt.setEnabled(False)
            self.cb_video.setEnabled(False)
            self.cb_max_res.setEnabled(False)
            self.cb_audio.setEnabled(False)
            self.btn_change.setEnabled(False)
            
            self.lbl_status.show()
            self.progress_bar.show()

            self.worker_dl = DownloadWorker(targets, self.cfg, self.dl_state, self.cb_video.currentData(), self.cb_audio.currentData())
            self.worker_dl.progress_update.connect(self.on_progress_update)
            self.worker_dl.status_update.connect(self.on_status_update)
            self.worker_dl.log_concise.connect(self.append_concise_log)
            self.worker_dl.log_full.connect(self.append_full_log)
            self.worker_dl.finished_all.connect(self.on_download_finished)
            self.worker_dl.start()

    def toggle_pause(self):
        if not self.dl_state["running"]: return
        if not self.dl_state["paused"]:
            self.dl_state["paused"] = True
            self.btn_pause.setText("중지 (완전종료)")
            self.btn_pause.setStyleSheet("QPushButton { background-color: #d32f2f; color: white; }")
            self.btn_download.setText("이어받기")
            self.btn_download.setEnabled(True)
            self.append_concise_log("[!] 일시중지됨. (건너뛰기 또는 완전 중지 가능)", True, False)
        else:
            self.dl_state["canceled"] = True
            self.dl_state["paused"] = False

    def skip_current(self):
        if self.dl_state["running"]:
            self.dl_state["skip"] = True
            self.dl_state["paused"] = False
            self.btn_pause.setText("일시중지")
            self.btn_pause.setStyleSheet("QPushButton { background-color: #f57c00; color: white; }")
            self.btn_download.setText("다운로드 중")
            self.btn_download.setEnabled(False)

    def on_download_finished(self, success):
        self.dl_state.update({"running": False, "paused": False, "canceled": False, "skip": False})
        self.btn_download.setText("다운로드 시작")
        self.btn_download.setEnabled(True)
        self.btn_pause.setText("일시중지")
        self.btn_pause.setStyleSheet("QPushButton { background-color: #f57c00; color: white; }")
        self.btn_pause.setEnabled(False)
        self.btn_skip.setEnabled(False)
        self.le_url.setEnabled(True)
        self.btn_txt.setEnabled(True)
        self.btn_change.setEnabled(True)
        self.update_ui_state()
        
        self.lbl_status.hide()
        self.progress_bar.hide()
        self.progress_bar.setValue(0)

        if success:
            if self.cfg.get("play_sound") and winsound:
                try: winsound.MessageBeep(winsound.MB_ICONASTERISK)
                except: pass
            if self.cfg.get("auto_open_folder"):
                _open_windows_explorer(self.cfg['download_path'])
            
            action = self.cfg.get("completion_action", "none")
            if action != "none":
                dlg = ActionCountdownDialog(action, self)
                if dlg.exec() == QDialog.DialogCode.Accepted:
                    if action == "shutdown" and platform.system() == "Windows":
                        os.system("shutdown -s -t 0")
                    elif action == "sleep" and platform.system() == "Windows":
                        os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")
                    elif action == "exit_app":
                        QApplication.quit()

if __name__ == "__main__":
    if platform.system() == "Windows":
        import ctypes
        myappid = 'chzzktube.subapp.v2'
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    if os.path.exists(ICON_PATH):
        app.setWindowIcon(QIcon(ICON_PATH))

    win = MainWindow()
    win.show()
    sys.exit(app.exec())