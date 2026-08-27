# theme.py - 다크 테마 색상 팔레트 및 QSS 단일 출처 (Single Source of Truth)
"""
UI 스킨 관련 문자열은 이 모듈에서만 정의한다.
main.py / dialogs.py 는 여기서 임포트해 사용한다.
값 변경 시 앱 전체 테마가 일관되게 반영된다.
"""

# ──────────────────────────────────────────────────────────────
# 색상 팔레트
# ──────────────────────────────────────────────────────────────
BG_WINDOW = "#121212"        # 창/다이얼로그 배경
BG_SURFACE = "#1e1e1e"       # 패널·입력 배경
BG_CONSOLE = "#0d0d0d"       # 콘솔 로그 배경
FG_TEXT = "#e3e3e3"          # 기본 전경
ACCENT_GREEN = "#02b275"     # 브랜드 그린 (다운로드/포커스)
STATUS_BLUE = "#64b5f6"      # 상태/메타 강조 파랑

# ──────────────────────────────────────────────────────────────
# MainWindow 전역 위젯 스타일
# ──────────────────────────────────────────────────────────────
MAIN_WINDOW_QSS = """
    QMainWindow, QDialog {
        background-color: #121212;
        color: #e3e3e3;
        font-family: 'Segoe UI', sans-serif;
        font-size: 12px;
    }
    QLabel {
        color: #e3e3e3;
    }
    QPushButton {
        background-color: #2b2b2b;
        color: #e3e3e3;
        border: 1px solid #3d3d3d;
        border-radius: 6px;
        padding: 6px 14px;
        font-weight: bold;
        font-size: 12px;
    }
    QPushButton:hover {
        background-color: #353535;
        border-color: #4a4a4a;
    }
    QPushButton:pressed {
        background-color: #1c1c1c;
        border-color: #303030;
    }
    QPushButton:disabled {
        background-color: #181818;
        color: #5a5a5a;
        border-color: #2d2d2d;
    }
    QLineEdit {
        background-color: #1e1e1e;
        color: #ffffff;
        border: 1px solid #3d3d3d;
        border-radius: 6px;
        padding: 8px 46px 8px 10px;
        font-size: 13px;
    }
    QLineEdit:hover {
        border-color: #4d4d4d;
    }
    QLineEdit:focus {
        border: 1.5px solid #02b275;
        background-color: #151515;
    }
    QLineEdit::clear-button {
        subcontrol-position: right;
        subcontrol-origin: padding;
        position: relative;
        right: 22px;
        width: 20px;
        height: 20px;
    }
    QTextEdit {
        background-color: #0d0d0d;
        color: #d4d4d4;
        border: 1px solid #2d2d2d;
        border-radius: 6px;
        font-family: 'Consolas', monospace;
        font-size: 12px;
        padding: 8px;
    }
    QProgressBar {
        text-align: center;
        border: none;
        border-radius: 5px;
        background-color: #1e1e1e;
        height: 8px;
        font-size: 10px;
        color: transparent;
    }
    QProgressBar::chunk {
        background-color: #02b275;
        border-radius: 5px;
    }
"""

# ──────────────────────────────────────────────────────────────
# 콘솔 로그 영역
# ──────────────────────────────────────────────────────────────
CONSOLE_INIT_QSS = """
    QTextEdit {
        background-color: #0d0d0d;
        color: #4caf50;
        border: 1px solid #2d2d2d;
        border-radius: 6px;
        font-family: 'Consolas', monospace;
        font-size: 12px;
        padding: 10px 10px 35px 10px; /* CLI 터미널 감성 하단 35px 여백 */
    }
"""

CONSOLE_LOG_QSS = """
    QTextEdit {
        background-color: #0d0d0d;
        color: #4caf50;
        border: 1px solid #2d2d2d;
        border-radius: 6px;
        padding: 10px 10px 50px 10px; /* [여백 확대] 하단 여백을 50px로 넉넉하게 확장 */
    }
    /* 스크롤바 전체 너비 줄임 (6px 슬림 바) */
    QScrollBar:vertical {
        border: none;
        background: transparent;
        width: 6px;
        margin: 0px 0px 0px 0px;
    }
    /* 스크롤바 이동 손잡이 (약간 어두운 회색 -> 호버 시 조금 더 밝게) */
    QScrollBar::handle:vertical {
        background: #333333;
        min-height: 20px;
        border-radius: 3px;
    }
    QScrollBar::handle:vertical:hover {
        background: #555555;
    }
    /* 화살표 버튼 완전히 가리고 크기 0으로 제거 */
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        border: none;
        background: none;
        height: 0px;
    }
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
        background: none;
    }
"""

# 간결 로그 색 위계 — 구조는 조용히, 값은 또렷이, 상태만 액센트 (3단 그레이 + 액센트)
LOG_COLOR_SUCCESS = "#4caf50"   # [v] 성공 헤더 — 유일한 초록 액센트
LOG_COLOR_ERROR = "#ff5252"     # [!]/[X] 에러·경고
LOG_COLOR_INFO = "#b0b6bc"      # [+]/[~] 정보·진행 헤더 (회백)
LOG_COLOR_STRUCT = "#5f6a72"    # 트리 글리프·라벨 (딤 그레이)
LOG_COLOR_VALUE = "#e8eaed"     # 트리 값·일반 텍스트 (화이트)

# ──────────────────────────────────────────────────────────────
# 패널 · 라벨
# ──────────────────────────────────────────────────────────────
BAR_PANEL_QSS = f"background-color: {BG_SURFACE}; border-radius: 8px;"
LBL_STATUS_QSS = f"color: {STATUS_BLUE}; font-weight: bold; font-size: 11px;"
LBL_META_QSS = f"color: {STATUS_BLUE}; font-weight: bold;"
LBL_STREAM_QSS = "color: #aaa; font-size: 11px; padding-left: 8px;"

# 액션 버튼 (상태별)
BTN_SETTINGS_FONT_QSS = (
    "QPushButton { font-family: 'MS Gothic', 'Segoe UI', sans-serif; }"
)

BTN_PRIMARY_QSS = (   # 다운로드 시작 (그린)
    "QPushButton { background-color: #02b275; color: white; border: none; } "
    "QPushButton:hover { background-color: #03cb85; } "
    "QPushButton:pressed { background-color: #018f5d; } "
    "QPushButton:disabled { background-color: #143d2c; color: #5a5a5a; }"
)

BTN_DANGER_QSS = (    # 작업 종료 (레드)
    "QPushButton { background-color: #c62828; color: white; border: none; } "
    "QPushButton:hover { background-color: #e53935; } "
    "QPushButton:pressed { background-color: #b71c1c; } "
    "QPushButton:disabled { background-color: #3e1515; color: #5a5a5a; }"
)

BTN_INFO_QSS = (      # 건너뛰기 (블루)
    "QPushButton { background-color: #1565c0; color: white; border: none; } "
    "QPushButton:hover { background-color: #1e88e5; } "
    "QPushButton:pressed { background-color: #0d47a1; } "
    "QPushButton:disabled { background-color: #12213d; color: #5a5a5a; }"
)

# ──────────────────────────────────────────────────────────────
# 다이얼로그
# ──────────────────────────────────────────────────────────────
MSGBOX_QSS = """
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
"""

BTN_EXIT_DANGER_QSS = (
    "QPushButton { background-color: #c62828; color: white; border: none; "
    "font-weight: bold; } QPushButton:hover { background-color: #e53935; }"
)

BTN_NEUTRAL_QSS = (
    "QPushButton { background-color: #2b2b2b; color: #e3e3e3; "
    "border: 1px solid #3d3d3d; }"
)

DIALOG_BG_QSS = (
    "background-color: #121212; color: #ffffff; font-family: 'Segoe UI', sans-serif;"
)

BTN_GRID_QSS = (
    "QPushButton { background-color: #2b2b2b; color: #e3e3e3; border: 1px solid #3d3d3d; "
    "border-radius: 6px; padding: 8px; font-size: 12px; font-weight: bold; } "
    "QPushButton:hover { background-color: #353535; border-color: #4a4a4a; } "
    "QPushButton:pressed { background-color: #1c1c1c; }"
)

TE_CONTENT_QSS = """
    QTextEdit {
        background-color: #0d0d0d;
        color: #d4d4d4;
        border: 1px solid #2d2d2d;
        border-radius: 6px;
        font-family: 'Consolas', monospace;
        font-size: 11px;
        padding: 8px;
    }
"""

BTN_CLOSE_QSS = """
    QPushButton {
        background-color: #2b2b2b; color: #e3e3e3; border: 1px solid #3d3d3d;
        border-radius: 6px; padding: 6px 16px; font-weight: bold;
    }
    QPushButton:hover { background-color: #353535; border-color: #4a4a4a; }
"""

BTN_SECONDARY_QSS = (
    "QPushButton { background-color: #2b2b2b; color: #e3e3e3; border: 1px solid #3d3d3d; "
    "border-radius: 6px; padding: 6px 16px; font-weight: bold; } "
    "QPushButton:hover { background-color: #353535; border-color: #4a4a4a; }"
)

BTN_SUCCESS_QSS = (
    "QPushButton { background-color: #02b275; color: white; border: none; "
    "border-radius: 6px; padding: 6px 16px; font-weight: bold; } "
    "QPushButton:hover { background-color: #03cb85; } "
    "QPushButton:pressed { background-color: #018f5d; }"
)

# 설정 다이얼로그 — 섹션 타이틀 / 상태 라벨 / 고스트 버튼 / 스크롤 영역
DLG_SECTION_TITLE_QSS = (
    "font-weight: bold; font-size: 12px; border: none; background: transparent;"
)
DLG_STATUS_QSS = (
    "color: #9e9e9e; font-size: 11px; border: none; background: transparent;"
)
DLG_GHOST_BTN_QSS = (
    "QPushButton { background-color: #2b2b2b; color: #e3e3e3; border: 1px solid #3d3d3d; "
    "border-radius: 6px; padding: 4px 10px; font-size: 11px; } "
    "QPushButton:hover { background-color: #353535; border-color: #4a4a4a; } "
    "QPushButton:disabled { background-color: #181818; color: #5a5a5a; border-color: #2d2d2d; }"
)
SETTINGS_SCROLL_QSS = """
    QScrollArea { background: transparent; border: none; }
    QScrollBar:vertical { background: transparent; width: 8px; margin: 4px 2px 4px 0; }
    QScrollBar::handle:vertical { background: #3d3d3d; border-radius: 4px; min-height: 30px; }
    QScrollBar::handle:vertical:hover { background: #4a4a4a; }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
"""