##### downloader.py - 백그라운드 스레드 및 훅 관리
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
    format_dropdown_label,
    get_audio_codec_rank,
    get_video_codec_rank,
    remux_live_to_container,
    remux_stream,
    short_codec,
    codec_detail,
)
from utils import clean_ansi, get_filename_template
import log_console
# [모듈 평면화] downloader_helpers/downloader_workers 패키지 → 메인 폴더 직접 import.
from dl_platform import (
    _dl_platform as _dl_platform_impl,
    detect_content_type as _detect_content_type,
)
from playlist import normalize_youtube_channel_url as _normalize_youtube_channel_url
from speed_window import SpeedWindow
from cleanup import safe_cleanup_temp_files as _safe_cleanup_temp_files
from client_opts import (
    _apply_client_opts as _apply_client_opts_impl,
    _apply_cookie_opts as _apply_cookie_opts_impl,
    _dedupe_by_label as _dedupe_by_label_impl,
)
from format_desc import (
    get_unified_video_desc as _get_unified_video_desc,
    get_unified_audio_desc as _get_unified_audio_desc,
)
import progress_emitter as _pe
import live_recorder as _lr
import target_downloader as _td
import finalizer as _fin

def _dl_platform(worker):
    """다운로더 워커에서 플랫폼 문자열 추출 (youtube/chzzk/streamlink)."""
    url = getattr(worker, "target_url", "") or ""
    return _dl_platform_impl(url)

def _dl_spec(worker):
    """다운로더 워커에서 사양 문자열 추출 (해상도·fps)."""
    v = getattr(worker, "v_spec", None) or {}
    h = v.get("height") or 0
    fps = v.get("fps") or 0
    if h:
        return f"{h}p{fps}" if fps else f"{h}p"
    a_desc = getattr(worker, "audio_desc", "") or ""
    if a_desc and ("(" in a_desc or "AAC" in a_desc or "OPUS" in a_desc):
        return a_desc
    return ""

def detect_content_type(url, info=None):
    return _detect_content_type(url, info)


def safe_cleanup_temp_files(filepath):
    return _safe_cleanup_temp_files(filepath)

def normalize_youtube_channel_url(url):
    return _normalize_youtube_channel_url(url)

### [수정사항 3 반영] 비디오 및 오디오 포맷 표기 통일 규격 헬퍼 함수 정의
def get_unified_video_desc(info):
    return _get_unified_video_desc(info)

def get_unified_audio_desc(info):
    return _get_unified_audio_desc(info)

# SpeedWindow은 인스턴스 메서드(add/reset/speed)와 상태(_samples, _window)를 가지므로
# 단순 함수형 위임이 불가능. speed_window.SpeedWindow를 그대로 재노출한다 (위 import 참조).

def _apply_client_opts(opts, cfg):
    return _apply_client_opts_impl(opts, cfg)

def _apply_cookie_opts(opts, cfg):
    return _apply_cookie_opts_impl(opts, cfg)

def _dedupe_by_label(formats):
    return _dedupe_by_label_impl(formats)

class YtLoggerBridge:
    def __init__(self, log_full_signal, log_concise_signal=None):
        self.log_full_signal = log_full_signal
        self.log_concise_signal = log_concise_signal

    def debug(self, msg):
        clean_msg = clean_ansi(msg)
        if "Merging formats into" in clean_msg and self.log_concise_signal:
            self.log_concise_signal.emit(
                log_console.format_log_line('MERG', 'RUN', platform='-', spec='-', msg='비디오와 오디오 스트림 병합 중...'),
                False, False,
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
                # 콘텐츠 타입 감지
                content_type = "CLIP" if m_clip else "VOD"
                
                ch_info = (
                    analyze_chzzk_clip_api(self.target_url)
                    if m_clip
                    else analyze_chzzk_vod_api(self.target_url)
                )
                v_list = []
                a_list = []
                for fmt in ch_info.get("formats", []):
                    vcodec = fmt.get("vcodec", "")
                    acodec = fmt.get("acodec", "")
                    has_v = bool(vcodec)
                    has_a = bool(acodec)
                    base = {
                        "id": fmt["id"],
                        "height": fmt["height"],
                        "fps": fmt.get("fps", 0),
                        "vcodec": vcodec,
                        "acodec": acodec,
                        "bitrate": fmt["bitrate"],
                        "tbr": fmt["bitrate"],
                    }
                    if has_v:
                        v_list.append({
                            **base,
                            "label": format_dropdown_label(
                                {
                                    "ext": "mp4",
                                    "height": fmt.get("height"),
                                    "fps": fmt.get("fps") or None,
                                    "tbr": fmt.get("bitrate"),
                                    "protocol": "https",
                                    "vcodec": vcodec,
                                    "acodec": "",
                                },
                                content_type,
                            ),
                        })
                    elif has_a:
                        a_list.append({
                            **base,
                            "abr": fmt.get("bitrate", 0),
                            "label": format_dropdown_label(
                                {
                                    "ext": "m4a",
                                    "tbr": fmt.get("bitrate"),
                                    "protocol": "https",
                                    "vcodec": "none",
                                    "acodec": acodec,
                                },
                                content_type,
                            ),
                        })
                if not v_list and not a_list:
                    self.error_occurred.emit(
                        "치지직 스트림 정보를 가져오지 못했습니다 (치지직 로그인 쿠키 확인)"
                    )
                    return
                self.result_ready.emit(
                    {"info": ch_info, "v_list": v_list, "a_list": [], "is_chzzk": True}
                )
            else:
                is_playlist = ("playlist?list=" in self.target_url) or ("list=" in self.target_url)
                is_channel = any(k in self.target_url for k in ["/@", "/channel/", "/c/", "/user/"])
                
                if is_playlist or is_channel:
                    ydl_opts = {
                        "logger": self.logger,
                        "extract_flat": True,
                        "skip_download": True,
                    }
                    _apply_cookie_opts(ydl_opts, self.cfg)
                    _apply_client_opts(ydl_opts, self.cfg)
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(normalize_youtube_channel_url(self.target_url), download=False)
                    
                    entries = info.get("entries") or []
                    video_count = len(entries)
                    title = info.get("title") or "재생목록/채널"
                    
                    self.result_ready.emit({
                        "is_playlist": True,
                        "title": title,
                        "count": video_count,
                        "v_list": [],
                        "a_list": [],
                    })
                    return

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
                    
                    # 콘텐츠 타입 감지 (URL + 메타데이터)
                    content_type = detect_content_type(self.target_url, info)
                    
                    v_list, a_list = [], []
                    for f in info.get("formats", []):
                        fid, ext = f.get("format_id", "?"), f.get("ext", "?")
                        vcodec, acodec = f.get("vcodec", "none"), f.get("acodec", "none")
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
                            # 비디오 드롭다운: 비디오 정보만 (오디오 코덱 생략)
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
                                    "label": format_dropdown_label(
                                        {**f, "acodec": ""}, content_type
                                    ),
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
                                    "label": format_dropdown_label(f, content_type),
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
        self.total_count = len(targets)
        self.current_idx = 1
        self.current_url = None

    def log_success_info(self, file_path):
        """개별 파일 완료 시 계층 구조의 마지막 가지에 맞춰 메타 정보 출력 (thin wrapper)"""
        return _pe.log_success_info(self, file_path)

    def hook(self, d):
        """yt-dlp progress_hook 콜백 (thin wrapper)"""
        return _pe.hook(self, d)

    def _emit_download_header(self, info):
        """VOD 다운로드 시작 헤더 (thin wrapper)"""
        return _pe.emit_download_header(self, info)

    def _emit_progress_tick(self, d):
        """진행률 0.5초 tick (thin wrapper)"""
        return _pe.emit_progress_tick(self, d)

    def _emit_live_final_stats(self, total_bytes, start_time):
        """라이브 종료 통계 (thin wrapper)"""
        return _pe.emit_live_final_stats(self, total_bytes, start_time)

    def _record_live_stream(self, cmd, temp_ts_file, out_file, thumb_file, log_tag="Streamlink"):
        """streamlink/ffmpeg 라이브 녹화 (thin wrapper)"""
        return _lr.record_live_stream(self, cmd, temp_ts_file, out_file, thumb_file, log_tag)

    def _emit_live_header(self, info, res_label=""):
        """라이브 녹화 시작 헤더 (thin wrapper)"""
        return _pe.emit_live_header(self, info, res_label)

    def _emit_chzzk_header(self, ch_info, fmt):
        """치지직 헤더 (thin wrapper)"""
        return _pe.emit_chzzk_header(self, ch_info, fmt)

    def _base_info_opts(self):
        """yt-dlp 정보 추출 opts (thin wrapper)"""
        return _pe.base_info_opts(self)

    def _prepare_live_paths(self, out_file, thumb_url):
        """라이브 임시 파일 경로 준비 (thin wrapper)"""
        return _lr.prepare_live_paths(self, out_file, thumb_url)

    def _download_youtube_live(self, url):
        """유튜브 라이브 녹화 (thin wrapper)"""
        return _lr.download_youtube_live(self, url)

    def handle_stream_finish(self, is_live, temp_file, proc_code=0):
        """스트림 종료 후처리 (thin wrapper)"""
        return _lr.handle_stream_finish(self, is_live, temp_file, proc_code)

    def _expand_targets(self):
        """재생목록/채널 URL 평탄화 (thin wrapper)"""
        return _td.expand_targets(self)

    def run(self):
        """DownloadWorker 메인 스레드 (thin wrapper)"""
        self.targets = self._expand_targets()
        self.total_count = len(self.targets)
        failed_targets = []
        success_count = 0

        try:
            for idx, url in enumerate(self.targets, 1):
                self.current_idx = idx
                self.current_url = url
                if self.state["canceled"]:
                    break
                self.state["skip"] = False
                self.current_file = None
                self._meta_logged = False
                self._last_tick_t = 0.0
                self._speed_win.reset()
                self._tick_file = None
                self._tick_last = 0
                self.status_update.emit(idx - 1, self.total_count, url)

                ok = self._download_target(url, failed_targets)
                if ok:
                    success_count += 1

            self._finalize(self.total_count, failed_targets, success_count)

        except Exception as ex:
            if "CANCELED_BY_USER" in str(ex) or "중지되었습니다" in str(ex) or self.state["canceled"]:
                pass
            else:
                # [TUI] 에러 라인 — 컬럼 포맷으로 통일
                self.log_concise.emit(
                    _pe.emit_err(str(ex)), is_status=False, is_error=True
                )

            self._finalize(self.total_count, failed_targets, success_count)

    def _download_target(self, url, failed_targets):
        """개별 URL 다운로드 (thin wrapper)"""
        return _td.download_target(self, url, failed_targets)

    def _finalize(self, total, failed_targets, success_count):
        """완료 요약 (thin wrapper)"""
        return _fin.finalize(self, total, failed_targets, success_count)
