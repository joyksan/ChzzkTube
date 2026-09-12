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


_PROGRESS_RE = re.compile(r"^\s*\[download\].*?(\d+(?:\.\d+)?)%(?:\s|$)")
_MERGE_TEXT = "Merging formats into"
_ALREADY_DOWNLOADED = "has already been downloaded"


class YtLoggerBridge:
    """yt-dlp logger → raw_log bus adapter."""

    _MAX_CARRIAGE_CHARS = 4096

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
                stage="DL",
                status="RUN",
                scope="YTDL",
                msg=msg,
                is_status=True,
            ),
            to_tui=True,
        )

    def _emit_non_progress(self, clean_msg: str, level: str) -> None:
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
                stage="DL",
                status=status,
                scope="YTDL",
                msg=clean_msg,
                is_error=level == "error",
            ),
        )
        if _MERGE_TEXT in clean_msg:
            raw_log.raw(
                "dl",
                LogEvent(stage="MERG", status="RUN", scope="FFMP", msg="merging"),
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
                    scope="YTDL",
                    msg=f"skip - exists ({os.path.basename(fname)})",
                ),
                to_tui=True,
            )

    def _flush_carriage(self, msg: str, level: str) -> None:
        clean_msg = clean_ansi(msg)
        if not clean_msg:
            return

        # warning/error는 progress buffer에 갇히지 않고 즉시 보존한다.
        if level in {"warning", "error"}:
            clean_msg = clean_msg.replace("\r", " ").replace("\n", " ").strip()
            if clean_msg:
                self._emit_non_progress(clean_msg, level)
            return

        with self._lock:
            parts = clean_msg.replace("\n", "\r").split("\r")
            if len(parts) > 1:
                # 같은 콜백 안 \r 반복 = 같은 줄 덮어쓰기 스냅샷 → 마지막이 최신.
                candidate = parts[-1] or (parts[-2] if len(parts) > 1 else "")
                if clean_msg.endswith("\r"):
                    # 줄이 아직 진행 중 → 다음 청크와 연결하기 위해 이월 보류.
                    self._carriage_buffer = candidate[-self._MAX_CARRIAGE_CHARS:]
                    return
                self._carriage_buffer = ""
                clean_msg = candidate
            elif self._carriage_buffer:
                # \r 없는 청크 = 직전 이월 조각의 이어짐 → 합쳐 한 줄로 재구성.
                clean_msg = (
                    self._carriage_buffer + parts[-1]
                )[-self._MAX_CARRIAGE_CHARS:]
                self._carriage_buffer = ""
            else:
                clean_msg = parts[-1]

        clean_msg = clean_msg.strip()
        if not clean_msg:
            return
        if self._is_progress(clean_msg):
            self._emit_progress(clean_msg)
            return
        self._emit_non_progress(clean_msg, level)

    def debug(self, msg):
        self._flush_carriage(msg, "debug")

    def info(self, msg):
        self._flush_carriage(msg, "info")

    def warning(self, msg):
        self._flush_carriage(msg, "warning")

    def error(self, msg):
        self._flush_carriage(msg, "error")
