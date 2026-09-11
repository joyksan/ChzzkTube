##### dl_platform.py - 다운로더 플랫폼/콘텐츠 타입 감별
"""URL 문자열에서 플랫폼(youtube/chzzk/streamlink 등)과 콘텐츠 타입을 판정한다.

표준 라이브러리 `platform`과의 이름 충돌을 피하기 위해 `dl_platform`으로
명명 — downloader.target_downloader / AnalyzeWorker 공용.

플랫폼 축약기호는 media.platform_short()를 사용한다.
"""
import re

# 도메인 → 플랫폼 추출기명 매핑 (동적 확장 가능)
# 우선순위: 위에서부터 매칭, 없으면 yt-dlp extractor에게 위임
_DOMAIN_EXTRACTORS = [
    # (도메인 패턴, extractor 이름)
    ("chzzk.naver.com", "chzzk"),
    ("twitch.tv", "twitch"),
    ("sooplive.co.kr", "sooplive"),
    ("soop.co.kr", "sooplive"),
    ("afreecatv.com", "afreecatv"),
    ("youtube.com", "youtube"),
    ("youtu.be", "youtube"),
    ("music.youtube.com", "youtube"),
    ("youtube-nocookie.com", "youtube"),
    ("instagram.com", "instagram"),
    ("tiktok.com", "tiktok"),
    ("facebook.com", "facebook"),
    ("twitter.com", "twitter"),
    ("x.com", "twitter"),
    ("bilibili.com", "bilibili"),
    ("dailymotion.com", "dailymotion"),
    ("vimeo.com", "vimeo"),
    ("soundcloud.com", "soundcloud"),
    ("naver.com", "naver"),
    ("kakao.com", "kakao"),
    ("fmkorea.com", "fmkorea"),
    ("theqoo.net", "theqoo"),
    ("clien.net", "clien"),
    ("dcinside.com", "dcinside"),
]


def _dl_platform(url):
    """URL 문자열에서 플랫폼 추출기명 추출.

    도메인 매핑 테이블에서 찾고, 없으면 'youtube'로 폴백
    (yt-dlp가 범용 처리하므로 대부분 동작).
    """
    if not url:
        return "youtube"
    u = str(url).lower()
    for pattern, extractor in _DOMAIN_EXTRACTORS:
        if pattern in u:
            return extractor
    return "youtube"  # 폴백: yt-dlp가 자동 감지


def _short_platform(p):
    """플랫폼 문자열을 TUI 컬럼 폭에 맞게 축약 (media.platform_short 위임)."""
    if not p or p == "-":
        return "-"
    try:
        from media import platform_short
        return platform_short(p)
    except ImportError:
        return str(p)[:8]


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