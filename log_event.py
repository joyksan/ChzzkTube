##### log_event.py - 구조화된 로그 이벤트 & 채널 플래그 (v3.2.4+)
"""raw_log 버스의 단일 진실 데이터 구조.

[구조] 모든 워커/모듈이 raw_log에 전송하는 로그는
**이미 렌더링된 문자열**이 아니라, 이 구조화된 LogEvent 객체여야 한다.

Channel 플래그로 각 구독자(TUI/F12/History)에게 정확히 전달.
- 정규식(is_tui_line) 추정 방식 완전 제거
- 발행자: LogEvent만 생성 → 어느 채널로 갈지 Enum으로 명시
- 구독자: 각자의 포맷에 맞게 렌더링 책임

[호환성] 기존 raw(tag, msg_str, ...) 호출도 그대로 동작.
LogEvent 객체 전달 시에만 새 경로 사용.
"""
from dataclasses import dataclass, field
from enum import Flag, auto
import time


class Channel(Flag):
    """로그 이벤트의 전달 대상 채널."""
    CONCISE = auto()   # 메인 TUI (컬럼 포맷)
    FULL = auto()      # F12 상세 서브 윈도우
    HISTORY = auto()   # log_history 파일

    BOTH = CONCISE | FULL
    ALL = CONCISE | FULL | HISTORY


@dataclass(slots=True)
class LogEvent:
    """구조화된 로그 이벤트."""
    stage: str = "SYS"
    status: str = "OK"
    platform: str = "-"
    spec: str = "-"
    speed: str = "-"
    pct: float = None
    bar_frac: float = None
    msg: str = ""
    is_status: bool = False
    is_error: bool = False
    timestamp: str = field(default_factory=lambda: time.strftime("[%H:%M:%S]"))

    def to_log_line(self) -> str:
        """log_console.format_log_line 시그니처와 100% 안전하게 바인딩하는 포맷터.
        
        Subscriber(View)에서 이 메서드를 호출하여 기존 format_log_line()의
        위치 인자 미스매치(TypeError) 없이 안전하게 TUI 컬럼 문자열로 변환한다.
        """
        from log_console import format_log_line  # lazy import (순환 참조 방지)
        return format_log_line(
            stage=self.stage,
            status=self.status,
            platform=self.platform,
            spec=self.spec,
            speed=self.speed,
            pct=self.pct,
            bar_frac=self.bar_frac,
            msg=self.msg,
        )