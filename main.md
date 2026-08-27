### main.py - 메인 윈도우 및 앱 실행 진입점
import os
import platform
import sys

from PyQt6.QtCore import qInstallMessageHandler

def qt_message_handler(mode, context, message):
    if "must be a top level window" in message:
        return
    sys.stderr.write(message + "\n")

qInstallMessageHandler(qt_message_handler)

from PyQt6.QtWidgets import QApplication
from qfluentwidgets import Theme, setTheme

setTheme(Theme.DARK)

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QFontDatabase, QIcon, QTextCursor
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

### 설정 상수/경로/로드·저장은 config 모듈에서 관리
import config
import log_console
import pot_provider
import theme
from controller import DownloadController
from dialogs import ExitConfirmDialog, SettingsDialog, UpdateWorker
from downloader import AnalyzeWorker, DownloadWorker
from media import audio_spec, codec_detail, map_res, short_codec
from ui_components import CustomComboBox
from utils import _open_windows_explorer

_audio_spec = audio_spec  # 구호명 유지 — 헤더 가지/배지 공용 단일 출처(media.audio_spec)

try:
    import winsound
except ImportError:
    winsound = None

APP_NAME = config._APP_NAME
APP_VERSION = config._APP_VERSION
BASE_DIR = config.BASE_DIR
CONFIG_DIR = config.CONFIG_DIR
CONFIG_FILE = config.CONFIG_FILE
ICON_PATH = config.ICON_PATH
DEFAULT_CONFIG = config.default_config()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        self.setMinimumSize(1000, 680)
        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))

        self.setStyleSheet(theme.MAIN_WINDOW_QSS)

        self.cfg = self._load_config()

        # 다운로드 세션 상태/워커는 컨트롤러가 소유 (dl_state 프로퍼티로 접근 가능)
        self.ctrl = DownloadController(self)
        self.extracted_data = {"info": None, "v_list": [], "a_list": []}

        self.worker_analyze = None
        self.settings_dlg = None

        self.analyze_timer = QTimer()
        self.analyze_timer.setSingleShot(True)
        self.analyze_timer.timeout.connect(self.run_analysis)

        self.init_ui()

        # 구성요소(yt-dlp/streamlink) 자동 업데이트 확인 — 기동 직후 비동기 1회
        QTimer.singleShot(500, self._start_update_check)

    @property
    def dl_state(self):
        """다운로드 세션 상태 — DownloadController.state의 별칭."""
        return self.ctrl.state

    def closeEvent(self, event):
        # 1. 최소화 상태 해제 및 Qt 표준 창 활성화
        self.setWindowState(
            self.windowState() & ~Qt.WindowState.WindowMinimized
            | Qt.WindowState.WindowActive
        )
        self.activateWindow()

        is_running = self.dl_state.get("running", False)
        parent_dlg = (
            self.settings_dlg
            if (
                hasattr(self, "settings_dlg")
                and self.settings_dlg
                and self.settings_dlg.isVisible()
            )
            else self
        )
        dlg = ExitConfirmDialog(parent_dlg, is_running=is_running)

        # 2. [소리 복구 & 반짝임] Windows 시스템 알림 음(Beep) 재생 및 작업 표시줄 알림
        if platform.system() == "Windows":
            self._flash_dialog(dlg, winsound)

        result = dlg.exec()

        # [종료] 클릭 시 -> 스레드 안전 중단 후 즉시 종료
        if result == 1:
            if hasattr(self, "settings_dlg") and self.settings_dlg:
                self.settings_dlg.close()
            self.ctrl.shutdown(1000)
            event.accept()

        # [취소] 클릭 시 -> 창 닫기 취소
        else:
            event.ignore()

    @staticmethod
    def _flash_dialog(dlg, winsound):
        """Windows에서 종료 확인 대화상자에 알림음 발생 + 작업 표시줄 반짝임."""
        if winsound:
            try:
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
            except Exception:
                pass
        try:
            import ctypes

            class FLASHWINFO(ctypes.Structure):
                _fields_ = [
                    ("cbSize", ctypes.c_uint),
                    ("hwnd", ctypes.c_void_p),
                    ("dwFlags", ctypes.c_uint),
                    ("uCount", ctypes.c_uint),
                    ("dwTimeout", ctypes.c_uint),
                ]

            hwnd = int(dlg.winId())
            info = FLASHWINFO(ctypes.sizeof(FLASHWINFO), hwnd, 3, 3, 0)
            ctypes.windll.user32.FlashWindowEx(ctypes.byref(info))
        except Exception:
            pass

    def save_cfg(self):
        config.save_config(self.cfg)

    def _load_config(self):
        """설정 로드 (기본값 + 기존 설정 병합). 상세 로직은 config 모듈에 위임."""
        return config.load_config()

    def init_ui(self):
        """UI 구성. 각 패널은 전용 빌더 메서드로 분리."""
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        vbox = QVBoxLayout(main_widget)
        vbox.setSpacing(15)
        vbox.setContentsMargins(15, 15, 15, 15)

        self._build_top_bar(vbox)
        self._build_input_row(vbox)
        self._build_stream_panel(vbox)
        self._build_log_area(vbox)

        self.update_ui_state()

    def _build_top_bar(self, vbox):
        """상단 바: 저장 위치 라벨 + 폴더 열기/변경/설정 버튼."""
        top_bar = QWidget()
        top_bar.setStyleSheet(theme.BAR_PANEL_QSS)
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(15, 10, 15, 10)

        self.lbl_path = QLabel(self._path_label_html())
        self.lbl_path.setTextFormat(Qt.TextFormat.RichText)
        top_layout.addWidget(self.lbl_path, 1)

        self.btn_open = QPushButton("폴더 열기")
        self.btn_open.clicked.connect(
            lambda: _open_windows_explorer(self.cfg["download_path"])
        )
        self.btn_change = QPushButton("폴더 변경")
        self.btn_change.clicked.connect(self.change_folder)
        self.btn_settings = QPushButton("⚙\ufe0e 설정")
        self.btn_settings.setStyleSheet(theme.BTN_SETTINGS_FONT_QSS)
        self.btn_settings.clicked.connect(self.open_settings)

        for b in [self.btn_open, self.btn_change, self.btn_settings]:
            top_layout.addWidget(b)
        vbox.addWidget(top_bar)

    def _build_input_row(self, vbox):
        """입력 행: .txt 선택 / URL 입력 / 시작·종료·건너뛰기 버튼."""
        input_layout = QHBoxLayout()
        self.btn_txt = QPushButton(".txt 선택")
        self.btn_txt.setObjectName("btn_txt")
        self.btn_txt.setFixedSize(80, 36)
        self.btn_txt.clicked.connect(self.pick_txt)
        input_layout.addWidget(self.btn_txt)

        self.le_url = QLineEdit()
        self.le_url.setPlaceholderText("URL, 재생목록, 채널주소, TXT파일 경로 입력...")
        self.le_url.setFixedHeight(36)
        self.le_url.setClearButtonEnabled(True)
        self.le_url.textChanged.connect(self.on_url_changed)
        input_layout.addWidget(self.le_url, 1)

        self.btn_download = QPushButton("다운로드 시작")
        self.btn_download.setFixedSize(110, 36)
        self.btn_download.setStyleSheet(theme.BTN_PRIMARY_QSS)
        self.btn_download.clicked.connect(self.toggle_download)
        self.btn_download.setEnabled(False)
        input_layout.addWidget(self.btn_download)

        self.btn_stop = QPushButton("작업종료")
        self.btn_stop.setFixedSize(90, 36)
        self.btn_stop.setStyleSheet(theme.BTN_DANGER_QSS)
        self.btn_stop.clicked.connect(self.stop_download)
        self.btn_stop.setEnabled(False)
        input_layout.addWidget(self.btn_stop)

        self.btn_skip = QPushButton("건너뛰기")
        self.btn_skip.setFixedSize(90, 36)
        self.btn_skip.setStyleSheet(theme.BTN_INFO_QSS)
        self.btn_skip.clicked.connect(self.skip_current)
        self.btn_skip.setEnabled(False)
        input_layout.addWidget(self.btn_skip)

        vbox.addLayout(input_layout)

    def _build_stream_panel(self, vbox):
        """스트림 패널: 비디오/해상도/오디오 콤보 + 메타 배지."""
        stream_bar = QWidget()
        stream_bar.setStyleSheet(theme.BAR_PANEL_QSS)
        stream_lay = QHBoxLayout(stream_bar)
        stream_lay.setContentsMargins(15, 10, 15, 10)

        def make_stream_col(title, cb, width=200):
            lay = QVBoxLayout()
            lay.setSpacing(8)
            lbl = QLabel(title)
            lbl.setStyleSheet(theme.LBL_STREAM_QSS)
            lay.addWidget(lbl)
            cb.setFixedWidth(width)
            lay.addWidget(cb)
            return lay

        self.cb_video = CustomComboBox()
        self.cb_video.addItem("최고 품질 자동 선택", "auto")
        self.cb_video.currentIndexChanged.connect(self.on_video_stream_changed)

        self.cb_max_res = CustomComboBox()
        for k, v in [
            ("none", "제한 없음"),
            ("2160", "2160p (4K) 이하"),
            ("1440", "1440p (QHD) 이하"),
            ("1080", "1080p (FHD) 이하"),
            ("720", "720p (HD) 이하"),
        ]:
            self.cb_max_res.addItem(v, k)
        idx = self.cb_max_res.findData(self.cfg.get("max_video_res", "none"))
        if idx >= 0:
            self.cb_max_res.setCurrentIndex(idx)
        self.cb_max_res.currentIndexChanged.connect(self.on_max_res_changed)

        self.cb_audio = CustomComboBox()
        self.cb_audio.addItem("최고 품질 자동 선택", "auto")
        self.cb_audio.currentIndexChanged.connect(self.update_meta_badge)

        stream_lay.addLayout(make_stream_col("비디오 스트림 선택", self.cb_video, 230))
        stream_lay.addLayout(make_stream_col("최고 해상도 제한", self.cb_max_res, 150))
        stream_lay.addLayout(make_stream_col("오디오 스트림 선택", self.cb_audio, 230))

        self.lbl_meta = QLabel("")
        self.lbl_meta.setStyleSheet(theme.LBL_META_QSS)
        stream_lay.addStretch()
        stream_lay.addWidget(self.lbl_meta, alignment=Qt.AlignmentFlag.AlignBottom)
        vbox.addWidget(stream_bar)

    def _build_log_area(self, vbox):
        """로그 영역: 간결 로그 + 전체 상세 로그 (D2Coding 폰트)."""
        log_lay = QHBoxLayout()
        c_lay = QVBoxLayout()
        c_lay.addWidget(QLabel("간결 로그 (진행 상태)"))

        self.te_concise = QTextEdit()
        self.te_concise.setReadOnly(True)
        self.te_concise.setStyleSheet(theme.CONSOLE_INIT_QSS)
        self.console = log_console.ConciseLogConsole(self.te_concise)

        # [핵심] Document 객체 자체에 하단 마진을 부여하여 항상 바닥 여백 유지
        doc = self.te_concise.document()
        doc.setDocumentMargin(8)  # 기본 마진

        self.te_concise.document().setDocumentMargin(8)
        self.te_concise.setHtml(
            f'<span style="color: #4caf50;">[{APP_NAME} {APP_VERSION}] by Miorine</span><br>'
        )
        c_lay.addWidget(self.te_concise)

        f_lay = QVBoxLayout()
        f_lay.addWidget(QLabel("전체 상세 로그 (시스템)"))

        # [D2Coding 최우선] 한글/영문/특수문자 2:1 폭 완벽 대응 개발자 폰트
        font = QFont("D2Coding", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setFamilies(["D2Coding", "Consolas", "Malgun Gothic", "Segoe UI"])
        self.te_concise.setFont(font)

        # QSS 세팅: 화살표 버튼 완전 제거 & 투명 레일 & 미니멀 바
        self.te_concise.setStyleSheet(theme.CONSOLE_LOG_QSS)
        # 트리 로그 줄바꿈 예산을 뷰포트 폭에 맞춤 (resizeEvent에서도 갱신)
        log_console.update_tree_budget(self.te_concise)

        # 전체 상세 로그 창에도 동일한 미니멀 스크롤바 스타일 적용 (색상만 다크 톤 유지)
        self.te_full = QTextEdit()
        self.te_full.setReadOnly(True)

        self.te_full.setStyleSheet(
            theme.CONSOLE_LOG_QSS.replace(
                "color: #4caf50;", "color: #9e9e9e; font-size: 11px;"
            )
        )

        self.te_full.append(f"[{APP_NAME}] 시스템 로그 활성화됨.")
        f_lay.addWidget(self.te_full)

        log_lay.addLayout(c_lay, 1)
        log_lay.addLayout(f_lay, 1)
        vbox.addLayout(log_lay, 1)

    def _path_label_html(self):
        """저장 위치 라벨용 RTF 텍스트 생성 (경로 반영)"""
        return (
            "<span style='font-size: 13px; font-weight: bold;'>저장 위치</span>"
            " &nbsp;&nbsp;&nbsp;|&nbsp;&nbsp;&nbsp; "
            "<span style='font-size: 13px; color: #aaa; font-style: italic;'>"
            f"{self.cfg['download_path']}</span>"
        )

    def change_folder(self):
        if self.ctrl.running:
            return
        folder = QFileDialog.getExistingDirectory(
            self, "저장 폴더 선택", self.cfg["download_path"]
        )
        if folder:
            self.cfg["download_path"] = os.path.normpath(folder)
            self.lbl_path.setText(self._path_label_html())
            self.save_cfg()
            self.append_concise_log(
                log_console.format_kv_line(
                    "[+]", "경로 변경", self.cfg["download_path"]
                ),
                False,
                False,
            )

    def format_target_url(self, url, max_len=50):
        """URL 접기 — 포매팅은 log_console.format_target_url에 위임."""
        return log_console.format_target_url(url, max_len)

    def open_settings(self):
        if (
            hasattr(self, "settings_dlg")
            and self.settings_dlg
            and self.settings_dlg.isVisible()
        ):
            self.settings_dlg.activateWindow()
            return
        self.settings_dlg = SettingsDialog(self, is_running=self.ctrl.running)
        self.settings_dlg.show()

    def pick_txt(self):
        if self.ctrl.running:
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "TXT 파일 선택",
            self.cfg["download_path"],
            "Text Files (*.txt);;All Files (*.*)",
        )
        if path:
            self.le_url.setText(os.path.normpath(path))

    def _reset_stream_ui(self):
        """스트림 선택 UI를 비활성 초기 상태로 완전 리셋 (URL 삭제/작업 완료 시)."""
        self._all_integrated = False
        for cb in (self.cb_video, self.cb_audio):
            cb.blockSignals(True)
            cb.clear()
            cb.addItem("최고 품질 자동 선택", "auto")
            cb.setEnabled(True)
            cb.blockSignals(False)
        self.update_meta_badge()

    def on_url_changed(self):
        self.analyze_timer.stop()
        text = self.le_url.text().strip()

        # [핵심] URL을 지웠을 때 드롭다운/메타 배지/분석 타이머·로그 즉시 초기화
        if not text:
            self.extracted_data = {"info": None, "v_list": [], "a_list": []}
            self._reset_stream_ui()
            self.btn_download.setEnabled(False)

            if self.worker_analyze and self.worker_analyze.isRunning():
                self.worker_analyze.terminate()
                self.worker_analyze.wait()
            if hasattr(self, "anim_timer") and self.anim_timer.isActive():
                self.anim_timer.stop()

            # 남아있는 애니메이션 상태 로그가 있다면 깔끔하게 지우기
            self.console.clear_status_line()
            # 직전 분석 결과 블록도 철회 — 링크를 지우면 그 링크의 분석 로그가 남아있던 현상 방지
            self._discard_analysis_result()
            return

        if not self.ctrl.running:
            self.btn_download.setText("분석 대기...")
            self.btn_download.setEnabled(False)
            self.analyze_timer.start(500)

    def _start_pot_provider(self):
        """앱 시작 시 bgutil PO Token 서버가 있도록 준비 (유튜브 성인제한/봇 확인 대응)."""
        try:
            self._pot_worker = pot_provider.POTProviderWorker(self)
            self._pot_worker.line.connect(self.append_concise_log)
            self._pot_worker.finished.connect(self._on_pot_provider_finished)
            self._pot_worker.start()
        except Exception:
            # PO 토큰 실패가 다운로더 전체를 막지 않도록 조용히 무시
            pass

    def _on_pot_provider_finished(self):
        self.append_concise_log("[+] 준비 완료.", False, False)
        self.append_concise_log("", False, False)

    def run_analysis(self):
        url = self.le_url.text().strip()
        if not url:
            return
        self.btn_download.setText("분석 중...")

        if self.worker_analyze and self.worker_analyze.isRunning():
            self.worker_analyze.terminate()
            self.worker_analyze.wait()

        # 이전 링크의 분석 결과 블록이 마지막에 남아 있으면 철회한다.
        self._discard_analysis_result()

        # [신규] 분석 중 마침표 애니메이션(. -> .. -> ...)을 위한 타이머 설정
        self.dots_count = 1
        if not hasattr(self, "anim_timer"):
            self.anim_timer = QTimer(self)
            self.anim_timer.setInterval(200)  # 0.2초마다 갱신
            self.anim_timer.timeout.connect(self.update_analysis_anim)

        self.base_anim_url = url
        self.anim_timer.start()

        self.worker_analyze = AnalyzeWorker(url, self.cfg)
        self.worker_analyze.result_ready.connect(self.on_analyze_success)
        self.worker_analyze.error_occurred.connect(self.on_analyze_error)
        self.worker_analyze.log_concise.connect(self.append_concise_log)
        self.worker_analyze.log_full.connect(self.append_full_log)
        self.worker_analyze.start()

    def update_analysis_anim(self):
        """마침표 애니메이션과 수직 정렬된 URL 렌더링"""
        raw_dots = "." * self.dots_count
        fixed_dots = raw_dots.ljust(3)
        formatted_url = self.format_target_url(self.base_anim_url)

        msg = f"[+] 미디어 스트림 분석 중{fixed_dots}\n{formatted_url}"
        self.append_concise_log(msg, is_status=True, is_error=False)
        self.dots_count = (self.dots_count + 1) % 4

    def stop_analysis_anim(self, ok=True):
        """분석 애니메이션 정지 후 임시 상태 로그를 지우고 최종 결과 로그를 히스토리로 박제.

        ok=False(분석 실패)면 타이머만 정지한다 — 직후 출력되는 [X] 오류 라인이 애니메이션 잔상을 대신 정리한다.
        """
        if hasattr(self, "anim_timer") and self.anim_timer.isActive():
            self.anim_timer.stop()
        if not ok:
            return

        counts = log_console.format_analysis_counts(
            len(self.extracted_data.get("v_list", [])),
            len(self.extracted_data.get("a_list", [])),
        )
        formatted_url = self.format_target_url(self.base_anim_url)
        self.append_concise_log(
            f"[+] 미디어 스트림 분석 완료{counts}\n{formatted_url}",
            is_status=False,
            is_error=False,
        )
        # 블록 철회 추적 — 입력란이 비거나 새 분석이 시작되면 이 블록을 제거한다
        self._analysis_block_active = True
        self._analysis_block_count = self.console.last_status_block_count
        self._analysis_last_line = formatted_url.split("\n")[-1]

    def _discard_analysis_result(self):
        """직전 분석 결과 블록을 철회한다 (마지막 콘텐츠일 때만)."""
        if not getattr(self, "_analysis_block_active", False):
            return
        last_text = self.console.last_content_block_text()
        if last_text != getattr(self, "_analysis_last_line", None):
            self._analysis_block_active = False
            return
        self.console.remove_last_blocks(getattr(self, "_analysis_block_count", 0))
        self._analysis_block_active = False

    def _start_update_check(self):
        """구성요소(yt-dlp/streamlink) 최신 버전 비동기 확인 — 기동 0.5초 후 1회."""
        self.update_worker = UpdateWorker(self, upgrade=False)
        self.update_worker.check_done.connect(self._on_update_check_done)
        self.update_worker.start()

    def _on_update_check_done(self, stale):
        """버전 확인 결과 처리 — 최신 표기 또는 자동 업그레이드 전환."""
        if not stale:
            self.append_concise_log("[v] 구성요소 최신", False, False)
            self._start_pot_provider()
            return

        summary = ", ".join(f"{p} {c}→{l}" for p, c, l in stale)
        if getattr(sys, "frozen", False):
            self.append_concise_log(
                log_console.format_kv_line("[~]", "업데이트", summary), False, False
            )
            self._start_pot_provider()
            return
        self.append_concise_log(
            log_console.format_kv_line(
                "[~]", "업데이트", f"{summary} — 자동 설치를 시작합니다"
            ),
            False,
            False,
        )
        self.update_worker = UpdateWorker(self, upgrade=True)
        self.update_worker.line.connect(self.append_concise_log)
        self.update_worker.upgrade_done.connect(self._on_auto_upgrade_done)
        self.update_worker.start()

    def _on_auto_upgrade_done(self, ok, summary):
        """기동 자동 업그레이드 결과."""
        self.append_concise_log(
            log_console.format_kv_line("[v]" if ok else "[!]", "업데이트", summary),
            False,
            not ok,
        )
        self._start_pot_provider()

    def on_analyze_success(self, data):
        self.extracted_data = data
        self.stop_analysis_anim()
        self.update_stream_dropdowns()
        self.btn_download.setText("다운로드 시작")
        self.btn_download.setEnabled(True)

    def on_analyze_error(self, err_msg):
        self.stop_analysis_anim(ok=False)
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
            if v["height"] > limit_val:
                continue
            self.cb_video.addItem(v["label"], v["id"])
        self.cb_video.blockSignals(False)

        v_list = self.extracted_data.get("v_list", [])
        self._all_integrated = bool(v_list) and all(
            str(v.get("acodec", "none")) not in ("none", "") for v in v_list
        )
        if self._all_integrated:
            self.on_video_stream_changed()
        else:
            self._rebuild_audio_combo()
            self.update_meta_badge()

    def _selected_video(self):
        vid = self.cb_video.currentData()
        return next(
            (v for v in self.extracted_data.get("v_list", []) if v["id"] == vid),
            None,
        )

    def _rebuild_audio_combo(self, integrated=False, match_id=None):
        self.cb_audio.blockSignals(True)
        try:
            self.cb_audio.clear()
            if integrated:
                groups, order = {}, []
                for v in self.extracted_data.get("v_list", []):
                    ac = str(v.get("acodec", "none"))
                    if ac in ("none", ""):
                        continue
                    spec = _audio_spec(ac)
                    if spec not in groups:
                        groups[spec] = []
                        order.append(spec)
                    groups[spec].append(v["id"])
                for spec in order:
                    self.cb_audio.addItem(spec, tuple(groups[spec]))
                if not self.cb_audio.count():
                    ids = [
                        v["id"]
                        for v in self.extracted_data.get("v_list", [])
                        if v.get("id")
                    ]
                    self.cb_audio.addItem("내장 오디오 (코덱 미보고)", tuple(ids))
                idx = next(
                    (
                        i
                        for i in range(self.cb_audio.count())
                        if match_id is not None
                        and match_id in (self.cb_audio.itemData(i) or ())
                    ),
                    0,
                )
                self.cb_audio.setCurrentIndex(idx)
            else:
                self.cb_audio.addItem("최고 품질 자동 선택", "auto")
                for a in self.extracted_data.get("a_list", []):
                    self.cb_audio.addItem(a["label"], a["id"])
        finally:
            self.cb_audio.blockSignals(False)

    def on_video_stream_changed(self):
        v = self._selected_video()
        if v is None and getattr(self, "_all_integrated", False):
            v = (self.extracted_data.get("v_list") or [None])[0]
        self._rebuild_audio_combo(
            integrated=getattr(self, "_all_integrated", False),
            match_id=v["id"] if v else None,
        )
        self.update_meta_badge()

    def update_meta_badge(self):
        if self.cfg.get("audio_only", False):
            self.lbl_meta.setText("MP3 | 192kbps (예상)")
            return
        v_list = self.extracted_data.get("v_list", [])
        if not v_list:
            self.lbl_meta.setText("")
            return
        v = self._selected_video()
        auto = v is None
        if auto:
            v = v_list[0]
        fps_str = f" {v['fps']}fps" if v.get("fps") else ""
        badge = (
            f"{map_res(None, v.get('height'))}{fps_str}"
            f" | {short_codec(v.get('vcodec'))}"
        )
        if v.get("acodec", "none") not in ("none", ""):
            badge += f" | {_audio_spec(v['acodec'])}"
        else:
            a_sel = self.cb_audio.currentData()
            a_list = self.extracted_data.get("a_list", [])
            a = next((x for x in a_list if x["id"] == a_sel), None) or (
                a_list[0] if a_list else None
            )
            if a:
                badge += f" | {_audio_spec(a.get('acodec'))}"
            badge += " (자동)" if auto else " (예상)"
        self.lbl_meta.setText(badge)

    def _audio_stream_desc(self):
        a_data = self.cb_audio.currentData()
        if isinstance(a_data, tuple):
            return ""
        a_list = self.extracted_data.get("a_list", [])
        a = next((x for x in a_list if x["id"] == a_data), None) or (
            a_list[0] if a_list else None
        )
        if a:
            return str(a.get("label") or "")
        return "자동 (병합)"

    def update_ui_state(self):
        is_audio = self.cfg.get("audio_only", False)
        self.cb_video.setEnabled(not is_audio and not self.ctrl.running)
        self.cb_max_res.setEnabled(not is_audio and not self.ctrl.running)
        self.cb_audio.setEnabled(not self.ctrl.running)
        self.update_meta_badge()
        self.console.reset_status_flag()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "te_concise"):
            log_console.update_tree_budget(self.te_concise)

    def append_concise_log(self, msg, is_status=False, is_error=False):
        self.console.append(msg, is_status, is_error)

    def append_full_log(self, msg):
        self.te_full.append(msg)

    def on_progress_update(self, val, msg):
        return

    def on_status_update(self, current, total, url):
        if total > 1:
            if url == "완료":
                self.append_concise_log(
                    f"[+] 전체 진행 [{total}/{total}] 완료", False, False
                )
            else:
                self.append_concise_log(
                    f"[+] 전체 진행 [{current}/{total}] 대상: {url[:40]}",
                    False,
                    False,
                )

    def toggle_download(self):
        if self.ctrl.running:
            return
        try:
            targets = DownloadController.parse_targets(
                self.le_url.text().strip(),
                dedup=self.cfg.get("remove_duplicates"),
            )
        except ValueError as e:
            self.append_concise_log(str(e), False, True)
            return
        if not targets:
            return

        self.ctrl.begin()

        self.btn_download.setText("다운로드 중")
        self.btn_download.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.btn_skip.setEnabled(True)

        self.le_url.setEnabled(False)
        self.btn_txt.setEnabled(False)
        self.cb_video.setEnabled(False)
        self.cb_max_res.setEnabled(False)
        self.cb_audio.setEnabled(False)
        self.btn_change.setEnabled(False)

        live_hint = len(targets) == 1 and bool(
            (self.extracted_data.get("info") or {}).get("is_live")
        )
        self.ctrl.spawn_worker(
            targets,
            self.cfg,
            self.cb_video.currentData(),
            self._worker_a_sel(),
            is_live_hint=live_hint,
            v_spec=self._selected_video(),
            audio_desc=self._audio_stream_desc(),
        )

    def _worker_a_sel(self):
        data = self.cb_audio.currentData()
        if not getattr(self, "_all_integrated", False):
            return data
        v = self._selected_video() or (self.extracted_data.get("v_list") or [{}])[0]
        if self.cfg.get("audio_only", False):
            return v.get("id")
        return "integrated"

    def stop_download(self):
        if self.ctrl.running:
            self.ctrl.request_cancel()
            self.btn_stop.setEnabled(False)
            self.btn_skip.setEnabled(False)
            self.btn_stop.setText("중단 요청 중...")

    def skip_current(self):
        if self.ctrl.running:
            self.ctrl.request_skip()
            self.append_concise_log(
                "[!] 현재 항목 건너뛰기를 요청했습니다...", False, False
            )

    def add_concise_task_separator(self):
        self.console.add_task_separator()

    def on_download_finished(self, success_count, fail_count):
        self.ctrl.end()

        if success_count > 0:
            self.le_url.clear()
            self.extracted_data = {"info": None, "v_list": [], "a_list": []}
            self._reset_stream_ui()

        self.btn_download.setText("다운로드 시작")
        self.btn_download.setEnabled(bool(self.le_url.text().strip()))
        self.btn_stop.setText("작업종료")
        self.btn_stop.setEnabled(False)
        self.btn_skip.setEnabled(False)

        self.le_url.setEnabled(True)
        self.btn_txt.setEnabled(True)
        self.btn_change.setEnabled(True)
        self.update_ui_state()

        total = success_count + fail_count
        if total > 1:
            summary_msg = f"[v] 일괄 다운로드 작업 완료! (성공: {success_count}개, 실패: {fail_count}개)"
            self.append_concise_log(
                summary_msg, is_status=False, is_error=(fail_count > 0)
            )

        self.add_concise_task_separator()

        if success_count > 0:
            if self.cfg.get("play_sound") and winsound:
                try:
                    winsound.MessageBeep(winsound.MB_ICONASTERISK)
                except Exception:
                    pass
            if self.cfg.get("auto_open_folder"):
                _open_windows_explorer(self.cfg["download_path"])

if __name__ == "__main__":
    if platform.system() == "Windows":
        import ctypes
        myappid = "chzzktube.subapp.v2"
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    if os.path.exists(ICON_PATH):
        app.setWindowIcon(QIcon(ICON_PATH))

    font_path = os.path.join(BASE_DIR, "D2Coding-Regular.ttf")
    if os.path.exists(font_path):
        QFontDatabase.addApplicationFont(font_path)

    win = MainWindow()
    win.show()
    sys.exit(app.exec())
