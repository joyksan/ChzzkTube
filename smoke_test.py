import os
import sys

# [Debug Dialogs] --debug-dialogs 감지 시 offscreen 미설정 → 네이티브 macOS 창으로 렌더링
if "--debug-dialogs" not in sys.argv:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"

# [Windows 리다이렉트 대비] stdout/stderr가 파이프·파일로 리다이렉트되면
# 로케일 인코딩(cp949)으로 떨어져 em-dash(\u2014) 등에서 UnicodeEncodeError가
# 발생한다 — 테스트 자체 결함이 아니라 하네스 결함이므로 UTF-8을 강제한다.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _setup_app():
    """공통 QApplication 세팅 (폰트, 스타일)"""
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QFont, QFontDatabase
    from chzzktube.core.config import BASE_DIR
    app = QApplication(sys.argv)
    font_path = os.path.join(BASE_DIR, "assets", "CascadiaMono-VariableFont_wght.ttf")
    if os.path.exists(font_path):
        QFontDatabase.addApplicationFont(font_path)
    app.setFont(QFont("Cascadia Mono", 11))
    return app


def test_main():
    print("[Smoke Test] PySide6 App 및 MainWindow 초기화 테스트 시작")
    from chzzktube.ui.dialogs import SettingsDialog
    from chzzktube.ui.main_window import MainWindow

    app = _setup_app()

    try:
        win = MainWindow()
        print("[Smoke Test] MainWindow 생성 성공!")
        assert win is not None
        assert win.ctrl is not None
        assert hasattr(win, "_force_unlock_input")
        print("[Smoke Test] ctrl.state 확인:", win.ctrl.state)
        dlg = SettingsDialog(win, is_running=False)
        assert dlg.cb_container.currentData() in ("mp4", "mkv", "webm")
        assert dlg.cb_container.count() == 3
        dlg.update_filename_preview()
        print("[Smoke Test] SettingsDialog 생성 OK — combos", dlg.cb_container.count())
        print("[Smoke Test] PASS")
        return 0
    except Exception as e:
        print("[Smoke Test] FAIL:", e)
        import traceback
        traceback.print_exc()
        return 1


def debug_show_all_dialogs():
    """모든 팝업 다이얼로그(9종)를 메인 윈도우 전면에 타일링 배치"""
    print("[Debug Dialogs] 전체 다이얼로그 프리뷰 모드 가동")
    app = _setup_app()

    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtWidgets import QMessageBox, QLabel
    import chzzktube.ui.theme as theme
    from chzzktube.ui.main_window import MainWindow
    from chzzktube.ui.dialogs import (
        ExitConfirmDialog,
        CookieSelectDialog,
        ActionCountdownDialog,
        CookieViewerDialog,
        SettingsDialog,
        VerboseLogWindow,
    )

    # 1. 배경 캔버스 역할을 할 메인 윈도우
    win = MainWindow()
    win.setWindowTitle("ChzzkTube [배경 캔버스]")
    # 화면 뒤편으로 시원하게 깔리도록 크기 및 위치 조정
    win.resize(960, 580)
    win.move(40, 420)
    win.show()

    # GC(가비지 컬렉터)에 의한 창 증발 방지 컨테이너
    dialogs = []

    # ── [1열: 좌측 컬럼 (x=40)] ────────────────────────────────
    # [1] ExitConfirmDialog (다운로드 중 경고)
    d1 = ExitConfirmDialog(win, is_running=True)
    d1.move(40, 40)
    dialogs.append(d1)

    # [2] ExitConfirmDialog (일반 대기 중 종료)
    d2 = ExitConfirmDialog(win, is_running=False)
    d2.move(40, 190)
    dialogs.append(d2)

    # [3] ActionCountdownDialog (메인창 뒤에 숨었던 녀석을 전면으로 구출)
    d3 = ActionCountdownDialog("exit_app", win)
    d3.timer.stop()  # 프리뷰 중 카운트다운 종료 차단
    d3.lbl_msg.setText("Download complete.\n<b>60s</b> until [<b>exit</b>] runs. (Preview)")
    d3.move(40, 340)
    dialogs.append(d3)

    # ── [2열: 중앙 컬럼 (x=420)] ────────────────────────────────
    # [4] CookieSelectDialog (쿠키 불러오기)
    d4 = CookieSelectDialog(win)
    d4.move(420, 40)
    dialogs.append(d4)

    # [5 & 6] show_info_message 프리뷰 박스 생성기 (선생님이 오해한 그 팝업!)
    def _create_msgbox(title, text, detail=None, is_error=False):
        box = QMessageBox(win)
        box.setIcon(QMessageBox.Icon.NoIcon)
        box.setWindowTitle(title)
        prefix = "▲ " if is_error else "✓ "
        box.setText(prefix + text)
        if detail:
            box.setDetailedText(detail)
        box.setStyleSheet(theme.MSGBOX_QSS)
        box.addButton("OK" if not is_error else "Close", QMessageBox.ButtonRole.AcceptRole)
        lbl = box.findChild(QLabel)
        if lbl:
            lbl.setAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                if is_error
                else Qt.AlignmentFlag.AlignCenter
            )
        return box

    # [5] show_info_message - 성공 알림
    d5_msg_ok = _create_msgbox(
        "[1-A] show_info_message (성공)",
        "작업이 완료되었습니다.",
        "다운로드 및 무결성 검증 통과 (테스트 데이터)",
    )
    d5_msg_ok.move(420, 450)
    dialogs.append(d5_msg_ok)

    # [6] show_info_message - 에러 알림
    d6_msg_err = _create_msgbox(
        "[1-B] show_info_message (에러)",
        "무언가 잘못되었습니다.",
        "HTTP Error 403: Forbidden (테스트 에러 예시)",
        is_error=True,
    )
    d6_msg_err.move(420, 590)
    dialogs.append(d6_msg_err)

    # ── [3열: 우측 컬럼 (x=740 ~)] ──────────────────────────────
    # [7] SettingsDialog (설정창)
    d7 = SettingsDialog(win, is_running=False)
    d7.move(740, 40)
    dialogs.append(d7)

    # [8] CookieViewerDialog (쿠키 뷰어)
    sample_cookie = (
        "# Netscape HTTP Cookie File\n"
        ".naver.com\tTRUE\t/\tTRUE\t1799999999\tNID_AUT\tSAMPLE_TOKEN_VALUE\n"
        ".naver.com\tTRUE\t/\tTRUE\t1799999999\tNID_SES\tSAMPLE_SESSION_VALUE\n"
        ".youtube.com\tTRUE\t/\tTRUE\t1799999999\tVISITOR_INFO1_LIVE\tSAMPLE_VISITOR"
    )
    d8 = CookieViewerDialog("쿠키 뷰어 (테스트 프리뷰)", sample_cookie, win)
    d8.move(1240, 40)
    dialogs.append(d8)

    # [9] VerboseLogWindow (F12 상세 로그)
    d9 = VerboseLogWindow(win)
    d9.set_content(
        "[12:00:00] SYS  │ OK    │ MAIN  │ System initialized\n"
        "[12:00:01] DEPS │ OK    │ YTDL  │ yt-dlp up to date\n"
        "[12:00:02] POT  │ READY │ POT   │ Server bound (127.0.0.1:4416)\n"
        "[12:00:03] ANAL │ OK    │ YT    │ [1080p60] Test Stream Isolated"
    )
    d9.move(1240, 560)
    dialogs.append(d9)

    # ── [Z-Order & 렌더링 강제 통제] ────────────────────────────
    # 1) 메인 윈도우를 Z-Stack 최하단(배경)으로 강제 격하
    win.lower()

    # 2) 모든 다이얼로그를 표시하고 최상위로 끌어올림
    for dlg in dialogs:
        dlg.show()
        dlg.raise_()

    # 3) macOS 윈도우 매니저 레이스 컨디션 대비: 루프 진입 직후 한 번 더 Z-Stack 교정
    def _enforce_z_order():
        win.lower()
        for dlg in dialogs:
            dlg.raise_()

    QTimer.singleShot(100, _enforce_z_order)

    print(f"[Debug Dialogs] 총 {len(dialogs)}개 팝업이 전면에 완전히 정렬되었습니다.")
    return app.exec()


if __name__ == "__main__":
    if "--debug-dialogs" in sys.argv:
        sys.exit(debug_show_all_dialogs())
    sys.exit(test_main())
