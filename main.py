##### main.py - 메인 윈도우 및 앱 실행 진입점
import os
import platform
import re
import sys
import time

from PySide6.QtCore import qInstallMessageHandler


def qt_message_handler(mode, context, message):
    if "must be a top level window" in message:
        return
    sys.stderr.write(message + "\n")


qInstallMessageHandler(qt_message_handler)

from PySide6.QtCore import Qt, QThread, QTimer, QEvent
from PySide6.QtGui import QFont, QFontDatabase, QIcon
from PySide6.QtWidgets import (
    QApplication,
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

# [시퀀스 코디네이터] 시작 시퀀스 단일 책임자
from startup_coordinator import StartupCoordinator

##### 설정 상수/경로/로드·저장은 config 모듈에서 관리
import config
import log_console
import log_history
import pot_provider
import theme
from controller import MediaController
from dialogs import ExitConfirmDialog, SettingsDialog, VerboseLogWindow
from update_worker import UpdateWorker
from utils import _open_windows_explorer

# [URL 인식 디바운스] 키 입력(타이핑) 침묵 기준 지연 — "타이핑 끝남"은 미래 입력
# 부재를 감지해야만 알 수 있어 키 입력 경로에선 구조상 필수다.
_ANALYZE_DEBOUNCE_MS = 900
# [벌크 입력 공출화] 붙여넣기·드래그&드롭·TXT 로드는 통째로 들어오므로 즉시 분석.
# 0ms 대신 150ms를 두는 건 프로그램적 다중 setText가 한 프레임에 겹칠 때의 점화 병합용.
_BULK_INPUT_DELAY_MS = 150

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

        # 다운로드 + 분석 세션 상태/워커는 컨트롤러가 소유 (dl_state 프로퍼티로 접근 가능)
        self.ctrl = MediaController(self)
        self.extracted_data = {"info": None, "v_list": [], "a_list": []}

                # StartupCoordinator: DEPS/POT/업데이트 시그널을 중앙에서 수신하고 3대 로그에 전파
        # 단일 인스턴스 원칙 (HANDOVER §7): 시그널 연결 전 최초 1회만 생성
        self._startup_coord = StartupCoordinator(self)

        self.settings_dlg = None
        self.verbose_win = None

        self.analyze_timer = QTimer()
        self.analyze_timer.setSingleShot(True)
        self.analyze_timer.timeout.connect(self.run_analysis)

        # ── 분석 워커 시그널 바인딩 (Controller → View 포워딩) ──
        self.ctrl.analyze_result_ready.connect(self.on_analyze_success)
        self.ctrl.analyze_error_occurred.connect(self.on_analyze_error)
        self.ctrl.analyze_log_full.connect(self.append_full_log)

        # 락 가드: 앱 시작 및 PO Token 서버 구성 중에는 드롭다운/입력 차단 및 순서 보정
        self._startup_completed = False
        # [가드 초기화] _try_emit_ready의 pot_needed 판별용 — 미정의 시
        # hasattr() False → pot 무시 → POT 진행 중 READY 선행 발산 결함.
        self._pot_provider_started = False
        # [프리웜 가드] READY 후 유휴 스테이징 단일 발화용.
        self._prewarm_started = False
        self._prewarm_worker = None

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
            if self.ctrl.worker_dl is not None and self.ctrl.worker_dl.isRunning():
                log_history.log(
                    "shutdown: download worker not stopped (1s) — cancelling then exiting",
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
                            "shutdown: orphaned analyze worker (1.5s) — forcing exit",
                            "WARN",
                        )
            for name in ("_pot_worker", "update_worker"):
                w = getattr(self, name, None)
                if w is not None and w.isRunning():
                    w.wait(1500)
                    if w.isRunning():
                        log_history.log(
                            f"shutdown: startup worker ({name}) not stopped (1.5s) — forcing exit",
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
        """[TUI Refactor] Hyper-Minimal Modern TUI — flat, borderless, mono.

        ├── Path ...  │ [F1] [F2] │ [F12] [F3]
        ├── ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─
        │ > [url_input..........................] [F4] [ENTER]
        ├── ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─
        └── [10:54:14] DEPS  │ OK  │ ...        ← console (stretch=1)
        """
        from PySide6.QtWidgets import QFrame

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
        self.path_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.path_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self._update_path_label()
        hlay.addWidget(self.path_label, 1)

        self.btn_change = _tui_tag(
            "[ F1: Change ]", "Change download folder (F1)", self.change_folder
        )
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

        self.btn_full_log = _tui_tag(
            "[ F12: Full Log ]", "Toggle full log window (F12)", self.toggle_verbose_log
        )
        self.btn_settings = _tui_tag(
            "[ F3: Settings ]", "Open settings (F3)", self.open_settings
        )
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
        prompt_font = QFont("Cascadia Mono", 11)
        prompt_font.setBold(True)
        self.prompt_label.setFont(prompt_font)
        self.prompt_label.setStyleSheet("color: #4ec9b0; border: none; background: transparent; padding: 0px;")
        ilay.addWidget(self.prompt_label)

        # [ObjectName] url_input — TUI_STYLE의 QLineEdit#url_input 선택자 타겟
        self.url_input = QLineEdit()
        self.url_input.setObjectName("url_input")
        self.url_input.setPlaceholderText("URL, playlist, or channel URL...")
        # [하이퍼미니멀] 네이티브 (x) 클리어 버튼 제거 — ESC 키로 대체
        self.url_input.setClearButtonEnabled(False)
        self.url_input.installEventFilter(self)
        self.url_input.textChanged.connect(self.on_url_changed)
        self.url_input.setDragEnabled(True)
        self.url_input.acceptDrops()
        self.url_input.dropEvent = lambda e: self._on_url_drop(e.mimeData())
        self.url_input.returnPressed.connect(self.toggle_download)
        ilay.addWidget(self.url_input, 1)

        self.btn_txt = _tui_tag(
            "[ F4: Load .txt ]", "Load URL list from TXT (F4)", self.pick_txt
        )
        ilay.addWidget(self.btn_txt)
        ilay.addWidget(_tui_sep())

        self.btn_enter = _tui_tag(
            "[ ENTER: Start ]",
            "Start download (Enter)",
            self.toggle_download,
        )
        self.btn_esc = _tui_tag(
            "[ ESC: Clear ]",
            "Clear input (Esc) — abort when running",
            self._esc_action,
        )
        ilay.addWidget(self.btn_esc)
        ilay.addWidget(_tui_sep())
        ilay.addWidget(self.btn_enter)

        main_layout.addWidget(self.input_group)

        # ── 1px 구분선 ──
        main_layout.addWidget(_separator())

        # ════════════════════════════════════════════════════════════════════
        # Layer 3: Live Console Monitor (flat, stretch=1 → 100% 채움)
        # ════════════════════════════════════════════════════════════════════
        self.console_group = QGroupBox("")
        self.console_group.setObjectName("console_group")
        self.console_group.setProperty("class", "tui-panel")
        self.console_group.style().unpolish(self.console_group)
        self.console_group.style().polish(self.console_group)
        self.console_group.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        clay = QVBoxLayout(self.console_group)
        clay.setContentsMargins(0, 0, 0, 0)
        clay.setSpacing(0)

        # [ObjectName] console_log — TUI_STYLE의 QTextEdit#console_log 선택자 타겟
        self.te_concise = QTextEdit()
        self.te_concise.setObjectName("console_log")
        self.te_concise.setReadOnly(True)
        self.te_concise.document().setDocumentMargin(0)
        font = QFont("Cascadia Mono", 11)
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setFamilies(["Cascadia Mono"])
        self.te_concise.setFont(font)
        self.console = log_console.ConciseLogConsole(self.te_concise)

        clay.addWidget(self.te_concise, 1)
        main_layout.addWidget(self.console_group, stretch=1)

        # ── 보조 상태 초기화 ──
        self._full_log_buf: list[str] = []
        # [raw 스택 버스] 모든 동작 로그의 단일 진실 공급원 구독.
        # Qt 시그널 경유이므로 워커 스레드에서 raw() 호출 안전.
        import raw_log
        raw_log.subscribe_concise(
            lambda msg, is_status=False, is_error=False:
                self.append_concise_log(msg, is_status=is_status, is_error=is_error)
        )
        raw_log.subscribe_full(self.append_full_log)
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
                lines = [
                    l.strip() for l in f if l.strip() and not l.strip().startswith("#")
                ]
            if lines:
                self.url_input.setText("\n".join(lines))
                self.append_concise_log(
                    log_console.emit_event(
                        "SYS", "OK", "TXT", f"{len(lines)} URLs"
                    ),
                    is_status=False,
                    is_error=False,
                )
        except Exception:
            self.append_concise_log(
                log_console.emit_event("SYS", "FAIL", "TXT", "read fail"),
                is_status=False,
                is_error=True,
            )

    def abort_download(self):
        """실행 중 다운로드 중단 (ESC 버튼 / 단축키 공용)."""
        if self.ctrl.running:
            self.ctrl.request_cancel()
            self.append_concise_log(
                log_console.emit_event("DL", "ABORT", "-", "download canceled by user"),
                is_status=False,
                is_error=True,
            )

    def _esc_action(self):
        """ESC 컨텍스트 액션 — 실행 중이면 중단, pick 대기면 취소, 아니면 입력 클리어."""
        if self.ctrl.running:
            self.abort_download()
        elif self.ctrl.picking:
            self._cancel_pick()
        else:
            self.url_input.clear()

    def eventFilter(self, obj, event):
        """url_input 내부 ESC — 클리어(아이들) / 중단(실행 중) 처리."""
        if (
            obj is self.url_input
            and event.type() == QEvent.Type.KeyPress
            and event.key() == Qt.Key.Key_Escape
        ):
            self._esc_action()
            return True
        return super().eventFilter(obj, event)

    def _update_path_label(self):
        """PATH 라벨 TUI 텍스트 갱신 — `path_label` 위젯 갱신."""
        path = self.cfg.get("download_path", "")
        self.path_label.setText(
            f"<span style='color:#4ec9b0; font-weight:bold;'>Path</span> {path}"
        )

    def change_folder(self):
        if self.ctrl.running:
            return
        folder = QFileDialog.getExistingDirectory(
            self, "Select Download Folder", self.cfg["download_path"]
        )
        if folder:
            self.cfg["download_path"] = os.path.normpath(folder)
            self._update_path_label()
            self.save_cfg()
            self.append_concise_log(
                log_console.emit_event(
                    "SYS", "OK", "CFG", f"path → {self.cfg['download_path']}"
                ),
                is_status=False,
                is_error=False,
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
            "Select TXT File",
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
            self._last_input_len = 0
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

        # [타이핑 인식 가드] 입력 증분으로 '키 입력'과 '벌크 입력'을 구별한다.
        #
        # "타이핑을 끝냈다"는 사실은 미래 입력 부재를 감지해야만 알 수 있으므로
        # 키 입력 경로는 침묵 대기(디바운스)가 구조상 필수다. 반면 붙여넣기·
        # 드래그&드롭·TXT 로드는 한 이벤트에 텍스트가 통째로 들어오므로
        # 증분 길이가 1을 초과 — 이 경우 지연을 걸 필요가 없다.
        prev_len = getattr(self, "_last_input_len", 0)
        self._last_input_len = len(text)
        is_bulk_input = (len(text) - prev_len) > 1

        if not self.ctrl.running and not self.ctrl.picking and getattr(
                self, "_startup_completed", False
            ):
            # [URL 형태 가드] 스킴 또는 '문자.문자' 형태의 도메인이 없으면
            # 분석 후보가 아니다 — 부분 타이핑에서의 불필요한 점화 방지.
            if "://" in text or re.search(r"\S\.\S", text):
                delay = _BULK_INPUT_DELAY_MS if is_bulk_input else _ANALYZE_DEBOUNCE_MS
                self.analyze_timer.start(delay)

    def _start_pot_provider(self):
        """PO Token 서버 가동 (필요 시에만)."""
        if hasattr(self, "_pot_worker") and self._pot_worker.isRunning():
            return  # 중복 기동 방지
        try:
            self._pot_worker = pot_provider.POTProviderWorker(self)
            self._pot_worker.line.connect(self._component_line)
            self._pot_worker.log_full.connect(self.append_full_log)
            # [시그널 계약] QThread.finished는 인자 0개 — report_pot(ok, msg)는
            # 직접 연결 시 TypeError → _on_pot_finished 어댑터 경유 필수.
            self._pot_worker.finished.connect(self._on_pot_finished)
            self._pot_worker.start()
            self._pot_provider_started = True
        except Exception:
            pass

    def _on_pot_finished(self):
        """POT 워커 종료 어댑터 — outcome을 풀어 Coordinator에 보고 + raw 적재."""
        import raw_log
        outcome = ("err", "")
        try:
            w = getattr(self, "_pot_worker", None)
            if w is not None:
                outcome = w.outcome
        except Exception:
            pass
        ok = outcome[0] == "ok"
        msg = outcome[1] if len(outcome) > 1 else ""
        raw_log.raw("pot", f"gate finished ok={ok} outcome={outcome[0]}")
        self._startup_coord.report_pot(ok, msg)

    def _ensure_pot_for_info(self, info):
        """PO 필요 여부 판단 후 필요 시에만 서버 가동.

        [Lazy 2층 분리] 게이트 책임은 View(main)가 유지 — AnalyzeWorker는
        순수 추출만 담당. spawn(Popen)만 이 지점까지 지연되며, DEPS 단계의
        pot_readiness(디스크 준비)가 선행 보장되므로 즉시 기동 가능.

        PO가 필요한 경우:
        - age_limit > 0 (연령 제한)
        - availability가 'needs_auth', 'premium_only', 'subscriber_only' 등
        """
        if getattr(self, "_pot_provider_started", False):
            return  # 이미 가동 중이거나 시도함

        needs_pot = False
        if info:
            age_limit = info.get("age_limit") or 0
            if age_limit > 0:
                needs_pot = True
            availability = info.get("availability") or ""
            if isinstance(availability, str) and availability.lower() in (
                "needs_auth",
                "premium_only",
                "subscriber_only",
                "private",
            ):
                needs_pot = True

        import raw_log as _rl
        _rl.raw(
            "pot-gate",
            f"gated={needs_pot} age_limit={age_limit if info else '-'} "
            f"availability={((info or {}).get('availability') or '-')}",
        )

        if needs_pot:
            # [프리웜 경합] 유휴 스테이징 진행 중이면 게이트 spawn과 npm 락이
            # 충돌 — 프리웜 종료를 기다리지 않고 게이트 워커가 이어받도록
            # 프리웜 워커는 그대로 두고(단일 스폰 가드) 게이트만 진행.
            # ensure_node_server의 npm ci는 디스크 산출물 기준 멱등이므로
            # 중복 실행돼도 산출물만 덮어쓴다.
            self.append_concise_log(
                log_console.emit_event("POT", "RUN", "pot", "starting..."),
                is_status=True,
                is_error=False,
            )
            self._start_pot_provider()

    def _force_unlock_input(self):
        """[폴백] 구성요소 체인이 15초 내 완료되지 않으면 입력 강제 개방.

        POT server is only needed for age-restricted videos — a stalled chain
        should not block basic downloads. 플래그 직접 세팅 대신 Coordinator에
        위임 — READY 로그도 이 경로에서 단 한 번 발산된다.
        """
        if getattr(self, "_startup_completed", False):
            return
        self._startup_coord.report_ready(True, "ready (fallback timeout)")

    def run_analysis(self):
        url = self.url_input.text().strip()
        if not url:
            return
        self.append_concise_log(
            log_console.emit_event("ANAL", "RUN", "-", "analyzing..."),
            is_status=True,
            is_error=False,
        )

        # 이전 링크의 분석 결과 블록이 마지막에 남아 있으면 철회한다.
        self._discard_analysis_result()

        self.base_anim_url = url

        # Controller가 기존 워커 유기 + 새 워커 생성을 담당 (Zombie Pattern)
        self.ctrl.spawn_analyzer(url, self.cfg)

    def stop_analysis_anim(self, ok=True):
        """분석 완료/실패 시 최종 결과 로그를 히스토리에 박제 (마침표 애니메이션 정리 불요)."""
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

        # 플랫폼 축약기호 (YT / CHZ 등)
        platform = self._platform_of_url()

        # 해상도: v_list 첫 항목에서 추출
        v_first = v_list[0] if v_list else {}
        res = ""
        if isinstance(v_first, dict):
            h = v_first.get("height") or v_first.get("v_height") or 0
            fps = v_first.get("fps") or v_first.get("v_fps") or 0
            if h:
                res = f"{h}p{fps}" if fps else f"{h}p"

        # ANAL OK 메인 라인: Platform=사이트, Spec=해상도, Msg=stream analyzed · channel · title
        counts = log_console.format_analysis_counts(len(v_list), len(a_list))
        base_msg = f"stream analyzed{counts}"
        if meta:
            base_msg += f" · {meta[:80]}"
        # format_log_line에 spec(res=해상도)을 직접 전달
        full_line = log_console.format_log_line(
            stage="ANAL", status="OK", platform=platform, spec=res,
            speed="-", pct=None, bar_frac=None, msg=base_msg,
        )
        self.append_concise_log(
            full_line,
            True,   # is_status — analyzing... 을 stream analyzed 로 덮어쓰기 (한 줄 유지)
            False,  # is_error
        )

        # 마지막 블록 철회 가드
        self._analysis_block_active = True
        self._analysis_block_count = self.console.last_status_block_count
        self._analysis_last_line = self.console.last_content_block_text()

        # 비디오/오디오 포맷 로그: 별도 줄로 출력 (코덱만 표시, 채널명·제목 제외)
        self._emit_format_logs(v_list, a_list, platform)

    def _format_analysis_summary(self):
        """분석 완료 요약 — 채널명 · 제목 등 기본 정보 (플레이리스트/치지직 공용)."""
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
        self.update_worker = UpdateWorker(self, upgrade=False, channel=self.cfg.get("update_channel", "stable"), check_updates=self.cfg.get("auto_update_check", True))
        # 구성요소 확인 라인은 필터 경유 — 루틴 '최신' 라인 간결 생략 + 히스토리 전건
        self.update_worker.line.connect(self._component_line)
        self.update_worker.full.connect(self.append_full_log)
        self.update_worker.check_done.connect(self._on_update_check_done)
        # [응답없음 방지] 낮은 우선순위로 시작해 GIL을 메인 스레드에 양보
        self.update_worker.start(QThread.Priority.LowPriority)

    def _on_update_check_done(self, stale):
        """버전 확인 결과 처리 — 메인에 결론 한 줄, 그 뒤 upgrade 워커로 진행.

        [min profile] 메인 콘솔에 emit되는 DEPS 라인은 정확히 한 줄:
        결론(최신 / 업데이트 가능 / 일시 장애). 패키지별 raw 라인은
        _component_line을 통해 상세로그로만 흘러간다.

        [시그널 교통 정리] check_done(list)은 시그니처가 (bool, str)이 아니므로
        Coordinator에 직결하면 안 된다 — 여기서 결론 라인 출력 + upgrade 워커
        기동 + Coordinator에 deps 완료 보고(report_deps)를 순서대로 수행한다.
        """
        # [결론 라인] — 메인 콘솔에 단 한 줄
        if stale:
            summary = ", ".join(f"{label} {cur}→{latest}" for label, _, cur, latest in stale)
            self.append_concise_log(
                log_console.emit_event(
                    "DEPS", "WARN", "-", f"update — {summary}"
                ),
                is_status=False,
                is_error=False,
            )
            self._stale_updates = True
        else:
            self._stale_updates = False
            self._pot_provider_started = False  # PO 서버는 필요 시에만 가동
            # [결론 라인] 최신 상태 — deps ok 단 한 줄 (체크 5줄과 구분되는 결론)
            self.append_concise_log(
                log_console.emit_event("DEPS", "OK", "-", "deps ok"),
                is_status=False,
                is_error=False,
            )
        # [stale case] Dev/Frozen integration — UpdateWorker handles all deps (PyPI + ffmpeg + node)
        # stale로 확인된 패키지만 업그레이드, 나머지는 수급(ensure)만 — 2중 출력 방지
        self.update_worker = UpdateWorker(self, upgrade=True, stale_updates=stale, channel=self.cfg.get("update_channel", "stable"), check_updates=self.cfg.get("auto_update_check", True))
        self.update_worker.line.connect(self._component_line)
        self.update_worker.full.connect(self.append_full_log)
        self.update_worker.upgrade_done.connect(self._startup_coord.report_upgrade)
        self.update_worker.start()
        # [Coordinator 보고] deps 체크 단계 완료 — READY 게이트용 플래그.
        # 결론 라인은 위에서 이미 출력했으므로 Coordinator는 플래그만 세팅한다.
        self._startup_coord.report_deps(not bool(stale), "deps ok" if not stale else "update")
        # [유휴 프리웜] READY 후 빌드 스테이징 — 첫 게이트 히트 0.1~3초 보장.
        # Popen 없이 디스크 산출물만 준비 (RAM 0MB·포트 미점유). READY 게이트
        # 미포함 — 실패해도 기동 블록 없음. 중복 스폰은 _maybe_prewarm_pot 가드.
        QTimer.singleShot(3000, self._maybe_prewarm_pot)

    def _maybe_prewarm_pot(self):
        """READY 후 유휴 POT 빌드 스테이징 — 단일 발화 가드 (전 경로 raw 적재)."""
        import raw_log
        try:
            from pot_server import pot_readiness
            from po_client import server_ping
            if server_ping():
                raw_log.raw("prewarm", "skip — server already running")
                return  # 이미 기동 — 스테이징 불필요
            ready, reason = pot_readiness(
                log_func=lambda m: raw_log.raw("pot-readiness", m),
                check_stale=True,
                want_refresh=True,
            )
            if ready:
                if "refresh" in reason:
                    raw_log.raw("prewarm", f"starting refresh (reason={reason})")
                else:
                    raw_log.raw("prewarm", "skip — artifacts ready")
                    return  # 산출물 완비 — 스테이징 불필요
            if getattr(self, "_pot_provider_started", False):
                raw_log.raw("prewarm", "skip — gate already started")
                return  # 게이트/프리웜 이미 진행 중 — 중복 스폰 금지
            if getattr(self, "_prewarm_started", False):
                raw_log.raw("prewarm", "skip — already in flight")
                return
            raw_log.raw("prewarm", f"starting staging (reason={reason})")
            self._prewarm_started = True
            self._prewarm_worker = pot_provider.POTProviderWorker(self, prewarm=True)
            self._prewarm_worker.line.connect(self._component_line)
            self._prewarm_worker.log_full.connect(self.append_full_log)
            self._prewarm_worker.finished.connect(self._on_prewarm_finished)
            self._prewarm_worker.start(QThread.Priority.LowPriority)
        except Exception as e:
            raw_log.raw("prewarm", f"spawn failed: {type(e).__name__}: {e}")

    def _on_prewarm_finished(self):
        """프리웜 워커 종료 — 플래그 정리 + 산출물 판별 로그 (게이트 READY 무관)."""
        import raw_log
        try:
            self._prewarm_started = False
            w = getattr(self, "_prewarm_worker", None)
            outcome = w.outcome if w is not None else ("err", "")
            raw_log.raw("prewarm", f"finished outcome={outcome[0]}")
            if outcome[0] == "ok":
                self.append_concise_log(
                    log_console.emit_event("POT", "OK", "POT", "prewarm staged"),
                    is_status=False,
                    is_error=False,
                )
        except Exception:
            pass

    def _is_stale_analyze_signal(self):
        """유령 분석 결과 판별 — 지운 뒤 "stream analyzed"가 한 번 더 뜨는 버그 차단.

        [경합상태] 워커 스레드의 result_ready/error_occurred는 GUI 이벤트 큐에
        적재(queued connection)된 뒤 전달된다. 유기 패턴의 disconnect()는
        "이후" 방출을 막을 뿐 이미 큐에 있는 전달은 취소하지 못한다 —
        그래서 입력을 지운 직전 큐잉된 결과가 슬롯에 도착해 로그를 오염시켰다.

        [Signal forwarding] Worker 시그널은 Controller.analyze_* 중계 Signal을
        거쳐 View 슬롯에 도달한다 (PySide6 Signal to Signal 직접 연결).
        이 체인에서 self.sender()는 MediaController를 반환하므로 워커 식별이
        불가능하다. state["analyzing"] 플래그 + URL 입력 여부로 대체 검증한다.
        """
        if not self.ctrl.state.get("analyzing"):
            return True  # 분석 상태가 아니면(유기·완료) 모든 큐잉된 시그널 폐기
        if not self.url_input.text().strip():
            return True  # 분석 도중 입력이 비워짐
        return False

    def on_analyze_success(self, data):
        if self._is_stale_analyze_signal():
            return
        self.extracted_data = data
        # PO 필요 여부 판단 후 필요 시에만 서버 가동
        self._ensure_pot_for_info(data.get("info"))
        if data.get("is_playlist"):
            self.stop_analysis_anim()
            return
        # [포맷 직접 고르기] 딥 분석 결과 → 메뉴 출력 + 입력 대기
        if getattr(self, "_pick_pending", False):
            self._pick_pending = False
            self._show_pick_menu(data)
            return
        self.stop_analysis_anim()
        # 콜백은 결과만 보관 — 콤보/버튼이 없으므로 UI 갱신 없음
        # 좌측 패널이 자동 처리 — 별도 UI 갱신 없음

    def on_analyze_error(self, err_msg):
        if self._is_stale_analyze_signal():
            return
        pick_pending = getattr(self, "_pick_pending", False)
        self._pick_pending = False
        if pick_pending:
            self.ctrl.state["picking"] = False
        self.stop_analysis_anim(ok=False)
        self.append_concise_log(
            log_console.emit_event("ANAL", "FAIL", "-", err_msg),
            True,   # is_status — analyzing... 을 에러 메시지로 덮어쓰기
            True,   # is_error
        )

    def update_ui_state(self):
        # URL 필드 활성도만 관리 — 진행바/콤보/버튼은 존재하지 않음
        is_running = self.ctrl.running
        startup_completed = getattr(self, "_startup_completed", False)
        self.url_input.setEnabled(not is_running and startup_completed)
        # ESC 버튼 동적 라벨 — 실행 중 Abort / pick 대기 Cancel / 대기 Clear
        if getattr(self, "btn_esc", None) is not None:
            if is_running:
                esc_label = "[ ESC: Abort ]"
            elif self.ctrl.picking:
                esc_label = "[ ESC: Cancel ]"
            else:
                esc_label = "[ ESC: Clear ]"
            self.btn_esc.setText(esc_label)
        self.console.reset_status_flag()

    def showEvent(self, event):
        super().showEvent(event)
        # 첫 노출 시 viewport 실측으로 트리 예산 산정 + 라벨/버퍼 reflow.
        if hasattr(self, "console"):
            self.console.on_resize()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # 창 가로 확장 → 예산 갱신 + 기존 로그 전체 reflow (로그가 펼쳐진다).
        if hasattr(self, "console"):
            self.console.on_resize()

    def _component_line(self, msg, is_status=False, is_error=False):
        """구성요소(POT/Update/워커) 라인 필터 — 간결 로그는 TUI 컬럼만.

        *  이미 TUI 컬럼 포맷이면 그대로 간결 로그에 통과.
        *  구형 prefix ([v]/[!]/[~]/[+]/[X]/[?])는 TUI 이벤트로 변환.
        *  그 외 플레인 텍스트(yt-dlp/pip raw 등)는 간결 로그에 **노출하지 않고**
           상세 로그(F12)와 히스토리에만 기록 — Single-Line Pipe-Format 유지.
        """
        # 1) 이미 TUI 컬럼 포맷이면 그대로 출력
        if log_console.is_tui_line(msg):
            self.append_concise_log(msg, is_status, is_error)
            return
        # 2) prefix로 매핑
        stripped = str(msg).lstrip()
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
            # 3) 플레인 텍스트 — 간결 로그에는 노출 금지, 상세/히스토리 전용
            if str(msg).strip():
                self._mirror_full_log(msg)
                log_history.log(msg, "ERROR" if is_error else "INFO")
            return
        stage = "pot" if "PO Token" in payload or "pot" in payload else "DEPS"
        self.append_concise_log(
            log_console.emit_event(stage, status, "-", payload),
            is_status=is_status,
            is_error=is_error,
        )

    def _mirror_full_log(self, msg, is_status=False):
        """상세 로그 버퍼 누적 + F12 창 미러링 (append_*_log 공용).

        [수정] 간결 로그의 TUI 포맷 메시지는 상세 로그에 포함하지 않음.
        상세 로그는 raw 원본 로그만 기록 (yt-dlp stdout 등).
        [추가] 모든 raw 로그 라인에 [HH:MM:SS] 타임스탬프 자동 부착.
        """
        # TUI 컬럼 포맷 메시지는 상세 로그에 제외 — raw만 기록
        if log_console.is_tui_line(msg):
            return
        ts = time.strftime("%H:%M:%S")
        # 다중 라인 메시지 모두에 동일 타임스탬프 부착
        stamped = "\n".join(f"[{ts}] {l}" if l else f"[{ts}]" for l in str(msg).split("\n"))
        if not is_status:
            self._full_log_buf.append(stamped)
            if len(self._full_log_buf) > 5000:
                del self._full_log_buf[: len(self._full_log_buf) - 5000]
        if (
            getattr(self, "verbose_win", None) is not None
            and self.verbose_win.isVisible()
        ):
            try:
                self.verbose_win.append(stamped, is_status)
            except Exception:
                pass

    def append_concise_log(self, msg, is_status=False, is_error=False, fg_color=None):
        # [콘솔 출력] ConciseLogConsole로 실제 텍스트 위젯에 렌더링
        self.console.append(msg, is_status, is_error, fg_color)
        # [전체 로그 미러] 상태 줄(진행률 덮어쓰기)은 누적 제외
        if not is_status:
            self._mirror_full_log(msg)
            # 히스토리 파일 기록 — 상태 줄(틱)은 기록하지 않음
            log_history.log(msg, "ERROR" if is_error else "INFO")

    def append_full_log(self, msg, is_status=False):
        # is_status=True: 진행률 틱 — F12에서 마지막 줄 갱신, 버퍼 미적재
        self._mirror_full_log(msg, is_status)

    def toggle_verbose_log(self):
        """F12 상세 로그 창 토글 — 최초 진입 시 누적 버퍼로 초기화 후 미러링."""
        if (
            getattr(self, "verbose_win", None) is not None
            and self.verbose_win.isVisible()
        ):
            self.verbose_win.close()
            return
        if self.verbose_win is None:
            self.verbose_win = VerboseLogWindow(self)
            content = "\n".join(self._full_log_buf)
            if not content.strip():
                content = log_console.emit_event(
                    "SYS",
                    "OK",
                    "LOG",
                    "empty buffer",
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
            self._esc_action()
            event.accept()
            return
        super().keyPressEvent(event)

    def toggle_download(self):
        if self.ctrl.running:
            return
        if self.ctrl.picking:
            self._submit_pick()
            return
        try:
            targets = MediaController.parse_targets(
                self.url_input.text().strip(),
                dedup=self.cfg.get("remove_duplicates"),
            )
        except ValueError as e:
            self.append_concise_log(
                log_console.emit_event("SYS", "FAIL", "-", f"parse error: {e}"),
                False, True
            )
            return
        if not targets:
            return

        # [포맷 직접 고르기] 1개 타깃 + pick_format 켜짐 → 딥 분석 후 선택 분기
        if self.cfg.get("pick_format") and len(targets) == 1:
            self._start_pick_flow(targets[0])
            return

        self._start_download(targets, "auto", "auto")

    def _start_download(self, targets, v_id, a_id):
        """워커 스폰 공통 루틴 — 자동(해상도 제한 내 최고)/포맷 직접 고르기 공용."""
        self.ctrl.begin_download()

        self.append_concise_log(
            log_console.emit_event("DL", "RUN", "-", "downloading..."),
            is_status=True,
            is_error=False,
        )

        self.url_input.setEnabled(False)

        live_hint = len(targets) == 1 and bool(
            (self.extracted_data.get("info") or {}).get("is_live")
        )
        # [다운로드 일관성] 분석에서 실증·통과한 클라이언트 그대로 전달 —
        # 시청 기록 다운로드가 봇 게이트/PO 토큰 경로에 재진입해 0%에
        # 머무르는 현상 방지 (auto면 기존 동작 유지).
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

    # ── 포맷 직접 고르기 흐름 ──────────────────────────────────────────
    def _start_pick_flow(self, url):
        """딥 분석 스폰 → on_analyze_success에서 _show_pick_menu로 이어진다."""
        self._pick_targets = [url]
        self._pick_pending = True
        self.append_concise_log(
            log_console.emit_event("ANAL", "RUN", "-", "format list analyzing..."),
            is_status=True,
            is_error=False,
        )
        self.ctrl.spawn_analyzer(url, self.cfg, deep=True)

    def _show_pick_menu(self, data):
        """포맷 목록을 콘솔에 번호 매겨 출력하고 입력 대기 상태로 전환."""
        v_list = data.get("v_list", [])
        a_list = data.get("a_list", [])
        if not v_list and not a_list:
            self.append_concise_log(
                log_console.emit_event("ANAL", "FAIL", "YT", "no formats for pick"),
                False, True,
            )
            return
        lines = log_console.format_pick_menu(v_list, a_list)
        lines.append("enter: 'N' video  /  'N.M' v+a  /  empty=best")
        self.append_concise_log("\n".join(lines), False, False)
        self.ctrl.state["picking"] = True
        self.url_input.setFocus()

    def _submit_pick(self):
        """pick 입력 파싱(1-based) 후 다운로드 시작 — v/a 각각 format_id 지정."""
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
                    False, True,
                )
                return
        self.ctrl.state["picking"] = False
        self.append_concise_log(
            log_console.emit_event("DL", "OK", "YT", f"picked {v_id} · {a_id}"),
            False, False,
        )
        self._start_download(list(targets), v_id, a_id)

    def _cancel_pick(self):
        self.ctrl.state["picking"] = False
        self._pick_pending = False
        self._pick_targets = []
        self.append_concise_log(
            log_console.emit_event("DL", "ABORT", "YT", "format pick canceled"),
            False, True,
        )

    def skip_current(self):
        if self.ctrl.running:
            self.ctrl.request_skip()
            self.append_concise_log(
                log_console.emit_event("DL", "SKIP", "-", "skip request"),
                is_status=False,
                is_error=False,
            )

    def add_concise_task_separator(self):
        self.console.add_task_separator()

    def on_download_finished(self, success_count, fail_count):
        # 상태 초기화와 분석 데이터 클리어는 Controller에 위임
        self.ctrl.on_download_finished(success_count, fail_count)

        self.url_input.setEnabled(True)
        self.update_ui_state()

        self.add_concise_task_separator()

        if success_count > 0:
            self.url_input.clear()
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

    font_path = os.path.join(BASE_DIR, "CascadiaMono-VariableFont_wght.ttf")
    if os.path.exists(font_path):
        QFontDatabase.addApplicationFont(font_path)

    win = MainWindow()
    win.show()
    sys.exit(app.exec())
