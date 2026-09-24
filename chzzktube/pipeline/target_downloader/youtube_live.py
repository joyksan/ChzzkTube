##### target_downloader/youtube_live.py - 유튜브 라이브 다운로드
"""YouTube 라이브 녹화 — yt-dlp/ffmpeg 파이프 단일 경로.

[v3.10.0] Streamlink 경로 완전 제거 — 모든 라이브 녹화는
`live_recorder.download_youtube_live()`(yt-dlp 포맷 추출 → ffmpeg 릴레이)로 통합.
"""


def _get_lr():
    """live_recorder 모듈 동적 조회 (테스트 패치 지원)."""
    import chzzktube.pipeline.target_downloader as td
    return getattr(td, "_lr", None) or __import__("chzzktube.pipeline.live_recorder", fromlist=[""])


def _download_youtube_live(ctx, url: str) -> bool | str:
    """유튜브 라이브 — yt-dlp로 포맷 URL만 추출 후 live_recorder로 위임."""
    return _get_lr().download_youtube_live(ctx, url)