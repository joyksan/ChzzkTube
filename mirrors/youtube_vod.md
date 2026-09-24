##### target_downloader/youtube_vod.py - 유튜브 VOD 다운로드 (yt-dlp)
"""YouTube VOD 다운로드 — yt-dlp 기반, 품질 우선 폴백 + PO 토큰 주입."""
import os
import time

import yt_dlp

# yt_dlp.utils가 없을 수 있으므로 안전하게 참조
try:
    YtDownloadError = yt_dlp.utils.DownloadError
except AttributeError:
    # 네임스페이스 패키지 형태에서는 직접 import 시도
    try:
        from yt_dlp.utils import DownloadError as YtDownloadError
    except ImportError:
        class YtDownloadError(Exception):
            pass

from chzzktube.pipeline.target_downloader.utils import (
    _WATCHDOG_HEARTBEAT_INTERVAL,
    _FormatQualityLoss,
    _emit_error_log,
    _emit_skip_log,
    _extract_yt_id,
    _is_retryable_bot_error,
    _has_configured_cookies,
)
from chzzktube.pipeline.target_downloader.options import _make_ytdl_opts, _format_selector
import chzzktube.core.raw_log as raw_log
from chzzktube.core.log_emitter import emit_event
from chzzktube.core.dl_platform import _dl_platform
from chzzktube.core.log_emitter import emit_event
from chzzktube.core.dl_platform import _dl_platform


# 품질 우선 폴백 체인 (v3.8.0): web → web_safari → ios → tv
_QUALITY_CLIENT_CHAIN = ("web", "web_safari", "ios", "tv")

# PO 토큰 주입 대상 클라이언트 (web/web_safari만)
_POT_CLIENTS = ("web", "web_safari")


def _ensure_pot_server_ready(ctx, timeout=60.0) -> bool:
    """[Layer 3] POT 서버 준비 — 워커 스레드 안전 (v3.8.0).

    [근본 수리] v3.7.2는 `POTManager.instance()`를 호출했지만 그런 API는
    존재하지 않았다(잠재 AttributeError — POT 경로 전체가 즉사). 게다가
    POTManager는 뷰가 소유한 QObject라 워커 스레드에서 접근하는 것 자체가
    스레드 경계 위반이다. 여기서는 L0(po_client.server_ping)과 L1
    (pot_server의 순수 스폰/빌드 헬퍼)만 호출해 동일 목적을 달성한다 —
    모두 Qt 무의존 순수 인프라라 백그라운드 스레드에서 안전하다.

    절차: /ping 생존 확인 → 빌드 존재 시 스폰 → (없으면) 프리웜 락 하에
    스테이징 빌드 → 스폰 → 포트 준비까지 폴링.

    Returns:
        True  : 서버가 /ping에 응답 (PO 토큰 패칭 가능)
        False : 미준비/타임아웃 — 호출부는 PO 없이 진행 여부를 판단한다
    """
    import time
    import chzzktube.pipeline.progress_emitter as _pe

    from chzzktube.infra.po_client import server_ping

    def _alive():
        return bool(server_ping())

    if _alive():
        return True

    def _log(msg):
        raw_log.raw(
            "dl",
            _pe.emit_event("DL", "RUN", "POT", str(msg)[:80]),
            to_tui=True,
        )

    def _heartbeat():
        wd = getattr(ctx, "_download_watchdog", None)
        if wd is not None:
            try:
                wd.heartbeat()
            except Exception:
                pass

    try:
        from chzzktube.infra.pot_server import (
            _spawn_existing, acquire_prewarm_lock, built_server_js,
            ensure_node_server, release_prewarm_lock, server_home,
            _SERVER_FALLBACK_VER,
        )
    except Exception as ex:  # noqa: BLE001 — 인프라 import 실패 시 PO 없이 진행
        _log(f"pot infra unavailable ({type(ex).__name__})")
        return False

    _log("starting POT server...")

    if not built_server_js():
        # 빌드 부재 — 프리웜 락 하에 1회 스테이징 후 스폰 재시도.
        fd = acquire_prewarm_lock(timeout=0, log_func=_log)
        if fd is None:
            _log("pot build busy — skipped")
            return False
        try:
            ensure_node_server(log_func=_log)
        finally:
            release_prewarm_lock(fd)

    # 스폰 또는 기존 프로세스 재사용
    proc = _spawn_existing(log_func=_log)
    if proc is None:
        _log("pot spawn failed")
        return False

    # /ping 준비까지 폴링
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _alive():
            _log("pot server ready")
            return True
        _heartbeat()
        time.sleep(0.5)

    _log("pot server timeout")
    return False


def _emit_vod_success(ctx, info: dict) -> None:
    """VOD 다운로드 성공 로그 — 제목/포맷/파일 크기."""
    title = info.get("title", "unknown")
    fmt = _format_selector(ctx) if hasattr(ctx, "v_spec") else "best"
    raw_log.raw(
        emit_event("DL", "OK", "YT", f"{title} [{fmt}]", url=ctx.current_url),
        to_tui=True,
    )


def _max_requested_height(info: dict) -> int:
    """요청된 최대 해상도 높이 반환 (포맷 선택 검증용)."""
    v_spec = info.get("v_spec") or {}
    return v_spec.get("height") or 0


def _needs_pot_promotion(ctx, info: dict) -> bool:
    """1차 다운로드 성공했지만 고화질(1080p+) 분리 포맷 누락 시 POT 승격 필요 여부."""
    requested = _max_requested_height(info)
    if requested < 1080:
        return False

    # 실제 획득한 포맷 확인
    formats = info.get("formats") or []
    has_high = any(
        f.get("height", 0) >= 1080 and f.get("vcodec") != "none"
        for f in formats
    )
    return not has_high


def _try_download_with_client(ctx, url: str, client: str, inject_pot: bool) -> tuple[bool, dict | None]:
    """지정된 client로 다운로드 시도 — 성공 시 (True, info), 실패 시 (False, err)."""
    opts = _make_ytdl_opts(ctx, {}, url, forced_client=client, inject_pot=inject_pot)

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            return True, info
    except yt_dlp.utils.DownloadError as ex:
        return False, ex
    except Exception as ex:  # noqa: BLE001
        return False, ex


def _download_vod(ctx, url: str) -> bool | str:
    """YouTube VOD 다운로드 — 품질 우선 폴백 + PO 토큰 재시도.

    반환:
        True  - 성공
        "skip" - 스킵 (연령 제한 등)
        False - 실패 (상위에서 재시도/에러 처리)
    """
    # 1. 연령 제한 등 스킵 사전 확인
    item = ctx.current_item
    if item.capability.requires_auth and not _has_configured_cookies(ctx.cfg):
        _emit_skip_log(ctx, item, "age/member gated")
        return "skip"

    # 2. 품질 우선 폴백 체인 시도
    last_err = None
    for i, client in enumerate(_QUALITY_CLIENT_CHAIN):
        inject_pot = client in _POT_CLIENTS and _ensure_pot_server_ready(ctx)
        success, result = _try_download_with_client(ctx, url, client, inject_pot)

        if success:
            info = result
            # 고화질(1080p+) 누락 시 POT 승격 필요 체크
            if _needs_pot_promotion(ctx, info):
                raise _FormatQualityLoss("1080p+ 분리 포맷 누락 — POT 재시도 필요")
            _emit_vod_success(ctx, info)
            return True

        last_err = result
        err = result if isinstance(result, Exception) else Exception(str(result))

        # 봇 차단 감지 → 다음 클라이언트로 폴백
        if _is_retryable_bot_error(err):
            raw_log.raw(
                emit_event("DL", "WARN", "YT", f"{client} 봇 차단 — 다음 클라이언트 시도"),
                to_tui=False,
            )
            continue

        # 터미널 에러 → 즉시 전파 (상위에서 처리)
        raise err

    # 3. 모든 클라이언트 실패 → 마지막 에러 기록
    _emit_error_log(ctx, url, f"전체 클라이언트 체인 실패: {last_err}", ctx.failed_targets)
    return False