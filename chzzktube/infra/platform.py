"""chzzktube/infra/platform.py - 크로스플랫폼 HAL (Hardware Abstraction Layer).

OS 종속 코드의 단일 격리 지점. 상위 비즈니스 로직은 이 모듈의 함수만
호출하고, OS 판정·ctypes·플래그를 직접 다루지 않는다.

원칙:
- OS 판정은 sys.platform 단일 출처 (is_windows/is_macos).
- Qt 역의존 금지: QWidget이 아니라 네이티브 핸들(int)/경로(str)만 받는다.
- 바보 모듈: chzzktube.* 상위 로직을 import하지 않는다 (stdlib only).
- 스폰 용도 분리: spawn_kwargs (단발/프로브) / daemon_spawn_kwargs (데몬).
- best-effort 부가 기능(알림음·작업표시줄 등)의 실패는 기능 상실일 뿐이므로
  삼키되 `_warn`으로 사유를 남긴다 — 무음 pass 금지 (S110/BLE001).
"""
import asyncio
import subprocess
import sys
from typing import Any


def _warn(scope: str, exc: BaseException) -> None:
    """best-effort 실패 진단 — 예외 삼킴(S110/BLE001)의 단일 탈출구.

    진단은 stderr로 1줄만 쓴다. 상위 로깅 계층(chzzktube.core) 역참조는
    '바보 모듈' 원칙 위반이므로 금지한다.

    Windows GUI(PyInstaller --noconsole)에서는 sys.stderr가 None일 수 있고,
    테스트에서는 pytest가 stderr를 교체한다. 어느 쪽이든 진단 실패가
    원래 삼키려던 동작을 되살리면 안 되므로 모든 오류를 무시한다
    (이 함수 자체는 S110/BLE001 예외 — 마지막 방어선이므로 상위로 못 올린다).
    """
    try:
        stream = sys.stderr
        if stream is None:
            return
        print(f"[platform] {scope}: {type(exc).__name__}", file=stream)
    except Exception:  # noqa: BLE001, S110 — 진단 실패가 호출자 동작을 바꾸면 안 됨
        pass


def is_windows() -> bool:
    return sys.platform == "win32"


def is_macos() -> bool:
    return sys.platform == "darwin"


def exe_suffix() -> str:
    """현재 OS의 실행 파일 확장자."""
    return ".exe" if is_windows() else ""


def spawn_kwargs(use_no_window: bool = True) -> dict[str, Any]:
    """단발/프로브용 스폰 인자 — Windows 창 억제만. POSIX는 빈 dict."""
    if is_windows() and use_no_window:
        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
    return {}


def daemon_spawn_kwargs(use_no_window: bool = True) -> dict[str, Any]:
    """장기 데몬용 스폰 인자 — Win: NO_WINDOW|NEW_PROCESS_GROUP, POSIX: 세션 분리."""
    kw = spawn_kwargs(use_no_window)
    if is_windows():
        # use_no_window=False일 때 spawn_kwargs가 {}를 반환해도
        # creationflags 키를 안전하게 초기화한 뒤 비트 연산 수행
        kw["creationflags"] = kw.get("creationflags", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
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
    except Exception as exc:  # noqa: BLE001 — xattr 부재·실행 권한 오류는 기능 상실일 뿐
        _warn(f"xattr quarantine strip 실패: {path}", exc)


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
    except Exception as exc:  # noqa: BLE001 — ctypes/windll 부재 시 알림 생략 (기능 상실일 뿐)
        _warn(f"FlashWindowEx 실패 (hwnd={hwnd})", exc)


def set_app_user_model_id(app_id: str) -> None:
    """Windows 작업 표시줄 그룹핑 ID (비-Windows는 no-op)."""
    if not is_windows() or not app_id:
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except (AttributeError, OSError) as exc:  # windll/shell32 부재 = 기능 상실일 뿐
        _warn(f"AppUserModelID 설정 실패: {app_id}", exc)


def play_beep() -> None:
    """Windows 시스템 알림음 (비-Windows no-op, winsound 가드 내장)."""
    if not is_windows():
        return
    try:
        import winsound  # type: ignore[import-not-found]

        winsound.MessageBeep()
    except Exception as exc:  # noqa: BLE001 — winsound 미지원 환경에서 알림음 생략
        _warn("MessageBeep 실패", exc)

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


def attach_to_parent_lifecycle(proc) -> bool:
    """Windows: 자식을 Job Object에 할당 (부모 종료 시 자동 정리, POSIX no-op).

    반환값은 "Job Object에 실제로 할당됐는가"다. 호출자는 이 값을
    `proc._ct_job` 같은 표식의 근거로만 써야 한다 — 종전에는 실패 경로에서도
    `CloseHandle`만 하고 아무 신호도 주지 않아, 호출자가 핸들 존재만 보고
    "할당 성공"으로 오인했다 (할당 실패 시 부모 종료 정리가 조용히 무력화됨).
    """
    if not is_windows() or proc is None:
        return False
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
            return False
        info = JOB_BASIC()
        info.LimitFlags = KILL_ON_CLOSE
        ok = ctypes.windll.kernel32.SetInformationJobObject(
            h_job, 4, ctypes.byref(info), ctypes.sizeof(info)
        )
        if not ok:
            ctypes.windll.kernel32.CloseHandle(h_job)
            return False
        h_proc = getattr(proc, "_handle", None)
        if h_proc is None:
            ctypes.windll.kernel32.CloseHandle(h_job)
            return False
        if not ctypes.windll.kernel32.AssignProcessToJobObject(h_job, h_proc):
            ctypes.windll.kernel32.CloseHandle(h_job)
            return False
        # [핸들 유지] 여기서 닫으면 KILL_ON_CLOSE 동작이 사라진다 — 열린 채 둔다.
        # 할당이 끝난 Job 핸들은 프로세스 수명 동안 유지되어야 부모 종료 시
        # 자식이 함께 정리된다.
        return True
    except Exception as exc:  # noqa: BLE001 — ctypes/windll 부재 등 → 미할당 보고 (호출자 폴백)
        _warn("Job Object 할당 실패 (상위 폴백에 위임)", exc)
        return False


def kill_tree(proc) -> None:
    """프로세스 트리 종료 — Windows Job Object / POSIX 프로세스 그룹."""
    import os as _os
    import signal as _signal

    if proc is None:
        return
    try:
        if proc.poll() is not None:
            return
    except Exception as exc:  # noqa: BLE001 — poll() 미구현 목/프로세스 → 종료 여부 미상이므로 킬 경로 계속 진행
        _warn("proc.poll() 확인 실패 — 킬 경로 계속", exc)
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
                    except Exception as exc:  # noqa: BLE001 — TerminateJobObject 기완료, 회수 대기 초과는 무해
                        _warn("Job Object 종료 후 회수 대기 초과", exc)
                    return
        except Exception as exc:  # noqa: BLE001 — Job Object 경로 불가(_handle 부재 등) → 아래 proc.kill() 폴백 수행
            _warn("Job Object 경로 불가 — kill() 폴백 수행", exc)
        try:
            proc.kill()
        except Exception as exc:  # noqa: BLE001 — Windows 폴백 kill 실패(이미 종료된 프로세스) = 멱등 정리
            _warn("kill() 폴백 실패 (이미 종료된 프로세스)", exc)
        return
    try:
        _os.killpg(_os.getpgid(proc.pid), _signal.SIGKILL)
    except Exception as exc:  # noqa: BLE001 — 그룹 킬 불가(단일 프로세스 등) → proc.kill() 폴백 수행
        _warn("프로세스 그룹 킬 실패 — kill() 폴백 수행", exc)
        try:
            proc.kill()
        except Exception as kill_exc:  # noqa: BLE001 — POSIX 최후 수단 kill 실패(이미 종료) = 멱등 정리
            _warn("kill() 폴백 실패 (이미 종료된 프로세스)", kill_exc)

