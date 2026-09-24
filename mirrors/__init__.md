##### target_downloader/__init__.py - 패키지 공개 API 재내보내기
"""DownloadWorker의 다운로드 실행부 분할 모듈 패키지.

- expand_targets : 재생목록/채널 URL을 개별 동영상 URL로 평탄화
- download_target : 개별 URL을 타입별로 분기해 실제 다운로드
  chzzk(clip/vod) → 직접 HTTP 스트림, youtube VOD → yt-dlp,
  youtube live → _download_youtube_live(ffmpeg), stream → streamlink

하위 모듈:
- utils: 공통 상수/유틸리티/에러 분류
- options: yt-dlp 옵션 빌더
- flatten: 재생목록/채널 평탄화
- chzzk: 치지직 VOD/클립/라이브 다운로드
- youtube_vod: 유튜브 VOD 다운로드 (yt-dlp)
- youtube_live: 유튜브 라이브/스트림링크 다운로드
- dispatch: 메인 디스패처 (download_target)
"""

# 공통 유틸리티/상수
from .utils import (
    _RETRYABLE_BOT_MARKERS,
    _TERMINAL_FAIL_MARKERS,
    _WATCHDOG_HEARTBEAT_INTERVAL,
    _FormatQualityLoss,
    _is_retryable_bot_error,
    _has_configured_cookies,
    _chzzk_filename,
    _extract_yt_id,
    _emit_error_log,
    _emit_skip_log,
    _is_youtube_live_url,
)

# yt-dlp 옵션
from .options import _make_ytdl_opts, _format_selector

# 평탄화
from .flatten import _flatten, _classify_item, _normalize_single_item, expand_targets

# 치지직
from .chzzk import _download_chzzk, _download_chzzk_live, _http_download

# 라이브 레코더 (기존 td._lr 호환용)
import chzzktube.pipeline.live_recorder as _lr

# 유튜브 VOD
from .youtube_vod import (
    _download_vod,
    _ensure_pot_server_ready,
    _emit_vod_success,
    _max_requested_height,
    _needs_pot_promotion,
    _QUALITY_CLIENT_CHAIN,
    _POT_CLIENTS,
    YtDownloadError,
)
import yt_dlp
import chzzktube.core.raw_log as raw_log

# 유튜브 라이브/스트림
from .youtube_live import _download_youtube_live, _download_streamlink

# 메인 디스패처
from .dispatch import download_target

# ── 공개 API (기존 import 호환) ────────────────────────────────────────────
__all__ = [
    # 상수
    "_RETRYABLE_BOT_MARKERS",
    "_TERMINAL_FAIL_MARKERS",
    "_WATCHDOG_HEARTBEAT_INTERVAL",
    "_QUALITY_CLIENT_CHAIN",
    "_POT_CLIENTS",
    # 예외
    "_FormatQualityLoss",
    "YtDownloadError",
    # 모듈
    "yt_dlp",
    "_lr",
    "raw_log",
    # 유틸리티
    "_is_retryable_bot_error",
    "_has_configured_cookies",
    "_chzzk_filename",
    "_extract_yt_id",
    "_emit_error_log",
    "_emit_skip_log",
    "_is_youtube_live_url",
    # 옵션
    "_make_ytdl_opts",
    "_format_selector",
    # 평탄화
    "_flatten",
    "_classify_item",
    "_normalize_single_item",
    "expand_targets",
    # 치지직
    "_http_download",
    "_download_chzzk",
    "_download_chzzk_live",
    # 유튜브 VOD
    "_download_vod",
    "_ensure_pot_server_ready",
    "_emit_vod_success",
    "_max_requested_height",
    "_needs_pot_promotion",
    # 유튜브 라이브/스트림
    "_download_youtube_live",
    "_download_streamlink",
    # 디스패처
    "download_target",
]