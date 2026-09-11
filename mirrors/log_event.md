##### log_event.py - 구조화된 로그 이벤트 (v3.3.0)
"""raw_log 버스의 단일 진실 데이터 구조.

[계약 v3.3.0 — 포함관계 모델]
- 발행자는 행동 근원(raw() 호출점)에서 LogEvent를 동봉해 전송한다.
  라벨링(stage/status/platform/spec)은 태어난 곳에서 결정된다.
- 채널 포함관계: history=전량, F12(full)=전량(⊇TUI), TUI(concise)=to_tui 선택.
  → "F12가 안 받는 로그"는 존재하지 않는다. (Channel 3비트 플래그 폐기)
- 콘텐츠 정규식(is_tui_line) 라우팅 제로 — 렌더링 책임은 구독자(View)에게.
"""
from dataclasses import dataclass, field
import time


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
    # msg가 이미 표시 완성형(컬럼 포맷·원문)일 때 True — 뷰는 재포맷하지 않는다
    rendered: bool = False
    timestamp: str = field(default_factory=lambda: time.strftime("[%H:%M:%S]"))
