### yt_logger_bridge.py - yt-dlp 로거 어댑터 (Analyze/Download 공용)
"""yt-dlp logger 콜백 인터페이스를 Qt 시그널로 브리징하는 공용 어댑터.

- AnalyzeWorker(Analyze용)와 DownloadWorker(다운로드용)가 모두 사용한다.
- yt-dlp는 logger 객체의 debug/info/warning/error만 호출한다 — 이 계약을
  log_full(Qt Signal)과 log_concise(Qt Signal) 두 경로로 매핑한다.
- [계층] L0.5 추출 파이프라인 계층의 leaf — 워커 클래스를 모르고 Qt Signal만 안다.
"""
import os

from utils import clean_ansi
import log_console


class YtLoggerBridge:
    def __init__(self, log_full_signal, log_concise_signal=None):
        self.log_full_signal = log_full_signal
        self.log_concise_signal = log_concise_signal

    def debug(self, msg):
        clean_msg = clean_ansi(msg)
        if "Merging formats into" in clean_msg and self.log_concise_signal:
            self.log_concise_signal.emit(
                log_console.format_log_line('MERG', 'RUN', platform='-', spec='-', msg='merging'),
                False, False,
            )
        if clean_msg.strip():
            self.log_full_signal.emit(clean_msg)
            # [핵심] yt-dlp가 출력하는 이미 다운로드됨 안내 문구 감지!
            if "has already been downloaded" in clean_msg and self.log_concise_signal:
                # 파일명만 깔끔하게 추출해서 간결 로그에 출판
                fname = (
                    clean_msg.replace("[download]", "")
                    .replace("has already been downloaded", "")
                    .strip()
                )
                self.log_concise_signal.emit(
                    log_console.emit_event("DL", "OK", "-", f"skip — exists ({os.path.basename(fname)})"),
                    False,
                    False,
                )

    def info(self, msg):
        self.debug(msg)

    def warning(self, msg):
        if msg.strip():
            self.log_full_signal.emit(clean_ansi(msg))

    def error(self, msg):
        if msg.strip():
            self.log_full_signal.emit(clean_ansi(msg))