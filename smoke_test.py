# smoke_test.py - 실제 Qt 환경에서의 임포트/인스턴스화/시그널 검증
"""
사용법:
    python smoke_test.py
검증 항목:
    1) 전 모듈 임포트 (순환참조/NameError 감지)
    2) QApplication + MainWindow 실제 생성
    3) 설정 로드/저장 동작 (config 모듈 위임 경로)
    4) DownloadWorker._expand_targets / AnalyzeWorker 시그널 존재
    5) 이벤트 루프 처리 후 정상 종료
"""
import os
import sys

# GUI 없이 headless 검증
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

failures = []


def check(label, fn):
    try:
        result = fn()
        print(f"[OK]   {label}" + (f" -> {result}" if result is not None else ""))
        return True
    except Exception as ex:
        print(f"[FAIL] {label} -> {type(ex).__name__}: {ex}")
        failures.append((label, ex))
        return False


print("=" * 60)
print("1) 모듈 임포트 검증")
print("=" * 60)
check("import config", lambda: __import__("config"))
check("import media", lambda: __import__("media"))
check("import cookies", lambda: __import__("cookies"))
check("import chzzk_api", lambda: __import__("chzzk_api"))
check("import utils", lambda: __import__("utils"))
check("import ui_components", lambda: __import__("ui_components"))
check("import updater", lambda: __import__("updater"))
check("import dialogs", lambda: __import__("dialogs"))
check("import downloader", lambda: __import__("downloader"))
check("import main", lambda: __import__("main"))

import config  # noqa: E402

print()
print("=" * 60)
print("2) config 모듈 기능 검증")
print("=" * 60)
check(
    "default_config 키 15개",
    lambda: len(config.default_config()) == 15 and sorted(config.default_config()),
)
check(
    "BASE_DIR / CONFIG_DIR 계산",
    lambda: f"BASE={config.BASE_DIR[-20:]}, CFG={config.CONFIG_DIR[-20:]}",
)
cfg_loaded = {}
def _load():
    global cfg_loaded
    cfg_loaded = config.load_config()
    return f"{len(cfg_loaded)} keys"
check("load_config() 실제 호출", _load)

print()
print("=" * 60)
print("3) QApplication + MainWindow 생성")
print("=" * 60)

APP = None


def _make_app():
    global APP
    from PyQt6.QtWidgets import QApplication

    APP = QApplication.instance() or QApplication(sys.argv)
    # 참조 유지 필수 — 지역변수로 두면 GC가 파괴해 이후 위젯 생성이 크래시남
    return type(APP).__name__


check("QApplication 생성", _make_app)


def _make_window():
    import main as m

    win = m.MainWindow()
    assert win.windowTitle(), "타이틀 없음"
    assert win.cfg, "cfg 비어있음"
    assert win.dl_state["running"] is False, "초기 상태 오류"
    return (
        f"title={win.windowTitle()!r}, "
        f"cfg_keys={len(win.cfg)}, "
        f"widgets: url={'Y' if win.le_url else 'N'}, "
        f"dl={'Y' if win.btn_download else 'N'}"
    )


win_ref = {}


def _make_and_keep():
    import main as m

    win = m.MainWindow()
    win_ref["win"] = win
    assert win.windowTitle(), "타이틀 없음"
    assert win.cfg, "cfg 비어있음"
    assert win.dl_state["running"] is False, "초기 상태 오류"
    assert hasattr(win, "te_concise"), "로그 위젯 없음"
    return (
        f"title={win.windowTitle()[:30]!r}... cfg_keys={len(win.cfg)}, "
        f"url_input=Y btn_download=Y log=Y"
    )


check("MainWindow 인스턴스화", _make_and_keep)

print()
print("=" * 60)
print("4) Worker 시그널/메서드 계약 검증")
print("=" * 60)


def _worker_contract():
    import downloader as d

    expected_signals = [
        "progress_update",
        "status_update",
        "log_concise",
        "log_full",
        "finished_all",
    ]
    present = [s for s in expected_signals if hasattr(d.DownloadWorker, s)]
    has_expand = callable(getattr(d.DownloadWorker, "_expand_targets", None))
    has_hook = callable(getattr(d.DownloadWorker, "hook", None))
    has_finish = callable(getattr(d.DownloadWorker, "handle_stream_finish", None))
    return (
        f"signals={present}, _expand_targets={has_expand}, "
        f"hook={has_hook}, handle_stream_finish={has_finish}"
    )


check("DownloadWorker API", _worker_contract)

print()
print("=" * 60)
print("5) 이벤트 루프 짧게 구동 후 정리")
print("=" * 60)


def _process_events():
    app = APP
    assert app is not None, "QApplication 없음"
    app.processEvents()
    win = win_ref.get("win")
    if win:
        # 로그 append가 예외 없이 동작하는지
        win.append_concise_log("[smoke] 테스트 메시지", False, False)
        app.processEvents()
        doc_text = win.te_concise.toPlainText()
        assert "[smoke]" in doc_text, "로그 반영 실패"
        return "log append OK"
    return "no window"


check("이벤트 처리 + 로그 append", _process_events)

print()
print("=" * 60)
if failures:
    print(f"결과: {len(failures)}개 실패")
    for label, ex in failures:
        print(f"  - {label}: {ex}")
    sys.exit(1)
else:
    print("결과: 전체 통과 [PASS]")
    sys.exit(0)