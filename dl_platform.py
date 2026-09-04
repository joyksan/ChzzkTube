##### dl_platform.py - 다운로더 플랫폼/콘텐츠 타입 감별
"""URL 문자열에서 플랫폼(youtube/chzzk/streamlink)과 콘텐츠 타입을 판정한다.

표준 라이브러리 `platform`과의 이름 충돌을 피하기 위해 `dl_platform`으로
명명 — downloader.target_downloader / AnalyzeWorker 공용.
"""
import re


def _dl_platform(url):
    """URL 문자열에서 플랫폼 문자열 추출 (youtube/chzzk/streamlink)."""
    if not url:
        return "youtube"
    u = str(url).lower()
    if "chzzk.naver.com" in u:
        return "chzzk"
    if (
        "youtube.com" in u
        or "youtu.be" in u
        or "music.youtube.com" in u
        or "youtube-nocookie.com" in u
    ):
        return "youtube"
    if (
        "twitch.tv" in u
        or "sooplive.co.kr" in u
        or "soop.co.kr" in u
        or "afreecatv.com" in u
    ):
        return "streamlink"
    return "youtube"


### ── Platform Abbreviations (for TUI column width ≤ 8) ──

_PLATFORM_ABBREV = {
    "youtube": "yt",
    "chzzk": "chzzk",
    "streamlink": "sl",
    "yt-dlp": "ytdlp",
    "ffmpeg": "ffmpeg",
    "DEPS": "deps",
    "POT": "pot",
    "ENGINE": "eng",
    "TXT": "txt",
    "CFG": "cfg",
}


def _short_platform(p):
    """플랫폼 문자열을 TUI 컬럼 폭(≤8)에 맞게 축약."""
    if not p or p == "-":
        return "-"
    return _PLATFORM_ABBREV.get(p, str(p)[:8])


def detect_content_type(url, info=None):
    """콘텐츠 종류 판정.

    chzzk      → clip / vod / live / chzzk
    youtube url → playlist / live / video
    streamlink  → stream
    info(dict)에 is_live 가 있으면 live 우선.
    """
    if not url:
        return "video"
    u = str(url).lower()

    if "chzzk.naver.com" in u:
        if re.search(r"clips?/", u):
            return "clip"
        if re.search(r"video/\d+", u):
            return "vod"
        if "/live/" in u:
            return "live"
        return "chzzk"

    if (
        info
        and isinstance(info, dict)
        and info.get("is_live")
        and not info.get("is_playlist")
    ):
        return "live"

    if "youtube.com/playlist" in u or "playlist?list=" in u:
        return "playlist"
    if (
        "youtu.be" in u
        or "youtube.com/watch" in u
        or "youtube.com/shorts" in u
        or "youtube.com/live" in u
    ):
        if info and isinstance(info, dict) and info.get("is_live"):
            return "live"
        return "video"

    if "twitch.tv" in u or "sooplive.co.kr" in u or "afreecatv.com" in u:
        return "stream"

    return "video"