import json
import socket
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("qt-pilot")

import time

def send_ipc(command: dict, wait_seconds: float = 8.0) -> dict:
    start = time.time()
    last_err = None
    while time.time() - start < wait_seconds:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
                client.settimeout(4.0)
                client.connect(("127.0.0.1", 49152))
                client.sendall(json.dumps(command).encode("utf-8"))
                res = client.recv(65536)
                return json.loads(res.decode("utf-8"))
        except (ConnectionRefusedError, socket.timeout, OSError) as e:
            last_err = e
            time.sleep(0.3)
    raise ConnectionError(f"Cannot connect to PySide6 QtPilotHook on port 49152: {last_err}")

@mcp.tool()
def get_widget_tree() -> str:
    """현재 화면에 활성화된 위젯의 objectName, 클래스, 가시성 목록을 조회합니다."""
    res = send_ipc({"action": "dump_tree"})
    return json.dumps(res.get("widgets", []), indent=2)

@mcp.tool()
def capture_ui(target_object_name: str = "", output_path: str = "debug_screenshot.png") -> str:
    """전체 창 또는 특정 위젯을 캡처하여 로컬 이미지 파일로 저장합니다."""
    res = send_ipc({"action": "capture", "target": target_object_name, "path": output_path})
    return f"Screenshot saved to {res.get('path')}"

@mcp.tool()
def click_widget(target_object_name: str) -> str:
    """지정된 objectName을 가진 위젯(버튼, 탭 등)을 클릭합니다."""
    res = send_ipc({"action": "click", "target": target_object_name})
    return res.get("status", "error")

# qt_pilot_server.py 하단에 추가
@mcp.tool()
def type_text(target_object_name: str, text: str) -> str:
    """지정된 objectName을 가진 입력창(QLineEdit 등)에 텍스트를 입력합니다."""
    res = send_ipc({"action": "type", "target": target_object_name, "text": text})
    return res.get("status")


@mcp.tool()
def capture_sequence(count: int = 3, interval: float = 1.0, prefix: str = "startup") -> str:
    """기동 과정 중 여러 시점의 화면을 연속으로 캡처합니다."""
    paths = []
    for i in range(count):
        path = f"{prefix}_{i+1}.png"
        res = send_ipc({"action": "capture", "target": "", "path": path}, wait_seconds=8.0 if i == 0 else 2.0)
        paths.append(res.get("path", path))
        if i < count - 1:
            time.sleep(interval)
    return f"Sequence saved: {', '.join(paths)}"

if __name__ == "__main__":
    mcp.run()

