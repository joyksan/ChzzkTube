### log_history.py - 기동·구성요소·PO 서버 로그의 영구 히스토리 기록기
"""매 실행마다 구성요소 확인/업데이트, PO Token 서버 기동, 다운로더 원본 로그를
날짜별 파일로 남겨 문제 재현·디버깅의 1차 증거로 삼는다.

*  위치 : config.LOG_DIR (frozen: <exe>/logs, source: <repo>/logs)
*  파일 : chzzktube_YYYY-MM-DD.log (하루 1파일, UTF-8, append)
*  세션 : session_begin / session_end 로 시작·종료 마커 기록
*  정리 : KEEP_DAYS 초과된 오래된 히스토리 파일은 세션 시작 시 자동 삭제
*  의존 : config(leaf)만 사용·비Qt — 워커 스레드에서 호출해도 안전(threading.Lock).
          기록 실패는 절대 앱 동작을 방해하지 않는다(모든 예외 흡수).
"""
import datetime
import os
import threading

KEEP_DAYS = 30
_LOCK = threading.Lock()

def _now():
    return datetime.datetime.now()

def _log_path(now):
    import config
    return os.path.join(config.LOG_DIR, f"chzzktube_{now:%Y-%m-%d}.log")

def log(msg, level="INFO"):
    """한 건(다중 줄 허용)을 오늘 히스토리 파일에 타임스탬프로 기록."""
    try:
        now = _now()
        lines = [
            l.rstrip()
            for l in str(msg).replace("\r", "").split("\n")
            if l.strip()
        ] or [""]
        with _LOCK:
            path = _log_path(now)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                for l in lines:
                    f.write(
                        f"[{now:%Y-%m-%d %H:%M:%S}] [{level:<5}] {l}\n"
                    )
    except Exception:
        pass  # 히스토리 기록 실패가 앱을 죽이지 않도록 흡수

def session_begin(app_name, app_version):
    """실행 세션 시작 마커 기록 + 오래된 히스토리 파일 정리."""
    log(
        f"===== {app_name} {app_version} 시작 (PID {os.getpid()}) =====",
        "BOOT",
    )
    log(
        "[~] 이 파일에는 구성요소 확인/업데이트, PO Token 서버 기동, "
        "다운로더 원본 로그가 기록됩니다.",
        "BOOT",
    )
    _prune()

def session_end():
    """실행 세션 종료 마커 기록."""
    log("===== 세션 종료 =====", "BOOT")

def exception(tag, t=None, v=None, tb=None):
    """미처리 예외 전체 트레이스백 기록. 인자 없이 except 블록 내에서도 호출 가능."""
    import sys
    import traceback

    if t is None:
        t, v, tb = sys.exc_info()
    try:
        body = "".join(traceback.format_exception(t, v, tb) or []).strip()
    except Exception:
        body = f"{t}: {v}"
    log(f"[{tag}]\n{body}", "ERROR")

def _prune():
    """KEEP_DAYS 초과 히스토리 파일 삭제 (세션 시작 시 1회)."""
    try:
        import config
        d = config.LOG_DIR
        cutoff = (_now() - datetime.timedelta(days=KEEP_DAYS)).timestamp()
        with _LOCK:
            if not os.path.isdir(d):
                return
            for name in os.listdir(d):
                if not (name.startswith("chzzktube_") and name.endswith(".log")):
                    continue
                p = os.path.join(d, name)
                try:
                    if os.path.getmtime(p) < cutoff:
                        os.remove(p)
                except OSError:
                    pass
    except Exception:
        pass
