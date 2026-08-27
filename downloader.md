### downloader.py - 백그라운드 스레드 및 훅 관리
import collections
import glob
import io
import os
import queue
import re
import subprocess
import sys
import threading
import time
import urllib.request

import yt_dlp
from PyQt6.QtCore import QThread, pyqtSignal

from chzzk_api import analyze_chzzk_clip_api, analyze_chzzk_vod_api
from log_console import format_kv_line, format_tree_item
from media import (
    audio_spec,
    cleanup_temp_files,
    cli_format_desc,
    format_bytes,
    get_audio_codec_rank,
    get_video_codec_rank,
    remux_live_to_container,
    remux_stream,
    short_codec,
)
from utils import clean_ansi, get_filename_template

class SpeedWindow:
    """수신 바이트 샘플의 최근 10초 이동평균 속도 계산기 — 라이브/VOD 공용.

    '네트워크에서 실제 흐른 바이트'만 샘플로 받는다. 디스크 파일 크기는
    ffmpeg/OS 버퍼가 계단식으로 플러시되어 0↔버스트 진동을 만드는 근원이므로
    절대 샘플로 쓰지 않는다 (라이브 릴레이 계수 = 파이프 수신량, VOD 훅
    downloaded_bytes = yt-dlp HTTP 수신량 — 둘 다 실제 네트워크 바이트).
    """

    def __init__(self, window=10.0):
        self._samples = collections.deque()
        self._window = window

    def reset(self):
        self._samples.clear()

    def add(self, t, total_bytes):
        self._samples.append((t, total_bytes))
        cutoff = t - self._window
        while len(self._samples) > 2 and self._samples[0][0] < cutoff:
            self._samples.popleft()

    def speed(self, t):
        """윈도우 양끝 차분의 평균 속도 — 샘플이 부족하면 0."""
        if len(self._samples) < 2:
            return 0
        base_t, base_b = self._samples[0]
        _, cur_b = self._samples[-1]
        span = t - base_t
        return (cur_b - base_b) / span if span > 0 else 0

def _apply_client_opts(opts, cfg):
    """유튜브 player_client 수동 지정을 ydl_opts에 반영 (성인제한 대응).

    쿠키 감지 시 유튜브가 'tv downgraded' 플레이어로 강제 전환해 SABR 스트리밍만
    남겨 360p(itag 18) 하나로 수렴하는 알려진 이슈(#16226)가 있다. 권장 우회는
    쿠키 + 'tv' 클라이언트 명시(yt-dlp.net), 세션 무효화 시 'web_safari'다.
    'auto'면 yt-dlp 기본값을 그대로 쓴다.
    """
    client = str(cfg.get("yt_player_client", "auto") or "auto")
    if client != "auto":
        opts["extractor_args"] = {"youtube": {"player_client": [client]}}
    return opts

def _apply_cookie_opts(opts, cfg):
    """브라우저 쿠키 설정을 ydl_opts에 반영 (4곳 중복 제거 공통 헬퍼)."""
    browser = cfg.get("browser_cookie", "none")
    if browser not in ["none", "auto", "cookie_file"]:
        opts["cookiesfrombrowser"] = (browser,)
    elif browser == "cookie_file" and os.path.exists(cfg.get("cookie_file_path", "")):
        opts["cookiefile"] = cfg["cookie_file_path"]
    return opts

def _dedupe_by_label(formats):
    """표시 라벨이 동일한 포맷은 대표 1개만 남긴다 (라이브 HLS 중복 제거)."""
    seen, unique = set(), []
    for fmt in formats:
        if fmt["label"] not in seen:
            seen.add(fmt["label"])
            unique.append(fmt)
    return unique

class YtLoggerBridge:
    def __init__(self, log_full_signal, log_concise_signal=None):
        self.log_full_signal = log_full_signal
        self.log_concise_signal = log_concise_signal

    def debug(self, msg):
        clean_msg = clean_ansi(msg)
        if "Merging formats into" in clean_msg and self.log_concise_signal:
            self.log_concise_signal.emit(
                " ├─ 비디오와 오디오 스트림 병합(Muxing) 중...", False, False
            )
        if clean_msg.strip():
            self.log_full_signal.emit(clean_msg)
            # [핵심] yt-dlp가 출력하는 이미 다운로드됨 안내 문구 감지!
            if "has already been downloaded" in clean_msg and self.log_concise_signal:
                # 파일명만 깔끔하게 추출해서 간결 로그에 출판
                fname = (
                    clean_msg.replace("[download]", "")
                    .replace("has already been downloaded", "")
                    .strip()
                )
                self.log_concise_signal.emit(
                    format_kv_line(
                        "[!]",
                        "건너뜀",
                        f"이미 존재하는 파일입니다. ({os.path.basename(fname)})",
                    ),
                    False,
                    True,
                )

    def info(self, msg):
        self.debug(msg)

    def warning(self, msg):
        if msg.strip():
            self.log_full_signal.emit(f"[WARNING] {clean_ansi(msg)}")

    def error(self, msg):
        if msg.strip():
            self.log_full_signal.emit(f"[ERROR] {clean_ansi(msg)}")

class AnalyzeWorker(QThread):
    """백그라운드 포맷 분석 스레드.

    UI와의 시그널 계약:
        result_ready(dict)           : 분석 성공 — 스트림/포맷 정보 딕셔너리
        error_occurred(str)          : 분석 실패 — 오류 메시지
        log_concise(str, bool, bool) : (텍스트, is_status, is_error) 간결 로그
        log_full(str)                : yt-dlp 원본 로그 라인
    """

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
        self.log_full.emit(f"--- [포맷 분석 시작] {self.target_url} ---")

        try:
            m_clip = re.search(r"chzzk\.naver\.com/clips?/", self.target_url)
            m_vod = re.search(r"chzzk\.naver\.com/video/(\d+)", self.target_url)
            if m_clip or m_vod:
                ch_info = (
                    analyze_chzzk_clip_api(self.target_url)
                    if m_clip
                    else analyze_chzzk_vod_api(self.target_url)
                )
                v_list = []
                for fmt in ch_info.get("formats", []):
                    v_list.append(
                        {
                            "id": fmt["id"],
                            "height": fmt["height"],
                            "fps": fmt.get("fps", 0),
                            "vcodec": fmt.get("vcodec", ""),
                            "acodec": fmt.get("acodec", ""),
                            "bitrate": fmt["bitrate"],
                            "tbr": fmt["bitrate"],
                            # yt-dlp -F 표와 동일한 CLI 스타일 라벨 (media 단일 출처)
                            "label": cli_format_desc(
                                {
                                    "ext": "mp4",
                                    "height": fmt.get("height"),
                                    "fps": fmt.get("fps") or None,
                                    "tbr": fmt.get("bitrate"),
                                    "protocol": "https",
                                    "vcodec": fmt.get("vcodec"),
                                    "acodec": "",  # 비디오 드롭다운에서 오디오 포맷 병기 버그 방지 (Bug 2)
                                }
                            ),
                        }
                    )
                if not v_list:
                    self.error_occurred.emit(
                        "치지직 스트림 정보를 가져오지 못했습니다 (치지직 로그인 쿠키 확인)"
                    )
                    return
                self.result_ready.emit(
                    {"info": ch_info, "v_list": v_list, "a_list": [], "is_chzzk": True}
                )
            else:
                ydl_opts = {
                    "logger": self.logger,
                    "skip_download": True,
                    "noplaylist": True,
                    "extract_flat": False,
                }

                _apply_cookie_opts(ydl_opts, self.cfg)
                _apply_client_opts(ydl_opts, self.cfg)

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(self.target_url, download=False)

                if info:
                    if "entries" in info:
                        info = info["entries"][0]
                    v_list, a_list = [], []
                    for f in info.get("formats", []):
                        fid, ext = f.get("format_id", "?"), f.get("ext", "?")
                        vcodec, acodec = f.get("vcodec", "none"), f.get(
                            "acodec", "none"
                        )
                        tbr, fps, height = (
                            int(f.get("tbr") or 0),
                            f.get("fps") or 0,
                            f.get("height") or 0,
                        )
                        proto = f.get("protocol") or ""
                        has_v = str(vcodec or "").strip() not in ("none", "", "None")
                        has_a = str(acodec or "").strip() not in (
                            "none",
                            "",
                            "None",
                        )

                        if has_v:
                            v_list.append(
                                {
                                    "id": fid,
                                    "height": height,
                                    "fps": fps,
                                    "tbr": tbr,
                                    "vcodec": vcodec,
                                    "acodec": acodec,
                                    "proto": proto,
                                    "ext": ext,
                                    "label": cli_format_desc(f),
                                }
                            )
                        if has_a and not has_v:
                            a_list.append(
                                {
                                    "id": fid,
                                    "abr": int(f.get("abr") or tbr or 0),
                                    "acodec": acodec,
                                    "ext": ext,
                                    "proto": proto,
                                    "label": cli_format_desc(f),
                                }
                            )

                    v_list.sort(
                        key=lambda x: (
                            x["height"],
                            x["fps"],
                            get_video_codec_rank(x["vcodec"]),
                            x["tbr"],
                        ),
                        reverse=True,
                    )
                    a_list.sort(
                        key=lambda x: (
                            x["abr"],
                            get_audio_codec_rank(x["acodec"], x["id"]),
                        ),
                        reverse=True,
                    )

                    v_list = _dedupe_by_label(v_list)
                    a_list = _dedupe_by_label(a_list)

                    self.result_ready.emit(
                        {
                            "info": info,
                            "v_list": v_list,
                            "a_list": a_list,
                            "is_chzzk": False,
                        }
                    )
                else:
                    self.error_occurred.emit("미디어 정보를 가져오지 못했습니다.")
        except Exception as ex:
            ex_str = str(ex).lower()
            if (
                "sign in to confirm your age" in ex_str
                or "age-restricted" in ex_str
                or "age-gated" in ex_str
                or "members-only" in ex_str
            ):
                self.error_occurred.emit(
                    "연령 제한/멤버십 전용 동영상입니다 — 설정에서 유튜브에 로그인된\n"
                    "브라우저의 쿠키를 지정하세요. (360p만 나오면 브라우저에서 해당\n"
                    "영상을 재생해 세션을 새로 만든 뒤 재시도)"
                )
            else:
                self.error_occurred.emit(f"분석 오류 발생: {str(ex)}")

class DownloadWorker(QThread):
    """백그라운드 다운로드 스레드.

    UI와의 시그널 계약:
        progress_update(float, str)   : (진행률 %, 다운로드 속도 문자열)
        status_update(int, int, str)  : (현재 인덱스, 전체 수, 현재 URL/상태)
        log_concise(str, bool, bool)  : (텍스트, is_status, is_error) 간결 로그
        log_full(str)                 : yt-dlp 원본 로그 라인
        finished_all(int, int)        : (성공 수, 실패 수)

    생성 인자:
        is_live_hint : 분석 단계에서 확인된 라이브 여부 힌트(단일 타겟 전용).
                       유튜브 라이브 전용 파이프라인 라우팅에 사용된다.
    """

    progress_update = pyqtSignal(float, str)
    status_update = pyqtSignal(int, int, str)
    log_concise = pyqtSignal(str, bool, bool)
    log_full = pyqtSignal(str)
    finished_all = pyqtSignal(int, int)

    def __init__(
        self,
        targets,
        cfg,
        state_dict,
        v_sel,
        a_sel,
        is_live_hint=False,
        v_spec=None,
        audio_desc="",
    ):
        super().__init__()
        self.targets = targets
        self.cfg = cfg
        self.state = state_dict
        self.v_sel = v_sel
        self.a_sel = a_sel
        self.audio_desc = str(audio_desc or "")
        self.v_spec = v_spec or {}
        self.is_live_hint = bool(is_live_hint)
        self.current_file = None
        self._meta_logged = False
        self._last_tick_t = 0.0
        self._speed_win = SpeedWindow()
        self._tick_file = None
        self._tick_last = 0
        self.live_partially_saved = False
        self.logger = YtLoggerBridge(self.log_full, self.log_concise)

    def log_success_info(self, file_path):
        """개별 파일 완료 시 계층 구조의 마지막 가지에 맞춰 메타 정보 출력"""
        if file_path and os.path.exists(file_path):
            abs_path = os.path.abspath(file_path)
            file_size = os.path.getsize(abs_path)
            size_str = format_bytes(file_size)

            self.log_concise.emit(
                format_tree_item("저장 완료", os.path.basename(abs_path)),
                False,
                False,
            )
            self.log_concise.emit(
                format_tree_item("저장 위치", os.path.dirname(abs_path)),
                False,
                False,
            )
            self.log_concise.emit(
                format_tree_item("용량", size_str, branch="└─"), False, False
            )
        else:
            self.log_concise.emit(
                format_tree_item(
                    "저장 완료",
                    os.path.basename(file_path) if file_path else "알 수 없는 파일",
                    branch="└─",
                ),
                False,
                False,
            )

    def hook(self, d):
        if d.get("filename"):
            self.current_file = d.get("filename")

        if self.state["canceled"]:
            if d.get("info_dict", {}).get("is_live", False):
                self.log_concise.emit(
                    "[!] 사용자 요청으로 라이브 녹화를 중단합니다.",
                    False,
                    True,
                )
            raise Exception("CANCELED_BY_USER")

        if self.state["skip"]:
            raise Exception("SKIP_CURRENT_ITEM")

        if d["status"] == "downloading":
            info = d.get("info_dict", {})
            if not self._meta_logged:
                self._meta_logged = True
                self._emit_download_header(info)
            now = time.time()
            if now - self._last_tick_t >= 0.5:
                self._last_tick_t = now
                self._emit_progress_tick(d)

    def _emit_download_header(self, info):
        """VOD 다운로드 시작 헤더 — 라이브 헤더와 동일 트리 문법으로 통일.

        포맷 줄은 media.cli_format_desc 단일 출처(yt-dlp -F 표 재현)로 조판.
        통합 포맷(비디오+오디오 내장)은 오디오 코덱이 비디오 줄에 한 번만
        표기되며 별도 '오디오' 가지를 두지 않는다 — 'AAC-LC (mp4a.40.2)'가
        비디오·오디오 양쪽에 중복되던 표기를 정리. 분리 병합 다운로드만
        UI가 전달한 audio_desc(CLI 규격)를 별도 가지로 표기한다.
        """
        vcodec = info.get("vcodec", "none")
        acodec = info.get("acodec", "none")
        has_v = str(vcodec) not in ("none", "")
        has_a = str(acodec) not in ("none", "")
        audio_only = bool(self.cfg.get("audio_only")) or (not has_v and has_a)
        integrated = has_v and has_a
        title = info.get("title") or "제목 없음"

        if audio_only:
            lines = [
                "[+] 오디오 다운로드 시작",
                format_tree_item("제목", title),
                format_tree_item("오디오", cli_format_desc(info)),
            ]
        else:
            lines = [
                "[+] 비디오 다운로드 시작",
                format_tree_item("제목", title),
                format_tree_item("비디오", cli_format_desc(info)),
            ]
            if not integrated:
                a_desc = str(self.audio_desc or "")
                if a_desc:
                    lines.append(format_tree_item("오디오", a_desc))

        duration = info.get("duration")
        size = info.get("filesize") or info.get("filesize_approx")
        if not size and duration and info.get("tbr"):
            size = float(info["tbr"]) * 1000 * float(duration) / 8
        if duration:
            lines.append(
                format_tree_item(
                    "길이", time.strftime("%H:%M:%S", time.gmtime(int(duration)))
                )
            )
        lines.append(
            format_tree_item(
                "예상",
                format_bytes(size) if size else "알 수 없음",
                branch="└─",
            )
        )
        self.log_concise.emit("\n".join(lines), False, False)

    def _emit_progress_tick(self, d):
        """VOD 진행 틱 — 라이브 녹화 틱과 동일 규격의 0.5초 덮어쓰기 상태 줄.

        속도는 yt-dlp가 보고하는 speed 필드를 쓰지 않는다 — 마지막 프래그먼트
        수준의 자체 스무딩이 얹혀 진동한다. 대신 downloaded_bytes(=HTTP 실제
        수신 바이트)를 SpeedWindow(10초 이동평균)에 직접 샘플링해 라이브
        릴레이 계수와 동일한 방식으로 계산한다. 디스크 파일 크기는 어디에도
        쓰지 않는다 — 라이브와 같은 '네트워크에서 흐른 바이트' 표기 통일.
        """
        now = time.time()
        done = d.get("downloaded_bytes") or 0
        total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
        fname = d.get("filename") or ""
        if fname != self._tick_file or done < self._tick_last:
            self._tick_file = fname
            self._speed_win.reset()
        self._tick_last = done
        self._speed_win.add(now, done)

        speed = self._speed_win.speed(now)
        pct = f"{done / total * 100:.1f}%".rjust(6) if total else "--".rjust(6)
        speed_str = f"{format_bytes(speed)}/s".rjust(11)
        size_str = format_bytes(done)
        if total:
            size_str += f"/{format_bytes(total)}"
        self.log_concise.emit(
            f" └─ [{pct.strip()}] {size_str} | {speed_str.strip()}",
            True,
            False,
        )
        self.progress_update.emit((done / total) if total else -1.0, "")

    def _emit_live_final_stats(self, total_bytes, start_time):
        """녹화 종료/중단 시점에 마지막 상태 줄 자리를 평균 속도로 마감한다.

        is_status=False로 확정 출력한다 — 덮어쓰기 대상이 아니라, 진행 중이던
        틱 상태 줄을 '그 자리에서' 대체해 히스토리에 영구 남는 마감 줄이다.
        용량은 디스크 크기가 아니라 릴레이 계수값(실제 수신 바이트)을 쓴다.
        """
        elapsed = int(time.time() - start_time)
        avg_speed = total_bytes / elapsed if elapsed > 0 else 0
        time_str = time.strftime("%H:%M:%S", time.gmtime(elapsed))
        size_str = format_bytes(total_bytes).rjust(9)
        speed_str = f"{format_bytes(avg_speed)}/s".rjust(11)
        self.log_concise.emit(
            f" └─ [녹화완료] {time_str} | {size_str.strip()} | 평균: {speed_str.strip()}",
            False,
            False,
        )

    def _record_live_stream(
        self, cmd, temp_ts_file, out_file, thumb_file, log_tag="Streamlink"
    ):
        """자식 프로세스로 스트림을 수신하며 비블로킹 감시 루프를 돌린다.

        생산자(ffmpeg/streamlink)는 미디어를 **stdout**, 진단 로그를
        **stderr**로 내보낸다(-O / pipe:1). Python이 바이트를 릴레이 기록하며
        직접 계수하므로, 속도·용량이 '파일 크기 차분'이 아니라 실제로 파이프를
        흐른 바이트 기반이 된다. 디스크 플러시/버퍼로 인한 계단식 왜곡(속도가
        0에 뭉칐다가 버스트마다 튀는 현상)이 사라져 틱이 연속적으로 움직인다.
        """
        log_queue = queue.Queue()
        def enqueue_stderr(out, q):
            for l in iter(out.readline, ""):
                q.put(l)
            out.close()

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,   # 미디어 원시 데이터 수신
            stderr=subprocess.PIPE,   # 진단 로그 수신
        )
        stderr_reader = io.TextIOWrapper(
            proc.stderr, encoding="utf-8", errors="replace"
        )
        t = threading.Thread(target=enqueue_stderr, args=(stderr_reader, log_queue))
        t.daemon = True
        t.start()

        recv_total = 0
        recv_lock = threading.Lock()
        pump_done = threading.Event()

        def _relay():
            nonlocal recv_total
            try:
                with open(temp_ts_file, "wb") as dst:
                    while True:
                        chunk = proc.stdout.read(256 * 1024)
                        if not chunk:
                            break
                        dst.write(chunk)
                        dst.flush()
                        with recv_lock:
                            recv_total += len(chunk)
            except Exception:
                pass
            finally:
                try:
                    proc.stdout.close()
                except Exception:
                    pass
                pump_done.set()

        pump_t = threading.Thread(target=_relay, daemon=True)
        pump_t.start()

        def _wait_pump(timeout=10):
            pump_done.wait(timeout)

        start_time = time.time()
        last_calc_time = start_time
        speed_win = SpeedWindow()

        while proc.poll() is None:
            if self.state["canceled"]:
                proc.kill()
                proc.wait()
                time.sleep(0.3)
                _wait_pump(5)

                if self.state.get("force_discard", False):
                    if os.path.exists(temp_ts_file):
                        os.remove(temp_ts_file)
                    if thumb_file and os.path.exists(thumb_file):
                        os.remove(thumb_file)
                    self.log_concise.emit(
                        "[!] 강제 종료되어 라이브 임시 파일이 전량 삭제되었습니다.",
                        False,
                        True,
                    )
                else:
                    with recv_lock:
                        recv_now = recv_total
                    if recv_now > 0:
                        ext = (
                            os.path.splitext(out_file)[1].lstrip(".").upper()
                            or "MP4"
                        )
                        self._emit_live_final_stats(recv_now, start_time)
                        self.log_concise.emit(
                            "[!] 사용자 요청으로 라이브 녹화를 중단합니다.",
                            False,
                            True,
                        )
                        self.log_concise.emit(
                            f"[~] 수신된 데이터를 재생 가능한 {ext}로 병합 중...",
                            False,
                            False,
                        )
                        remux_stream(temp_ts_file, out_file, thumb_file)
                        self.log_concise.emit(
                            "[✓] 라이브 부분 녹화 저장 완료!", False, False
                        )
                        self.log_success_info(out_file)
                        self.live_partially_saved = True
                        return
                    else:
                        if os.path.exists(temp_ts_file):
                            os.remove(temp_ts_file)
                        if thumb_file and os.path.exists(thumb_file):
                            os.remove(thumb_file)
                        raise Exception("CANCELED_BY_USER")

            now = time.time()
            dt = now - last_calc_time
            if dt >= 0.5:
                with recv_lock:
                    cur_bytes = recv_total
                elapsed = int(now - start_time)

                speed_win.add(now, cur_bytes)
                speed = speed_win.speed(now)
                time_str = time.strftime("%H:%M:%S", time.gmtime(elapsed))
                size_str = format_bytes(cur_bytes).rjust(9)
                speed_str = f"{format_bytes(speed)}/s".rjust(11)

                self.log_concise.emit(
                    f" └─ [{time_str}] {size_str.strip()} | {speed_str.strip()}",
                    True,
                    False,
                )
                self.progress_update.emit(-1.0, "")
                last_calc_time = now

            try:
                line = log_queue.get_nowait()
                if line and line.strip():
                    self.log_full.emit(f"[{log_tag}] {line.strip()}")
            except queue.Empty:
                pass

            time.sleep(0.1)

        proc.wait()
        _wait_pump(30)
        self._emit_live_final_stats(recv_total, start_time)
        self.handle_stream_finish(
            is_live=True,
            temp_file=temp_ts_file,
            proc_code=proc.returncode,
        )

    def _emit_live_header(self, info, res_label=""):
        """라이브 녹화 시작 헤더 — 치지직/유튜브 공통 트리 문법."""
        info = info or {}
        title = info.get("title") or "제목 없음"

        muxed = [
            f
            for f in (info.get("formats") or [])
            if f.get("vcodec") not in (None, "none")
            and f.get("acodec") not in (None, "none")
        ]
        fmt = (
            max(muxed, key=lambda f: ((f.get("height") or 0), (f.get("tbr") or 0)))
            if muxed
            else {}
        )
        vcodec = fmt.get("vcodec") or info.get("vcodec")
        acodec = fmt.get("acodec") or info.get("acodec")

        quality_parts = [res_label] if res_label else []
        if str(vcodec) not in ("none", "", "None"):
            quality_parts.append(short_codec(vcodec))
        has_audio = str(acodec) not in ("none", "", "None")
        if has_audio:
            quality_parts.append(audio_spec(acodec))

        lines = ["[+] 라이브 녹화 시작", format_tree_item("제목", title)]
        if quality_parts:
            lines.append(
                format_tree_item("비디오", " | ".join(quality_parts), branch="└─")
            )
        self.log_concise.emit("\n".join(lines), False, False)

    def _emit_chzzk_header(self, ch_info, fmt):
        """치지직 클립/다시보기 헤더 — API 결과와 선택 포맷 기준으로 직접 조판.

        비디오 정보는 오디오 포맷 병기 방지를 위해 acodec을 비운 채 조판하고,
        오디오 스펙을 별도 라인으로 생성하여 출력한다 (Bug 6).
        """
        fmt = fmt or {}
        quality = cli_format_desc(
            {
                "ext": "mp4",
                "height": fmt.get("height"),
                "fps": fmt.get("fps") or None,
                "tbr": fmt.get("bitrate"),
                "protocol": "https",
                "vcodec": fmt.get("vcodec"),
                "acodec": "",  # 비디오 줄에는 오디오 코덱 병기하지 않음
            }
        )
        lines = [
            "[+] 비디오 다운로드 시작",
            format_tree_item("제목", ch_info.get("title") or "제목 없음"),
            format_tree_item("비디오", quality),
        ]
        
        acodec_val = fmt.get("acodec")
        if str(acodec_val or "none") not in ("none", ""):
            short_ac = short_codec(acodec_val)
            audio_val = f"{acodec_val} | {short_ac}" if acodec_val != short_ac else acodec_val
            lines.append(format_tree_item("오디오", audio_val))
            
        if ch_info.get("date"):
            lines.append(format_tree_item("생성 일자", ch_info["date"]))
        duration = ch_info.get("duration")
        if duration:
            try:
                lines.append(
                    format_tree_item(
                        "길이",
                        time.strftime("%H:%M:%S", time.gmtime(int(duration))),
                    )
                )
            except (ValueError, TypeError, OverflowError):
                pass
        
        # 마지막 줄을 말단 가지(└─)로 — 트리 문법 일관성
        if lines:
            last_idx = len(lines) - 1
            if lines[last_idx].startswith(" ├─"):
                lines[last_idx] = " └─" + lines[last_idx][3:]
                
        self.log_concise.emit("\n".join(lines), False, False)

    def _base_info_opts(self):
        """정보 추출용 공통 ydl_opts (파일명 템플릿 + 쿠키 + 유튜브 클라이언트)."""
        opts = {
            "skip_download": True,
            "noplaylist": True,
            "logger": self.logger,
            "outtmpl": os.path.join(
                self.cfg["download_path"], get_filename_template(self.cfg)
            ),
            "windowsfilenames": True,
        }
        _apply_cookie_opts(opts, self.cfg)
        _apply_client_opts(opts, self.cfg)
        return opts

    def _prepare_live_paths(self, out_file, thumb_url=None):
        """라이브 녹화 경로 준비 — 컨테이너 확장자 적용 및 임시 TS/썸네일 생성."""
        ext = self.cfg.get("container", "mp4")
        if ext == "webm":
            ext = "mkv"

        if not out_file:
            out_file = os.path.join(self.cfg["download_path"], f"Chzzk_Live.{ext}")
        else:
            out_file = os.path.splitext(out_file)[0] + f".{ext}"

        temp_ts_file = out_file.rsplit(".", 1)[0] + "_temp.ts"
        thumb_file = out_file.rsplit(".", 1)[0] + "_temp_thumb.jpg"

        if thumb_url:
            try:
                urllib.request.urlretrieve(thumb_url, thumb_file)
            except Exception:
                thumb_file = None

        return temp_ts_file, thumb_file, out_file

    def _download_youtube_live(self, url):
        """유튜브 라이브를 치지직 라이브와 동일한 자체 파이프라인으로 녹화한다.

        비디오 릴레이 계수와 속도 측정을 위해 ffmpeg의 출력을 stdout(pipe:1)으로 보내고,
        _record_live_stream이 파일 기록 및 바이트 계수를 직접 제어하게 수정 (Bug 5).
        """
        self.log_concise.emit("[+] 유튜브 라이브 메타데이터 파싱 중...", False, False)

        out_file = None
        thumb_url = None
        info = None
        with yt_dlp.YoutubeDL(self._base_info_opts()) as ydl:
            info = ydl.extract_info(url, download=False)
            if info and "entries" in info:
                info = info["entries"][0]
            if info:
                out_file = ydl.prepare_filename(info)
                thumb_url = info.get("thumbnail")
        if not info:
            raise Exception("라이브 정보를 가져오지 못했습니다.")

        muxed = [
            f
            for f in (info.get("formats") or [])
            if f.get("vcodec") not in (None, "none")
            and f.get("acodec") not in (None, "none")
            and f.get("url")
        ]
        fmt = None
        if self.v_sel and self.v_sel != "auto":
            fmt = next(
                (f for f in muxed if str(f.get("format_id")) == str(self.v_sel)),
                None,
            )
        if fmt is None:
            max_res = self.cfg.get("max_video_res", "none")
            limit = int(max_res) if max_res != "none" else 99999
            cands = [f for f in muxed if (f.get("height") or 0) <= limit]
            if cands:
                fmt = max(
                    cands,
                    key=lambda f: ((f.get("height") or 0), (f.get("tbr") or 0)),
                )
        if fmt is None:
            raise Exception("녹화 가능한 통합 라이브 포맷을 찾지 못했습니다.")

        height = fmt.get("height") or 0
        res_label = fmt.get("resolution") or (f"{height}p" if height else "자동")
        if fmt.get("tbr"):
            res_label = f"{res_label} | {int(fmt['tbr'])}kbps"
        self._emit_live_header(info, res_label)

        temp_ts_file, thumb_file, out_file = self._prepare_live_paths(
            out_file, thumb_url
        )
        cmd = [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            fmt["url"],
            "-c",
            "copy",
            "-f",
            "mpegts",
            "pipe:1",  # stdout(pipe:1)으로 출력하도록 수정하여 릴레이 계수 활성화
        ]
        self._record_live_stream(
            cmd, temp_ts_file, out_file, thumb_file, log_tag="ffmpeg"
        )

    def handle_stream_finish(self, is_live, temp_file, proc_code=0):
        """라이브 및 VOD 공통 마감 및 예외 처리기"""
        chosen_container = self.cfg.get("container", "mp4")
        if is_live and (self.state["canceled"] or proc_code == 0):
            valid_file = (
                temp_file
                and os.path.exists(temp_file)
                and os.path.getsize(temp_file) > 0
            )
            if valid_file:
                final_path = remux_live_to_container(temp_file, chosen_container)
                self.log_success_info(final_path)

            if self.state["canceled"]:
                if valid_file:
                    self.live_partially_saved = True
                self.log_concise.emit(
                    "[!] 사용자에 의해 라이브 녹화가 중단됐습니다.", False, True
                )
            elif valid_file:
                self.log_concise.emit(
                    "[v] 라이브 방송이 종료되어 녹화를 완료했습니다.", False, False
                )
            else:
                self.log_concise.emit(
                    "[!] 방송이 종료되었으나 감지된 녹화 데이터가 없습니다.",
                    False,
                    True,
                )

        elif is_live:
            err_log = str(getattr(self, "last_error_log", "")).lower()
            if any(
                net_err in err_log
                for net_err in [
                    "timeout",
                    "connection",
                    "network",
                    "unable to open url",
                ]
            ):
                self.log_concise.emit(
                    "[X] 네트워크 연결이 끊어져 녹화가 중단되었습니다.", False, True
                )
            else:
                raise Exception(
                    f"Streamlink 프로세스 비정상 종료 (Code: {proc_code})"
                )

        else:
            if self.state["canceled"]:
                if temp_file and os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                    except Exception:
                        pass
                self.log_concise.emit("[!] 다운로드가 취소되었습니다.", False, True)

    def _expand_targets(self):
        """재생목록/채널 URL을 개별 영상 URL 목록으로 평탄화. (실패 시 원본 유지)"""
        expanded = []
        for u in self.targets:
            is_playlist_only = ("playlist?list=" in u) or (
                ("list=" in u) and ("watch?v=" not in u)
            )
            is_channel_only = any(k in u for k in ["/@", "/channel/", "/c/", "/user/"])

            if (is_playlist_only or is_channel_only) and not ("chzzk.naver.com" in u):
                self.log_concise.emit(
                    f"[+] 재생목록/채널 감지: 항목 목록 고속 파싱 중...", False, False
                )
                try:
                    ydl_flat_opts = {
                        "extract_flat": "in_playlist",
                        "skip_download": True,
                        "logger": self.logger,
                    }
                    with yt_dlp.YoutubeDL(ydl_flat_opts) as ydl:
                        p_info = ydl.extract_info(u, download=False)
                        if p_info and "entries" in p_info:
                            for entry in p_info["entries"]:
                                if entry and entry.get("url"):
                                    expanded.append(entry["url"])
                                elif entry and entry.get("id"):
                                    expanded.append(
                                        f"https://www.youtube.com/watch?v={entry['id']}"
                                    )
                        else:
                            expanded.append(u)
                except Exception:
                    expanded.append(u)
            else:
                expanded.append(u)
        return expanded

    def run(self):
        self.targets = self._expand_targets()
        total = len(self.targets)
        failed_targets = []

        try:
            for idx, url in enumerate(self.targets, 1):
                if self.state["canceled"]:
                    break
                self.state["skip"] = False
                self.current_file = None
                self._meta_logged = False
                self._last_tick_t = 0.0
                self._speed_win.reset()
                self._tick_file = None
                self._tick_last = 0
                self.status_update.emit(idx - 1, total, url)

                self._download_target(url, failed_targets)

            self.status_update.emit(total, total, "완료")

            if not self._finalize(total, failed_targets):
                return

        except Exception as ex:
            if "CANCELED_BY_USER" in str(ex) or "중지되었습니다" in str(ex):
                self.log_concise.emit(
                    "\n[!] 사용자에 의해 다운로드 작업이 중단됐습니다.\n", False, True
                )
            else:
                self.log_concise.emit(
                    f"\n{format_kv_line('[X]', '중단됨', str(ex))}\n", False, True
                )

            fail_len = (
                len(self.targets) if hasattr(self, "targets") and self.targets else 1
            )
            self.finished_all.emit(0, fail_len)

    def _download_target(self, url, failed_targets):
        """단일 타겟(치지직 클립/일반 URL)을 다운로드하고 예외를 자체 처리한다."""
        try:
            m_clip = re.search(r"chzzk\.naver\.com/clips?/", url)
            m_vod = re.search(r"chzzk\.naver\.com/video/(\d+)", url)
            if m_clip or m_vod:
                max_res = self.cfg.get("max_video_res", "none")
                ch_info = (
                    analyze_chzzk_clip_api(url)
                    if m_clip
                    else analyze_chzzk_vod_api(url)
                )
                if not ch_info.get("formats"):
                    self.log_concise.emit(
                        format_kv_line(
                            "[!]",
                            "치지직 오류",
                            "스트림 정보 없음 — 치지직 로그인 쿠키를 확인하세요",
                        ),
                        False,
                        True,
                    )
                    failed_targets.append(
                        (url, "치지직 API에서 스트림 정보를 가져오지 못함")
                    )
                    return
                dl_target = (
                    self.v_sel if self.v_sel and self.v_sel != "auto" else None
                )
                selected_fmt = None
                if ch_info["formats"]:
                    if dl_target:
                        for fmt in ch_info["formats"]:
                            if fmt["url"] == dl_target:
                                selected_fmt = fmt
                                break
                        if not selected_fmt and self.v_spec:
                            for fmt in ch_info["formats"]:
                                if (
                                    fmt.get("height") == self.v_spec.get("height")
                                    and fmt.get("bitrate") == self.v_spec.get("bitrate")
                                    and fmt.get("vcodec") == self.v_spec.get("vcodec")
                                ):
                                    selected_fmt = fmt
                                    dl_target = fmt["url"]
                                    break
                    if not selected_fmt:
                        limit = int(max_res) if max_res != "none" else 99999
                        for fmt in ch_info["formats"]:
                            if fmt["height"] <= limit or limit == 99999:
                                selected_fmt = fmt
                                dl_target = fmt["url"]
                                break
                        if not selected_fmt:
                            selected_fmt = ch_info["formats"][0]
                            dl_target = selected_fmt["url"]

                self._meta_logged = True
                self._emit_chzzk_header(ch_info, selected_fmt)

                tmpl = os.path.join(
                    self.cfg["download_path"], get_filename_template(self.cfg)
                )
                ydl_opts = {
                    "outtmpl": tmpl,
                    "progress_hooks": [self.hook],
                    "logger": self.logger,
                    "ignoreerrors": True,
                    "windowsfilenames": True,
                    "remux_video": self.cfg.get("container", "mp4"),  # mkv / mp4 설정 반영 (Bug 4)
                }
                if self.cfg["fast_download"]:
                    ydl_opts["concurrent_fragment_downloads"] = 5
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(
                        dl_target if dl_target else url, download=False  # Metadata injection (Bug 3)
                    )
                    if info:
                        info["title"] = ch_info.get("title") or info.get("title")
                        info["id"] = ch_info.get("clip_id") or ch_info.get("video_no") or info.get("id")
                        info["uploader"] = "Chzk"
                        if ch_info.get("date"):
                            raw_date = ch_info.get("date", "").replace("-", "")
                            if raw_date:
                                info["upload_date"] = raw_date
                        ydl.process_info(info)

                if info:
                    out_path = ydl.prepare_filename(info) if info else None
                    if out_path:
                        # remux_video가 실행되면 파일 확장자가 설정된 컨테이너에 맞춰지므로 보정
                        chosen_container = self.cfg.get("container", "mp4")
                        base, _ = os.path.splitext(out_path)
                        out_path = f"{base}.{chosen_container}"
                    self.log_success_info(out_path)
                else:
                    failed_targets.append(
                        (url, "다운로드 결과 파일을 확인하지 못함")
                    )

            elif "chzzk.naver.com/live/" in url:
                self.log_concise.emit(
                    "[+] 치지직 라이브 메타데이터 및 썸네일 파싱 중...",
                    False,
                    False,
                )

                out_file = None
                thumb_url = None
                info_dict = None
                with yt_dlp.YoutubeDL(self._base_info_opts()) as ydl:
                    info_dict = ydl.extract_info(url, download=False)
                    if info_dict and "entries" in info_dict:
                        info_dict = info_dict["entries"][0]
                    if info_dict:
                        out_file = ydl.prepare_filename(info_dict)
                        thumb_url = info_dict.get("thumbnail")
                if not info_dict:
                    raise Exception("라이브 정보를 가져오지 못했습니다.")

                res_label = info_dict.get("resolution") or (
                    f"{info_dict.get('height')}p" if info_dict.get("height") else ""
                )
                self._emit_live_header(info_dict, res_label)

                temp_ts_file, thumb_file, out_file = self._prepare_live_paths(
                    out_file, thumb_url
                )
                cmd = [
                    sys.executable,
                    "-m",
                    "streamlink",
                    url,
                    "best",
                    "-O",  # stdout(-O)으로 출력하도록 수정하여 릴레이 계수 및 속도 계측 활성화 (Bug 5)
                    "--force",
                    "--hls-live-restart",
                ]
                self._record_live_stream(
                    cmd, temp_ts_file, out_file, thumb_file, log_tag="Streamlink"
                )

            elif self.is_live_hint or "youtube.com/live/" in url:
                self._download_youtube_live(url)

            else:
                ydl_opts = {
                    "outtmpl": os.path.join(
                        self.cfg["download_path"],
                        get_filename_template(self.cfg),
                    ),
                    "progress_hooks": [self.hook],
                    "logger": self.logger,
                    "ignoreerrors": True,
                    "windowsfilenames": True,
                }
                _apply_cookie_opts(ydl_opts, self.cfg)

                ydl_opts.update(
                    {
                        "writethumbnail": True,
                        "embedmetadata": True,
                        "postprocessors": [
                            {
                                "key": "FFmpegThumbnailsConvertor",
                                "format": "jpg",
                            },
                            {"key": "EmbedThumbnail"},
                        ],
                    }
                )
                _apply_client_opts(ydl_opts, self.cfg)

                max_res = self.cfg.get("max_video_res", "none")
                if self.cfg["audio_only"]:
                    ydl_opts["format"] = (
                        "bestaudio/best" if self.a_sel == "auto" else self.a_sel
                    )
                    ydl_opts["postprocessors"] = [
                        {
                            "key": "FFmpegExtractAudio",
                            "preferredcodec": "mp3",
                            "preferredquality": "192",
                        }
                    ]
                else:
                    if self.v_sel != "auto":
                        ydl_opts["format"] = (
                            self.v_sel
                            if self.a_sel == "integrated"
                            else f"{self.v_sel}+ba/b"
                        )
                    else:
                        if max_res != "none":
                            ydl_opts["format"] = (
                                f"bestvideo[height<={max_res}]+bestaudio/best"
                            )
                        else:
                            ydl_opts["format"] = "bv*+ba/b"
                    ydl_opts["merge_output_format"] = self.cfg.get(
                        "container", "mkv"
                    )

                if self.cfg["fast_download"]:
                    ydl_opts["concurrent_fragment_downloads"] = 5

                if self.cfg["embed_subtitles"] and not self.cfg["audio_only"]:
                    ydl_opts.update(
                        {
                            "writesubtitles": True,
                            "writeautomaticsub": False,
                            "subtitleslangs": ["ko"],
                            "subtitlesformat": "srt/best",
                            "embedsubtitles": True,
                        }
                    )
                    ydl_opts.setdefault("postprocessors", []).insert(
                        0,
                        {
                            "key": "FFmpegSubtitlesConvertor",
                            "format": "srt",
                        },
                    )

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)

                if info:
                    if "entries" in info:
                        info = info["entries"][0]
                    out_path = ydl.prepare_filename(info) if info else None
                    self.log_success_info(out_path)
                else:
                    failed_targets.append(
                        (url, "다운로드 결과 파일을 확인하지 못함")
                    )

        except Exception as item_ex:
            if "SKIP_CURRENT_ITEM" in str(item_ex):
                self.log_concise.emit(
                    format_kv_line("[~]", "건너뜀", url), False, False
                )
                return

            if "CANCELED_BY_USER" in str(item_ex) or "중지되었습니다" in str(
                item_ex
            ):
                raw_file = getattr(self, "current_file", None)
                cleanup_temp_files(raw_file)
                self.log_concise.emit(
                    "[!] 작업 종료: 다운로드 중인 임시 파일 및 썸네일 삭제 완료",
                    False,
                    True,
                )
                raise item_ex

            ex_msg = str(item_ex).lower()
            ex_reason = " ".join(str(item_ex).split())[:70] or "원인 불명"
            failed_targets.append((url, ex_reason))
            if (
                "permission" in ex_msg
                or "winerror 32" in ex_msg
                or "already exists" in ex_msg
            ):
                self.log_concise.emit(
                    format_kv_line(
                        "[X]",
                        "접근 오류",
                        "동일한 파일이 이미 존재하거나 사용 중입니다.",
                    ),
                    False,
                    True,
                )
            elif (
                "cookie" in ex_msg
                or "dpapi" in ex_msg
                or "encryption" in ex_msg
                or "locked" in ex_msg
            ):
                self.log_concise.emit(
                    format_kv_line(
                        "[X]",
                        "쿠키 오류",
                        "접근 실패 (브라우저 보안 제한)"
                        " — Cookies.txt 방식을 사용해주세요.",
                    ),
                    False,
                    True,
                )
            else:
                self.log_concise.emit(
                    format_kv_line("[X]", "오류 발생", str(item_ex)), False, True
                )

    def _finalize(self, total, failed_targets):
        """완료 요약/실패 리포트/finished_all emit. 취소 시 False 반환."""
        success_cnt = total - len(failed_targets)
        self.status_update.emit(total, total, "완료")

        if self.state["canceled"]:
            if getattr(self, "live_partially_saved", False):
                self.live_partially_saved = False
            else:
                self.log_concise.emit(
                    "\n[!] 사용자에 의해 다운로드 작업이 중단됐습니다.\n", False, True
                )
            self.finished_all.emit(success_cnt, len(failed_targets))
            return False

        if failed_targets:
            if total > 1:
                ff_path = os.path.join(self.cfg["download_path"], "failed_urls.txt")
                with open(ff_path, "w", encoding="utf-8") as f:
                    for u, _ in failed_targets:
                        f.write(u + "\n")
                self.log_concise.emit(
                    f"[!] 실패 항목 {len(failed_targets)}개 'failed_urls.txt' 저장됨",
                    False,
                    True,
                )

            if len(failed_targets) == total:
                if total == 1:
                    self.log_concise.emit(
                        "\n[X] 다운로드 작업이 실패했습니다.\n", False, True
                    )
                else:
                    self.log_concise.emit(
                        "\n[X] 모든 다운로드 작업이 실패했습니다.\n", False, True
                    )
            else:
                self.log_concise.emit(
                    f"\n[!] 작업 완료 (성공: {success_cnt}개, 실패: {len(failed_targets)}개)\n",
                    False,
                    True,
                )

            for u, reason in failed_targets:
                self.log_concise.emit(
                    format_tree_item("대상", u, branch="├─"), False, True
                )
                self.log_concise.emit(
                    format_tree_item("실패 사유", reason, branch="└─"), False, True
                )
        else:
            self.log_concise.emit("\n[✓] 다운로드 작업 완료!\n", False, False)

        self.finished_all.emit(success_cnt, len(failed_targets))
        return True
