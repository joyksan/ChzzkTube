##### main.py - 메인 윈도우 및 앱 실행 진입점
import ctypes
import os
import platform
import re
import sys
import time
from collections import deque

from PySide6.QtCore import (
    QEvent,
    QObject,
    Qt,
    QThread,
    QTimer,
    Signal,
    qInstallMessageHandler,
)
from PySide6.QtGui import QFont, QFontDatabase, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
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

from chzzktube.control.controller import MediaController
from chzzktube.control.pot_manager import POTManager
from chzzktube.control.startup_coordinator import StartupCoordinator
from chzzktube.core import config, log_history, raw_log
from chzzktube.core.dl_platform import _dl_platform, _short_platform
from chzzktube.core.log_emitter import emit_component
from chzzktube.core.log_event import LogEvent
from chzzktube.core.media import short_codec
from chzzktube.core.utils import _open_windows_explorer
from chzzktube.infra.po_client import server_ping
from chzzktube.infra.pylib_bootstrap import bootstrap as _bootstrap
from chzzktube.ui import log_console, theme
from chzzktube.ui.dialogs import ExitConfirmDialog, SettingsDialog, VerboseLogWindow
from chzzktube.workers.update_worker import UpdateWorker

try:
    import winsound
except ImportError:
    winsound = None

# Qt 내부 노이즈 필터링 핸들러
def qt_message_handler(mode, context, message):
    if "must be a top level window" in message:
        return
    sys.stderr.write(message + "\n")


qInstallMessageHandler(qt_message_handler)

# [URL 인식 디바운스] 키 입력(타이핑) 침묵 기준 지연 — "타이핑 끝남"은 미래 입력
# 부재를 감지해야만 알 수 있어 키 입력 경로에선 구조상 필수다.
_ANALYZE_DEBOUNCE_MS = 900
# [벌크 입력 공출화] 붙여넣기·드래그&드롭·TXT 로드는 통째로 들어오므로 즉시 분석.
# 0ms 대신 150ms를 두는 건 프로그램적 다중 setText가 한 프레임에 겹칠 때의 점화 병합용.
_BULK_INPUT_DELAY_MS = 150
# [Followup-3] POT gate 대기 2차 워치독 — READY 개방 이후 시작된 gate hang 보호.
_POT_GATE_TIMEOUT_MS = 120_000
# [Followup-4] 폴백 유예 — GUI 블록 등으로 15초 폴백이 체인보다 먼저 만기한 경우
# 1회 유예 후 재판정한다(위양성 폴백 차단).
_FALLBACK_GRACE_MS = 3000
# [Followup-6] 분석 실패가 봇 체크/PO 토큰 사유인지 판별하는 마커(소문자 비교).
_BOT_CHECK_MARKERS = (
    "sign in to confirm you're not a bot",
    "not a bot",
    "po token",
    "failed to extract any player response",
    "confirm your age",
)


def _needs_pot_retry(err_msg: str) -> bool:
    """[Followup-6] 분석 실패가 봇 체크/PO 토큰 사유인지 — POT 기동 후 1회 재시도 대상."""
    text = (err_msg or "").lower()
    return any(marker in text for marker in _BOT_CHECK_MARKERS)

# [E1 단일화] POT 게이트 판정 — 3곳에 복사되던 판정식을 단일 진실로 통합한다.
# HANDOVER §3 '다운로드 게이트' 상수 목록의 유일한 코드 출처이다.
_POT_AVAIL_GATED = ("needs_auth", "premium_only", "subscriber_only", "private")


def _needs_pot(info):
    """PO 토큰 필요 여부 — age_limit>0 ∨ availability∈게이트 집합."""
    if not info:
        return False
    age_limit = info.get("age_limit") or 0
    if age_limit > 0:
        return True
    availability = info.get("availability") or ""
    return isinstance(availability, str) and availability.lower() in _POT_AVAIL_GATED


APP_NAME = config._APP_NAME
APP_VERSION = config._APP_VERSION
BASE_DIR = config.BASE_DIR
CONFIG_DIR = config.CONFIG_DIR
CONFIG_FILE = config.CONFIG_FILE
ICON_PATH = config.ICON_PATH
DEFAULT_CONFIG = config.default_config()


class _GuiLogBridge(QObject):
    """순수 raw_log 백그라운드 스레드 이벤트를 Qt GUI 루프로 안전하게 흡수하는 브리지.

    raw_log의 데몬 dispatcher 스레드는 본 브리지의 Signal.emit만 호출하고,
    슬롯은 QueuedConnection으로 메인 스레드 이벤트 루프에서 실행된다 —
    배경 스레드의 QTextEdit 직접 접근(세그폴트/레이스 원인)을 차단한다.
    raw_log는 표준 라이브러리 기반 순수성을 유지하고, 스레드 경계 책임은
    GUI를 점유한 수신층(main.py)이 진다.
    """

    tui_signal = Signal(object, bool, bool)   # (event, is_status, is_error)
    full_signal = Signal(object, bool)        # (event, is_status)


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

        # 다운로드 + 분석 세션 상태/워커는 컨트롤러가 소유 (ctrl.state 단일 참조)
        self.ctrl = MediaController(self)
        self.extracted_data = {"info": None, "v_list": [], "a_list": []}

                # StartupCoordinator: DEPS/POT/업데이트 시그널을 중앙에서 수신하고 3대 로그에 전파
        # POTManager: POT 서버 수명주기 단일 관리자 (prewarm + gate 통합).
        # 단일 인스턴스 원칙 (HANDOVER §7): 시그널 연결 전 최초 1회만 생성
        self._pot_manager = POTManager()
        self._startup_coord = StartupCoordinator(self._pot_manager, self)
        self._pot_manager.pot_finished.connect(self._on_pot_finished)
        # [P5] POT 수급/빌드 진행 중에는 기동 폴백 타이머를 연장한다(맹인 폴백 방지).
        self._pot_manager.pot_status_changed.connect(self._on_pot_activity)
        # [Followup-1] POT 빌드 수급 하트비트 → 폴백 타이머 연장
        self._pot_manager.pot_work_tick.connect(self.defer_fallback_timer)
        self._startup_coord.ui_unlocked.connect(self._on_startup_unlocked)

        self.settings_dlg = None
        self.verbose_win = None

        self.analyze_timer = QTimer()
        self.analyze_timer.setSingleShot(True)
        self.analyze_timer.timeout.connect(self.run_analysis)

        # ── 분석 워커 시그널 바인딩 (Controller → View 포워딩) ──
        self.ctrl.analyze_result_ready.connect(self.on_analyze_success)
        self.ctrl.analyze_error_occurred.connect(self.on_analyze_error)

        # POTManager가 서버 수명주기를 담당
        self._startup_completed = False
        self._pending_download = None

        self.init_ui()

        # 구성요소(yt-dlp/streamlink) 자동 업데이트 확인 — 기동 직후 비동기 1회
        QTimer.singleShot(500, self._start_update_check)

        # [응답없음 폴백] 구성요소 체인(POT 포함)이 15초 안에 끝나지 않으면
        # 입력을 강제 개방 — URL 잠금이 영구화되지 않게 한다.
        # [P5] 단발 singleShot → 인스턴스 타이머 승격. 15초 단발 타이머는 "의존성을
        # 열심히 받는 중"과 "멈춤"을 구분하지 못하는 맹인이었다 — 실제 수급 작업
        # 진행 신호(UpdateWorker.work_tick / POT 상태 전이)가 오면 수명을 연장한다.
        self._fallback_timer = QTimer(self)
        self._fallback_timer.setSingleShot(True)
        self._fallback_timer.timeout.connect(self._force_unlock_input)
        self._fallback_timer.start(15000)

        # [Followup-3] POT gate 대기 2차 워치독 — READY 개방 이후 시작된 gate hang에도
        # 보호를 둔다(1차는 위 폴백). 만료 시 POT 작업을 트리 종료하고 큐를 푼다.
        self._gate_watchdog = QTimer(self)
        self._gate_watchdog.setSingleShot(True)
        self._gate_watchdog.timeout.connect(self._on_gate_timeout)
        # [Followup-5] DEPS 검사의 실제 FAIL(미설치 등)은 게이트 사유로 승격한다.
        self._deps_failed = []
        # [Followup-6] 봇 체크 실패 시 POT 기동 후 1회 재시도용 상태.
        self._pot_retry_url = None
        self._pot_retry_pending = False
        self._pot_retry_done = set()

    def _platform_of_url(self) -> str:
            """[결함 수리] stop_analysis_anim 호출 대비 URL 플랫폼 축약 기호 추출."""
            url = self.url_input.text().strip()
            return _short_platform(_dl_platform(url))

    def closeEvent(self, event):
        # 1. 최소화 상태 해제 및 Qt 표준 창 활성화
        self.setWindowState(
            self.windowState() & ~Qt.WindowState.WindowMinimized
            | Qt.WindowState.WindowActive
        )
        self.activateWindow()

        is_running = self.ctrl.state.get("running", False)
        parent_dlg = (
            self.settings_dlg
            if (hasattr(self, "settings_dlg")
                and self.settings_dlg
                and self.settings_dlg.isVisible())
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
            if self.ctrl.worker_dl is not None and self.ctrl.worker_dl.isRunning():
                raw_log.raw(
                    "shutdown",
                    LogEvent(
                        stage="SYS", status="WARN",
                        msg="shutdown: download worker not stopped (1s) — cancelling then exiting",
                        is_error=False,
                    ),
                    to_tui=False,
                )
            # [스레드 경계] 종료 전 러닝 QThread 회수 — 좀비 분석 워커/기동 워커가
            # 살아있으면 Qt가 "QThread: Destroyed while thread is still running"
            # 경고와 함께 종료 크래시를 낼 수 있다. terminate 금지 원칙 유지,
            # 짧은 wait만 시도 (워커들은 취소 플래그로 자연 종료를 약속받는다).
            for w in list(getattr(self, "_zombie_workers", []) or []):
                if w is not None and w.isRunning():
                    w.wait(1500)
                    if w.isRunning():
                        raw_log.raw(
                            "shutdown",
                            LogEvent(
                                stage="SYS",
                                status="WARN",
                                msg="shutdown: orphaned analyze worker (1.5s) — forcing exit",
                                is_error=False,
                            ),
                            to_tui=False,
                        )
            # POTManager가 서버/워커 정리 담당
            self._pot_manager.cancel()

            for name in ("update_worker",):
                w = getattr(self, name, None)
                if w is not None and w.isRunning():
                    w.wait(1500)
                    if w.isRunning():
                        raw_log.raw(
                            "shutdown",
                            LogEvent(
                                stage="SYS",
                                status="WARN",
                                msg=f"shutdown: startup worker ({name}) not stopped (1.5s) — forcing exit",
                                is_error=False,
                            ),
                            to_tui=False,
                        )

            # 다운로드 워커의 라이브 녹화 프로세스 정리
            if hasattr(self.ctrl, "worker_dl") and self.ctrl.worker_dl is not None:
                try:
                    if hasattr(self.ctrl.worker_dl, "kill_live_process"):
                        self.ctrl.worker_dl.kill_live_process()
                except OSError:
                    pass

            log_history.session_end()
            raw_log.flush()
            raw_log.shutdown()
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
            except OSError:
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
        except (AttributeError, OSError):
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
        """[TUI Refactor] Hyper-Minimal Modern TUI — flat, borderless, mono.

        ├── Path ...  │ [F1] [F2] │ [F12] [F3]
        ├── ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─
        │ > [url_input..........................] [F4] [ENTER]
        ├── ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─
        └── [10:54:14] DEPS  │ OK  │ ...        ← console (stretch=1)
        """
        # ── 중앙 위젯 / 메인 레이아웃 (flat, no master wrapper) ──
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(12, 8, 12, 8)
        main_layout.setSpacing(0)

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

        # ── 헬퍼: 힌트 버튼 사이 딤 '│' 구분자 ──
        def _tui_sep():
            sep = QLabel("│")
            sep.setStyleSheet(
                f"color: {theme.FG_DIM}; border: none; background: transparent; padding: 0px;"
            )
            return sep

        # ── 헬퍼: 1px 섹션 구분선 ──
        def _separator():
            line = QFrame()
            line.setProperty("class", "tui-separator")
            line.setFrameShape(QFrame.Shape.HLine)
            line.setFrameShadow(QFrame.Shadow.Plain)
            line.setStyleSheet("QFrame { background-color: #1a1a1a; max-height: 1px; min-height: 1px; border: none; }")
            line.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            return line

        # ════════════════════════════════════════════════════════════════════
        # Layer 1: Configuration (flat — no border, no title)
        # ════════════════════════════════════════════════════════════════════
        self.header_group = QGroupBox("")
        self.header_group.setObjectName("header_group")
        self.header_group.setProperty("class", "tui-panel")
        self.header_group.style().unpolish(self.header_group)
        self.header_group.style().polish(self.header_group)
        hlay = QHBoxLayout(self.header_group)
        hlay.setContentsMargins(0, 0, 0, 0)
        hlay.setSpacing(6)

        self.path_label = QLabel()
        self.path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.path_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._update_path_label()
        hlay.addWidget(self.path_label, 1)

        self.btn_change = _tui_tag("[ F1: Change ]", "Change download folder (F1)", self.change_folder)
        self.btn_open = _tui_tag(
            "[ F2: Open ]",
            "Open download folder (F2)",
            lambda: _open_windows_explorer(self.cfg["download_path"]),
        )
        hlay.addWidget(self.btn_change)
        hlay.addWidget(self.btn_open)

        # v_line: Change/Open과 Full Log/Settings 그룹 사이 시각 구분
        self.v_line = QLabel("\u2502")
        self.v_line.setProperty("class", "tui-sep")
        hlay.addWidget(self.v_line)

        self.btn_full_log = _tui_tag("[ F12: Full Log ]", "Toggle full log window (F12)", self.toggle_verbose_log)
        self.btn_settings = _tui_tag("[ F3: Settings ]", "Open settings (F3)", self.open_settings)
        hlay.addWidget(self.btn_full_log)
        hlay.addWidget(self.btn_settings)

        main_layout.addWidget(self.header_group)

        # ── 1px 구분선 ──
        main_layout.addWidget(_separator())

        # ════════════════════════════════════════════════════════════════════
        # Layer 2: Input & Action (flat — no border, prompt-style)
        # ════════════════════════════════════════════════════════════════════
        self.input_group = QGroupBox("")
        self.input_group.setObjectName("input_group")
        self.input_group.setProperty("class", "tui-panel")
        self.input_group.style().unpolish(self.input_group)
        self.input_group.style().polish(self.input_group)
        ilay = QHBoxLayout(self.input_group)
        ilay.setContentsMargins(0, 0, 0, 0)
        ilay.setSpacing(6)

        # 프롬프트 `>` 기호 — 콘솔 출력처럼 보이게
        self.prompt_label = QLabel(">")
        self.prompt_label.setStyleSheet(
            "color: #4ec9b0;font-weight: bold; border: none; background: transparent; padding: 0px;")
        ilay.addWidget(self.prompt_label)

        self.url_input = QLineEdit()
        self.url_input.setObjectName("url_input")
        self.url_input.setPlaceholderText("URL, playlist, or channel URL...")
        self.url_input.setClearButtonEnabled(False)
        self.url_input.installEventFilter(self)
        self.url_input.textChanged.connect(self.on_url_changed)
        self.url_input.setDragEnabled(True)
        self.url_input.acceptDrops()
        self.url_input.dropEvent = lambda e: self._on_url_drop(e.mimeData())
        self.url_input.returnPressed.connect(self.toggle_download)
        ilay.addWidget(self.url_input, 1)

        self.btn_txt = _tui_tag("[ F4: Load .txt ]", "Load URL list from TXT (F4)", self.pick_txt)
        ilay.addWidget(self.btn_txt)
        ilay.addWidget(_tui_sep())

        self.btn_enter = _tui_tag("[ ENTER: Start ]", "Start download (Enter)", self.toggle_download)
        self.btn_esc = _tui_tag("[ ESC: Clear ]", "Clear input (Esc) — abort when running", self._esc_action)
        ilay.addWidget(self.btn_esc)
        ilay.addWidget(_tui_sep())
        ilay.addWidget(self.btn_enter)

        main_layout.addWidget(self.input_group)
        main_layout.addWidget(_separator())

        # Layer 3: Live Console Monitor
        self.console_group = QGroupBox("")
        self.console_group.setObjectName("console_group")
        self.console_group.setProperty("class", "tui-panel")
        self.console_group.style().unpolish(self.console_group)
        self.console_group.style().polish(self.console_group)
        self.console_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        clay = QVBoxLayout(self.console_group)
        clay.setContentsMargins(0, 0, 0, 0)
        clay.setSpacing(0)

        self.te_concise = QTextEdit()
        self.te_concise.setObjectName("console_log")
        self.te_concise.setReadOnly(True)
        self.te_concise.document().setDocumentMargin(0)
        self.console = log_console.ConciseLogConsole(self.te_concise)

        clay.addWidget(self.te_concise, 1)
        main_layout.addWidget(self.console_group, stretch=1)

        self._full_log_buf: deque[str] = deque(maxlen=4096)
        self._full_log_win_n = 0
        self._last_status_line = ""

        self._gui_bridge = _GuiLogBridge(self)
        self._gui_bridge.tui_signal.connect(self._render_concise, Qt.ConnectionType.QueuedConnection)
        self._gui_bridge.full_signal.connect(self._mirror_event_full, Qt.ConnectionType.QueuedConnection)

        raw_log.subscribe_concise(self._gui_bridge.tui_signal.emit)
        raw_log.subscribe_full(self._gui_bridge.full_signal.emit)
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
            if path.startswith(("http://", "https://")):
                self.url_input.setText(path)
                return

    def pick_txt_from_path(self, path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = [l.strip() for l in f if l.strip() and not l.strip().startswith("#")]
            if lines:
                self.url_input.setText("\n".join(lines))
                self.append_concise_log(
                    log_console.emit_event("SYS", "OK", "MAIN", f"TXT — {len(lines)} URLs"),
                    is_status=False,
                    is_error=False,
                )
        except OSError:
            self.append_concise_log(
                log_console.emit_event("SYS", "FAIL", "MAIN", "TXT read fail"),
                is_status=False,
                is_error=True,
            )

    def abort_download(self):
        if self.ctrl.running:
            self.ctrl.request_cancel()
            self.append_concise_log(
                log_console.emit_event("DL", "ABORT", "-", "download canceled by user"),
                is_status=False,
                is_error=True,
            )

    def _esc_action(self):
        state = self.get_current_app_state()
        if state == "RUNNING":
            self.abort_download()
        elif state == "PICKING":
            self._cancel_pick()
        elif state == "ANALYZING":
            self.ctrl.request_cancel()
        else:
            self.url_input.clear()

    def eventFilter(self, obj, event):
        if (
            obj is self.url_input
            and event.type() == QEvent.Type.KeyPress
            and event.key() == Qt.Key.Key_Escape
        ):
            self._esc_action()
            return True
        return super().eventFilter(obj, event)

    def _update_path_label(self):
        path = self.cfg.get("download_path", "")
        self.path_label.setText(
            f"<span style='color:#4ec9b0; font-weight:bold;'>Path</span> {path}"
        )

    def change_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select Download Folder", self.cfg["download_path"]
        )
        if folder:
            self.cfg["download_path"] = os.path.normpath(folder)
            self._update_path_label()
            self.save_cfg()
            self.append_concise_log(
                log_console.emit_event("SYS", "OK", "CFG", f"path → {self.cfg['download_path']}"),
                is_status=False,
                is_error=False,
            )

    def format_target_url(self, url, max_len=50):
        return log_console.format_target_url(url, max_len)

    def open_settings(self):
        if hasattr(self, "settings_dlg") and self.settings_dlg and self.settings_dlg.isVisible():
            self.settings_dlg.activateWindow()
            return
        self.settings_dlg = SettingsDialog(self)
        self.settings_dlg.show()

    def pick_txt(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select TXT File",
            self.cfg["download_path"],
            "Text Files (*.txt);;All Files (*.*)",
        )
        if path:
            self.url_input.setText(os.path.normpath(path))

    def on_url_changed(self):
        self.analyze_timer.stop()
        text = self.url_input.text().strip()

        if not text:
            self._last_input_len = 0
            self.extracted_data = {"info": None, "v_list": [], "a_list": []}
            self.ctrl._abandon_analyzer()
            self.console.clear_status_line()
            self._discard_analysis_result()
            return

        prev_len = getattr(self, "_last_input_len", 0)
        self._last_input_len = len(text)
        is_bulk_input = (len(text) - prev_len) > 1

        is_idle_state = not self.ctrl.running and not self.ctrl.picking
        is_valid_pattern = "://" in text or bool(re.search(r"\S\.\S", text))

        if is_idle_state and getattr(self, "_startup_completed", False) and is_valid_pattern:
            delay = _BULK_INPUT_DELAY_MS if is_bulk_input else _ANALYZE_DEBOUNCE_MS
            self.analyze_timer.start(delay)

    def _ensure_pot_for_info(self, info):
        info = info or {}
        needs_pot = _needs_pot(info)
        age_limit = info.get("age_limit") or 0
        availability = info.get("availability") or ""

        event = LogEvent(
            stage="POT",
            status="RUN",
            scope="POT",
            msg=f"gated={needs_pot} age_limit={age_limit if info else '-'} availability={availability or '-'}",
        )
        raw_log.raw("pot-gate", event, to_tui=True)

        if needs_pot:
            self.append_concise_log(
                log_console.emit_event("POT", "RUN", "POT", "starting..."),
                is_status=True,
                is_error=False,
            )
            self._pot_manager.ensure_ready("gate")
            self._start_gate_watchdog()

    def run_analysis(self):
        url = self.url_input.text().strip()
        if not url:
            return
        self.append_concise_log(
            log_console.emit_event("ANAL", "RUN", "YT", "analyzing..."),
            is_status=True,
            is_error=False,
        )
        self._discard_analysis_result()
        self.base_anim_url = url
        self.ctrl.spawn_analyzer(url, self.cfg)
        self.update_ui_state()

    def stop_analysis_anim(self, ok=True):
        if not ok:
            return

        data = self.extracted_data or {}
        info = data.get("info") or {}
        v_list = data.get("v_list", [])
        a_list = data.get("a_list", [])
        uploader = (
            info.get("uploader")
            or info.get("channel")
            or info.get("uploader_id")
            or info.get("creator")
            or ""
        )
        title = info.get("title") or data.get("title") or ""
        meta = " · ".join(x for x in (uploader, title) if x)

        platform_tag = self._platform_of_url()

        v_first = v_list[0] if v_list else {}
        res = ""
        if isinstance(v_first, dict):
            h = v_first.get("height") or v_first.get("v_height") or 0
            fps = v_first.get("fps") or v_first.get("v_fps") or 0
            if h:
                res = f"{h}p{fps}" if fps else f"{h}p"

        counts = log_console.format_analysis_counts(len(v_list), len(a_list))
        base_msg = f"analyzed{counts}"
        if meta:
            base_msg += f" · {meta[:80]}"
        anal_msg = f"[{res}] {base_msg}" if res else base_msg
        raw_log.raw(
            "anal",
            LogEvent(
                stage="ANAL",
                status="OK",
                scope=platform_tag,
                msg=anal_msg,
                is_status=True,
                is_error=False,
            ),
            to_tui=True,
        )

        self._analysis_block_active = True
        self._analysis_block_count = self.console.last_status_block_count
        self._analysis_last_line = self.console.last_content_block_text()

        self._emit_format_logs(v_list, a_list, platform_tag)

    def _emit_format_logs(self, v_list, a_list, platform_tag):
        v_seen = list(dict.fromkeys(short_codec(f.get("vcodec")) for f in v_list if f.get("vcodec")))
        a_seen = list(dict.fromkeys(short_codec(f.get("acodec")) for f in a_list if f.get("acodec")))
        codecs = "/".join([c for c in ("/".join(v_seen[:2]), "/".join(a_seen[:2])) if c])
        if not codecs:
            return
        raw_log.raw(
            "anal",
            LogEvent(
                stage="ANAL",
                status="OK",
                scope=platform_tag,
                msg=f"[{codecs}] streams isolated",
            ),
            to_tui=True,
        )

    def _format_analysis_summary(self):
        data = self.extracted_data or {}
        info = data.get("info") or {}
        uploader = (
            info.get("uploader")
            or info.get("channel")
            or info.get("uploader_id")
            or info.get("creator")
            or ""
        )
        title = info.get("title") or data.get("title") or ""
        meta = " · ".join(x for x in (uploader, title) if x)
        if not meta:
            return ""
        return " — " + meta[:80]

    def _discard_analysis_result(self):
        if not getattr(self, "_analysis_block_active", False):
            return
        last_text = self.console.last_content_block_text()
        if last_text != getattr(self, "_analysis_last_line", None):
            self._analysis_block_active = False
            return
        self.console.remove_last_blocks(getattr(self, "_analysis_block_count", 0))
        self._analysis_block_active = False

    def _retire_qthread(self, worker):
        if worker is None:
            return
        retired = getattr(self, "_retired_workers", None)
        if retired is None:
            retired = []
            self._retired_workers = retired
        if worker.isFinished() or worker in retired:
            return
        worker.finished.connect(worker.deleteLater)
        worker.finished.connect(lambda w=worker: self._drop_retired(w))
        retired.append(worker)

    def _drop_retired(self, worker):
        retired = getattr(self, "_retired_workers", [])
        try:
            retired.remove(worker)
        except ValueError:
            pass

    def _start_update_check(self):
        if hasattr(self, "update_worker"):
            self._retire_qthread(self.update_worker)
        self.update_worker = UpdateWorker(
            self,
            upgrade=False,
            channel=self.cfg.get("update_channel", "stable"),
            check_updates=self.cfg.get("auto_update_check", True),
        )
        self.update_worker.check_done.connect(self._on_update_check_done)
        # [Followup-5] DEPS 검사 FAIL 목록 — 게이트 판정에 반영
        self.update_worker.deps_failed.connect(self._on_deps_failed)
        self.update_worker.start(QThread.Priority.LowPriority)

    def _on_update_check_done(self, stale):
        if stale:
            summary = ", ".join(f"{label} {cur}→{latest}" for label, _, cur, latest in stale)
            self.append_concise_log(
                log_console.emit_event("DEPS", "WARN", "-", f"update — {summary}"),
                is_status=False,
                is_error=False,
            )
            self._stale_updates = True
        else:
            self._stale_updates = False
            self.append_concise_log(
                log_console.emit_event("DEPS", "", "-", "deps ok"),
                is_status=False,
                is_error=False,
            )

        self._retire_qthread(self.update_worker)
        self.update_worker = UpdateWorker(
            self,
            upgrade=True,
            stale_updates=stale,
            channel=self.cfg.get("update_channel", "stable"),
            check_updates=self.cfg.get("auto_update_check", True),
        )
        self.update_worker.upgrade_done.connect(self._startup_coord.report_upgrade)
        # [P5] 수급 진행 하트비트 → 폴백 타이머 연장(맹인 15초 폴백 방지)
        self.update_worker.work_tick.connect(self.defer_fallback_timer)
        self.update_worker.start()
        # [P1] deps 게이트의 의미는 "검사 단계 완료"다 — stale(업데이트 대상) 존재는 게이트 사유가 아니다.
        # 업데이트 적용은 업데이트 워커의 일이며, READY 게이트를 막으면 안 된다.
        # (stale 발생 시 deps_ok=False로 잠겨, 업데이트가 감지되는 모든 기동이 정상
        #  READY 대신 15초 폴백 문구로만 열리는 구조적 결함이 있었다.)
        # [Followup-5] 실제 FAIL(미설치/미발견)은 게이트 사유로 승격한다.
        if getattr(self, "_deps_failed", []):
            self._startup_coord.report_deps(False, "deps fail: " + ", ".join(self._deps_failed))
        else:
            self._startup_coord.report_deps(True, "deps ok" if not stale else "update")
        self._pot_manager.ensure_ready("prewarm")

    def _on_deps_failed(self, labels):
        """[Followup-5] DEPS 검사 FAIL 목록 수신 — 게이트 판정에 반영한다."""
        self._deps_failed = list(labels or [])
        if self._deps_failed:
            self.append_concise_log(
                log_console.emit_event("DEPS", "FAIL", "MAIN",
                                       "deps fail: " + ", ".join(self._deps_failed)),
                is_status=False,
                is_error=True,
            )

    def _on_pot_finished(self, ok: bool, msg: str):
        self._stop_gate_watchdog()
        # [Followup-6] 봇 체크 재시도가 대기 중이면 POT 준비와 함께 재분석한다.
        if ok and self._pot_retry_pending:
            self._run_pending_retry()
            return
        pending = getattr(self, "_pending_download", None)
        if pending is None or not ok or not self._pot_manager.is_ready():
            return
        targets, v_id, a_id = pending
        self._pending_download = None
        self._start_download(targets, v_id, a_id)

    def _on_startup_unlocked(self):
        self._startup_completed = True
        self.update_ui_state()

    def _force_unlock_input(self):
        if self._startup_completed:
            return
        # [Followup-4] 유예 1회 — GUI 블록 등으로 15초 폴백이 체인보다 먼저 만기한
        # 경우를 건너뛴다. 체인이 실제로 동작 중이면 큐에 적재된 진행 신호가 도착할
        # 짧은 유예를 주고, 그래도 열리지 않으면 폴백으로 개방한다(잠금 영구화 방지).
        if not getattr(self, "_fallback_grace_used", False) and self._startup_chain_active():
            self._fallback_grace_used = True
            self._fallback_timer.start(_FALLBACK_GRACE_MS)
            return
        self._log_gate_pending("fallback fired")
        self._startup_coord.force_unlock()

    def _startup_chain_active(self) -> bool:
        """[Followup-4] 기동 체인이 실제로 동작 중인지 — 폴백 유예 판정."""
        if self._pot_manager.is_busy():
            return True
        worker = getattr(self, "update_worker", None)
        return bool(worker is not None and worker.isRunning())

    def _log_gate_pending(self, reason: str):
        """[Followup-4] 게이트 대기 원인을 F12/history에 남긴다(TUI 폭 예산 보존)."""
        names = [f"pot={self._pot_manager.mode}"]
        worker = getattr(self, "update_worker", None)
        if worker is not None and worker.isRunning():
            names.append("deps=running")
        if getattr(self, "_deps_failed", []):
            names.append("deps_fail=" + ",".join(self._deps_failed))
        raw_log.raw(
            "startup",
            LogEvent(stage="SYS", status="RUN", scope="MAIN",
                     msg=f"{reason} · " + " ".join(names)),
            to_tui=False,
        )

    def _start_gate_watchdog(self):
        """[Followup-3] POT gate 대기 2차 워치독 기동."""
        self._gate_watchdog.start(_POT_GATE_TIMEOUT_MS)

    def _stop_gate_watchdog(self):
        self._gate_watchdog.stop()

    def _on_gate_timeout(self):
        """[Followup-3] gate hang — POT 작업을 트리 종료하고 대기 큐를 해제한다."""
        if not self._pot_manager.is_busy():
            return
        self._pot_manager.cancel()
        self.append_concise_log(
            log_console.emit_event("SYS", "WARN", "POT", "gate timeout — pot abandoned"),
            is_status=False,
            is_error=False,
        )
        self._pending_download = None
        self.update_ui_state()

    def _maybe_retry_analysis(self, err_msg: str) -> bool:
        """[Followup-6] 봇 체크 실패 시 POT 서버 기동 후 1회만 재분석을 큐잉한다."""
        if not _needs_pot_retry(err_msg):
            return False
        if self._pot_retry_pending:
            return False
        url = self.url_input.text().strip()
        if not url or url in self._pot_retry_done:
            return False
        self._pot_retry_done.add(url)
        self._pot_retry_url = url
        self._pot_retry_pending = True
        self.append_concise_log(
            log_console.emit_event("POT", "RUN", "POT",
                                   "bot-check detected — starting pot server, retrying once"),
            is_status=True,
            is_error=False,
        )
        if self._pot_manager.is_ready():
            self._run_pending_retry()
        else:
            self._pot_manager.ensure_ready("gate")
            self._start_gate_watchdog()
        return True

    def _run_pending_retry(self):
        """[Followup-6] POT 준비 완료 후 재분석 — textChanged 디바운스로 재진입한다."""
        url = self._pot_retry_url
        self._pot_retry_pending = False
        self._pot_retry_url = None
        if not url:
            return
        self.append_concise_log(
            log_console.emit_event("POT", "RUN", "YT", "retrying analysis with po token"),
            is_status=True,
            is_error=False,
        )
        self.url_input.setText(url)

    def defer_fallback_timer(self, extension_ms: int = 15000):
        """[P5] 수급 작업 진행 중에는 폴백 타이머를 연장해 섣부른 UI 개방을 막는다.

        15초 단발 타이머는 수급 진행 중과 멈춤을 구분하지 못했다. 실제 작업
        하트비트(UpdateWorker.work_tick / POT 상태 전이)마다 카운트다운을 되감아,
        진짜 무응답일 때만 폴백이 발화한다.
        """
        if not self._startup_completed and self._fallback_timer.isActive():
            self._fallback_timer.start(extension_ms)

    def _on_pot_activity(self, status: str):
        """[P5] POT 수급/기동 국면(prewarm·starting)에서는 폴백을 서두르지 않는다."""
        if status in ("prewarm", "starting"):
            self.defer_fallback_timer()

    def _is_stale_analyze_signal(self) -> bool:
        """유령 분석 결과 판별 — 지운 뒤 "stream analyzed"가 한 번 더 뜨는 버그 차단."""
        if not self.ctrl.state.get("analyzing"):
            return True
        return not bool(self.url_input.text().strip())

    def on_analyze_success(self, data):
        if self._is_stale_analyze_signal():
            return
        self.ctrl.state["analyzing"] = False
        self.extracted_data = data
        self._ensure_pot_for_info(data.get("info"))
        if data.get("is_playlist"):
            self.stop_analysis_anim()
            self.update_ui_state()
            return
        if getattr(self, "_pick_pending", False):
            self._pick_pending = False
            self._show_pick_menu(data)
            self.update_ui_state()
            return
        self.stop_analysis_anim()
        self.update_ui_state()

    def on_analyze_error(self, err_msg):
        if self._is_stale_analyze_signal():
            return
        self.ctrl.state["analyzing"] = False
        pick_pending = getattr(self, "_pick_pending", False)
        self._pick_pending = False
        if pick_pending:
            self.ctrl.state["picking"] = False
        self.stop_analysis_anim(ok=False)
        self.update_ui_state()
        self.append_concise_log(
            log_console.emit_event("ANAL", "FAIL", "-", err_msg),
            True,
            True,
        )
        # [Followup-6] 봇 체크/PO 토큰 사유면 POT 기동 후 1회 재시도를 큐잉한다.
        if self._maybe_retry_analysis(err_msg):
            return

    def get_current_app_state(self) -> str:
        # [P3b] POT 백그라운드 작업(is_busy)은 입력 잠금 사유가 아니다 — 그 역할은
        # toggle_download의 큐잉(_pending_download)이 맡는다. is_busy를 STARTUP 사유로
        # 두면 프리웜 진행 중 ENTER가 큐잉 분기에 도달하지 못하고 무반응으로 끝났다.
        if not getattr(self, "_startup_completed", False):
            return "STARTUP"
        if self.ctrl.running:
            return "RUNNING"
        if self.ctrl.analyzing:
            return "ANALYZING"
        if self.ctrl.picking:
            return "PICKING"
        return "IDLE"

    def update_ui_state(self):
        state = self.get_current_app_state()

        self.url_input.setEnabled(state in ("IDLE", "PICKING"))

        self.btn_open.setEnabled(True)
        self.btn_change.setEnabled(state == "IDLE")
        self.btn_settings.setEnabled(state in ("IDLE", "RUNNING"))
        self.btn_txt.setEnabled(state == "IDLE")

        if state == "STARTUP":
            self.btn_esc.setEnabled(False)
            self.btn_esc.setText("[ ESC: Clear ]")
        elif state == "RUNNING":
            self.btn_esc.setEnabled(True)
            self.btn_esc.setText("[ ESC: Abort ]")
        elif state in ("ANALYZING", "PICKING"):
            self.btn_esc.setEnabled(True)
            self.btn_esc.setText("[ ESC: Cancel ]")
        else:
            self.btn_esc.setEnabled(True)
            self.btn_esc.setText("[ ESC: Clear ]")

        if state == "IDLE":
            self.btn_enter.setEnabled(True)
            self.btn_enter.setText("[ ENTER: Start ]")
        elif state == "PICKING":
            self.btn_enter.setEnabled(True)
            self.btn_enter.setText("[ ENTER: Select ]")
        else:
            self.btn_enter.setEnabled(False)
            self.btn_enter.setText("[ ENTER: Start ]")

        self.console.reset_status_flag()

    def showEvent(self, event):
        super().showEvent(event)
        if hasattr(self, "console"):
            self.console.on_resize()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "console"):
            self.console.on_resize()

    def _render_concise(self, event, is_status=False, is_error=False):
        if isinstance(event, LogEvent):
            line = log_console.format_log_line_for_event(event)
            no_wrap = True
        else:
            line = str(event)
            no_wrap = False
        if len(line) > 4096:
            line = line[:4096] + "…"
        self.console.append(line, is_status, is_error, no_wrap=no_wrap)

    def _mirror_event_full(self, event, is_status=False):
        if isinstance(event, LogEvent):
            line = event.msg if event.msg else ""
        else:
            line = str(event)
        if is_status:
            self._last_status_line = line
        self._mirror_full_log(line, is_status)

    def _mirror_full_log(self, msg, is_status=False):
        msg = str(msg)
        if len(msg) > 4096:
            msg = msg[:4096] + "…"
        ts = time.strftime("%H:%M:%S")
        stamped = "\n".join(f"[{ts}] {l}" if l else f"[{ts}]" for l in msg.split("\n"))
        if not is_status:
            self._full_log_buf.append(stamped)
        win = getattr(self, "verbose_win", None)
        win_visible = win is not None and win.isVisible()
        if not is_status and win_visible:
            self._full_log_win_n = len(self._full_log_buf)
        if win_visible:
            try:
                win.append(stamped, is_status)
            except (AttributeError, RuntimeError):
                pass

    def append_concise_log(self, msg, is_status=False, is_error=False, fg_color=None):
        if isinstance(msg, LogEvent):
            msg.is_status = is_status
            msg.is_error = is_error
            raw_log.raw("ui", msg, to_tui=True)
        else:
            raw_log.raw("ui", msg, is_status=is_status, is_error=is_error, to_tui=True)

    def toggle_verbose_log(self):
        if getattr(self, "verbose_win", None) is not None and self.verbose_win.isVisible():
            self.verbose_win.close()
            return
        if self.verbose_win is None:
            self.verbose_win = VerboseLogWindow(self)
            content = "\n".join(self._full_log_buf)
            if not content.strip():
                content = log_console.emit_event("SYS", "OK", "LOG", "empty buffer")
            self.verbose_win.set_content(content)
            self._full_log_win_n = len(self._full_log_buf)
        else:
            pending = list(self._full_log_buf)[self._full_log_win_n:]
            for line in pending:
                self.verbose_win.append(line, False)
            self._full_log_win_n = len(self._full_log_buf)
        self.verbose_win.show()
        self.verbose_win.raise_()
        self.verbose_win.activateWindow()

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key.Key_F12:
            self.toggle_verbose_log()
            event.accept()
            return
        if key == Qt.Key.Key_F1:
            self.change_folder()
            event.accept()
            return
        if key == Qt.Key.Key_F2:
            _open_windows_explorer(self.cfg["download_path"])
            event.accept()
            return
        if key == Qt.Key.Key_F3:
            self.open_settings()
            event.accept()
            return
        if key == Qt.Key.Key_F4:
            self.pick_txt()
            event.accept()
            return
        if key == Qt.Key.Key_Escape:
            self._esc_action()
            event.accept()
            return
        super().keyPressEvent(event)

    def toggle_download(self):
        state = self.get_current_app_state()
        if state == "PICKING":
            self._submit_pick()
            return
        if state != "IDLE":
            return
        try:
            targets = MediaController.parse_targets(
                self.url_input.text().strip(),
                dedup=self.cfg.get("remove_duplicates"),
            )
        except ValueError as e:
            self.append_concise_log(
                log_console.emit_event("SYS", "FAIL", "-", f"parse error: {e}"),
                False,
                True,
            )
            return
        if not targets:
            return

        if self.cfg.get("pick_format") and len(targets) == 1:
            self._start_pick_flow(targets[0])
            return

        info = (self.extracted_data or {}).get("info") or {}
        needs_pot = _needs_pot(info)
        if needs_pot and self._pot_manager.is_busy():
            self._pending_download = (targets, "auto", "auto")
            self.append_concise_log(
                log_console.emit_event("SYS", "RUN", "POT", "queued — waiting for pot server"),
                is_status=True,
                is_error=False,
            )
            return
        if needs_pot:
            self._wait_pot_if_needed()
            if not self._pot_manager.is_ready():
                self._pending_download = (targets, "auto", "auto")
                self.append_concise_log(
                    log_console.emit_event("SYS", "RUN", "POT", "queued — waiting for pot server"),
                    is_status=True,
                    is_error=False,
                )
                return

        self._start_download(targets, "auto", "auto")

    def _start_download(self, targets, v_id, a_id):
        self.ctrl.begin_download()
        self.append_concise_log(
            log_console.emit_event("DL", "RUN", "YT", "downloading..."),
            is_status=True,
            is_error=False,
        )
        self.update_ui_state()

        live_hint = len(targets) == 1 and bool(
            (self.extracted_data.get("info") or {}).get("is_live")
        )
        self.ctrl.spawn_worker(
            targets,
            self.cfg,
            v_id,
            a_id,
            is_live_hint=live_hint,
            v_spec=None,
            audio_desc="",
            yt_client=self.extracted_data.get("yt_client", "auto"),
        )

    def _wait_pot_if_needed(self):
        info = (self.extracted_data or {}).get("info") or {}
        if not _needs_pot(info):
            return

        if server_ping():
            self._pot_manager.use_existing()
            return

        self.append_concise_log(
            log_console.emit_event("POT", "RUN", "POT", "starting server..."),
            is_status=True,
            is_error=False,
        )
        self._pot_manager.ensure_ready("gate")
        self._start_gate_watchdog()

    def _start_pick_flow(self, url):
        self._pick_targets = [url]
        self._pick_pending = True
        self.append_concise_log(
            log_console.emit_event("ANAL", "RUN", "YT", "analyzing formats..."),
            is_status=True,
            is_error=False,
        )
        self.ctrl.spawn_analyzer(url, self.cfg, deep=True)
        self.update_ui_state()

    def _show_pick_menu(self, data):
        v_list = data.get("v_list", [])
        a_list = data.get("a_list", [])
        if not v_list and not a_list:
            self.append_concise_log(
                log_console.emit_event("ANAL", "FAIL", "YT", "no formats for pick"),
                False,
                True,
            )
            self.update_ui_state()
            return
        lines = log_console.format_pick_menu(v_list, a_list)
        lines.append("enter: 'N' video  /  'N.M' v+a  /  empty=best")
        self.append_concise_log("\n".join(lines), False, False)
        self.ctrl.state["picking"] = True
        self.url_input.setFocus()
        self.update_ui_state()

    def _submit_pick(self):
        targets = getattr(self, "_pick_targets", None)
        if not targets:
            self.ctrl.state["picking"] = False
            return
        text = self.url_input.text().strip()
        v_list = self.extracted_data.get("v_list", [])
        a_list = self.extracted_data.get("a_list", [])
        v_id, a_id = "auto", "auto"
        if text:
            parts = re.split(r"[.,\s]+", text)
            try:
                if parts[0]:
                    idx = int(parts[0])
                    if not (1 <= idx <= len(v_list)):
                        raise ValueError
                    v_id = v_list[idx - 1]["id"]
                if len(parts) > 1 and parts[1].strip():
                    idx = int(parts[1])
                    if not (1 <= idx <= len(a_list)):
                        raise ValueError
                    a_id = a_list[idx - 1]["id"]
            except (ValueError, IndexError):
                self.append_concise_log(
                    log_console.emit_event("ANAL", "FAIL", "YT", "pick fail — retry"),
                    False,
                    True,
                )
                return
        self.ctrl.state["picking"] = False
        self.append_concise_log(
            log_console.emit_event("DL", "OK", "YT", f"picked {v_id} · {a_id}"),
            False,
            False,
        )
        self._start_download(list(targets), v_id, a_id)

    def _cancel_pick(self):
        self.ctrl.state["picking"] = False
        self._pick_pending = False
        self._pick_targets = []
        self.append_concise_log(
            log_console.emit_event("DL", "ABORT", "YT", "format pick canceled"),
            False,
            True,
        )
        self.update_ui_state()

    def skip_current(self):
        if self.ctrl.running:
            self.ctrl.request_skip()
            self.append_concise_log(
                log_console.emit_event("DL", "SKIP", "MAIN", "skip requested"),
                is_status=False,
                is_error=False,
            )

    def add_concise_task_separator(self):
        self.console.add_task_separator()

    def on_download_finished(self, success_count, fail_count):
        self.ctrl.on_download_finished(success_count, fail_count)
        self.update_ui_state()
        self.add_concise_task_separator()

        if success_count > 0:
            self.url_input.clear()
            if self.cfg.get("play_sound") and winsound:
                try:
                    winsound.MessageBeep(winsound.MB_ICONASTERISK)
                except OSError:
                    pass
            if self.cfg.get("auto_open_folder"):
                _open_windows_explorer(self.cfg["download_path"])


def main() -> int:
    try:
        _pylib = _bootstrap()
    except (OSError, ImportError):
        _pylib = ""

    sys.excepthook = lambda t, v, tb: log_history.exception("미처리 예외", t, v, tb)

    if platform.system() == "Windows":
        try:
            myappid = "chzzktube.subapp.v2"
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except (AttributeError, OSError):
            pass

    app = QApplication(sys.argv)
    if os.path.exists(ICON_PATH):
        app.setWindowIcon(QIcon(ICON_PATH))

    font_path = os.path.join(BASE_DIR, "assets", "CascadiaMono-VariableFont_wght.ttf")
    if os.path.exists(font_path):
        QFontDatabase.addApplicationFont(font_path)

    # [핵심 교정] 라틴(Cascadia Mono) + CJK(맑은 고딕) 다중 패밀리 체인 구축
    font = QFont()
    font.setFamilies(["Cascadia Mono", "Malgun Gothic", "맑은 고딕", "Apple SD Gothic Neo"])
    font.setPointSize(11)

    # [한글 뭉개짐 방지] 힌팅을 완전 끄지 않고 수직 힌팅을 허용하여 한글 가독성 확보
    font.setHintingPreference(QFont.HintingPreference.PreferVerticalHinting)
    font.setStyleStrategy(
        QFont.StyleStrategy.PreferAntialias 
        | QFont.StyleStrategy.PreferQuality
    )

    # Windows CJK 인조 볼드 왜곡(자글거림)을 유발하던 Weight(550)을 제거하고 순정 Normal(400)로 안정화
    font.setWeight(QFont.Weight.Normal)

    app.setFont(font)

    try:
        if _pylib and os.path.isdir(_pylib):
            try:
                pkgs = sorted(
                    d.name for d in os.scandir(_pylib) if d.is_dir() and d.name.endswith(".dist-info")
                )
            except OSError:
                pkgs = []
            _suffix = f" [{', '.join(pkgs)}]" if pkgs else " [empty]"
            raw_log.raw(
                "deps",
                emit_component("DEPS", "OK", "PYLIB", f"overlay: {_pylib}{_suffix}"),
                to_tui=True,
            )
            sys.stderr.write(f"[DEPS] OK PYLIB overlay: {_pylib}{_suffix}\n")
    except OSError:
        pass

    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())