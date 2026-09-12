### po_client.py - PO Token 서버 HTTP 클라이언트 (L0 leaf)
"""bgutil PO Token 서버와의 순수 HTTP 통신 계층.

[계층 규약] 서버 프로세스 수급·빌드·스폰(lifecycle)은 pot_server(L1)와
그 수명주기 관리자(POTManager)가 담당하고, 본 모듈은 그 서버에 대한
**순수 HTTP 클라이언트**만 제공한다 — 상위 계층 역참조(lazy import) 없이
표준 라이브러리만으로 완결된다.
- client_opts(L0) / updater(L0) 가 pot_provider(L1)를 역참조하던 계층 역전 해소:
  이제 옵션 빌더·버전 체커는 본 leaf만 본다.
- 의존: 표준 라이브러리만 — Qt/워커 무의존, 어디서 import해도 안전.
"""
import json
import re
import socket
import urllib.error
import urllib.request

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 4416


def server_ping(host=DEFAULT_HOST, port=DEFAULT_PORT, timeout=1):
    """PO token server alive 확인 (L0 순수 HTTP 핑). 성공 시 True.

    [계약] L0 leaf는 표준 라이브러리만 본다 — 상위 계층(pot_server)의 락
    파일을 들여다보던 PID 역참조는 폐기했다. TCP 연결 성공 + HTTP 200은
    Node.js 이벤트 루프가 실제로 I/O를 처리 중이라는 증거이므로 프로토콜
    검증만으로 생존 판정이 충분하다. 좀비 락 회수는 pot_server가 서버
    기동 시 본인의 책임 영역에서 처리한다.
    """
    try:
        url = f"http://{host}:{port}/ping"
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def probe_server(host=DEFAULT_HOST, port=DEFAULT_PORT, timeout=1.5):
    """서버 상태 모니터링 (HTTP /ping 응답 기준)"""
    url = f"http://{host}:{port}/ping"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if 200 <= resp.status < 300:
                return "ok", ""
            return "conflict", f"HTTP {resp.status}"
    except urllib.error.HTTPError as e:
        return "conflict", f"HTTP {e.code}"
    except urllib.error.URLError as e:
        if isinstance(getattr(e, "reason", None), ConnectionRefusedError):
            return "down", ""
    except Exception:
        pass

    # [폴백] HTTPError/URLError 외 (예: OS 레벨 연결 거부 랩핑) 소켓 직접 확인
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return "conflict", "ping no response"
    except OSError:
        return "down", ""


def fetch_po_token(video_id, host=DEFAULT_HOST, port=DEFAULT_PORT, timeout=5):
    """bgutil 독립 서버에서 PO 토큰 직접 패칭 (플러그인 우회).

    POST /get_pot {"content_binding": video_id} → {"poToken": "..."}
    서버 미기동/오류 시 None 반환 — 호출부는 PO 없이 진행.
    """
    url = f"http://{host}:{port}/get_pot"
    try:
        body = json.dumps({"content_binding": video_id}).encode("utf-8")
        req = urllib.request.Request(
            url, data=body, method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        token = data.get("poToken") or ""
        if token:
            return token
    except Exception:
        pass
    return None


def extract_video_id(url):
    """YouTube URL에서 11자리 video ID 추출 (실패 시 None)."""
    m = re.search(
        r"(?:v=|/shorts/|/embed/|youtu\.be/)([a-zA-Z0-9_-]{11})", str(url or "")
    )
    return m.group(1) if m else None