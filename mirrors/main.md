"""ChzzkTube — 씬 런처 (루트 진입점).

실행 계약:
- `python main.py` (개발) — chzzktube.ui.main_window.main() 호출
- PyInstaller `Analysis(['main.py'])` (번들) — 동일 진입점 자동 추적

앱 본체는 chzzktube/ 패키지에 계층별로 분리되어 있다.
"""
import sys

# Qt보다 먼저: 프로젝트 로컬 pip 오버레이(.pylib)를 sys.path 선두에.
# (venv는 uv 소유 → 앱이 직접 수정 금지. 상세: pylib_bootstrap.docstring)
import chzzktube.infra.cleanup as _cleanup
import chzzktube.infra.pylib_bootstrap as _pylib_bootstrap

_PYLIB_PATH = _pylib_bootstrap.bootstrap()

# 앱 기동 시 이전 세션 잔재 정리
_cleanup.cleanup_on_startup()

from chzzktube.ui.main_window import main

if __name__ == "__main__":
    sys.exit(main())
