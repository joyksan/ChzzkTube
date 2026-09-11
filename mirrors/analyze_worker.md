### analyze_worker.py - URL 분석 백그라운드 스레드
"""yt-dlp URL 분석 전용 워커 (AnalyzeWorker).

- 경량(매니페스트 미열거)/딥(매니페스트 열거) 분석 모드 지원.
- ios→tv 플레이어 클라이언트 순차 폴백 등 추출 우회 로직 보유.
- [계층] L1 Worker Thread — controller에서 직접 생성, log_full 시그널은
  log_console 경유로 View에 전달.
"""
import os
import re
import subprocess
import sys
import time
import urllib.request
import yt_dlp

# [플러그인 기생 차단] 구 getpot bgutil 플러그인(venv pip + %APPDATA% 잔재)이
# 모든 yt-dlp 추출에 자동 로딩되어 자체 deno PO 생성(generate_once.ts — 첫 실행
# 시 TS 컴파일+FFI로 수십 초, 15~20초 타임아웃 반복)을 돌려 분석 스톨과
# "page needs to be reloaded" 실패를 유발했다. 앱의 PO 공급은 자체 Node 서버
# (pot_provider)로 완전 이전했으므로 외부 플러그인을 전면 차단한다.
# 반드시 첫 YoutubeDL 생성 전에 설정 (plugins 로딩은 1회성 lazy init).
yt_dlp.plugins.plugin_dirs.value = []

from PySide6.QtCore import QThread, QTimer, Signal

from chzzk_api import analyze_chzzk_clip_api, analyze_chzzk_vod_api, analyze_chzzk_live_api
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
from client_opts import (
    _apply_client_opts,
    _apply_cookie_opts,
    _apply_ejs_opts,
    _apply_ffmpeg_opts,
    _apply_light_analysis_opts,
    _dedupe_by_label,
)
from yt_logger_bridge import YtLoggerBridge

class AnalyzeWorker(QThread):
    # [v3.3.0] 로그는 raw 버스 단일 경유 — log_full 시그널 폐기.
    result_ready = Signal(dict)
    error_occurred = Signal(str)

    def __init__(self, target_url, cfg, deep=False):
        super().__init__()
        self.target_url = target_url
        self.cfg = cfg
        self.deep = bool(deep)  # True → 매니페스트 열거 포함(포맷 직접 고르기). False → 경량(기본)
        self.logger = YtLoggerBridge()
        # [다운로드 일관성] 분석에서 통과한 클라이언트 기록 — 다운로드가
        # 봇 게이트/PO 토큰 경로를 재진입해 0%에 머무는 것을 방지.
        self.client_used = "auto"
        self._timeout_timer = QTimer()
        self._timeout_timer.setSingleShot(True)
        self._timeout_timer.timeout.connect(self._on_analysis_timeout)

    # [bot-check 회피] auto 클라이언트 실패 시 순차 폴백 — ios는 PO Token
    # 불필요·SABR 무관(720p급), tv는 최후 수단(SABR 360p 리스크).
    _RETRY_CLIENTS = ["ios", "tv"]
    _ANALYSIS_TIMEOUT_MS = 45000

    def _on_analysis_timeout(self):
        """[hang-prevention] 분석 타임아웃 — yt-dlp가 멈췄을 때 스레드 강제 종료 + 에러 보고."""
        import raw_log
        raw_log.raw(
            "analyze",
            f"[analyze] timed out after {self._ANALYSIS_TIMEOUT_MS // 1000}s - yt-dlp hung.",
        )
        self.terminate()
        self.error_occurred.emit(
            f"Analysis timed out after {self._ANALYSIS_TIMEOUT_MS // 1000}s."
        )

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
            # [경량 분석] 매니페스트(hls/dash) 열거 생략 — m3u8 다운로드 스톨
            # 원천 차단. 포맷 직접 고르기(deep=True)일 때만 매니페스트를
            # 열거해 최대 해상도/코덱/비트레이트 정보를 확보한다.
            if not self.deep:
                _apply_light_analysis_opts(ydl_opts)
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
                import raw_log
                raw_log.raw("analyze", f"[client retry] bot check — {client} → {nxt}")
        raise last_err

    def run(self):
        import raw_log
        raw_log.raw("analyze", f"--- [format analysis start] {self.target_url} ---")
        self._timeout_timer.start(self._ANALYSIS_TIMEOUT_MS)

        try:
            try:
                m_clip = re.search(r"chzzk\.naver\.com/clips?/", self.target_url)
                m_vod = re.search(r"chzzk\.naver\.com/video/(\d+)", self.target_url)
                m_live = re.search(r"chzzk\.naver\.com/live/", self.target_url)
                if m_clip or m_vod or m_live:
                    # 콘텐츠 타입 감지
                    content_type = "CLIP" if m_clip else ("LIVE" if m_live else "VOD")
                
                    ch_info = (
                        analyze_chzzk_clip_api(self.target_url)
                        if m_clip
                        else (analyze_chzzk_live_api(self.target_url) if m_live
                              else analyze_chzzk_vod_api(self.target_url))
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
            finally:
                self._timeout_timer.stop()
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

