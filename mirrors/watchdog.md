"""chzzktube/core/watchdog.py - 단일 진실 시간(monotonic) 기반 구독형 워치독.

모든 타임아웃 상수와 하트비트 판정을 이 모듈로 집중해
15초 폴백/45초 분석/120초 게이트 등 산재한 매직 넘버를 단일 출처로 관리한다.

[설계]
- time.monotonic() 단일 진실 (시스템 시계 변경 영향 없음)
- 스레드 안전: Lock으로 _last_heartbeat / _grace_used 보호
- 주입 가능한 clock 파라미터로 단위 테스트에서 시간 조작 가능
- 워커는 heartbeat() 호출, 감시자는 check_timeout() 폴링
"""
import threading
import time
from typing import Callable


# ── 상수 단일 출처 (HANDOVER §3 표와 동기화) ───────────────────────────
FALLBACK_TIMEOUT_SEC = 15.0   # 기동 폴백 (READY 강제 개방)
FALLBACK_GRACE_SEC = 3.0      # 폴백 유예 1회 (Followup-4)
GATE_TIMEOUT_SEC = 120.0      # POT 게이트 2차 워치독 (Followup-3)
ANALYSIS_TIMEOUT_SEC = 45.0   # AnalyzeWorker 타임아웃


class LivenessWatchdog:
    """단일 진실 시간 기반 워치독 — 워커 하트비트로 수명 연장, Grace 1회 지원."""

    __slots__ = ("timeout_sec", "grace_sec", "_clock", "_lock", "_last_heartbeat", "_grace_used")

    def __init__(
        self,
        timeout_sec: float,
        grace_sec: float = 0.0,
        clock: Callable[[], float] | None = None,
    ):
        self.timeout_sec = float(timeout_sec)
        self.grace_sec = float(grace_sec)
        self._clock = clock or time.monotonic
        self._lock = threading.Lock()
        self._last_heartbeat = self._clock()
        self._grace_used = False

    def heartbeat(self) -> None:
        """워커 진행 틱(yt-dlp 콜백, download 진행 등)에서 호출해 수명을 연장한다."""
        with self._lock:
            self._last_heartbeat = self._clock()
            self._grace_used = False

    def check_timeout(self) -> bool:
        """타임아웃 만료 여부 판정. Grace 1회 적용 시 False 반환 후 grace 소진."""
        now = self._clock()
        with self._lock:
            elapsed = now - self._last_heartbeat
            if elapsed <= self.timeout_sec:
                return False
            if self.grace_sec > 0 and not self._grace_used:
                # 1회 유예: last_heartbeat를 'timeout - grace' 시점으로 이동
                self._last_heartbeat = now - self.timeout_sec + self.grace_sec
                self._grace_used = True
                return False
            return True

    def elapsed(self) -> float:
        """마지막 하트비트 이후 경과 시간 (조회용)."""
        with self._lock:
            return self._clock() - self._last_heartbeat

    def remaining(self) -> float:
        """타임아웃까지 남은 시간 (음수면 이미 만료)."""
        with self._lock:
            return self.timeout_sec - (self._clock() - self._last_heartbeat)

    def reset(self) -> None:
        """하트비트와 동일 — last_heartbeat=now, grace 복구."""
        self.heartbeat()