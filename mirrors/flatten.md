##### target_downloader/flatten.py - 재생목록/채널 평탄화
"""재생목록/채널 URL을 개별 동영상 ClassifiedTarget 리스트로 평탄화."""
import yt_dlp

from chzzktube.core.playlist import normalize_youtube_channel_url
from chzzktube.pipeline.classifier import ClassifiedTarget, ItemClassifier
from chzzktube.pipeline.target_downloader.utils import _has_configured_cookies


def _flatten(ctx, url: str) -> list[ClassifiedTarget]:
    """yt-dlp extract_flat 기반 재생목록/채널 평탄화.

    [원칙 준수]
    - 어설픈 하드코딩 dict 날조 금지: entries의 원시 메타를 ItemClassifier에 그대로 위임.
    - extract_flat 환경에서는 StreamCapability.indeterminate()가 자동 적용되어
      has_video/has_audio=None (미정) 상태가 거짓말 없이 정직하게 보존된다.
    """
    opts = {
        "logger": ctx.logger,
        "extract_flat": True,
        "skip_download": True,
        "noplaylist": False,
        "socket_timeout": 30,
    }
    _apply_cookie_opts(opts, ctx.cfg)
    _apply_client_opts(opts, ctx.cfg, forced=None)  # 순정 위임
    _apply_light_analysis_opts(opts)
    _apply_ejs_opts(opts)

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
        entries = (info or {}).get("entries") or []
        targets: list[ClassifiedTarget] = []

        for e in entries:
            if not e:
                continue
            # yt-dlp flat 추출 시 url 또는 webpage_url 필드 참조
            target_url = e.get("url") or e.get("webpage_url")
            if not target_url:
                continue

            # YouTube ID만 떨어진 경우 정규 URL로 복원
            if not target_url.startswith("http"):
                target_url = f"https://www.youtube.com/watch?v={target_url}"

            # 1단계 ItemClassifier에 위임하여 TriState(None) 메타데이터 보존 객체 생성
            classified = ItemClassifier.classify(target_url, raw_info=e)
            targets.append(classified)

        return targets


def _classify_item(ctx, raw_target: ClassifiedTarget | str | dict) -> ClassifiedTarget:
    """원시 대상을 ClassifiedTarget으로 승격 — 다운로드 가능성/인증 요구 검증 포함."""
    if isinstance(raw_target, ClassifiedTarget):
        item = raw_target
    elif isinstance(raw_target, str):
        item = ItemClassifier.classify(raw_target, raw_info=None)
    elif isinstance(raw_target, dict):
        # dict 형태로 들어온 경우 (레거시 호환)
        item = ItemClassifier.classify(raw_target.get("url", ""), raw_info=raw_target)
    else:
        raise TypeError(f"지원하지 않는 대상 타입: {type(raw_target)}")

    # 1. 다운로드 불가 (이미지 전용 등) 조기 반환
    if not item.downloadable:
        return item

    # 2. 인증 요구사항 교차 검증 (도메인 정책 vs 현재 런타임 cfg)
    if item.capability.requires_auth and not _has_configured_cookies(ctx.cfg):
        return ClassifiedTarget(
            url=item.url,
            title=item.title,
            kind=item.kind,
            capability=item.capability,
            platform_tag=item.platform_tag,
            downloadable=False,
            needs_pot=item.needs_pot,
            skip_reason="age/member gated",
            metadata=item.metadata,
        )

    return item


def _normalize_single_item(url: str) -> ClassifiedTarget:
    """단일 영상 URL을 ClassifiedTarget으로 정규화 (메타는 다운로드 단계에서 채움)."""
    return ItemClassifier.classify(url, raw_info=None)


def expand_targets(ctx) -> list[ClassifiedTarget]:
    """재생목록/채널 URL을 개별 동영상 항목 객체로 펼친다.

    반환: List[ClassifiedTarget] - 파이프라인 전체가 공유하는 단일 계약
    """
    from chzzktube.core.dl_platform import detect_content_type
    from chzzktube.pipeline.target_downloader.utils import _emit_error_log

    expanded: list[ClassifiedTarget] = []
    for url in ctx.targets:
        try:
            urls: list[ClassifiedTarget] | None = None
            if detect_content_type(url) == "playlist":
                urls = _flatten(ctx, url)
            else:
                u = url.lower()
                if "/@" in u or "/channel/" in u or "/c/" in u or "/user/" in u:
                    urls = _flatten(ctx, normalize_youtube_channel_url(url))

            if urls:
                # _flatten이 이미 List[ClassifiedTarget] 반환
                expanded.extend(urls)
            else:
                # 단일 영상 - 정규화 팩토리를 통해 즉시 승격
                expanded.append(_normalize_single_item(url))
        except Exception as ex:  # noqa: BLE001
            # [v3.8.1] 즉시 TUI 발행 금지 — finalizer에서 단일 출력
            _emit_error_log(ctx, url, str(ex), failed_targets=[])
            expanded.append(_normalize_single_item(url))

    return expanded


# 지연 import로 순환 의존성 방지
def _apply_cookie_opts(opts, cfg):
    from chzzktube.core.client_opts import _apply_cookie_opts as _aco
    _aco(opts, cfg)


def _apply_client_opts(opts, cfg, forced):
    from chzzktube.core.client_opts import _apply_client_opts as _acl
    _acl(opts, cfg, forced=forced)


def _apply_light_analysis_opts(opts):
    from chzzktube.core.client_opts import _apply_light_analysis_opts as _ala
    _ala(opts)


def _apply_ejs_opts(opts):
    from chzzktube.core.client_opts import _apply_ejs_opts as _ae
    _ae(opts)