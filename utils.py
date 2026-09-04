### 유틸리티 및 코어 로직
import os
import platform
import re
import subprocess

# Python 3.11+의 FutureWarning (nested set) 방지를 위해 대괄호 이스케이프 정밀화 적용
ANSI_ESCAPE_RE = re.compile(r"\x1B(?:[@-Z\-_]|\[[0-?]*[ -/]*[@-~])")


def clean_ansi(text):
    return ANSI_ESCAPE_RE.sub("", text)


def get_filename_template(cfg):
    prefix_key = cfg.get("filename_prefix", "none")
    suffix_key = cfg.get("filename_suffix", "id")

    prefix_map = {
        "none": "",
        "uploader": "[%(uploader)s] ",
        "date_dash_uploader": "%(upload_date>%Y-%m-%d)s [%(uploader)s] ",
        "date_compact_uploader": "%(upload_date>%Y%m%d)s [%(uploader)s] ",
        "date_dash": "%(upload_date>%Y-%m-%d)s ",
        "date_compact": "%(upload_date>%Y%m%d)s ",
    }

    suffix_map = {
        "id_res_fps": " [%(id)s] [%(height)sp] [%(fps)sfps]",
        "id_res": " [%(id)s] [%(height)sp]",
        "id": " [%(id)s]",
    }
    prefix = prefix_map.get(prefix_key, "")
    suffix = suffix_map.get(suffix_key, "")
    return f"{prefix}%(title)s{suffix}.%(ext)s"


def _open_windows_explorer(path):
    target = os.path.normpath(os.path.abspath(path))
    if platform.system() == "Windows":
        is_file = os.path.isfile(target)
        folder = target if not is_file else os.path.dirname(target)
        args = (
            ["explorer.exe", "/n,", "/select," + target]
            if is_file
            else [["explorer.exe", "/n,", folder]]
        )
        # Windows Popen fix
        if isinstance(args[0], list):
            args = args[0]
        subprocess.Popen(args, close_fds=True)
    elif platform.system() == "Darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def parse_sec(time_str):
    """시간 문자열(HH:MM:SS, MM:SS, SS)을 초(초 단위 float)로 변환"""
    if not time_str or str(time_str).strip().lower() == "inf":
        return float("inf")
    try:
        parts = [float(p) for p in str(time_str).strip().split(":")]
        multipliers = [3600, 60, 1]
        return sum(p * m for p, m in zip(parts, multipliers[-len(parts) :]))
    except (ValueError, TypeError):
        pass
    return 0.0
