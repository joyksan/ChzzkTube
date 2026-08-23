# downloader.py - 백그라운드 스레드 및 훅 관리

import os
import sys
import time
import re
import glob
import subprocess
import urllib.request
import queue
import threading
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

def format_bytes(size):
    """바이트(Bytes) 수치를 KB, MB, GB 단위로 자동 환산"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} PB"

def cleanup_temp_files(filepath):
    """작업 중단 시 .part, .ytdl, .f*** 스트림 조각 및 임시 썸네일 일괄 삭제"""
    if not filepath: return
    
    try:
        # 파일 경로에서 확장자를 뗀 순수 베이스 파일명 추출
        base_path = os.path.splitext(filepath)[0]
        directory = os.path.dirname(filepath) or "."
        
        # 파일명 기본 패턴 (예: "C:/.../video_title*")
        # .f251.webm.part, .f399.mp4.part, .webp, .jpg 등 모든 연관 임시 파일 검색
        search_pattern = base_path + "*"
        
        for target in glob.glob(search_pattern):
            # 완제품 mp4/mkv/mp3 등을 제외한 임시/후처리 파일 대상 삭제
            if target.endswith(('.part', '.ytdl', '.temp', '_temp.ts', '_temp_thumb.jpg', '.webp', '.jpg', '.png')):
                if os.path.exists(target):
                    try:
                        os.remove(target)
                    except Exception:
                        pass
    except Exception:
        pass

def remux_stream(ts_path, output_path, thumb_path=None):
    """MPEG-TS 스트림을 사용자가 지정한 컨테이너(MP4/MKV)로 초고속 리먹싱"""
    cmd = ['ffmpeg', '-y', '-i', ts_path]
    
    # 썸네일 커버 내장
    if thumb_path and os.path.exists(thumb_path):
        cmd.extend(['-i', thumb_path, '-map', '0', '-map', '1', '-disposition:v:1', 'attached_pic'])
    
    # MP4일 경우에만 빠른 재생용 faststart 인덱스 추가, 그 외(MKV 등)는 무재인코딩 스트림 카피
    if output_path.lower().endswith('.mp4'):
        cmd.extend(['-c', 'copy', '-movflags', '+faststart', output_path])
    else:
        cmd.extend(['-c', 'copy', output_path])
    
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # 임시 수신 파이프 파일 및 썸네일 정리
    if os.path.exists(ts_path):
        try: os.remove(ts_path)
        except Exception: pass
    if thumb_path and os.path.exists(thumb_path):
        try: os.remove(thumb_path)
        except Exception: pass

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
            # 단수형(clip), 복수형(clips) 정규식 감지
            if re.search(r'chzzk\.naver\.com/clips?/', self.target_url):
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
                
                # 브라우저 쿠키 반영
                browser = self.cfg.get("browser_cookie", "none")
                if browser not in ["none", "auto", "cookie_file"]:
                    ydl_opts['cookiesfrombrowser'] = (browser,)
                elif browser == "cookie_file" and os.path.exists(self.cfg.get("cookie_file_path", "")):
                    ydl_opts['cookiefile'] = self.cfg["cookie_file_path"]

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
        self.current_file = None
        self.logger = YtLoggerBridge(self.log_full)

    def log_success_info(self, file_path):
        """다운로드 성공/완료 시 트리 형태 저장 메타정보 출력"""
        if file_path and os.path.exists(file_path):
            abs_path = os.path.abspath(file_path)
            file_size = os.path.getsize(abs_path)
            size_str = format_bytes(file_size)
            
            self.log_concise.emit("[✓] 다운로드 완료!", False, False)
            self.log_concise.emit(f" ├─ 저장 위치: {os.path.dirname(abs_path)}", False, False)
            self.log_concise.emit(f" ├─ 파 일 명: {os.path.basename(abs_path)}", False, False)
            self.log_concise.emit(f" └─ 파일 용량: {size_str}", False, False)
        else:
            self.log_concise.emit(f"[✓] 완료: {os.path.basename(file_path if file_path else '알 수 없는 파일')}", False, False)

    # yt_dlp 훅(hook) 구역 - 유튜브 및 일반 VOD 공통 제어
    def hook(self, d):
        if d.get('filename'):
            self.current_file = d.get('filename')

        # 작업종료 또는 건너뛰기 감지 시 즉시 예외 전파 (자동 cleanup 발동)
        if self.state["canceled"]: raise Exception("CANCELED_BY_USER")
        if self.state["skip"]: raise Exception("SKIP_CURRENT_ITEM")

        # 진행 상태 실시간 로그 전달
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
        # [보강] 재생목록(list=)뿐만 아니라 유튜브 채널(/@, /channel/) URL까지 고속 순차 언롤링
        expanded_targets = []
        for u in self.targets:
            is_multi_source = any(k in u for k in ["list=", "playlist", "/@", "/channel/", "/c/", "/user/"])
            
            if is_multi_source and not ("chzzk.naver.com" in u):
                self.log_concise.emit(f"[+] 재생목록/채널 감지: 항목 목록 고속 파싱 중...", False, False)
                try:
                    ydl_flat_opts = {
                        'extract_flat': 'in_playlist',
                        'skip_download': True,
                        'logger': self.logger
                    }
                    with yt_dlp.YoutubeDL(ydl_flat_opts) as ydl:
                        p_info = ydl.extract_info(u, download=False)
                        if p_info and 'entries' in p_info:
                            for entry in p_info['entries']:
                                if entry and entry.get('url'):
                                    expanded_targets.append(entry['url'])
                                elif entry and entry.get('id'):
                                    expanded_targets.append(f"https://www.youtube.com/watch?v={entry['id']}")
                        else:
                            expanded_targets.append(u)
                except Exception:
                    expanded_targets.append(u)
            else:
                expanded_targets.append(u)

        self.targets = expanded_targets
        total = len(self.targets)
        failed_targets = []

        try:
            for idx, url in enumerate(self.targets, 1):
                if self.state["canceled"]: break
                self.state["skip"] = False
                self.current_file = None
                self.status_update.emit(idx - 1, total, url)

                try:
                    # 1. 치지직 클립 (API 커스텀)
                    if re.search(r'chzzk\.naver\.com/clips?/', url):
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
                        ydl_opts = {
                            'outtmpl': tmpl, 
                            'progress_hooks': [self.hook], 
                            'logger': self.logger, 
                            'ignoreerrors': True,
                            'windowsfilenames': True
                        }
                        if self.cfg['fast_download']: ydl_opts['concurrent_fragment_downloads'] = 5
                        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                            info = ydl.extract_info(dl_target if dl_target else url, download=True)
                        if info:
                            out_path = ydl.prepare_filename(info) if info else None
                            self.log_success_info(out_path)
                        else: failed_targets.append(url)

                    # 2. 치지직 실시간 라이브 (MPEG-TS 백그라운드 수신 -> MP4 리먹싱 안전 파이프라인)
                    elif "chzzk.naver.com/live/" in url:
                        self.log_concise.emit("[+] 치지직 라이브 메타데이터 및 썸네일 파싱 중...", False, False)
                        
                        browser = self.cfg.get("browser_cookie", "none")
                        ydl_opts_info = {
                            'skip_download': True, 'noplaylist': True, 'logger': self.logger,
                            'outtmpl': os.path.join(self.cfg['download_path'], get_filename_template(self.cfg)),
                            'windowsfilenames': True
                        }
                        if browser not in ["none", "auto", "cookie_file"]:
                            ydl_opts_info['cookiesfrombrowser'] = (browser,)
                        elif browser == "cookie_file" and os.path.exists(self.cfg.get("cookie_file_path", "")):
                            ydl_opts_info['cookiefile'] = self.cfg["cookie_file_path"]

                        out_file = None
                        thumb_url = None
                        with yt_dlp.YoutubeDL(ydl_opts_info) as ydl:
                            info_dict = ydl.extract_info(url, download=False)
                            if info_dict:
                                if 'entries' in info_dict: info_dict = info_dict['entries'][0]
                                out_file = ydl.prepare_filename(info_dict)
                                thumb_url = info_dict.get('thumbnail')

                        # [수정] 설정에 지정된 컨테이너 확장자(mkv/mp4) 적용
                        ext = self.cfg.get('container', 'mp4')
                        if ext == 'webm': ext = 'mkv' # 라이브 H.264 코덱 호환성을 위해 webm 선택 시 mkv로 안전 우회

                        if not out_file:
                            out_file = os.path.join(self.cfg['download_path'], f"Chzzk_Live.{ext}")
                        else:
                            # 확장자가 .mp4로 기본 지정되어 들어오는 경우 설정된 확장자로 변경
                            out_file = os.path.splitext(out_file)[0] + f".{ext}"

                        temp_ts_file = out_file.rsplit('.', 1)[0] + "_temp.ts"
                        thumb_file = out_file.rsplit('.', 1)[0] + "_temp_thumb.jpg"
                        
                        if thumb_url:
                            try:
                                urllib.request.urlretrieve(thumb_url, thumb_file)
                            except Exception:
                                thumb_file = None

                        cmd = [sys.executable, "-m", "streamlink", url, "best", "-o", temp_ts_file, "--force", "--hls-live-restart"]
                        self.log_concise.emit("[+] Streamlink 실시간 세션 수신 시작...", False, False)
                        
                        # I/O 블로킹 방지 비동기 큐(Queue) 수신 파이프라인
                        log_queue = queue.Queue()
                        def enqueue_stdout(out, q):
                            for l in iter(out.readline, ''):
                                q.put(l)
                            out.close()

                        proc = subprocess.Popen(
                            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, 
                            universal_newlines=True, encoding='utf-8', errors='replace'
                        )

                        t = threading.Thread(target=enqueue_stdout, args=(proc.stdout, log_queue))
                        t.daemon = True
                        t.start()

                        start_time = time.time()
                        last_calc_time = start_time
                        last_bytes = 0

                        # 비블로킹 생존 감시 루프
                        while proc.poll() is None:
                            # A. 작업 종료 (Cancel) 발생 시: 즉시 프로세스 사살 후 MP4 리먹싱
                            if self.state["canceled"]:
                                proc.kill()
                                proc.wait()
                                time.sleep(0.3)

                                # [보강] 강제 종료(force_discard) 플래그가 켜진 경우 보존 없이 즉시 삭제!
                                if self.state.get("force_discard", False):
                                    if os.path.exists(temp_ts_file): os.remove(temp_ts_file)
                                    if thumb_file and os.path.exists(thumb_file): os.remove(thumb_file)
                                    self.log_concise.emit("[!] 강제 종료되어 라이브 임시 파일이 전량 삭제되었습니다.", False, True)
                                else:
                                    # [저장&종료] 클릭 시 기존처럼 재생 가능한 MP4로 리먹싱 저장
                                    if os.path.exists(temp_ts_file) and os.path.getsize(temp_ts_file) > 0:
                                        self.log_concise.emit("[!] 라이브 녹화 중단됨. 수신된 데이터를 재생 가능한 MP4로 변환 중...", False, False)
                                        remux_ts_to_mp4(temp_ts_file, out_file, thumb_file)

                                        abs_path = os.path.abspath(out_file)
                                        file_size = os.path.getsize(abs_path)
                                        self.log_concise.emit("[✓] 라이브 부분 녹화 저장 완료!", False, False)
                                        self.log_concise.emit(f" ├─ 저장 위치: {os.path.dirname(abs_path)}", False, False)
                                        self.log_concise.emit(f" ├─ 파 일 명: {os.path.basename(abs_path)}", False, False)
                                        self.log_concise.emit(f" └─ 저장 용량: {format_bytes(file_size)}", False, False)
                                    else:
                                        if os.path.exists(temp_ts_file): os.remove(temp_ts_file)
                                        if thumb_file and os.path.exists(thumb_file): os.remove(thumb_file)

                                raise Exception("CANCELED_BY_USER")

                            # B. 1초 주기 실시간 라이브 속도/용량/시간 계산
                            now = time.time()
                            dt = now - last_calc_time
                            if dt >= 1.0:
                                if os.path.exists(temp_ts_file):
                                    cur_bytes = os.path.getsize(temp_ts_file)
                                    speed = (cur_bytes - last_bytes) / dt if dt > 0 else 0
                                    elapsed = int(now - start_time)

                                    time_str = time.strftime('%H:%M:%S', time.gmtime(elapsed))
                                    size_str = format_bytes(cur_bytes)
                                    speed_str = f"{format_bytes(speed)}/s"

                                    self.log_concise.emit(f"[라이브 녹화 중] 시간: {time_str} | 용량: {size_str} | 속도: {speed_str}", True, False)
                                    self.progress_update.emit(-1.0, "")

                                    last_bytes = cur_bytes
                                    last_calc_time = now

                            # C. 상세 로그 비동기 수신 (Non-blocking)
                            try:
                                line = log_queue.get_nowait()
                                if line and line.strip():
                                    self.log_full.emit(f"[Streamlink] {line.strip()}")
                            except queue.Empty:
                                pass

                            time.sleep(0.1)

                        proc.wait()
                        
                        # 정상 완료 시 MP4 리먹싱 후 정리
                        if proc.returncode == 0:
                            remux_ts_to_mp4(temp_ts_file, out_file, thumb_file)
                            self.log_success_info(out_file)
                        else:
                            if not self.state["canceled"]:
                                raise Exception(f"Streamlink 프로세스 비정상 종료 (Code: {proc.returncode})")

                    # 3. 기타 일반 VOD, Shorts, YouTube Live
                    else:
                        browser = self.cfg.get("browser_cookie", "none")
                        is_yt_live = ("youtube.com/live/" in url) or ("watch?v=" in url and "live" in url)

                        ydl_opts = {
                            'outtmpl': os.path.join(self.cfg['download_path'], get_filename_template(self.cfg)),
                            'progress_hooks': [self.hook], 
                            'logger': self.logger, 
                            'ignoreerrors': True,
                            'windowsfilenames': True
                        }

                        if browser not in ["none", "auto", "cookie_file"]:
                            ydl_opts['cookiesfrombrowser'] = (browser,)
                        elif browser == "cookie_file" and os.path.exists(self.cfg.get("cookie_file_path", "")):
                            ydl_opts['cookiefile'] = self.cfg["cookie_file_path"]

                        if is_yt_live:
                            ydl_opts['format'] = 'best'
                            ydl_opts['concurrent_fragment_downloads'] = 1
                        else:
                            ydl_opts.update({
                                'writethumbnail': True,
                                'embedmetadata': True,
                                'postprocessors': [
                                    {'key': 'FFmpegThumbnailsConvertor', 'format': 'jpg'},
                                    {'key': 'EmbedThumbnail'}
                                ]
                            })

                            max_res = self.cfg.get("max_video_res", "none")
                            if self.cfg['audio_only']:
                                ydl_opts['format'] = 'bestaudio/best' if self.a_sel == "auto" else self.a_sel
                                ydl_opts['postprocessors'] = [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}]
                            else:
                                if self.v_sel != "auto":
                                    ydl_opts['format'] = f'{self.v_sel}+ba/b'
                                else:
                                    if max_res != "none": 
                                        ydl_opts['format'] = f'bestvideo[height<={max_res}]+bestaudio/best'
                                    else: 
                                        ydl_opts['format'] = 'bv*+ba/b'
                                ydl_opts['merge_output_format'] = self.cfg.get('container', 'mkv')

                            if self.cfg['fast_download']:
                                ydl_opts['concurrent_fragment_downloads'] = 5

                            if self.cfg['embed_subtitles'] and not self.cfg['audio_only']:
                                ydl_opts.update({'writesubtitles': True, 'writeautomaticsub': False, 'subtitleslangs': ['ko'], 'subtitlesformat': 'srt/best', 'embedsubtitles': True})
                                ydl_opts.setdefault('postprocessors', []).insert(0, {'key': 'FFmpegSubtitlesConvertor', 'format': 'srt'})

                        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                            info = ydl.extract_info(url, download=True)

                        if info:
                            if 'entries' in info: info = info['entries'][0]
                            out_path = ydl.prepare_filename(info) if info else None
                            self.log_success_info(out_path)
                        else: failed_targets.append(url)

                except Exception as item_ex:
                    if "SKIP_CURRENT_ITEM" in str(item_ex):
                        self.log_concise.emit(f"[!] 현재 항목 건너뜀: {url}", False, False)
                        continue
                    
                    # [핵심] 작업 종료 시 다운로드 중이던 영상/음원 및 썸네일 파일 일괄 삭제
                    if "CANCELED_BY_USER" in str(item_ex) or "중지되었습니다" in str(item_ex):
                        raw_file = getattr(self, 'current_file', None)
                        cleanup_temp_files(raw_file)
                        self.log_concise.emit("[!] 작업 종료: 다운로드 중인 임시 파일 및 썸네일 삭제 완료", False, True)
                        raise item_ex
                    
                    ex_msg = str(item_ex).lower()
                    failed_targets.append(url)
                    if "cookie" in ex_msg or "dpapi" in ex_msg or "encryption" in ex_msg or "locked" in ex_msg:
                        self.log_concise.emit(f"[X] 쿠키 접근 실패 (브라우저 보안 제한): 쿠키 불러오기에서 'Cookies.txt' 방식을 사용해주세요.", False, True)
                    else:
                        self.log_concise.emit(f"[X] 오류 발생: {str(item_ex)}", False, True)

            self.status_update.emit(total, total, "완료")

            # 실패 건수에 따른 요약 로그 분기 처리
            if failed_targets:
                ff_path = os.path.join(self.cfg['download_path'], "failed_urls.txt")
                with open(ff_path, "w", encoding="utf-8") as f:
                    for u in failed_targets: 
                        f.write(u + "\n")
                self.log_concise.emit(f"[!] 실패 항목 {len(failed_targets)}개 'failed_urls.txt' 저장됨", False, True)
                
                if len(failed_targets) == total:
                    self.log_concise.emit("\n[X] 모든 다운로드 작업이 실패했습니다.\n", False, True)
                else:
                    success_cnt = total - len(failed_targets)
                    self.log_concise.emit(f"\n[!] 작업 완료 (성공: {success_cnt}개, 실패: {len(failed_targets)}개)\n", False, True)
            else:
                self.log_concise.emit("\n[✓] 전체 다운로드 작업 완료!\n", False, False)

            self.finished_all.emit(len(failed_targets) < total)

        except Exception as ex:
            if "CANCELED_BY_USER" in str(ex) or "중지되었습니다" in str(ex):
                self.log_concise.emit("\n[!] 사용자에 의해 다운로드가 완전히 중지되었습니다.\n", False, True)
            else:
                self.log_concise.emit(f"\n[X] 중단됨: {str(ex)}\n", False, True)
            self.finished_all.emit(False)