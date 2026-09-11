### yt_logger_bridge.py - yt-dlp 로거 어댑터 (Analyze/Download 공용)
"""yt-dlp logger 콜백 인터페이스를 raw 버스로 브리징하는 공용 어댑터.

- AnalyzeWorker(Analyze용)와 DownloadWorker(다운로드용)가 모두 사용한다.
- yt-dlp는 logger 객체의 debug/info/warning/error만 호출한다 — 이 계약을
  raw_log 버스 단일 경유로 매핑한다 (F12 원문 + TUI 이벤트).
- [계층] L0.5 추출 파이프라인 계층의 leaf — 워커 클래스를 모른다.
- [스레드] yt-dlp 로거는 워커 스레드에서 호출된다 — raw()는 Signal.emit으로
  GUI 스레드에 큐잉하므로 직접 호출 안전.
- [v3.3.0] 시그널 인자 폐기 — 버스 직행.
"""
import os

from utils import clean_ansi


class YtLoggerBridge:
    """yt-dlp logger → raw_log 버스 어댑터 (시그널 없음 — 버스 직행)."""

    def debug(self, msg):
        clean_msg = clean_ansi(msg)
        import raw_log
        from log_event import LogEvent
        if "Merging formats into" in clean_msg:
            raw_log.raw(
                "dl",
                LogEvent(stage="MERG", status="RUN", platform="-", msg="merging"),
                to_tui=True,
            )
        if clean_msg.strip():
            # [F12 원문] yt-dlp stdout 그대로 — TUI 오염 없음
            raw_log.raw(
                "ytdlp",
                LogEvent(stage="YTDLP", status="OK", msg=clean_msg),
            )
            # [핵심] yt-dlp가 출력하는 이미 다운로드됨 안내 문구 감지!
            if "has already been downloaded" in clean_msg:
                # 파일명만 깔끔하게 추출해서 간결 로그에 출판
                fname = (
                    clean_msg.replace("[download]", "")
                    .replace("has already been downloaded", "")
                    .strip()
                )
                raw_log.raw(
                    "dl",
                    LogEvent(stage="DL", status="OK", platform="-",
                             msg=f"skip — exists ({os.path.basename(fname)})"),
                    to_tui=True,
                )

    def info(self, msg):
        self.debug(msg)

    def warning(self, msg):
        if msg.strip():
            import raw_log
            from log_event import LogEvent
            raw_log.raw("ytdlp", LogEvent(stage="YTDLP", status="WARN",
                                          msg=clean_ansi(msg)))

    def error(self, msg):
        if msg.strip():
            import raw_log
            from log_event import LogEvent
            raw_log.raw("ytdlp", LogEvent(stage="YTDLP", status="FAIL",
                                          msg=clean_ansi(msg), is_error=True))