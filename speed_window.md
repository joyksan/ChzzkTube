##### speed_window.py - 10초 이동평균 속도계
"""네트워크에서 실제 흐른 바이트만 샘플로 누적해 평균 속도를 계산한다.

라이브=릴레이 파이프 계수, VOD=yt-dlp downloaded_bytes 를 add()에 넘기며,
스트림 전환(비디오→오디오)·타겟 전환 시 reset()으로 윈도우를 비운다.
"""
import time


class SpeedWindow:
    """10초 이동평균 속도계.

    add(총 바이트 누적값)를 계속 공급하면 speed()가 초당 바이트를 반환.
    내부적으로 (타임스탬프, 누적바이트) 표본을 10초 윈도우로 유지한다.
    """

    def __init__(self, window=10.0):
        self._window = float(window)
        self._samples = []
        self._last_total = 0
        self._last_t = 0.0

    def reset(self):
        """윈도우 초기화 — 스트림 전환·타겟 전환 시 호출."""
        self._samples.clear()
        self._last_total = 0
        self._last_t = 0.0

    def add(self, total_bytes, t=None):
        """누적 바이트를 샘플로 추가 (t는 monotonic 초, 기본 now)."""
        now = t if t is not None else time.monotonic()
        self._last_total = total_bytes
        self._last_t = now
        self._samples.append((now, float(total_bytes)))
        cutoff = now - self._window
        if cutoff > 0:
            self._samples = [(tt, b) for tt, b in self._samples if tt >= cutoff]

    def speed(self):
        """초당 바이트. 표본 2개 미만 또는 시간차 없으면 0.0."""
        if len(self._samples) < 2:
            return 0.0
        t0, b0 = self._samples[0]
        t1, b1 = self._samples[-1]
        dt = t1 - t0
        if dt <= 0:
            return 0.0
        return (b1 - b0) / dt