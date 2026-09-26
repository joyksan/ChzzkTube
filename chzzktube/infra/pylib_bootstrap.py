"""프로젝트 로컬 pip 오버레이 부트스트랩 (<repo>/.pylib).

인앱 업데이터가 venv(site-packages, uv 소유)를 직접 수정하지 않고
프로젝트별 .pylib/ 디렉터리에만 whl을 해제하도록 한다. 이 모듈을 진입점
최상단에서 import하면 sys.path 선두에 .pylib/을 올려 오버레이 복사가
항상 venv보다 우선한다 (importlib.metadata 포함).

순환 import 금지: stdlib(os/sys) + config(경로 계산)만 의존.
로깅은 진입점 main()에서 1줄 진단으로 처리한다.
"""
import os
import sys

from chzzktube.core.config import pylib_overlay_path


def bootstrap(clear_caches=True):
    """sys.path 선두에 .pylib/ 삽입. 중복 호출 안전. 반환: 실제 삽입된 경로."""
    try:
        path = os.path.abspath(pylib_overlay_path())
    except Exception:  # noqa: BLE001 — 경로 계산 실패 시 부트스트랩 중단
        return ""
    # [v3.12.6] 빈 .pylib 디렉터리 무단 생성(os.makedirs) 전면 차단.
    # yt-dlp 등 의존성이 bin/ 바이너리로 전환되었으므로 오버레이 내용물이 존재할 때만 sys.path에 추가.
    if not os.path.isdir(path):
        return ""

    try:
        entries = os.listdir(path)
    except OSError:
        return ""

    if not entries:
        # 빈 디렉터리 잔재는 안전하게 정리
        try:
            os.rmdir(path)
        except OSError:
            pass
        return ""

    if path not in sys.path:
        sys.path.insert(0, path)
    if clear_caches:
        try:
            import importlib

            importlib.invalidate_caches()
            # .venv 등에서 사전 로드된 구버전 모듈 캐시 제거
            for mod_name in list(sys.modules.keys()):
                if mod_name.startswith("yt_dlp"):
                    del sys.modules[mod_name]
        except Exception:  # noqa: BLE001, S110 — 캐시 무효화 실패는 부트스트랩 반환에 영향 없음
            pass
    return path