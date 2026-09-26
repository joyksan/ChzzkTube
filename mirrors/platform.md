"""chzzktube/infra/platform.py - 크로스플랫폼 HAL (Hardware Abstraction Layer).

OS 종속 코드의 단일 격리 지점. 상위 비즈니스 로직은 이 모듈의 함수만
호출하고, OS 판정·ctypes·플래그를 직접 다루지 않는다.

원칙:
- OS 판정은 sys.platform 단일 출처 (is_windows/is_macos).
- Qt 역의존 금지: QWidget이 아니라 네이티브 핸들(int)/경로(str)만 받는다.
- 바보 모듈: chzzktube.* 상위 로직을 import하지 않는다 (stdlib only).
- 스폰 용도 분리: spawn_kwargs (단발/프로브) / daemon_spawn_kwargs (데몬).
"""
import asyncio
import subprocess
import sys
from typing import Any, Dict


def is_windows() -> bool:
    return sys.platform == "win32"


def is_macos() -> bool:
    return sys.platform == "darwin"


def exe_suffix() -> str:
    """현재 OS의 실행 파일 확장자."""
    return ".exe" if is_windows() else ""


def spawn_kwargs(use_no_window: bool = True) -> Dict[str, Any]:
    """단발/프로브용 스폰 인자 — Windows 창 억제만. POSIX는 빈 dict."""
    if is_windows() and use_no_window:
        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
    return {}


def daemon_spawn_kwargs(use_no_window: bool = True) -> Dict[str, Any]:
    """장기 데몬용 스폰 인자 — Win: NO_WINDOW|NEW_PROCESS_GROUP, POSIX: 세션 분리."""
    kw = spawn_kwargs(use_no_window)
    if is_windows():
        kw["creationflags"] |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        kw["start_new_session"] = True
    return kw


def strip_macos_quarantine(path: str) -> None:
    """macOS quarantine xattr 제거 (동기). 비-macOS 및 xattr 부재 시 무해한 no-op."""
    if not is_macos() or not path:
        return
    try:
        subprocess.run(
            ["xattr", "-dr", "com.apple.quarantine", str(path)],
            capture_output=True, check=False,
        )
    except Exception:
        pass


async def astrip_macos_quarantine(path: str) -> None:
    """`strip_macos_quarantine`의 async 래퍼 — worker thread 위임.

    async 함수에서 `subprocess.run`을 직접 호출하면 이벤트 루프가 블로킹되므로
    (ruff ASYNC221) 반드시 이 헬퍼를 경유한다. 비-macOS에서는 thread 생성 없이 즉시 반환.
    """
    if not is_macos() or not path:
        return
    await asyncio.to_thread(strip_macos_quarantine, path)


def flash_window(hwnd: int) -> None:
    """Windows 작업 표시줄 알림 (Qt 역의존 제거 — 순수 int 핸들 수신)."""
    if not is_windows() or not hwnd:
        return
    try:
        import ctypes

        class FLASHWINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", ctypes.c_uint),
                ("hwnd", ctypes.c_void_p),
                ("dwFlags", ctypes.c_uint),
                ("uCount", ctypes.c_uint),
                ("dwTimeout", ctypes.c_uint),
            ]

        info = FLASHWINFO(ctypes.sizeof(FLASHWINFO), hwnd, 3, 3, 0)
        ctypes.windll.user32.FlashWindowEx(ctypes.byref(info))
    except Exception:
        pass


def set_app_user_model_id(app_id: str) -> None:
    """Windows 작업 표시줄 그룹핑 ID (비-Windows는 no-op)."""
    if not is_windows() or not app_id:
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except (AttributeError, OSError):
        pass


def play_beep() -> None:
    """Windows 시스템 알림음 (비-Windows no-op, winsound 가드 내장)."""
    if not is_windows():
        return
    try:
        import winsound  # type: ignore[import-not-found]

        winsound.MessageBeep()
    except Exception:
        pass

def reveal_in_file_manager(path: str) -> None:
    """탐색기/파인더로 경로 노출 (utils._open_windows_explorer 승격)."""
    import os as _os

    target = _os.path.normpath(_os.path.abspath(path))
    if is_windows():
        import subprocess as _sp

        is_file = _os.path.isfile(target)
        folder = target if not is_file else _os.path.dirname(target)
        if is_file:
            _sp.Popen(["explorer.exe", "/n,", "/select," + target], close_fds=True)
        else:
            _sp.Popen(["explorer.exe", "/n,", folder], close_fds=True)
    elif is_macos():
        import subprocess as _sp

        _sp.Popen(["open", path])
    else:
        import subprocess as _sp

        _sp.Popen(["xdg-open", path])


def attach_to_parent_lifecycle(proc) -> None:
    """Windows: 자식을 Job Object에 할당 (부모 종료 시 자동 정리, POSIX no-op)."""
    if not is_windows() or proc is None:
        return
    try:
        import ctypes
        from ctypes import wintypes

        class JOB_BASIC(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        KILL_ON_CLOSE = 0x2000
        h_job = ctypes.windll.kernel32.CreateJobObjectW(None, None)
        if not h_job:
            return
        info = JOB_BASIC()
        info.LimitFlags = KILL_ON_CLOSE
        ok = ctypes.windll.kernel32.SetInformationJobObject(
            h_job, 4, ctypes.byref(info), ctypes.sizeof(info)
        )
        if not ok:
            ctypes.windll.kernel32.CloseHandle(h_job)
            return
        h_proc = getattr(proc, "_handle", None)
        if h_proc is None:
            ctypes.windll.kernel32.CloseHandle(h_job)
            return
        if not ctypes.windll.kernel32.AssignProcessToJobObject(h_job, h_proc):
            ctypes.windll.kernel32.CloseHandle(h_job)
    except Exception:
        pass


def kill_tree(proc) -> None:
    """프로세스 트리 종료 — Windows Job Object / POSIX 프로세스 그룹."""
    import os as _os
    import signal as _signal

    if proc is None:
        return
    try:
        if proc.poll() is not None:
            return
    except Exception:
        pass
    if is_windows():
        try:
            import ctypes

            h_proc = getattr(proc, "_handle", None)
            if h_proc is not None:
                h_job = ctypes.windll.kernel32.CreateJobObjectW(None, None)
                if h_job:
                    try:
                        ctypes.windll.kernel32.AssignProcessToJobObject(h_job, h_proc)
                        ctypes.windll.kernel32.TerminateJobObject(h_job, 1)
                    finally:
                        ctypes.windll.kernel32.CloseHandle(h_job)
                    try:
                        proc.wait(timeout=5)
                    except Exception:
                        pass
                    return
        except Exception:
            pass
        try:
            proc.kill()
        except Exception:
            pass
        return
    try:
        _os.killpg(_os.getpgid(proc.pid), _signal.SIGKILL)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass

