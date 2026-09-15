import os
import sys

# Offscreen QPA 플랫폼 활성화 (headless 환경에서 GUI 실행 가능하게 함)
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
    """모든 다이얼로그 한 번에 띄워서 크기/폰트/버튼/정렬 육안 검증"""
    print("[Debug Dialogs] 전체 다이얼로그 프리뷰 모드")
    app = _setup_app()

    from chzzktube.ui.main_window import MainWindow
    from chzzktube.ui.dialogs import (
        ExitConfirmDialog, CookieSelectDialog, ActionCountdownDialog,
        CookieViewerDialog, SettingsDialog, VerboseLogWindow, show_info_message
    )

    win = MainWindow()
    win.show()  # 부모 필요

    # 1. ExitConfirmDialog (다운로드 중 / 아닌 경우 둘 다)
    print("\n[1/7] ExitConfirmDialog — 다운로드 중")
    dlg1 = ExitConfirmDialog(win, is_running=True)
    dlg1.show()
    print(f"    Size: {dlg1.size().width()}x{dlg1.size().height()} (fixed: {dlg1.maximumSize() == dlg1.minimumSize()})")

    print("\n[2/7] ExitConfirmDialog — 일반")
    dlg2 = ExitConfirmDialog(win, is_running=False)
    dlg2.show()

    # 2. SettingsDialog
    print("\n[3/7] SettingsDialog")
    dlg3 = SettingsDialog(win, is_running=False)
    dlg3.show()
    print(f"    Size: {dlg3.size().width()}x{dlg3.size().height()} (fixed: {dlg3.maximumSize() == dlg3.minimumSize()})")

    # 3. VerboseLogWindow (F12)
    print("\n[4/7] VerboseLogWindow")
    dlg4 = VerboseLogWindow(win)
    dlg4.show()
    print(f"    Size: {dlg4.size().width()}x{dlg4.size().height()} (resizable)")

    # 4. CookieSelectDialog
    print("\n[5/7] CookieSelectDialog")
    dlg5 = CookieSelectDialog(win)
    dlg5.show()
    print(f"    Size: {dlg5.size().width()}x{dlg5.size().height()} (fixed: {dlg5.maximumSize() == dlg5.minimumSize()})")

    # 5. CookieViewerDialog
    print("\n[6/7] CookieViewerDialog")
    dlg6 = CookieViewerDialog("쿠키 뷰어 (테스트)", "Sample cookie content\nLine 2\nLine 3", win)
    dlg6.show()
    print(f"    Size: {dlg6.size().width()}x{dlg6.size().height()} (resizable)")

    # 6. ActionCountdownDialog (현재 미연결 — 프리뷰만)
    print("\n[7/7] ActionCountdownDialog (미사용/미완성)")
    dlg7 = ActionCountdownDialog("exit_app", win)
    dlg7.show()
    print(f"    Size: {dlg7.size().width()}x{dlg7.size().height()} (fixed: {dlg7.maximumSize() == dlg7.minimumSize()})")

    # 7. show_info_message (모달이라 마지막에)
    print("\n[+] show_info_message — 성공")
    show_info_message(win, "성공", "작업이 완료되었습니다.", detail="상세 내용 예시")

    print("\n[+] show_info_message — 에러")
    show_info_message(win, "오류", "무언가 잘못되었습니다.", detail="에러 상세", is_error=True)

    print("\n[Debug Dialogs] 모든 다이얼로그 표시 완료. 창을 닫으면 종료됩니다.")
    return app.exec()


if __name__ == "__main__":
    if "--debug-dialogs" in sys.argv:
        sys.exit(debug_show_all_dialogs())
    sys.exit(test_main())
