### cookies.py - 브라우저 쿠키 추출 (yt-dlp 네이티브 위임)

"""
yt-dlp의 extract_cookies_from_browser를 위임하여 브라우저별 경로 탐색,
암호화 복호화(DPAPI/Keychain), SQLite 락 처리, 프로필 다중 선택을 모두 맡긴다.

지원 브라우저: chrome, chromium, edge, brave, vivaldi, firefox, opera, safari
"""

from __future__ import annotations

import platform

try:
    from yt_dlp.cookies import extract_cookies_from_browser
except ImportError:
    extract_cookies_from_browser = None  # yt-dlp 버전 미지원 시 None


# yt-dlp가 인식하는 브라우저 이름 매핑 (한글/별칭 → 표준 이름)
_BROWSER_ALIASES = {
    "chrome": "chrome",
    "크롬": "chrome",
    "google chrome": "chrome",
    "chromium": "chromium",
    "edge": "edge",
    "msedge": "edge",
    "microsoft edge": "edge",
    "brave": "brave",
    "vivaldi": "vivaldi",
    "opera": "opera",
    "opera gx": "opera",
    "firefox": "firefox",
    "ff": "firefox",
    "mozilla": "firefox",
    "safari": "safari",
}


def _normalize_browser_name(name: str) -> str | None:
    """사용자 입력/설정값을 yt-dlp 표준 브라우저명으로 정규화."""
    if not name:
        return None
    key = name.strip().lower()
    return _BROWSER_ALIASES.get(key)


def get_browser_cookies(browser: str | None = None) -> dict[str, dict[str, str]]:
    """
    yt-dlp 네이티브 쿠키 추출기로 브라우저 쿠키 획득.
    
    Args:
        browser: 브라우저 이름 (None이면 자동 탐색 시도)
        
    Returns:
        {domain: {name: value}} 형태의 쿠키 딕셔너리.
        실패/미지원 시 빈 딕셔너리 반환.
    """
    if extract_cookies_from_browser is None:
        return {}
    
    cookie_data: dict[str, dict[str, str]] = {}
    
    # 브라우저 지정 시 단일 시도
    if browser:
        norm = _normalize_browser_name(browser)
        if norm:
            try:
                cookies = extract_cookies_from_browser(norm)
                for c in cookies:
                    domain = c.get("domain", "")
                    if domain:
                        cookie_data.setdefault(domain, {})[c["name"]] = c["value"]
            except Exception:  # noqa: BLE001, S110 — 브라우저 쿠키 추출 실패는 다음 브라우저로/빈 데이터
                pass  # yt-dlp 내부에서 로깅/처리
        return cookie_data
    
    # 자동 탐색: 플랫폼별 우선순위대로 시도
    system = platform.system().lower()
    candidates = []
    if system == "windows":
        candidates = ["chrome", "edge", "brave", "vivaldi", "opera", "firefox"]
    elif system == "darwin":
        candidates = ["chrome", "edge", "brave", "vivaldi", "opera", "firefox", "safari"]
    else:  # linux
        candidates = ["chrome", "chromium", "edge", "brave", "vivaldi", "opera", "firefox"]
    
    for b in candidates:
        try:
            cookies = extract_cookies_from_browser(b)
            for c in cookies:
                domain = c.get("domain", "")
                if domain:
                    cookie_data.setdefault(domain, {})[c["name"]] = c["value"]
            if cookie_data:
                break  # 첫 성공 시 종료 (충돌 방지)
        except Exception:  # noqa: BLE001, S112 — 개별 브라우저 실패 시 다음 브라우저 후보 시도
            continue
    
    return cookie_data


def get_cookie_string_for_domain(domain: str, browser: str | None = None) -> str:
    """
    특정 도메인의 쿠키를 'name=value; name=value' 문자열로 반환.
    yt-dlp의 cookiefile 포맷 또는 requests headers 용도.
    """
    cookies = get_browser_cookies(browser)
    domain_cookies = cookies.get(domain, {})
    return "; ".join(f"{k}={v}" for k, v in domain_cookies.items())
