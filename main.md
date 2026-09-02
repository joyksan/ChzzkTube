##### main.py - 메인 윈도우 및 앱 실행 진입점
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

from PyQt6.QtCore import Qt, QThread, QTimer
from PyQt6.QtGui import QFont, QFontDatabase, QIcon
from PyQt6.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

##### 설정 상수/경로/로드·저장은 config 모듈에서 관리
import config
import log_console
import log_history
import pot_provider
import theme
from controller import DownloadController
from dialogs import ExitConfirmDialog, SettingsDialog, UpdateWorker, VerboseLogWindow
from downloader import AnalyzeWorker
from utils import _open_windows_explorer

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
        # [히스토리] 실행 세션 시작 마커 — 이후 모든 구성요소/PO 서버/다운로드 로그 기록
        log_history.session_begin(APP_NAME, APP_VERSION)
        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        self.setMinimumSize(800, 680)
        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))

        self.setStyleSheet(theme.TUI_STYLE)

        self.cfg = self._load_config()

        # 다운로드 세션 상태/워커는 컨트롤러가 소유 (dl_state 프로퍼티로 접근 가능)
        self.ctrl = DownloadController(self)
        self.extracted_data = {"info": None, "v_list": [], "a_list": []}

        self.worker_analyze = None
        self.settings_dlg = None
        self.verbose_win = None

        self.analyze_timer = QTimer()
        self.analyze_timer.setSingleShot(True)
        self.analyze_timer.timeout.connect(self.run_analysis)

        # 락 가드: 앱 시작 및 PO Token 서버 구성 중에는 드롭다운/입력 차단 및 순서 보정
        self._startup_completed = False

        self.init_ui()

        # 구성요소(yt-dlp/streamlink) 자동 업데이트 확인 — 기동 직후 비동기 1회
        QTimer.singleShot(500, self._start_update_check)

        # [응답없음 폴백] 구성요소 체인(POT 포함)이 15초 안에 끝나지 않으면
        # 입력을 강제 개방 — URL 잠금이 영구화되지 않게 한다.
        QTimer.singleShot(15000, self._force_unlock_input)

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
            if getattr(self, "verbose_win", None) is not None:
                self.verbose_win.close()
            self.ctrl.shutdown(1000)
            if self.ctrl.worker is not None and self.ctrl.worker.isRunning():
                log_history.log(
                    "종료: 다운로드 워커 미종료(1s) — 취소 플래그로 자연 종료 예정, 프로세스 종료 진행",
                    "WARN",
                )
            # [스레드 경계] 종료 전 러닝 QThread 회수 — 좀비 분석 워커/기동 워커가
            # 살아있으면 Qt가 "QThread: Destroyed while thread is still running"
            # 경고와 함께 종료 크래시를 낼 수 있다. terminate 금지 원칙 유지,
            # 짧은 wait만 시도 (워커들은 취소 플래그로 자연 종료를 약속받는다).
            for w in list(getattr(self, "_zombie_workers", []) or []):
                if w is not None and w.isRunning():
                    w.wait(1500)
                    if w.isRunning():
                        log_history.log(
                            "종료: 유기된 분석 워커 미종료(1.5s) — 프로세스 종료 진행",
                            "WARN",
                        )
            for name in ("_pot_worker", "update_worker"):
                w = getattr(self, name, None)
                if w is not None and w.isRunning():
                    w.wait(1500)
                    if w.isRunning():
                        log_history.log(
                            f"종료: 기동 워커({name}) 미종료(1.5s) — 프로세스 종료 진행",
                            "WARN",
                        )
            log_history.session_end()
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
        """[4단계] Blank Slate — setup_ui()로 위임."""
        self.setup_ui()

    def setup_ui(self):
        """[TUI Refactor] fzf-style minimalist 3-GroupBox 레이아웃.

        ├── Configuration ── PATH: ... │ [F1] [F2] │ [F12] [F3]
        ├── Input & Action ── > [url_input] │ [F4] │ [ENTER │ ESC]
        └── Live Console Monitor ── (stretch=1 → 100% 채움)
        """
        # ── 중앙 위젯 / 메인 레이아웃 (flat 3-panel, no master wrapper) ──
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)

        # ── 헬퍼: tui-tag 클래스 버튼 ──
        def _tui_tag(text, tooltip, slot):
            b = QPushButton(text)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(slot)
            b.setToolTip(tooltip)
            b.setProperty("class", "tui-tag")
            b.style().unpolish(b)
            b.style().polish(b)
            return b

        # ════════════════════════════════════════════════════════════════════
        # Layer 1: Configuration (QGroupBox)
        # ════════════════════════════════════════════════════════════════════
        self.header_group = QGroupBox("Configuration")
        self.header_group.setObjectName("header_group")
        self.header_group.setProperty("class", "tui-panel")
        self.header_group.style().unpolish(self.header_group)
        self.header_group.style().polish(self.header_group)
        hlay = QHBoxLayout(self.header_group)
        hlay.setContentsMargins(10, 6, 10, 6)
        hlay.setSpacing(6)

        self.path_label = QLabel()
        self.path_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.path_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self._update_path_label()
        hlay.addWidget(self.path_label, 1)

        self.btn_change = _tui_tag(
            "[ F1: Change ]", "저장 폴더 변경 (F1)", self.change_folder
        )
        self.btn_open = _tui_tag(
            "[ F2: Open ]", "저장 폴더 열기 (F2)",
            lambda: _open_windows_explorer(self.cfg["download_path"]),
        )
        hlay.addWidget(self.btn_change)
        hlay.addWidget(self.btn_open)

        # v_line: Change/Open과 Full Log/Settings 그룹 사이 시각 구분
        self.v_line = QLabel("\u2502")
        self.v_line.setProperty("class", "tui-sep")
        hlay.addWidget(self.v_line)

        self.btn_full_log = _tui_tag(
            "[ F12: Full Log ]", "전체 상세 로그 창 토글 (F12)", self.toggle_verbose_log
        )
        self.btn_settings = _tui_tag(
            "[ F3: Settings ]", "설정 열기 (F3)", self.open_settings
        )
        hlay.addWidget(self.btn_full_log)
        hlay.addWidget(self.btn_settings)

        main_layout.addWidget(self.header_group)

        # ════════════════════════════════════════════════════════════════════
        # Layer 2: Input & Action (QGroupBox)
        # ════════════════════════════════════════════════════════════════════
        self.input_group = QGroupBox("Input && Action")
        self.input_group.setObjectName("input_group")
        self.input_group.setProperty("class", "tui-panel")
        self.input_group.style().unpolish(self.input_group)
        self.input_group.style().polish(self.input_group)
        ilay = QHBoxLayout(self.input_group)
        ilay.setContentsMargins(10, 6, 10, 6)
        ilay.setSpacing(6)

        self.prompt_symbol = QLabel(">")
        ilay.addWidget(self.prompt_symbol)

        # [ObjectName] url_input — TUI_STYLE의 QLineEdit#url_input 선택자 타겟
        self.url_input = QLineEdit()
        self.url_input.setObjectName("url_input")
        self.url_input.setPlaceholderText("URL, 재생목록, 채널주소 입력...")
        self.url_input.setClearButtonEnabled(True)
        self.url_input.textChanged.connect(self.on_url_changed)
        self.url_input.setDragEnabled(True)
        self.url_input.acceptDrops()
        self.url_input.dropEvent = lambda e: self._on_url_drop(e.mimeData())
        self.url_input.returnPressed.connect(self.toggle_download)
        ilay.addWidget(self.url_input, 1)

        self.btn_txt = _tui_tag(
            "[ F4: Load .txt ]", "TXT 파일에서 URL 목록 로드 (F4)", self.pick_txt
        )
        ilay.addWidget(self.btn_txt)

        self.btn_enter = _tui_tag(
            "[ ENTER: Start ]", "URL 입력 후 시작 (Enter)",
            self.toggle_download,
        )
        self.btn_esc = _tui_tag(
            "[ ESC: Abort ]", "실행 중 중단 (Esc)",
            self.abort_download,
        )
        ilay.addWidget(self.btn_enter)
        ilay.addWidget(self.btn_esc)

        main_layout.addWidget(self.input_group)

        # ════════════════════════════════════════════════════════════════════
        # Layer 3: Live Console Monitor (QGroupBox, stretch=1 → 100% 채움)
        # ════════════════════════════════════════════════════════════════════
        self.console_group = QGroupBox("Live Console Monitor")
        self.console_group.setObjectName("console_group")
        self.console_group.setProperty("class", "tui-panel")
        self.console_group.style().unpolish(self.console_group)
        self.console_group.style().polish(self.console_group)
        self.console_group.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        clay = QVBoxLayout(self.console_group)
        # 콘솔 박스 안쪽: 좌 8, 우 8, 상 4, 하 8px 여백
        clay.setContentsMargins(8, 4, 8, 8)
        clay.setSpacing(0)

        # [ObjectName] console_log — TUI_STYLE의 QTextEdit#console_log 선택자 타겟
        self.te_concise = QTextEdit()
        self.te_concise.setObjectName("console_log")
        self.te_concise.setReadOnly(True)
        self.te_concise.document().setDocumentMargin(0)
        # 모던 TUI 미니멀 헤더 — 한 줄로 통합 (배너 + 메타)
        # [paint 루프 방지] table/float 없이 순차 span만 사용 — QTextEdit의
        # 제한된 HTML 서브셋에서 float:right는 layout이 깨진다.
        self.te_concise.setHtml(
            f'<span style="color:#4ec9b0;font-weight:bold;">[{APP_NAME} {APP_VERSION}]</span>'
            f'<span style="color:#888888;">  by Miorine  </span>'
            f'<span style="color:#4ec9b0;">── live console monitor ──</span>'
        )
        font = QFont("D2Coding", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setFamilies(["D2Coding", "Consolas", "Malgun Gothic", "Segoe UI"])
        self.te_concise.setFont(font)
        self.console = log_console.ConciseLogConsole(self.te_concise)
        # update_tree_budget은 showEvent에서 위젯 실측 폭으로 1회 계산 (paint 루프 방지)

        clay.addWidget(self.te_concise, 1)
        main_layout.addWidget(self.console_group, stretch=1)

        # ── 보조 상태 초기화 ──
        self._full_log_buf: list[str] = []
        self.update_ui_state()


    def _on_url_drop(self, mime_data):
        """드래그드롭된 .txt 파일 URL 자동 추출."""
        if not mime_data.hasUrls():
            return
        for url in mime_data.urls():
            path = url.toLocalFile()
            if path.lower().endswith(".txt"):
                self.pick_txt_from_path(path)
                return
            if path.startswith("http://") or path.startswith("https://"):
                self.url_input.setText(path)
                return

    def pick_txt_from_path(self, path):
        """선택된 .txt 파일 URL 로드."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = [l.strip() for l in f if l.strip() and not l.strip().startswith("#")]
            if lines:
                self.url_input.setText("\n".join(lines))
                self.append_concise_log(
                    log_console.emit_event("SYS", "OK", "TXT", f"로드 완료 — {len(lines)}개 URL"),
                    is_status=False, is_error=False,
                )
        except Exception:
            self.append_concise_log(
                log_console.emit_event("SYS", "FAIL", "TXT", "파일 읽기 실패"),
                is_status=False, is_error=True,
            )

    def abort_download(self):
        """실행 중 다운로드 중단 (ESC 버튼 / 단축키 공용)."""
        if self.ctrl.running:
            self.ctrl.request_cancel()
            self.append_concise_log(
                log_console.emit_event("DL", "ABORT", "-", "사용자에 의해 중단 요청됨"),
                is_status=False, is_error=True,
            )

    def _update_path_label(self):
        """PATH 라벨 TUI 텍스트 갱신 — `path_label` 위젯 갱신."""
        path = self.cfg.get("download_path", "")
        self.path_label.setText(
            f"<span style='color:#4ec9b0; font-weight:bold;'>PATH:</span> "
            f"{path}"
        )

    def change_folder(self):
        if self.ctrl.running:
            return
        folder = QFileDialog.getExistingDirectory(
            self, "저장 폴더 선택", self.cfg["download_path"]
        )
        if folder:
            self.cfg["download_path"] = os.path.normpath(folder)
            self._update_path_label()
            self.save_cfg()
            self.append_concise_log(
                log_console.emit_event("SYS", "OK", "CFG", f"경로 변경 → {self.cfg['download_path']}"),
                is_status=False, is_error=False,
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
            self.url_input.setText(os.path.normpath(path))

    def on_url_changed(self):
        self.analyze_timer.stop()
        text = self.url_input.text().strip()

        # [핵심] URL을 지웠을 때 분석 타이머·로그 즉시 초기화
        if not text:
            self.extracted_data = {"info": None, "v_list": [], "a_list": []}

            # [결함 수리] terminate()+wait()는 GIL을 보유한 파이썬 스레드를
            # 야매 종료시켜 GUI 전체의 파이썬 실행을 영구 정지시켰다 — 이 뒤의
            # 로그 정리(clear_status_line)가 절대 실행되지 않아 'URL을 지워도
            # 분석중·URL 로그가 남는' 현상의 근본 원인. 유기 패턴으로 대체.
            self._abandon_analyze_worker()
            self.console.clear_status_line()
            # 직전 분석 결과 블록도 철회 — 링크를 지우면 그 링크의 분석 로그가 남아있던 현상 방지
            self._discard_analysis_result()
            return

        if not self.ctrl.running and getattr(self, "_startup_completed", False):
            self.analyze_timer.start(500)

    def _start_pot_provider(self):
        """앱 시작 시 bgutil PO Token 서버가 있도록 준비 (유튜브 성인제한/봇 확인 대응)."""
        if (
            hasattr(self, "_pot_worker")
            and self._pot_worker.isRunning()
        ):
            return  # 중복 기동 방지
        try:
            self._pot_worker = pot_provider.POTProviderWorker(self)
            self._pot_worker.line.connect(self._component_line)
            self._pot_worker.log_full.connect(self.append_full_log)
            self._pot_worker.finished.connect(self._on_pot_provider_finished)
            self._pot_worker.start()
        except Exception:
            pass

    def _force_unlock_input(self):
        """[폴백] 구성요소 체인이 15초 내 완료되지 않으면 입력 강제 개방.

        POT 서버는 연령제한 영상에만 필요 — 체인이 멈춰도 기본 다운로드는 막지 않는다.
        """
        if getattr(self, "_startup_completed", False):
            return
        self._startup_completed = True
        self.update_ui_state()
        self.append_concise_log(
            log_console.emit_event("SYS", "SKIP", "DEPS", "구성요소 확인 지연 — 입력 선개방"),
            is_status=False, is_error=False,
        )

    def _on_pot_provider_finished(self):
        state, msg = self._pot_worker.outcome
        log_history.log(f"PO Token 서버 기동 결과: {state} — {msg}")

        # 순서 정합성 패치: PO Token 설정 완료된 가장 마지막 단계에서 버전 체크 결과를 출력
        # [로그 정책] 구성요소별 '최신/건너뜀' 개별 라인은 간결 로그에서 생략되므로
        # (_component_line 필터), 그 요약 한 줄만 간결에 남긴다 — 개별 결과는
        # 상세 로그와 히스토리 파일에 전건 기록. 구버전 감지(_stale_updates) 시엔
        # 업데이트 진행 라인이 이미 간결에 뜨므로 도장깨기하지 않는다.
        if state == "ok" and not getattr(self, "_stale_updates", False):
            self.append_concise_log(
                log_console.emit_event("SYS", "OK", "DEPS", "Components up-to-date"),
                is_status=False, is_error=False,
            )

        # 실제 성공/실패 여부를 설계 사양과 일치하게 출력
        if state == "ok":
            if msg:
                self.append_concise_log(
                log_console.emit_event("SYS", "OK", "POT", msg),
                is_status=False, is_error=False,
            )
        else:
            self.append_concise_log(
                log_console.emit_event("SYS", "FAIL", "POT", "Server bind failed — 연령제한 영상 다운로드 불가"),
                is_status=False, is_error=True,
            )

        self.append_concise_log(
                log_console.emit_event("SYS", "READY", "ENGINE", "Ready for download"),
                is_status=False, is_error=False,
            )

        # 락 가드 해제 및 UI 기동
        self._startup_completed = True
        self.update_ui_state()

        self.add_concise_task_separator()  # 한 줄 여백 보증

    def _abandon_analyze_worker(self):
        """실행 중 분석 워커를 종료 강요 없이 유기한다 (zombie 패턴).

        [결함 수리] 구버전은 재분석/URL 삭제 시 QThread.terminate()+wait()로
        워커를 죽였다. terminate는 파이썬 스레드를 GIL 보유 상태로 강제 종료 —
        죽은 스레드가 GIL을 영원히 반환하지 않아 GUI 스레드의 파이썬 실행
        (시그널·타이머·슬롯 전부)이 영구 정지했고, '미디어 스트림 분석 중'에서
        영원히 넘어가지 않는 증상의 근본 원인이었다.

        대신: 시그널을 전부 끊어 UI 오염을 차단하고, 워커는 자연 종료까지
        실행한 뒤 finished로 회수한다. yt-dlp 추출은 내부 취소 지점이 없어
        강제 종료가 불가능하므로, 결과를 버리고 방치하는 것이 유일한 안전한 취책.
        """
        w = self.worker_analyze
        if not w:
            return
        if w.isRunning():
            for sig in (w.result_ready, w.error_occurred, w.log_full):
                try:
                    sig.disconnect()
                except TypeError:
                    pass
            w.finished.connect(self._reap_zombie_worker)
            if not hasattr(self, "_zombie_workers"):
                self._zombie_workers = []
            self._zombie_workers.append(w)
        self.worker_analyze = None

    def _reap_zombie_worker(self):
        """자연 종료된 유기 워커를 참조 목록에서 회수 (메모리 정리)."""
        try:
            self._zombie_workers.remove(self.sender())
        except (ValueError, AttributeError):
            pass

    def run_analysis(self):
        url = self.url_input.text().strip()
        if not url:
            return
        self.append_concise_log(
                log_console.emit_event("ANAL", "RUN", "-", "분석 시작..."),
                is_status=True, is_error=False,
            )

        # [결함 수리] 구버전의 terminate()+wait() 대신 유기 패턴 — GIL 사망 방지
        self._abandon_analyze_worker()

        # 이전 링크의 분석 결과 블록이 마지막에 남아 있으면 철회한다.
        self._discard_analysis_result()

        self.base_anim_url = url

        # [스레드 경계 / 경쟁상태 수리] 이전 분석 워커가 아직 러닝 중일 수 있다
        # (500ms 디바운스보다 yt-dlp 추출이 길면 항상 그렇다). 참조를 그냥
        # 덮어쓰면 옛 워커가 시그널 연결된 채 생존해 나중에 result_ready를
        # 쏘아 낡은 URL의 결과로 extracted_data를 오염시킨다(stale callback
        # race). 유기(disconnect + 좀비 등록) 후에 새 워커를 만든다.
        self._abandon_analyze_worker()

        self.worker_analyze = AnalyzeWorker(url, self.cfg)
        self.worker_analyze.result_ready.connect(self.on_analyze_success)
        self.worker_analyze.error_occurred.connect(self.on_analyze_error)
        self.worker_analyze.log_full.connect(self.append_full_log)
        self.worker_analyze.start()

    def stop_analysis_anim(self, ok=True):
        """분석 완료/실패 시 최종 결과 로그를 히스토리에 박제 (마침표 애니메이션 정리 불요)."""
        if not ok:
            return

        counts = log_console.format_analysis_counts(
            len(self.extracted_data.get("v_list", [])),
            len(self.extracted_data.get("a_list", [])),
        )
        formatted_url = self.format_target_url(self.base_anim_url)
        self.append_concise_log(
                log_console.emit_event("ANAL", "OK", "YT", f"분석 완료{counts} — {formatted_url}"),
                is_status=False, is_error=False,
            )
        # 마지막 블록 철회 가드
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
        # 구성요소 확인 라인은 필터 경유 — 루틴 '최신' 라인 간결 생략 + 히스토리 전건
        self.update_worker.line.connect(self._component_line)
        self.update_worker.check_done.connect(self._on_update_check_done)
        # [응답없음 방지] 낮은 우선순위로 시작해 GIL을 메인 스레드에 양보
        self.update_worker.start(QThread.Priority.LowPriority)

    def _on_update_check_done(self, stale):
        """버전 확인 결과 처리 — 메인에 결론 한 줄, 그 뒤 POT로 진행.

        [min profile] 메인 콘솔에 emit되는 DEPS 라인은 정확히 한 줄:
        결론(최신 / 업데이트 가능 / 일시 장애). 패키지별 raw 라인은
        _component_line을 통해 상세로그로만 흘러간다. startup 게이트는
        여전히 _on_pot_provider_finished 책임.
        """
        # [결론 라인] — 메인 콘솔에 단 한 줄
        if stale:
            summary = ", ".join(f"{p} {c}→{l}" for p, c, l in stale)
            self.append_concise_log(
                log_console.emit_event("DEPS", "WARN", "-",
                                       f"업데이트 가능 — {summary}"),
                is_status=False, is_error=False,
            )
            self._stale_updates = True
        else:
            # 정상/네트워크 일시장애 모두 같은 결론 라인 — 사용자는 'OK/실패'만 알면 됨
            self.append_concise_log(
                log_console.emit_event("DEPS", "OK", "-", "DEPS 확인 완료"),
                is_status=False, is_error=False,
            )
            self._stale_updates = False
            self._start_pot_provider()
            return
        # [stale case] 포터블이면 업그레이드 skip, 그 외엔 백그라운드 자동 설치
        if getattr(sys, "frozen", False):
            self._stale_updates = False
            self._start_pot_provider()
            return
        self.update_worker = UpdateWorker(self, upgrade=True)
        self.update_worker.line.connect(self._component_line)  # detail 채널
        self.update_worker.upgrade_done.connect(self._on_auto_upgrade_done)
        self.update_worker.start()

    def _on_auto_upgrade_done(self, ok, summary):
        """기동 자동 업그레이드 결과."""
        status = "OK" if ok else "FAIL"
        self.append_concise_log(
            log_console.emit_event("SYS", status, "DEPS", f"업데이트 {summary}"),
            is_status=False, is_error=not ok,
        )
        self._start_pot_provider()

    def on_analyze_success(self, data):
        self.extracted_data = data
        self.stop_analysis_anim()
        # 콜백은 결과만 보관 — 콤보/버튼이 없으므로 UI 갱신 없음
        if data.get("is_playlist"):
            return
        # 좌측 패널이 자동 처리 — 별도 UI 갱신 없음

    def on_analyze_error(self, err_msg):
        self.stop_analysis_anim(ok=False)
        self.append_concise_log(
                log_console.emit_event("ANAL", "FAIL", "-", err_msg),
                is_status=False, is_error=True,
            )

    def update_ui_state(self):
        # URL 필드 활성도만 관리 — 진행바/콤보/버튼은 존재하지 않음
        is_running = self.ctrl.running
        startup_completed = getattr(self, "_startup_completed", False)
        self.url_input.setEnabled(not is_running and startup_completed)
        self.console.reset_status_flag()

    def showEvent(self, event):
        super().showEvent(event)
        # 첫 노출 시 viewport 실측으로 트리 예산 산정 — 이게 없으면
        # 위젯 폭=0 상태로 계산해 paint 중 재계산이 반복될 수 있다.
        if hasattr(self, "te_concise") and self.te_concise is not None:
            log_console.update_tree_budget(self.te_concise)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "te_concise"):
            log_console.update_tree_budget(self.te_concise)

    def _component_line(self, msg, is_status=False, is_error=False):
        """구성요소(POT/Update/워커) 라인 필터 — ad-hoc prefix를 TUI 컬럼 포맷으로 매핑.

        raw 메시지가 이미 "[HH:MM:SS] STAGE │ ... " 컬럼 형식이면 그대로 통과.
        그 외 POT/Update의 [v]/[!]/[~]/[+] prefix는 SYS 단계 + OK/FAIL/SKIP/RUN으로 변환.
        """
        # 1) 이미 TUI 컬럼 포맷이면 그대로 출력
        if msg.lstrip().startswith("[") and " │ " in msg and len(msg) > 18:
            self.append_concise_log(msg, is_status, is_error)
            return
        # 2) prefix로 매핑
        stripped = msg.lstrip()
        if stripped.startswith("[v]") or stripped.startswith("[+]"):
            status = "OK"
            payload = stripped.split("]", 1)[-1].strip()
        elif stripped.startswith("[!]") or stripped.startswith("[X]"):
            status = "FAIL"
            payload = stripped.split("]", 1)[-1].strip()
        elif stripped.startswith("[~]"):
            status = "RUN"
            payload = stripped.split("]", 1)[-1].strip()
        elif stripped.startswith("[?]"):
            status = "WARN"
            payload = stripped.split("]", 1)[-1].strip()
        else:
            self.append_concise_log(msg, is_status, is_error)
            return
        stage = "POT" if "PO Token" in payload or "POT" in payload else "DEPS"
        # [min profile] platform 컬럼은 단일 stage일 때 '-'로 — stage=DEPS, plat=DEPS
        # 같은 중복이 시각적 노이즈가 된다.
        self.append_concise_log(
            log_console.emit_event(stage, status, "-", payload),
            is_status=is_status, is_error=is_error,
        )

    def _mirror_full_log(self, msg):
        """상세 로그 버퍼 누적 + F12 창 미러링 (append_*_log 공용)."""
        self._full_log_buf.append(msg)
        if len(self._full_log_buf) > 5000:
            del self._full_log_buf[: len(self._full_log_buf) - 5000]
        if getattr(self, "verbose_win", None) is not None and self.verbose_win.isVisible():
            try:
                self.verbose_win.append(msg)
            except Exception:
                pass

    def append_concise_log(self, msg, is_status=False, is_error=False, fg_color=None):
        # [콘솔 출력] ConciseLogConsole로 실제 텍스트 위젯에 렌더링
        self.console.append(msg, is_status, is_error, fg_color)
        # [전체 로그 미러] 상태 줄(진행률 덮어쓰기)은 누적 제외
        if not is_status:
            self._mirror_full_log(msg)
        # 히스토리 파일 기록
        log_history.log(msg, "ERROR" if is_error else "INFO")

    def append_full_log(self, msg):
        self._mirror_full_log(msg)

    def toggle_verbose_log(self):
        """F12 상세 로그 창 토글 — 최초 진입 시 누적 버퍼로 초기화 후 미러링."""
        if getattr(self, "verbose_win", None) is not None and self.verbose_win.isVisible():
            self.verbose_win.close()
            return
        if self.verbose_win is None:
            self.verbose_win = VerboseLogWindow(self)
            content = "\n".join(self._full_log_buf)
            if not content.strip():
                content = log_console.emit_event(
                    "SYS", "OK", "LOG", "상세 로그 버퍼 비어 있음 — 다운로드 시작 시 채워짐"
                )
            self.verbose_win.set_content(content)
        self.verbose_win.show()
        self.verbose_win.raise_()
        self.verbose_win.activateWindow()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_F12:
            self.toggle_verbose_log()
            event.accept()
            return
        if event.key() == Qt.Key.Key_F1:
            self.change_folder()
            event.accept()
            return
        if event.key() == Qt.Key.Key_F2:
            _open_windows_explorer(self.cfg["download_path"])
            event.accept()
            return
        if event.key() == Qt.Key.Key_F3:
            self.open_settings()
            event.accept()
            return
        if event.key() == Qt.Key.Key_F4:
            self.pick_txt()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Escape:
            self.abort_download()
            event.accept()
            return
        super().keyPressEvent(event)

    def toggle_download(self):
        if self.ctrl.running:
            return
        try:
            targets = DownloadController.parse_targets(
                self.url_input.text().strip(),
                dedup=self.cfg.get("remove_duplicates"),
            )
        except ValueError as e:
            self.append_concise_log(str(e), False, True)
            return
        if not targets:
            return

        self.ctrl.begin()

        self.append_concise_log(
            log_console.emit_event("ANAL", "RUN", "-", "분석 시작..."),
            is_status=True, is_error=False,
        )

        self.url_input.setEnabled(False)

        live_hint = len(targets) == 1 and bool(
            (self.extracted_data.get("info") or {}).get("is_live")
        )
        # 최고 품질 자동 선택 — 콤보 박스 없이 기본값 사용
        self.ctrl.spawn_worker(
            targets,
            self.cfg,
            "auto",          # video_id — 최고 품질 자동
            "auto",          # audio_id — 최고 품질 자동
            is_live_hint=live_hint,
            v_spec=None,     # 사양 미지정 — 분석 결과 선두 포맷 기준
            audio_desc="",
        )

    def skip_current(self):
        if self.ctrl.running:
            self.ctrl.request_skip()
            self.append_concise_log(
                log_console.emit_event("DL", "SKIP", "-", "현재 항목 건너뛰기 요청됨"),
                is_status=False, is_error=False,
            )

    def add_concise_task_separator(self):
        self.console.add_task_separator()

    def on_download_finished(self, success_count, fail_count):
        self.ctrl.end()

        if success_count > 0:
            self.url_input.clear()
            self.extracted_data = {"info": None, "v_list": [], "a_list": []}

        self.url_input.setEnabled(True)
        self.update_ui_state()

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
    # [히스토리] 미처리 예외 전체 트레이스백을 히스토리 파일로 유출 — 디버깅 1차 증거
    sys.excepthook = lambda t, v, tb: log_history.exception("미처리 예외", t, v, tb)
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
