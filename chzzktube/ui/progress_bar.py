"""ProgressBar — 시각적 다운로드 진행률 표시 (stdlib-only).

raw_log 버스에 진행률 이벤트(pct, bar_frac, speed)를 발행한다.
is_status=False로 히스토리에만 쌓이게 하여 TUI 상태 줄 덮어쓰기 방지.
"""
import time
from collections.abc import Callable


class ProgressBar:
    """다운로드 진행률을 추적하고 raw_log에 시각적 진행 바를 발행한다.

    사용 예:
        bar = ProgressBar(component="yt-dlp", log_func=my_log_func)
        async with bar:
            # 다운로드 루프에서
            bar.update(downloaded, total)
        bar.finish("completed")
    """

    BAR_WIDTH = 10
    MIN_UPDATE_INTERVAL = 2.0
    MIN_PCT_DELTA = 5

    def __init__(
        self,
        component: str,
        log_func: Callable | None = None,
        *,
        total: int | None = None,
        label: str = "",
    ):
        self.component = component
        self.log_func = log_func
        self.total = total
        self.label = label or component
        self._start_time: float | None = None
        self._last_update: float = 0
        self._last_downloaded: int = 0
        self._finished = False

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if not self._finished:
            self.finish("completed" if exc_type is None else "failed")
        return False

    def start(self):
        self._start_time = time.monotonic()
        self._last_update = 0
        self._last_downloaded = 0
        self._finished = False
        self._emit(0, 0.0, "starting", speed="")

    def update(self, downloaded: int, total: int):
        if self._finished:
            return

        now = time.monotonic()
        if self.total is None or total != self.total:
            self.total = total

        # Rate limit: minimum time interval OR minimum percentage delta
        pct = 0
        if self.total and self.total > 0:
            pct = int(downloaded * 100 / self.total)
        
        if (now - self._last_update < self.MIN_UPDATE_INTERVAL and 
            pct - getattr(self, '_last_pct', 0) < self.MIN_PCT_DELTA and
            downloaded < self.total):
            return

        self._last_update = now
        self._last_pct = pct

        elapsed = now - self._start_time if self._start_time else 1.0
        speed_bps = downloaded / elapsed if elapsed > 0 else 0.0
        speed_str = self._format_speed(speed_bps)

        if self.total and self.total > 0:
            pct = int(downloaded * 100 / self.total)
            bar_frac = min(downloaded / self.total, 1.0)
        else:
            pct = 0
            bar_frac = 0.0

        # Minimal MSG for TUI: just "downloading"
        msg = "downloading"
        self._emit(pct, bar_frac, msg, speed=speed_str)

    def finish(self, status: str = "completed"):
        if self._finished:
            return
        self._finished = True

        if self.total and self.total > 0:
            pct = 100
            bar_frac = 1.0
        else:
            pct = 0
            bar_frac = 0.0

        elapsed = time.monotonic() - (self._start_time or time.monotonic())
        speed_bps = self.total / elapsed if self.total and elapsed > 0 else 0
        speed_str = self._format_speed(speed_bps)

        # Minimal MSG for TUI
        msg = status  # "completed" | "failed" | "verifying"
        # 완료 로그는 is_status=False (히스토리만, 상태 줄 덮어쓰기 방지)
        self._emit(pct, bar_frac, msg, speed=speed_str, status="OK", is_status=False)

    def _emit(self, pct: int, bar_frac: float, msg: str, speed: str = "", status: str = "RUN", is_status: bool = True):
        event = emit_progress(
            stage="DEPS",
            status=status,
            scope=self.component.upper(),
            msg=msg,
            speed=speed,
            pct=pct,
            bar_frac=bar_frac,
            is_status=is_status,  # 진행중=True(갱신형), 완료=False(히스토리만)
            is_error=False,
        )
        raw_log.raw("provisioning", event, to_tui=is_status, is_error=False)
        if self.log_func:
            self.log_func(event)

    @staticmethod
    def _format_speed(bps: float) -> str:
        if bps >= 1024 * 1024:
            return f"{bps / (1024 * 1024):.1f} MB/s"
        elif bps >= 1024:
            return f"{bps / 1024:.1f} KB/s"
        elif bps > 0:
            return f"{bps:.0f} B/s"
        return ""

    @staticmethod
    def _format_eta(seconds: float) -> str:
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            return f"{int(seconds // 60)}m {int(seconds % 60)}s"
        else:
            return f"{int(seconds // 3600)}h {int((seconds % 3600) // 60)}m"
from chzzktube.core import raw_log
from chzzktube.core.log_emitter import emit_progress


class ProgressManager:
    """다중 ProgressBar를 관리하는 컨텍스트 매니저.

    여러 동시 다운로드의 진행 바를 각각 독립적으로 관리한다.
    """

    def __init__(self, log_func: Callable | None = None):
        self.log_func = log_func
        self._bars: dict[str, ProgressBar] = {}

    def create(self, component: str, *, total: int | None = None, label: str = "") -> ProgressBar:
        bar = ProgressBar(component, log_func=self.log_func, total=total, label=label)
        self._bars[component] = bar
        return bar

    def get(self, component: str) -> ProgressBar | None:
        return self._bars.get(component)

    def remove(self, component: str):
        self._bars.pop(component, None)

    def finish_all(self, status: str = "completed"):
        for bar in self._bars.values():
            if not bar._finished:
                bar.finish(status)
        self._bars.clear()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.finish_all("completed" if exc_type is None else "failed")
        return False