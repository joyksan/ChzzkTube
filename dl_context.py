### dl_context.py - 다운로드 파이프라인 컨텍스트 (D: worker grab-bag 해결)
"""DownloadWorker가 파이프라인 모듈에 넘기는 명시적 컨텍스트.

[문제] target_downloader/progress_emitter/finalizer가 worker 객체를 통째로
받아 worker.cfg, worker.logger, worker._speed_win 등을 암시적으로 접근.
"worker가 뭘 제공하는지"가 불명확해 신규 파이프라인 추가 시 계약을 알 수 없다.

[해결] 아래 dataclass로 계약을 명시한다. DownloadWorker는 자신의 상태에서
DownloadContext를 생성해 파이프라인에 넘기고, 파이프라인은 이 컨텍스트만 본다.
Qt Signal(YtLoggerBridge)은 그대로 참조로 전달된다 (QThread 상속 구조 유지).
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class DownloadContext:
    """다운로드 파이프라인 함수들이 소비하는 컨텍스트.

    DownloadWorker 인스턴스에서 extract()로 생성된다.
    파이프라인 모듈(target_downloader, progress_emitter, finalizer)은
    worker 객체 대신 이 컨텍스트만 받아 명시적 계약을 이행한다.
    """

    # 설정 (worker.cfg 딕셔너리 참조)
    cfg: Dict[str, Any]

    # 포맷 선택 ("auto"면 자동 선택)
    v_sel: str = "auto"
    a_sel: str = "auto"

    # 비디오 스펙 (v_list[0]에서 추출된 height/fps 등)
    v_spec: Dict[str, Any] = field(default_factory=dict)

    # 오디오 설명 (a_list[0]에서 추출)
    audio_desc: str = ""

    # 로거 (YtLoggerBridge — log_full/log_concise 시그널 포함)
    logger: Any = None
    
    # 간결 로그용 콜백 (progress_emitter 연동용)
    log_concise: Any = None

    # 현재 처리 중인 대상
    current_url: str = ""
    current_file: Optional[str] = None

    # 세션 상태 (UI→워커 단방향: canceled, skip)
    state: Dict[str, bool] = field(default_factory=lambda: {"canceled": False, "skip": False})

    # 속도 계산 (SpeedWindow — 이동평균)
    speed_win: Any = None

    # 배치 진행 현황
    total_count: int = 0
    current_idx: int = 0

    # 라이브 관련
    is_live_hint: bool = False
    live_partially_saved: bool = False

    # 포맷 선택 (분석 단계에서 결정된 클라이언트)
    yt_client: str = "auto"

    # 대상 목록 (expand_targets에서 참조)
    targets: list = field(default_factory=list)

    # 배치 완료 시그널 (DownloadWorker.finished_all 바인딩)
    finished_all: Any = None

    # 오류 수집 (다운로드 실패 시 메시지 누적)
    _errors: List[str] = field(default_factory=list, repr=False)

    def add_error(self, msg: str) -> None:
        """오류 메시지를 수집한다. finalizer가 배치 마감에서 참조한다."""
        self._errors.append(msg)

    @property
    def errors(self) -> List[str]:
        """수집된 오류 목록 (읽기 전용)."""
        return list(self._errors)

    def advance_target(self, idx: int, url: str) -> None:
        """타겟 진행 상태를 단일 지점에서 안전하게 업데이트하고 속도계 윈도우를 초기화한다."""
        self.current_idx = idx
        self.current_url = url
        self.current_file = None
        self._meta_logged = False
        if self.speed_win:
            self.speed_win.reset()