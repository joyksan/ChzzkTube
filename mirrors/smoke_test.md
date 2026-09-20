import os
import re
import sys
import traceback

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

from chzzktube.core.config import BASE_DIR
from chzzktube.ui.dialogs import (
    ActionCountdownDialog,
    CookieSelectDialog,
    CookieViewerDialog,
    ExitConfirmDialog,
    SettingsDialog,
    VerboseLogWindow,
)
from chzzktube.ui.main_window import MainWindow

# [Debug Dialogs] --debug-dialogs 감지 시 offscreen 미설정 → 네이티브 macOS 창으로 렌더링
if "--debug-dialogs" not in sys.argv:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"

# [Windows 리다이렉트 대비] stdout/stderr가 파이프·파일로 리다이렉트되면
# 로케일 인코딩(cp949)으로 떨어져 em-dash(\u2014) 등에서 UnicodeEncodeError가
# 발생한다 — 테스트 자체 결함이 아니라 하네스 결함이므로 UTF-8을 강제한다.
for _stream in (sys.stdout, sys.stderr):
    _reconfig = getattr(_stream, "reconfigure", None)
    if callable(_reconfig):
        try:
            _reconfig(encoding="utf-8", errors="replace")
        except (OSError, re.error):
            pass


def _setup_app():
    """공통 QApplication 세팅 (Windows 자글거림 박멸: 안티앨리어싱 및 힌팅 통제)."""
    from PySide6.QtCore import Qt

    # 1. High-DPI 스케일링 정책 동기화 (QApplication 생성 전 필수 지정)
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication.instance() or QApplication(sys.argv)

    # 2. Cascadia Mono 가변 폰트 에셋 로드
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
    return app


def test_main():
    print("[Smoke Test] PySide6 App 및 MainWindow 초기화 테스트 시작")
    app = _setup_app()
    assert app is not None

    try:
        win = MainWindow()
        print("[Smoke Test] MainWindow 생성 성공!")
        assert win is not None
        assert win.ctrl is not None
        # [v3.8.1] 폴백 제거 — _force_unlock_input 속성 없음
        print("[Smoke Test] ctrl.state 확인:", win.ctrl.state)

        dlg = SettingsDialog(win, is_running=False)
        assert dlg.cb_container.currentData() in ("mp4", "mkv", "webm")
        assert dlg.cb_container.count() == 3
        dlg.update_filename_preview()
        print("[Smoke Test] SettingsDialog 생성 OK — combos", dlg.cb_container.count())
        print("[Smoke Test] PASS")
        return 0
    except (OSError, re.error) as e:
        
        print("[Smoke Test] FAIL:", e)
        traceback.print_exc()
        return 1


def debug_show_all_dialogs():
    """메인 윈도우를 비 파이썬 창 전면에 띄우고, 7종 다이얼로그를 그 위에 완벽히 정렬"""
    print("[Debug Dialogs] 전면 프리뷰 모드 가동 (다이얼로그 7종)")
    app = _setup_app()

    # 1. 배경 캔버스 (메인 윈도우 먼저 전면에 전개)
    win = MainWindow()
    win.setWindowTitle("ChzzkTube [배경 캔버스]")
    win.resize(1000, 600)
    win.move(30, 420)
    win.show()
    win.raise_()
    win.activateWindow()

    # 다이얼로그 GC 방어 컨테이너 (여기에 메인 윈도우를 섞지 마세요!)
    dialogs = []

    # ── [1열: 좌측 소형 스택 (x=30)] ──
    d1 = ExitConfirmDialog(win, is_running=True)
    d1.move(30, 30)
    dialogs.append(d1)

    d2 = ExitConfirmDialog(win, is_running=False)
    d2.move(30, 175)
    dialogs.append(d2)

    d3 = ActionCountdownDialog("exit_app", win)
    d3.timer.stop()
    d3.lbl_msg.setText("Download complete.\n<b>60s</b> until [<b>exit</b>] runs. (Preview)")
    d3.move(30, 320)
    dialogs.append(d3)

    # ── [2열: 쿠키 관리 스택 (x=430)] ──
    d4 = CookieSelectDialog(win)
    d4.move(430, 30)
    dialogs.append(d4)

    # ── [3열: 660px 메인 설정창 (x=750)] ──
    d5 = SettingsDialog(win, is_running=False)
    d5.move(750, 30)
    dialogs.append(d5)

    # ── [4열: 대형 뷰어 스택 (x=1430)] ──
    sample_cookie = (
        "# Netscape HTTP Cookie File\n"
        ".naver.com\tTRUE\t/\tTRUE\t1799999999\tNID_AUT\tSAMPLE_TOKEN_VALUE\n"
        ".naver.com\tTRUE\t/\tTRUE\t1799999999\tNID_SES\tSAMPLE_SESSION_VALUE\n"
        ".youtube.com\tTRUE\t/\tTRUE\t1799999999\tVISITOR_INFO1_LIVE\tSAMPLE_VISITOR"
    )
    d6 = CookieViewerDialog("쿠키 뷰어 (테스트 프리뷰)", sample_cookie, win)
    d6.move(1430, 30)
    dialogs.append(d6)

    d7 = VerboseLogWindow(win)
    d7.set_content(
        "[12:00:00] SYS  │ OK    │ MAIN  │ System initialized\n"
        "[12:00:01] DEPS │ OK    │ YTDL  │ yt-dlp up to date\n"
        "[12:00:02] POT  │ READY │ POT   │ Server bound (127.0.0.1:4416)\n"
        "[12:00:03] ANAL │ OK    │ YT    │ [1080p60] Test Stream Isolated"
    )
    d7.move(1430, 550)
    dialogs.append(d7)

    # ── [무결점 계층 정렬 시퀀스] ──
    # 메인 윈도우 위로 다이얼로그들을 순차적으로 끌어올림
    for dlg in dialogs:
        dlg.show()
        dlg.raise_()

    # macOS 창 관리자의 비동기 렌더링 대비 1회 재정돈 (lower 호출 절대 금지)
    def _enforce_stack():
        for dlg in dialogs:
            dlg.raise_()
        # 설정창에 포커스를 주어 키보드 ESC 테스트 편의성 확보
        d5.activateWindow()

    QTimer.singleShot(100, _enforce_stack)

    print(f"[Debug Dialogs] 총 {len(dialogs)}개 핵심 팝업이 메인 윈도우 전면에 고정되었습니다.")
    return app.exec()

if __name__ == "__main__":
    if "--debug-dialogs" in sys.argv:
        sys.exit(debug_show_all_dialogs())
    sys.exit(test_main())
