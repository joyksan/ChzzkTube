"""chzzktube/pipeline/classifier.py — 미디어 항목 사전 분류 및 규격 단일 출처 (SSOT).

[원칙]
- I/O 및 UI 설정(cfg) 오염 0건: 디스크나 전역 상태를 절대 건드리지 않는 순수 도메인 로직.
- 정직한 TriState 삼치 논리: 포맷 미확정(extract_flat) 상태를 함부로 True/False로 날조하지 않는다.
- None-Safety 보장: 하류 파이프라인이 None을 False로 오판해 스트림을 강등시키지 않도록 명시적 질의 메서드 제공.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any


class ContentKind(Enum):
    """콘텐츠 종류 — 플랫폼 및 스트림 성격의 명확한 분리."""
    VOD = auto()
    CLIP = auto()
    LIVE_YOUTUBE = auto()
    LIVE_CHZZK = auto()
    PLAYLIST = auto()
    UNKNOWN = auto()

    @property
    def is_live(self) -> bool:
        return self in (ContentKind.LIVE_YOUTUBE, ContentKind.LIVE_CHZZK)


@dataclass(frozen=True, slots=True)
class StreamCapability:
    """True / False / None(미확정) 삼치 논리를 엄격히 캡슐화한 스트림 역량 모델."""
    has_video: bool | None
    has_audio: bool | None
    requires_auth: bool = False

    @classmethod
    def indeterminate(cls, requires_auth: bool = False) -> StreamCapability:
        """extract_flat 등 메타데이터가 미비한 경우 사용하는 안전 팩토리."""
        return cls(has_video=None, has_audio=None, requires_auth=requires_auth)

    def is_video_confirmed(self) -> bool:
        """확정적으로 비디오가 존재하는지 여부 (None은 False 처리하여 보수적 접근)."""
        return self.has_video is True

    def is_audio_confirmed(self) -> bool:
        """확정적으로 오디오가 존재하는지 여부."""
        return self.has_audio is True

    def could_have_video(self) -> bool:
        """비디오가 존재할 가능성이 열려 있는지 (True 또는 None일 때 참)."""
        return self.has_video is not False

    def could_have_audio(self) -> bool:
        """오디오가 존재할 가능성이 열려 있는지 (True 또는 None일 때 참)."""
        return self.has_audio is not False


@dataclass(frozen=True, slots=True)
class CookiePolicyContext:
    """SRP 준수를 위한 인증/쿠키 요구사항 정책 명세 (I/O 없음)."""
    needs_cookie: bool
    reason: str = ""


@dataclass(slots=True)
class ClassifiedTarget:
    """파이프라인 전체가 공유하는 정규화된 항목 계약 객체."""
    url: str
    title: str
    kind: ContentKind
    capability: StreamCapability
    platform_tag: str
    downloadable: bool = True
    needs_pot: bool = False
    skip_reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_live(self) -> bool:
        return self.kind.is_live


class ItemClassifier:
    """UI cfg 및 부수 효과로부터 완벽히 격리된 순수 분류 엔진."""

    _POT_AVAIL_GATED = frozenset({
        "needs_auth", "premium_only", "private"
    })

    @classmethod
    def evaluate_cookie_policy(
        cls, info: Mapping[str, Any] | None = None
    ) -> CookiePolicyContext:
        """메타데이터 기반 인증 필요성 순수 판정."""
        if not info:
            return CookiePolicyContext(needs_cookie=False)
        age_limit = int(info.get("age_limit") or 0)
        availability = str(info.get("availability") or "").lower()

        if age_limit > 0:
            return CookiePolicyContext(needs_cookie=True, reason="age_limit")
        if availability in cls._POT_AVAIL_GATED:
            return CookiePolicyContext(needs_cookie=True, reason=availability)
        return CookiePolicyContext(needs_cookie=False)

    @classmethod
    def classify(
        cls, url: str, raw_info: Mapping[str, Any] | None = None
    ) -> ClassifiedTarget:
        """URL 및 메타데이터를 정밀 심사하여 ClassifiedTarget으로 변환."""
        info = dict(raw_info or {})
        u = url.lower().strip()

        # 1. 플랫폼 감별
        is_chzzk = "chzzk.naver.com" in u
        is_yt = any(p in u for p in ("youtube.com", "youtu.be"))
        platform = "CHZ" if is_chzzk else ("YT" if is_yt else "EXT")

        title = str(info.get("title") or info.get("videoTitle") or "untitled")
        is_live = bool(info.get("is_live"))
        cookie_policy = cls.evaluate_cookie_policy(info)
        # [핵심 변경] needs_pot는 age_limit>0(성인인증)만 — 멤버십은 Layer 1/2에서 해결
        needs_pot = is_yt and (info.get("age_limit", 0) > 0)

        # 2. 치지직 분기
        if is_chzzk:
            if "/clips/" in u or "/clip/" in u:
                return ClassifiedTarget(
                    url=url, title=title, kind=ContentKind.CLIP,
                    capability=StreamCapability(has_video=True, has_audio=True),
                    platform_tag=platform, needs_pot=False, metadata=info,
                )
            if "/live/" in u or is_live:
                return ClassifiedTarget(
                    url=url, title=title, kind=ContentKind.LIVE_CHZZK,
                    capability=StreamCapability(has_video=True, has_audio=True),
                    platform_tag=platform, needs_pot=False, metadata=info,
                )
            return ClassifiedTarget(
                url=url, title=title, kind=ContentKind.VOD,
                capability=StreamCapability(has_video=True, has_audio=True),
                platform_tag=platform, needs_pot=False, metadata=info,
            )

        # 3. 유튜브 라이브 정밀 판정 (회피 없이 일급 시민으로 등록)
        if is_yt and (is_live or "/live/" in u):
            return ClassifiedTarget(
                url=url, title=title, kind=ContentKind.LIVE_YOUTUBE,
                capability=StreamCapability(has_video=True, has_audio=True, requires_auth=cookie_policy.needs_cookie),
                platform_tag=platform, needs_pot=needs_pot, metadata=info,
            )

        # 4. 평탄화(Flat) 단계: 거짓말하지 않는 TriState 적용
        formats = info.get("formats")
        if info.get("_type") == "url" or not formats:
            is_audio_hint = "music.youtube.com" in u
            return ClassifiedTarget(
                url=url,
                title=title,
                kind=ContentKind.VOD,
                capability=StreamCapability(
                    has_video=False if is_audio_hint else None,
                    has_audio=True if is_audio_hint else None,
                    requires_auth=cookie_policy.needs_cookie,
                ),
                platform_tag=platform,
                needs_pot=needs_pot,
                metadata=info,
            )

        # 5. 완전 추출 포맷 메타데이터 심사 (이미지 전용 / 오디오 전용 정밀 감별)
        has_v = any(f.get("vcodec") not in (None, "none", "") for f in formats)
        has_a = any(f.get("acodec") not in (None, "none", "") for f in formats)

        # 비디오도 오디오도 없는 이미지 전용 영상 사전 필터링
        if not has_v and not has_a:
            return ClassifiedTarget(
                url=url, title=title, kind=ContentKind.UNKNOWN,
                capability=StreamCapability(has_video=False, has_audio=False),
                platform_tag=platform, downloadable=False,
                skip_reason="image-only", metadata=info,
            )

        return ClassifiedTarget(
            url=url,
            title=title,
            kind=ContentKind.VOD,
            capability=StreamCapability(
                has_video=has_v,
                has_audio=has_a,
                requires_auth=cookie_policy.needs_cookie,
            ),
            platform_tag=platform,
            needs_pot=needs_pot,
            metadata=info,
        )