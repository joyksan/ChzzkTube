##### playlist.py - 유튜브 채널/재생목록 URL 정규화
"""채널 URL을 평탄화(expand_targets)에 적합한 형태로 정규화한다."""
import re


def normalize_youtube_channel_url(url):
    """채널 URL 정규화.

    - `/@handle`      → `/@handle/videos`  (채널 탭 평탄화 기준 탭으로 이동)
    - `/c/...` `/channel/...` → 상위 목록 접미 제거 후 `/videos` 부착
    - 일반 watch/playlist URL은 그대로 반환
    """
    if not url:
        return url
    u = url.strip()
    u_lower = u.lower()
    if "youtube.com" not in u_lower and "youtu.be" not in u_lower:
        return u

    # 채널 계열만 대상 — 일반 동영상/재생목록은 그대로
    if re.search(r"playlist\?list=", u_lower):
        return u
    if "/watch" in u_lower or "/shorts/" in u_lower or "youtu.be/" in u_lower:
        return u
    if "/live/" in u_lower:
        return u

    # 이미 /videos|streams|playlists|shorts|featured|about 탭이면 그대로
    if re.search(r"/(videos|streams|playlists|shorts|featured|about)/?$", u_lower):
        return u

    # /@handle 또는 /channel/UC... — 뒤의 탭 잔여물 제거 후 /videos
    m = re.match(r"(https?://(?:www\.)?youtube\.com/(?:@[^/?#]+|channel/[^/?#]+))", u)
    if m:
        return m.group(1).rstrip("/") + "/videos"

    # 기타 (music.youtube 등) — 그대로
    return u