import sys
import traceback
from PyQt6.QtWidgets import QApplication

print("START", flush=True)
try:
    import main
    print("IMPORT_OK", flush=True)
    app = QApplication.instance() or QApplication(sys.argv)
    print("QAPP_OK", flush=True)
    w = main.MainWindow()
    print("WINDOW_OK", flush=True)
    w.show()
    print("SHOW_OK", flush=True)
    # app.exec()는 호출하지 않음 — 이벤트 루프 블로킹 방지 (크래시 재현용 아님)
except Exception:
    traceback.print_exc()
    print("SMOKE_CRASHED", flush=True)
