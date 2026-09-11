### worker_context.py - Worker 컨텍스트 데이터클래스
"""DownloadWorker가 공유하는 상태를 타입 안전하게 캡슐화.

[계층] L0.5 leaf — Qt 없음, dataclass만. Worker 구현체와 추출 파이프라인의
계약서 역할. mypy/pyright 타입 힌트로 IDE 자동완성·정적 검증 지원.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from speed_window import SpeedWindow
from yt_logger_bridge import YtLoggerBridge


@dataclass
class WorkerContext:
    """DownloadWorker가 공유하는 컨텍스트 — 불필요한 속성 전이 방지."""

    # 설정 (불변에 가깝음)
    cfg: Dict[str, Any]
    
    # 선택된 포맷
    v_sel: str = "auto"
    a_sel: str = "auto"
    v_spec: Dict[str, Any] = field(default_factory=dict)
    audio_desc: str = ""
    
    # 런타임 상태 (가변)
    logger: Optional[YtLoggerBridge] = None
    current_url: str = ""
    current_file: str = ""
    state: Dict[str, Any] = field(default_factory=dict)  # canceled, skip
    _speed_win: SpeedWindow = field(default_factory=SpeedWindow)
    
    # 배치 진행
    total_count: int = 0
    current_idx: int = 0
    
    # 라이브/치즈직 특화
    is_live_hint: bool = False
    live_partially_saved: bool = False
    
    # 치즈직 메타데이터
    chzzk_info: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        if not isinstance(self.cfg, dict):
            raise TypeError("cfg must be dict")
        if not isinstance(self.v_spec, dict):
            raise TypeError("v_spec must be dict")
        if not isinstance(self.state, dict):
            raise TypeError("state must be dict")
        if self.logger is not None and not isinstance(self.logger, YtLoggerBridge):
            raise TypeError("logger must be YtLoggerBridge")
        if not isinstance(self._speed_win, SpeedWindow):
            raise TypeError("_speed_win must be SpeedWindow")