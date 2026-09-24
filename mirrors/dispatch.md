##### target_downloader/dispatch.py - 다운로드 디스패처 (메인 엔트리포인트)
"""개별 항목 다운로드 — 사전 분류 스킵 및 정적 디스패치 테이블 실행."""
from chzzktube.pipeline.classifier import ContentKind, ClassifiedTarget
from chzzktube.pipeline.target_downloader.chzzk import _download_chzzk, _download_chzzk_live
from chzzktube.pipeline.target_downloader.youtube_vod import _download_vod
from chzzktube.pipeline.target_downloader.youtube_live import _download_youtube_live, _download_streamlink
from chzzktube.pipeline.target_downloader.utils import _emit_error_log
import chzzktube.core.raw_log as raw_log
from chzzktube.core.log_emitter import emit_event
from chzzktube.core.dl_platform import _dl_platform


# ── 정적 디스패치 테이블 ───────────────────────────────────────────────────
# ContentKind -> 다운로드 함수 매핑 (확장 용이)
_DISPATCH_TABLE = {
    ContentKind.CLIP: _download_chzzk,           # CHZZK_CLIP
    ContentKind.VOD: _download_chzzk,            # CHZZK_VOD + YOUTUBE_VOD (구분은 handler 내부에서)
    ContentKind.LIVE_CHZZK: _download_chzzk_live,
    ContentKind.LIVE_YOUTUBE: _download_youtube_live,
}


def download_target(ctx, item, failed_targets, skip_targets=None) -> bool | str:
    """개별 항목 다운로드 — 사전 분류 스킵 및 정적 디스패치 테이블 실행.

    Args:
        ctx: DownloadContext (logger, cfg, speed_win, classifier, current_item 등 포함)
        item: ClassifiedTarget 또는 dict/str (내부에서 _classify_item으로 승격)
        failed_targets: list[(url, reason)] — 실패 항목 누적용
        skip_targets: list[(url, reason)] — 스킵 항목 누적용 (None이면 무시)

    Returns:
        True  - 다운로드 성공
        "skip" - 스킵 (연령 제한, 라이브 미지원 등)
        False - 다운로드 실패 (에러 로그는 이미 기록됨)
    """
    from chzzktube.pipeline.target_downloader.flatten import _classify_item
    from chzzktube.pipeline.target_downloader.utils import _emit_skip_log

    # 1. ClassifiedTarget으로 승격 (이미 승격된 경우 통과)
    item = _classify_item(ctx, item)
    ctx.current_item = item

    # 2. 다운로드 불가 사전 필터링
    if not item.downloadable:
        reason = item.skip_reason or "다운로드 불가"
        _emit_skip_log(ctx, item, reason)
        if skip_targets is not None:
            skip_targets.append((item.url, reason))
        return "skip"

    # 3. 디스패치 테이블에서 핸들러 조회
    handler = _DISPATCH_TABLE.get(item.kind)
    if not handler:
        _emit_error_log(ctx, item.url, f"지원하지 않는 콘텐츠 종류: {item.kind}", failed_targets)
        return False

    # 4. 핸들러 실행 (예외는 핸들러 내부에서 처리 후 False 반환)
    try:
        # VOD는 플랫폼 태그로 분기 (CHZZK vs YouTube)
        if item.kind == ContentKind.VOD:
            if item.platform_tag == "chzzk":
                return _download_chzzk(ctx, item.url, "vod")
            else:
                return _download_vod(ctx, item.url)
        elif item.kind == ContentKind.CLIP:
            return _download_chzzk(ctx, item.url, "clip")
        else:
            return handler(ctx, item.url)
    except Exception as ex:  # noqa: BLE001
        _emit_error_log(ctx, item.url, f"디스패치 예외: {ex}", failed_targets)
        return False