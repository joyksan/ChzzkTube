"""raw_log — 앱 전체 동작의 단일 진실 공급원 (raw 스택 버스).

[구조] 모든 동작 로그는 raw(tag, msg) 하나로 진입 → 3채널 팬아웃:
- concise : MainWindow.append_concise_log (TUI 화면)
- full    : MainWindow.append_full_log (F12 상세)
- history : log_history.log (영구 파일)
필터링은 각 모듈이 알아서 — raw에는 모든 게 쌓인다.

[계층] Qt·위젯 무의존. 구독자는 MainWindow가 기동 시 1회 등록.
워커 스레드에서 raw() 호출 안전 (팬아웃은 구독자 책임 — Qt 시그널 경유).
구독 전 호출은 history에만 적재 (유실 방지).
"""
import threading

_LOCK = threading.RLock()
_concise_subs: list = []
_full_subs: list = []


def subscribe_concise(fn):
    """메인로그 구독 등록 (중복 방지)."""
    with _LOCK:
        if fn not in _concise_subs:
            _concise_subs.append(fn)


def subscribe_full(fn):
    """F12 상세로그 구독 등록 (중복 방지)."""
    with _LOCK:
        if fn not in _full_subs:
            _full_subs.append(fn)


def raw(tag, msg, is_status=False, is_error=False):
    """단일 진입점 — 모든 앱 동작은 여기로.

    Args:
        tag: 발생원 (pot-readiness / prewarm-lock / pot / deps 등)
        msg: TUI 컬럼 라인이면 concise 화면에도, 아니면 F12/history에만.
        is_status/is_error: concise 상태줄 계약 그대로 전달.
    """
    from log_console import is_tui_line
    import log_history
    text = str(msg)
    try:
        log_history.log(f"[{tag}] {text}")
    except Exception:
        pass
    with _LOCK:
        concise = list(_concise_subs)
        full = list(_full_subs)
    if is_tui_line(text):
        for fn in concise:
            try:
                fn(text, is_status=is_status, is_error=is_error)
            except Exception:
                pass
    for fn in full:
        try:
            fn(f"[{tag}] {text}" if not text.startswith(f"[{tag}]") else text)
        except Exception:
            pass
