import json
import socket
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("qt-pilot")

def send_ipc(command: dict) -> dict:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
        client.connect(("127.0.0.1", 49152))
        client.sendall(json.dumps(command).encode("utf-8"))
        res = client.recv(65536)
        return json.loads(res.decode("utf-8"))

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

if __name__ == "__main__":
    mcp.run()

