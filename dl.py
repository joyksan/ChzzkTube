import sys, json, urllib.request, glob, os, sqlite3, shutil, tempfile, re, datetime, platform, threading, time, subprocess
import flet as ft
import tkinter as tk
from tkinter import filedialog
import yt_dlp

try:
    import winsound
except ImportError:
    winsound = None

APP_NAME = "ChzzkTube"
APP_VERSION = "v10.9.0"
APP_AUTHOR = "M i o r i n e"

if getattr(sys, 'frozen', False):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

if getattr(sys, 'frozen', False):
    CONFIG_DIR = os.path.dirname(sys.executable)
else:
    CONFIG_DIR = BASE_DIR

CONFIG_FILE = os.path.join(CONFIG_DIR, "dl_config.json")

DEFAULT_CONFIG = {
    "download_path": CONFIG_DIR,
    "container": "mkv",
    "embed_subtitles": True,
    "audio_only": False,
    "fast_download": True,
    "remove_duplicates": True,
    "auto_open_folder": True,
    "auto_shutdown": False,
    "play_sound": True,
    "max_res": "none",
    "filename_preset": "%(upload_date>%Y-%m-%d)s %(title)s [%(id)s].%(ext)s",
    "browser_cookie": "firefox"
}

FILENAME_PRESETS = {
    "%(upload_date>%Y-%m-%d)s %(title)s [%(id)s].%(ext)s": "날짜 제목 [ID]",
    "%(uploader)s - %(title)s.%(ext)s": "채널명 - 제목",
    "%(title)s (%(resolution)s).%(ext)s": "제목 (해상도)",
    "%(title)s [%(id)s].%(ext)s": "제목 [ID]",
    "%(uploader)s [%(upload_date>%Y-%m-%d)s] %(title)s.%(ext)s": "채널 [날짜] 제목",
    "%(title)s.%(ext)s": "제목만",
    "Chzzk_%(id)s.%(ext)s": "ID만"
}

class YtDlpLogger:
    def __init__(self, log_func):
        self.log_func = log_func

    def debug(self, msg):
        if msg.strip(): self.log_func(msg)

    def info(self, msg):
        if msg.strip(): self.log_func(msg)

    def warning(self, msg):
        if msg.strip(): self.log_func(f"[WARNING] {msg}")

    def error(self, msg):
        if msg.strip(): self.log_func(f"[ERROR] {msg}")

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
    cookie_dict = {}
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
                            cur.execute('SELECT name, value FROM moz_cookies WHERE host LIKE "%naver.com"')
                            for n, v in cur.fetchall():
                                if n not in cookie_dict: cookie_dict[n] = v
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
                        cur.execute('SELECT name, value FROM cookies WHERE host_key LIKE "%naver.com"')
                        for n, v in cur.fetchall():
                            if n not in cookie_dict: cookie_dict[n] = v
                        conn.close()
                        shutil.rmtree(td, ignore_errors=True)
            except Exception:
                continue
            if "NID_AUT" in cookie_dict: break
    except Exception:
        pass
    return cookie_dict

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
                        "res": encoding_opt,
                        "height": height,
                        "bitrate": bitrate_kbps,
                        "url": source_url,
                        "vcodec": v_codec
                    })
    except Exception:
        pass

    video_formats.sort(key=lambda x: (x["height"], get_video_codec_rank(x["vcodec"]), x["bitrate"]), reverse=True)

    return {
        "title": clip_title,
        "date": created_date,
        "clip_id": clip_id,
        "formats": video_formats
    }

def download_chzzk_clip_direct(target_url, chosen_stream_url, max_res_val, cfg, my_hook, full_logger):
    ch_info = analyze_chzzk_clip_api(target_url)
    dl_target = chosen_stream_url if chosen_stream_url and chosen_stream_url != "auto" else None
    
    selected_fmt = None
    if ch_info["formats"]:
        if dl_target:
            for fmt in ch_info["formats"]:
                if fmt["url"] == dl_target:
                    selected_fmt = fmt
                    break
        
        if not selected_fmt:
            limit = int(max_res_val) if max_res_val != "none" else 99999
            for fmt in ch_info["formats"]:
                if fmt["height"] <= limit or limit == 99999:
                    selected_fmt = fmt
                    dl_target = fmt["url"]
                    break
            if not selected_fmt:
                selected_fmt = ch_info["formats"][0]
                dl_target = selected_fmt["url"]

    clean_title = re.sub(r'[\\/:*?"<>|]', '_', ch_info["title"])
    clean_title = re.sub(r'^(?:\d{2}|\d{4})[-._]?(?:0[1-9]|1[0-2])[-._]?(?:0[1-9]|[12]\d|3[01])\s*', '', clean_title)
    
    base_name = f"{ch_info['date']} {clean_title} [{ch_info['clip_id']}]" if clean_title else f"{ch_info['date']} [{ch_info['clip_id']}]"
    save_dir = cfg.get("download_path") or BASE_DIR
    custom_filename_tmpl = os.path.join(save_dir, f"{base_name}.%(ext)s")

    ydl_opts = {
        'outtmpl': custom_filename_tmpl,
        'progress_hooks': [my_hook],
        'logger': full_logger,
        'ignoreerrors': True,
        'writethumbnail': True,
        'embedmetadata': True,
        'postprocessors': [
            {'key': 'FFmpegThumbnailsConvertor', 'format': 'jpg'},
            {'key': 'EmbedThumbnail'},
        ]
    }

    if cfg['audio_only']:
        ydl_opts['format'] = 'bestaudio/best'
        ydl_opts['postprocessors'].insert(0, {
            'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'
        })
    else:
        ydl_opts['merge_output_format'] = cfg.get('container', 'mkv')

    if cfg['fast_download']:
        ydl_opts['concurrent_fragment_downloads'] = 5

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(dl_target if dl_target else target_url, download=True)

    if info and selected_fmt:
        info['width'] = info.get('width') or (1920 if '1080' in selected_fmt.get('res', '') else 1280)
        info['height'] = info.get('height') or selected_fmt.get('height', 1080)
        info['vcodec'] = info.get('vcodec') or selected_fmt.get('vcodec', 'H.264')
        info['acodec'] = info.get('acodec') or 'AAC'

    return info

def main(page: ft.Page):
    page.title = f"{APP_NAME} {APP_VERSION}"
    page.vertical_alignment = "start"
    page.horizontal_alignment = "center"
    page.padding = 15
    page.theme_mode = "dark"

    # Flet 0.86+ 최신 window 속성 대응
    page.window.width = 1180
    page.window.height = 800

    icon_path = os.path.abspath(os.path.join(BASE_DIR, "icon.ico"))
    if os.path.exists(icon_path):
        page.window.icon = icon_path

    cfg = DEFAULT_CONFIG.copy()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if loaded.get("download_path") and os.path.exists(loaded["download_path"]):
                    cfg.update(loaded)
        except Exception:
            pass

    def save_cfg():
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=4)

    path_text = ft.Text(value=cfg["download_path"], size=12, italic=True, color="grey")
    
    concise_log_field = ft.TextField(
        multiline=True, read_only=True, expand=True, text_size=12,
        border=ft.InputBorder.NONE, bgcolor="black", color="green",
        value=f"[{APP_NAME} {APP_VERSION}] 준비 완료.\n"
    )

    full_log_field = ft.TextField(
        multiline=True, read_only=True, expand=True, text_size=11,
        border=ft.InputBorder.NONE, bgcolor="black", color="grey500",
        value=f"[{APP_NAME}] 시스템 로그 출력이 활성화되었습니다.\n"
    )

    download_state = {"running": False, "paused": False, "canceled": False, "skip": False}
    extracted_info_data = {"info": None, "v_list": [], "a_list": []}
    analysis_timer = [None]

    batch_progress_bar = ft.ProgressBar(value=0, visible=False, color="blue400", height=6)
    batch_status_text = ft.Text("", size=12, weight="bold", color="blue200", visible=False)

    spinner = ft.ProgressRing(width=20, height=20, stroke_width=2.5, visible=False)

    def log_concise(message, is_status=False, is_error=False):
        val = concise_log_field.value
        if is_status and val.strip():
            lines = val.rstrip().split("\n")
            if lines and lines[-1].startswith("[다운로드 중]"):
                lines[-1] = message
                concise_log_field.value = "\n".join(lines) + "\n"
                page.update()
                return

        concise_log_field.value += message + "\n"
        page.update()

    def log_full(message):
        full_log_field.value += message + "\n"
        page.update()

    yt_logger = YtDlpLogger(log_full)

    def pick_directory_click(e):
        def open_dialog():
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            folder_path = filedialog.askdirectory(initialdir=cfg["download_path"])
            root.destroy()
            if folder_path:
                cfg["download_path"] = os.path.normpath(folder_path)
                path_text.value = cfg["download_path"]
                save_cfg()
                log_concise(f"[+] 저장 경로 변경됨: {cfg['download_path']}")
                page.update()
        threading.Thread(target=open_dialog, daemon=True).start()

    def open_folder_click(e=None):
        path = cfg.get("download_path", BASE_DIR)
        if os.path.exists(path):
            if platform.system() == "Windows":
                subprocess.Popen(f'explorer /select,"{path}"' if os.path.isfile(path) else f'explorer "{path}"')
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])

    def option_changed(e=None):
        cfg["container"] = container_dropdown.value
        cfg["embed_subtitles"] = sub_chk.value
        cfg["audio_only"] = audio_chk.value
        cfg["fast_download"] = fast_chk.value
        cfg["remove_duplicates"] = dedup_chk.value
        cfg["auto_open_folder"] = auto_open_chk.value
        cfg["auto_shutdown"] = auto_shutdown_chk.value
        cfg["play_sound"] = play_sound_chk.value
        cfg["filename_preset"] = tmpl_dropdown.value
        
        cut_start_input.disabled = not use_cut_chk.value or download_state["running"]
        cut_end_input.disabled = not use_cut_chk.value or download_state["running"]

        save_cfg()
        page.update()

    container_dropdown = ft.Dropdown(
        label="포맷 컨테이너", value=cfg.get("container", "mkv"),
        options=[ft.dropdown.Option("mkv"), ft.dropdown.Option("mp4")], width=140, height=40, text_size=12
    )
    container_dropdown.on_change = option_changed

    sub_chk = ft.Checkbox(label="한국어 자막 포함 (SRT 자동 변환 병합)", value=cfg["embed_subtitles"], on_change=option_changed)
    audio_chk = ft.Checkbox(label="음원만 추출 (MP3)", value=cfg["audio_only"], on_change=option_changed)
    fast_chk = ft.Checkbox(label="고속 분할 다운로드 (5스레드 병렬)", value=cfg["fast_download"], on_change=option_changed)
    dedup_chk = ft.Checkbox(label="중복 URL 자동 제거", value=cfg.get("remove_duplicates", True), on_change=option_changed)
    auto_open_chk = ft.Checkbox(label="완료 시 폴더 열기", value=cfg.get("auto_open_folder", True), on_change=option_changed)
    auto_shutdown_chk = ft.Checkbox(label="작업 완료 시 PC 자동 종료", value=cfg.get("auto_shutdown", False), on_change=option_changed)
    play_sound_chk = ft.Checkbox(label="완료 알림음 재생", value=cfg.get("play_sound", True), on_change=option_changed)

    tmpl_dropdown = ft.Dropdown(
        label="파일명 형식 템플릿", width=320, height=40, text_size=11,
        value=cfg.get("filename_preset", "%(upload_date>%Y-%m-%d)s %(title)s [%(id)s].%(ext)s"),
        options=[ft.dropdown.Option(k, v) for k, v in FILENAME_PRESETS.items()]
    )
    tmpl_dropdown.on_change = option_changed

    use_cut_chk = ft.Checkbox(label="구간 추출 (Cut)", value=False, on_change=option_changed)
    cut_start_input = ft.TextField(label="시작 (hh:mm:ss)", hint_text="00:00:00", width=140, height=40, text_size=11, disabled=True)
    cut_end_input = ft.TextField(label="종료 (hh:mm:ss)", hint_text="00:05:00", width=140, height=40, text_size=11, disabled=True)

    video_dropdown = ft.Dropdown(
        label="비디오 스트림 선택", width=420, height=40, text_size=11,
        options=[ft.dropdown.Option("auto", "자동 선택 (최고 품질)")], value="auto"
    )
    audio_dropdown = ft.Dropdown(
        label="오디오 스트림 선택", width=340, height=40, text_size=11,
        options=[ft.dropdown.Option("auto", "자동 선택 (최고 품질)")], value="auto"
    )

    def close_settings(e):
        settings_overlay.visible = False
        page.update()

    def open_settings_dialog(e):
        settings_overlay.visible = True
        page.update()

    # Flet 0.86+ 대응: ft.Border.all(대문자) 사용
    settings_overlay = ft.Container(
        content=ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Text("부가 기능 및 옵션 설정", weight="bold", size=16, color="white"),
                    ft.IconButton(icon=ft.Icons.CLOSE, icon_size=20, on_click=close_settings)
                ], alignment="spaceBetween"),
                ft.Divider(height=10),
                ft.Row([container_dropdown, sub_chk], spacing=15),
                ft.Row([audio_chk, dedup_chk], spacing=15),
                ft.Column([
                    fast_chk,
                    ft.Text("  ※ 네트워크가 불안정하거나 서버 IP 차단/다운로드 튕김 현상 발생 시 해제하세요.", size=11, color="grey500")
                ], spacing=1),
                ft.Row([auto_open_chk, auto_shutdown_chk, play_sound_chk], spacing=15),
                ft.Divider(height=10),
                tmpl_dropdown,
                ft.Divider(height=10),
                ft.Row([use_cut_chk, cut_start_input, cut_end_input], spacing=10, vertical_alignment="center"),
                ft.Row([
                    ft.ElevatedButton("설정 완료", bgcolor="blue700", color="white", on_click=close_settings)
                ], alignment="end")
            ], tight=True, spacing=12),
            bgcolor="grey900",
            padding=20,
            border_radius=12,
            border=ft.Border.all(1, "grey700"),
            width=540
        ),
        alignment=ft.alignment.center,
        bgcolor="black54",
        visible=False,
        expand=True
    )

    settings_btn = ft.ElevatedButton("옵션 설정", icon=ft.Icons.SETTINGS, bgcolor="grey800", color="white", on_click=open_settings_dialog)

    action_btn = ft.ElevatedButton("다운로드 시작", icon=ft.Icons.DOWNLOAD, bgcolor="green700", color="white", disabled=True)
    pause_stop_btn = ft.ElevatedButton("일시중지", icon=ft.Icons.PAUSE, bgcolor="orange800", color="white", disabled=True)
    skip_btn = ft.ElevatedButton("건너뛰기", icon=ft.Icons.SKIP_NEXT, bgcolor="blue800", color="white", disabled=True)

    def run_analyze_task(target_url):
        action_btn.disabled = True
        action_btn.text = "분석 중..."
        spinner.visible = True
        page.update()
        log_concise(f"[+] 미디어 스트림 분석 중... : {target_url}")
        log_full(f"--- [포맷 분석 시작] {target_url} ---")

        try:
            if "chzzk.naver.com/clips/" in target_url:
                log_concise("[+] 치지직 클립 전용 API 엔진 가동...")
                ch_info = analyze_chzzk_clip_api(target_url)
                formats = ch_info.get("formats", [])
                v_list = []
                for fmt in formats:
                    v_list.append({
                        "id": fmt["id"], "height": fmt["height"], "vcodec": fmt.get("vcodec", ""),
                        "bitrate": fmt["bitrate"], "label": f"해상도: {fmt['res']} | 비트레이트: {fmt['bitrate']}kbps"
                    })
                extracted_info_data["v_list"] = v_list
                audio_dropdown.options = [ft.dropdown.Option("auto", "자동 포함 (치지직 통합 스트림)")]
                audio_dropdown.value = "auto"
                log_concise(f"[✓] 치지직 클립 분석 완료! (제목: {ch_info['title']})")
                action_btn.disabled = False
            else:
                browser = cfg.get("browser_cookie", "firefox")
                ydl_opts = {'cookiesfrombrowser': (browser,), 'logger': yt_logger, 'skip_download': True}
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(target_url, download=False)

                if info:
                    if 'entries' in info: info = info['entries'][0]
                    extracted_info_data["info"] = info
                    formats = info.get('formats', [])
                    v_list, a_list = [], []

                    for f_item in formats:
                        fid, ext = f_item.get('format_id', '?'), f_item.get('ext', '?')
                        vcodec, acodec = f_item.get('vcodec', 'none'), f_item.get('acodec', 'none')
                        tbr, fps, height = int(f_item.get('tbr') or 0), f_item.get('fps') or 0, f_item.get('height') or 0
                        fps_str = f"{fps}fps" if fps else ""
                        res = f_item.get('resolution') or (f"{height}p" if height else "audio")

                        if vcodec != 'none':
                            v_list.append({"id": fid, "height": height, "fps": fps, "tbr": tbr, "vcodec": vcodec, "label": f"ID: {fid} | {res} {fps_str} | {tbr}kbps | Codec: {vcodec} ({ext})"})
                        if acodec != 'none' and vcodec == 'none':
                            abr = int(f_item.get('abr') or tbr or 0)
                            a_list.append({"id": fid, "abr": abr, "acodec": acodec, "label": f"ID: {fid} | {abr}kbps | Codec: {acodec} ({ext})"})

                    v_list.sort(key=lambda x: (x["height"], x["fps"], get_video_codec_rank(x["vcodec"]), x["tbr"]), reverse=True)
                    a_list.sort(key=lambda x: (x["abr"], get_audio_codec_rank(x["acodec"], x["id"])), reverse=True)

                    extracted_info_data["v_list"], extracted_info_data["a_list"] = v_list, a_list
                    audio_dropdown.options = [ft.dropdown.Option("auto", "자동 선택 (최고 품질)")] + [ft.dropdown.Option(x["id"], x["label"]) for x in a_list]
                    audio_dropdown.value = "auto"

                    v_opts = [ft.dropdown.Option("auto", "자동 선택 (최고 품질)")] + [ft.dropdown.Option(x["id"], x["label"]) for x in v_list]
                    video_dropdown.options = v_opts
                    video_dropdown.value = "auto"

                    log_concise(f"[✓] 스트림 분석 완료! (비디오 {len(v_list)}개, 오디오 {len(a_list)}개)")
                    action_btn.disabled = False
                else:
                    log_concise("[X] 미디어 정보를 가져오지 못했습니다.", is_error=True)
        except Exception as ex:
            log_concise(f"[X] 분석 오류 발생: {str(ex)}", is_error=True)
        finally:
            action_btn.text = "다운로드 시작"
            if not download_state["running"]:
                spinner.visible = False
            page.update()

    def on_url_changed(e=None):
        if analysis_timer[0] is not None:
            analysis_timer[0].cancel()
        val = url_input.value.strip()
        if not val:
            action_btn.disabled = True
            action_btn.text = "다운로드 시작"
            spinner.visible = False
            page.update()
            return

        first_line = val.splitlines()[0].strip().strip('"').strip("'")
        if first_line and not download_state["running"]:
            analysis_timer[0] = threading.Timer(0.5, run_analyze_task, args=(first_line,))
            analysis_timer[0].start()

    def clear_url_click(e):
        if analysis_timer[0] is not None:
            analysis_timer[0].cancel()
        url_input.value = ""
        action_btn.disabled = True
        action_btn.text = "다운로드 시작"
        spinner.visible = False
        
        concise_log_field.value = f"[{APP_NAME} {APP_VERSION}] 준비 완료.\n"
        full_log_field.value = f"[{APP_NAME}] 시스템 로그 출력이 활성화되었습니다.\n"
        extracted_info_data.update({"info": None, "v_list": [], "a_list": []})
        batch_progress_bar.visible = False
        batch_status_text.visible = False
        page.update()

    def pick_txt_click(e):
        def open_file():
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            file_path = filedialog.askopenfilename(initialdir=cfg["download_path"], filetypes=[("Text Files (*.txt)", "*.txt"), ("All Files (*.*)", "*.*")])
            root.destroy()
            if file_path:
                url_input.value = os.path.normpath(file_path)
                on_url_changed(None)
                page.update()
        threading.Thread(target=open_file, daemon=True).start()

    txt_pick_btn = ft.ElevatedButton(".txt 선택", icon=ft.Icons.FILE_OPEN, on_click=pick_txt_click)

    url_input = ft.TextField(
        label="다운로드 링크 입력 (URL, 재생목록, 또는 TXT 파일 경로)",
        hint_text="주소를 넣으면 즉시 분석이 시작됩니다...",
        border_radius=10, expand=True, multiline=True, min_lines=1, max_lines=3, text_size=12,
        on_change=on_url_changed,
        suffix=ft.IconButton(icon=ft.Icons.CANCEL, icon_size=18, tooltip="주소 지우기", on_click=clear_url_click)
    )

    def reset_ui_state():
        download_state.update({"running": False, "paused": False, "canceled": False, "skip": False})
        action_btn.text = "다운로드 시작"
        action_btn.icon = ft.Icons.DOWNLOAD
        action_btn.bgcolor = "green700"
        action_btn.disabled = not bool(extracted_info_data.get("v_list") or extracted_info_data.get("info"))
        
        pause_stop_btn.text = "일시중지"
        pause_stop_btn.icon = ft.Icons.PAUSE
        pause_stop_btn.bgcolor = "orange800"
        pause_stop_btn.disabled = True
        skip_btn.disabled = True
        
        spinner.visible = False
        batch_progress_bar.visible = False
        batch_status_text.visible = False
        page.update()

    def my_hook(d):
        if download_state["canceled"]: raise Exception("사용자에 의해 다운로드가 중지되었습니다.")
        if download_state["skip"]: raise Exception("SKIP_CURRENT_ITEM")
        while download_state["paused"]:
            if download_state["canceled"]: raise Exception("사용자에 의해 다운로드가 중지되었습니다.")
            if download_state["skip"]: raise Exception("SKIP_CURRENT_ITEM")
            time.sleep(0.2)

        if d['status'] == 'downloading':
            p, s, e = d.get('_percent_str', '0.0%').strip(), d.get('_speed_str', '속도 계산중').strip(), d.get('_eta_str', '시간 미정').strip()
            log_concise(f"[다운로드 중] 진행률: {p} | 속도: {s} | 남은 시간: {e}", is_status=True)
        elif d['status'] == 'finished':
            log_concise("[+] 다운로드 완료, 후처리 진행 중...")

    def run_download_task(target_input):
        task_start_time = time.time()
        spinner.visible = True

        targets = []
        clean_input = target_input.strip().strip('"').strip("'")
        if os.path.isfile(clean_input) and clean_input.lower().endswith('.txt'):
            try:
                with open(clean_input, 'r', encoding='utf-8') as f:
                    for line in f:
                        l = line.strip()
                        if l and not l.startswith('#'):
                            if l.startswith("www."): l = "https://" + l
                            targets.append(l)
                log_concise(f"[+] TXT 파일에서 총 {len(targets)}개 주소 추출완료.")
            except Exception as txt_err:
                log_concise(f"[X] TXT 읽기 실패: {str(txt_err)}", is_error=True)
                reset_ui_state()
                return
        else:
            for l in clean_input.splitlines():
                l = l.strip()
                if l:
                    if l.startswith("www."): l = "https://" + l
                    targets.append(l)

        if dedup_chk.value and targets:
            orig_len = len(targets)
            targets = list(dict.fromkeys(targets))
            if len(targets) < orig_len:
                log_concise(f"[+] 중복 URL {orig_len - len(targets)}개 제거됨 (유효: {len(targets)}개)")

        if not targets:
            log_concise("[X] 다운로드할 유효 주소가 없습니다.", is_error=True)
            reset_ui_state()
            return

        total_count = len(targets)
        batch_progress_bar.visible = True
        batch_status_text.visible = True
        batch_progress_bar.value = 0
        batch_status_text.value = f"전체 진행률: [0/{total_count}] (0%)"
        
        log_concise(f"\n[+] 총 {total_count}개 항목 일괄 다운로드 개시")
        failed_targets = []

        try:
            for idx, url in enumerate(targets, 1):
                if download_state["canceled"]: break
                download_state["skip"] = False

                batch_progress_bar.value = (idx - 1) / total_count
                batch_status_text.value = f"전체 진행률: [{idx-1}/{total_count}] ({int(((idx-1)/total_count)*100)}%) | 처리중: {url[:30]}..."
                page.update()

                try:
                    if "chzzk.naver.com/clips/" in url:
                        info = download_chzzk_clip_direct(url, video_dropdown.value, "none", cfg, my_hook, yt_logger)
                    else:
                        browser = cfg.get("browser_cookie", "firefox")
                        ydl_opts = {
                            'cookiesfrombrowser': (browser,),
                            'outtmpl': os.path.join(cfg['download_path'], tmpl_dropdown.value),
                            'progress_hooks': [my_hook], 'logger': yt_logger,
                            'ignoreerrors': True, 'writethumbnail': True, 'embedmetadata': True,
                            'postprocessors': [{'key': 'FFmpegThumbnailsConvertor', 'format': 'jpg'}, {'key': 'EmbedThumbnail'}]
                        }

                        if use_cut_chk.value:
                            s_time, e_time = cut_start_input.value.strip() or "00:00:00", cut_end_input.value.strip() or "inf"
                            ydl_opts['download_ranges'] = yt_dlp.utils.download_range_func(None, [(yt_dlp.utils.parse_sec(s_time), yt_dlp.utils.parse_sec(e_time))])
                            ydl_opts['force_keyframes_at_cuts'] = True

                        v_sel, a_sel = video_dropdown.value, audio_dropdown.value
                        if cfg['audio_only']:
                            ydl_opts['format'] = 'bestaudio/best' if a_sel == "auto" else a_sel
                            ydl_opts['postprocessors'].insert(0, {'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'})
                        else:
                            ydl_opts['format'] = f'{v_sel}+ba/b' if v_sel != "auto" else 'bv*+ba/b'
                            ydl_opts['merge_output_format'] = cfg.get('container', 'mkv')

                        if cfg['fast_download']: ydl_opts['concurrent_fragment_downloads'] = 5

                        if cfg['embed_subtitles'] and not cfg['audio_only']:
                            ydl_opts.update({'writesubtitles': True, 'writeautomaticsub': False, 'subtitleslangs': ['ko'], 'subtitlesformat': 'srt/best', 'embedsubtitles': True})
                            ydl_opts['postprocessors'].insert(0, {'key': 'FFmpegSubtitlesConvertor', 'format': 'srt'})

                        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                            info = ydl.extract_info(url, download=True)

                    if info:
                        if 'entries' in info: info = info['entries'][0]
                        raw_filename = info.get('_filename') or info.get('filename') or ""
                        out_filename = os.path.basename(raw_filename) if raw_filename else "완료"
                        log_concise(f"[✓] 완료: {out_filename}")
                    else:
                        failed_targets.append(url)
                except Exception as item_ex:
                    if "SKIP_CURRENT_ITEM" in str(item_ex):
                        log_concise(f"[!] 현재 항목 스킵됨: {url}")
                        continue
                    if "중지되었습니다" in str(item_ex): raise item_ex
                    failed_targets.append(url)
                    log_concise(f"[X] 오류 발생: {str(item_ex)}", is_error=True)

            batch_progress_bar.value = 1.0
            batch_status_text.value = f"전체 진행률: [{total_count}/{total_count}] (100%) - 완료"

            if failed_targets:
                failed_file_path = os.path.join(cfg['download_path'], "failed_urls.txt")
                with open(failed_file_path, "w", encoding="utf-8") as ff:
                    for f_url in failed_targets: ff.write(f_url + "\n")
                log_concise(f"[!] 실패 항목 {len(failed_targets)}개 'failed_urls.txt' 저장됨", is_error=True)

            log_concise(f"\n[✓] 전체 다운로드 작업 완료!\n")
            if play_sound_chk.value and winsound:
                try: winsound.MessageBeep(winsound.MB_ICONASTERISK)
                except Exception: pass
            if auto_open_chk.value: open_folder_click()
            if auto_shutdown_chk.value and platform.system() == "Windows": os.system("shutdown -s -t 60")
        except Exception as ex:
            log_concise(f"\n[X] 중단됨: {str(ex)}\n", is_error=True)
        finally:
            reset_ui_state()

    def action_btn_click(e):
        val = url_input.value.strip()
        if not val and not download_state["running"]: return

        if not download_state["running"]:
            download_state.update({"running": True, "paused": False, "canceled": False, "skip": False})
            action_btn.disabled = True
            pause_stop_btn.disabled = False
            pause_stop_btn.text, pause_stop_btn.icon, pause_stop_btn.bgcolor = "일시중지", ft.Icons.PAUSE, "orange800"
            skip_btn.disabled = True
            page.update()
            threading.Thread(target=run_download_task, args=(val,), daemon=True).start()
        elif download_state["paused"]:
            download_state["paused"] = False
            action_btn.disabled = True
            pause_stop_btn.text, pause_stop_btn.icon, pause_stop_btn.bgcolor = "일시중지", ft.Icons.PAUSE, "orange800"
            skip_btn.disabled = True
            log_concise("[+] 다운로드 재개...", is_status=True)
            page.update()

    def pause_stop_click(e):
        if not download_state["running"]: return
        if not download_state["paused"]:
            download_state["paused"] = True
            pause_stop_btn.text, pause_stop_btn.icon, pause_stop_btn.bgcolor = "중지", ft.Icons.STOP, "red700"
            action_btn.disabled = False
            action_btn.text = "다시 시작"
            skip_btn.disabled = False
            log_concise("[!] 일시중지됨. (스킵 또는 완전 중지 가능)", is_status=True)
        else:
            download_state["canceled"] = True
            download_state["paused"] = False
            reset_ui_state()
        page.update()

    def skip_click(e):
        if download_state["running"] and download_state["paused"]:
            download_state.update({"skip": True, "paused": False})
            skip_btn.disabled = True
            action_btn.disabled = True
            pause_stop_btn.text, pause_stop_btn.icon, pause_stop_btn.bgcolor = "일시중지", ft.Icons.PAUSE, "orange800"
            log_concise("[!] 다음 항목으로 스킵합니다...", is_status=True)
            page.update()

    action_btn.on_click = action_btn_click
    pause_stop_btn.on_click = pause_stop_click
    skip_btn.on_click = skip_click

    page.add(
        ft.Stack([
            ft.Column([
                ft.Container(
                    content=ft.Row([
                        ft.Column([
                            ft.Text("저장 위치", weight="bold", size=13),
                            path_text
                        ], expand=True, spacing=2),
                        ft.Row([
                            settings_btn,
                            ft.ElevatedButton("폴더 열기", icon=ft.Icons.FOLDER, on_click=open_folder_click),
                            ft.ElevatedButton("폴더 변경", icon=ft.Icons.FOLDER_OPEN, on_click=pick_directory_click)
                        ], spacing=8)
                    ], alignment="spaceBetween"),
                    padding=12, border_radius=10, bgcolor="grey900"
                ),
                
                ft.Column([batch_status_text, batch_progress_bar], spacing=3),

                ft.Row([
                    txt_pick_btn,
                    url_input,
                    spinner,
                    action_btn,
                    pause_stop_btn,
                    skip_btn
                ], alignment="spaceBetween", spacing=8),
                
                ft.Container(
                    content=ft.Row([video_dropdown, audio_dropdown], alignment="start", spacing=12),
                    padding=10, border_radius=8, bgcolor="grey900"
                ),

                ft.Row([
                    ft.Container(
                        content=ft.Column([
                            ft.Text("간결 로그", weight="bold", size=12, color="grey"),
                            ft.Container(content=concise_log_field, padding=10, bgcolor="black", border_radius=8, expand=True)
                        ]),
                        padding=10, border_radius=10, bgcolor="grey900", expand=True
                    ),
                    ft.Container(
                        content=ft.Column([
                            ft.Text("전체 상세 로그", weight="bold", size=12, color="grey"),
                            ft.Container(content=full_log_field, padding=10, bgcolor="black", border_radius=8, expand=True)
                        ]),
                        padding=10, border_radius=10, bgcolor="grey900", expand=True
                    )
                ], expand=True, spacing=12)
            ], expand=True, spacing=12),
            settings_overlay
        ], expand=True)
    )

if __name__ == "__main__":
    ft.app(target=main)