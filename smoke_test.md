import os
import sys

# Offscreen QPA 플랫폼 활성화 (headless 환경에서 GUI 실행 가능하게 함)
os.environ["QT_QPA_PLATFORM"] = "offscreen"

def test_main():
    print("[Smoke Test] PyQt6 App 및 MainWindow 초기화 테스트 시작")
    from PyQt6.QtWidgets import QApplication
    from main import MainWindow
    
    app = QApplication(sys.argv)
    
    # 윈도우 인스턴스 생성
    try:
        win = MainWindow()
        print("[Smoke Test] MainWindow 생성 성공!")
        assert win is not None
        assert win.ctrl is not None
        print("[Smoke Test] dl_state 프로퍼티 확인:", win.dl_state)
        print("[Smoke Test] PASS")
        return 0
    except Exception as e:
        print("[Smoke Test] FAIL:", e)
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(test_main())
