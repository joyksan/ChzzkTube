##### target_downloader/utils.py - 공통 유틸리티/상수/분류 헬퍼
"""target_downloader 패키지 공통 유틸리티.

- 에러 마커 상수 (봇 재시도 가능 vs 터미널 실패)
- 워치독 하트비트 간격
- 쿠키 설정 확인
- 치지직 파일명 생성
- YouTube ID 추출
"""
import re

from chzzktube.core import raw_log
from chzzktube.core.dl_platform import _dl_platform
from chzzktube.core.log_emitter import emit_event
from chzzktube.pipeline.classifier import ClassifiedTarget

# ── 봇 차단 재시도 가능 마커 vs 터미널 에러 판별 (SSOT) ───────────────────────
_RETRYABLE_BOT_MARKERS = frozenset({
    "confirm you're not a bot",
    "not a bot",
    "sign in to confirm",
    "the page needs to be reloaded",
    "n challenge solving failed",
    "challenge solving failed",
    "po token",
    "failed to extract any player response",
    "http error 403",
    "requested format is not available",
    "only images are available",
    "no video formats found",
})

_TERMINAL_FAIL_MARKERS = frozenset({
    "private video",
    "this video is private",
    "video unavailable",
    "this video is not available",
    "has been removed",
    "account has been terminated",
    "copyright",
    "members-only",
})

# [결함 5 수리] 워치독 하트비트 발행 간격 (초)
_WATCHDOG_HEARTBEAT_INTERVAL = 5.0


class _FormatQualityLoss(Exception):
    """1차 다운로드가 성공했지만 1080p+ 분리 포맷 수급에 실패한 내부 신호.

    봇 차단과 동일하게 Layer 3(POT 서버) 승격 트리거로 취급하되,
    720p tv 클라이언트로의 타협은 없다 (v3.8.0).
    """


def _is_retryable_bot_error(err: Exception) -> bool:
    """봇 차단/JS 챌린지 계열인지 판별 — 터미널 에러는 즉시 상위로 탈출."""
    msg = str(err).lower()
    if any(term in msg for term in _TERMINAL_FAIL_MARKERS):
        return False
    return any(bot in msg for bot in _RETRYABLE_BOT_MARKERS)


def _has_configured_cookies(cfg: dict) -> bool:
    """현재 설정에서 쿠키가 구성되어 있는지 확인."""
    return bool(cfg.get("cookies") or cfg.get("cookies_file"))


def _chzzk_filename(ch_info, fmt, cfg):
    """치지직 다운로드 파일명 — get_filename_template(cfg) 계약을 치지직 메타로 치환."""
    cfg = cfg or {}
    title = str(ch_info.get("title") or ch_info.get("videoTitle") or "chzzk")
    title = re.sub(r'[\\/:*?"<>|]+', "_", title).strip(" _") or "chzzk"
    cid = str(
        ch_info.get("clip_id")
        or ch_info.get("video_no")
        or ch_info.get("live_id")
        or ""
    ).strip()
    chan = str(ch_info.get("channel_name") or "").strip()
    date = str(ch_info.get("date") or "").strip()[:10]
    height = fmt.get("height") if isinstance(fmt, dict) else None

    prefix_map = {
        "none": "",
        "uploader": f"[{chan}] " if chan else "",
        "date_dash_uploader": f"{date} [{chan}] " if (date and chan) else "",
        "date_compact_uploader": (
            f"{date.replace('-', '')} [{chan}] " if (date and chan) else ""
        ),
        "date_dash": f"{date} " if date else "",
        "date_compact": f"{date.replace('-', '')} " if date else "",
    }
    prefix = prefix_map.get(str(cfg.get("filename_prefix", "none") or "none"), "")

    suffix = ""
    if cid:
        suffix = f" [{cid}]"
        if str(cfg.get("filename_suffix", "id") or "id") == "id_res" and height:
            suffix += f" [{height}p]"
    return f"{prefix}{title}{suffix}.mp4"


def _extract_yt_id(url: str) -> str | None:
    """YouTube URL에서 video_id 추출."""
    patterns = [
        r"(?:v=|/)([0-9A-Za-z_-]{11})(?:[&?#]|$)",
        r"youtu\.be/([0-9A-Za-z_-]{11})",
        r"youtube\.com/shorts/([0-9A-Za-z_-]{11})",
    ]
    for pat in patterns:
        m = re.search(pat, url)
        if m:
            return m.group(1)
    return None


def _emit_error_log(ctx, url: str, reason: str, failed_targets: list) -> None:
    """에러 로그 기록만 수행 (즉시 TUI 발행 금지 — finalizer에서 단일 출력).

    raw 버스에도 즉시 발행하지 않고, failed_targets에만 누적한다.
    finalize 단계에서 한 번에 출력한다.
    """
    failed_targets.append((url, reason))


def _is_youtube_live_url(ctx, url: str) -> bool:
    """현재 항목이 YouTube 라이브 URL인지 확인."""
    try:
        return ctx.classifier.is_youtube_live(url)
    except AttributeError:
        # classifier 미주입 시 폴백
        return "youtube.com/live" in url or "youtu.be/" in url and "live" in url


def _emit_skip_log(ctx, item: ClassifiedTarget, reason: str) -> None:
    """스킵 로그 기록 (to_tui=True — 사용자 알림 필요)."""
    raw_log.raw(
        emit_event("DL", "SKIP", _dl_platform(item.url), reason, url=item.url),
        to_tui=True,
    )