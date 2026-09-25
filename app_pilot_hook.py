import json
from PySide6.QtCore import QObject, Qt
from PySide6.QtNetwork import QTcpServer, QHostAddress
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

class QtPilotHook(QObject):
    def __init__(self, main_window: QWidget, port: int = 49152):
        super().__init__()
        self.window = main_window
        self.server = QTcpServer(self)
        self.server.newConnection.connect(self._handle_connection)
        self.server.listen(QHostAddress.LocalHost, port)

    def _handle_connection(self):
        socket = self.server.nextPendingConnection()
        socket.readyRead.connect(lambda: self._process_command(socket))

    def _process_command(self, socket):
        raw_data = socket.readAll().data().decode("utf-8")
        try:
            cmd = json.loads(raw_data)
        except json.JSONDecodeError:
            return
        
        action = cmd.get("action")
        response = {"status": "ok"}

        if action == "dump_tree":
            response["widgets"] = [
                {"name": w.objectName(), "class": w.metaObject().className(), "visible": w.isVisible()}
                for w in self.window.findChildren(QWidget) if w.objectName()
            ]

        elif action == "capture":
            target_name = cmd.get("target")
            target = self.window.findChild(QWidget, target_name) if target_name else self.window
            if target:
                pixmap = target.grab()
                save_path = cmd.get("path", "ui_debug.png")
                pixmap.save(save_path)
                response["path"] = save_path
            else:
                response = {"status": "error", "message": "Widget not found"}

        elif action == "click":
            target = self.window.findChild(QWidget, cmd.get("target"))
            if target:
                QTest.mouseClick(target, Qt.MouseButton.LeftButton)
            else:
                response = {"status": "error", "message": "Widget not found"}

        elif action == "type":
            target = self.window.findChild(QWidget, cmd.get("target"))
            text = cmd.get("text", "")
            if target:
                target.setFocus()
                QTest.keyClicks(target, text)
            else:
                response = {"status": "error", "message": "Widget not found"}

        socket.write(json.dumps(response).encode("utf-8"))
        socket.flush()
        socket.disconnectFromHost()

