import sys
import os
import json
import urllib.request
import glob
import sqlite3
import shutil
import tempfile
import re
import datetime
import platform
import subprocess
import time

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QLineEdit, QPushButton, QComboBox, QCheckBox, 
    QTextEdit, QProgressBar, QFileDialog, QMessageBox, QDialog, QListView, QFrame
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QTextCursor, QIcon

import yt_dlp

try:
    import winsound
except ImportError:
    winsound = None

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

ANSI_ESCAPE_RE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
def clean_ansi(text):
    return ANSI_ESCAPE_RE.sub('', text)

def get_filename_template(cfg):
    prefix_key = cfg.get("filename_prefix", "none")
    suffix_key = cfg.get("filename_suffix", "id")

    prefix_map = {
        "none": "",
        "date_dash_uploader": "%(upload_date>%Y-%m-%d)s [%(uploader)s] ",
        "date_compact_uploader": "%(upload_date>%Y%m%d)s [%(uploader)s] ",
        "date_dash": "%(upload_date>%Y-%m-%d)s ",
        "date_compact": "%(upload_date>%Y%m%d)s "
    }

    suffix_map = {
        "id_res_fps": " [%(id)s] [%(height)sp] [%(fps)sfps]",
        "id_res": " [%(id)s] [%(height)sp]",
        "id": " [%(id)s]"
    }
    prefix = prefix_map.get(prefix_key, "")
    suffix = suffix_map.get(suffix_key, "")
    return f"{prefix}%(title)s{suffix}.%(ext)s"

def get_video_codec_rank(vcodec):
    v = str(vcodec).lower()
    if 'av01' in v or 'av1' in v: return 3
    if 'vp09' in v or 'vp9' in v: return 2
    if 'avc' in v or 'h264' in v or 'h.264' in v: return 1
    return 0

def get_audio_codec_rank(acodec, fid=""):
    a = str(acodec).lower()
    f = str(fid).lower()
    rank = 0
    if 'opus' in a: rank = 30
    elif 'mp4a' in a or 'aac' in a or 'm4a' in a: rank = 20
    elif 'vorbis' in a: rank = 10
    if 'drc' in f: rank -= 1
    return rank

def get_browser_cookies():
    cookie_dict = {}
    try:
        sys_name = platform.system()
        appdata = os.environ.get("APPDATA", "")
        localappdata = os.environ.get("LOCALAPPDATA", "")
        home = os.path.expanduser("~")
        paths = []
        if sys_name == "Windows":
            paths = [
                os.path.join(appdata, "Mozilla", "Firefox", "Profiles"),
                os.path.join(localappdata, "Google", "Chrome", "User Data", "Default"),
                os.path.join(localappdata, "Microsoft", "Edge", "User Data", "Default")
            ]
        elif sys_name == "Darwin":
            paths = [os.path.join(home, "Library", "Application Support", "Firefox", "Profiles")]

        for p in paths:
            if not os.path.exists(p): continue
            try:
                if "Firefox" in p:
                    for prof in glob.glob(os.path.join(p, "*")):
                        cf = os.path.join(prof, "cookies.sqlite")
                        if os.path.exists(cf):
                            td = tempfile.mkdtemp()
                            tdb = os.path.join(td, "cookies.sqlite")
                            shutil.copy2(cf, tdb)
                            conn = sqlite3.connect(tdb)
                            cur = conn.cursor()
                            cur.execute('SELECT name, value FROM moz_cookies WHERE host LIKE "%naver.com"')
                            for n, v in cur.fetchall():
                                if n not in cookie_dict: cookie_dict[n] = v
                            conn.close()
                            shutil.rmtree(td, ignore_errors=True)
                else:
                    cf = os.path.join(p, "Network", "Cookies")
                    if not os.path.exists(cf): cf = os.path.join(p, "Cookies")
                    if os.path.exists(cf):
                        td = tempfile.mkdtemp()
                        tdb = os.path.join(td, "Cookies")
                        shutil.copy2(cf, tdb)
                        conn = sqlite3.connect(tdb)
                        cur = conn.cursor()
                        cur.execute('SELECT name, value FROM cookies WHERE host_key LIKE "%naver.com"')
                        for n, v in cur.fetchall():
                            if n not in cookie_dict: cookie_dict[n] = v
                        conn.close()
                        shutil.rmtree(td, ignore_errors=True)
            except Exception:
                continue
            if "NID_AUT" in cookie_dict: break
    except Exception:
        pass
    return cookie_dict

def analyze_chzzk_clip_api(target_url):
    clip_id = target_url.split("/")[-1].split("?")[0]
    cookie_dict = get_browser_cookies()
    cookie_str = "; ".join([f"{k}={v}" for k, v in cookie_dict.items()])
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://chzzk.naver.com/"
    }
    if cookie_str: headers["Cookie"] = cookie_str

    clip_title = clip_id
    created_date = datetime.date.today().strftime("%Y-%m-%d")

    detail_url = f"https://api.chzzk.naver.com/service/v1/clips/{clip_id}/detail"
    try:
        req = urllib.request.Request(detail_url, headers=headers)
        with urllib.request.urlopen(req) as res:
            d_data = json.loads(res.read().decode("utf-8")).get("content", {})
            if d_data.get("clipTitle"): clip_title = d_data.get("clipTitle")
            if d_data.get("createdDate"): created_date = d_data.get("createdDate").split(" ")[0]
    except Exception:
        pass

    play_info_url = f"https://api.chzzk.naver.com/service/v1/play-info/clip/{clip_id}"
    video_formats = []
    try:
        req = urllib.request.Request(play_info_url, headers=headers)
        with urllib.request.urlopen(req) as res:
            data = json.loads(res.read().decode("utf-8"))
            cnt = data.get("content", {})
            in_key, video_id = cnt.get("inKey"), cnt.get("videoId")

        if in_key and video_id:
            rmc_url = f"https://apis.naver.com/rmcnmv/rmcnmv/vod/play/v2.0/{video_id}?key={in_key}"
            req_rmc = urllib.request.Request(rmc_url, headers=headers)
            with urllib.request.urlopen(req_rmc) as rmc_res:
                rmc_data = json.loads(rmc_res.read().decode("utf-8"))
                videos = rmc_data.get("videos", {}).get("list", [])
                for idx, v in enumerate(videos):
                    encoding_opt = v.get("encodingOption", {}).get("name", f"Stream_{idx}")
                    bitrate = v.get("bitrate", {}).get("video", 0) if isinstance(v.get("bitrate"), dict) else v.get("bitrate", 0)
                    bitrate_kbps = int(bitrate / 1000) if bitrate else 0
                    source_url = v.get("source", "")
                    v_codec = v.get("encodingOption", {}).get("vcodec", "H.264")
                    height = 0
                    h_match = re.search(r'(\d+)p', encoding_opt)
                    if h_match: height = int(h_match.group(1))

                    video_formats.append({
                        "id": source_url if source_url else f"chzzk_{idx}",
                        "res": encoding_opt, "height": height, "bitrate": bitrate_kbps,
                        "url": source_url, "vcodec": v_codec
                    })
    except Exception:
        pass

    video_formats.sort(key=lambda x: (x["height"], get_video_codec_rank(x["vcodec"]), x["bitrate"]), reverse=True)
    return {"title": clip_title, "date": created_date, "clip_id": clip_id, "formats": video_formats}

def _open_windows_explorer(path):
    target = os.path.normpath(os.path.abspath(path))
    if platform.system() == "Windows":
        is_file = os.path.isfile(target)
        folder = target if not is_file else os.path.dirname(target)
        args = ["explorer.exe", "/n,", "/select," + target] if is_file else ["explorer.exe", "/n,", folder]
        subprocess.Popen(args, close_fds=True)
    elif platform.system() == "Darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


class CustomComboBox(QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setView(QListView())
        
    def showPopup(self):
        super().showPopup()
        popup = self.view().window()
        popup.move(self.mapToGlobal(self.rect().bottomLeft()))


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
        btn_save_exit.setStyleSheet("""
            QPushButton {
                background-color: #3b5998; color: white; font-weight: bold;
                padding: 6px 12px; border-radius: 4px; border: none;
            }
            QPushButton:hover { background-color: #4c6ef5; }
        """)
        btn_save_exit.clicked.connect(lambda: self.done(1))

        btn_exit = QPushButton("종료")
        btn_exit.setStyleSheet("""
            QPushButton {
                background-color: #333; color: #ddd; padding: 6px 16px;
                border-radius: 4px; border: 1px solid #444;
            }
            QPushButton:hover { background-color: #444; }
        """)
        btn_exit.clicked.connect(lambda: self.done(2))

        btn_cancel = QPushButton("취소")
        btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: #333; color: #ddd; padding: 6px 16px;
                border-radius: 4px; border: 1px solid #444;
            }
            QPushButton:hover { background-color: #444; }
        """)
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
            ("Cookies.txt", "file"),
            ("Chrome", "chrome"),
            ("Firefox", "firefox"),
            ("Edge", "edge"),
            ("Opera", "opera"),
            ("Brave", "brave"),
            ("Vivaldi", "vivaldi"),
            ("Chromium", "chromium"),
            ("Whale", "whale")
        ]

        for text, b_type in buttons:
            btn = QPushButton(text)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #2b2b2b;
                    color: #d4d4d4;
                    border: 1px solid #3c3c3c;
                    border-radius: 4px;
                    padding: 8px;
                    font-size: 12px;
                    font-weight: bold;
                }
                QPushButton:hover { background-color: #383838; border-color: #555; }
            """)
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
            # 크로미움 계열 브라우저 선택 시 파일 락/권한 에러 사전 테스트
            if b_type in ["chrome", "edge", "whale", "chromium", "brave", "vivaldi"]:
                try:
                    import yt_dlp.cookies
                    yt_dlp.cookies.extract_cookies_from_browser(b_type)
                except Exception as ex:
                    ex_str = str(ex)
                    
                    # Hitomi 스타일의 다각화된 원인 분석 및 로그 구성
                    error_cause = "알 수 없는 오류"
                    solution_tip = "인터넷 검색 또는 수동 Cookies.txt 방식을 이용해주세요."
                    
                    if "Permission denied" in ex_str or "13" in ex_str:
                        error_cause = "브라우저 파일 락(Lock) 또는 권한 거부"
                        solution_tip = f"해당 브라우저({b_type})가 실행 중이거나 백그라운드 프로세스가 파일을 점유하고 있습니다. 브라우저를 완전히 종료 후 다시 시도하세요."
                    elif "no such table" in ex_str or "sqlite" in ex_str.lower():
                        error_cause = "브라우저 쿠키 데이터베이스 손상 또는 경로 오류"
                        solution_tip = "브라우저 프로필 경로가 올바르지 않거나 데이터베이스 구조가 변경되었습니다."
                    elif "decryption" in ex_str or "dpapi" in ex_str.lower():
                        error_cause = "운영체제 DPAPI 보안 복호화 실패"
                        solution_tip = "윈도우 자격 증명 또는 사용자 계정 보안 정책으로 인해 쿠키 암호화 해제에 실패했습니다."

                    detailed_log = (
                        f"[오류 진단 분석]\n"
                        f" - 실패한 브라우저 : {b_type}\n"
                        f" - 감지된 원인     : {error_cause}\n"
                        f" - 권장 해결 조치  : {solution_tip}\n\n"
                        f"[원본 시스템 상세 트레이스백]\n{ex_str}"
                    )

                    msg_box = QMessageBox(self)
                    msg_box.setIcon(QMessageBox.Icon.Critical)
                    msg_box.setWindowTitle("오류 상세 분석")
                    msg_box.setText(f"브라우저({b_type}) 쿠키를 불러오는 데 실패했습니다.\n\n[원인] {error_cause}")
                    msg_box.setDetailedText(detailed_log)
                    
                    for child in msg_box.findChildren(QWidget):
                        if isinstance(child, QTextEdit) or isinstance(child, QLabel):
                            child.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard)

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


# --- PyQt6 Threads ---
class YtLoggerBridge:
    def __init__(self, log_full_signal):
        self.log_full_signal = log_full_signal
    def debug(self, msg):
        if msg.strip(): self.log_full_signal.emit(clean_ansi(msg))
    def info(self, msg):
        if msg.strip(): self.log_full_signal.emit(clean_ansi(msg))
    def warning(self, msg):
        if msg.strip(): self.log_full_signal.emit(f"[WARNING] {clean_ansi(msg)}")
    def error(self, msg):
        if msg.strip(): self.log_full_signal.emit(f"[ERROR] {clean_ansi(msg)}")

class AnalyzeWorker(QThread):
    result_ready = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)
    log_concise = pyqtSignal(str, bool, bool)
    log_full = pyqtSignal(str)

    def __init__(self, target_url, cfg):
        super().__init__()
        self.target_url = target_url
        self.cfg = cfg
        self.logger = YtLoggerBridge(self.log_full)

    def run(self):
        self.log_concise.emit(f"[+] 미디어 스트림 분석 중... : {self.target_url}", False, False)
        self.log_full.emit(f"--- [포맷 분석 시작] {self.target_url} ---")
        
        try:
            if "chzzk.naver.com/clips/" in self.target_url:
                ch_info = analyze_chzzk_clip_api(self.target_url)
                v_list = []
                for fmt in ch_info.get("formats", []):
                    v_list.append({
                        "id": fmt["id"], "height": fmt["height"], "vcodec": fmt.get("vcodec", ""),
                        "bitrate": fmt["bitrate"], "tbr": fmt["bitrate"], 
                        "label": f"해상도: {fmt['res']} | 비트레이트: {fmt['bitrate']}kbps"
                    })
                self.log_concise.emit(f"[✓] 치지직 클립 분석 완료! (제목: {ch_info['title']})", False, False)
                self.result_ready.emit({"info": ch_info, "v_list": v_list, "a_list": [], "is_chzzk": True})
            else:
                ydl_opts = {'logger': self.logger, 'skip_download': True, 'noplaylist': True, 'extract_flat': False}
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(self.target_url, download=False)
                
                if info:
                    if 'entries' in info: info = info['entries'][0]
                    v_list, a_list = [], []
                    for f in info.get('formats', []):
                        fid, ext = f.get('format_id', '?'), f.get('ext', '?')
                        vcodec, acodec = f.get('vcodec', 'none'), f.get('acodec', 'none')
                        tbr, fps, height = int(f.get('tbr') or 0), f.get('fps') or 0, f.get('height') or 0
                        fps_str = f"{fps}fps" if fps else ""
                        res = f.get('resolution') or (f"{height}p" if height else "audio")

                        if vcodec != 'none':
                            v_list.append({"id": fid, "height": height, "fps": fps, "tbr": tbr, "vcodec": vcodec, 
                                           "label": f"ID: {fid} | {res} {fps_str} | {tbr}kbps | Codec: {vcodec} ({ext})"})
                        if acodec != 'none' and vcodec == 'none':
                            abr = int(f.get('abr') or tbr or 0)
                            a_list.append({"id": fid, "abr": abr, "acodec": acodec, "label": f"ID: {fid} | {abr}kbps | Codec: {acodec} ({ext})"})

                    v_list.sort(key=lambda x: (x["height"], x["fps"], get_video_codec_rank(x["vcodec"]), x["tbr"]), reverse=True)
                    a_list.sort(key=lambda x: (x["abr"], get_audio_codec_rank(x["acodec"], x["id"])), reverse=True)
                    
                    self.log_concise.emit(f"[✓] 스트림 분석 완료! (비디오 {len(v_list)}개, 오디오 {len(a_list)}개)", False, False)
                    self.result_ready.emit({"info": info, "v_list": v_list, "a_list": a_list, "is_chzzk": False})
                else:
                    self.error_occurred.emit("미디어 정보를 가져오지 못했습니다.")
        except Exception as ex:
            ex_str = str(ex).lower()
            if "sign in to confirm your age" in ex_str or "age-gated" in ex_str or "members-only" in ex_str:
                self.error_occurred.emit("연령 제한 또는 멤버십 전용 동영상입니다. 설정에서 쿠키를 불러오세요.")
            else:
                self.error_occurred.emit(f"분석 오류 발생: {str(ex)}")

class DownloadWorker(QThread):
    progress_update = pyqtSignal(float, str)
    status_update = pyqtSignal(int, int, str)
    log_concise = pyqtSignal(str, bool, bool)
    log_full = pyqtSignal(str)
    finished_all = pyqtSignal(bool)

    def __init__(self, targets, cfg, state_dict, v_sel, a_sel):
        super().__init__()
        self.targets = targets
        self.cfg = cfg
        self.state = state_dict
        self.v_sel = v_sel
        self.a_sel = a_sel
        self.logger = YtLoggerBridge(self.log_full)

    def hook(self, d):
        if self.state["canceled"]: raise Exception("사용자에 의해 다운로드가 중지되었습니다.")
        if self.state["skip"]: raise Exception("SKIP_CURRENT_ITEM")
        
        while self.state["paused"]:
            if self.state["canceled"]: raise Exception("사용자에 의해 다운로드가 중지되었습니다.")
            if self.state["skip"]: raise Exception("SKIP_CURRENT_ITEM")
            time.sleep(0.2)

        if d['status'] == 'downloading':
            p_str = clean_ansi(d.get('_percent_str', '0.0%')).strip().replace('%', '')
            try:
                p_val = float(p_str) / 100.0
                self.progress_update.emit(p_val, "")
            except Exception: pass
            s = clean_ansi(d.get('_speed_str', '속도 계산중')).strip()
            e = clean_ansi(d.get('_eta_str', '시간 미정')).strip()
            p_display = clean_ansi(d.get('_percent_str', '0.0%')).strip()
            self.log_concise.emit(f"[다운로드 중] 진행률: {p_display} | 속도: {s} | 남은 시간: {e}", True, False)
        elif d['status'] == 'finished':
            self.log_concise.emit("[+] 다운로드 완료, 후처리 진행 중...", False, False)

    def run(self):
        total = len(self.targets)
        failed_targets = []

        try:
            for idx, url in enumerate(self.targets, 1):
                if self.state["canceled"]: break
                self.state["skip"] = False
                self.status_update.emit(idx - 1, total, url)

                try:
                    if "chzzk.naver.com/clips/" in url:
                        max_res = self.cfg.get("max_video_res", "none")
                        ch_info = analyze_chzzk_clip_api(url)
                        dl_target = self.v_sel if self.v_sel and self.v_sel != "auto" else None
                        selected_fmt = None
                        if ch_info["formats"]:
                            if dl_target:
                                for fmt in ch_info["formats"]:
                                    if fmt["url"] == dl_target: selected_fmt = fmt; break
                            if not selected_fmt:
                                limit = int(max_res) if max_res != "none" else 99999
                                for fmt in ch_info["formats"]:
                                    if fmt["height"] <= limit or limit == 99999:
                                        selected_fmt = fmt; dl_target = fmt["url"]; break
                                if not selected_fmt: dl_target = ch_info["formats"][0]["url"]

                        tmpl = os.path.join(self.cfg['download_path'], get_filename_template(self.cfg))
                        ydl_opts = {'outtmpl': tmpl, 'progress_hooks': [self.hook], 'logger': self.logger, 'ignoreerrors': True}
                        if self.cfg['fast_download']: ydl_opts['concurrent_fragment_downloads'] = 5
                        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                            info = ydl.extract_info(dl_target if dl_target else url, download=True)
                        if info:
                            out = os.path.basename(info.get('_filename', '완료'))
                            self.log_concise.emit(f"[✓] 완료: {out}", False, False)
                        else: failed_targets.append(url)
                    else:
                        browser = self.cfg.get("browser_cookie", "none")
                        ydl_opts = {
                            'outtmpl': os.path.join(self.cfg['download_path'], get_filename_template(self.cfg)),
                            'progress_hooks': [self.hook], 'logger': self.logger, 'ignoreerrors': True,
                            'writethumbnail': True, 'embedmetadata': True,
                            'postprocessors': [{'key': 'FFmpegThumbnailsConvertor', 'format': 'jpg'}, {'key': 'EmbedThumbnail'}]
                        }
                        if browser not in ["none", "auto", "cookie_file"]:
                            ydl_opts['cookiesfrombrowser'] = (browser,)
                        elif browser == "cookie_file" and os.path.exists(self.cfg.get("cookie_file_path", "")):
                            ydl_opts['cookiefile'] = self.cfg["cookie_file_path"]

                        if self.cfg.get("use_cut"):
                            s_time = self.cfg.get("cut_start", "00:00:00")
                            e_time = self.cfg.get("cut_end", "inf")
                            ydl_opts['download_ranges'] = yt_dlp.utils.download_range_func(None, [(yt_dlp.utils.parse_sec(s_time), yt_dlp.utils.parse_sec(e_time))])
                            ydl_opts['force_keyframes_at_cuts'] = True

                        max_res = self.cfg.get("max_video_res", "none")
                        if self.cfg['audio_only']:
                            ydl_opts['format'] = 'bestaudio/best' if self.a_sel == "auto" else self.a_sel
                            ydl_opts['postprocessors'].insert(0, {'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'})
                        else:
                            if self.v_sel != "auto":
                                ydl_opts['format'] = f'{self.v_sel}+ba/b'
                            else:
                                if max_res != "none": ydl_opts['format'] = f'bestvideo[height<={max_res}]+bestaudio/best'
                                else: ydl_opts['format'] = 'bv*+ba/b'
                            ydl_opts['merge_output_format'] = self.cfg.get('container', 'mkv')

                        if self.cfg['fast_download']: ydl_opts['concurrent_fragment_downloads'] = 5
                        if self.cfg['embed_subtitles'] and not self.cfg['audio_only']:
                            ydl_opts.update({'writesubtitles': True, 'writeautomaticsub': False, 'subtitleslangs': ['ko'], 'subtitlesformat': 'srt/best', 'embedsubtitles': True})
                            ydl_opts['postprocessors'].insert(0, {'key': 'FFmpegSubtitlesConvertor', 'format': 'srt'})

                        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                            info = ydl.extract_info(url, download=True)

                        if info:
                            if 'entries' in info: info = info['entries'][0]
                            out = os.path.basename(info.get('_filename', '완료'))
                            self.log_concise.emit(f"[✓] 완료: {out}", False, False)
                        else: failed_targets.append(url)

                except Exception as item_ex:
                    if "SKIP_CURRENT_ITEM" in str(item_ex):
                        self.log_concise.emit(f"[!] 현재 항목 스킵됨: {url}", False, False)
                        continue
                    if "중지되었습니다" in str(item_ex): raise item_ex
                    
                    ex_msg = str(item_ex).lower()
                    failed_targets.append(url)
                    
                    # 브라우저 암호화/쿠키 접근 오류 감지 시 구체적인 안내 추가
                    if "cookie" in ex_msg or "dpapi" in ex_msg or "encryption" in ex_msg or "locked" in ex_msg:
                        self.log_concise.emit(f"[X] 쿠키 접근 실패 (브라우저 보안 제한): 쿠키 불러오기에서 'Cookies.txt' 방식을 사용해주세요.", False, True)
                    else:
                        self.log_concise.emit(f"[X] 오류 발생: {str(item_ex)}", False, True)

            self.status_update.emit(total, total, "완료")
            if failed_targets:
                ff_path = os.path.join(self.cfg['download_path'], "failed_urls.txt")
                with open(ff_path, "w", encoding="utf-8") as f:
                    for u in failed_targets: f.write(u + "\n")
                self.log_concise.emit(f"[!] 실패 항목 {len(failed_targets)}개 'failed_urls.txt' 저장됨", False, True)
            self.log_concise.emit(f"\n[✓] 전체 다운로드 작업 완료!\n", False, False)
            self.finished_all.emit(True)

        except Exception as ex:
            if "중지되었습니다" in str(ex):
                self.log_concise.emit("\n[!] 사용자에 의해 다운로드가 완전히 중지되었습니다.\n", False, True)
            else:
                self.log_concise.emit(f"\n[X] 중단됨: {str(ex)}\n", False, True)
            self.finished_all.emit(False)


# --- PyQt6 UI Classes ---
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
            cb.setStyleSheet("""
                QComboBox {
                    background-color: #1e1e1e;
                    border: 1px solid #444;
                    border-radius: 4px;
                    padding: 0px 6px;
                    font-size: 11px;
                    min-height: 24px;
                    max-height: 24px;
                }
                QComboBox:disabled { background-color: #161616; color: #555; border-color: #333; }
                QComboBox QAbstractItemView {
                    background-color: #1e1e1e;
                    color: #ffffff;
                    selection-background-color: #1976d2;
                    border: 1px solid #444;
                }
            """)
            for k, v in options: cb.addItem(v, k)
            return cb

        # 1. 포맷 컨테이너
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

        # 2. 쿠키 설정
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
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #1e1e1e;
                    border: 1px solid #444;
                    padding: 0px;
                    border-radius: 4px;
                    min-height: 24px;
                    max-height: 24px;
                    font-size: 11px;
                }
                QPushButton:hover { background-color: #2a2a2a; }
                QPushButton:disabled { background-color: #161616; color: #555; border-color: #333; }
            """)
            btn.clicked.connect(func)
            c_hlay.addWidget(btn)
            self.cookie_buttons.append(btn)
        cookie_layout.addLayout(c_hlay)
        layout.addWidget(cookie_box)

        # 3. 체크박스 옵션들
        self.chk_sub = QCheckBox("한국어 자막 포함 (SRT 자동 변환 병합)")
        self.chk_audio = QCheckBox("음원만 추출 (MP3)")
        self.chk_dedup = QCheckBox("중복 URL 자동 제거")
        self.chk_fast = QCheckBox("고속 분할 다운로드 (5스레드 병렬)")
        self.chk_auto_open = QCheckBox("완료 시 폴더 열기")
        self.chk_sound = QCheckBox("완료 알림음 재생")
        for chk in [self.chk_sub, self.chk_audio, self.chk_dedup, self.chk_fast, self.chk_auto_open, self.chk_sound]:
            chk.setEnabled(not self.is_running)
            layout.addWidget(chk)

        # 4. 작업 완료 후 동작
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("작업 완료 후 동작"))
        row2.addStretch()
        self.cb_completion = make_combo([
            ("none", "사용 안 함"), ("sleep", "절전 모드 진입"),
            ("shutdown", "PC 자동 종료"), ("exit_app", "프로그램 종료")
        ], 250)
        row2.addWidget(self.cb_completion)
        layout.addLayout(row2)

        # 5. 파일명 형식
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

        # 6. 구간 추출
        cut_layout = QHBoxLayout()
        self.chk_cut = QCheckBox("구간 추출 (Cut)")
        self.chk_cut.setEnabled(not self.is_running)
        cut_layout.addWidget(self.chk_cut)
        cut_layout.addStretch()
        
        line_edit_style = """
            QLineEdit {
                background-color: #2d2d2d;
                border: 1px solid #444;
                border-radius: 4px;
                font-size: 11px;
                padding: 0px 4px;
                margin: 0px;
                min-height: 24px;
                max-height: 24px;
            }
            QLineEdit:disabled { background-color: #1a1a1a; color: #555; border-color: #333; }
        """

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
        btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: #333; color: #ddd; border: 1px solid #444;
                border-radius: 4px; padding: 6px 16px; font-weight: bold;
            }
            QPushButton:hover { background-color: #444; }
        """)
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
        if result == 1:  # 저장&종료
            if hasattr(self, 'settings_dlg') and self.settings_dlg:
                self.settings_dlg.close()
            event.accept()
        elif result == 2:  # 종료
            if hasattr(self, 'settings_dlg') and self.settings_dlg:
                self.settings_dlg.close()
            event.accept()
        else:  # 취소
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