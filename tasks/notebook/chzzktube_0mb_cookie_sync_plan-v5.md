# 📋 [v5.0 개정판] 0MB 전 사이트 범용 쿠키 동기화 & CDP 무혈입성 아키텍처 계획서

> **문서 버전**: v5.0 (2026-09-26)  
> **상태**: ChzzkTube v3.12.5 아키텍처 및 GUI/파이프라인 리팩토링 정합 완료  
> **핵심 목표**: `PySide6.QtWebEngine` 번들링 없이 용량 0MB 증가로 YouTube, 치지직(Chzzk) 등 **전 사이트 로그인 쿠키 단일 Netscape SSOT 동기화** 및 Chrome 127+ App-Bound Encryption 완벽 우회

---

## 1. 기획 배경 및 근본적 패러다임 전환

### 1.1 기존 구현의 치명적 모순 및 결함 종결
1. **Windows Chrome 127+ App-Bound Encryption (DPAPI-NG) 결함**:
   * 최신 크롬의 `Cookies` SQLite DB 내 `value` 컬럼은 평문이 비어 있으며, `encrypted_value`는 SYSTEM 서비스 권한이 없는 일반 파이썬 프로세스의 `sqlite3.connect` 접근으로는 절대로 복호화할 수 없음.
   * `sqlite3.connect` 방식은 깡통 토큰(빈 문자열)만 유출되는 치명적 모순을 품고 있었음.
2. **도메인별 하드코딩 및 분기 패러다임의 비효율성**:
   * 유튜브, 치지직 등 도메인별로 `youtube_cookies.txt`, `chzzk_cookies.txt`를 쪼개 관리하려던 기존 접근은 Netscape 규격의 본질을 오해한 삼류 개발 방식임.
   * **Netscape `cookies.txt` 규격은 단 하나의 파일 안에 수십 개의 도메인(`.youtube.com`, `.naver.com`, `.twitch.tv`, `.x.com` 등)을 한꺼번에 저장하도록 설계된 범용 표준**임.
   * `yt-dlp` 및 `chzzk_api.py`는 단 하나의 통합 `cookies.txt` 파일만 주어지면, 자신이 접근하는 사이트의 도메인에 맞는 쿠키만 알아서 헤더에 실어 보냄.

### 1.2 v5.0 핵심 해결책: CDP (`Network.getAllCookies`) 단일 무혈입성
* **Chrome DevTools Protocol (CDP)**을 활용하여 크롬 본체 프로세스 메모리에서 직접 `Network.getAllCookies` 명령을 단 1회 전송.
* 크롬 본체가 정식 복호화한 **모든 도메인의 쿠키 JSON 배열을 1초 만에 통째로 획득**.
* 도메인 하드코딩 0건, 암호화 장벽 0%, 배포 바이너리 용량 0MB 증가 달성 (`ChzzkTube.spec` 내 `--exclude-module PySide6.QtWebEngine` 유지).

---

## 2. v3.12.5 리팩토링 아키텍처 & 데이터 흐름 (Single Netscape SSOT)

```text
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        [0MB 격리 브라우저 런처 (subprocess)]                             │
│  chrome --user-data-dir="<writable_base>/browser_profile" --remote-debugging-port=0   │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │
                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        [CDP 소켓 통신 (stdlib socket/json)]                            │
│   DevToolsActivePort 읽기 ➔ WebSocket 연결 ➔ {"method": "Network.getAllCookies"}      │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │ (전 사이트 쿠키 JSON 수집)
                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                    [Netscape 7컬럼 포맷 세탁 & 원자적 저장]                            │
│  <writable_base>/cookies/cookies.txt 단일 SSOT 파일 생성 (#HttpOnly_ 태그 보존)       │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │
                      ┌─────────────────────┴─────────────────────┐
                      ▼                                           ▼
          [yt-dlp (YouTube / VOD)]                  [chzzk_api.py (치지직)]
     DownloadContext / options.py 연동           Netscape 파서로 NID_AUT/SES 추출
  .youtube.com 쿠키 자동 매칭 주입             .naver.com 쿠키(NID_AUT/SES) 헤더 주입
```

---

## 3. 모듈별 상세 구현 명세 (v3.12.5 계층 규약 준수)

### 3.1 `chzzktube/core/cookies.py` - 전 사이트 자동 감지 및 CDP 동기화 엔진

```python
# chzzktube/core/cookies.py - 전 사이트 자동 감지 및 0MB 완전 무결 쿠키 동기화 엔진 (v5.0)

import json
import os
import socket
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from chzzktube.core import config
import chzzktube.core.raw_log as raw_log
from chzzktube.infra.platform import is_windows, is_macos, spawn_kwargs, kill_tree


def get_browser_profile_dir() -> Path:
    """ChzzkTube 전용 격리 브라우저 프로필 디렉터리 (SSOT)."""
    profile_dir = Path(config.writable_base()) / "browser_profile"
    profile_dir.mkdir(parents=True, exist_ok=True)
    return profile_dir


def get_cookie_file_path() -> Path:
    """단일 통합 Netscape 쿠키 파일 경로 (SSOT)."""
    cookie_dir = Path(config.writable_base()) / "cookies"
    cookie_dir.mkdir(parents=True, exist_ok=True)
    return cookie_dir / "cookies.txt"


def launch_isolated_browser() -> Optional[subprocess.Popen]:
    """사용자 시스템의 Chrome/Edge를 ChzzkTube 전용 프로필 + CDP 포트로 기동합니다."""
    profile_dir = get_browser_profile_dir()
    
    # 디버깅 포트 파일 초기화
    port_file = profile_dir / "DevToolsActivePort"
    if port_file.exists():
        try:
            port_file.unlink()
        except OSError:
            pass

    chrome_path = _find_system_browser()
    if not chrome_path:
        return None

    args = [
        str(chrome_path),
        f"--user-data-dir={profile_dir}",
        "--remote-debugging-port=0",  # 동적 포트 할당
        "--no-first-run",
        "--no-default-browser-check",
        "https://www.youtube.com",
    ]
    
    return subprocess.Popen(args, **spawn_kwargs())


def _read_cdp_port(profile_dir: Path, timeout: float = 4.0) -> Optional[int]:
    """크롬이 생성한 DevToolsActivePort 파일에서 할당된 동적 포트를 추출합니다."""
    port_file = profile_dir / "DevToolsActivePort"
    start_time = time.monotonic()
    while time.monotonic() - start_time < timeout:
        if port_file.is_file():
            try:
                lines = port_file.read_text(encoding="utf-8").splitlines()
                if lines:
                    return int(lines[0].strip())
            except (ValueError, OSError):
                pass
        time.sleep(0.2)
    return None


def _fetch_cookies_via_cdp(ws_url: str) -> List[Dict[str, Any]]:
    """경량 단일 프레임 웹소켓 통신으로 Network.getAllCookies를 호출합니다 (stdlib 기반)."""
    parsed = urllib.parse.urlparse(ws_url)
    host, port = parsed.hostname, parsed.port
    path = parsed.path

    sock = socket.create_connection((host, port), timeout=3)
    handshake = (
        f"GET {path} HTTP/1.1
"
        f"Host: {host}:{port}
"
        "Upgrade: websocket
"
        "Connection: Upgrade
"
        "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==
"
        "Sec-WebSocket-Version: 13

"
    )
    sock.sendall(handshake.encode())
    resp = sock.recv(4096)
    if b"101 Switching Protocols" not in resp:
        sock.close()
        return []

    # Network.getAllCookies 명령 전송 (도메인 무제한 전수 수집)
    payload = json.dumps({"id": 1, "method": "Network.getAllCookies"}).encode("utf-8")
    length = len(payload)

    frame = bytearray([0x81])
    if length <= 125:
        frame.append(0x80 | length)
    elif length <= 65535:
        frame.append(0x80 | 126)
        frame.extend(length.to_bytes(2, "big"))
    mask = b"4Vx"
    frame.extend(mask)
    masked_payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    frame.extend(masked_payload)
    sock.sendall(frame)

    data = bytearray()
    sock.settimeout(3.0)
    while True:
        try:
            chunk = sock.recv(65536)
            if not chunk:
                break
            data.extend(chunk)
            if b'"result"' in data:
                break
        except socket.timeout:
            break
    sock.close()

    idx = data.find(b'{"id":1,')
    if idx != -1:
        res = json.loads(data[idx:].decode("utf-8", errors="replace"))
        return res.get("result", {}).get("cookies", [])
    return []


def sync_all_cookies_from_browser() -> Tuple[bool, str]:
    """브라우저의 모든 쿠키를 도메인 제한 없이 가로채어 단일 Netscape 파일로 저장합니다."""
    profile_dir = get_browser_profile_dir()
    out_file = get_cookie_file_path()

    port = _read_cdp_port(profile_dir)
    if not port:
        return False, "Could not find active browser session. Launch browser first."

    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/json/version")
        with urllib.request.urlopen(req, timeout=2) as resp:
            ver_info = json.loads(resp.read().decode("utf-8"))
            ws_url = ver_info.get("webSocketDebuggerUrl")

        if not ws_url:
            return False, "Browser DevTools websocket URL unavailable."

        raw_cookies = _fetch_cookies_via_cdp(ws_url)
        if not raw_cookies:
            return False, "No cookies retrieved from browser."

        # Netscape 7컬럼 포맷 변환 및 저장
        lines = [
            "# Netscape HTTP Cookie File",
            "# http://curl.haxx.se/rfc/cookie_spec.html",
            "# This is a generated file! Do not edit.",
            "",
        ]
        count = 0
        for c in raw_cookies:
            domain = c.get("domain", "")
            if not domain:
                continue
            httponly = "#HttpOnly_" if c.get("httpOnly") else ""
            subdomain = "TRUE" if domain.startswith(".") else "FALSE"
            path = c.get("path", "/")
            secure = "TRUE" if c.get("secure") else "FALSE"
            expires = str(int(c.get("expires", 0)))
            name = c.get("name", "")
            val = c.get("value", "")

            lines.append(f"{httponly}{domain}	{subdomain}	{path}	{secure}	{expires}	{name}	{val}")
            count += 1

        tmp_file = out_file.with_suffix(".tmp")
        tmp_file.write_text("
".join(lines), encoding="utf-8")
        tmp_file.replace(out_file)

        raw_log.raw("cookies", f"Synchronized {count} cookies across all domains into {out_file.name}")
        return True, f"{count} cookies synced (YouTube, Chzzk, etc.)"

    except Exception as e:
        return False, f"CDP sync error: {e}"


def parse_netscape_cookies(domain_keyword: str = "naver.com") -> Dict[str, str]:
    """통합 Netscape cookies.txt 파일에서 특정 도메인(예: naver.com) 키-값 쿠키 딕셔너리를 추출합니다."""
    out_file = get_cookie_file_path()
    if not out_file.is_file():
        return {}

    cookies = {}
    try:
        for line in out_file.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("# ") or line == "#":
                continue
            if line.startswith("#HttpOnly_"):
                line = line[len("#HttpOnly_"):]

            parts = line.split("	")
            if len(parts) >= 7:
                domain, _, _, _, _, name, val = parts[:7]
                if domain_keyword in domain:
                    cookies[name] = val
    except Exception as e:
        raw_log.raw("cookies", f"Failed to parse netscape cookies for {domain_keyword}: {e}")
    return cookies


def _find_system_browser() -> Optional[Path]:
    """OS별 크롬/에지 정규 실행 파일 경로 탐색."""
    if is_windows():
        candidates = [
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        ]
    elif is_macos():
        candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        ]
    else:
        candidates = ["/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/microsoft-edge"]

    for cand in candidates:
        p = Path(cand)
        if p.is_file():
            return p
    return None
```

---

### 3.2 `chzzktube/pipeline/` 파이프라인 수급 연동 명세

v3.12.5 전략 패턴 분리 구조에 맞추어 `DownloadContext`와 `options.py`, `chzzk.py`에서 단일 Netscape `cookies.txt`를 주입합니다.

#### ① `chzzktube/pipeline/target_downloader/options.py` (`yt-dlp` 옵션 구성)
```python
def build_yt_dlp_options(ctx: DownloadContext) -> dict:
    """DownloadContext 파라미터를 기반으로 yt-dlp 옵션 딕셔너리를 빌드합니다."""
    opts = {}
    cookie_path = ctx.cookie_file_path or str(config.get_cookie_file_path())
    if os.path.is_file(cookie_path):
        opts["cookiefile"] = cookie_path
    return opts
```

#### ② `chzzktube/pipeline/target_downloader/chzzk.py` 및 `chzzk_api.py` (치지직 연동)
```python
def fetch_chzzk_live_stream(ctx: DownloadContext) -> str:
    """치지직 라이브/VOD 수급 시 통합 Netscape 쿠키에서 NID_AUT / NID_SES를 자동 적용합니다."""
    from chzzktube.core.cookies import parse_netscape_cookies
    
    naver_cookies = parse_netscape_cookies("naver.com")
    nid_aut = naver_cookies.get("NID_AUT")
    nid_ses = naver_cookies.get("NID_SES")
    
    # Chzzk API 클라이언트에 쿠키 헤더 전달
    api_client = ChzzkAPI(aut=nid_aut, ses=nid_ses)
    return api_client.get_stream_url(ctx.target.url)
```

---

### 3.3 `chzzktube/ui/dialogs.py` - 모던 TUI UI 개편 (v3.12.5)

#### ① `CookieSelectDialog` 개편 (Fixed: 320x220)
작동하지 않는 레거시 브라우저 버튼을 완전히 걷어내고, **단 3개의 명확한 선택지**로 개편합니다.

```python
class CookieSelectDialog(QDialog):
    """0MB 격리 브라우저 동기화 & 파일 임포트 통합 다이얼로그 (Fixed: 320x220)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.selected_type = None
        self.selected_path = ""
        self.browser_proc = None
        self.setWindowTitle("Cookie Sync Manager")
        self.setFixedSize(320, 220)
        self.setStyleSheet(theme.DIALOG_BG_QSS)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        lbl = QLabel("// SELECT COOKIE METHOD")
        lbl.setStyleSheet("color: #4ec9b0; font-weight: bold; font-size: 11px;")
        layout.addWidget(lbl)

        # 1. 원클릭 격리 브라우저 연동 (모든 사이트 범용)
        btn_browser = QPushButton("[ Launch Isolated Browser ]")
        btn_browser.setStyleSheet(theme.BTN_GRID_QSS)
        btn_browser.setToolTip("Open dedicated browser to login YouTube, Chzzk, Twitch, etc.")
        btn_browser.clicked.connect(self._on_launch_browser)
        layout.addWidget(btn_browser)

        # 2. 기존 수동 cookies.txt 가져오기
        btn_file = QPushButton("[ Import cookies.txt File ]")
        btn_file.setStyleSheet(theme.BTN_GRID_QSS)
        btn_file.clicked.connect(self._on_import_file)
        layout.addWidget(btn_file)

        # 3. Firefox 사용자 전용 네이티브 연동
        btn_firefox = QPushButton("[ Firefox (Native Auto) ]")
        btn_firefox.setStyleSheet(theme.BTN_GRID_QSS)
        btn_firefox.clicked.connect(lambda: self._on_browser_select("firefox"))
        layout.addWidget(btn_firefox)

        layout.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setStyleSheet(theme.BTN_CLOSE_QSS)
        btn_cancel.clicked.connect(self.reject)
        layout.addWidget(btn_cancel)

    def _on_launch_browser(self):
        from chzzktube.core.cookies import launch_isolated_browser
        self.browser_proc = launch_isolated_browser()
        if self.browser_proc:
            self.selected_type = "isolated_browser"
            self.selected_path = ""
            self.accept()
        else:
            show_info_message(self, "Error", "No Chrome or Edge browser found on this system.", is_error=True)

    def _on_import_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Netscape Cookie File", "", "Text Files (*.txt);;All Files (*.*)"
        )
        if path:
            self.selected_type = "cookie_file"
            self.selected_path = path
            self.accept()

    def _on_browser_select(self, b_type):
        self.selected_type = b_type
        self.selected_path = ""
        self.accept()

    def reject(self):
        """다이얼로그 닫힘 시 기동된 브라우저 프로세스 안전 종료 (kill_tree)."""
        if self.browser_proc and self.browser_proc.poll() is None:
            try:
                kill_tree(self.browser_proc.pid)
            except Exception:
                pass
        super().reject()
```

#### ② `SettingsDialog` 5대 섹션 빌더 연동 및 `sync_cookie` 슬롯
`SettingsDialog` 내 쿠키 섹션에 **`[ Sync ]`** 버튼을 배치하여, 브라우저에서 로그인 후 원클릭으로 쿠키를 즉시 낚아채 오도록 배선합니다.

```python
# SettingsDialog 내부 sync_cookie 슬롯
def sync_cookie(self):
    """격리 브라우저 세션으로부터 모든 사이트의 쿠키를 즉시 낚아채어 동기화합니다."""
    from chzzktube.core.cookies import sync_all_cookies_from_browser, get_cookie_file_path
    
    ok, msg = sync_all_cookies_from_browser()
    if ok:
        cookie_path = str(get_cookie_file_path())
        self.cfg["browser_cookie"] = "cookie_file"
        self.cfg["cookie_file_path"] = cookie_path
        self.save_cfg()
        self._refresh_cookie_status()
        show_info_message(self, "Success", f"All session cookies synchronized!
({msg})")
    else:
        show_info_message(self, "Sync Failed", f"Could not sync cookies: {msg}
Ensure the isolated browser is running and logged in.", is_error=True)

# UI 조립부 4대 액션 버튼 배치
for text, func in [("View", self.view_cookie), ("Load", self.load_cookie), ("Sync", self.sync_cookie), ("Reset", self.reset_cookie)]:
    btn = QPushButton(f"[ {text} ]")
    btn.setStyleSheet(theme.TUI_STYLE)
    btn.setProperty("class", "tui-tag")
    btn.clicked.connect(func)
    self.cookie_buttons.append(btn)
    r_cookie.addWidget(btn)
```

---

## 4. 검증 시나리오 (Verification Checklist)

1. **0MB 용량 사수 검증**: `PySide6.QtWebEngine`이 제외된 상태로 `ChzzkTube.spec` 빌드 시 용량이 50~60MB 수준을 유지하는지 확인.
2. **Windows 127+ 크롬 우회 검증**: 최신 Chrome 127 이상 버전에서 `sync_all_cookies_from_browser()` 실행 시 `Network.getAllCookies`로 전 도메인 쿠키가 추출되는지 확인.
3. **v3.12.5 파이프라인 연동 검증**:
   * 유튜브 로그인 ➔ `Sync` ➔ `DownloadContext` 주입 ➔ `youtube_vod.py` 멤버십 VOD 수급 검증.
   * 치지직 로그인 ➔ `Sync` ➔ `parse_netscape_cookies("naver.com")` ➔ `chzzk.py` 구독자 전용 라이브/VOD 수급 검증.
4. **UI 반응성 및 프로세스 안전성 검증**: `CookieSelectDialog` 팝업 닫힘 시 `kill_tree` 프로세스 완전 회수 및 `SettingsDialog` 4개 버튼 스모크 테스트 수행.
