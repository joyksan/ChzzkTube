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
    except Exception:
        return ""
    try:
        os.makedirs(path, exist_ok=True)
    except Exception:
        return ""
    if path not in sys.path:
        sys.path.insert(0, path)
    if clear_caches:
        try:
            import importlib

            importlib.invalidate_caches()
        except Exception:
            pass
    return path