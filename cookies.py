### cookies.py - 브라우저 쿠키 추출 (Firefox / Chromium 계열)
import glob
import os
import platform
import shutil
import sqlite3
import tempfile

import log_history

def get_browser_cookies():
    # 도메인별 쿠키를 담기 위해 {domain: {name: value}} 구조로 변경
    cookie_data = {}
    try:
        sys_name = platform.system()
        appdata = os.environ.get("APPDATA", "")
        localappdata = os.environ.get("LOCALAPPDATA", "")
        home = os.path.expanduser("~")
        paths = []
        if sys_name == "Windows":
            paths = [
                os.path.join(appdata, "Mozilla", "Firefox", "Profiles"),
                os.path.join(localappdata, "Google", "Chrome", "User Data", "Default"),
                os.path.join(localappdata, "Microsoft", "Edge", "User Data", "Default"),
            ]
        elif sys_name == "Darwin":
            paths = [
                os.path.join(home, "Library", "Application Support", "Firefox", "Profiles")
            ]

        for p in paths:
            if not os.path.exists(p):
                continue
            try:
                if "Firefox" in p:
                    for prof in glob.glob(os.path.join(p, "*")):
                        cf = os.path.join(prof, "cookies.sqlite")
                        if os.path.exists(cf):
                            td = tempfile.mkdtemp()
                            tdb = os.path.join(td, "cookies.sqlite")
                            shutil.copy2(cf, tdb)
                            conn = sqlite3.connect(tdb)
                            cur = conn.cursor()
                            # host와 name, value를 함께 조회
                            cur.execute("SELECT host, name, value FROM moz_cookies")
                            for host, n, v in cur.fetchall():
                                if host not in cookie_data:
                                    cookie_data[host] = {}
                                cookie_data[host][n] = v
                            conn.close()
                            shutil.rmtree(td, ignore_errors=True)
                else:
                    cf = os.path.join(p, "Network", "Cookies")
                    if not os.path.exists(cf):
                        cf = os.path.join(p, "Cookies")
                    if os.path.exists(cf):
                        td = tempfile.mkdtemp()
                        tdb = os.path.join(td, "Cookies")
                        shutil.copy2(cf, tdb)
                        conn = sqlite3.connect(tdb)
                        cur = conn.cursor()
                        # host_key와 name, value를 함께 조회
                        cur.execute("SELECT host_key, name, value FROM cookies")
                        for host, n, v in cur.fetchall():
                            if host not in cookie_data:
                                cookie_data[host] = {}
                            cookie_data[host][n] = v
                        conn.close()
                        shutil.rmtree(td, ignore_errors=True)
            except Exception as e:
                # [증거 남김] DB 잠금/권한 실패는 '쿠키가 있는데도 401' 증상의
                # 유일한 추적 단서 — 흡수는 유지하고 원인만 히스토리에 남긴다.
                import raw_log
                from log_event import LogEvent
                raw_log.raw(
                    "cookie",
                    LogEvent(
                        stage="CK", status="WARN", platform="cookie",
                        msg=f"cookie DB read failed ({os.path.basename(p)}): {type(e).__name__}: {e}",
                        is_error=False,
                    ),
                    to_tui=False,
                )
                continue
    except Exception:
        pass
    return cookie_data
