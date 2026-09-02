import os
import sys

# Offscreen QPA 플랫폼 활성화 (headless 환경에서 GUI 실행 가능하게 함)
os.environ["QT_QPA_PLATFORM"] = "offscreen"

def test_main():
    print("[Smoke Test] PyQt6 App 및 MainWindow 초기화 테스트 시작")
    from PyQt6.QtWidgets import QApplication
    from dialogs import SettingsDialog
    from main import MainWindow

    app = QApplication(sys.argv)

    # 윈도우 인스턴스 생성
    try:
        win = MainWindow()
        print("[Smoke Test] MainWindow 생성 성공!")
        assert win is not None
        assert win.ctrl is not None
        print("[Smoke Test] dl_state 프로퍼티 확인:", win.dl_state)
        # [다이얼로그 커버] SettingsDialog 실생성 — 콤보/체크박스 초기화가
        # NameError 없이 완료되는지 검증 (QGroupBox 미import·format__flay
        # 오타 잠복 결함을 잡기 위해 도입 — 스모크가 다이얼로그를 안 만들어
        # [TUI 패널 일체화] 결함이 오래 잠복했었다)
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

if __name__ == "__main__":
    sys.exit(test_main())
