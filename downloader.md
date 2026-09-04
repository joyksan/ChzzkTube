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
    cli_format_desc,
    format_bytes,
    format_dropdown_label,
    get_audio_codec_rank,
    get_video_codec_rank,
    short_codec,
    codec_detail,
)
from utils import clean_ansi, get_filename_template
import log_console
from dl_platform import detect_content_type
from playlist import normalize_youtube_channel_url
from speed_window import SpeedWindow
from client_opts import _apply_client_opts, _apply_cookie_opts, _apply_ejs_opts, _apply_ffmpeg_opts, _dedupe_by_label
import progress_emitter as _pe
import live_recorder as _lr
import target_downloader as _td
import finalizer as _fin

class YtLoggerBridge:
    def __init__(self, log_full_signal, log_concise_signal=None):
        self.log_full_signal = log_full_signal
        self.log_concise_signal = log_concise_signal

    def debug(self, msg):
        clean_msg = clean_ansi(msg)
        if "Merging formats into" in clean_msg and self.log_concise_signal:
            self.log_concise_signal.emit(
                log_console.format_log_line('MERG', 'RUN', platform='-', spec='-', msg='merging'),
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
                    log_console.emit_event("DL", "OK", "-", f"skip — exists ({os.path.basename(fname)})"),
                    False,
                    False,
                )

    def info(self, msg):
        self.debug(msg)

    def warning(self, msg):
        if msg.strip():
            self.log_full_signal.emit(clean_ansi(msg))

    def error(self, msg):
        if msg.strip():
            self.log_full_signal.emit(clean_ansi(msg))

class AnalyzeWorker(QThread):
    result_ready = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)
    log_full = pyqtSignal(str)

    def __init__(self, target_url, cfg):
        super().__init__()
        self.target_url = target_url
        self.cfg = cfg
        self.logger = YtLoggerBridge(self.log_full)
        # [다운로드 일관성] 분석에서 통과한 클라이언트 기록 — 다운로드가
        # 봇 게이트/PO 토큰 경로를 재진입해 0%에 머무는 것을 방지.
        self.client_used = "auto"

    # [bot-check 회피] auto 클라이언트 실패 시 순차 폴백 — ios는 PO Token
    # 불필요·SABR 무관(720p급), tv는 최후 수단(SABR 360p 리스크).
    _RETRY_CLIENTS = ["ios", "tv"]

    @staticmethod
    def _is_bot_block(ex):
        """YouTube 봇 체크/JS 챌린지 실패 판별 — 클라이언트 회전 대상 여부."""
        s = str(ex).lower()
        return (
            "the page needs to be reloaded" in s
            or "n challenge solving failed" in s
            or "challenge solving failed" in s
        )

    def _extract_youtube(self, url, flat):
        """yt-dlp 추출 — bot-check 실패 시 ios→tv 클라이언트 회전.

        [회전 정책] 사용자가 특정 클라이언트를 지정했으면 그 값 하나만
        시도하고 자동 회전하지 않는다(auto일 때만 ios→tv). 회전 흔적은
        상세 로그(F12)에만 남기고 간결 로그는 조용히 유지한다.
        """
        configured = str(self.cfg.get("yt_player_client", "auto") or "auto")
        base = {
            "logger": self.logger,
            "skip_download": True,
            # [가드] updater.py의 socket.setdefaulttimeout(2) 전역값이 새 소켓에
            # 적용되는 것 대비 — 명시 타임아웃으로 안전하게 오버라이드.
            "socket_timeout": 30,
        }
        if flat:
            base["extract_flat"] = True
        else:
            base["noplaylist"] = True
            base["extract_flat"] = False

        attempts = [configured]
        if configured == "auto":
            attempts += list(self._RETRY_CLIENTS)

        last_err = None
        for idx, client in enumerate(attempts):
            ydl_opts = dict(base)
            _apply_cookie_opts(ydl_opts, self.cfg)
            if client != "auto":
                ydl_opts["extractor_args"] = {
                    "youtube": {"player_client": [client]}
                }
            _apply_ffmpeg_opts(ydl_opts)
            _apply_ejs_opts(ydl_opts)
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                self.client_used = client
                return info
            except Exception as e:
                last_err = e
                if not self._is_bot_block(e):
                    break
                nxt = attempts[idx + 1] if idx + 1 < len(attempts) else "give up"
                self.log_full.emit(
                    f"[client retry] bot check — {client} → {nxt}"
                )
        raise last_err

    def run(self):
        self.log_full.emit(f"--- [format analysis start] {self.target_url} ---")

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
                        "chzzk stream fail (cookie)"
                    )
                    return
                self.result_ready.emit(
                    {"info": ch_info, "v_list": v_list, "a_list": [], "is_chzzk": True}
                )
            else:
                is_playlist = ("playlist?list=" in self.target_url) or ("list=" in self.target_url)
                is_channel = any(k in self.target_url for k in ["/@", "/channel/", "/c/", "/user/"])
                
                if is_playlist or is_channel:
                    info = self._extract_youtube(
                        normalize_youtube_channel_url(self.target_url), flat=True
                    )
                    
                    entries = info.get("entries") or []
                    video_count = len(entries)
                    title = info.get("title") or "playlist/channel"
                    
                    self.result_ready.emit({
                        "is_playlist": True,
                        "title": title,
                        "count": video_count,
                        "v_list": [],
                        "a_list": [],
                    })
                    return

                info = self._extract_youtube(self.target_url, flat=False)

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
                            "yt_client": getattr(self, "client_used", "auto") or "auto",
                        }
                    )
                else:
                    self.error_occurred.emit("media info fail")
        except Exception as ex:
            ex_str = str(ex).lower()
            if (
                "sign in to confirm your age" in ex_str
                or "age-restricted" in ex_str
                or "age-gated" in ex_str
                or "members-only" in ex_str
            ):
                self.error_occurred.emit(
                    "age/membership restricted"
                )
            elif "the page needs to be reloaded" in ex_str or "challenge solving failed" in ex_str:
                # [봇 체크] EJS 솔버 + ios/tv 회전까지 실패하면 남은 수단은
                # 브라우저에서 영상 재생(세션 갱신) — 미니멀 영문 매핑.
                self.error_occurred.emit("bot check — reload browser")
            else:
                self.error_occurred.emit(f"analysis error: {clean_ansi(str(ex))}")

class DownloadWorker(QThread):
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
        yt_client="auto",
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
        # [다운로드 일관성] 분석 단계에서 실증·통과한 클라이언트 (auto면 yt-dlp 기본)
        self.yt_client = str(yt_client or "auto")
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
