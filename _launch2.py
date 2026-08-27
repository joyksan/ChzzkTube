import sys, traceback
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

print("START", flush=True)
try:
    import main
    print("IMPORT_OK", flush=True)
    app = QApplication.instance() or QApplication(sys.argv)
    print("QAPP_OK", flush=True)
    w = main.MainWindow()
    w.show()
    print("SHOW_OK", flush=True)
    # 3초 뒤 자동 종료 — app.exec() + showEvent(2초 업데이트/포토 프로바이더) 시뮬레이션
    QTimer.singleShot(3000, app.quit)
    rc = app.exec()
    print("APPEC_EXIT", rc, flush=True)
    print("SMOKE_DONE", flush=True)
except Exception:
    traceback.print_exc()
    print("SMOKE_CRASHED", flush=True)
