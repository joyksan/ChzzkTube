# 유틸리티 및 코어 로직

import os
import re
import json
import urllib.request
import sqlite3
import shutil
import tempfile
import platform
import subprocess
import datetime

ANSI_ESCAPE_RE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
def clean_ansi(text):
    return ANSI_ESCAPE_RE.sub('', text)

def get_filename_template(cfg):
    prefix_key = cfg.get("filename_prefix", "none")
    suffix_key = cfg.get("filename_suffix", "id")

    prefix_map = {
        "none": "",
        "date_dash_uploader": "%(upload_date>%Y-%m-%d)s [%(uploader)s] ",
        "date_compact_uploader": "%(upload_date>%Y%m%d)s [%(uploader)s] ",
        "date_dash": "%(upload_date>%Y-%m-%d)s ",
        "date_compact": "%(upload_date>%Y%m%d)s "
    }

    suffix_map = {
        "id_res_fps": " [%(id)s] [%(height)sp] [%(fps)sfps]",
        "id_res": " [%(id)s] [%(height)sp]",
        "id": " [%(id)s]"
    }
    prefix = prefix_map.get(prefix_key, "")
    suffix = suffix_map.get(suffix_key, "")
    return f"{prefix}%(title)s{suffix}.%(ext)s"

def get_video_codec_rank(vcodec):
    v = str(vcodec).lower()
    if 'av01' in v or 'av1' in v: return 3
    if 'vp09' in v or 'vp9' in v: return 2
    if 'avc' in v or 'h264' in v or 'h.264' in v: return 1
    return 0

def get_audio_codec_rank(acodec, fid=""):
    a = str(acodec).lower()
    f = str(fid).lower()
    rank = 0
    if 'opus' in a: rank = 30
    elif 'mp4a' in a or 'aac' in a or 'm4a' in a: rank = 20
    elif 'vorbis' in a: rank = 10
    if 'drc' in f: rank -= 1
    return rank

def get_browser_cookies():
    # 도메인별 쿠키를 담기 위해 {domain: {name: value}} 구조로 변경
    cookie_data = {}
    try:
        sys_name = platform.system()
        appdata = os.environ.get("APPDATA", "")
        localappdata = os.environ.get("LOCALAPPDATA", "")
        home = os.path.expanduser("~")
        paths = []
        if sys_name == "Windows":
            paths = [
                os.path.join(appdata, "Mozilla", "Firefox", "Profiles"),
                os.path.join(localappdata, "Google", "Chrome", "User Data", "Default"),
                os.path.join(localappdata, "Microsoft", "Edge", "User Data", "Default")
            ]
        elif sys_name == "Darwin":
            paths = [os.path.join(home, "Library", "Application Support", "Firefox", "Profiles")]

        for p in paths:
            if not os.path.exists(p): continue
            try:
                if "Firefox" in p:
                    for prof in glob.glob(os.path.join(p, "*")):
                        cf = os.path.join(prof, "cookies.sqlite")
                        if os.path.exists(cf):
                            td = tempfile.mkdtemp()
                            tdb = os.path.join(td, "cookies.sqlite")
                            shutil.copy2(cf, tdb)
                            conn = sqlite3.connect(tdb)
                            cur = conn.cursor()
                            # host와 name, value를 함께 조회
                            cur.execute('SELECT host, name, value FROM moz_cookies')
                            for host, n, v in cur.fetchall():
                                if host not in cookie_data: cookie_data[host] = {}
                                cookie_data[host][n] = v
                            conn.close()
                            shutil.rmtree(td, ignore_errors=True)
                else:
                    cf = os.path.join(p, "Network", "Cookies")
                    if not os.path.exists(cf): cf = os.path.join(p, "Cookies")
                    if os.path.exists(cf):
                        td = tempfile.mkdtemp()
                        tdb = os.path.join(td, "Cookies")
                        shutil.copy2(cf, tdb)
                        conn = sqlite3.connect(tdb)
                        cur = conn.cursor()
                        # host_key와 name, value를 함께 조회
                        cur.execute('SELECT host_key, name, value FROM cookies')
                        for host, n, v in cur.fetchall():
                            if host not in cookie_data: cookie_data[host] = {}
                            cookie_data[host][n] = v
                        conn.close()
                        shutil.rmtree(td, ignore_errors=True)
            except Exception:
                continue
    except Exception:
        pass
    return cookie_data

def analyze_chzzk_clip_api(target_url):
    clip_id = target_url.split("/")[-1].split("?")[0]
    cookie_dict = get_browser_cookies()
    cookie_str = "; ".join([f"{k}={v}" for k, v in cookie_dict.items()])
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://chzzk.naver.com/"
    }
    if cookie_str: headers["Cookie"] = cookie_str

    clip_title = clip_id
    created_date = datetime.date.today().strftime("%Y-%m-%d")

    detail_url = f"https://api.chzzk.naver.com/service/v1/clips/{clip_id}/detail"
    try:
        req = urllib.request.Request(detail_url, headers=headers)
        with urllib.request.urlopen(req) as res:
            d_data = json.loads(res.read().decode("utf-8")).get("content", {})
            if d_data.get("clipTitle"): clip_title = d_data.get("clipTitle")
            if d_data.get("createdDate"): created_date = d_data.get("createdDate").split(" ")[0]
    except Exception:
        pass

    play_info_url = f"https://api.chzzk.naver.com/service/v1/play-info/clip/{clip_id}"
    video_formats = []
    try:
        req = urllib.request.Request(play_info_url, headers=headers)
        with urllib.request.urlopen(req) as res:
            data = json.loads(res.read().decode("utf-8"))
            cnt = data.get("content", {})
            in_key, video_id = cnt.get("inKey"), cnt.get("videoId")

        if in_key and video_id:
            rmc_url = f"https://apis.naver.com/rmcnmv/rmcnmv/vod/play/v2.0/{video_id}?key={in_key}"
            req_rmc = urllib.request.Request(rmc_url, headers=headers)
            with urllib.request.urlopen(req_rmc) as rmc_res:
                rmc_data = json.loads(rmc_res.read().decode("utf-8"))
                videos = rmc_data.get("videos", {}).get("list", [])
                for idx, v in enumerate(videos):
                    encoding_opt = v.get("encodingOption", {}).get("name", f"Stream_{idx}")
                    bitrate = v.get("bitrate", {}).get("video", 0) if isinstance(v.get("bitrate"), dict) else v.get("bitrate", 0)
                    bitrate_kbps = int(bitrate / 1000) if bitrate else 0
                    source_url = v.get("source", "")
                    v_codec = v.get("encodingOption", {}).get("vcodec", "H.264")
                    height = 0
                    h_match = re.search(r'(\d+)p', encoding_opt)
                    if h_match: height = int(h_match.group(1))

                    video_formats.append({
                        "id": source_url if source_url else f"chzzk_{idx}",
                        "res": encoding_opt, "height": height, "bitrate": bitrate_kbps,
                        "url": source_url, "vcodec": v_codec
                    })
    except Exception:
        pass

    video_formats.sort(key=lambda x: (x["height"], get_video_codec_rank(x["vcodec"]), x["bitrate"]), reverse=True)
    return {"title": clip_title, "date": created_date, "clip_id": clip_id, "formats": video_formats}

def _open_windows_explorer(path):
    target = os.path.normpath(os.path.abspath(path))
    if platform.system() == "Windows":
        is_file = os.path.isfile(target)
        folder = target if not is_file else os.path.dirname(target)
        args = ["explorer.exe", "/n,", "/select," + target] if is_file else ["explorer.exe", "/n,", folder]
        subprocess.Popen(args, close_fds=True)
    elif platform.system() == "Darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])