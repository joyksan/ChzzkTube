### yt_logger_bridge.py - yt-dlp 로거 어댑터 (Analyze/Download 공용)
"""yt-dlp logger 콜백을 raw_log 버스로 연결하는 공용 어댑터.

- ANSI 제거는 utils.clean_ansi()만 사용한다.
- \r progress tick은 한 청크로 조립해 최신 meaningful tick만 발행한다.
- 일반 info/warning/error는 원문을 F12/history에 보존한다.
"""
import os
import re
import threading
import time

from utils import clean_ansi


_PROGRESS_RE = re.compile(r"^\s*\[download\].*?(\d+(?:\.\d+)?)%\s*$")
_MERGE_TEXT = "Merging formats into"
_ALREADY_DOWNLOADED = "has already been downloaded"


class YtLoggerBridge:
    """yt-dlp logger → raw_log bus adapter."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._carriage_buffer = ""
        self._last_progress = None
        self._last_progress_at = 0.0

    @staticmethod
    def _is_progress(msg: str) -> bool:
        return bool(_PROGRESS_RE.match(msg))

    def _emit_progress(self, msg: str) -> None:
        now = time.monotonic()
        with self._lock:
            # yt-dlp progress callbacks are often far faster than 2 Hz.
            if self._last_progress is not None and now - self._last_progress_at < 0.5:
                return
            self._last_progress = msg
            self._last_progress_at = now
        import raw_log
        from log_event import LogEvent
        raw_log.raw(
            "ytdlp",
            LogEvent(
                stage="YTDLP",
                status="RUN",
                platform="-",
                msg=msg,
                is_status=True,
            ),
            to_tui=True,
        )

    def _flush_carriage(self, msg: str, level: str) -> None:
        clean_msg = clean_ansi(msg)
        if not clean_msg:
            return
        with self._lock:
            if "\r" in clean_msg:
                parts = clean_msg.split("\r")
                self._carriage_buffer = parts[-1]
                clean_msg = self._carriage_buffer
            elif "\n" in clean_msg:
                clean_msg = self._carriage_buffer + clean_msg
                self._carriage_buffer = ""
            else:
                clean_msg = (self._carriage_buffer + clean_msg).strip()
                self._carriage_buffer = ""
        if not clean_msg.strip():
            return
        if self._is_progress(clean_msg):
            self._emit_progress(clean_msg)
            return
        import raw_log
        from log_event import LogEvent
        status = {
            "warning": "WARN",
            "error": "FAIL",
            "info": "OK",
            "debug": "OK",
        }.get(level, "OK")
        raw_log.raw(
            "ytdlp",
            LogEvent(
                stage="YTDLP",
                status=status,
                platform="-",
                msg=clean_msg,
                is_error=level == "error",
            ),
        )
        if _MERGE_TEXT in clean_msg:
            raw_log.raw(
                "dl",
                LogEvent(stage="MERG", status="RUN", platform="-", msg="merging"),
                to_tui=True,
            )
        if _ALREADY_DOWNLOADED in clean_msg:
            fname = (
                clean_msg.replace("[download]", "")
                .replace(_ALREADY_DOWNLOADED, "")
                .strip()
            )
            raw_log.raw(
                "dl",
                LogEvent(
                    stage="DL",
                    status="OK",
                    platform="-",
                    msg=f"skip — exists ({os.path.basename(fname)})",
                ),
                to_tui=True,
            )

    def debug(self, msg):
        self._flush_carriage(msg, "debug")

    def info(self, msg):
        self._flush_carriage(msg, "info")

    def warning(self, msg):
        self._flush_carriage(msg, "warning")

    def error(self, msg):
        self._flush_carriage(msg, "error")
