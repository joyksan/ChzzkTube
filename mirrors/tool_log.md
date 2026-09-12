"""tool_log — 외부툴 출력 흡수 단일 래퍼 (v3.3.2).

[원칙] 새 기능이 외부툴(yt-dlp/streamlink/ffmpeg/bgutil)을 호출할 때는
이 모듈 경유만 허용한다. 직접 subprocess 파싱·로거 세팅 코드의 중복 작성을
금지한다 — 파싱 로직은 여기서 한 번만, 기능은 호출만.

[채널]
- yt-dlp Python API   : logger=YtLoggerBridge 주입 (Injection) — 기존 브리지 재사용
- subprocess(stderr)  : pump() — reader 스레드로 라인 흡수 → LogEvent(rendered=True)
                        원문 보존 → raw 버스. TUI 요약 1줄(상태 틱)은 progress_tick.
- CLI 일괄 실행       : run_cli() — updater.cli_raw 래핑 + F12 절취 분리 계약 유지.

[프로토콜] 무거운 추상화 없이 얇은 Protocol 3종만 선언한다.
새 어댑터는 아래 형상만 만족하면 된다 (덕타이핑 + 정적 검사 양립).
"""
import subprocess
import threading
from typing import Iterable, Optional, Protocol


class ToolLogger(Protocol):
    """yt-dlp logger 형상 — debug/info/warning/error 4메서드."""

    def debug(self, msg: str) -> None: ...
    def info(self, msg: str) -> None: ...
    def warning(self, msg: str) -> None: ...
    def error(self, msg: str) -> None: ...


class LineRunner(Protocol):
    """subprocess 라인 펌프 형상 — cmd 실행 → stdout+stderr 원문 라인 스트림."""

    def run(self, cmd: list, **kw) -> Iterable[str]: ...


class TokenProvider(Protocol):
    """PO 토큰 공급 형상 — video_id → 토큰 또는 None."""

    def fetch(self, video_id: str) -> Optional[str]: ...


def make_ytdlp_logger():
    """yt-dlp Python API 주입용 로거 — YtLoggerBridge 단일 출처.

    새 기능에서 yt-dlp logger 파라미터가 필요하면 이 팩토리만 호출할 것.
    YtLoggerBridge 클래스 직접 import·인스턴스화의 산발을 금지한다.
    """
    from yt_logger_bridge import YtLoggerBridge

    return YtLoggerBridge()


def pump(cmd, tag, stage, scope="-", to_tui=False, cancel=None,
         line_budget=4096, encoding="utf-8"):
    """subprocess stderr 실시간 흡수 — ffmpeg/streamlink/bgutil 공용.

    - reader 스레드로 stderr를 라인 단위 흡수, LogEvent(rendered=True) 원문
      보존으로 raw 버스에 적재한다 (F12+history, to_tui면 TUI도).
    - stdout은 호출부가 소비(파이프/파일)하도록 proc을 반환한다.
    - cancel(): 호출 시 True면 자식을 kill하고 drain한다.
    - 종료 코드가 0이 아니면 FAIL 1줄을 TUI에 남긴다.

    반환: (proc, stderr_thread) — 호출부는 stdout 처리 후 proc.wait() +
    stderr_thread.join()으로 마감할 것.
    """
    import os

    import raw_log
    from log_event import LogEvent

    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=creationflags,
    )

    def _drain():
        try:
            for raw in iter(proc.stderr.readline, b""):
                if not raw:
                    break
                try:
                    line = raw.decode(encoding, "replace").strip()
                except Exception:
                    continue
                if not line:
                    continue
                if len(line) > line_budget:
                    line = line[:line_budget] + "…"
                try:
                    raw_log.raw(
                        tag,
                                                LogEvent(stage=stage, status="OK", scope=scope,
                                 msg=line, rendered=True),
                        to_tui=bool(to_tui),
                    )
                except Exception:
                    pass
                if cancel is not None:
                    try:
                        if cancel():
                            break
                    except Exception:
                        pass
        except Exception:
            pass

    t = threading.Thread(target=_drain, daemon=True)
    t.start()
    return proc, t


def run_cli(label, *args, timeout=15):
    """CLI 일괄 실행 — updater.cli_raw 래핑 (수집 원문 전량 반환).

    절취는 호출부가 updater.truncate_for_full_log로 적재 시점에 수행할 것.
    """
    import updater

    return updater.cli_raw(label, *args, timeout=timeout)
