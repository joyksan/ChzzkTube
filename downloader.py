# 백그라운드 스레드 및 훅 관리

import os
import time
from PyQt6.QtCore import QThread, pyqtSignal
import yt_dlp
from utils import clean_ansi, get_filename_template, get_video_codec_rank, get_audio_codec_rank, analyze_chzzk_clip_api, parse_sec

def map_res(res, height):
    h = int(height or 0)
    if h == 2160 or "2160" in str(res): return "4K"
    if h == 1440 or "1440" in str(res): return "2K"
    if h == 1080 or "1080" in str(res): return "1080p"
    if h == 720 or "720" in str(res): return "720p"
    if h == 480 or "480" in str(res): return "480p"
    if h == 360 or "360" in str(res): return "360p"
    return str(res)

class YtLoggerBridge:
    def __init__(self, log_full_signal):
        self.log_full_signal = log_full_signal
    def debug(self, msg):
        if msg.strip(): self.log_full_signal.emit(clean_ansi(msg))
    def info(self, msg):
        if msg.strip(): self.log_full_signal.emit(clean_ansi(msg))
    def warning(self, msg):
        if msg.strip(): self.log_full_signal.emit(f"[WARNING] {clean_ansi(msg)}")
    def error(self, msg):
        if msg.strip(): self.log_full_signal.emit(f"[ERROR] {clean_ansi(msg)}")

class AnalyzeWorker(QThread):
    result_ready = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)
    log_concise = pyqtSignal(str, bool, bool)
    log_full = pyqtSignal(str)

    def __init__(self, target_url, cfg):
        super().__init__()
        self.target_url = target_url
        self.cfg = cfg
        self.logger = YtLoggerBridge(self.log_full)

    def run(self):
        self.log_concise.emit(f"[+] 미디어 스트림 분석 중... : {self.target_url}", False, False)
        self.log_full.emit(f"--- [포맷 분석 시작] {self.target_url} ---")
        
        try:
            if "chzzk.naver.com/clips/" in self.target_url:
                ch_info = analyze_chzzk_clip_api(self.target_url)
                v_list = []
                for fmt in ch_info.get("formats", []):
                    v_list.append({
                        "id": fmt["id"], "height": fmt["height"], "vcodec": fmt.get("vcodec", ""),
                        "bitrate": fmt["bitrate"], "tbr": fmt["bitrate"], 
                        "label": f"{map_res(fmt['res'], fmt['height'])} | {fmt['bitrate']}kbps"
                    })
                self.log_concise.emit(f"[✓] 치지직 클립 분석 완료! (제목: {ch_info['title']})", False, False)
                self.result_ready.emit({"info": ch_info, "v_list": v_list, "a_list": [], "is_chzzk": True})
            else:
                ydl_opts = {'logger': self.logger, 'skip_download': True, 'noplaylist': True, 'extract_flat': False}
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(self.target_url, download=False)
                
                if info:
                    if 'entries' in info: info = info['entries'][0]
                    v_list, a_list = [], []
                    for f in info.get('formats', []):
                        fid, ext = f.get('format_id', '?'), f.get('ext', '?')
                        vcodec, acodec = f.get('vcodec', 'none'), f.get('acodec', 'none')
                        tbr, fps, height = int(f.get('tbr') or 0), f.get('fps') or 0, f.get('height') or 0
                        fps_str = f"{fps}fps" if fps else ""
                        res = f.get('resolution') or (f"{height}p" if height else "audio")

                        if vcodec != 'none':
                            v_list.append({"id": fid, "height": height, "fps": fps, "tbr": tbr, "vcodec": vcodec, 
                                           "label": f"{map_res(res, height)} {fps_str} | {tbr}kbps ({ext})"})
                        if acodec != 'none' and vcodec == 'none':
                            abr = int(f.get('abr') or tbr or 0)
                            a_list.append({"id": fid, "abr": abr, "acodec": acodec, "label": f"{abr}kbps | Codec: {acodec} ({ext})"})

                    v_list.sort(key=lambda x: (x["height"], x["fps"], get_video_codec_rank(x["vcodec"]), x["tbr"]), reverse=True)
                    a_list.sort(key=lambda x: (x["abr"], get_audio_codec_rank(x["acodec"], x["id"])), reverse=True)
                    
                    self.log_concise.emit(f"[✓] 스트림 분석 완료! (비디오 {len(v_list)}개, 오디오 {len(a_list)}개)", False, False)
                    self.result_ready.emit({"info": info, "v_list": v_list, "a_list": a_list, "is_chzzk": False})
                else:
                    self.error_occurred.emit("미디어 정보를 가져오지 못했습니다.")
        except Exception as ex:
            ex_str = str(ex).lower()
            if "sign in to confirm your age" in ex_str or "age-gated" in ex_str or "members-only" in ex_str:
                self.error_occurred.emit("연령 제한 또는 멤버십 전용 동영상입니다. 설정에서 쿠키를 불러오세요.")
            else:
                self.error_occurred.emit(f"분석 오류 발생: {str(ex)}")

class DownloadWorker(QThread):
    progress_update = pyqtSignal(float, str)
    status_update = pyqtSignal(int, int, str)
    log_concise = pyqtSignal(str, bool, bool)
    log_full = pyqtSignal(str)
    finished_all = pyqtSignal(bool)

    def __init__(self, targets, cfg, state_dict, v_sel, a_sel):
        super().__init__()
        self.targets = targets
        self.cfg = cfg
        self.state = state_dict
        self.v_sel = v_sel
        self.a_sel = a_sel
        self.logger = YtLoggerBridge(self.log_full)

    def hook(self, d):
        if self.state["canceled"]: raise Exception("사용자에 의해 다운로드가 중지되었습니다.")
        if self.state["skip"]: raise Exception("SKIP_CURRENT_ITEM")
        
        while self.state["paused"]:
            if self.state["canceled"]: raise Exception("사용자에 의해 다운로드가 중지되었습니다.")
            if self.state["skip"]: raise Exception("SKIP_CURRENT_ITEM")
            time.sleep(0.2)

        if d['status'] == 'downloading':
            p_str = clean_ansi(d.get('_percent_str', '0.0%')).strip().replace('%', '')
            try:
                p_val = float(p_str) / 100.0
                self.progress_update.emit(p_val, "")
            except Exception: pass
            s = clean_ansi(d.get('_speed_str', '속도 계산중')).strip()
            e = clean_ansi(d.get('_eta_str', '시간 미정')).strip()
            p_display = clean_ansi(d.get('_percent_str', '0.0%')).strip()
            self.log_concise.emit(f"[다운로드 중] 진행률: {p_display} | 속도: {s} | 남은 시간: {e}", True, False)
        elif d['status'] == 'finished':
            self.log_concise.emit("[+] 다운로드 완료, 후처리 진행 중...", False, False)

    def run(self):
        total = len(self.targets)
        failed_targets = []

        try:
            for idx, url in enumerate(self.targets, 1):
                if self.state["canceled"]: break
                self.state["skip"] = False
                self.status_update.emit(idx - 1, total, url)

                try:
                    if "chzzk.naver.com/clips/" in url:
                        max_res = self.cfg.get("max_video_res", "none")
                        ch_info = analyze_chzzk_clip_api(url)
                        dl_target = self.v_sel if self.v_sel and self.v_sel != "auto" else None
                        selected_fmt = None
                        if ch_info["formats"]:
                            if dl_target:
                                for fmt in ch_info["formats"]:
                                    if fmt["url"] == dl_target: selected_fmt = fmt; break
                            if not selected_fmt:
                                limit = int(max_res) if max_res != "none" else 99999
                                for fmt in ch_info["formats"]:
                                    if fmt["height"] <= limit or limit == 99999:
                                        selected_fmt = fmt; dl_target = fmt["url"]; break
                                if not selected_fmt: dl_target = ch_info["formats"][0]["url"]

                        tmpl = os.path.join(self.cfg['download_path'], get_filename_template(self.cfg))
                        ydl_opts = {'outtmpl': tmpl, 'progress_hooks': [self.hook], 'logger': self.logger, 'ignoreerrors': True}
                        if self.cfg['fast_download']: ydl_opts['concurrent_fragment_downloads'] = 5
                        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                            info = ydl.extract_info(dl_target if dl_target else url, download=True)
                        if info:
                            out = os.path.basename(info.get('_filename', '완료'))
                            self.log_concise.emit(f"[✓] 완료: {out}", False, False)
                        else: failed_targets.append(url)
                    else:
                        browser = self.cfg.get("browser_cookie", "none")
                        ydl_opts = {
                            'outtmpl': os.path.join(self.cfg['download_path'], get_filename_template(self.cfg)),
                            'progress_hooks': [self.hook], 'logger': self.logger, 'ignoreerrors': True,
                            'writethumbnail': True, 'embedmetadata': True,
                            'postprocessors': [{'key': 'FFmpegThumbnailsConvertor', 'format': 'jpg'}, {'key': 'EmbedThumbnail'}]
                        }
                        if browser not in ["none", "auto", "cookie_file"]:
                            ydl_opts['cookiesfrombrowser'] = (browser,)
                        elif browser == "cookie_file" and os.path.exists(self.cfg.get("cookie_file_path", "")):
                            ydl_opts['cookiefile'] = self.cfg["cookie_file_path"]

                        if self.cfg.get("use_cut"):
                            s_time = self.cfg.get("cut_start", "00:00:00")
                            e_time = self.cfg.get("cut_end", "inf")
                            ydl_opts['download_ranges'] = yt_dlp.utils.download_range_func(None, [(parse_sec(s_time), parse_sec(e_time))])
                            ydl_opts['force_keyframes_at_cuts'] = True

                        max_res = self.cfg.get("max_video_res", "none")
                        if self.cfg['audio_only']:
                            ydl_opts['format'] = 'bestaudio/best' if self.a_sel == "auto" else self.a_sel
                            ydl_opts['postprocessors'].insert(0, {'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'})
                        else:
                            if self.v_sel != "auto":
                                ydl_opts['format'] = f'{self.v_sel}+ba/b'
                            else:
                                if max_res != "none": ydl_opts['format'] = f'bestvideo[height<={max_res}]+bestaudio/best'
                                else: ydl_opts['format'] = 'bv*+ba/b'
                            ydl_opts['merge_output_format'] = self.cfg.get('container', 'mkv')

                        if self.cfg['fast_download']: ydl_opts['concurrent_fragment_downloads'] = 5
                        if self.cfg['embed_subtitles'] and not self.cfg['audio_only']:
                            ydl_opts.update({'writesubtitles': True, 'writeautomaticsub': False, 'subtitleslangs': ['ko'], 'subtitlesformat': 'srt/best', 'embedsubtitles': True})
                            ydl_opts['postprocessors'].insert(0, {'key': 'FFmpegSubtitlesConvertor', 'format': 'srt'})

                        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                            info = ydl.extract_info(url, download=True)

                        if info:
                            if 'entries' in info: info = info['entries'][0]
                            out = os.path.basename(info.get('_filename', '완료'))
                            self.log_concise.emit(f"[✓] 완료: {out}", False, False)
                        else: failed_targets.append(url)

                except Exception as item_ex:
                    if "SKIP_CURRENT_ITEM" in str(item_ex):
                        self.log_concise.emit(f"[!] 현재 항목 스킵됨: {url}", False, False)
                        continue
                    if "중지되었습니다" in str(item_ex): raise item_ex
                    
                    ex_msg = str(item_ex).lower()
                    failed_targets.append(url)
                    if "cookie" in ex_msg or "dpapi" in ex_msg or "encryption" in ex_msg or "locked" in ex_msg:
                        self.log_concise.emit(f"[X] 쿠키 접근 실패 (브라우저 보안 제한): 쿠키 불러오기에서 'Cookies.txt' 방식을 사용해주세요.", False, True)
                    else:
                        self.log_concise.emit(f"[X] 오류 발생: {str(item_ex)}", False, True)

            self.status_update.emit(total, total, "완료")
            if failed_targets:
                ff_path = os.path.join(self.cfg['download_path'], "failed_urls.txt")
                with open(ff_path, "w", encoding="utf-8") as f:
                    for u in failed_targets: f.write(u + "\n")
                self.log_concise.emit(f"[!] 실패 항목 {len(failed_targets)}개 'failed_urls.txt' 저장됨", False, True)
            self.log_concise.emit(f"\n[✓] 전체 다운로드 작업 완료!\n", False, False)
            self.finished_all.emit(True)

        except Exception as ex:
            if "중지되었습니다" in str(ex):
                self.log_concise.emit("\n[!] 사용자에 의해 다운로드가 완전히 중지되었습니다.\n", False, True)
            else:
                self.log_concise.emit(f"\n[X] 중단됨: {str(ex)}\n", False, True)
            self.finished_all.emit(False)