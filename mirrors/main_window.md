##### main.py - 메인 윈도우 및 앱 실행 진입점
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
    QDialog,
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

from chzzktube.control.controller import MediaController, _is_valid_url
from chzzktube.control.gate_state import GateState
import chzzktube.control.gate_state as gate_state
from chzzktube.control.pot_manager import POTManager
from chzzktube.control.startup_coordinator import StartupCoordinator
from chzzktube.core import config, log_emitter, log_history, raw_log
from chzzktube.core.dl_platform import _dl_platform, _short_platform
from chzzktube.core.log_emitter import emit_component
from chzzktube.core.log_event import LogEvent
from chzzktube.core.media import short_codec
from chzzktube.core.utils import _open_windows_explorer
from chzzktube.core.watchdog import (
    ANALYSIS_TIMEOUT_SEC,
    FALLBACK_GRACE_SEC,
    GATE_TIMEOUT_SEC,
    LivenessWatchdog,
)
from chzzktube.infra.po_client import server_ping
from chzzktube.infra.pylib_bootstrap import bootstrap as _bootstrap
from chzzktube.ui import log_console, theme
from chzzktube.ui.dialogs import DepsProvisioningDialog, ExitConfirmDialog, SettingsDialog, VerboseLogWindow
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
# [Followup-4] 폴백 유예 — GUI 블록 등으로 15초 폴백이 체인보다 먼저 만기한 경우
# 1회 유예 후 재판정한다(위양성 폴백 차단).
_FALLBACK_GRACE_MS = int(FALLBACK_GRACE_SEC * 1000)
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
# [핵심 변경] subscriber_only(멤버십) 제거 — Layer 1/2에서 쿠키+JS솔버로 1080p+ 수급 가능
_POT_AVAIL_GATED = ("needs_auth", "premium_only", "private")


def _needs_pot(info):
    """PO 토큰 필요 여부 — age_limit>0(성인인증)만 필수 게이트.
    
    subscriber_only(멤버십)은 쿠키+EJS 솔버로 Layer 1/2에서 해결하므로
    POT 서버 기동 트리거에서 제외. 봇 체크 감지 시 _needs_pot_retry()가
    별도 처리하여 Layer 3로 라우팅한다.
    """
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
        # [v3.8.1] 폴백 타이머 제거로 _on_pot_activity 연결 제거
        # POT 진행은 기동 폴백과 활성 게이트의 생존 시간을 함께 연장한다.
        self._pot_manager.pot_work_tick.connect(self._on_pot_work_tick)
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

        # [워치독] 단일 진실 시간(monotonic) 기반 워치독 인스턴스들.
        # 기동 폴백은 워치독으로 감시하지 않는다 — 만료의 단일 기준은 아래 _fallback_timer.
        self._gate_watchdog = LivenessWatchdog(GATE_TIMEOUT_SEC, 0.0)
        self._analysis_watchdog = LivenessWatchdog(ANALYSIS_TIMEOUT_SEC, 0.0)
        # [Watchdog] 워커의 무페이로드 진행 신호가 분석 워치독 수명을 연장한다.
        # 수명은 스폰 3곳의 명시적 무장에서만 시작되고, 만료 판정·복구·해제는
        # 뷰(_on_analysis_timeout)가 단독 수행한다(만료의 영속 재판정 금지).
        self.ctrl.analyze_activity.connect(self._analysis_watchdog.heartbeat)

        # 워치독 폴링용 타이머 (1초 주기)
        self._watchdog_poll_timer = QTimer(self)
        self._watchdog_poll_timer.setInterval(1000)
        self._watchdog_poll_timer.timeout.connect(self._poll_watchdogs)

        self.init_ui()

        # 구성요소(yt-dlp/ffmpeg/node) 자동 업데이트 확인 — 기동 직후 비동기 1회
        QTimer.singleShot(500, self._start_update_check)

        # [v3.8.1] 폴백 타이머 제거 — deps 수급 실패 시 영구 잠금, 사용자 재시도(ENTER) 대기
        # self._fallback_timer = QTimer(self)
        # self._fallback_timer.setSingleShot(True)
        # self._fallback_timer.timeout.connect(self._force_unlock_input)
        # self._fallback_timer.start(int(FALLBACK_TIMEOUT_SEC * 1000))
        # [정리] 기동 폴백 만료의 단일 기준 — 이 타이머가 유일한 판정자다(폴링
        # 워치독이 같은 만료를 따로 판정해 유예를 끊던 이중 구조 제거).
        # [v3.8.1] 폴백 완전 제거 — deps 수급 완료까지 입력 잠금 유지

        # [Task 4-2] 게이트·분석 워치독 무장/해제 + POT 재시도 상태를
        # GateState 컨테이너로 통합 — 상태 변수 개별 초기화 금지(§6) 준수.
        self._gate_state = GateState(self._gate_watchdog, self._analysis_watchdog)

        # [Followup-5] DEPS 검사의 실제 FAIL(미설치 등)은 게이트 사유로 승격한다.
        self._deps_failed = []
        self._watchdog_poll_timer.start()

    # ── GateState 호환 property ──────────────────────────────────────────
    # 판정 로직 실체는 gate_state 모듈 함수. 여기는 데이터 위임 층만 담당.
    @property
    def _gate_watchdog_active(self) -> bool:
        gs = getattr(self, "_gate_state", None)
        if gs is not None:
            return gs.gate_active
        # fallback: old attribute (tests/mocks)
        return bool(getattr(self, "_gate_watchdog_active_fallback", False))

    @_gate_watchdog_active.setter
    def _gate_watchdog_active(self, val: bool) -> None:
        gs = getattr(self, "_gate_state", None)
        if gs is not None:
            gs.gate_active = val
        else:
            # fallback: old attribute (tests/mocks)
            self._gate_watchdog_active_fallback = val

    @property
    def _analysis_watchdog_active(self) -> bool:
        gs = getattr(self, "_gate_state", None)
        if gs is not None:
            return gs.analysis_active
        return bool(getattr(self, "_analysis_watchdog_active_fallback", False))

    @_analysis_watchdog_active.setter
    def _analysis_watchdog_active(self, val: bool) -> None:
        gs = getattr(self, "_gate_state", None)
        if gs is not None:
            gs.analysis_active = val
        else:
            self._analysis_watchdog_active_fallback = val

    @property
    def _pot_retry_pending(self) -> bool:
        gs = getattr(self, "_gate_state", None)
        if gs is not None:
            return gs.pot_retry_pending
        return bool(getattr(self, "_pot_retry_pending_fallback", False))

    @_pot_retry_pending.setter
    def _pot_retry_pending(self, val: bool) -> None:
        gs = getattr(self, "_gate_state", None)
        if gs is not None:
            gs.pot_retry_pending = val
        else:
            self._pot_retry_pending_fallback = val

    @property
    def _pot_retry_url(self):
        gs = getattr(self, "_gate_state", None)
        if gs is not None:
            return gs.pot_retry_url
        return getattr(self, "_pot_retry_url_fallback", None)

    @_pot_retry_url.setter
    def _pot_retry_url(self, val) -> None:
        gs = getattr(self, "_gate_state", None)
        if gs is not None:
            gs.pot_retry_url = val
        else:
            self._pot_retry_url_fallback = val

    @property
    def _pot_retry_done(self):
        gs = getattr(self, "_gate_state", None)
        if gs is not None:
            return gs.pot_retry_done
        return getattr(self, "_pot_retry_done_fallback", set())

    @_pot_retry_done.setter
    def _pot_retry_done(self, val) -> None:
        gs = getattr(self, "_gate_state", None)
        if gs is not None:
            gs.pot_retry_done = val
        else:
            self._pot_retry_done_fallback = val

    @property
    def _gate_watchdog(self):
        gs = getattr(self, "_gate_state", None)
        if gs is not None:
            return gs.gate_watchdog
        return getattr(self, "_gate_watchdog_fallback", None)

    @_gate_watchdog.setter
    def _gate_watchdog(self, val) -> None:
        gs = getattr(self, "_gate_state", None)
        if gs is not None:
            gs.gate_watchdog = val
        else:
            self._gate_watchdog_fallback = val

    @property
    def _analysis_watchdog(self):
        gs = getattr(self, "_gate_state", None)
        if gs is not None:
            return gs.analysis_watchdog
        return getattr(self, "_analysis_watchdog_fallback", None)

    @_analysis_watchdog.setter
    def _analysis_watchdog(self, val) -> None:
        gs = getattr(self, "_gate_state", None)
        if gs is not None:
            gs.analysis_watchdog = val
        else:
            self._analysis_watchdog_fallback = val

    # ── 게이트·분석 워치독·재시도 메서드 (Thin Wrapper 금지: 실체는 gate_state) ──
    def _start_gate_watchdog(self):
        """[Followup-3] POT gate 대기 2차 워치독 기동."""
        gate_state.start_gate(self._ensure_gate_state())

    def _stop_gate_watchdog(self):
        gate_state.stop_gate(self._ensure_gate_state())

    def _on_pot_work_tick(self):
        """실제 POT 진행만 활성 게이트를 연장한다. 완료 후에는 재무장하지 않는다."""
        gate_state.on_pot_work_tick(self._ensure_gate_state())

    def _on_gate_timeout(self):
        """[Followup-3] gate hang — POT 작업을 트리 종료하고 대기 큐를 해제한다."""
        gs = self._ensure_gate_state()
        if not gs.gate_active:
            return
        self._stop_gate_watchdog()
        if not self._pot_manager.is_busy():
            return
        # cancel()에서 pot_finished가 즉시 발행되어도 보류 요청은 재실행되지 않는다.
        self._pending_download = None
        gate_state.clear_retry(gs)
        self._pot_manager.cancel()
        self.append_concise_log(
            log_emitter.emit_event("SYS", "WARN", "POT", "gate timeout — pot abandoned"),
            is_status=False,
            is_error=False,
        )
        self.update_ui_state()

    def _arm_analysis_watchdog(self):
        """[Watchdog] 분석 스폰 1회 무장 — 이후 만료 판정은 폴링이 담당한다."""
        gs = self._ensure_gate_state()
        gate_state.arm_analysis(gs)

    def _disarm_analysis_watchdog(self):
        """[Watchdog] 분석 마감(성공/실패/만료) 해제 — 만료의 영속 재판정을 끊는다."""
        gs = self._ensure_gate_state()
        gate_state.disarm_analysis(gs)

    def _poll_watchdogs(self):
        """1초마다 워치독 타임아웃을 폴링해 발화 조건 충족 시 처리.

        기동 폴백은 여기서 판정하지 않는다 — 만료의 단일 기준은 _fallback_timer며,
        이중 판정은 Followup-4 유예(재무장 직후 폴링이 유예를 끊는 결함)를 낳았다.
        """
        gs = self._ensure_gate_state()
        # 1) 게이트 워치독
        if gs.gate_active and gs.gate_watchdog.check_timeout():
            self._on_gate_timeout()
            return

        # 2) 분석 워치독 — 워커의 activity 신호가 수명을 연장하고,
        #    만료 시 여기서 복구(워커 유기 + FAIL 마감)를 단독 수행한다.
        if gs.analysis_active and gs.analysis_watchdog.check_timeout():
            self._on_analysis_timeout()
            return

    def _on_analysis_timeout(self):
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
        
        # 2. 수급 중(UpdateWorker/POTManager) 감지
        is_upgrading = (
            hasattr(self, "update_worker") 
            and self.update_worker is not None 
            and self.update_worker.isRunning()
        )
        is_pot_busy = (
            hasattr(self, "_pot_manager") 
            and self._pot_manager is not None 
            and self._pot_manager.is_busy()
        )

        parent_dlg = (
            self.settings_dlg
            if (hasattr(self, "settings_dlg")
                and self.settings_dlg
                and self.settings_dlg.isVisible())
            else self
        )

        # 수급 중이면 전용 다이얼로그 표시
        if is_upgrading or is_pot_busy:
            dlg = DepsProvisioningDialog(
                parent_dlg, 
                is_upgrading=is_upgrading, 
                is_pot_busy=is_pot_busy
            )
        else:
            dlg = ExitConfirmDialog(parent_dlg, is_running=is_running)

        # 3. [소리 복구 & 반짝임] Windows 시스템 알림 음(Beep) 재생 및 작업 표시줄 알림
        if platform.system() == "Windows":
            self._flash_dialog(dlg, winsound)

        result = dlg.exec()

        # [종료] 클릭 시 -> 스레드 안전 중단 후 즉시 종료
        if result == 1:
            # 수급 중 강제 종료 시 협조적 취소 요청
            if is_upgrading and hasattr(self, "update_worker") and self.update_worker is not None:
                self.update_worker.cancel()
            if is_pot_busy and hasattr(self, "_pot_manager") and self._pot_manager is not None:
                self._pot_manager.cancel()

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

            # 프로비저닝 아티팩트 정리 (종료 시)
            import chzzktube.infra.cleanup as _cleanup
            _cleanup.cleanup_on_shutdown()

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
        from chzzktube.infra.platform import flash_window, play_beep

        play_beep()
        hwnd = int(dlg.winId())
        flash_window(hwnd)

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
                lines = [raw.strip() for raw in f if raw.strip() and not raw.strip().startswith("#")]
            if lines:
                self.url_input.setText("\n".join(lines))
                self.append_concise_log(
                    log_emitter.emit_event("SYS", "OK", "MAIN", f"TXT — {len(lines)} URLs"),
                    is_status=False,
                    is_error=False,
                )
        except OSError:
            self.append_concise_log(
                log_emitter.emit_event("SYS", "FAIL", "MAIN", "TXT read fail"),
                is_status=False,
                is_error=True,
            )

    def abort_download(self):
        if self.ctrl.running:
            self.ctrl.request_cancel()
            self.append_concise_log(
                log_emitter.emit_event("DL", "ABORT", "-", "download canceled by user"),
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
            self._disarm_analysis_watchdog()

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
                log_emitter.emit_event("SYS", "OK", "CFG", f"path → {self.cfg['download_path']}"),
                is_status=False,
                is_error=False,
            )

    def format_target_url(self, url, max_len=50):
        return log_emitter.format_target_url(url, max_len)

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
            self._disarm_analysis_watchdog()
            self.ctrl.abandon_analysis()
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
                log_emitter.emit_event("POT", "RUN", "POT", "starting..."),
                is_status=True,
                is_error=False,
            )
            self._pot_manager.ensure_ready("gate")
            self._start_gate_watchdog()

    def _preflight_deps_check(self) -> bool:
        """런타임 deps 무결성 사전 체크 — 실패 시 사용자 알림 후 False 반환."""
        from chzzktube.infra.updater import verify_deps_integrity
        ok, missing = verify_deps_integrity()
        if not ok:
            self.append_concise_log(
                log_emitter.emit_event("DEPS", "FAIL", "DEPS", f"deps missing: {', '.join(missing)}"),
                False,
                True,
            )
            try:
                from chzzktube.ui.dialogs import TuiNoticeDialog
                from PySide6.QtWidgets import QWidget
                # 부모가 유효한 QWidget인지 확인 (테스트 mock 환경 방지)
                if isinstance(self, QWidget):
                    TuiNoticeDialog(
                        self,
                        title="ChzzkTube",
                        text=f"missing dependencies:\n{', '.join(missing)}\nrestart to auto-provision",
                        ok_label="OK",
                    ).exec()
            except Exception:
                pass
            return False
        return True

    def run_analysis(self):
        url = self.url_input.text().strip()
        if not url:
            return
        if not self._preflight_deps_check():
            return
        self.append_concise_log(
            log_emitter.emit_event("ANAL", "RUN", "YT", "analyzing..."),
            is_status=True,
            is_error=False,
        )
        self._discard_analysis_result()
        self.base_anim_url = url
        self._arm_analysis_watchdog()
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

        # [v3.8.0 Hyper-Minimalist TUI] ANAL 마감 정갈 명세:
        #   1) RUN  complete 라인            — analyzing complete!
        #   2) OK   제목 · 채널              — [제목] · [채널명]
        #   3) OK   가용성(public/member 등) — POT 스코프
        #   4) OK   대표 포맷(코덱)          — streams isolated
        availability = str(info.get("availability") or "").strip() or "-"
        platform_tag = self._platform_of_url()
        raw_log.raw(
            "anal",
            LogEvent(
                stage="ANAL", status="RUN", scope=platform_tag,
                msg=log_emitter.analysis_done_msg(), is_status=True, is_error=False,
            ),
            to_tui=True,
        )
        meta_msg = f"[{title}] · {uploader}" if (title and uploader) else (title or uploader or "unknown")
        raw_log.raw(
            "anal",
            LogEvent(
                stage="ANAL", status="OK", scope=platform_tag,
                msg=meta_msg, is_error=False,
            ),
            to_tui=True,
        )
        raw_log.raw(
            "anal",
            LogEvent(
                stage="ANAL", status="OK", scope="POT",
                msg=f"[{availability}]", is_error=False,
            ),
            to_tui=True,
        )

        self._analysis_block_active = True
        self._analysis_block_count = self.console.last_status_block_count
        self._analysis_last_line = self.console.last_content_block_text()

        self._emit_format_logs(v_list, a_list, platform_tag)

    def _emit_format_logs(self, v_list, a_list, platform_tag):
        # [v3.8.0 Hyper-Minimalist TUI] ANAL 마감 4행 명세의 4번째 행 —
        # 비디오/오디오 대표 코덱을 지시서 형식([codec] · [codec])으로 1줄 발행.
        v_seen = list(dict.fromkeys(short_codec(f.get("vcodec")) for f in v_list if f.get("vcodec")))
        a_seen = list(dict.fromkeys(short_codec(f.get("acodec")) for f in a_list if f.get("acodec")))
        parts = [f"[{c}]" for c in v_seen[:1] + a_seen[:1] if c]
        if not parts:
            return
        raw_log.raw(
            "anal",
            LogEvent(
                stage="ANAL",
                status="OK",
                scope=platform_tag,
                msg=" · ".join(parts),
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
            for label, _, cur, latest in stale:
                self.append_concise_log(
                    log_emitter.emit_event("DEPS", "WARN", label.upper(), f"update {cur}→{latest}"),
                    is_status=False,
                    is_error=False,
                )
            self._stale_updates = True
        else:
            self._stale_updates = False
            self.append_concise_log(
                log_emitter.emit_event("DEPS", "OK", "-", "deps ok"),
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
        # [P5] 수급 진행 하트비트 → 폴백 타이머 연장
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
                log_emitter.emit_event("DEPS", "FAIL", "MAIN",
                                       "deps fail: " + ", ".join(self._deps_failed)),
                is_status=False,
                is_error=True,
            )

    def _on_pot_finished(self, ok: bool, msg: str):
        self._stop_gate_watchdog()
        # [Followup-6] 봇 체크 재시도가 대기 중이면 POT 준비와 함께 재분석한다.
        if ok and self._ensure_gate_state().pot_retry_pending:
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

    def _ensure_gate_state(self):
        """[Task 4-2] GateState 보장 — 기존 테스트 대역(SimpleNamespace)이
        직접 플래그만 가질 때 자동으로 GateState를 구성해 호환성을 유지한다.
        Thin Wrapper 금지(§6) 준수: gate_state 모듈 함수가 판정 로직의
        단일 진실이며, 여기는 호출부 컨테이너 생성만 담당한다.
        """
        if getattr(self, "_gate_state", None) is not None:
            return self._gate_state
        # watchdog 인스턴스는 property일 수 있지만, 재귀 루프를 막기 위해
        # property 내부가 또 _ensure_gate_state를 호출하기 전에 종료해야 한다.
        # _gate_watchdog/_analysis_watchdog property는 자신의 _gate_state를
        # 먼저 조회하므로, _gate_state가 없을 때만 인스턴스 dict로 폴백한다.
        # _analysis_watchdog_raw 키도 함께 확인한다 (테스트 대역 Raw 저장용).
        gs = GateState(
            self.__dict__.get("_gate_watchdog", None),
            self.__dict__.get("_analysis_watchdog",
                              self.__dict__.get("_analysis_watchdog_raw", None)),
        )
        # 기존 플래그 값 마이그레이션 (설정자 우선, 없으면 기본 False)
        # __dict__ 직접 조회 대신 getattr 사용 — 테스트 대역의 property getter가
        # 다시 _ensure_gate_state()를 호출하는 순환(RecursionError)을 원천 차단한다.
        # watchdog 인스턴스는 property일 수 있으므로 getattr 유지 (재귀 없음).
        gs.gate_active = bool(getattr(self, "_gate_watchdog_active", False))
        gs.analysis_active = bool(getattr(self, "_analysis_watchdog_active", False))
        gs.pot_retry_pending = bool(getattr(self, "_pot_retry_pending", False))
        gs.pot_retry_url = getattr(self, "_pot_retry_url", None)
        gs.pot_retry_done = getattr(self, "_pot_retry_done", set())
        self._gate_state = gs
        return gs

    def get_current_app_state(self) -> str:
        """[P3b] POT 백그라운드 작업(is_busy)은 입력 잠금 사유가 아니다 — 그 역할은
        toggle_download의 큐잉(_pending_download)이 맡는다. is_busy를 STARTUP 사유로
        두면 프리웜 진행 중 ENTER가 큐잉 분기에 도달하지 못하고 무반응으로 끝났다.
        """
        if not getattr(self, "_startup_completed", False):
            return "STARTUP"
        if self.ctrl.running:
            return "RUNNING"
        if self.ctrl.analyzing:
            return "ANALYZING"
        if self.ctrl.picking:
            return "PICKING"
        return "IDLE"

    def _start_gate_watchdog(self):
        """[Followup-3] POT gate 대기 2차 워치독 기동."""
        gate_state.start_gate(self._ensure_gate_state())

    def _stop_gate_watchdog(self):
        gate_state.stop_gate(self._ensure_gate_state())

    def _on_pot_work_tick(self):
        """실제 POT 진행만 활성 게이트를 연장한다. 완료 후에는 재무장하지 않는다."""
        gate_state.on_pot_work_tick(self._ensure_gate_state())

    def _on_gate_timeout(self):
        """[Followup-3] gate hang — POT 작업을 트리 종료하고 대기 큐를 해제한다."""
        gs = self._ensure_gate_state()
        if not gs.gate_active:
            return
        self._stop_gate_watchdog()
        if not self._pot_manager.is_busy():
            return
        # cancel()에서 pot_finished가 즉시 발행되어도 보류 요청은 재실행되지 않는다.
        self._pending_download = None
        gate_state.clear_retry(gs)
        self._pot_manager.cancel()
        self.append_concise_log(
            log_emitter.emit_event("SYS", "WARN", "POT", "gate timeout — pot abandoned"),
            is_status=False,
            is_error=False,
        )
        self.update_ui_state()

    def _arm_analysis_watchdog(self):
        """[Watchdog] 분석 스폰 1회 무장 — 이후 만료 판정은 폴링이 담당한다."""
        gate_state.arm_analysis(self._ensure_gate_state())

    def _disarm_analysis_watchdog(self):
        """[Watchdog] 분석 마감(성공/실패/만료) 해제 — 만료의 영속 재판정을 끊는다."""
        gate_state.disarm_analysis(self._ensure_gate_state())

    def _on_analysis_timeout(self):
        """[Watchdog] 분석 무응답 — 워커를 유기하고 FAIL로 마감한다.

        강제 terminate() 금지. 유기된 워커는 좀비 패턴으로 자연 종료를 기다리고,
        늦게 도착한 결과는 `_is_stale_analyze_signal()`이 폐기한다.
        """
        self._disarm_analysis_watchdog()
        if not self.ctrl.analyzing:
            return
        self.ctrl.abandon_analysis()
        self._pick_pending = False
        self._pick_targets = []
        self.ctrl._set_picking(False)
        self.update_ui_state()
        self.append_concise_log(
            log_emitter.emit_event(
                "ANAL", "FAIL", self._platform_of_url(),
                f"analysis timeout ({ANALYSIS_TIMEOUT_SEC:.0f}s) - no progress",
            ),
            True,
            True,
        )

    def _maybe_retry_analysis(self, err_msg: str) -> bool:
        """[Followup-6] 봇 체크 실패 시 POT 서버 기동 후 1회만 재분석을 큐잉한다."""
        if not _needs_pot_retry(err_msg):
            return False
        gs = self._ensure_gate_state()
        if gs.pot_retry_pending:
            return False
        url = self.url_input.text().strip()
        if not gate_state.schedule_retry(gs, url):
            return False
        self.append_concise_log(
            log_emitter.emit_event("POT", "RUN", "POT",
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
        """[Followup-6] POT 준비 완료 후 보류 URL을 명시적으로 재분석한다."""
        url = gate_state.consume_retry(self._ensure_gate_state())
        if not url:
            return
        self.url_input.setText(url)
        self.append_concise_log(
            log_emitter.emit_event("POT", "RUN", "YT", "retrying analysis with po token"),
            is_status=True,
            is_error=False,
        )
        self._arm_analysis_watchdog()
        if not self._preflight_deps_check():
            return
        self.ctrl.spawn_analyzer(url, self.cfg)
        self.update_ui_state()

    def _is_stale_analyze_signal(self) -> bool:
        """유령 분석 결과 판별 — 지운 뒤 "stream analyzed"가 한 번 더 뜨는 버그 차단."""
        if not self.ctrl.state.analyzing:
            return True
        return not bool(self.url_input.text().strip())

    def on_analyze_success(self, data):
        if self._is_stale_analyze_signal():
            return
        self._disarm_analysis_watchdog()
        self.ctrl._set_analyzing(False)
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
        self._disarm_analysis_watchdog()
        self.ctrl._set_analyzing(False)
        # [v3.8.0] 분석 실패 시 잔여 분석 데이터 즉시 초기화 —
        # 이전 URL의 info로 억지 다운로드가 실행되는 것을 원천 차단.
        self.extracted_data = {"info": None, "v_list": [], "a_list": []}
        pick_pending = getattr(self, "_pick_pending", False)
        self._pick_pending = False
        if pick_pending:
            self.ctrl._set_picking(False)
        self.stop_analysis_anim(ok=False)
        self.update_ui_state()
        self.append_concise_log(
            log_emitter.emit_event("ANAL", "FAIL", "-", err_msg),
            True,
            True,
        )
        # [쿠키 팝업 인터락 v3.8.0] 멤버십/연령제한 감지 시 쿠키 선택창 자동 표시
        low = (err_msg or "").lower()
        if (
            "chzzk cookie expired" in low
            or "members-only" in low
            or "member gated" in low
            or ("age" in low and "restricted" in low)
            or "confirm your age" in low
        ):
            from chzzktube.ui.dialogs import CookieSelectDialog
            dlg = CookieSelectDialog(self)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                self.cfg["browser_cookie"] = dlg.selected_type
                # 재분석 트리거
                if self._preflight_deps_check():
                    self.ctrl.spawn_analyzer(self.url_input.text().strip(), self.cfg)
            return
        # [Followup-6] 봇 체크/PO 토큰 사유면 POT 기동 후 1회 재시도를 큐잉한다.
        if self._maybe_retry_analysis(err_msg):
            return

    def _retry_deps(self):
        """[v3.8.1] deps 에러 시 ENTER로 재시도 — 에러 상태 초기화 후 재시도."""
        # 에러 상태 초기화
        self._startup_coord._state.deps_error_msg = ""
        # URL 입력창에 포커스
        self.url_input.setFocus()
        # deps 체크 재시도 (toggle_download와 유사하지만 에러 상태에서 호출)
        try:
            targets = MediaController.parse_targets(
                self.url_input.text().strip(),
                dedup=self.cfg.get("remove_duplicates"),
            )
        except ValueError as e:
            self.append_concise_log(
                log_emitter.emit_event("ANAL", "FAIL", "-", f"Invalid URL format — {e}" if "Invalid URL" not in str(e) else str(e)),
                False,
                True,
            )
            return
        if not targets:
            return
        # deps 재시도 트리거
        self._startup_coord.report_deps(False, "")  # 에러 상태 클리어용
        self.toggle_download()

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
        elif state == "STARTUP" and self._startup_coord._state.deps_error_msg:
            # [v3.8.1] deps 에러 시 재시도 버튼 표시
            self.btn_enter.setEnabled(True)
            self.btn_enter.setText("[ ENTER: Retry Setup ]")
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

    def _finalize_concise_progress(self, line, is_status, is_error, component_id):
        """component_id로 추적 중인 TUI 진행 라인을 마감 이벤트로 확정한다."""
        if not component_id:
            return False
        console = getattr(self, "console", None)
        progress_lines = getattr(console, "_progress_lines", None)
        buffer = getattr(console, "_buffer", None)
        if not isinstance(progress_lines, dict) or buffer is None:
            return False

        index = progress_lines.get(component_id)
        if not isinstance(index, int) or not (0 <= index < len(buffer)):
            progress_lines.pop(component_id, None)
            return False

        entry = dict(buffer[index])
        entry.update({
            "msg": line,
            "is_status": bool(is_status),
            "is_error": bool(is_error),
            "component_id": component_id,
            "is_progress": False,
        })
        buffer[index] = entry
        progress_lines.pop(component_id, None)
        reflow = getattr(console, "reflow", None)
        if callable(reflow):
            reflow()
        return True

    # [v3.9.0] 로그 미러는 ui/log_mirror.py로 이전 — 아래 4종은 호환 바인딩.
    def _finalize_concise_progress(self, line, is_status, is_error, component_id):
        from chzzktube.ui import log_mirror as _lm

        return _lm.finalize_concise_progress(self, line, is_status, is_error, component_id)

    def _render_concise(self, event, is_status=False, is_error=False):
        from chzzktube.ui import log_mirror as _lm

        return _lm.render_concise(self, event, is_status, is_error)

    def _mirror_event_full(self, event, is_status=False):
        from chzzktube.ui import log_mirror as _lm

        return _lm.mirror_event_full(self, event, is_status)

    def _mirror_full_log(self, line, is_status=False, component_id: str = None):
        from chzzktube.ui import log_mirror as _lm

        return _lm.mirror_full_log(self, line, is_status, component_id)

    def append_concise_log(self, msg, is_status=False, is_error=False, fg_color=None):
        if isinstance(msg, LogEvent):
            msg.is_status = is_status
            msg.is_error = is_error
            raw_log.raw("ui", msg, to_tui=True)
        else:
            raw_log.raw("ui", msg, is_status=is_status, is_error=is_error, to_tui=True)

    def toggle_verbose_log(self):
        """F12 상세 로그 창 토글 — 정돈된 버퍼만 표시."""
        if getattr(self, "verbose_win", None) is not None and self.verbose_win.isVisible():
            self.verbose_win.close()
            return
        if self.verbose_win is None:
            self.verbose_win = VerboseLogWindow(self)
            content = "\n".join(self._full_log_buf)
            if not content.strip():
                content = log_emitter.emit_event("SYS", "OK", "LOG", "empty buffer")
            self.verbose_win.set_content(content)
            self._full_log_win_n = len(self._full_log_buf)
        else:
            pending = list(self._full_log_buf)[self._full_log_win_n:]
            for line in pending:
                # [초천재의 무결점 렌더링] 지연 동기화 시에도 임의로 False를 박지 않고 상태 플래그를 정직하게 반영!
                is_stat = getattr(self, "_last_full_was_status", False)
                self.verbose_win.append(line, is_stat)
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
        if key == Qt.Key.Key_Return or key == Qt.Key.Key_Enter:
            # [v3.8.1] deps 에러 시 ENTER로 재시도
            if self._startup_coord._state.deps_error_msg and not self._startup_completed:
                self._retry_deps()
                event.accept()
                return
            # [v3.8.1] Setup 완료 후 ENTER로 다운로드 시작
            if self._startup_completed:
                self.toggle_download()
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

        if not self._preflight_deps_check():
            return

        try:
            targets = MediaController.parse_targets(
                self.url_input.text().strip(),
                dedup=self.cfg.get("remove_duplicates"),
            )
        except ValueError as e:
            # [v3.8.0 게이트] 비URL 임의 문자열 등 — 파이프라인 진입 전 1회 경고 후 중단.
            self.append_concise_log(
                log_emitter.emit_event("ANAL", "FAIL", "-", f"Invalid URL format — {e}" if "Invalid URL" not in str(e) else str(e)),
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
                log_emitter.emit_event("SYS", "RUN", "POT", "queued — waiting for pot server"),
                is_status=True,
                is_error=False,
            )
            return
        if needs_pot:
            self._wait_pot_if_needed()
            if not self._pot_manager.is_ready():
                self._pending_download = (targets, "auto", "auto")
                self.append_concise_log(
                    log_emitter.emit_event("SYS", "RUN", "POT", "queued — waiting for pot server"),
                    is_status=True,
                    is_error=False,
                )
                return

        self._start_download(targets, "auto", "auto")

    def _start_download(self, targets, v_id, a_id):
        # [v3.8.0 2차 방어선] 워커 구동 직전 URL 재검증 — 잔여 데이터/직접 호출
        # 경로로 비URL이 유입되는 것을 최종 차단한다.
        bad = [t for t in targets or [] if not _is_valid_url(getattr(t, "url", t))]
        if bad:
            self.append_concise_log(
                log_emitter.emit_event(
                    "ANAL", "FAIL", "-",
                    f"Invalid URL format: {bad[0][:40]}",
                ),
                False,
                True,
            )
            return
        self.ctrl.begin_download()
        self.append_concise_log(
            log_emitter.emit_event("DL", "RUN", "YT", "downloading..."),
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
            log_emitter.emit_event("POT", "RUN", "POT", "starting server..."),
            is_status=True,
            is_error=False,
        )
        self._pot_manager.ensure_ready("gate")
        self._start_gate_watchdog()

    def _start_pick_flow(self, url):
        self._pick_targets = [url]
        self._pick_pending = True
        self.append_concise_log(
            log_emitter.emit_event("ANAL", "RUN", "YT", "analyzing formats..."),
            is_status=True,
            is_error=False,
        )
        self._arm_analysis_watchdog()
        if not self._preflight_deps_check():
            return
        self.ctrl.spawn_analyzer(url, self.cfg, deep=True)
        self.update_ui_state()

    def _show_pick_menu(self, data):
        v_list = data.get("v_list", [])
        a_list = data.get("a_list", [])
        if not v_list and not a_list:
            self.append_concise_log(
                log_emitter.emit_event("ANAL", "FAIL", "YT", "no formats for pick"),
                False,
                True,
            )
            self.update_ui_state()
            return
        from chzzktube.core.log_emitter import format_pick_menu

        lines = format_pick_menu(v_list, a_list)
        lines.append("enter: 'N' video  /  'N.M' v+a  /  empty=best")
        self.append_concise_log("\n".join(lines), False, False)
        self.ctrl._set_picking(True)
        self.url_input.setFocus()
        self.update_ui_state()

    def _submit_pick(self):
        targets = getattr(self, "_pick_targets", None)
        if not targets:
            self.ctrl._set_picking(False)
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
                    log_emitter.emit_event("ANAL", "FAIL", "YT", "pick fail — retry"),
                    False,
                    True,
                )
                return
        self.ctrl._set_picking(False)
        self.append_concise_log(
            log_emitter.emit_event("DL", "OK", "YT", f"picked {v_id} · {a_id}"),
            False,
            False,
        )
        self._start_download(list(targets), v_id, a_id)

    def _cancel_pick(self):
        self.ctrl._set_picking(False)
        self._pick_pending = False
        self._pick_targets = []
        self.append_concise_log(
            log_emitter.emit_event("DL", "ABORT", "YT", "format pick canceled"),
            False,
            True,
        )
        self.update_ui_state()

    def skip_current(self):
        if self.ctrl.running:
            self.ctrl.request_skip()
            self.append_concise_log(
                log_emitter.emit_event("DL", "SKIP", "MAIN", "skip requested"),
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

    from chzzktube.infra.platform import set_app_user_model_id

    set_app_user_model_id("chzzktube.subapp.v2")

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