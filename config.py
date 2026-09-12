import json
import os
import sys

def resolve_dirs():
    """실행 모드에 따라 소스/설정 Base 경로를 결정. (frozen 여부 기반)"""
    if getattr(sys, "frozen", False):
        base_dir = sys._MEIPASS
        config_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        config_dir = base_dir
    return base_dir, config_dir

def writable_base():
    """쓰기 보장 런타임 캐시 루트 — node/PO 서버/플러그인/ffmpeg 등
    실행 시 수급하는 구성요소의 단일 경로 출처 (pot_provider·components 공용).
    """
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        return os.path.join(local_appdata, "ChzzkTube")
    return os.path.join(os.path.expanduser("~"), ".chzzktube")

_APP_NAME = "ChzzkTube"
_APP_VERSION = "v3.4.0"

BASE_DIR, CONFIG_DIR = resolve_dirs()
CONFIG_FILE = os.path.join(CONFIG_DIR, "dl_config.json")
ICON_PATH = os.path.join(BASE_DIR, "icon.ico")
LOG_DIR = os.path.join(CONFIG_DIR, "logs")

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
        # [외부툴 가변 설정 — client_opts._apply_* 헬퍼가 yt-dlp/streamlink/ffmpeg
        #  옵션으로 배선한다. 새 키 추가 시 (1) 아래 기본값 (2) _apply_* 헬퍼
        #  (3) dialogs.py 체크박스/콤보 3점 세트를 함께 추가할 것.]
        "streamlink_quality": "best",      # streamlink 화질 선택 (best/1080p,720p/…)
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
