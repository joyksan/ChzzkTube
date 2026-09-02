### theme.py - TUI-inspired fzf 스타일 테마 (Dark Terminal Palette)
""" UI 스킨 문자열은 이 모듈에서만 정의한다. main.py / dialogs.py / log_console.py 는 여기서 임포트해 사용한다. """

### 색상 팔레트 (fzf-inspired dark terminal)
BG_WINDOW = "#0d0d0d"        # 메인/다이얼로그 콘솔 톤
BG_SURFACE = "#252525"       # 패널 배경
BG_CONSOLE = "#0d0d0d"       # 콘솔 배경
BG_HOVER = "#2a2a2a"         # 호버 배경
FG_TEXT = "#e3e3e3"          # 기본 전경
FG_DIM = "#888888"           # 딤 텍스트
BORDER = "#444444"           # 테두리
ACCENT = "#4ec9b0"           # 액센트 (청록)
ACCENT_ALT = "#ce9178"       # 보조 액센트 (주황)
ERROR = "#f44747"            # 에러 레드
WARN = "#e5c07b"             # 경고 옐로
SUCCESS = "#6a9955"          # 성공 그린

### MainWindow 전역 스타일 (fzf border-line aesthetic)
MAIN_WINDOW_QSS = f"""
QMainWindow, QDialog {{ background-color: {BG_WINDOW}; color: {FG_TEXT}; font-family: 'JetBrains Mono', 'Consolas', 'Cascadia Code', monospace; font-size: 12px; }}
QLabel {{ color: {FG_TEXT}; font-family: 'JetBrains Mono', 'Consolas', monospace; }}
QPushButton {{ background-color: {BG_SURFACE}; color: {FG_TEXT}; border: 1px solid {BORDER}; border-radius: 0px; padding: 4px 12px; font-family: 'JetBrains Mono', 'Consolas', monospace; font-size: 11px; }}
QPushButton:hover {{ background-color: {BG_HOVER}; border-color: {ACCENT}; }}
QPushButton:pressed {{ background-color: #333333; }}
QPushButton:disabled {{ background-color: #1a1a1a; color: #555555; border-color: #333333; }}
QLineEdit {{ background-color: {BG_SURFACE}; color: {FG_TEXT}; border: 1px solid {BORDER}; border-radius: 0px; padding: 6px 10px; font-family: 'JetBrains Mono', 'Consolas', monospace; font-size: 12px; }}
QLineEdit:focus {{ border: 1px solid {ACCENT}; }}
QProgressBar {{ text-align: center; border: none; background-color: {BG_SURFACE}; height: 4px; color: transparent; }}
QProgressBar::chunk {{ background-color: {ACCENT}; }}
QScrollBar:vertical {{ border: none; background: transparent; width: 6px; }}
QScrollBar::handle:vertical {{ background: {BORDER}; min-height: 20px; border-radius: 0px; }}
QScrollBar::handle:vertical:hover {{ background: #555555; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
QListWidget {{ background-color: {BG_CONSOLE}; color: {FG_TEXT}; border: 1px solid {BORDER}; border-radius: 0px; font-family: 'JetBrains Mono', 'Consolas', monospace; font-size: 11px; outline: none; }}
QListWidget::item {{ padding: 3px 6px; border: none; }}
QListWidget::item:hover {{ background-color: {BG_HOVER}; }}
QListWidget::item:selected {{ background-color: #1d3a34; color: {ACCENT}; }}
QSplitter::handle {{ background-color: {BORDER}; }}
"""

### fzf-style 보더 프레임 (타이틀을 보더 위 중앙 배치)
def groupbox_qss(title=""):
    """fzf-style QGroupBox — 타이틀을 보더 위 중앙에 배치."""
    return f"""
QGroupBox {{
    border: 1px solid {BORDER};
    border-radius: 0px;
    margin-top: 8px;
    padding-top: 12px;
    font-family: 'JetBrains Mono', 'Consolas', monospace;
    font-size: 11px;
    color: {FG_DIM};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top center;
    padding: 0 6px;
    background-color: {BG_WINDOW};
    color: {ACCENT};
}}
"""

FRAME_QSS = f"""
QFrame {{
    border: 1px solid {BORDER};
    border-radius: 0px;
    background-color: {BG_SURFACE};
}}
"""
### 콘솔 로그 영역
CONSOLE_LOG_QSS = f"""
QTextEdit {{
    background-color: {BG_CONSOLE};
    color: {FG_TEXT};
    border: 1px solid {BORDER};
    border-radius: 0px;
    font-family: 'JetBrains Mono', 'Consolas', monospace;
    font-size: 11px;
    padding: 4px;
}}
QScrollBar:vertical {{ border: none; background: transparent; width: 6px; }}
QScrollBar::handle:vertical {{ background: {BORDER}; min-height: 20px; border-radius: 0px; }}
QScrollBar::handle:vertical:hover {{ background: #555555; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
"""

### 간결 로그 색 위계
LOG_COLOR_SUCCESS = SUCCESS
LOG_COLOR_ERROR = ERROR
LOG_COLOR_WARN = WARN
LOG_COLOR_INFO = "#b0b6bc"   # 회백 — 정보성 헤더
LOG_COLOR_STRUCT = "#5f6a72"  # 트리 글리프·라벨 (딤 그레이)
LOG_COLOR_VALUE = "#e8eaed"   # 트리 값·일반 텍스트
LOG_COLOR_DIM = FG_DIM
LOG_COLOR_ACCENT = ACCENT
LOG_COLOR_ACCENT_ALT = ACCENT_ALT

### 버튼 QSS — 새 팔레트 단일 출처
BTN_ACTION_QSS = f"""QPushButton {{ background-color: {BG_SURFACE}; color: {ACCENT}; border: 1px solid {ACCENT}; border-radius: 0px; padding: 6px 16px; font-family: 'JetBrains Mono', 'Consolas', monospace; font-size: 11px; }}
QPushButton:hover {{ background-color: #2a3a35; }}
QPushButton:pressed {{ background-color: #1a2a25; }}
QPushButton:disabled {{ background-color: #1a1a1a; color: #555555; border-color: #333333; }}
"""

BTN_DANGER_QSS = f"""QPushButton {{ background-color: {BG_SURFACE}; color: {ERROR}; border: 1px solid {ERROR}; border-radius: 0px; padding: 6px 16px; font-family: 'JetBrains Mono', 'Consolas', monospace; font-size: 11px; }}
QPushButton:hover {{ background-color: #3a2525; }}
QPushButton:pressed {{ background-color: #2a1515; }}
QPushButton:disabled {{ background-color: #1a1a1a; color: #555555; border-color: #333333; }}
"""

BTN_NEUTRAL_QSS = f"""QPushButton {{ background-color: {BG_SURFACE}; color: {FG_TEXT}; border: 1px solid {BORDER}; border-radius: 0px; padding: 6px 16px; font-family: 'JetBrains Mono', 'Consolas', monospace; font-size: 11px; }}
QPushButton:hover {{ background-color: {BG_HOVER}; }}
QPushButton:disabled {{ background-color: #1a1a1a; color: #555555; border-color: #333333; }}
"""
### 다이얼로그 QSS
MSGBOX_QSS = f"""
QMessageBox {{ background-color: {BG_WINDOW}; }}
QLabel {{ color: {FG_TEXT}; font-size: 12px; font-family: 'JetBrains Mono', 'Consolas', monospace; padding: 8px 16px; }}
QPushButton {{ background-color: {BG_SURFACE}; color: {FG_TEXT}; border: 1px solid {BORDER}; border-radius: 0px; padding: 6px 16px; font-family: 'JetBrains Mono', 'Consolas', monospace; min-width: 70px; }}
QPushButton:hover {{ background-color: {BG_HOVER}; border-color: {ACCENT}; }}
QTextEdit {{ background-color: {BG_CONSOLE}; color: {FG_TEXT}; border: 1px solid {BORDER}; border-radius: 0px; font-family: 'JetBrains Mono', 'Consolas', monospace; font-size: 11px; padding: 4px; }}
"""

### 설정 다이얼로그 — 모던 TUI 패널
SETTINGS_TUI_QSS = """
QGroupBox.tui-panel {
    border: 1px solid #2a2a2a;
    border-radius: 6px;
    margin-top: 10px;
    padding: 8px;
    background-color: #0d0d0d;
}
QGroupBox.tui-panel::title {
    subcontrol-origin: margin;
    subcontrol-position: top center;
    padding: 0 8px;
    background-color: #0d0d0d;
    color: #4ec9b0;
    font-size: 11px;
    font-weight: bold;
}
QLabel { color: #cccccc; font-size: 11px; }
QCheckBox { color: #d4d4d4; spacing: 6px; }
QCheckBox::indicator {
    width: 14px; height: 14px;
    border: 1px solid #2a2a2a;
    background: #161616;
    border-radius: 2px;
}
QCheckBox::indicator:checked {
    background: #4ec9b0;
    border-color: #4ec9b0;
}
QPushButton {
    background: #161616;
    color: #d4d4d4;
    border: 1px solid #2a2a2a;
    padding: 4px 12px;
    font-size: 11px;
}
QPushButton:hover {
    border-color: #4ec9b0;
    color: #4ec9b0;
}
"""

DIALOG_BG_QSS = f"background-color: {BG_WINDOW}; color: {FG_TEXT}; font-family: 'JetBrains Mono', 'Consolas', monospace;"
TE_CONTENT_QSS = CONSOLE_LOG_QSS

DLG_SECTION_TITLE_QSS = f"font-weight: bold; font-size: 12px; border: none; background: transparent; color: {ACCENT}; font-family: 'JetBrains Mono', 'Consolas', monospace;"
DLG_STATUS_QSS = f"color: {FG_DIM}; font-size: 11px; border: none; background: transparent; font-family: 'JetBrains Mono', 'Consolas', monospace;"
DLG_GHOST_BTN_QSS = f"""
QPushButton {{ background-color: {BG_SURFACE}; color: {FG_TEXT}; border: 1px solid {BORDER}; border-radius: 0px; padding: 4px 10px; font-size: 11px; font-family: 'JetBrains Mono', 'Consolas', monospace; }}
QPushButton:hover {{ background-color: {BG_HOVER}; border-color: {ACCENT}; }}
QPushButton:disabled {{ background-color: #1a1a1a; color: #555555; border-color: #333333; }}
"""

SETTINGS_SCROLL_QSS = f"""
QScrollArea {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 6px; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 0px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: #555555; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
"""

### MainWindow TUI 스타일 (fzf border-line aesthetic — main.py에서 이동)
### ──────────────────────────────────────────────────────────────
TUI_STYLE = """
/* Core Dark Palette & Monospace Typography */
QWidget, QMainWindow {
    background-color: #0d0d0d;
    color: #cccccc;
    font-family: 'JetBrains Mono', 'Consolas', 'Cascadia Code', monospace;
    font-size: 12px;
}

/* ── Inner Sub-Panels (fzf Style Cards) ── */
QGroupBox.tui-panel {
    border: 1px solid #2a2a2a;
    border-radius: 6px;
    margin-top: 12px;
    padding: 6px;
    background-color: #0d0d0d;
}

QGroupBox.tui-panel::title {
    subcontrol-origin: margin;
    subcontrol-position: top center;
    padding: 0 8px;
    background-color: #0d0d0d;
    color: #4ec9b0;
    font-size: 11px;
    font-weight: bold;
}

QPushButton[class="tui-tag"] {
    background-color: transparent;
    border: none;
    color: #ce9178;
    font-family: 'JetBrains Mono', 'Consolas', monospace;
    font-size: 11px;
    padding: 2px 6px;
}

QPushButton[class="tui-tag"]:hover {
    color: #ffffff;
    background-color: #252526;
    border-radius: 3px;
}

QPushButton[class="tui-tag"]:pressed {
    color: #4ec9b0;
}

QLineEdit#url_input::placeholder { color: #666666; }

QLineEdit#url_input {
    background-color: transparent;
    border: none;
    color: #dcdcdc;
    font-family: 'JetBrains Mono', 'Consolas', monospace;
    font-size: 12px;
    selection-background-color: #264f78;
}

QPlainTextEdit#console_log, QTextEdit#console_log {
    background-color: #0d0d0d;
    border: none;
    color: #d4d4d4;
    font-family: 'JetBrains Mono', 'Consolas', monospace;
    font-size: 12px;
    line-height: 1.3;
}

QScrollBar:vertical {
    border: none;
    background: #121212;
    width: 6px;
}

QScrollBar::handle:vertical {
    background: #333333;
    border-radius: 3px;
    min-height: 20px;
}

QScrollBar::handle:vertical:hover {
    background: #555555;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
"""




### 호환 참조 (main.py / dialogs.py 가 참조하는 이름 — 새 팔레트로 연결)
BAR_PANEL_QSS = f"background-color: {BG_SURFACE}; border: 1px solid {BORDER}; border-radius: 0px;"
LBL_STREAM_QSS = f"color: {FG_DIM}; font-size: 11px; border: none; background: transparent; font-family: 'JetBrains Mono', 'Consolas', monospace;"
LBL_META_QSS = f"color: {ACCENT_ALT}; font-size: 11px; border: none; background: transparent; font-family: 'JetBrains Mono', 'Consolas', monospace;"
CONSOLE_INIT_QSS = CONSOLE_LOG_QSS

BTN_PRIMARY_QSS = BTN_ACTION_QSS        # 다운로드 시작 (액센트 아웃라인)
BTN_INFO_QSS = BTN_NEUTRAL_QSS          # 건너뛰기 (중립)
BTN_SETTINGS_FONT_QSS = BTN_NEUTRAL_QSS # 설정 (중립)
BTN_EXIT_DANGER_QSS = BTN_DANGER_QSS    # 종료 확인 (에러 아웃라인)
BTN_GRID_QSS = BTN_NEUTRAL_QSS          # 쿠키 소스 그리드
BTN_CLOSE_QSS = BTN_NEUTRAL_QSS         # 다이얼로그 닫기