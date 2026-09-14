"""ChzzkTube — 씬 런처 (루트 진입점).

실행 계약:
- `python main.py` (개발) — chzzktube.ui.main_window.main() 호출
- PyInstaller `Analysis(['main.py'])` (번들) — 동일 진입점 자동 추적

앱 본체는 chzzktube/ 패키지에 계층별로 분리되어 있다.
"""

import sys

from chzzktube.ui.main_window import main

if __name__ == "__main__":
    sys.exit(main())