### pot_provider.py - 유튜브 PO Token(bgutil) 프로바이더 서버 감지·자동 구동
"""성인제한/봇 확인을 우회하는 yt-dlp의 PO Token Provider를 관리한다.
bgutil-ytdlp-pot-provider는 두 부분으로 이뤄진다:
*  (플러그인) pip으로 앱 인터프리터에 설치 → yt-dlp이 PO Token Provider Framework로 로드한다.
*  (HTTP 서버) 기본 127.0.0.1:4416에서 동작 — 서버가 떠 있으면 플러그인이 자동 감지해 쓰므로,  **앱은 extractor_arg를 건드리지 않고 서버만 있으면 된다** .

여기서는 앱 시작 시 서버가 이미 떠 있는지(포트 프로브) 확인하고, 없으면 설치된 플러그인의 서버를 백그라운드로 기동한다. 서버 엔진은 bgutil의 Node 의존성을 필요로 할 수 있어 실패해도 조용히 '설치 필요' 상태로 남기고, 구성요소 자동 업데이트(updater)가 플러그인 설치는 보장한다. """
import importlib.util
import socket
import subprocess
import sys
import threading
import time

import yt_dlp
from PyQt6.QtCore import QThread, pyqtSignal

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 4416

def plugin_installed():
    """bgutil 플러그인이 현재 인터프리터에 있는지."""
    try:
        import importlib.metadata as im
        im.version("bgutil-ytdlp-pot-provider")
        return True
    except Exception:
        pass
    try:
        return importlib.util.find_spec("bgutil_ytdlp_pot_provider") is not None
    except Exception:
        return False

def server_running(host=DEFAULT_HOST, port=DEFAULT_PORT, timeout=0.5):
    """기본 포트에서 bgutil HTTP 서버가 실제로 응답하는지 TCP 프로브."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False

def _spawn_server():
    """설치된 플러그인의 서버 모듈을 백그라운드로 띄운다.
    우선순위: (1) 데이터 'bgutil_ytdlp_pot_provider.server' 메인,
    (2) 패키지 메인(진입점이 있는 경우). 서버 포트가 열리는 데 몇 초 걸리므로
    기동 후 비블로킹 폴링으로 확인한다. 실패/부재 시 None.
    """
    for mod in ("bgutil_ytdlp_pot_provider.server", "bgutil_ytdlp_pot_provider"):
        if importlib.util.find_spec(mod) is None:
            continue
        try:
            proc = subprocess.Popen(
                [sys.executable, "-m", mod],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception:
            continue
        # 서버가 포트를 열 때까지 최대 15초 대기 (백그라운드 스레드에서 호출 가정)
        for _ in range(30):
            if server_running():
                return proc
            if proc.poll() is not None:
                break
            time.sleep(0.5)
        try:
            proc.kill()
        except Exception:
            pass
    return None

class POTProviderWorker(QThread):
    """앱 시작 시 PO Token 서버가 준비되도록 보장하는 스레드.

    line(str) : 실행 중단 없이 간결 로그로 포워딩할 상태 한 줄.
    """

    line = pyqtSignal(str)

    def run(self):
        if server_running():
            self.line.emit(
                "[~] PO Token 프로바이더 서버 감지됨 (127.0.0.1:4416)"
            )
            return
        if not plugin_installed():
            self.line.emit(
                "[~] PO Token 프로바이더 미설치 — 업데이트 시 자동 설치됩니다"
            )
            return
        self.line.emit(
            "[~] PO Token 프로바이더 서버 기동 중..."
        )
        proc = _spawn_server()
        if proc is not None and server_running():
            self.line.emit("[v] PO Token 프로바이더 서버 기동 완료 (127.0.0.1:4416)")
        else:
            self.line.emit(
                "[!] PO Token 프로바이더 서버 기동 실패 — bgutil 서버를 직접 띄워 주세요"
            )
