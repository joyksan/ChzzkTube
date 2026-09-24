##### target_downloader/youtube_live.py - 유튜브 라이브/스트림링크 다운로드
"""YouTube 라이브(ffmpeg 파이프) / Streamlink 기반 스트림 다운로드."""
import os
import time
import subprocess
import threading
import queue
from contextlib import suppress

import yt_dlp

# _lr는 동적 조회로 테스트 패치 지원
def _get_lr():
    """live_recorder 모듈 동적 조회 (테스트 패치 지원)."""
    import chzzktube.pipeline.target_downloader as td
    return getattr(td, "_lr", None) or __import__("chzzktube.pipeline.live_recorder", fromlist=[""])


def _download_youtube_live(ctx, url: str) -> bool | str:
    """유튜브 라이브 — yt-dlp로 포맷 URL만 추출 후 live_recorder로 위임."""
    return _get_lr().download_youtube_live(ctx, url)


def _download_streamlink(ctx, url: str) -> bool:
    """Streamlink 지원 사이트(트위치 등) — streamlink로 포맷 URL 추출 후 ffmpeg 파이프."""
    _lr = _get_lr()
    out_file = os.path.join(ctx.cfg["download_path"], "streamlink_live.mp4")
    temp_ts, _, _ = _lr.prepare_live_paths(ctx, out_file, None)
    quality = str(ctx.cfg.get("streamlink_quality") or "best").strip() or "best"
    cmd = ["streamlink", url, quality, "-O"]
    return _lr.record_live_stream(ctx, cmd, temp_ts)