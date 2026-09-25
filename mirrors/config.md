import json
import os
import sys


def _repo_root():
    """저장소 루트 — chzzktube/core/config.py 기준 parents[2] 고정."""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def resolve_dirs():
    """실행 모드에 따라 소스/설정 Base 경로를 결정. (frozen 여부 기반)

    Dev: 저장소 루트 고정 — config.py가 chzzktube/core/로 이동해도
    dl_config.json·logs/ 생성 위치는 이전(루트)과 동일하다.
    frozen: sys._MEIPASS + exe 디렉터리 (기존 계약 유지).
    """
    if getattr(sys, "frozen", False):
        base_dir = sys._MEIPASS
        config_dir = os.path.dirname(sys.executable)
    else:
        base_dir = _repo_root()
        config_dir = base_dir
    assert os.path.isdir(base_dir), base_dir
    return base_dir, config_dir


def is_frozen() -> bool:
    """단일 진실: 실행 환경의 frozen 여부.

    호출부는 이 함수를 직접 쓰지 말 것 — 경로 리졸버가 캡슐화한다.
    """
    return getattr(sys, "frozen", False)


def writable_base():
    """쓰기 보장 런타임 캐시 루트 — node/PO 서버/플러그인/ffmpeg 등
    실행 시 수급하는 구성요소의 단일 경로 출처 (pot_provider·components 공용).
    """
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        return os.path.join(local_appdata, "ChzzkTube")
    return os.path.join(os.path.expanduser("~"), ".chzzktube")

_APP_NAME = "ChzzkTube"
_APP_VERSION = "v3.12.0"

BASE_DIR, CONFIG_DIR = resolve_dirs()
CONFIG_FILE = os.path.join(CONFIG_DIR, "dl_config.json")
ICON_PATH = os.path.join(BASE_DIR, "assets", "icon.ico")
FONT_PATH = os.path.join(BASE_DIR, "assets", "CascadiaMono-VariableFont_wght.ttf")
LOG_DIR = os.path.join(CONFIG_DIR, "logs")

def _pylib_root():
    """프로젝트 로컬 pip 오버레이 루트 (<repo>/.pylib).

    [DEPRECATED] 하위 호환용 별칭 — 새 코드는 pylib_overlay_path() 사용.
    호출부는 환경을 분기하지 않는다. pylib_overlay_path()가 SSOT다.
    """
    env = os.environ.get("CHZZKTUBE_PYLIB_DIR")
    if env:
        return os.path.abspath(env)
    # Dev 모드 기본값 (frozen이면 pylib_overlay_path()가 writable_base() 사용)
    return os.path.join(_repo_root(), ".pylib")


def pylib_overlay_path() -> str:
    """Python 오버레이 패키지(.pylib)의 단일 진실 공급원 (SSOT).

    호출부는 환경을 분기하지 않는다.
    우선순위 체인:
    1. 환경변수 강제 오버라이드 — CHZZKTUBE_PYLIB_DIR (CI/테스트/진단)
    2. Frozen 환경: writable_base()/.pylib (%LOCALAPPDATA%/ChzzkTube/.pylib 또는 ~/.chzzktube/.pylib)
    3. Dev 환경: <repo>/.pylib
    """
    env_override = os.environ.get("CHZZKTUBE_PYLIB_DIR")
    if env_override:
        return os.path.abspath(env_override)

    if is_frozen():
        base = writable_base()
    else:
        base = _repo_root()

    return os.path.join(base, ".pylib")


def default_config():
    """기본 설정 딕셔너리 생성. (download_path 는 현재 설정 디렉토리 기준)"""
    return {
        "download_path": CONFIG_DIR,
        "container": "mp4",
        "embed_subtitles": False,
        "audio_only": False,
        "fast_download": True,
        "remove_duplicates": True,
        "auto_open_folder": True,
        "completion_action": "none",
        "play_sound": True,
        "max_video_res": "none",
        "pick_format": False,
        "filename_prefix": "none",
        "filename_suffix": "id",
        "browser_cookie": "auto",
        "cookie_file_path": "",
        "yt_player_client": "auto",
        "update_channel": "stable",
        "auto_update_check": True,
        # [외부툴 가변 설정 — client_opts._apply_* 헬퍼가 yt-dlp/ffmpeg
        #  옵션으로 배선한다. 새 키 추가 시 (1) 아래 기본값 (2) _apply_* 헬퍼
        #  (3) dialogs.py 체크박스/콤보 3점 세트를 함께 추가할 것.]
        "embed_thumbnail": False,          # 커버 썸네일 병합 (ffmpeg -c copy + 썸네일 주입)
        "embed_chapters": True,            # 챕터/메타데이터 병합 (mp4/mkv)
        "subtitle_langs": "all",           # 자막 언어 (all/ko,en/ko 등, embed_subtitles와 연동)
        "concurrent_fragments": 4,         # 병렬 조각 수 (fast_download와 연동)
    }

def load_config():
    """기본 설정에 기존 config 파일을 병합(다운로드 경로 유효 시)."""
    cfg = default_config()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if loaded.get("download_path") and os.path.exists(
                    loaded["download_path"]
                ):
                    cfg.update(loaded)
        except Exception:
            pass
    return cfg

def save_config(cfg):
    """현재 설정을 config 파일로 저장."""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=4)
