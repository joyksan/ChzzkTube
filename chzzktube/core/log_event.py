##### log_event.py - 구조화된 로그 이벤트 (v3.4.0)
"""raw_log 버스의 단일 진실 데이터 구조.

[계약 v3.4.0 — 4칸 미니멀 포맷]
- 발행자는 행동 근원(raw() 호출점)에서 LogEvent를 동봉해 전송한다.
  라벨링(stage/status/scope)은 태어난 곳에서 결정된다.
- SPEC 컬럼 폐지: spec 필드는 deprecated — 렌더러가 [spec] 태그로 MSG에 흡수.
  새 발행점에서 spec= 전달 금지.
- 채널 포함관계: history=전량, F12(full)=전량(⊇TUI), TUI(concise)=to_tui 선택.
  → "F12가 안 받는 로그"는 존재하지 않는다.
- 콘텐츠 정규식(is_tui_line) 라우팅 제로 — 렌더링 책임은 구독자(View)에게.
"""
from dataclasses import dataclass, field
import time


# v3.4.0 허용 STAGE 8종 / STATUS 9종 — 이외 값 발행 금지.
STAGES = ("SYS", "DEPS", "ANAL", "DL", "LIVE", "MERG", "BATCH", "POT")
STATUSES = ("READY", "RUN", "OK", "DONE", "SKIP", "WARN", "FAIL", "ABORT", "END")


@dataclass(slots=True)
class LogEvent:
    """구조화된 로그 이벤트."""
    stage: str = "SYS"
    status: str = "OK"
    # v3.4.0: platform → scope 개명. platform은 호환 별칭(읽기 전용 X, 쓰기 허용).
    scope: str = "-"
    platform: str = field(default="-", repr=False, compare=False)  # deprecated
    # v3.4.0 deprecated: SPEC 컬럼 폐지. 전달 시 [spec] 태그로 MSG 흡수된다.
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
