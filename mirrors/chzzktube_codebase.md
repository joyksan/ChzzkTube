# ChzzkTube Project Full Codebase


## File: analyze_worker.py

```python
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


```

## File: bump_version.py

```python
### bump_version.py
import re
import sys

FILE_PATH = "config.py"
try:
    with open(FILE_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    # 큰따옴표/작은따옴표 및 한글/특수문자 괄호 조합까지 모두 허용하는 정규식
    pattern = r'(_APP_VERSION\s*=\s*["\']v)(\d+)\.(\d+)\.(\d+)(.*?["\'])'

    def bump_patch(match):
        prefix = match.group(1)         # _APP_VERSION = "v
        major = match.group(2)          # 3
        minor = match.group(3)          # 1
        patch = int(match.group(4)) + 1 # 0 -> 1
        suffix = match.group(5)         
        
        new_ver = f"{prefix}{major}.{minor}.{patch}{suffix}"
        print(f"[Labmem 004] Version Bump: {match.group(0)} -> {new_ver}")
        return new_ver

    updated_content, count = re.subn(pattern, bump_patch, content)

    if count > 0:
        with open(FILE_PATH, "w", encoding="utf-8") as f:
            f.write(updated_content)
        print("[Labmem 004] config.py 버전 업그레이드 성공!")
    else:
        print("[Labmem 004 ERROR] config.py에서 _APP_VERSION 패턴을 찾지 못했습니다!")
        sys.exit(1)

except Exception as e:
    print(f"[Labmem 004 CRITICAL] 오류 발생: {e}")
    sys.exit(1)

```

## File: chzzk_api.py

```python
﻿### chzzk_api.py - 치지직 공개 API 통신 (클립/VOD/LIVE 메타데이터 + 스트림 목록)
import datetime
import json
import re
import urllib.request

import log_history
from cookies import get_browser_cookies
from media import get_video_codec_rank

def _chzzk_headers():
    """치지직/네이버 API 공통 헤더 — 쿠키는 naver/chzzk 도메인만 평탄화.
    cookies.py 반환 구조는 {도메인: {이름: 값}} 중첩 딕셔너리다.
    치지직/네이버 API 인증에는 naver 계열 쿠키(NID_SEAUT, LDTID 등)가
    필요하므로 해당 도메인만 골라 Cookie 헤더를 구성한다.
    """
    flat_cookies = {}
    for host, names in get_browser_cookies().items():
        if "naver.com" not in host and "chzzk" not in host:
            continue
        flat_cookies.update(names)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://chzzk.naver.com/",
    }
    if flat_cookies:
        headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in flat_cookies.items())
    return headers

def _get_json(url, headers):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as res:
        return json.loads(res.read().decode("utf-8"))

def analyze_chzzk_clip_api(target_url):
    """치지직 클립 — detail(제목/생성일/채널명) + play-info(rmcnmv MP4 목록)."""
    clean_url = target_url.split("?")[0].rstrip("/")
    clip_id = clean_url.split("/")[-1]
    headers = _chzzk_headers()

    clip_title = clip_id
    created_date = None
    channel_name = None

    detail_url = f"https://api.chzzk.naver.com/service/v1/clips/{clip_id}/detail"
    try:
        d_data = _get_json(detail_url, headers).get("content", {})
        if d_data.get("clipTitle"):
            clip_title = d_data.get("clipTitle")
        if d_data.get("createdDate"):
            created_date = d_data.get("createdDate").split(" ")[0]
        # 채널명 파싱
        owner = d_data.get("ownerChannel") or {}
        channel_name = owner.get("channelName") or d_data.get("channelName")
    except Exception as e:
        # [증거 남김] 세부 정보 폴백(제목=ID 표기)으로 계속 진행 — 원인은 히스토리에.
        import raw_log
        from log_event import LogEvent
        raw_log.raw(
            "chzzk",
            LogEvent(
                stage="CHZ", status="WARN", platform="CHZ",
                msg=f"치지직 클립 detail API 실패 (clip {clip_id}): {type(e).__name__}: {e}",
                is_error=True,
            ),
            to_tui=False,
        )

    play_info_url = f"https://api.chzzk.naver.com/service/v1/play-info/clip/{clip_id}"
    video_formats = []
    try:
        data = _get_json(play_info_url, headers)
        cnt = data.get("content", {})
        in_key, video_id = cnt.get("inKey"), cnt.get("videoId")

        if in_key and video_id:
            rmc_url = f"https://apis.naver.com/rmcnmv/rmcnmv/vod/play/v2.0/{video_id}?key={in_key}"
            rmc_data = _get_json(rmc_url, headers)
            videos = rmc_data.get("videos", {}).get("list", [])
            for idx, v in enumerate(videos):
                enc = v.get("encodingOption", {}) or {}
                encoding_opt = enc.get("name", f"Stream_{idx}")
                height = int(enc.get("height") or 0)
                if not height:
                    h_match = re.search(r"(\d+)p", encoding_opt, re.IGNORECASE)
                    if h_match:
                        height = int(h_match.group(1))
                br = v.get("bitrate", {})
                bitrate_kbps = (
                    int(br.get("video", 0) or 0)
                    if isinstance(br, dict)
                    else int(br or 0)
                )
                source_url = v.get("source", "")
                v_codec = enc.get("vcodec", "H.264")
                a_codec = enc.get("acodec", "AAC")

                video_formats.append(
                    {
                        "id": source_url if source_url else f"chzzk_{idx}",
                        "res": encoding_opt,
                        "height": height,
                        "fps": int(float(enc.get("fps") or 0)),
                        "bitrate": bitrate_kbps,
                        "url": source_url,
                        "vcodec": v_codec,
                        "acodec": a_codec,
                    }
                )
    except Exception as e:
        # [증거 남김] play-info 실패 → formats 비어 상위에서 RuntimeError fail-fast.
        import raw_log
        from log_event import LogEvent
        raw_log.raw(
            "chzzk",
            LogEvent(
                stage="CHZ", status="WARN", platform="CHZ",
                msg=f"치지직 클립 play-info API 실패 (clip {clip_id}): {type(e).__name__}: {e}",
                is_error=True,
            ),
            to_tui=False,
        )

    video_formats.sort(
        key=lambda x: (x["height"], get_video_codec_rank(x["vcodec"]), x["bitrate"]),
        reverse=True,
    )
    return {
        "title": clip_title,
        "date": created_date,
        "clip_id": clip_id,
        "formats": video_formats,
        "channel_name": channel_name,
    }

def analyze_chzzk_vod_api(target_url):
    """치지직 VOD(다시보기) — 메타 + progressive MP4 포맷 목록."""
    m = re.search(r"chzzk\.naver\.com/(?:video|live)/(\d+)", target_url)
    if not m:
        return {"title": None, "date": None, "duration": None, "formats": [], "channel_name": None}
    video_no = m.group(1)
    headers = _chzzk_headers()

    title, date, duration = video_no, None, None
    channel_name = None
    video_formats = []
    try:
        meta = (
            _get_json(
                f"https://api.chzzk.naver.com/service/v2/videos/{video_no}",
                headers,
            ).get("content")
            or {}
        )
        title = meta.get("videoTitle") or video_no
        title = re.sub(r"\.(mp4|mkv|ts|webm|mov)$", "", title, flags=re.IGNORECASE)
        date = (meta.get("publishDate") or "").split(" ")[0] or None
        duration = meta.get("duration")
        vid, inkey = meta.get("videoId"), meta.get("inKey")
        
        # 채널명 파싱
        channel = meta.get("channel") or {}
        channel_name = channel.get("channelName") or meta.get("channelName")

        if vid and inkey:
            pb = _get_json(
                f"https://apis.naver.com/neonplayer/vodplay/v2/playback/{vid}"
                f"?key={inkey}&env=real&country=KR&platform=web",
                headers,
            )
            for period in pb.get("period") or []:
                for aset in period.get("adaptationSet") or []:
                    for rep in aset.get("representation") or []:
                        url = next(
                            (
                                b.get("value")
                                for b in (rep.get("baseURL") or [])
                                if isinstance(b, dict)
                                and ".mp4" in str(b.get("value")).split("?")[0]
                            ),
                            None,
                        )
                        if not url:
                            continue
                        codecs = [
                            c.strip()
                            for c in str(rep.get("codecs") or "").split(",")
                            if c.strip()
                        ]
                        h = int(rep.get("height") or 0)
                        video_formats.append(
                            {
                                "id": rep.get("id") or f"vod_{h}",
                                "res": f"{h}p",
                                "height": h,
                                "fps": int(float(rep.get("frameRate") or 0)),
                                "bitrate": int(rep.get("bandwidth") or 0) // 1000,
                                "url": url,
                                "vcodec": codecs[0] if codecs else "H.264",
                                "acodec": codecs[1] if len(codecs) > 1 else "AAC",
                            }
                        )
    except Exception as e:
        # [증거 남김] VOD API 실패 → formats 비어 상위에서 RuntimeError fail-fast.
        import raw_log
        from log_event import LogEvent
        raw_log.raw(
            "chzzk",
            LogEvent(
                stage="CHZ", status="WARN", platform="CHZ",
                msg=f"치지직 VOD API 실패 (video/{video_no}): {type(e).__name__}: {e}",
                is_error=True,
            ),
            to_tui=False,
        )

    video_formats.sort(
        key=lambda x: (x["height"], get_video_codec_rank(x["vcodec"]), x["bitrate"]),
        reverse=True,
    )
    return {
        "title": title,
        "date": date,
        "duration": duration,
        "video_no": video_no,
        "formats": video_formats,
        "channel_name": channel_name,
    }


def _fetch_m3u8_streams(m3u8_url, headers, timeout=15):
    """m3u8 HLS 매니페스트를 경량 조회 — 분석 단계에서 format 목록만 추출.

    yt-dlp의 'Downloading m3u8 information' 스텝은 매니페스트 전체를
    변형하며 (variants/iframe/subtitle 등) googlevideo 셔드 스로틀에서
    영구 HANG 위험이 있다. 여기서는 #EXT-X-STREAM-INF 라인만 빠르게
    스캔해 (resolution/bandwidth) 포맷 목록을 반환한다.
    """
    req = urllib.request.Request(m3u8_url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as res:
        content = res.read().decode("utf-8", errors="replace")

    fmt_by_res = {}
    cur_bw = 0
    cur_res = ""
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("#EXT-X-STREAM-INF"):
            attrs = dict(re.findall(r'(\w+)="([^"]*)"', line))
            cur_bw = int(float(attrs.get("BANDWIDTH", 0) or 0)) // 1000
            cur_res = attrs.get("RESOLUTION", "")
        elif line and not line.startswith("#"):
            height = 0
            h_match = re.search(r"(\d+)x(\d+)", cur_res)
            if h_match:
                height = int(h_match.group(2))
            elif cur_res:
                h_match = re.search(r"(\d+)p", cur_res, re.IGNORECASE)
                if h_match:
                    height = int(h_match.group(1))
            if height and height not in fmt_by_res:
                fmt_by_res[height] = {
                    "id": line,
                    "res": cur_res,
                    "height": height,
                    "fps": 0,
                    "bitrate": cur_bw,
                    "url": line,
                    "vcodec": "H.264",
                    "acodec": "AAC",
                }
    return sorted(fmt_by_res.values(), key=lambda x: x["height"], reverse=True)


def analyze_chzzk_live_api(target_url):
    """치지직 실시간 방송 — 메타 + HLS 포맷 목록 (m3u8 경량 스캔).

    live ID는 32자리 16진수 해시(a0e26a105c3b5ac212d5e0ca40c5c747)이므로
    기존 VOD API의 (\\d+) 정규식과 분리 필요.
    """
    m = re.search(r"chzzk\.naver\.com/live/([\w-]+)", target_url)
    if not m:
        return {"title": None, "date": None, "duration": None, "formats": [], "channel_name": None}
    live_id = m.group(1)
    headers = _chzzk_headers()

    title = live_id
    date = None
    duration = None
    channel_name = None
    video_formats = []
    live_status = "UNKNOWN"

    try:
        meta = (
            _get_json(
                f"https://api.chzzk.naver.com/service/v1/live/{live_id}",
                headers,
            ).get("content", {})
            or {}
        )
        title = meta.get("liveTitle") or live_id
        title = re.sub(r"\.(mp4|mkv|ts|webm|mov)$", "", title, flags=re.IGNORECASE)
        date = (meta.get("liveStartTime") or "").split(" ")[0] or None
        channel = meta.get("channel") or {}
        channel_name = channel.get("channelName") or meta.get("channelName")
        live_status = meta.get("liveStatus", "PROGRESS")

        # 스트림 URL 추출
        stream_info = meta.get("liveStreamInfo", {})
        if isinstance(stream_info, dict):
            m3u8_url = (
                stream_info.get("serviceUrl")
                or stream_info.get("streamingUrl")
                or stream_info.get("sourceUrl")
                or ""
            )
        elif isinstance(stream_info, str):
            m3u8_url = stream_info
        else:
            m3u8_url = ""

        if m3u8_url:
            video_formats = _fetch_m3u8_streams(m3u8_url, headers)
    except Exception as e:
        # [증거 남김] live API 실패 → formats 비어 상위에서 fail-fast.
        import raw_log
        from log_event import LogEvent
        raw_log.raw(
            "chzzk",
            LogEvent(
                stage="CHZ", status="WARN", platform="CHZ",
                msg=f"치지직 LIVE API 실패 (live/{live_id}): {type(e).__name__}: {e}",
                is_error=True,
            ),
            to_tui=False,
        )

    if not video_formats:
        if live_status != "PROGRESS":
            import raw_log
            from log_event import LogEvent
            raw_log.raw(
                "chzzk",
                LogEvent(
                    stage="CHZ", status="WARN", platform="CHZ",
                    msg=f"치지직 LIVE 비방송 중 ({live_status}) — live/{live_id}",
                    is_error=False,
                ),
                to_tui=False,
            )

    video_formats.sort(
        key=lambda x: (x["height"], get_video_codec_rank(x["vcodec"]), x["bitrate"]),
        reverse=True,
    )
    return {
        "title": title,
        "date": date,
        "duration": duration,
        "live_id": live_id,
        "live_status": live_status,
        "formats": video_formats,
        "channel_name": channel_name,
    }

```

## File: client_opts.py

```python
##### downloader_helpers/client_opts.py - yt-dlp 옵션 빌더
"""yt-dlp 옵션에 player_client/쿠키 설정을 주입하는 순수 헬퍼."""
import os
import shutil


def _apply_ffmpeg_opts(opts):
    """ffmpeg 경로를 ydl_opts에 반영 (Windows/macOS/Linux 호환)."""
    # 이미 ffmpeg_location이 설정되어 있으면 스킵
    if "ffmpeg_location" in opts:
        return opts
    # 시스템 PATH에서 ffmpeg 검색 (Windows에서는 ffmpeg.exe도 시도)
    ffmpeg_path = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
    if ffmpeg_path:
        opts["ffmpeg_location"] = ffmpeg_path
    return opts


def _apply_client_opts(opts, cfg, forced=None):
    """유튜브 player_client 수동 지정을 ydl_opts에 반영 (성인제한 대응).

    forced가 주어지면(분석 단계에서 실증·통과한 클라이언트) cfg 값보다
    우선한다. 다운로드가 분석과 같은 클라이언트를 쓰도록 해 PO 토큰/
    봇 게이트 경로 재진입(0% 스톨)을 막는다.

    [중요] yt-dlp 기본 _DEFAULT_CLIENTS는 ('visionos', 'web')인데,
    visionos는 연령제한 영상을 처리하지 못해 "No video formats found"로
    실패한다. 쿠키가 있으면 인증 클라이언트(web, web_embedded, tv_downgraded)
    를 우선 시도하도록 기본값을 'web'으로 강제한다 — 사용자가 명시적으로
    'auto'를 선택한 경우에만 yt-dlp 기본을 따른다.
    """
    client = str(forced or cfg.get("yt_player_client", "auto") or "auto")
    if client == "auto":
        # [연령제한 방어] visionos 기본이 age-gate를 통과 못함.
        # 쿠키가 있으면 'web'으로 강제 → 인증 클라이언트 경로로 진입.
        # 쿠키 미설정이면 'auto' 유지(yt-dlp 기본 → 빠른 분석).
        cookie_file = (cfg.get("cookiefile")
                       or cfg.get("cookiesfrombrowser")
                       or cfg.get("cookie_file_path"))
        browser = cfg.get("browser_cookie", "none")
        if browser not in ("none", "auto") or cookie_file:
            client = "web"
        else:
            return opts  # 쿠키 없으면 yt-dlp 기본(visionos→web) 사용
    opts.setdefault("extractor_args", {}).setdefault("youtube", {}) \
        .setdefault("player_client", []).append(client)
    return opts


def _apply_cookie_opts(opts, cfg):
    """브라우저 쿠키 설정을 ydl_opts에 반영 (4곳 중복 제거 공통 헬퍼)."""
    browser = cfg.get("browser_cookie", "none")
    if browser not in ["none", "auto", "cookie_file"]:
        opts["cookiesfrombrowser"] = (browser,)
    elif browser == "cookie_file" and os.path.exists(cfg.get("cookie_file_path", "")):
        opts["cookiefile"] = cfg["cookie_file_path"]
    return opts


def _apply_ejs_opts(opts):
    """YouTube JS 챌린지(n-sig) 솔버 원격 수급 — ejs:github 허용.

    [배경] YouTube가 web 계열 클라이언트에 JS 챌린지를 요구할 때
    기본 설정은 원격 솔버 다운로드를 skip해 'page needs to be reloaded'
    오류로 귀결된다. ejs:github 허용치를 주면 GitHub에서 챌린지 솔버
    스크립트를 자동 수급해 n-sig 해결을 돕는다.
    """
    if "remote_components" not in opts:
        opts["remote_components"] = []
    if "ejs:github" not in opts["remote_components"]:
        opts["remote_components"].append("ejs:github")
    return opts


def _apply_light_analysis_opts(opts):
    """[경량 분석] YouTube HLS/DASH 매니페스트 열거 생략 — 분석 스톨 차단.

    yt-dlp youtube 추출기는 web 붕괴 시 tv/visionos 등 HLS 계열 클라이언트로
    폴백하며, 이때 'Downloading m3u8 information' 단계에서 매니페스트 전체
    변형을 내려받는다. 이 요청은 googlevideo 셔드 지연/스로틀 환경에서
    멈춰 분석이 'analyzing...'에 영원히 갇히는 원인이 된다.

    분석은 채널명/제목/포맷 개수 등 기본 정보만 필요하므로 매니페스트를
    열거하지 않고 플레이어 응답의 직접 URL 포맷만 취한다. 실제 데이터 수급
    (매니페스트 재열거 + JS 챌린지/PO 토큰 우회)은 DownloadWorker의 무거운
    경로가 담당한다 — 가벼운 동작(살펴보기)과 무거운 동작(내려받기) 분리.
    """
    ea = opts.setdefault("extractor_args", {}).setdefault("youtube", {})
    skip = ea.setdefault("skip", [])
    for manifest in ("hls", "dash"):
        if manifest not in skip:
            skip.append(manifest)
    return opts


def _apply_pot_opts(opts, video_id, client="web_embedded"):
    """bgutil 독립 서버에서 PO 토큰을 직접 패칭해 extractor_args로 주입.

    [변경] 기존 Python 플러그인(yt_dlp_plugins/getpot_bgutil) 자동 주입을
    제거하고, 앱이 bgutil HTTP 서버에 POST /get_pot를 직접 호출해
    `youtube:po_token=CLIENT.gvs+TOKEN` 형태로 명시 전달한다.
    - 플러그인 제거 → 토큰 생성이 블랙박스가 아니라 앱이 완전히 제어
    - 서버 미기동/오류 시 None → PO 없이 진행 (플러그인 실패와 달리 조용)
    - player_client가 이미 설정돼 있으면 병합 (덮어쓰지 않음)
    """
    if not video_id:
        return opts
    from po_client import fetch_po_token
    token = fetch_po_token(video_id)
    if not token:
        return opts
    ea = opts.setdefault("extractor_args", {}).setdefault("youtube", {})
    # po_token은 list[str] — 기존 값 유지하며 gvs 컨텍스트만 추가
    ea.setdefault("po_token", []).append(f"{client}.gvs+{token}")
    return opts


def _dedupe_by_label(formats):
    """표시 라벨이 동일한 포맷은 대표 1개만 남긴다 (라이브 HLS 중복 제거)."""
    seen, unique = set(), []
    for fmt in formats:
        if fmt["label"] not in seen:
            seen.add(fmt["label"])
            unique.append(fmt)
    return unique

```

## File: components.py

```python
﻿### components.py - ffmpeg runtime manager
"""ffmpeg 자동 수급/관리 전용 모듈.

*  시스템 PATH의 ffmpeg 최우선 사용, 없으면 GitHub(GyanD/codexffmpeg)
   release 바이너리를 writable_base/ffmpeg/에 전개해 PATH에 연결.
*  macOS는 Homebrew 설치 우선, 실패 시 Homebrew bottle 직접 다운로드.

[전수조사 정리 2026-09-04] 구 설계(Hitomi Downloader style 전체 구성요소
자동수급: yt-dlp 휠 / bgutil 플러그인 / pot-pack / streamlink-pack)는
main.py에 연결된 적이 없는 죽은 코드였음 — 실제 의존 흐름은
venv pip(yt-dlp / streamlink) + pot_provider(bgutil 서버 빌드) + 본 모듈.
"""
import hashlib
import json
import os
import platform
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

import config
from log_console import emit_component

_UA = "ChzzkTube-Components/1.0"


def components_root():
    """구성요소 전개 루트. frozen: <exe>/components, source: <repo>/components."""
    env = os.environ.get("CHZZKTUBE_COMPONENTS_DIR")
    if env:
        return env
    if getattr(sys, "frozen", False):
        return os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "components")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "components")



def _logcb(log):
    return log if callable(log) else (lambda *a, **k: None)


def _http_get(url, timeout=30):
    """HTTP GET 요청, ghcr.io는 토큰 인증 자동 처리."""
    headers = {"User-Agent": _UA}
    if "ghcr.io" in url:
        try:
            token = _ghcr_token("repository:homebrew/core/ffmpeg:pull")
            headers["Authorization"] = f"Bearer {token}"
        except Exception:
            pass
    req = urllib.request.Request(url, headers=headers)
    return urllib.request.urlopen(req, timeout=timeout)


def _ghcr_token(scope):
    """ghcr.io 익명 토큰 획득."""
    url = f"https://ghcr.io/token?scope={scope}"
    with urllib.request.urlopen(url, timeout=15) as resp:
        data = json.load(resp)
    return data.get("token")


def _download(url, dest, log, label="", is_status=False):
    """파일 다운로드(진행 로그 포함). 성공 시 dest 경로 반환.
    
    is_status=True 면 진행률 로그를 상태 줄로 표시 (이전 줄 덮어쓰기).
    """
    log(emit_component("DEPS", "RUN", "-", f"{label or os.path.basename(url)} fetching..."), is_status)
    tmp = dest + ".part"
    with _http_get(url, timeout=60) as resp, open(tmp, "wb") as f:
        total = int(resp.headers.get("Content-Length") or 0)
        done, last_mb = 0, -1
        while True:
            chunk = resp.read(1024 * 512)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            mb = done // (1024 * 1024)
            # 진행률 로그 빈도 조절: 8MB 이상 파일은 2MB마다, 미만은 완료 시에만
            if total < 8 * 1024 * 1024 or mb != last_mb and mb % 2 == 0:
                last_mb = mb
                pct = f" ({done * 100 // total}%)" if total else ""
                log(emit_component("DEPS", "RUN", "-", f"{label or 'download'} {mb} MB{pct}"), is_status)
    os.replace(tmp, dest)
    log(emit_component("DEPS", "OK", "-", f"{label or os.path.basename(dest)} done ({done / 1048576:.1f} MB)"))
    return dest


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _rmtree(p):
    shutil.rmtree(p, ignore_errors=True)


def _exe_suffix():
    """현재 OS의 실행 파일 확장자를 반환한다."""
    return ".exe" if os.name == "nt" else ""


def _extract_zip(zip_path, dest_dir, log, label, promote_single_root=False):
    """zip 을 임시 폴더에 풀고 완성 후 dest_dir 로 교체 (실패 시 기존 버전 보존).

    promote_single_root=True 면 zip 최상위에 폴더 하나만 있을 때(예: zipball 루트
    bgutil-ytdlp-pot-provider-1.3.2/) 그 내부를 dest_dir 로 승격한다.
    """
    tmp = dest_dir + ".tmp"
    _rmtree(tmp)
    os.makedirs(os.path.dirname(tmp) or ".", exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(tmp)
    if promote_single_root:
        entries = os.listdir(tmp)
        if len(entries) == 1 and os.path.isdir(os.path.join(tmp, entries[0])):
            inner = os.path.join(tmp, entries[0])
            _rmtree(dest_dir)
            shutil.move(inner, dest_dir)
            _rmtree(tmp)
    else:
        for entry in os.listdir(tmp):
            s = os.path.join(tmp, entry)
            d = os.path.join(dest_dir, entry)
            if os.path.isdir(d):
                shutil.rmtree(d, ignore_errors=True)
            os.makedirs(os.path.dirname(d) or ".", exist_ok=True)
            shutil.move(s, d)
        _rmtree(tmp)
    log(emit_component("DEPS", "OK", "-", f"{label} extracted → {os.path.relpath(dest_dir, components_root())}"))


FFMPEG_DIRNAME = "ffmpeg"
# GitHub 릴리즈 URL: 버전 명시 (latest 사용 시 source code를 가리켜 404 발생)
FFMPEG_RELEASE_URL = (
    "https://github.com/GyanD/codexffmpeg/releases/download/7.1/"
    "ffmpeg-7.1-essentials.zip"
)
_FFMPEG_BREW_API = "https://formulae.brew.sh/api/formula/ffmpeg.json"

# macOS 버전 → Homebrew bottle 키 매핑 (arm64 우선, intel 폴백)
_MACOS_BOTTLE_KEY_ORDER = [
    # (major, minor), arm64_key, intel_key
    ((15, 0), "arm64_sonoma", "sonoma"),
    ((14, 0), "arm64_sonoma", "sonoma"),
    ((13, 0), "arm64_ventura", "ventura"),
    ((12, 0), "arm64_monterey", "monterey"),
    ((11, 0), "arm64_big_sur", "big_sur"),
    ((10, 15), "arm64_catalina", "catalina"),
]


def _macos_bottle_keys():
    """현재 macOS 버전/아키텍처에 맞는 Homebrew bottle 키 목록 (우선순위순)."""
    ver = platform.mac_ver()[0]
    if not ver:
        return []
    parts = ver.split(".")
    major = int(parts[0]) if parts else 0
    minor = int(parts[1]) if len(parts) > 1 else 0
    arch = platform.machine()  # 'arm64' or 'x86_64'

    # 현재 버전 이상의 bottle 키를 모두 수집
    keys = []
    for (m, M), arm_key, intel_key in _MACOS_BOTTLE_KEY_ORDER:
        if (major, minor) >= (m, M):
            if arch == "arm64":
                keys.append(arm_key)
            keys.append(intel_key)
    # 현재 버전 매칭이 없으면 최신 키로 폴백
    if not keys:
        _, arm_key, intel_key = _MACOS_BOTTLE_KEY_ORDER[0]
        if arch == "arm64":
            keys.append(arm_key)
        keys.append(intel_key)
    return keys



def ensure_ffmpeg(log=None, force=False):
    """ffmpeg 자동 수급 — 시스템 설치 우선, 없으면 바이너리 다운로드.

    [퍼사드 함수] 외부(pot_provider 등)에서 호출하는 단일 진입점.
    성공 시 None, 실패 시 오류 문자열.

    OS별 처리:
    - Windows: 시스템 ffmpeg.exe 우선 → GitHub GyanD/codexffmpeg 다운로드
    - macOS: 시스템 ffmpeg 우선 → Homebrew bottle 다운로드
    - Linux: 시스템 ffmpeg 우선 → johnvansickle.com 정적 빌드 다운로드
    """
    log = _logcb(log)
    log(emit_component("DEPS", "RUN", "ffmpeg", "checking..."))
    try:
        # 1. 시스템 ffmpeg 검색 (OS별 확장자 자동 처리)
        suffix = _exe_suffix()
        which = shutil.which("ffmpeg") or shutil.which(f"ffmpeg{suffix}")
        if which and not force:
            if os.access(which, os.X_OK) and _verify_ffmpeg(which):
                log(emit_component("DEPS", "OK", "ffmpeg", "ok"))
                return None
            else:
                log(emit_component("DEPS", "WARN", "ffmpeg", f"found but not working ({which})"))

        # 2. 로컬 캐시 확인
        cached = ffmpeg_exe()
        if cached and not force:
            _wire_ffmpeg_path(os.path.dirname(cached))
            log(emit_component("DEPS", "OK", "ffmpeg", "ok"))
            return None

        # 3. OS별 전략 호출
        return _ensure_ffmpeg_by_platform(log, force)
    except Exception as e:
        return f"{type(e).__name__}: {e}"

def _ensure_ffmpeg_by_platform(log, force):
    """플랫폼에 따라 적절한 전략 함수에 위임 (전략 패턴)."""
    platform = sys.platform
    if platform == "win32":
        return _ensure_ffmpeg_windows(log, force)
    elif platform == "darwin":
        return _ensure_ffmpeg_macos(log, force)
    elif platform.startswith("linux"):
        return _ensure_ffmpeg_linux(log, force)
    else:
        return f"Unsupported OS: {platform}"


def _ensure_ffmpeg_windows(log, force):
    """Windows용 ffmpeg 자동 수급 - GitHub GyanD/codexffmpeg 다운로드.
    시스템 ffmpeg.exe 우선, 없으면 GitHub release에서 다운로드.
    """
    dest = os.path.join(config.writable_base(), FFMPEG_DIRNAME)
    bin_dir = os.path.join(dest, "bin")
    exe_path = os.path.join(bin_dir, "ffmpeg.exe")
    
    # 캐시된 ffmpeg 확인
    if not force:
        if os.path.isfile(exe_path):
            _wire_ffmpeg_path(bin_dir)
            log(emit_component("DEPS", "OK", "ffmpeg", "ok"))
            return None
    
    # GitHub에서 다운로드
    os.makedirs(dest, exist_ok=True)
    log(emit_component("DEPS", "RUN", "ffmpeg", "downloading..."))
    
    with tempfile.TemporaryDirectory(prefix="cz_ffmpeg_") as td:
        zp = _download(FFMPEG_RELEASE_URL, os.path.join(td, "ffmpeg.zip"), log, "ffmpeg")
        _extract_zip(zp, dest, log, "ffmpeg", promote_single_root=True)
    
    if os.path.isfile(exe_path):
        _wire_ffmpeg_path(bin_dir)
        log(emit_component("DEPS", "OK", "ffmpeg", "ok"))
        return None
    
    return "ffmpeg.exe not found after extract"


def _ensure_ffmpeg_macos(log, force):
    """맥용 ffmpeg 자동 수급 - Homebrew 우선, 없으면 bottle 다운로드."""
    dest = os.path.join(config.writable_base(), FFMPEG_DIRNAME)

    if not force:
        cached = ffmpeg_exe()
        if cached:
            # ffmpeg가 실제로 실행 가능한지 확인
            if _verify_ffmpeg(cached):
                _wire_ffmpeg_path(os.path.dirname(cached))
                log(emit_component("DEPS", "OK", "ffmpeg", "ok"))
                return None
            else:
                log(emit_component("DEPS", "WARN", "ffmpeg", "cached not working, reinstalling"))
                # 캐시된 ffmpeg가 작동하지 않으므로 삭제
                try:
                    if os.path.exists(dest):
                        shutil.rmtree(dest, ignore_errors=True)
                except Exception:
                    pass

    # Homebrew가 설치되어 있으면 brew install ffmpeg 시도
    brew_path = shutil.which("brew")
    if brew_path:
        log(emit_component("DEPS", "RUN", "ffmpeg", "installing via Homebrew..."))
        import subprocess
        try:
            result = subprocess.run(
                ["brew", "install", "ffmpeg"],
                capture_output=True,
                text=True,
                timeout=300  # 5분 타임아웃
            )
            if result.returncode == 0:
                # 설치 성공 - 경로 확인
                ffmpeg_path = shutil.which("ffmpeg")
                if ffmpeg_path and _verify_ffmpeg(ffmpeg_path):
                    log(emit_component("DEPS", "OK", "ffmpeg", "ok"))
                    return None
            else:
                log(emit_component("DEPS", "WARN", "ffmpeg", f"brew install failed: {result.stderr[:100]}"))
        except subprocess.TimeoutExpired:
            log(emit_component("DEPS", "WARN", "ffmpeg", "brew install timed out"))
        except Exception as e:
            log(emit_component("DEPS", "WARN", "ffmpeg", f"brew install error: {e}"))

    # Homebrew 실패 시 bottle 다운로드 시도
    try:
        log(emit_component("DEPS", "RUN", "ffmpeg", "downloading (Homebrew bottle)..."))
        with urllib.request.urlopen(_FFMPEG_BREW_API, timeout=15) as resp:
            data = json.load(resp)

        bottle = data.get("bottle", {}).get("stable", {})
        files = bottle.get("files", {})

        keys = _macos_bottle_keys()
        selected = None
        for key in keys:
            if key in files:
                selected = files[key]
                break

        if not selected:
            return "no compatible Homebrew bottle for this macOS version/arch"

        url = selected.get("url")
        sha256 = selected.get("sha256")
        if not url:
            return "Homebrew bottle URL missing"

        with tempfile.TemporaryDirectory(prefix="cz_ffmpeg_") as td:
            tar_path = os.path.join(td, "ffmpeg.tar.gz")
            _download(url, tar_path, log, "ffmpeg", is_status=True)

            if sha256:
                got = _sha256(tar_path)
                if got != sha256:
                    return f"ffmpeg bottle hash mismatch ({got[:12]}…)"
                log(emit_component("DEPS", "OK", "ffmpeg", "SHA-256 ok"))

            log(emit_component("DEPS", "RUN", "ffmpeg", "extracting..."))
            # 기존 디렉토리를 완전히 삭제
            if os.path.exists(dest):
                shutil.rmtree(dest, ignore_errors=True)
            os.makedirs(dest, exist_ok=True)

            # subprocess로 tar 명령어 직접 실행
            import subprocess
            result = subprocess.run(
                ["tar", "-xzf", tar_path, "-C", dest],
                capture_output=True,
                text=True,
                timeout=120
            )
            if result.returncode != 0:
                return f"tar extraction failed: {result.stderr}"

            # bottle 추출 구조에서 ffmpeg 검색
            ffmpeg_src = None
            ffmpeg_bin_dir = None
            for root, dirs, files in os.walk(dest):
                if "ffmpeg" in files:
                    candidate = os.path.join(root, "ffmpeg")
                    if os.path.isfile(candidate):
                        ffmpeg_src = candidate
                        ffmpeg_bin_dir = root
                        break

            if ffmpeg_src and ffmpeg_bin_dir:
                # 원래 디렉토리 구조를 유지하고 PATH에 추가
                _wire_ffmpeg_path(ffmpeg_bin_dir)
                # 설치 확인
                if _verify_ffmpeg(ffmpeg_src):
                    log(emit_component("DEPS", "OK", "ffmpeg", "ok"))
                    return None
                else:
                    return "ffmpeg installed but not working (verification failed)"
        return "ffmpeg exe not found after extract"
    except Exception as e:
        return f"{type(e).__name__}: {e}"

def ffmpeg_exe():
    """ffmpeg 실행 파일 경로. 수급 캐시 우선, 없으면 시스템 PATH."""
    exe_name = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    # 기존 위치 (bin_dir) 확인
    local = os.path.join(
        config.writable_base(), FFMPEG_DIRNAME, "bin", exe_name
    )
    if os.path.isfile(local) and os.access(local, os.X_OK):
        return local
    # Homebrew bottle 추출 디렉토리에서 검색
    dest = os.path.join(config.writable_base(), FFMPEG_DIRNAME)
    if os.path.isdir(dest):
        for root, dirs, files in os.walk(dest):
            if exe_name in files:
                candidate = os.path.join(root, exe_name)
                if os.access(candidate, os.X_OK):
                    return candidate
    return shutil.which("ffmpeg")

def _ensure_ffmpeg_linux(log, force):
    """리눅스용 ffmpeg 자동 수급 - 시스템 패키지 매니저 우선, 없으면 정적 빌드 다운로드.

    johnvansickle.com의 정적 빌드를 사용하여 어떤 배포판에서도 작동.
    """
    dest = os.path.join(config.writable_base(), FFMPEG_DIRNAME)

    # 캐시된 ffmpeg 확인
    if not force:
        cached = ffmpeg_exe()
        if cached:
            if _verify_ffmpeg(cached):
                _wire_ffmpeg_path(os.path.dirname(cached))
                log(emit_component("DEPS", "OK", "ffmpeg", "ok"))
                return None
            else:
                log(emit_component("DEPS", "WARN", "ffmpeg", "cached not working, reinstalling"))
                try:
                    if os.path.exists(dest):
                        shutil.rmtree(dest, ignore_errors=True)
                except Exception:
                    pass

    # 시스템 패키지 매니저 시도 (apt/dnf/pacman)
    import subprocess
    pkg_managers = [
        (["apt-get", "install", "-y", "ffmpeg"], "apt"),
        (["dnf", "install", "-y", "ffmpeg"], "dnf"),
        (["pacman", "-S", "--noconfirm", "ffmpeg"], "pacman"),
    ]
    for cmd, name in pkg_managers:
        if shutil.which(cmd[0]):
            log(emit_component("DEPS", "RUN", "ffmpeg", f"installing via {name}..."))
            try:
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=300
                )
                if result.returncode == 0:
                    ffmpeg_path = shutil.which("ffmpeg")
                    if ffmpeg_path and _verify_ffmpeg(ffmpeg_path):
                        log(emit_component("DEPS", "OK", "ffmpeg", "ok"))
                        return None
            except subprocess.TimeoutExpired:
                log(emit_component("DEPS", "WARN", "ffmpeg", f"{name} install timed out"))
            except Exception as e:
                log(emit_component("DEPS", "WARN", "ffmpeg", f"{name} install error: {e}"))

    # 정적 빌드 다운로드 (johnvansickle.com)
    try:
        log(emit_component("DEPS", "RUN", "ffmpeg", "downloading (static build)..."))
        url = "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"
        with tempfile.TemporaryDirectory(prefix="cz_ffmpeg_") as td:
            tar_path = os.path.join(td, "ffmpeg.tar.xz")
            _download(url, tar_path, log, "ffmpeg", is_status=True)

            log(emit_component("DEPS", "RUN", "ffmpeg", "extracting..."))
            if os.path.exists(dest):
                shutil.rmtree(dest, ignore_errors=True)
            os.makedirs(dest, exist_ok=True)

            # tar.xz 압축 해제
            import tarfile
            with tarfile.open(tar_path, "r:xz") as tar:
                # ffmpeg와 ffprobe만 추출
                for member in tar.getmembers():
                    if member.name.endswith("/ffmpeg") or member.name.endswith("/ffprobe"):
                        member.name = os.path.basename(member.name)
                        tar.extract(member, dest)

            # 실행 권한 보장
            ffmpeg_bin = os.path.join(dest, "ffmpeg")
            if os.path.isfile(ffmpeg_bin):
                os.chmod(ffmpeg_bin, 0o755)
                if _verify_ffmpeg(ffmpeg_bin):
                    _wire_ffmpeg_path(dest)
                    log(emit_component("DEPS", "OK", "ffmpeg", "ok"))
                    return None

        return "ffmpeg binary not found after extract"
    except Exception as e:
        return f"linux ffmpeg install failed: {type(e).__name__}: {e}"


def _wire_ffmpeg_path(bin_dir):
    """수급/캐시된 ffmpeg bin을 프로세스 PATH 선두에 연결.

    media.py·downloader.py가 subprocess로 bare 'ffmpeg'를 호출하므로, 시스템
    설치가 없는 PC에서도 이 세션의 자식 프로세스가 수급본을 즉시 사용하게 한다.
    """
    try:
        if os.path.isdir(bin_dir):
            path_env = os.environ.get("PATH", "")
            parts = path_env.split(os.pathsep) if path_env else []
            if bin_dir not in parts:
                os.environ["PATH"] = os.pathsep.join([bin_dir] + parts)
                # 디버그: PATH 확인
                import logging
                logging.debug(f"ffmpeg bin added to PATH: {bin_dir}")
                logging.debug(f"ffmpeg executable check: {shutil.which('ffmpeg')}")
    except Exception:
        pass

def _verify_ffmpeg(ffmpeg_path):
    """ffmpeg이 실제로 실행 가능한지 확인."""
    import subprocess
    try:
        result = subprocess.run(
            [ffmpeg_path, "-version"],
            capture_output=True,
            timeout=10
        )
        return result.returncode == 0
    except Exception:
        return False



```

## File: config.py

```python
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
_APP_VERSION = "v3.3.1"

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

```

## File: controller.py

```python
### controller.py - 다운로드 세션의 상태 머신 및 DownloadWorker 생명주기 관리
import os
import re

from PySide6.QtCore import QObject, Signal

from analyze_worker import AnalyzeWorker
from downloader import DownloadWorker


class MediaController(QObject):
    """다운로드 + 분석 세션의 상태 머신과 생명주기를 통치하는 완벽한 컨트롤러.

    계약:
    *  state 딕셔너리는 DownloadWorker에 참조 그대로 전달된다. 즉, 워커 스레드와 UI 스레드가 동일 객체를 공유하며 기존 MainWindow.dl_state와 완전히 동치이다.
    *  스레드 경계 — state 플래그는 단방향 쓰기: canceled/skip 는
       UI 스레드만 쓰고 워커 스레드는 읽기만 한다. CPython GIL 하에서 dict 단일 키 읽기/쓰기는 원자적이고
       각 키의 쓰기 주체가 하나뿐이므로 lock 없이도 경쟁상태(lost update)가 발생하지 않는다.
    *  워커 → UI 통보는 절대 state가 아니라 Qt 시그널(log_concise/log_full/
       finished_all/result_ready/error_occurred)로만 — 시그널 emit은 스레드 안전(QueuedConnection으로
       수신 스레드 큐에 적재)이므로 UI 위젯은 워커에서 직접 조작 금지.
    *  UI 조작(버튼/로그/진행바)은 view(MainWindow)의 메서드를 통해서만 수행한다.
    *  좀비 워커(분석 중 새 분석 요청으로 폐기된 워커)는 View가 아닌 Controller가 소유하며,
       자연 종료 시 _reap_zombie()로 메모리에서 소거한다. """

    # ── 분석 워커 시그널 포워딩 (View 바인딩용) ──
    # [v3.3.0] 로그는 raw 버스 단일 경유 — analyze_log_full 포워딩 폐기.
    analyze_result_ready = Signal(dict)
    analyze_error_occurred = Signal(str)

    def __init__(self, view):
        super().__init__()
        self.view = view
        self.state = {
            "running": False,
            "canceled": False,
            "skip": False,
            "analyzing": False,
            "picking": False,  # 포맷 직접 고르기 대기 (UI pick 입력 수신 중)
        }
        self.worker_dl = None
        self.worker_analyze = None
        self._zombie_workers = []  # View가 아닌 Controller가 무덤을 관리한다

    @property
    def running(self):
        return self.state["running"]

    @property
    def analyzing(self):
        return self.state["analyzing"]

    @property
    def picking(self):
        return self.state["picking"]

    # ── 분석 워커 생명주기 (main.py에서 구출 완료) ──
    def spawn_analyzer(self, url, cfg, deep=False):
        """URL 분석 워커 생성 및 관리 (기존 분석 강제 유기 포함)

        deep=True: 매니페스트(스클) 포함 포맷 목록 확보 — 포맷 직접 고르기 전용.
        """
        self._abandon_analyzer()

        self.state["analyzing"] = True
        self.worker_analyze = AnalyzeWorker(url, cfg, deep=deep)
        # View 시그널로 포워딩 (Controller가 중개)
        self.worker_analyze.result_ready.connect(self.analyze_result_ready)
        self.worker_analyze.error_occurred.connect(self.analyze_error_occurred)
        self.worker_analyze.start()

    def _abandon_analyzer(self):
        """GIL 데드락을 회피하기 위한 우아한 워커 유기 (Zombie Pattern)"""
        w = self.worker_analyze
        if not w:
            return
        if w.isRunning():
            # 시그널을 끊어 UI 오염 차단
            for sig in (w.result_ready, w.error_occurred):
                try:
                    sig.disconnect()
                except TypeError:
                    pass
            w.finished.connect(self._reap_zombie)
            self._zombie_workers.append(w)
        self.worker_analyze = None
        self.state["analyzing"] = False

    def _reap_zombie(self):
        """자연 종료된 유기 워커를 메모리에서 우아하게 소거한다."""
        try:
            self._zombie_workers.remove(self.sender())
        except (ValueError, AttributeError):
            pass

    ### ── 순수 로직: 타겟 파싱 ──────────────────────────────────
    @staticmethod
    def parse_targets(raw_text, dedup=False):
        """URL/TXT 입력을 다운로드 타겟 목록으로 파싱.
        *  TXT 파일 경로면 줄 단위로 읽는다 (# 주석 제외). 실패 시 ValueError.
        *  www. 로 시작하는 항목은 https:// 접두사를 보정한다.
        *  watch?v= 단일 영상 주소 뒤 &list= / &index= / &start_radio= 플레이리스트 파라미터를 강제 제거한다.
        *  dedup=True 이면 중복 타겟을 제거한다. """
        targets = []
        if os.path.isfile(raw_text) and raw_text.lower().endswith(".txt"):
            try:
                with open(raw_text, "r", encoding="utf-8") as f:
                    for l in f:
                        t = l.strip()
                        if t and not t.startswith("#"):
                            targets.append(
                                "https://" + t if t.startswith("www.") else t
                            )
            except Exception as e:
                raise ValueError(f"TXT read fail: {e}") from e
        else:
            for l in raw_text.splitlines():
                t = l.strip()
                if t:
                    targets.append("https://" + t if t.startswith("www.") else t)

        # [핵심] watch?v= 단일 영상 뒤에 붙은 플레이리스트 파라미터 강제 제거!
        cleaned_targets = []
        for u in targets:
            if "watch?v=" in u and "&list=" in u:
                u = re.sub(r"&list=[^&]+", "", u)
                u = re.sub(r"&index=[^&]+", "", u)
                u = re.sub(r"&start_radio=[^&]+", "", u)
            cleaned_targets.append(u)
        targets = cleaned_targets

        if dedup:
            targets = list(dict.fromkeys(targets))
        return targets

    ### ── 세션 상태 머신 ────────────────────────────────────────
    def begin_download(self):
        self.state.update(
            {"running": True, "canceled": False, "skip": False}
        )

    def end_download(self):
        self.state.update(
            {"running": False, "canceled": False, "skip": False}
        )

    def on_download_finished(self, success_count, fail_count):
        """다운로드 완료 후 상태 정리 (View → Controller 이관).

        View는 이 메서드를 호출만 하고, 실제 상태 초기화와 후처리는
        Controller가 담당한다. 사운드 재생/폴더 열기는 UI 전용 로직이므로
        View에서 유지한다.
        """
        self.end_download()

        if success_count > 0:
            # 분석 데이터 초기화 — 다음 URL 입력 시 깨끗한 상태로 시작
            self.view.extracted_data = {"info": None, "v_list": [], "a_list": []}

    def request_cancel(self):
        if self.running:
            self.state["canceled"] = True
        elif self.analyzing:
            self._abandon_analyzer()

    def request_skip(self):
        if self.running:
            self.state["skip"] = True

    ### ── 다운로드 워커 생명주기 ─────────────────────────────────
    def spawn_worker(
        self,
        targets,
        cfg,
        video_id,
        audio_id,
        is_live_hint=False,
        v_spec=None,
        audio_desc="",
        yt_client="auto",
    ):
        """DownloadWorker 생성 + 시그널 연결 + 구동.

        yt_client: 분석 단계에서 실증·통과한 YouTube player_client.
        다운로드가 분석과 같은 클라이언트를 쓰도록 강제 (0% 스톨 방지).
        """
        v = self.view
        w = DownloadWorker(
            targets,
            cfg,
            self.state,
            video_id,
            audio_id,
            is_live_hint=is_live_hint,
            v_spec=v_spec,
            audio_desc=audio_desc,
            yt_client=yt_client,
        )
        w.finished_all.connect(v.on_download_finished)
        self.worker_dl = w
        w.start()

    def shutdown(self, wait_ms=1000):
        """앱 종료 시 활성 스레드 및 좀비 스레드 안전 중단 (closeEvent용)."""
        if self.worker_dl and self.worker_dl.isRunning():
            self.state["canceled"] = True
            self.worker_dl.wait(wait_ms)

        for w in list(self._zombie_workers):
            if w.isRunning():
                w.wait(1500)

        # POT 서버 워커 정리는 POTManager.cancel()이 담당 (MainWindow.closeEvent에서 호출)


# ── 하위 호환성 유지 (기존 코드에서 DownloadController로 참조 가능) ──
DownloadController = MediaController

```

## File: cookies.py

```python
﻿### cookies.py - 브라우저 쿠키 추출 (Firefox / Chromium 계열)
import glob
import os
import platform
import shutil
import sqlite3
import tempfile

import log_history

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
                os.path.join(localappdata, "Microsoft", "Edge", "User Data", "Default"),
            ]
        elif sys_name == "Darwin":
            paths = [
                os.path.join(home, "Library", "Application Support", "Firefox", "Profiles")
            ]

        for p in paths:
            if not os.path.exists(p):
                continue
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
                            cur.execute("SELECT host, name, value FROM moz_cookies")
                            for host, n, v in cur.fetchall():
                                if host not in cookie_data:
                                    cookie_data[host] = {}
                                cookie_data[host][n] = v
                            conn.close()
                            shutil.rmtree(td, ignore_errors=True)
                else:
                    cf = os.path.join(p, "Network", "Cookies")
                    if not os.path.exists(cf):
                        cf = os.path.join(p, "Cookies")
                    if os.path.exists(cf):
                        td = tempfile.mkdtemp()
                        tdb = os.path.join(td, "Cookies")
                        shutil.copy2(cf, tdb)
                        conn = sqlite3.connect(tdb)
                        cur = conn.cursor()
                        # host_key와 name, value를 함께 조회
                        cur.execute("SELECT host_key, name, value FROM cookies")
                        for host, n, v in cur.fetchall():
                            if host not in cookie_data:
                                cookie_data[host] = {}
                            cookie_data[host][n] = v
                        conn.close()
                        shutil.rmtree(td, ignore_errors=True)
            except Exception as e:
                # [증거 남김] DB 잠금/권한 실패는 '쿠키가 있는데도 401' 증상의
                # 유일한 추적 단서 — 흡수는 유지하고 원인만 히스토리에 남긴다.
                import raw_log
                from log_event import LogEvent
                raw_log.raw(
                    "cookie",
                    LogEvent(
                        stage="CK", status="WARN", platform="cookie",
                        msg=f"cookie DB read failed ({os.path.basename(p)}): {type(e).__name__}: {e}",
                        is_error=False,
                    ),
                    to_tui=False,
                )
                continue
    except Exception:
        pass
    return cookie_data

```

## File: dialogs.py

```python
##### 팝업 다이얼로그 모음
import os
import updater
from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
import theme
import log_console
from log_console import emit_component

try:
    import winsound
except ImportError:
    winsound = None

def show_info_message(parent, title, text, detail=None, is_error=False):
    msg_box = QMessageBox(parent)
    msg_box.setIcon(QMessageBox.Icon.NoIcon)
    msg_box.setWindowTitle(title)
    # Prepend monochrome icon
    prefix = "▲  " if is_error else "✓  "
    msg_box.setText(prefix + text)
    if detail:
        msg_box.setDetailedText(detail)
    msg_box.setStyleSheet(theme.MSGBOX_QSS)
    msg_box.addButton(
        "OK" if not is_error else "Close", QMessageBox.ButtonRole.AcceptRole
    )

    # Programmatic text alignment centering for success / left alignment for error
    label = msg_box.findChild(QLabel)
    if label:
        if is_error:
            label.setAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )
        else:
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)

    msg_box.exec()


class CustomComboBox(QComboBox):
    """표준 QComboBox 기반 콤보 — addItem(text, userData, icon) 계약 유지.

    [qfluentwidgets 의존 제거] 실제로 쓰던 기능은 시그니처 정규화뿐이었고,
    표준 위젯 + 다이얼로그 QSS로 통일해 PyQt-Fluent-Widgets 의존을 뗀다.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

    def addItem(self, text, userData=None, icon=None):
        if icon is not None:
            super().addItem(icon, text)
        else:
            super().addItem(text)
        if userData is not None:
            self.setItemData(self.count() - 1, userData)


class ExitConfirmDialog(QDialog):
    def __init__(self, parent=None, is_running=False):
        super().__init__(parent)
        self.is_running = is_running
        self.setWindowTitle("ChzzkTube")
        self.setFixedSize(360, 130)
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint
        )
        vbox = QVBoxLayout(self)
        vbox.setSpacing(15)
        vbox.setContentsMargins(20, 20, 20, 20)

        # 1. 상태별 문구 직관화 (따옴표 제거 및 명확한 의도 전달)
        if self.is_running:
            msg = "⚠️ A download is in progress.\nStop and exit ChzzkTube?"
        else:
            msg = "Exit ChzzkTube?"

        lbl = QLabel(msg)
        lbl.setWordWrap(True)
        lbl.setStyleSheet("font-size: 12px; color: #e3e3e3; line-height: 1.4;")
        vbox.addWidget(lbl)

        btn_box = QHBoxLayout()
        btn_box.setSpacing(10)

        btn_exit = QPushButton("Exit")
        btn_exit.setStyleSheet(theme.BTN_EXIT_DANGER_QSS)
        btn_exit.clicked.connect(lambda: self.done(1))

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setStyleSheet(theme.BTN_NEUTRAL_QSS)
        btn_cancel.clicked.connect(lambda: self.done(0))

        btn_box.addWidget(btn_exit)
        btn_box.addWidget(btn_cancel)

        vbox.addLayout(btn_box)


class CookieSelectDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.selected_type = None
        self.selected_path = ""
        self.setWindowTitle("쿠키 불러오기...")
        self.setFixedSize(300, 380)
        self.setStyleSheet(theme.DIALOG_BG_QSS)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(8)

        buttons = [
            ("Cookies.txt", "file"),
            ("Chrome", "chrome"),
            ("Firefox", "firefox"),
            ("Edge", "edge"),
            ("Opera", "opera"),
            ("Brave", "brave"),
            ("Vivaldi", "vivaldi"),
            ("Chromium", "chromium"),
            ("Whale", "whale"),
        ]

        for text, b_type in buttons:
            btn = QPushButton(text)
            btn.setStyleSheet(theme.BTN_GRID_QSS)
            btn.clicked.connect(lambda checked, t=b_type: self.on_select(t))
            layout.addWidget(btn)

    def on_select(self, b_type):
        if b_type == "file":
            path, _ = QFileDialog.getOpenFileName(
                self,
                "Netscape HTTP Cookie Files",
                "",
                "Text Files (*.txt);;All Files (*.*)",
            )
            if path:
                self.selected_type = "cookie_file"
                self.selected_path = path
                self.accept()
        else:
            if b_type in ["chrome", "edge", "whale", "chromium", "brave", "vivaldi"]:
                try:
                    import yt_dlp.cookies
                    yt_dlp.cookies.extract_cookies_from_browser(b_type)
                except Exception as ex:
                    show_info_message(
                        self,
                        "Error",
                        f"Failed to read browser ({b_type}) cookies.\n\nThe browser may be running, or\nsecurity policy (permission denied) blocks access.",
                        detail=str(ex),
                        is_error=True,
                    )
                    return

            self.selected_type = b_type
            self.selected_path = ""
            self.accept()


class ActionCountdownDialog(QDialog):
    def __init__(self, action_type, parent=None):
        super().__init__(parent)
        self.action_type = action_type
        self.remaining_seconds = 60
        action_names = {
            "sleep": "sleep",
            "shutdown": "PC shutdown",
            "exit_app": "exit",
        }
        self.action_name = action_names.get(action_type, "unknown action")
        self.setWindowTitle("Post-Download Action")
        self.setFixedSize(380, 160)
        self.setStyleSheet("background-color: #121212; color: #ffffff;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        self.lbl_msg = QLabel(
            f"Download complete.\n<b>{self.remaining_seconds}s</b> until [<b>{self.action_name}</b>] runs."
        )
        self.lbl_msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_msg.setStyleSheet("font-size: 13px; color: #e0e0e0;")
        layout.addWidget(self.lbl_msg)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.btn_now = QPushButton("Run Now")
        self.btn_now.setStyleSheet(
            "QPushButton { background-color: #c62828; color: white; font-weight: bold; padding: 6px; border-radius: 6px; border: none; } QPushButton:hover { background-color: #e53935; } QPushButton:pressed { background-color: #b71c1c; }"
        )
        self.btn_now.clicked.connect(self.execute_now)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setStyleSheet(
            "QPushButton { background-color: #2b2b2b; color: #e3e3e3; border: 1px solid #3d3d3d; font-weight: bold; padding: 6px; border-radius: 6px; } QPushButton:hover { background-color: #353535; border-color: #4a4a4a; }"
        )
        self.btn_cancel.clicked.connect(self.cancel_action)

        btn_layout.addWidget(self.btn_now)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)

        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.update_timer)
        self.timer.start()

    def update_timer(self):
        self.remaining_seconds -= 1
        if self.remaining_seconds <= 0:
            self.timer.stop()
            self.accept()
        else:
            self.lbl_msg.setText(
                f"Download complete.\n<b>{self.remaining_seconds}s</b> until [<b>{self.action_name}</b>] runs."
            )

    def execute_now(self):
        self.timer.stop()
        self.accept()

    def cancel_action(self):
        self.timer.stop()
        self.reject()


class CookieViewerDialog(QDialog):
    def __init__(self, title_text, content_text, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title_text)
        self.setFixedSize(650, 500)
        self.setStyleSheet(theme.DIALOG_BG_QSS)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        self.te_content = QTextEdit(self)
        self.te_content.setReadOnly(True)
        self.te_content.setPlainText(content_text)
        self.te_content.setStyleSheet(theme.TE_CONTENT_QSS)
        layout.addWidget(self.te_content)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        btn_close = QPushButton("Close")
        btn_close.setFixedWidth(90)
        btn_close.setStyleSheet(theme.BTN_CLOSE_QSS)
        btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)


# [raw 상세 로그] DEPS 확인 시 실제 CLI를 실행해 셸에서 친 것과 동일한 원문을
# F12 상세 로그에 기록한다. yt-dlp --version → '2026.08.19', streamlink
# --version → 'streamlink 8.5.0' 식의 터미널 출력 그대로.
class SettingsDialog(QDialog):
    def __init__(self, parent=None, is_running=False):
        super().__init__(parent)
        self.parent_win = parent
        self.cfg = parent.cfg
        self.is_running = is_running
        self._loading = True  # 초기 값 주입 중에는 저장 스킵
        self.setWindowTitle("설정")
        self.setFixedSize(480, 640)
        self.setStyleSheet( "QDialog { background-color: #0d0d0d; color: #d4d4d4; }" "QLabel { color: #cccccc; font-size: 11px; }" "QLabel[role=\"key\"] { color: #4ec9b0; font-weight: bold; }" "QCheckBox { color: #d4d4d4; spacing: 6px; }" "QCheckBox::indicator { width: 14px; height: 14px; border: 1px solid #2a2a2a; background: #161616; border-radius: 2px; }" "QCheckBox::indicator:checked { background: #4ec9b0; border-color: #4ec9b0; }" "QPushButton { background: #161616; color: #d4d4d4; border: 1px solid #2a2a2a; padding: 4px 12px; font-size: 11px; }" "QPushButton:hover { border-color: #4ec9b0; color: #4ec9b0; }" "QPushButton:disabled { color: #555555; border-color: #1a1a1a; }" "QComboBox { background: #161616; color: #d4d4d4; border: 1px solid #2a2a2a; padding: 4px 8px; font-size: 11px; }" "QComboBox:hover { border-color: #4ec9b0; }" "QComboBox::drop-down { border: none; width: 18px; }" "QComboBox QAbstractItemView { background: #161616; color: #d4d4d4; border: 1px solid #2a2a2a; selection-background-color: #264f78; outline: none; }" )
        self.init_ui()
        self.load_settings()
        self._loading = False

    def closeEvent(self, event):
        event.accept()

    def init_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(theme.SETTINGS_SCROLL_QSS)
        body = QWidget()
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        layout = QVBoxLayout(body)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 14, 16, 14)
        # TUI 패널 일체화 — 다크 콘솔 + 민트 액센트

        def make_combo(options, width):
            cb = CustomComboBox()
            cb.setFixedWidth(width)
            for k, v in options:
                cb.addItem(v, k)
            return cb

        row1 = QHBoxLayout()
        _sec1 = QGroupBox("Container")
        _sec1.setProperty("class", "tui-panel")
        _sec1.setLayout(row1)
        row1.addWidget(QLabel("Container"))
        row1.addStretch()
        self.cb_container = make_combo(
            [
                ("mkv", "mkv (general / full subtitle support)"),
                ("mp4", "mp4 (mobile & universal player)"),
                ("webm", "webm (web upload & efficient)"),
            ],
            250,
        )
        self.cb_container.currentIndexChanged.connect(
            lambda: self._apply_change("container", self.cb_container.currentData())
        )
        row1.addWidget(self.cb_container)
        layout.addWidget(_sec1)

        cookie_box = QFrame()
        cookie_box.setObjectName("cookie_section")
        cookie_box.setProperty("class", "tui-panel")
        try:
            cookie_box.setTitle("Cookie")
        except Exception:
            pass
        cookie_box.setObjectName("cookie_box")
        cookie_box.setStyleSheet(
            "QFrame#cookie_box { border: 1px solid #3d3d3d; border-radius: 6px; background-color: #1e1e1e; }"
        )
        cookie_layout = QVBoxLayout(cookie_box)
        cookie_layout.setContentsMargins(12, 10, 12, 10)
        cookie_layout.setSpacing(8)

        cookie_lbl = QLabel("Cookie (age / membership)")
        cookie_lbl.setStyleSheet(theme.DLG_SECTION_TITLE_QSS)
        cookie_layout.addWidget(cookie_lbl)

        self.lbl_cookie_status = QLabel(self._cookie_status_text())
        self.lbl_cookie_status.setStyleSheet(theme.DLG_STATUS_QSS)
        cookie_layout.addWidget(self.lbl_cookie_status)

        c_hlay = QHBoxLayout()
        c_hlay.setSpacing(8)
        self.cookie_buttons = []
        for text, func in [
            ("View...", self.view_cookie),
            ("Load...", self.load_cookie),
            ("Reset", self.reset_cookie),
        ]:
            btn = self._ghost_btn(text, func)
            self.cookie_buttons.append(btn)
            c_hlay.addWidget(btn, 1)
        cookie_layout.addLayout(c_hlay)

        yt_hlay = QHBoxLayout()
        yt_hlay.setSpacing(8)
        yt_hlay.addWidget(QLabel("YouTube Client"))
        yt_hlay.addStretch()
        self.cb_yt_client = make_combo(
            [
                ("auto", "auto (default)"),
                ("tv", "tv (age-gated recommended)"),
                ("web_safari", "web_safari (session invalid)"),
                ("tv_simply", "tv_simply"),
                ("mweb", "mweb"),
            ],
            210,
        )
        self.cb_yt_client.currentIndexChanged.connect(
            lambda: self._apply_change(
                "yt_player_client", self.cb_yt_client.currentData()
            )
        )
        yt_hlay.addWidget(self.cb_yt_client)
        cookie_layout.addLayout(yt_hlay)
        layout.addWidget(cookie_box)

        opt_lbl = QLabel("Download Options")
        opt_lbl.setStyleSheet(theme.DLG_SECTION_TITLE_QSS)
        layout.addWidget(opt_lbl)

        self.chk_sub = QCheckBox()
        self.chk_audio = QCheckBox()
        self.chk_dedup = QCheckBox()
        self.chk_fast = QCheckBox()
        self.chk_auto_open = QCheckBox()
        self.chk_sound = QCheckBox()

        self.chk_sub.toggled.connect(
            lambda v: self._apply_change("embed_subtitles", v)
        )
        self.chk_audio.toggled.connect(self._on_audio_only_toggled)
        self.chk_dedup.toggled.connect(
            lambda v: self._apply_change("remove_duplicates", v)
        )
        self.chk_fast.toggled.connect(lambda v: self._apply_change("fast_download", v))
        self.chk_auto_open.toggled.connect(
            lambda v: self._apply_change("auto_open_folder", v)
        )
        self.chk_sound.toggled.connect(lambda v: self._apply_change("play_sound", v))

        chk_items = [
            (self.chk_sub, "Embed subtitles (SRT auto-convert + merge)"),
            (self.chk_audio, "Audio only (MP3)"),
            (self.chk_dedup, "Auto-remove duplicate URLs"),
            (self.chk_fast, "Fast segmented download (5 threads)"),
            (self.chk_auto_open, "Open folder on finish"),
            (self.chk_sound, "Play completion sound"),
        ]

        chk_style = """
            QCheckBox {
                background: transparent;
                border: none;
                outline: none;
            }
            QCheckBox::indicator:unchecked {
                width: 14px;
                height: 14px;
                border: 1.5px solid #888888;
                border-radius: 3px;
                background-color: #1e1e1e;
                image: none;
            }
            QCheckBox[custom_hover="true"]::indicator:unchecked {
                width: 14px;
                height: 14px;
                border: 1.5px solid #d4d4d4;
                border-radius: 3px;
                background-color: #d4d4d4;
                image: none;
            }
            QCheckBox::indicator:checked {
                width: 14px;
                height: 14px;
                border: 1.5px solid #d4d4d4;
                border-radius: 3px;
                background-color: #d4d4d4;
                image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='14' height='14' viewBox='0 0 24 24' fill='none' stroke='%231e1e1e' stroke-width='3.5' stroke-linecap='round' stroke-linejoin='round'><polyline points='20 6 9 17 4 12'/></svg>");
            }
            QCheckBox[custom_hover="true"]::indicator:checked {
                width: 14px;
                height: 14px;
                border: 1.5px solid #ffffff;
                border-radius: 3px;
                background-color: #ffffff;
                image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='14' height='14' viewBox='0 0 24 24' fill='none' stroke='%231e1e1e' stroke-width='3.5' stroke-linecap='round' stroke-linejoin='round'><polyline points='20 6 9 17 4 12'/></svg>");
            }
        """

        def update_chk_style(c):
            c.style().unpolish(c)
            c.style().polish(c)

        for chk, text in chk_items:
            chk.setStyleSheet(chk_style)
            chk.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            chk.setProperty("custom_hover", False)
            chk.setProperty("suppress_hover", False)

            lbl = QLabel(text)
            lbl.setStyleSheet(
                "color: #d4d4d4; background: transparent; font-size: 12px;"
            )
            lbl.setCursor(Qt.CursorShape.PointingHandCursor)
            lbl.mousePressEvent = lambda event, c=chk: (
                c.toggle() if c.isEnabled() else None
            )

            chk.toggled.connect(
                lambda checked, c=chk: (
                    (
                        c.setProperty("suppress_hover", True),
                        c.setProperty("custom_hover", False),
                        update_chk_style(c),
                    )
                    if not checked
                    else None
                )
            )

            row_widget = QFrame()
            row_widget.setStyleSheet(
                "QFrame { background: transparent; border: none; }"
            )
            row_chk = QHBoxLayout(row_widget)
            row_chk.setSpacing(8)
            row_chk.setContentsMargins(0, 2, 0, 2)
            row_chk.addWidget(chk)
            row_chk.addWidget(lbl)
            row_chk.addStretch()

            def on_enter(e, c=chk):
                if not c.property("suppress_hover"):
                    c.setProperty("custom_hover", True)
                    update_chk_style(c)

            def on_leave(e, c=chk):
                c.setProperty("suppress_hover", False)
                c.setProperty("custom_hover", False)
                update_chk_style(c)

            row_widget.enterEvent = on_enter
            row_widget.leaveEvent = on_leave

            layout.addWidget(row_widget)

        row2 = QHBoxLayout()
        _sec2 = QGroupBox("Video Quality")
        _sec2.setProperty("class", "tui-panel")
        _sec2.setLayout(row2)
        row2.addWidget(QLabel("작업 완료 후 동작"))
        row2.addStretch()
        self.cb_completion = make_combo(
            [
                ("none", "사용 안 함"),
                ("sleep", "절전 모드 진입"),
                ("shutdown", "PC 자동 종료"),
                ("exit_app", "프로그램 종료"),
            ],
            250,
        )
        self.cb_completion.currentIndexChanged.connect(
            lambda: self._apply_change(
                "completion_action", self.cb_completion.currentData()
            )
        )
        row2.addWidget(self.cb_completion)
        layout.addWidget(_sec2)

        row3 = QHBoxLayout()
        _sec3 = QGroupBox("Format Picker")
        _sec3.setProperty("class", "tui-panel")
        _sec3.setLayout(row3)
        row3.addWidget(QLabel("해상도 제한"))
        row3.addStretch()
        self.cb_max_res = make_combo(
            [
                ("none", "(무제한)"),
                ("2160", "4K (2160p)"),
                ("1440", "2K (1440p)"),
                ("1080", "1080p"),
                ("720", "720p"),
                ("480", "480p"),
                ("360", "360p"),
            ],
            140,
        )
        self.cb_max_res.currentIndexChanged.connect(
            lambda: self._apply_change("max_video_res", self.cb_max_res.currentData())
        )
        row3.addWidget(self.cb_max_res)
        row3.addSpacing(12)
        self.chk_pick = QCheckBox("포맷 직접 고르기 (최고 품질 off)")
        self.chk_pick.toggled.connect(lambda on: self._apply_change("pick_format", on))
        row3.addWidget(self.chk_pick)
        layout.addWidget(_sec3)

        format_layout = QHBoxLayout()
        _sec_filename = QGroupBox("Filename")
        _sec_filename.setProperty("class", "tui-panel")
        _flay = QVBoxLayout(_sec_filename)
        _flay.setContentsMargins(10, 6, 10, 6)
        _flay.setSpacing(6)
        _flay.addWidget(QLabel("파일명 형식"))
        format_layout.addStretch()
        self.cb_prefix = make_combo(
            [
                ("none", "(없음)"),
                ("uploader", "[채널명]"),
                ("date_dash_uploader", "YYYY-MM-DD [채널명]"),
                ("date_compact_uploader", "YYYYMMDD [채널명]"),
                ("date_dash", "YYYY-MM-DD"),
                ("date_compact", "YYYYMMDD"),
            ],
            140,
        )
        self.cb_prefix.currentIndexChanged.connect(
            lambda: self._apply_change("filename_prefix", self.cb_prefix.currentData())
        )
        format_layout.addWidget(self.cb_prefix)

        lbl_title = QLabel("제목")
        lbl_title.setFixedWidth(45)
        lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_title.setStyleSheet(
            "font-weight: bold; background: transparent; border: none;"
        )
        format_layout.addWidget(lbl_title)

        self.cb_suffix = make_combo(
            [
                ("id_res_fps", "[ID] [해상도] [fps]"),
                ("id_res", "[ID] [해상도]"),
                ("id", "[ID]"),
            ],
            130,
        )
        self.cb_suffix.currentIndexChanged.connect(
            lambda: self._apply_change("filename_suffix", self.cb_suffix.currentData())
        )
        format_layout.addWidget(self.cb_suffix)
        _flay.addLayout(format_layout)

        self.lbl_filename_preview = QLabel("미리보기  :  동영상제목.mp4")
        self.lbl_filename_preview.setStyleSheet(
            "color: #64b5f6; font-size: 11px; padding-left: 2px;"
        )
        _flay.addWidget(self.lbl_filename_preview)
        layout.addWidget(_sec_filename)

        self.cb_prefix.currentIndexChanged.connect(self.update_filename_preview)
        self.cb_suffix.currentIndexChanged.connect(self.update_filename_preview)
        self.cb_container.currentIndexChanged.connect(self.update_filename_preview)
        self.update_filename_preview()

        # ── Update Channel 섹션 ──
        update_row = QHBoxLayout()
        _sec_update = QGroupBox("Update Channel")
        _sec_update.setProperty("class", "tui-panel")
        _sec_update.setLayout(update_row)
        update_row.addWidget(QLabel("채널"))
        update_row.addStretch()
        self.cb_update_channel = make_combo(
            [
                ("stable", "Stable (안정)"),
                ("nightly", "Nightly (최신 우회)"),
            ],
            140,
        )
        self.cb_update_channel.currentIndexChanged.connect(
            lambda: self._apply_change("update_channel", self.cb_update_channel.currentData())
        )
        update_row.addWidget(self.cb_update_channel)
        update_row.addSpacing(12)
        self.chk_auto_update = QCheckBox("시작 시 자동 확인")
        self.chk_auto_update.toggled.connect(lambda on: self._apply_change("auto_update_check", on))
        update_row.addWidget(self.chk_auto_update)
        layout.addWidget(_sec_update)

        layout.addStretch()

    def update_filename_preview(self):
        import datetime
        today = datetime.datetime.now()
        date_dash = today.strftime("%Y-%m-%d")
        date_compact = today.strftime("%Y%m%d")

        prefix_map = {
            "none": "",
            "uploader": "[채널명] ",
            "date_dash_uploader": f"{date_dash} [채널명] ",
            "date_compact_uploader": f"{date_compact} [채널명] ",
            "date_dash": f"{date_dash} ",
            "date_compact": f"{date_compact} ",
        }
        suffix_map = {
            "id_res_fps": " [PLCAxEuddBvAs] [1080p] [60fps]",
            "id_res": " [PLCAxEuddBvAs] [1080p]",
            "id": " [PLCAxEuddBvAs]",
        }
        p_text = prefix_map.get(self.cb_prefix.currentData(), "")
        s_text = suffix_map.get(self.cb_suffix.currentData(), "")
        ext = self.cb_container.currentData()
        preview_str = f"미리보기  :  {p_text}동영상제목{s_text}.{ext}"
        self.lbl_filename_preview.setText(preview_str)

    def load_settings(self):
        def set_combo(cb, val):
            idx = cb.findData(val)
            if idx >= 0:
                cb.setCurrentIndex(idx)

        set_combo(self.cb_container, self.cfg.get("container", "mkv"))
        set_combo(self.cb_completion, self.cfg.get("completion_action", "none"))
        set_combo(self.cb_prefix, self.cfg.get("filename_prefix", "none"))
        set_combo(self.cb_suffix, self.cfg.get("filename_suffix", "id"))
        set_combo(self.cb_yt_client, self.cfg.get("yt_player_client", "auto"))
        set_combo(self.cb_update_channel, self.cfg.get("update_channel", "stable"))
        set_combo(self.cb_max_res, self.cfg.get("max_video_res", "none"))
        self.chk_pick.setChecked(self.cfg.get("pick_format", False))

        self.chk_sub.setChecked(self.cfg.get("embed_subtitles", False))
        self.chk_audio.setChecked(self.cfg.get("audio_only", False))
        self.chk_dedup.setChecked(self.cfg.get("remove_duplicates", True))
        self.chk_fast.setChecked(self.cfg.get("fast_download", True))
        self.chk_auto_open.setChecked(self.cfg.get("auto_open_folder", True))
        self.chk_sound.setChecked(self.cfg.get("play_sound", True))
        self.chk_auto_update.setChecked(self.cfg.get("auto_update_check", True))

    def view_cookie(self):
        cookie_src = self.cfg.get("browser_cookie", "none")
        content = "로드된 쿠키가 없습니다."
        if cookie_src == "cookie_file" and os.path.exists(
            self.cfg.get("cookie_file_path", "")
        ):
            try:
                with open(self.cfg["cookie_file_path"], "r", encoding="utf-8") as f:
                    content = f.read(5000) + (
                        "\n... (생략)"
                        if os.path.getsize(self.cfg["cookie_file_path"]) > 5000
                        else ""
                    )
            except Exception as ex:
                content = f"파일 읽기 오류: {ex}"
        elif cookie_src not in ["none", "auto"]:
            try:
                from cookies import get_browser_cookies
                cookie_data = get_browser_cookies()
                if cookie_data:
                    lines = []
                    for host, kv_dict in cookie_data.items():
                        lines.append(f"[{host}]")
                        for k, v in kv_dict.items():
                            lines.append(f"  {k} = {v}")
                        lines.append("")
                    content = f"[{cookie_src}] 브라우저 추출 전체 쿠키 목록:\n\n" + "\n".join(lines)
                else:
                    content = f"[{cookie_src}] 브라우저에서 쿠키를 가져오지 못했습니다. (브라우저 실행 중 또는 권한 문제)"
            except Exception as ex:
                content = f"쿠키 조회 중 오류 발생: {ex}"
        viewer = CookieViewerDialog("쿠키 뷰어 (상세)", content, self)
        viewer.exec()

    def load_cookie(self):
        dlg = CookieSelectDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.cfg["browser_cookie"] = dlg.selected_type
            self.cfg["cookie_file_path"] = dlg.selected_path
            self.parent_win.save_cfg()
            self._refresh_cookie_status()
            show_info_message(
                self, "성공", f"쿠키 설정이 완료되었습니다.\n({dlg.selected_type})"
            )

    def reset_cookie(self):
        self.cfg["browser_cookie"] = "none"
        self.cfg["cookie_file_path"] = ""
        self.parent_win.save_cfg()
        self._refresh_cookie_status()
        show_info_message(self, "초기화", "쿠키가 초기화되었습니다.")

    def _ghost_btn(self, text, handler):
        btn = QPushButton(text)
        btn.setEnabled(not self.is_running)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedHeight(28)
        btn.setStyleSheet(theme.DLG_GHOST_BTN_QSS)
        btn.clicked.connect(handler)
        return btn

    def _cookie_status_text(self):
        src = self.cfg.get("browser_cookie", "none")
        names = {
            "none": "사용 안 함",
            "auto": "자동 (브라우저 탐색)",
            "cookie_file": "Cookies.txt 파일",
        }
        label = names.get(src, f"브라우저 직접 추출 ({src})")
        if src == "cookie_file" and self.cfg.get("cookie_file_path"):
            label += f" — {os.path.basename(self.cfg['cookie_file_path'])}"
        return f"현재: {label}"

    def _refresh_cookie_status(self):
        self.lbl_cookie_status.setText(self._cookie_status_text())

    def _apply_change(self, key, value):
        if getattr(self, "_loading", False):
            return
        self.cfg[key] = value
        self.parent_win.save_cfg()

    def _on_audio_only_toggled(self, on):
        self._apply_change("audio_only", on)
        self.parent_win.update_ui_state()
class VerboseLogWindow(QDialog):
    """상세(Full Detailed) 로그 전용 서브 윈도우 — 메인 뷰에서 상세 로그 탭을
    분리해 접근한다(F12). MainWindow가 외부로 유출하는 상세 로그를 그대로
    미러링하며, 항상 하단(최신)을 팔로우한다."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Full Log (F12)")
        self.resize(760, 480)

        self.te = QTextEdit(self)
        self.te.setReadOnly(True)
        self.te.setStyleSheet(theme.TE_CONTENT_QSS)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(self.te)

        btn_row = QHBoxLayout()
        self.lbl_info = QLabel("")
        self.lbl_info.setStyleSheet(theme.DLG_STATUS_QSS)
        btn_close = QPushButton("Close")
        btn_close.setStyleSheet(theme.BTN_NEUTRAL_QSS)
        btn_close.clicked.connect(self.close)
        btn_row.addWidget(self.lbl_info)
        btn_row.addStretch(1)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

    def append(self, msg, is_status=False):
        """Mirror raw text — timestamps pre-applied by _mirror_full_log."""
        if not msg:
            return
        if is_status:
            cursor = self.te.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock, QTextCursor.MoveMode.KeepAnchor)
            cursor.removeSelectedText()
            cursor.insertText(str(msg))
        else:
            self.te.append(msg)
        sb = self.te.verticalScrollBar()
        sb.setValue(sb.maximum())
        self.lbl_info.setText(f"mirroring — {self.te.document().blockCount()} lines")

    def set_content(self, text):
        """Replace all content at once (initial display)."""
        self.te.setPlainText(text)
        self.lbl_info.setText(f"buffer — {self.te.document().blockCount()} lines")

```

## File: dl_context.py

```python
### dl_context.py - 다운로드 파이프라인 컨텍스트 (D: worker grab-bag 해결)
"""DownloadWorker가 파이프라인 모듈에 넘기는 명시적 컨텍스트.

[문제] target_downloader/progress_emitter/finalizer가 worker 객체를 통째로
받아 worker.cfg, worker.logger, worker._speed_win 등을 암시적으로 접근.
"worker가 뭘 제공하는지"가 불명확해 신규 파이프라인 추가 시 계약을 알 수 없다.

[해결] 아래 dataclass로 계약을 명시한다. DownloadWorker는 자신의 상태에서
DownloadContext를 생성해 파이프라인에 넘기고, 파이프라인은 이 컨텍스트만 본다.
Qt Signal(YtLoggerBridge)은 그대로 참조로 전달된다 (QThread 상속 구조 유지).
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class DownloadContext:
    """다운로드 파이프라인 함수들이 소비하는 컨텍스트.

    DownloadWorker 인스턴스에서 extract()로 생성된다.
    파이프라인 모듈(target_downloader, progress_emitter, finalizer)은
    worker 객체 대신 이 컨텍스트만 받아 명시적 계약을 이행한다.
    """

    # 설정 (worker.cfg 딕셔너리 참조)
    cfg: Dict[str, Any]

    # 포맷 선택 ("auto"면 자동 선택)
    v_sel: str = "auto"
    a_sel: str = "auto"

    # 비디오 스펙 (v_list[0]에서 추출된 height/fps 등)
    v_spec: Dict[str, Any] = field(default_factory=dict)

    # 오디오 설명 (a_list[0]에서 추출)
    audio_desc: str = ""

    # 로거 (YtLoggerBridge — raw 버스 직행 어댑터)
    logger: Any = None

    # 현재 처리 중인 대상
    current_url: str = ""
    current_file: Optional[str] = None

    # 세션 상태 (UI→워커 단방향: canceled, skip)
    state: Dict[str, bool] = field(default_factory=lambda: {"canceled": False, "skip": False})

    # 속도 계산 (SpeedWindow — 이동평균)
    speed_win: Any = None

    # 배치 진행 현황
    total_count: int = 0
    current_idx: int = 0

    # 라이브 관련
    is_live_hint: bool = False
    live_partially_saved: bool = False

    # 포맷 선택 (분석 단계에서 결정된 클라이언트)
    yt_client: str = "auto"

    # 대상 목록 (expand_targets에서 참조)
    targets: list = field(default_factory=list)

    # 배치 완료 시그널 (DownloadWorker.finished_all 바인딩)
    finished_all: Any = None

    # 오류 수집 (다운로드 실패 시 메시지 누적)
    _errors: List[str] = field(default_factory=list, repr=False)

    def add_error(self, msg: str) -> None:
        """오류 메시지를 수집한다. finalizer가 배치 마감에서 참조한다."""
        self._errors.append(msg)

    @property
    def errors(self) -> List[str]:
        """수집된 오류 목록 (읽기 전용)."""
        return list(self._errors)

    def advance_target(self, idx: int, url: str) -> None:
        """타겟 진행 상태를 단일 지점에서 안전하게 업데이트하고 속도계 윈도우를 초기화한다."""
        self.current_idx = idx
        self.current_url = url
        self.current_file = None
        self._meta_logged = False
        if self.speed_win:
            self.speed_win.reset()
```

## File: dl_platform.py

```python
##### dl_platform.py - 다운로더 플랫폼/콘텐츠 타입 감별
"""URL 문자열에서 플랫폼(youtube/chzzk/streamlink 등)과 콘텐츠 타입을 판정한다.

표준 라이브러리 `platform`과의 이름 충돌을 피하기 위해 `dl_platform`으로
명명 — downloader.target_downloader / AnalyzeWorker 공용.

플랫폼 축약기호는 media.platform_short()를 사용한다.
"""
import re

# 도메인 → 플랫폼 추출기명 매핑 (동적 확장 가능)
# 우선순위: 위에서부터 매칭, 없으면 yt-dlp extractor에게 위임
_DOMAIN_EXTRACTORS = [
    # (도메인 패턴, extractor 이름)
    ("chzzk.naver.com", "chzzk"),
    ("twitch.tv", "twitch"),
    ("sooplive.co.kr", "sooplive"),
    ("soop.co.kr", "sooplive"),
    ("afreecatv.com", "afreecatv"),
    ("youtube.com", "youtube"),
    ("youtu.be", "youtube"),
    ("music.youtube.com", "youtube"),
    ("youtube-nocookie.com", "youtube"),
    ("instagram.com", "instagram"),
    ("tiktok.com", "tiktok"),
    ("facebook.com", "facebook"),
    ("twitter.com", "twitter"),
    ("x.com", "twitter"),
    ("bilibili.com", "bilibili"),
    ("dailymotion.com", "dailymotion"),
    ("vimeo.com", "vimeo"),
    ("soundcloud.com", "soundcloud"),
    ("naver.com", "naver"),
    ("kakao.com", "kakao"),
    ("fmkorea.com", "fmkorea"),
    ("theqoo.net", "theqoo"),
    ("clien.net", "clien"),
    ("dcinside.com", "dcinside"),
]


def _dl_platform(url):
    """URL 문자열에서 플랫폼 추출기명 추출.

    도메인 매핑 테이블에서 찾고, 없으면 'youtube'로 폴백
    (yt-dlp가 범용 처리하므로 대부분 동작).
    """
    if not url:
        return "youtube"
    u = str(url).lower()
    for pattern, extractor in _DOMAIN_EXTRACTORS:
        if pattern in u:
            return extractor
    return "youtube"  # 폴백: yt-dlp가 자동 감지


def _short_platform(p):
    """플랫폼 문자열을 TUI 컬럼 폭에 맞게 축약 (media.platform_short 위임)."""
    if not p or p == "-":
        return "-"
    try:
        from media import platform_short
        return platform_short(p)
    except ImportError:
        return str(p)[:8]


def detect_content_type(url, info=None):
    """콘텐츠 종류 판정.

    chzzk      → clip / vod / live / chzzk
    youtube url → playlist / live / video
    streamlink  → stream
    info(dict)에 is_live 가 있으면 live 우선.
    """
    if not url:
        return "video"
    u = str(url).lower()

    if "chzzk.naver.com" in u:
        if re.search(r"clips?/", u):
            return "clip"
        if re.search(r"video/\d+", u):
            return "vod"
        if "/live/" in u:
            return "live"
        return "chzzk"

    if (
        info
        and isinstance(info, dict)
        and info.get("is_live")
        and not info.get("is_playlist")
    ):
        return "live"

    if "youtube.com/playlist" in u or "playlist?list=" in u:
        return "playlist"
    if (
        "youtu.be" in u
        or "youtube.com/watch" in u
        or "youtube.com/shorts" in u
        or "youtube.com/live" in u
    ):
        if info and isinstance(info, dict) and info.get("is_live"):
            return "live"
        return "video"

    if "twitch.tv" in u or "sooplive.co.kr" in u or "afreecatv.com" in u:
        return "stream"

    return "video"
```

## File: downloader.py

```python
##### downloader.py - 다운로드 백그라운드 스레드
"""배치 다운로드 실행 워커 (DownloadWorker).

- 대상 평탄화·개별 분기(_td), 진행 틱(_pe), 배치 마감(_fin)을 worker 인자
  방식으로 호출하는 껝데기 오케스트레이션.
- [분리] YtLoggerBridge·AnalyzeWorker → analyze_worker.py / yt_logger_bridge.py.
  라우팅·종속 헬퍼는 각각의 전용 모듈에서만 import한다 (미사용 임포트 금지).
"""
import os
import yt_dlp

# [플러그인 기생 차단] analyze_worker.py와 동일 사유. 값 대입은 idempotent라
# 모듈 로딩 순서와 무관하게 안전 (첫 YoutubeDL 생성 전 1회 유효하면 된다).
yt_dlp.plugins.plugin_dirs.value = []

from PySide6.QtCore import QThread, Signal
from speed_window import SpeedWindow
from yt_logger_bridge import YtLoggerBridge
import raw_log
import progress_emitter as _pe
import target_downloader as _td
import finalizer as _fin

class DownloadWorker(QThread):
    # [v3.3.0] 로그는 raw 버스(raw_log.raw) 단일 경유 — log_concise/log_full 시그널 폐기.
    finished_all = Signal(int, int)

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
        self.logger = YtLoggerBridge()  # [v3.3.0] 버스 직행 — 시그널 인자 폐기
        self.total_count = len(targets)
        self.current_idx = 1
        self.current_url = None
        self._live_proc = None  # 라이브 녹화 프로세스 핸들 (앱 종료 시 정리용)

    def extract(self):
        """파이프라인 모듈에 넘길 DownloadContext를 생성한다 (D: 명시적 계약)."""
        from dl_context import DownloadContext

        return DownloadContext(
            cfg=self.cfg,
            v_sel=self.v_sel,
            a_sel=self.a_sel,
            v_spec=self.v_spec,
            audio_desc=self.audio_desc,
            logger=self.logger,
            current_url=self.current_url or "",
            current_file=self.current_file,
            state=self.state,
            speed_win=self._speed_win,
            total_count=self.total_count,
            current_idx=self.current_idx,
            is_live_hint=self.is_live_hint,
            live_partially_saved=self.live_partially_saved,
            yt_client=self.yt_client,
            targets=self.targets,
            finished_all=self.finished_all,
        )

    def _reset_loop_state(self):
        """매 타겟마다 필요한 상태 변수들을 한 번에 초기화 (worker 내부용)."""
        self._last_tick_t = 0.0
        self._tick_file = None
        self._tick_last = 0

    def run(self):
        """DownloadWorker 메인 스레드 — 하이퍼미니멀리즘 실행부."""
        ctx = self.extract()
        ctx.targets = _td.expand_targets(ctx)
        self.targets = ctx.targets  # 동기화 (current_file 등 내부 상태 유지)
        self.total_count = len(self.targets)
        failed_targets = []
        success_count = 0

        try:
            for idx, url in enumerate(self.targets, 1):
                ctx.advance_target(idx, url)
                self.current_idx = ctx.current_idx
                self.current_url = ctx.current_url

                if self.state["canceled"]:
                    break
                if self.state["skip"]:
                    self.state["skip"] = False
                    raw_log.raw(
                        "dl",
                        _pe.emit_dl("SKIP", "-", spec="-", speed="-", pct=None, bar_frac=None,
                                    msg=f"skipped ({idx}/{self.total_count})"),
                        to_tui=True,
                    )
                    continue

                if _td.download_target(ctx, url, failed_targets):
                    success_count += 1

            _fin.finalize(ctx, self.total_count, failed_targets, success_count)

        except Exception as ex:
            if "CANCELED_BY_USER" in str(ex) or "중지되었습니다" in str(ex) or self.state["canceled"]:
                pass
            else:
                raw_log.raw("dl", _pe.emit_err(str(ex)), to_tui=True)

            _fin.finalize(ctx, self.total_count, failed_targets, success_count)

    def terminate(self):
        """스레드 강제 종료 시 라이브 녹화 프로세스도 함께 정리."""
        if self._live_proc is not None:
            try:
                self._live_proc.kill()
                raw_log.raw(
                    "dl",
                    _pe.emit_event("DL", "WARN", "FFMP",
                                   "killed live recorder on worker terminate", is_error=True),
                    to_tui=True,
                )
            except Exception:
                pass
            self._live_proc = None
        super().terminate()

    def kill_live_process(self):
        """외부에서 라이브 녹화 프로세스만 강제 종료 (워커 스레드는 유지)."""
        if self._live_proc is not None:
            try:
                self._live_proc.kill()
                raw_log.raw(
                    "dl",
                    _pe.emit_event("DL", "WARN", "FFMP",
                                   "killed live recorder externally", is_error=True),
                    to_tui=True,
                )
            except Exception:
                pass
            self._live_proc = None


```

## File: finalizer.py

```python
"""finalizer.py - DownloadWorker의 _finalize 분할 — TUI 컬럼 포맷.

── Worker Contract ──────────────────────────────────────────────
본 모듈의 함수들이 요구하는 worker 객체의 인터페이스:
  worker.logger           : YtLoggerBridge — raw 버스 직행 (log_full/log_concise 시그널 폐기)
  worker.total_count      : int   — 전체 대상 수
  worker.current_url       : str   — 현재 처리 중인 URL (실패 시 참조)
──────────────────────────────────────────────────────────────────
"""
import os

import raw_log
from progress_emitter import emit_dl, emit_err


def finalize(ctx, total, failed_targets, success_count):
    """완료 요약 — TUI 컬럼 라인 1줄 + 개별 실패는 ERR 라인. (버스 단일 경유)"""
    fail_count = len(failed_targets)

    if ctx.state["canceled"]:
        if ctx.live_partially_saved:
            ctx.live_partially_saved = False
        else:
            raw_log.raw(
                "dl",
                emit_dl("ABORT", "-", spec="-", speed="-", pct=0, bar_frac=0,
                        msg="download canceled by user"),
                to_tui=True,
            )

    if failed_targets:
        if total > 1:
            ff_path = os.path.join(ctx.cfg["download_path"], "failed_urls.txt")
            try:
                with open(ff_path, "w", encoding="utf-8") as f:
                    for u, _ in failed_targets:
                        f.write(u + "\n")
            except Exception:
                pass
        # [개별 실패 라인] — ERR 컬럼 포맷으로 1건 1줄
        for u, reason in failed_targets:
            raw_log.raw("dl", emit_err(f"{u} — {reason}"), to_tui=True)

    # [결론 라인] — 성공/실패 카운트는 MSG 전용 (SPEC/SPEED 침범 금지)
    raw_log.raw(
        "dl",
        emit_dl(
            status="DONE" if fail_count == 0 else "WARN",
            platform="-",
            spec="-",
            speed="-",
            pct=100,
            bar_frac=1.0,
            msg=f"batch finished (success: {success_count}, fail: {fail_count})",
            is_error=fail_count > 0,
        ),
        to_tui=True,
    )

    ctx.finished_all.emit(success_count, fail_count)
    return not ctx.state["canceled"]

```

## File: live_recorder.py

```python
##### live_recorder.py - 라이브 녹화 파이프라인 (streamlink/ffmpeg)
"""유튜브·치지직 라이브를 ffmpeg 자식 프로세스로 녹화한다.

- yt-dlp/streamlink 로 포맷 URL만 추출하고, 실제 수신은 ffmpeg로 위임
- **릴레이 계측**: ffmpeg stdout 을 Python 이 256KB 청크로 읽어 실기록하며
  그 바이트 수 = 네트워크 실수신량 → _speed_win(add) 로 속도 측정
- stderr 는 별도 스레드로 상세 로그 유지
- 취소 시 kill + stdout 큐 drain (이후 'truncated' 오탐 방지)
"""
import os
import subprocess
import threading
import time

import yt_dlp

import raw_log
from media import cleanup_temp_files, format_bytes, remux_live_to_container
from utils import get_filename_template
from dl_platform import _dl_platform
from progress_emitter import emit_dl, emit_live_final_stats, log_success_info


def download_youtube_live(worker, url):
    """유튜브 라이브 — yt-dlp로 통합 포맷 URL만 추출 후 ffmpeg로 녹화."""
    opts = {
        "logger": worker.logger,
        "noplaylist": True,
        "format": "bv*+ba/b",
        "skip_download": True,
        "extract_flat": False,
    }
    from client_opts import _apply_client_opts, _apply_cookie_opts, _apply_ejs_opts, _apply_ffmpeg_opts

    _apply_cookie_opts(opts, worker.cfg)
    _apply_client_opts(opts, worker.cfg, forced=worker.yt_client)
    _apply_ejs_opts(opts)
    _apply_ffmpeg_opts(opts)

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)

    if not info:
        raise RuntimeError("live info fail")

    stream_url = info.get("url")
    if not stream_url:
        raise RuntimeError("live URL missing")

    out_file = os.path.join(
        worker.cfg["download_path"],
        get_filename_template(worker.cfg) % info,
    )
    temp_ts, thumb, _ = prepare_live_paths(worker, out_file, info.get("thumbnail"))

    cmd = ["ffmpeg", "-y", "-i", stream_url, "-c", "copy", "-f", "mpegts", temp_ts]
    return record_live_stream(worker, cmd, temp_ts, out_file, thumb)


def prepare_live_paths(ctx, out_file, thumb_url=None):
    """라이브 녹화용 임시 TS 파일 및 썸네일 경로 도출."""
    base, _ = os.path.splitext(out_file)
    temp_ts = f"{base}_temp.ts"
    thumb_file = f"{base}_temp_thumb.jpg" if thumb_url else None
    return temp_ts, thumb_file, out_file


def handle_stream_finish(worker, is_live, temp_file, proc_code=0):
    """스트림 종료 후처리 — 컨테이너 리먹싱 + 임시 파일 정리 + 완료 로그."""
    if proc_code not in (0, None):
        if worker.state.get("canceled"):
            worker.live_partially_saved = True
        else:
            raw_log.raw(
                "dl",
                emit_dl(
                    status="FAIL",
                    platform="-",
                    spec="-",
                    speed="-",
                    pct=None,
                    bar_frac=None,
                    stage="LIVE",
                    msg="exit code error",
                    is_error=True,
                ),
                to_tui=True,
            )
        cleanup_temp_files(temp_file)
        return False

    out_path = remux_live_to_container(temp_file, worker.cfg.get("container", "mp4"))
    if out_path and os.path.exists(out_path):
        size = os.path.getsize(out_path)
        raw_log.raw(
            "dl",
            emit_dl(
                status="DONE",
                platform="-",
                spec="-",
                speed="-",
                pct=100,
                bar_frac=1.0,
                stage="LIVE",
                msg=f"saved — {os.path.basename(out_path)} ({format_bytes(size)})",
            ),
            to_tui=True,
        )
        log_success_info(worker, out_path)
    cleanup_temp_files(temp_file)
    return True

_READ_CHUNK = 256 * 1024
_TICK_INTERVAL = 0.5


def _no_window():
    """Windows 전용 자식 창 억제 플래그."""
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def record_live_stream(worker, cmd, temp_ts_file, out_file, thumb_file, log_tag="Streamlink"):
    """ffmpeg/streamlink 자식 프로세스 녹화 — 릴레이 계측 + stderr 로그 + 취소 처리."""
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=False,
        creationflags=_no_window(),
    )

    # 워커에 프로세스 핸들 저장 (앱 종료 시 정리용)
    worker._live_proc = proc

    worker._speed_win.reset()
    total_bytes = 0
    start_t = time.monotonic()
    last_tick = 0.0

    def _drain_stderr():
        # stderr 는 별도 스레드로 실시간 상세 로그 유지 (버스 단일 경유)
        from log_event import LogEvent
        for raw in iter(proc.stderr.readline, b""):
            if raw:
                try:
                    raw_log.raw("ffmpeg",
                                LogEvent(stage="FFMP", status="OK",
                                         msg=raw.decode("utf-8", "replace").strip()))
                except Exception:
                    pass

    stderr_t = threading.Thread(target=_drain_stderr, daemon=True)
    stderr_t.start()

    returncode = -1
    try:
        with open(temp_ts_file, "wb") as tmp:
            while True:
                chunk = proc.stdout.read(_READ_CHUNK)
                if not chunk:
                    break
                tmp.write(chunk)
                total_bytes += len(chunk)
                worker._speed_win.add(total_bytes)

                now = time.monotonic()
                if now - last_tick >= _TICK_INTERVAL:
                    last_tick = now
                    rate = worker._speed_win.speed()
                    fname = os.path.basename(out_file)
                    raw_log.raw(
                        "dl",
                        emit_dl(
                            status="RUN",
                            platform=_dl_platform(
                                getattr(worker, "current_url", "") or ""
                            ),
                            spec="-",
                            speed=f"{format_bytes(rate)}/s" if rate else "-",
                            pct=None,
                            bar_frac=None,
                            stage="LIVE",
                            msg=f"recording — {fname}",
                            is_status=True,  # 진행률 틱은 한 줄 덮어쓰기(갱신형)
                        ),
                        to_tui=True,
                    )

                # 취소 요청 — 자식 죽이고 stdout queue drain ('truncated' 오탐 방지)
                if worker.state.get("canceled") and proc.poll() is None:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                    try:
                        while proc.stdout.read(_READ_CHUNK):
                            pass
                    except Exception:
                        pass

        worker._speed_win.add(total_bytes)
        returncode = proc.wait()
        if returncode not in (0, None):
            if not worker.state.get("canceled"):
                raise RuntimeError(f"{log_tag} process exit code {returncode}")
        emit_live_final_stats(worker, total_bytes, start_t)
    except Exception:
        if proc.poll() is None:
            try:
                proc.kill()
            except Exception:
                pass
        raw_log.raw(
            "dl",
            emit_dl(
                status="FAIL",
                platform="-",
                spec="-",
                speed="-",
                pct=None,
                bar_frac=None,
                stage="LIVE",
                msg=f"{log_tag} fail",
                is_error=True,
            ),
            to_tui=True,
        )
    finally:
        stderr_t.join(timeout=1.0)
        return handle_stream_finish(worker, True, temp_ts_file, returncode)
```

## File: log_console.py

```python
﻿### log_console.py - 간결 로그 콘솔 렌더러
"""간결 로그 QTextEdit의 렌더링 책임을 MainWindow로부터 분리한 모듈.
상태 줄 덮어쓰기(진행률 갱신), 색상 출력, 작업 구분 여백을 담당하며, MainWindow는 이 모듈에 로그 출력만 위임한다. """
from collections import deque
import re
import time
import unicodedata
import theme
from dl_platform import _short_platform
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QTextEdit

class ConciseLogConsole:
    """간결 로그 패널 전용 렌더러."""

    def __init__(self, text_edit):
        self.te = text_edit
        # 직전 로그가 덮어쓰기용 상태 로그였는지 기록하는 플래그
        self.last_log_was_status = False
        self.last_status_block_count = 1
        # 작업 종료 시 보증한 여백(add_task_separator) — 다음 append가 살린다
        self._pending_blank = False
        # [버그 수정] 상태 블록 제거 직후 플래그 — 다음 메시지가 새 블록에서 시작하도록 보장
        self._just_removed_status = False
        # [핵심] 자동 워드랩 금지 — QTextEdit이 임의로 줄을 접으면 '│' 줄기 없는
        # 침범 줄이 생겨 트리 문법이 파괴된다. 줄바꿈은 format_tree_item의
        # 예산 기반 wrap이 유일해야 하며, 화면 초과분은 가로로 흘러버리는 것을
        # 방지하기 위해 가로 스크롤로 흘린다.
        self.te.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        # [가로 스크롤 금지] 넘치는 내용은 '…' 절단이 처리 — 스크롤바가 생기지 않는다.
        self.te.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # 예산 동기화 캐시 — (뷰포트 폭, 글자 폭)이 바뀐 때만 재계산
        self._budget_key = None
        # [리플로우 대비] 원본 로그 버퍼 — msg는 잘리지 않은 전체를 보관하고,
        # 화면에는 렌더 시점 예산으로 잘라서 그린다. 창 폭 변경 시 재구성 루트.
        self._buffer = deque(maxlen=4096)  # list[dict] = {msg, is_status, is_error, fg_color}

    def _sync_budget(self):
        """로그를 찍는 시점 기준으로 트리 줄바꿈 예산을 재동기화한다.

        init_ui 시점엔 레이아웃이 실행 전이라 뷰포트 폭이 부정확하고,
        스플리터로 콘솔 폭을 조정하면 MainWindow.resizeEvent 자체가
        호출되지 않는다. append 직전에 폭/폰트를 검사해 바뀌었을 때만
        재계산하므로 비용은 사실상 없다.

        [리플로우] 예산이 실제로 바뀌면 _buffer의 원본 로그들을 새 예산으로
        전체 재구성한다 — 창을 가로로 늘리면 기존 로그까지 펼쳐진다.
        """
        self.on_resize()

    def on_resize(self):
        """콘솔 뷰포트 폭/폰트 변화 감시 — 바뀌면 예산 갱신 + 전체 reflow."""
        vp_w = self.te.viewport().width()
        char_w = self.te.fontMetrics().horizontalAdvance(" ")
        key = (vp_w, char_w)
        if key != self._budget_key:
            self._budget_key = key
            update_tree_budget(self.te)
            if self._buffer:
                self.reflow()

    def append(self, msg, is_status=False, is_error=False, fg_color=None, no_wrap=False):
        """빈 줄 생성 차단 및 정밀 문단 삭제 파이프라인.

        [진행률 갱신형 계약] 진행률/진행 중 상태 로그는 반드시 is_status=True로
        호출할 것 — ConciseLogConsole이 직전 상태 블록을 같은 줄에 덮어쓴다
        (Single-Line In-Place Status, HANDOVER §6). is_status=False로 emit하면
        매 틱 새 줄이 쌓여 '한 행 = 한 정보' 규칙을 위반한다. DL/LIVE 틱,
        DEPS 다운로드 %, PO 서버 진행 등 모든 반복 로그가 해당.

        [줄바꿈 계약] 줄바꿈 결정은 발행자(raw() 경유 LogEvent → 구독자) 측의
        no_wrap 플래그를 그대로 따르며, 렌더 레이어에서 문자열 내용을 다시
        뜯어 판단하지 않는다(정규식 라우팅 제로). LogEvent 경유분(컬럼 포맷·
        프리포맷)은 True, 큐 호환용 bare 문자열은 False다.
        """
        self._sync_budget()  # 현재 뷰포트/폰트 기준 예산 보장 — 자동랩 침범 방지
        # [리플로우 대비] 원본 로그를 버퍼에 보관 (렌더 시점 절단을 위해 잘리지 않음)
        self._buffer.append(
            {"msg": msg, "is_status": is_status, "is_error": is_error,
             "fg_color": fg_color, "no_wrap": bool(no_wrap)}
        )
        doc = self.te.document()
        cursor = self.te.textCursor()

        # 0. 바닥 여백용 빈 블록을 치운다 — 새 로그는 항상 내용 위에 붙고,
        #    여백은 삽입 완료 후 다시 깔린다(상시 유지). 직전에 작업 종료
        #    여백이 보증됐다면(add_task_separator) 빈 블록 '한 줄'은 살려
        #    둔다 — 완료 로그와 다음 로그 사이의 한 칸 띄우기.
        keep_blank = self._pending_blank
        self._pending_blank = False
        self._strip_tail_padding(keep_one=keep_blank)

        # 1. 직전 로그가 상태 메시지(is_status=True)였다면 상태 블록을 정리한다.
        #    이때 마지막 블록은 '빈 홈 블록'으로 남긴다 — 상태 줄의 첫 블록을
        #    직전 블록(작업 구분 여백)에 병합하면 여백이 먹혀 중단 로그와
        #    다음 작업 로그가 붙어버리는 문제의 원인이었다.
        if self.last_log_was_status and not doc.isEmpty():
            self._remove_status_blocks()
            self.last_log_was_status = False
            self._just_removed_status = True  # 빈 홈 재사용 좌표 시그널

        # 2. 커서 최하단 이동 (문서가 비어있지 않고 줄 시작점이 아니면 1줄 개행).
        #    커서가 '보증된 여백' 빈 블록 위에 서 있으면 그 블록을 내용으로
        #    채우지 않고 한 줄 더 개행해 여백을 살린다.
        cursor.movePosition(QTextCursor.MoveOperation.End)
        # [핵심] 상태 틱 종료/업데이트 → 빈 홈 블록 시작점으로 재사용(같은 줄)
        #    상태 틱 재사용도 허용(not is_status 한정 X) — 퍼센트 업데이트가
        #    매번 새 줄에 나오는 '붙어나오는 퍼센트 로그' 버그 예방.
        if self._just_removed_status and not doc.isEmpty() and not doc.lastBlock().text():
            cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        on_kept_blank = (
            keep_blank
            and not doc.isEmpty()
            and cursor.atBlockStart()
            and not doc.lastBlock().text()
        )
        # [핵심] 블록 삽입 판정 — Single-Line In-Place Status를 지킨다.
        # 재사용 중(빈 홈 시작점)이면 insertBlock 생략 → 같은 블록에 텍스트 삽입
        reuse_status_home = (
            self._just_removed_status
            and not doc.isEmpty()
            and not doc.lastBlock().text()
            and cursor.atBlockStart()
        )
        if not doc.isEmpty() and not reuse_status_home and (
            not cursor.atBlockStart()
            or on_kept_blank
            or doc.lastBlock().text()
        ):
            cursor.insertBlock()
        self._just_removed_status = False  # 플래그 소비

        clean_msg = msg

        # 3. [핵심] 줄바꿈(\n) 사이에만 insertBlock()을 호출하여 문장 끝 불필요한 빈 줄 생성 완전 차단
        #    비트리 일반 라인(pip 출력 등)은 예산 폭을 넘기면 여기서 wrap한다 —
        #    NoWrap 콘솔에서 화면 초과분이 가로로 흘러버리는 것을 방지.
        #    [리플로우] 렌더 시점 예산으로 msg를 잘라서 그린다 (원본은 버퍼 보존).
        inserted = self._insert_clamped(
            cursor, clean_msg, is_status, is_error, fg_color, bool(no_wrap)
        )

        # 4. 상태 플래그 및 블록 수 기록 — wrap 포함 실제 삽입 블록 수
        self.last_log_was_status = is_status
        self.last_status_block_count = max(1, inserted)

        # 5. 바닥 여백 상시 유지 — 마지막 로그와 콘솔 바닥 사이 2줄 간격
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self._add_tail_padding(cursor)

        self.te.moveCursor(QTextCursor.MoveOperation.End)
        sb = self.te.verticalScrollBar()
        sb.setValue(sb.maximum())

    def add_task_separator(self):
        """하나의 다운로드 작업이 완전히 종료되었을 때만 1줄 여백 추가.

        삽입한 빈 블록은 다음 append of _strip_tail_padding에서 걷히지 않게
        _pending_blank로 보증한다 — '완료 로그 다음 한 칸 띄우기'.
        """
        doc = self.te.document()
        if not doc.isEmpty():
            self._strip_tail_padding()
            cursor = self.te.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            cursor.insertBlock()
            self._add_tail_padding(cursor)
            self.last_log_was_status = False
            self._pending_blank = True

    def clear_status_line(self):
        """남아있는 애니메이션 상태 로그 블록을 깔끔하게 삭제.

        블록 자체는 빈 홈으로 남긴다 — 상태 줄이 차지했던 자리가 원래
        작업 구분 여백이었다면 원상복구되어야 하기 때문이다.
        """
        if self.last_log_was_status:
            self._remove_status_blocks()
            self.last_log_was_status = False
            self._just_removed_status = True

    def _remove_status_blocks(self):
        """상태 로그 블록 last_status_block_count개를 '빈 홈 블록 1개'로 정리.

        블록 경계는 (n-1)개만 병합하고 마지막 블록은 텍스트만 지워 빈 채로
        남긴다. 기존 방식(n회 clear+병합)은 상태 줄의 첫 블록을 직전 블록에
        병합해버려서, 직전 블록이 작업 구분 여백(빈 줄)이면 여백이 먹혔다 —
        '중단 로그 바로 아래에 다음 작업 로그가 붙는' 현상의 원인.
        """
        cursor = self.te.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        for _ in range(max(0, self.last_status_block_count - 1)):
            cursor.movePosition(
                QTextCursor.MoveOperation.StartOfBlock,
                QTextCursor.MoveMode.KeepAnchor,
            )
            cursor.removeSelectedText()
            if not cursor.atStart():
                cursor.deletePreviousChar()
            cursor.movePosition(QTextCursor.MoveOperation.End)
        # 마지막 남은 상태 블록의 텍스트만 제거 (블록/여백은 유지)
        cursor.movePosition(
            QTextCursor.MoveOperation.StartOfBlock,
            QTextCursor.MoveMode.KeepAnchor,
        )
        cursor.removeSelectedText()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        # [버그 수정] 상태 블록 제거 직후 — 다음 append가 새 블록을 삽입하도록 플래그 설정
        self._just_removed_status = True

    def reset_status_flag(self):
        """상태 로그를 히스토리로 확정 보존(덮어쓰기 중단)."""
        self.last_log_was_status = False

    def _render_clamp(self, line):
        """렌더 시점 절단 — 마지막 ' │ ' 이후 msg를 viewport 우측까지 픽셀 정렬.

        원본(msg 전체)은 _buffer에 보존되고, 이 함수는 화면 표시만
        viewport 픽셀 폭에 맞춰 '…'로 자른다. 핵심은 display_width
        (east_asian_width 기반 문자 단위 추정)가 아니라 fontMetrics의
        horizontalAdvance로 *실제 픽셀 폭*을 재는 것이다 — D2Coding은
        한글 2칸·latin 1칸·'│'(U+2502, Ambiguous)는 폰트에 따라 1칸이
        되는 비일관성이 있어, 문자 단위 추론만으로는 짤림 위치가 들쭉날쭉
        해진다. 픽셀 단위 절단으로 폰트/Ambiguous 폭/한영 혼용에 무관하게
        viewport 우측에서 일정하게 끝난다.

        우측에는 RIGHT_PADDING_PX 만큼 가독성 여백을 남긴다 — 글자
        가장자리가 프레임에 붙는 것을 막아 위 압박감을 줄인다.
        """
        fm = self.te.fontMetrics()
        viewport_px = self.te.viewport().width()
        if viewport_px <= 0:
            # 위젯이 아직 실측되지 않은 시점(초기화 직후) — 보수적으로 원본 유지
            return line
        if " │ " not in line:
            # TUI 가 아닌 라인 — viewport 폭에서 우측 패딩을 뺀 만큼 통째로 자른다
            return _truncate_by_pixels(line, viewport_px - RIGHT_PADDING_PX, fm)
        head, _, msg = line.rpartition(" │ ")
        if not head:
            return line
        # head + 마지막 ' │ ' 까지의 실제 픽셀 폭을 잰다 — '│'의 Ambiguous
        # 폭(1칸/2칸)과 D2Coding의 한글/라틴 폭 차이를 그대로 반영한다.
        head_px = fm.horizontalAdvance(head + " │ ")
        msg_budget_px = viewport_px - head_px - RIGHT_PADDING_PX
        return head + " │ " + _truncate_by_pixels(msg, msg_budget_px, fm)

    def _insert_clamped(self, cursor, msg, is_status, is_error, fg_color, no_wrap=False):
        """한 로그(다중 줄 허용)를 렌더 클램프 후 삽입. (삽입 블록 수 반환)

        append와 reflow가 공유하는 유일한 삽입 경로 — 파이프라인 중복 제거.
        no_wrap 플래그를 _flow_lines에 그대로 전달한다.
        """
        inserted = 0
        lines = msg.split("\n")
        for idx, raw in enumerate(lines):
            for f_idx, line in enumerate(_flow_lines(raw, no_wrap)):
                if idx > 0 or f_idx > 0:
                    cursor.insertBlock()
                inserted += 1
                line = self._render_clamp(line)
                if fg_color is not None:
                    fmt = QTextCharFormat()
                    fmt.setFont(self.te.font())
                    fmt.setForeground(QColor(fg_color))
                    cursor.insertText(line, fmt)
                else:
                    for seg, color in _line_segments(line, is_error, is_status):
                        fmt = QTextCharFormat()
                        fmt.setFont(self.te.font())
                        fmt.setForeground(QColor(color))
                        cursor.insertText(seg, fmt)
        return inserted

    def reflow(self):
        """창 폭 변경 시 전체 재렌더링 — 버퍼의 원본 로그를 새 예산으로 다시 그린다.

        상태 로그는 연속 그룹의 마지막 것만 그려 Single-Line In-Place를 유지한다.
        """
        buf = self._buffer
        if not buf:
            return
        self.te.clear()
        self.last_log_was_status = False
        self.last_status_block_count = 1
        self._pending_blank = False
        self._just_removed_status = False

        # 상태 로그 연속 그룹의 마지막만 렌더링 대상으로 추려낸다
        entries = []
        i = 0
        while i < len(buf):
            e = buf[i]
            if e["is_status"]:
                j = i
                while j + 1 < len(buf) and buf[j + 1]["is_status"]:
                    j += 1
                entries.append(buf[j])
                i = j + 1
            else:
                entries.append(e)
                i += 1

        doc = self.te.document()
        cursor = self.te.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        for idx, e in enumerate(entries):
            if idx > 0 or not doc.isEmpty():
                cursor.insertBlock()
            self._insert_clamped(
                cursor, e["msg"], e["is_status"], e["is_error"], e["fg_color"],
                e.get("no_wrap", False),
            )

        # 바닥 여백 상시 유지
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self._add_tail_padding(cursor)

        self.te.moveCursor(QTextCursor.MoveOperation.End)
        sb = self.te.verticalScrollBar()
        sb.setValue(sb.maximum())

    def remove_last_blocks(self, count):
        """마지막 count개 블록을 흔적 없이 제거 (분석 결과 블록 철회용).

        _remove_status_blocks가 '빈 홈'을 남기는 것과 달리 블록 경계까지
        완전히 삭제한다 — '없었던 일'로 만드는 것이 목적. 문서 첫 블록
        (초기 안내문)은 항상 남긴다.
        """
        doc = self.te.document()
        if count <= 0 or doc.isEmpty():
            return
        self._strip_tail_padding()
        count = min(count, doc.blockCount() - 1)
        if count <= 0:
            return
        cursor = self.te.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        for _ in range(count):
            cursor.movePosition(
                QTextCursor.MoveOperation.StartOfBlock,
                QTextCursor.MoveMode.KeepAnchor,
            )
            cursor.removeSelectedText()
            if not cursor.atStart():
                cursor.deletePreviousChar()
            cursor.movePosition(QTextCursor.MoveOperation.End)
        self._add_tail_padding()
        self.last_log_was_status = False

    def _strip_tail_padding(self, keep_one=False):
        """문서 끝의 여백용 빈 블록을 제거한다 (내용 블록이 마지막이 되도록).

        첫 블록은 어떤 경우에도 남긴다 — 문서 전체가 빈 블록뿐일 때는
        그 상태를 유지해야 QTextEdit '빈 문서' 판정(isEmpty)이 유효하기 때문.
        keep_one=True면 내용 블록 바로 뒤의 빈 블록 한 개는 남긴다 —
        작업 종료 시 보증된 여백(add_task_separator)이다.
        """
        doc = self.te.document()
        while doc.blockCount() > 1:
            b = doc.lastBlock()
            if b.text():
                break
            cursor = self.te.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            cursor.movePosition(
                QTextCursor.MoveOperation.StartOfBlock,
                QTextCursor.MoveMode.KeepAnchor,
            )
            cursor.removeSelectedText()
            if not cursor.atStart():
                cursor.deletePreviousChar()
        # keep_one — 마지막 내용 블록 바로 뒤 of 빈 블록 '한 개'를 보증한다.
        # (strip은 문서 앞쪽 크기와 무관하게 전부 걷으므로, 보증은 재삽입으로)
        if keep_one and not doc.isEmpty():
            b = doc.lastBlock()
            if b.text():
                cursor = self.te.textCursor()
                cursor.movePosition(QTextCursor.MoveOperation.End)
                cursor.insertBlock()

    def _add_tail_padding(self, cursor=None):
        """콘솔 바닥에 2줄 여백을 깐다 — 마지막 로그가 테두리에 붙지 않게.

        QSS padding-bottom(정적 여백)과 달리 문서 블록이라 스크롤 범위에
        포함되며, 새 로그 삽입 직전 _strip_tail_padding으로 걷어낸다.
        """
        if cursor is None:
            cursor = self.te.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
        for _ in range(TAIL_PADDING_BLOCKS):
            cursor.insertBlock()

    def last_content_block_text(self):
        """바닥 여백 빈 블록을 건너뛴 마지막 내용 블록의 텍스트.

        setHtml 산출 블록은 줄구분자(U+2028)·공백 꼬리를 가질 수 있어
        toPlainText 기반 문자열과 비교 가능하도록 잘라낸다.
        """
        b = self.te.document().lastBlock()
        while b.isValid() and not b.text():
            b = b.previous()
        return b.text().rstrip("\u2028 \t") if b.isValid() else ""

    def insert_after_ready(self, text):
        """기동 인사줄('[ChzzkTube vX.Y.Z] by Miorine') 바로 다음 줄에 로그를 삽입."""
        self._sync_budget()
        b = self.te.document().lastBlock()
        for _ in range(4):
            if not b.isValid():
                break
            t = b.text()
            if "by Miorine" in t:
                body = t.rstrip("\u2028 \t")
                cursor = QTextCursor(b)
                cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
                cursor.movePosition(
                    QTextCursor.MoveOperation.Right,
                    QTextCursor.MoveMode.MoveAnchor,
                    len(body),
                )
                fmt = QTextCharFormat()
                fmt.setFont(self.te.font())
                # 심볼별 색 — append 파이프라인의 색 위계와 동일하게
                if text.startswith("[v]"):
                    fmt.setForeground(QColor(theme.LOG_COLOR_SUCCESS))
                elif text.startswith("[!]"):
                    fmt.setForeground(QColor(theme.LOG_COLOR_ERROR))
                else:
                    fmt.setForeground(QColor(theme.LOG_COLOR_INFO))
                # 인사줄 '다음 줄'에 새 블록으로 삽입한다(같은 줄 병기 아님).
                # 예산 초과분은 줄기 없는 연속 줄 문법(공백 나열)으로 접지
                # 않으면 NoWrap 콘솔에서 가로로 침범한다.
                chunks = _wrap_by_width(text, TREE_TOTAL_WIDTH)
                joined = "\n" + ("\n" + " " * STEMLESS_CONT_WIDTH).join(chunks)
                cursor.insertText(joined, fmt)
                # 삽입 후 커서가 남아 가로 스크롤을 밀지 않게 원점 복귀
                hsb = self.te.horizontalScrollBar()
                hsb.setValue(0)
                return True
            b = b.previous()
        return False

def display_width(text):
    """콘솔 표시 폭 계산 (한글 등 전각 문자는 2칸)."""
    return sum(
        2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
        for ch in str(text)
    )

def _wrap_by_width(text, max_width):
    """표시 폭 기준 단어 단위 줄바꿈. 단어 자체가 예산보다 길면 강제 분할."""
    lines, cur, cur_w = [], "", 0
    for word in str(text).split(" "):
        while display_width(word) > max_width:
            if cur:
                lines.append(cur)
            cur, cur_w = "", 0
            part, take = "", 0
            for ch in word:
                cw = display_width(ch)
                if take + cw > max_width:
                    break
                part += ch
                take += cw
            lines.append(part)
            word = word[len(part):]
        w = display_width(word)
        cand_w = cur_w + (1 if cur else 0) + w
        if cur and cand_w > max_width:
            lines.append(cur)
            cur, cur_w = word, w
        else:
            cur = word if not cur else cur + " " + word
            cur_w = cand_w
    if cur:
        lines.append(cur)
    return lines

def _line_segments(line, is_error, is_status=False):
    """간결 로그 한 줄의 색 위계 — 구조는 딤, 값은 화이트, 상태만 액센트."""
    if is_error:
        return [(line, theme.LOG_COLOR_ERROR)]
    if is_status or " | 용량:" in line:
        return [(line, theme.LOG_COLOR_INFO)]
    if line.startswith("[v]"):
        if "PO Token" in line:
            return [(line, theme.LOG_COLOR_VALUE)]
        return [(line, theme.LOG_COLOR_SUCCESS)]
    if line.startswith(("[+]", "[~]")):
        return [(line, theme.LOG_COLOR_INFO)]
    if line[:2] in (" ├", " └"):
        head, sep, tail = line.partition(": ")
        if sep:
            return [(head + sep, theme.LOG_COLOR_STRUCT), (tail, theme.LOG_COLOR_VALUE)]
        return [(line[:2], theme.LOG_COLOR_STRUCT), (line[2:], theme.LOG_COLOR_VALUE)]
    if line[:2] in (" │", "  "):
        # 줄기/들여쓰기 2칸만 딤 — 나머지는 전부 값(화이트)
        return [(line[:2], theme.LOG_COLOR_STRUCT), (line[2:], theme.LOG_COLOR_VALUE)]
    return [(line, theme.LOG_COLOR_VALUE)]

### 트리 라벨 공통 폭 — 콜론(:) 위치를 모든 가지에서 세로로 일치시킨다.
TREE_LABEL_WIDTH = 9  # kv 라벨('저장 완료'·'실패 사유' 등 전각 4자+공백) 기준
TREE_TOTAL_WIDTH = 56  # 간결 로그 창의 실질 가로 예산 (폴백 — update_tree_budget으로 갱신)
TAIL_PADDING_BLOCKS = 2  # 콘솔 바닥에 상시 유지하는 여백 빈 블록 수
RIGHT_PADDING_PX = 20  # 픽셀 기반 절단 시 viewport 우측에 남기는 가독성 여백 (한글 1자 너비)

def update_tree_budget(text_edit):
    """콘솔 뷰포트 폭을 글자 폭으로 나눠 트리 줄바꿈 예산을 동적 갱신한다.

    상한(100)을 두지 않는다 — 창을 가로로 늘리면 잘려 보이던 로그가
    유연하게 펼쳐진다. 초과분은 format_log_line의 '…' 절단이 처리한다.
    """
    global TREE_TOTAL_WIDTH
    char_w = text_edit.fontMetrics().horizontalAdvance(" ")
    if char_w > 0:
        # document margin(8px × 2) + QSS 프레임 여백을 제외한 실제 텍스트 폭
        cols = (text_edit.viewport().width() - 16) // char_w
        TREE_TOTAL_WIDTH = max(40, int(cols))

### 줄기 없는(' └─') 연속 줄의 선행 공백 폭 — cont_prefix는 prefix 폭(TREE_LABEL_WIDTH+6)만큼의 공백 나열
STEMLESS_CONT_WIDTH = TREE_LABEL_WIDTH + 6

def _flow_lines(line, no_wrap=False):
    """라인 분할 규칙 — Single-Line TUI는 wrap하지 않는다.

    *  no_wrap=True(LogEvent 경유 컬럼/프리포맷 라인): 그대로 한 줄 —
       예산 초과분은 ConciseLogConsole._render_clamp가 '…'로 절단한다.
       (트리 조판 줄은 자식 줄 예산 산정용으로 내부 wrap 유지)
    *  no_wrap=False(큐 호환 bare 문자열·yt-dlp/pip 출력 등 비트리 일반
       라인): 예산 폭으로 wrap한다.
    발행자(raw → 구독자) 플래그가 유일한 분기 기준이며, 문자열 콘텐츠를
    다시 뜯어 판단하지 않는다(정규식 라우팅 제로).
    """
    if no_wrap:
        return [line]
    if line[:2] in (" ├", " └", " │"):
        return [line]
    if line.startswith(" " * STEMLESS_CONT_WIDTH):
        return [line]
    return _wrap_by_width(line, max(20, TREE_TOTAL_WIDTH))

def _pad_label(label, width):
    """라벨을 width칸까지 뒤에 공백을 붙여 확장한다."""
    return str(label) + " " * max(0, width - display_width(label))

def format_tree_item(label, value, branch="├─", indent=" "):
    """트리 가지 한 항목을 '라벨 정렬 + 콜론 정렬 + 값 줄바꿈 시 세로줄 연결'로 조판."""
    padded = _pad_label(label, TREE_LABEL_WIDTH)
    prefix = f"{indent}{branch} {padded}: "
    stem = "│" if branch.startswith("├") else " "
    cont_prefix = indent + stem + " " * (
        display_width(prefix) - display_width(indent) - 1
    )
    chunks = _wrap_by_width(value, TREE_TOTAL_WIDTH - display_width(prefix))
    out = prefix + (chunks[0] if chunks else "")
    for chunk in chunks[1:]:
        out += "\n" + cont_prefix + chunk
    return out

def format_kv_line(symbol, label, value):
    """'[!] 건너뜀   : 값' — 트리 가지와 같은 콜론 열에 정렬된 단일 kv 라인."""
    padded = _pad_label(label, TREE_LABEL_WIDTH)
    prefix = f"{symbol} {padded}: "
    chunks = _wrap_by_width(value, max(10, TREE_TOTAL_WIDTH - display_width(prefix)))
    out = prefix + (chunks[0] if chunks else "")
    cont = " " * display_width(prefix)
    for chunk in chunks[1:]:
        out += "\n" + cont + chunk
    return out

def format_target_url(url, max_len=50):
    """URL을 트리 가지 형태로 출력. 길면 '│' 세로줄로 이어지는 정렬된 줄바꿈."""
    return format_tree_item("대상", url, branch="└─")

def format_analysis_counts(v_count, a_count):
    """분석 완료 로그의 포맷 개수 요약 문자열."""
    if v_count and a_count:
        return f" (v:{v_count}, a:{a_count})"
    if v_count:
        return f" (v:{v_count})"
    if a_count:
        return f" (a:{a_count})"
    return ""


def format_pick_menu(v_list, a_list, max_rows=40):
    """[포맷 직접 고르기] 비디오/오디오 목록을 번호 매긴 선택 메뉴로 변환.

    각 항목 라벨은 media.format_dropdown_label(py)이 이미 파이프 컬럼 식이므로
    앞에 1-based 인덱스만 붙여 출력한다. UX 규칙 — 빈 입력 = 최고 품질,
    'N' = 비디오 N, 'N.M' = 비디오 N + 오디오 M.
    """
    lines = []
    if v_list:
        lines.append("video formats")
        for idx, f in enumerate(v_list[:max_rows], 1):
            label = f.get("label") or f.get("id") or "?"
            lines.append(f"  {idx:>2}  {label}")
        if len(v_list) > max_rows:
            lines.append(f"  ... {len(v_list) - max_rows} more")
    if a_list:
        lines.append("audio formats")
        for idx, f in enumerate(a_list[:max_rows], 1):
            label = f.get("label") or f.get("id") or "?"
            lines.append(f"  {idx:>2}  {label}")
        if len(a_list) > max_rows:
            lines.append(f"  ... {len(a_list) - max_rows} more")
    return lines

### ──────────────────────────────────────────────────────────────
### 컬럼 로그 라인 — TUI 스타일 고정 칼럼 포맷
### ──────────────────────────────────────────────────────────────
# 포맷: [HH:MM:SS] STAGE │ STATUS │ PLATFORM │ SPEC │ PERCENT │ [BAR] │ MSG
#   STAGE   : SYS / ANAL / DL / MERG / BATCH
#   STATUS  : OK / READY / RUN / DONE / ABORT / FAIL / END
#   BAR     : 텍스트 진행 바 (bar_frac 0.0~1.0)

def _log_ts():
    """현재 시각 — [HH:MM:SS] 형식."""
    return time.strftime("[%H:%M:%S]")

def is_tui_line(msg):
    """[호환 shim] 구버전 콘텐츠 판정 — 렌더 레이어에서는 더 이상 사용하지 않는다.

    줄바꿈 결정은 발행자(raw → 구독자) 플래그(_flow_lines no_wrap)가 유일한
    기준이다. 외부 호출부 호환용으로만 남겨두며, 구조적(non-regex) 판정은 유지한다.
    """
    s = str(msg).strip()
    # [HH:MM:SS] : 위치/숫자 구조 검증 (regex 없음)
    if not (len(s) >= 12 and s[0] == "[" and s[3] == ":"
            and s[6] == ":" and s[9] == "]" and s[10] == " "
            and s[1:3].isdigit() and s[4:6].isdigit() and s[7:9].isdigit()):
        return False
    # 컬럼 구분자 │ : 타임스탬프 뒤에 1글자 이상, 뒤에 1글자 이상
    idx = s.find("│", 11)
    return idx > 11 and idx < len(s) - 1

def _log_pct(pct):
    """퍼센트 컬럼 — None 이면 '-', 아니면 '42.1%'."""
    if pct is None:
        return "-"
    try:
        return f"{float(pct):5.1f}%"
    except (TypeError, ValueError):
        return "-"

def _log_bar(bar_frac, width=10):
    """텍스트 진행 바 — None 이면 '-', 아니면 '[████░░░░░░]'."""
    if bar_frac is None:
        return "-"
    try:
        frac = min(max(float(bar_frac), 0.0), 1.0)
    except (TypeError, ValueError):
        return "-"
    filled = int(round(frac * width))
    return f"[{'█' * filled}{'░' * (width - filled)}]"

def _truncate_by_pixels(msg, budget_px, fm):
    """msg를 fontMetrics 기반 *실제 픽셀 폭*으로 절단 — 초과 시 '…' 부착.

    display_width(east_asian_width 기반 문자 단위 추정) 대신
    horizontalAdvance로 실제 픽셀을 잰다 — D2Coding은 한글 2칸·
    latin 1칸·'│'(U+2502, Ambiguous)는 폰트에 따라 1칸/2칸이 되는
    비일관성이 있어, 문자 단위 추론만으로는 한영 혼용 라인의 짤림
    위치가 들쭉날쭉해진다. 픽셀 단위 절단으로 폰트/Ambiguous 폭/
    한영 혼용에 무관하게 끝이 일정해진다.

    budget_px는 msg 영역 전체(우측 패딩 포함)의 픽셀 폭. '…'의
    픽셀도 함께 고려해 msg가 budget을 초과하면 직전까지 자르고 '…'를
    붙인다. budget이 너무 작아 '…'조차 못 넣으면 '…'만 출력.

    주의: 개별 글자 폭의 합 ≠ 전체 문자열 폭(커닝/반올림)이므로,
    매 글자 추가 시마다 후보 문자열 전체의 horizontalAdvance를 재서
    budget 오버를 판정한다 — 이렇게 해야 정확히 budget 안에 든다.
    """
    if budget_px <= 0:
        return "…"
    ellipsis_px = fm.horizontalAdvance("…")
    if budget_px <= ellipsis_px:
        return "…"
    out = []
    for ch in msg:
        candidate = "".join(out) + ch + "…"
        if fm.horizontalAdvance(candidate) > budget_px:
            break
        out.append(ch)
    result = "".join(out)
    if len(result) < len(msg):
        result += "…"
    return result


def format_log_line(stage, status, platform="", spec="", speed="", pct=None, bar_frac=None, msg=""):
    """TUI 스타일 컬럼 로그 라인 — 단일 라인, 고정 칼럼 정렬.

    표준 포맷:
        [HH:MM:SS] STAGE │ STATUS │ PLATFORM │ SPEC │ MSG

    특징:
    - SPEC: 순수 미디어 스펙만 (1080p30, h264, opus 등). 파일명·채널명 금지.
    - MSG: 제목·파일명·속도·진행률·바 등 가변 정보.
    - PCT/BAR는 SPEC 오른쪽에 MSG로 통합해 세로 정렬 안정화.

    인자:
        stage    : SYS / ANAL / DL / LIVE / MERG / BATCH / DEPS / POT ...
        status   : OK / READY / RUN / DONE / ABORT / FAIL / END / SKIP ...
        platform : yt / chzzk / ytdlp / streamlink / pot / deps 등 (8자 축약)
        spec     : 스트림 속성 전용 (예: 1080p30, h264) — 파일명·통계 금지
        speed    : 네트워크 속도 전용 (예: 12.4M/s) — 카운터·기타 금지
        pct      : 진행률 (0~100, None 가능)
        bar_frac : 진행 바 (0.0~1.0, None 가능)
        msg      : 제목·파일명·시스템 메시지 (예산 초과 시 자동 절단)
    """
    stage_s = str(stage).upper()[:8].ljust(8)
    status_s = str(status).upper()[:8].ljust(8)
    plat_s = _short_platform(platform)[:8].ljust(8)
    spec_s = str(spec or "-")
    speed_s = str(speed or "-")
    pct_s = _log_pct(pct)
    bar_s = _log_bar(bar_frac)

    # [핵심] PCT와 BAR를 MSG에 통합해 고정 5칸 구조 유지
    extra = ""
    if pct is not None:
        extra = f"{pct_s} · {bar_s}"

    head = _log_ts() + " " + stage_s
    rest = [status_s, plat_s, spec_s, speed_s]
    fixed = head + " │ " + " │ ".join(rest)

    if msg:
        # MSG가 비어있으면 extra만, 있으면 extra · msg 형태
        if msg.strip():
            full_msg = f"{extra} · {msg}" if extra else msg
        else:
            full_msg = extra
        return fixed + " │ " + full_msg
    return fixed


def format_log_line_for_event(event):
    """구조화된 LogEvent → TUI 컬럼 문자열 (뷰 전용 컬럼화 — 정규식 판정 제로).

    렌더링 책임은 View(메인로그 모듈)에 있고, LogEvent는 모델이다.
    rendered=True면 msg가 이미 표시 완성형이므로 재포맷하지 않는다.
    """
    from log_event import LogEvent  # lazy import (순환 참조 방지)
    if not isinstance(event, LogEvent):
        return str(event)
    if event.rendered:
        return event.msg
    return format_log_line(
        stage=event.stage,
        status=event.status,
        platform=event.platform,
        spec=event.spec,
        speed=event.speed,
        pct=event.pct,
        bar_frac=event.bar_frac,
        msg=event.msg,
    )


def _log_line_segments(line):
    """컬럼 로그 라인의 색상 — STATUS 기반 단색 분기."""
    if " │ FAIL" in line:
        return [(line, theme.LOG_COLOR_ERROR)]
    if " │ WARN" in line:
        return [(line, theme.LOG_COLOR_WARN)]
    if " │ ABORT" in line:
        return [(line, theme.LOG_COLOR_WARN)]
    if " │ DONE" in line or " │ OK " in line or " │ END" in line or " │ READY" in line:
        return [(line, theme.LOG_COLOR_SUCCESS)]
    if " │ SKIP" in line:
        return [(line, theme.LOG_COLOR_DIM)]
    if " │ RUN" in line:
        return [(line, theme.LOG_COLOR_ACCENT)]
    return [(line, theme.LOG_COLOR_INFO)]


# ════════════════════════════════════════════════════════════════════════
# LogEvent 빌더 — emit_event / emit_dl / emit_err / emit_progress / emit_component
# 행동 근원에서 라벨링을 동봉한 LogEvent를 생성한다. 뷰 렌더링은 구독자 몫.
# ════════════════════════════════════════════════════════════════════════

def emit_event(stage, status, platform="-", msg="", is_status=False, is_error=False):
    """단순 이벤트 1건 — POT/Update/사용자 액션/에러 모두 공통."""
    from log_event import LogEvent  # lazy import (순환 참조 방지)
    return LogEvent(
        stage=stage, status=status, platform=platform, msg=msg,
        is_status=is_status, is_error=is_error,
    )


def emit_dl(status, platform="", spec="", speed="", pct=None, bar_frac=None, msg="", stage="DL",
            is_status=False, is_error=False):
    """다운로드 진행률/완료 이벤트 — SPEC(스트림 속성)과 SPEED(네트워크) 분리.

    예: [12:00:01] DL │ RUN │ YT  │ 1080p30 │ 12.4M/s │ 65.0% │ [█⋯░] │ 제목
    """
    from log_event import LogEvent  # lazy import (순환 참조 방지)
    return LogEvent(
        stage=stage, status=status, platform=platform, spec=spec,
        speed=speed, pct=pct, bar_frac=bar_frac, msg=msg,
        is_status=is_status, is_error=is_error,
    )


def emit_err(msg):
    """에러 1건 — FAIL 상태, 플랫폼 '-'."""
    from log_event import LogEvent  # lazy import (순환 참조 방지)
    return LogEvent(stage="DL", status="FAIL", msg=msg, is_error=True)


def emit_progress(stage, status, platform="-", spec="-", speed="-", pct=None, bar_frac=None, msg="",
                  is_status=False, is_error=False):
    """진행률 표시 이벤트 — ANAL/DL/LIVE 단계."""
    from log_event import LogEvent  # lazy import (순환 참조 방지)
    return LogEvent(
        stage=stage, status=status, platform=platform, spec=spec, speed=speed,
        pct=pct, bar_frac=bar_frac, msg=msg,
        is_status=is_status, is_error=is_error,
    )


def emit_component(stage, status, platform, msg="", is_status=False, is_error=False):
    """컴포넌트/워커 결과 — DEPS / POT / READY 등 system 단계."""
    from log_event import LogEvent  # lazy import (순환 참조 방지)
    return LogEvent(
        stage=stage, status=status, platform=platform, msg=msg,
        is_status=is_status, is_error=is_error,
    )

```

## File: log_event.py

```python
##### log_event.py - 구조화된 로그 이벤트 (v3.3.0)
"""raw_log 버스의 단일 진실 데이터 구조.

[계약 v3.3.0 — 포함관계 모델]
- 발행자는 행동 근원(raw() 호출점)에서 LogEvent를 동봉해 전송한다.
  라벨링(stage/status/platform/spec)은 태어난 곳에서 결정된다.
- 채널 포함관계: history=전량, F12(full)=전량(⊇TUI), TUI(concise)=to_tui 선택.
  → "F12가 안 받는 로그"는 존재하지 않는다. (Channel 3비트 플래그 폐기)
- 콘텐츠 정규식(is_tui_line) 라우팅 제로 — 렌더링 책임은 구독자(View)에게.
"""
from dataclasses import dataclass, field
import time


@dataclass(slots=True)
class LogEvent:
    """구조화된 로그 이벤트."""
    stage: str = "SYS"
    status: str = "OK"
    platform: str = "-"
    spec: str = "-"
    speed: str = "-"
    pct: float = None
    bar_frac: float = None
    msg: str = ""
    is_status: bool = False
    is_error: bool = False
    # msg가 이미 표시 완성형(컬럼 포맷·원문)일 때 True — 뷰는 재포맷하지 않는다
    rendered: bool = False
    timestamp: str = field(default_factory=lambda: time.strftime("[%H:%M:%S]"))

```

## File: log_history.py

```python
### log_history.py - 기동·구성요소·PO 서버 로그의 영구 히스토리 기록기
"""매 실행마다 구성요소 확인/업데이트, PO Token 서버 기동, 다운로더 원본 로그를
날짜별 파일로 남겨 문제 재현·디버깅의 1차 증거로 삼는다.

*  위치 : config.LOG_DIR (frozen: <exe>/logs, source: <repo>/logs)
*  파일 : chzzktube_YYYY-MM-DD.log (하루 1파일, UTF-8, append)
*  세션 : session_begin / session_end 로 시작·종료 마커 기록
*  정리 : KEEP_DAYS 초과된 오래된 히스토리 파일은 세션 시작 시 자동 삭제
*  의존 : config(leaf)만 사용·비Qt — 워커 스레드에서 호출해도 안전(threading.Lock).
          기록 실패는 절대 앱 동작을 방해하지 않는다(모든 예외 흡수).
"""
import datetime
import os
import threading

KEEP_DAYS = 30
_LOCK = threading.Lock()

def _now():
    return datetime.datetime.now()

def _log_path(now):
    import config
    return os.path.join(config.LOG_DIR, f"chzzktube_{now:%Y-%m-%d}.log")

def log(msg, level="INFO", **kwargs):
    """한 건(다중 줄 허용)을 오늘 히스토리 파일에 타임스탬프로 기록."""
    try:
        now = _now()
        lines = [
            l.rstrip()
            for l in str(msg).replace("\r", "").split("\n")
            if l.strip()
        ] or [""]
        with _LOCK:
            path = _log_path(now)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                for l in lines:
                    f.write(
                        f"[{now:%Y-%m-%d %H:%M:%S}] [{level:<5}] {l}\n"
                    )
    except Exception:
        pass  # 히스토리 기록 실패가 앱을 죽이지 않도록 흡수

def session_begin(app_name, app_version):
    """실행 세션 시작 마커 기록 + 오래된 히스토리 파일 정리."""
    log(
        f"===== {app_name} {app_version} 시작 (PID {os.getpid()}) =====",
        "BOOT",
    )
    log(
        "[~] 이 파일에는 구성요소 확인/업데이트, PO Token 서버 기동, "
        "다운로더 원본 로그가 기록됩니다.",
        "BOOT",
    )
    _prune()

def session_end():
    """실행 세션 종료 마커 기록."""
    log("===== 세션 종료 =====", "BOOT")

def exception(tag, t=None, v=None, tb=None):
    """미처리 예외 전체 트레이스백 기록. 인자 없이 except 블록 내에서도 호출 가능."""
    import sys
    import traceback

    if t is None:
        t, v, tb = sys.exc_info()
    try:
        body = "".join(traceback.format_exception(t, v, tb) or []).strip()
    except Exception:
        body = f"{t}: {v}"
    log(f"[{tag}]\n{body}", "ERROR")

def _prune():
    """KEEP_DAYS 초과 히스토리 파일 삭제 (세션 시작 시 1회)."""
    try:
        import config
        d = config.LOG_DIR
        cutoff = (_now() - datetime.timedelta(days=KEEP_DAYS)).timestamp()
        with _LOCK:
            if not os.path.isdir(d):
                return
            for name in os.listdir(d):
                if not (name.startswith("chzzktube_") and name.endswith(".log")):
                    continue
                p = os.path.join(d, name)
                try:
                    if os.path.getmtime(p) < cutoff:
                        os.remove(p)
                except OSError:
                    pass
    except Exception:
        pass

```

## File: main.py

```python
﻿##### main.py - 메인 윈도우 및 앱 실행 진입점
from collections import deque
import os
import platform
import re
import sys
import time

from PySide6.QtCore import qInstallMessageHandler


def qt_message_handler(mode, context, message):
    if "must be a top level window" in message:
        return
    sys.stderr.write(message + "\n")


qInstallMessageHandler(qt_message_handler)

from PySide6.QtCore import QObject, Qt, QThread, QTimer, QEvent, Signal
from PySide6.QtGui import QFont, QFontDatabase, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

# [시퀀스 코디네이터] 시작 시퀀스 단일 책임자
from startup_coordinator import StartupCoordinator
from pot_manager import POTManager

##### 설정 상수/경로/로드·저장은 config 모듈에서 관리
import config
import log_console
import log_history
import pot_provider
import theme
from controller import MediaController
from dialogs import ExitConfirmDialog, SettingsDialog, VerboseLogWindow
from update_worker import UpdateWorker
from utils import _open_windows_explorer

# [URL 인식 디바운스] 키 입력(타이핑) 침묵 기준 지연 — "타이핑 끝남"은 미래 입력
# 부재를 감지해야만 알 수 있어 키 입력 경로에선 구조상 필수다.
_ANALYZE_DEBOUNCE_MS = 900
# [벌크 입력 공출화] 붙여넣기·드래그&드롭·TXT 로드는 통째로 들어오므로 즉시 분석.
# 0ms 대신 150ms를 두는 건 프로그램적 다중 setText가 한 프레임에 겹칠 때의 점화 병합용.
_BULK_INPUT_DELAY_MS = 150

try:
    import winsound
except ImportError:
    winsound = None

APP_NAME = config._APP_NAME
APP_VERSION = config._APP_VERSION
BASE_DIR = config.BASE_DIR
CONFIG_DIR = config.CONFIG_DIR
CONFIG_FILE = config.CONFIG_FILE
ICON_PATH = config.ICON_PATH
DEFAULT_CONFIG = config.default_config()


class _GuiLogBridge(QObject):
    """순수 raw_log 백그라운드 스레드 이벤트를 Qt GUI 루프로 안전하게 흡수하는 브리지.

    raw_log의 데몬 dispatcher 스레드는 본 브리지의 Signal.emit만 호출하고,
    슬롯은 QueuedConnection으로 메인 스레드 이벤트 루프에서 실행된다 —
    배경 스레드의 QTextEdit 직접 접근(세그폴트/레이스 원인)을 차단한다.
    raw_log는 표준 라이브러리 기반 순수성을 유지하고, 스레드 경계 책임은
    GUI를 점유한 수신층(main.py)이 진다.
    """

    tui_signal = Signal(object, bool, bool)   # (event, is_status, is_error)
    full_signal = Signal(object, bool)        # (event, is_status)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # [히스토리] 실행 세션 시작 마커 — 이후 모든 구성요소/PO 서버/다운로드 로그 기록
        log_history.session_begin(APP_NAME, APP_VERSION)
        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        self.setMinimumSize(800, 680)
        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))

        self.setStyleSheet(theme.TUI_STYLE)

        self.cfg = self._load_config()

        # 다운로드 + 분석 세션 상태/워커는 컨트롤러가 소유 (dl_state 프로퍼티로 접근 가능)
        self.ctrl = MediaController(self)
        self.extracted_data = {"info": None, "v_list": [], "a_list": []}

                # StartupCoordinator: DEPS/POT/업데이트 시그널을 중앙에서 수신하고 3대 로그에 전파
        # POTManager: POT 서버 수명주기 단일 관리자 (prewarm + gate 통합).
        # 단일 인스턴스 원칙 (HANDOVER §7): 시그널 연결 전 최초 1회만 생성
        self._pot_manager = POTManager()
        self._startup_coord = StartupCoordinator(self._pot_manager, self)
        self._pot_manager.pot_finished.connect(self._on_pot_finished)
        self._startup_coord.ui_unlocked.connect(self._on_startup_unlocked)

        self.settings_dlg = None
        self.verbose_win = None

        self.analyze_timer = QTimer()
        self.analyze_timer.setSingleShot(True)
        self.analyze_timer.timeout.connect(self.run_analysis)

        # ── 분석 워커 시그널 바인딩 (Controller → View 포워딩) ──
        self.ctrl.analyze_result_ready.connect(self.on_analyze_success)
        self.ctrl.analyze_error_occurred.connect(self.on_analyze_error)

        # POTManager가 서버 수명주기를 담당
        self._startup_completed = False
        self._pending_download = None

        self.init_ui()

        # 구성요소(yt-dlp/streamlink) 자동 업데이트 확인 — 기동 직후 비동기 1회
        QTimer.singleShot(500, self._start_update_check)

        # [응답없음 폴백] 구성요소 체인(POT 포함)이 15초 안에 끝나지 않으면
        # 입력을 강제 개방 — URL 잠금이 영구화되지 않게 한다.
        QTimer.singleShot(15000, self._force_unlock_input)

    @property
    def dl_state(self):
        """다운로드 세션 상태 — DownloadController.state의 별칭."""
        return self.ctrl.state

    def closeEvent(self, event):
        # 1. 최소화 상태 해제 및 Qt 표준 창 활성화
        self.setWindowState(
            self.windowState() & ~Qt.WindowState.WindowMinimized
            | Qt.WindowState.WindowActive
        )
        self.activateWindow()

        is_running = self.dl_state.get("running", False)
        parent_dlg = (
            self.settings_dlg
            if (
                hasattr(self, "settings_dlg")
                and self.settings_dlg
                and self.settings_dlg.isVisible()
            )
            else self
        )
        dlg = ExitConfirmDialog(parent_dlg, is_running=is_running)

        # 2. [소리 복구 & 반짝임] Windows 시스템 알림 음(Beep) 재생 및 작업 표시줄 알림
        if platform.system() == "Windows":
            self._flash_dialog(dlg, winsound)

        result = dlg.exec()

        # [종료] 클릭 시 -> 스레드 안전 중단 후 즉시 종료
        if result == 1:
            if hasattr(self, "settings_dlg") and self.settings_dlg:
                self.settings_dlg.close()
            if getattr(self, "verbose_win", None) is not None:
                self.verbose_win.close()
            self.ctrl.shutdown(1000)
            if self.ctrl.worker_dl is not None and self.ctrl.worker_dl.isRunning():
                import raw_log
                from log_event import LogEvent
                raw_log.raw(
                    "shutdown",
                    LogEvent(
                        stage="SYS", status="WARN",
                        msg="shutdown: download worker not stopped (1s) — cancelling then exiting",
                        is_error=False,
                    ),
                    to_tui=False,
                )
            # [스레드 경계] 종료 전 러닝 QThread 회수 — 좀비 분석 워커/기동 워커가
            # 살아있으면 Qt가 "QThread: Destroyed while thread is still running"
            # 경고와 함께 종료 크래시를 낼 수 있다. terminate 금지 원칙 유지,
            # 짧은 wait만 시도 (워커들은 취소 플래그로 자연 종료를 약속받는다).
            for w in list(getattr(self, "_zombie_workers", []) or []):
                if w is not None and w.isRunning():
                    w.wait(1500)
                    if w.isRunning():
                        import raw_log
                        from log_event import LogEvent
                        raw_log.raw(
                            "shutdown",
                            LogEvent(
                                stage="SYS", status="WARN",
                                msg="shutdown: orphaned analyze worker (1.5s) — forcing exit",
                                is_error=False,
                            ),
                            to_tui=False,
                        )
            # POTManager가 서버/워커 정리 담당
            self._pot_manager.cancel()

            for name in ("update_worker",):
                w = getattr(self, name, None)
                if w is not None and w.isRunning():
                    w.wait(1500)
                    if w.isRunning():
                        import raw_log
                        from log_event import LogEvent
                        raw_log.raw(
                            "shutdown",
                            LogEvent(
                                stage="SYS", status="WARN",
                                msg=f"shutdown: startup worker ({name}) not stopped (1.5s) — forcing exit",
                                is_error=False,
                            ),
                            to_tui=False,
                        )

            # 다운로드 워커의 라이브 녹화 프로세스 정리
            if hasattr(self.ctrl, "worker_dl") and self.ctrl.worker_dl is not None:
                try:
                    if hasattr(self.ctrl.worker_dl, "kill_live_process"):
                        self.ctrl.worker_dl.kill_live_process()
                except Exception:
                    pass

            log_history.session_end()
            import raw_log
            raw_log.flush()
            raw_log.shutdown()
            event.accept()

        # [취소] 클릭 시 -> 창 닫기 취소
        else:
            event.ignore()

    @staticmethod
    def _flash_dialog(dlg, winsound):
        """Windows에서 종료 확인 대화상자에 알림음 발생 + 작업 표시줄 반짝임."""
        if winsound:
            try:
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
            except Exception:
                pass
        try:
            import ctypes

            class FLASHWINFO(ctypes.Structure):
                _fields_ = [
                    ("cbSize", ctypes.c_uint),
                    ("hwnd", ctypes.c_void_p),
                    ("dwFlags", ctypes.c_uint),
                    ("uCount", ctypes.c_uint),
                    ("dwTimeout", ctypes.c_uint),
                ]

            hwnd = int(dlg.winId())
            info = FLASHWINFO(ctypes.sizeof(FLASHWINFO), hwnd, 3, 3, 0)
            ctypes.windll.user32.FlashWindowEx(ctypes.byref(info))
        except Exception:
            pass

    def save_cfg(self):
        config.save_config(self.cfg)

    def _load_config(self):
        """설정 로드 (기본값 + 기존 설정 병합). 상세 로직은 config 모듈에 위임."""
        return config.load_config()

    def init_ui(self):
        """[4단계] Blank Slate — setup_ui()로 위임."""
        self.setup_ui()

    def setup_ui(self):
        """[TUI Refactor] Hyper-Minimal Modern TUI — flat, borderless, mono.

        ├── Path ...  │ [F1] [F2] │ [F12] [F3]
        ├── ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─
        │ > [url_input..........................] [F4] [ENTER]
        ├── ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─
        └── [10:54:14] DEPS  │ OK  │ ...        ← console (stretch=1)
        """
        from PySide6.QtWidgets import QFrame

        # ── 중앙 위젯 / 메인 레이아웃 (flat, no master wrapper) ──
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(12, 8, 12, 8)
        main_layout.setSpacing(0)

        # ── 헬퍼: tui-tag 클래스 버튼 ──
        def _tui_tag(text, tooltip, slot):
            b = QPushButton(text)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(slot)
            b.setToolTip(tooltip)
            b.setProperty("class", "tui-tag")
            b.style().unpolish(b)
            b.style().polish(b)
            return b

        # ── 헬퍼: 힌트 버튼 사이 딤 '│' 구분자 ──
        def _tui_sep():
            sep = QLabel("│")
            sep.setStyleSheet(
                f"color: {theme.FG_DIM}; border: none; background: transparent; padding: 0px;"
            )
            return sep

        # ── 헬퍼: 1px 섹션 구분선 ──
        def _separator():
            line = QFrame()
            line.setProperty("class", "tui-separator")
            line.setFrameShape(QFrame.Shape.HLine)
            line.setFrameShadow(QFrame.Shadow.Plain)
            line.setStyleSheet("QFrame { background-color: #1a1a1a; max-height: 1px; min-height: 1px; border: none; }")
            line.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            return line

        # ════════════════════════════════════════════════════════════════════
        # Layer 1: Configuration (flat — no border, no title)
        # ════════════════════════════════════════════════════════════════════
        self.header_group = QGroupBox("")
        self.header_group.setObjectName("header_group")
        self.header_group.setProperty("class", "tui-panel")
        self.header_group.style().unpolish(self.header_group)
        self.header_group.style().polish(self.header_group)
        hlay = QHBoxLayout(self.header_group)
        hlay.setContentsMargins(0, 0, 0, 0)
        hlay.setSpacing(6)

        self.path_label = QLabel()
        self.path_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.path_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self._update_path_label()
        hlay.addWidget(self.path_label, 1)

        self.btn_change = _tui_tag(
            "[ F1: Change ]", "Change download folder (F1)", self.change_folder
        )
        self.btn_open = _tui_tag(
            "[ F2: Open ]",
            "Open download folder (F2)",
            lambda: _open_windows_explorer(self.cfg["download_path"]),
        )
        hlay.addWidget(self.btn_change)
        hlay.addWidget(self.btn_open)

        # v_line: Change/Open과 Full Log/Settings 그룹 사이 시각 구분
        self.v_line = QLabel("\u2502")
        self.v_line.setProperty("class", "tui-sep")
        hlay.addWidget(self.v_line)

        self.btn_full_log = _tui_tag(
            "[ F12: Full Log ]", "Toggle full log window (F12)", self.toggle_verbose_log
        )
        self.btn_settings = _tui_tag(
            "[ F3: Settings ]", "Open settings (F3)", self.open_settings
        )
        hlay.addWidget(self.btn_full_log)
        hlay.addWidget(self.btn_settings)

        main_layout.addWidget(self.header_group)

        # ── 1px 구분선 ──
        main_layout.addWidget(_separator())

        # ════════════════════════════════════════════════════════════════════
        # Layer 2: Input & Action (flat — no border, prompt-style)
        # ════════════════════════════════════════════════════════════════════
        self.input_group = QGroupBox("")
        self.input_group.setObjectName("input_group")
        self.input_group.setProperty("class", "tui-panel")
        self.input_group.style().unpolish(self.input_group)
        self.input_group.style().polish(self.input_group)
        ilay = QHBoxLayout(self.input_group)
        ilay.setContentsMargins(0, 0, 0, 0)
        ilay.setSpacing(6)

        # 프롬프트 `>` 기호 — 콘솔 출력처럼 보이게
        self.prompt_label = QLabel(">")
        prompt_font = QFont("Cascadia Mono", 11)
        prompt_font.setBold(True)
        self.prompt_label.setFont(prompt_font)
        self.prompt_label.setStyleSheet("color: #4ec9b0; border: none; background: transparent; padding: 0px;")
        ilay.addWidget(self.prompt_label)

        # [ObjectName] url_input — TUI_STYLE의 QLineEdit#url_input 선택자 타겟
        self.url_input = QLineEdit()
        self.url_input.setObjectName("url_input")
        self.url_input.setPlaceholderText("URL, playlist, or channel URL...")
        # [하이퍼미니멀] 네이티브 (x) 클리어 버튼 제거 — ESC 키로 대체
        self.url_input.setClearButtonEnabled(False)
        self.url_input.installEventFilter(self)
        self.url_input.textChanged.connect(self.on_url_changed)
        self.url_input.setDragEnabled(True)
        self.url_input.acceptDrops()
        self.url_input.dropEvent = lambda e: self._on_url_drop(e.mimeData())
        self.url_input.returnPressed.connect(self.toggle_download)
        ilay.addWidget(self.url_input, 1)

        self.btn_txt = _tui_tag(
            "[ F4: Load .txt ]", "Load URL list from TXT (F4)", self.pick_txt
        )
        ilay.addWidget(self.btn_txt)
        ilay.addWidget(_tui_sep())

        self.btn_enter = _tui_tag(
            "[ ENTER: Start ]",
            "Start download (Enter)",
            self.toggle_download,
        )
        self.btn_esc = _tui_tag(
            "[ ESC: Clear ]",
            "Clear input (Esc) — abort when running",
            self._esc_action,
        )
        ilay.addWidget(self.btn_esc)
        ilay.addWidget(_tui_sep())
        ilay.addWidget(self.btn_enter)

        main_layout.addWidget(self.input_group)

        # ── 1px 구분선 ──
        main_layout.addWidget(_separator())

        # ════════════════════════════════════════════════════════════════════
        # Layer 3: Live Console Monitor (flat, stretch=1 → 100% 채움)
        # ════════════════════════════════════════════════════════════════════
        self.console_group = QGroupBox("")
        self.console_group.setObjectName("console_group")
        self.console_group.setProperty("class", "tui-panel")
        self.console_group.style().unpolish(self.console_group)
        self.console_group.style().polish(self.console_group)
        self.console_group.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        clay = QVBoxLayout(self.console_group)
        clay.setContentsMargins(0, 0, 0, 0)
        clay.setSpacing(0)

        # [ObjectName] console_log — TUI_STYLE의 QTextEdit#console_log 선택자 타겟
        self.te_concise = QTextEdit()
        self.te_concise.setObjectName("console_log")
        self.te_concise.setReadOnly(True)
        self.te_concise.document().setDocumentMargin(0)
        font = QFont("Cascadia Mono", 11)
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setFamilies(["Cascadia Mono"])
        self.te_concise.setFont(font)
        self.console = log_console.ConciseLogConsole(self.te_concise)

        clay.addWidget(self.te_concise, 1)
        main_layout.addWidget(self.console_group, stretch=1)

        # ── 보조 상태 초기화 ──
        self._full_log_buf: deque[str] = deque(maxlen=4096)
        self._last_status_line = ""
        # [버스 구독 — 스레드 경계 분리] raw_log의 순수 데몬 스레드는 브리지의
        # Signal.emit만 호출하고, 슬롯은 QueuedConnection으로 GUI 스레드 이벤트
        # 루프에서 실행된다 — 배경 스레드의 QTextEdit 직접 접근을 차단한다.
        self._gui_bridge = _GuiLogBridge(self)
        self._gui_bridge.tui_signal.connect(
            self._render_concise, Qt.ConnectionType.QueuedConnection
        )
        self._gui_bridge.full_signal.connect(
            self._mirror_event_full, Qt.ConnectionType.QueuedConnection
        )
        import raw_log
        raw_log.subscribe_concise(self._gui_bridge.tui_signal.emit)
        raw_log.subscribe_full(self._gui_bridge.full_signal.emit)
        self.update_ui_state()

    def _on_url_drop(self, mime_data):
        """드래그드롭된 .txt 파일 URL 자동 추출."""
        if not mime_data.hasUrls():
            return
        for url in mime_data.urls():
            path = url.toLocalFile()
            if path.lower().endswith(".txt"):
                self.pick_txt_from_path(path)
                return
            if path.startswith("http://") or path.startswith("https://"):
                self.url_input.setText(path)
                return

    def pick_txt_from_path(self, path):
        """선택된 .txt 파일 URL 로드."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = [
                    l.strip() for l in f if l.strip() and not l.strip().startswith("#")
                ]
            if lines:
                self.url_input.setText("\n".join(lines))
                self.append_concise_log(
                    log_console.emit_event(
                        "SYS", "OK", "TXT", f"{len(lines)} URLs"
                    ),
                    is_status=False,
                    is_error=False,
                )
        except Exception:
            self.append_concise_log(
                log_console.emit_event("SYS", "FAIL", "TXT", "read fail"),
                is_status=False,
                is_error=True,
            )

    def abort_download(self):
        """실행 중 다운로드 중단 (ESC 버튼 / 단축키 공용)."""
        if self.ctrl.running:
            self.ctrl.request_cancel()
            self.append_concise_log(
                log_console.emit_event("DL", "ABORT", "-", "download canceled by user"),
                is_status=False,
                is_error=True,
            )

    def _esc_action(self):
        """ESC 컨텍스트 액션 — 실행 중이면 중단, pick 대기면 취소, 아니면 입력 클리어."""
        state = self.get_current_app_state()
        if state == "RUNNING":
            self.abort_download()
        elif state == "PICKING":
            self._cancel_pick()
        elif state == "ANALYZING":
            self.ctrl.request_cancel()
        else:
            self.url_input.clear()

    def eventFilter(self, obj, event):
        """url_input 내부 ESC — 클리어(아이들) / 중단(실행 중) 처리."""
        if (
            obj is self.url_input
            and event.type() == QEvent.Type.KeyPress
            and event.key() == Qt.Key.Key_Escape
        ):
            self._esc_action()
            return True
        return super().eventFilter(obj, event)

    def _update_path_label(self):
        """PATH 라벨 TUI 텍스트 갱신 — `path_label` 위젯 갱신."""
        path = self.cfg.get("download_path", "")
        self.path_label.setText(
            f"<span style='color:#4ec9b0; font-weight:bold;'>Path</span> {path}"
        )

    def change_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select Download Folder", self.cfg["download_path"]
        )
        if folder:
            self.cfg["download_path"] = os.path.normpath(folder)
            self._update_path_label()
            self.save_cfg()
            self.append_concise_log(
                log_console.emit_event(
                    "SYS", "OK", "CFG", f"path → {self.cfg['download_path']}"
                ),
                is_status=False,
                is_error=False,
            )

    def format_target_url(self, url, max_len=50):
        """URL 접기 — 포매팅은 log_console.format_target_url에 위임."""
        return log_console.format_target_url(url, max_len)

    def open_settings(self):
        if (
            hasattr(self, "settings_dlg")
            and self.settings_dlg
            and self.settings_dlg.isVisible()
        ):
            self.settings_dlg.activateWindow()
            return
        self.settings_dlg = SettingsDialog(self)
        self.settings_dlg.show()

    def pick_txt(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select TXT File",
            self.cfg["download_path"],
            "Text Files (*.txt);;All Files (*.*)",
        )
        if path:
            self.url_input.setText(os.path.normpath(path))

    def on_url_changed(self):
        self.analyze_timer.stop()
        text = self.url_input.text().strip()

        # [핵심] URL을 지웠을 때 분석 타이머·로그 즉시 초기화
        if not text:
            self._last_input_len = 0
            self.extracted_data = {"info": None, "v_list": [], "a_list": []}

            # [결함 수리] terminate()+wait()는 GIL을 보유한 파이썬 스레드를
            # 야매 종료시켜 GUI 전체의 파이썬 실행을 영구 정지시켰다 — 이 뒤의
            # 로그 정리(clear_status_line)가 절대 실행되지 않아 'URL을 지워도
            # 분석중·URL 로그가 남는' 현상의 근본 원인. 유기 패턴으로 대체.
            self._abandon_analyze_worker()
            self.console.clear_status_line()
            # 직전 분석 결과 블록도 철회 — 링크를 지우면 그 링크의 분석 로그가 남아있던 현상 방지
            self._discard_analysis_result()
            return

        # [타이핑 인식 가드] 입력 증분으로 '키 입력'과 '벌크 입력'을 구별한다.
        #
        # "타이핑을 끝냈다"는 사실은 미래 입력 부재를 감지해야만 알 수 있으므로
        # 키 입력 경로는 침묵 대기(디바운스)가 구조상 필수다. 반면 붙여넣기·
        # 드래그&드롭·TXT 로드는 한 이벤트에 텍스트가 통째로 들어오므로
        # 증분 길이가 1을 초과 — 이 경우 지연을 걸 필요가 없다.
        prev_len = getattr(self, "_last_input_len", 0)
        self._last_input_len = len(text)
        is_bulk_input = (len(text) - prev_len) > 1

        if not self.ctrl.running and not self.ctrl.picking and getattr(
                self, "_startup_completed", False
            ):
            # [URL 형태 가드] 스킴 또는 '문자.문자' 형태의 도메인이 없으면
            # 분석 후보가 아니다 — 부분 타이핑에서의 불필요한 점화 방지.
            if "://" in text or re.search(r"\S\.\S", text):
                delay = _BULK_INPUT_DELAY_MS if is_bulk_input else _ANALYZE_DEBOUNCE_MS
                self.analyze_timer.start(delay)

    def _ensure_pot_for_info(self, info):
        """PO 필요 여부 판단 후 필요 시에만 서버 가동.

        [POTManager 위임] 게이트 책임은 POTManager가 담당.
        Spawn(Popen)은 POTManager.ensure_ready("gate")로 지연.
        """
        needs_pot = False
        if info:
            age_limit = info.get("age_limit") or 0
            if age_limit > 0:
                needs_pot = True
            availability = info.get("availability") or ""
            if isinstance(availability, str) and availability.lower() in (
                "needs_auth",
                "premium_only",
                "subscriber_only",
                "private",
            ):
                needs_pot = True

        import raw_log
        from log_event import LogEvent
        event = LogEvent(
            stage="POT", status="RUN", platform="pot", spec="-",
            msg=(
                f"gated={needs_pot} age_limit={age_limit if info else '-'} "
                f"availability={((info or {}).get('availability') or '-')}"
            ),
        )
        raw_log.raw("pot-gate", event, to_tui=True)

        if needs_pot:
            self.append_concise_log(
                log_console.emit_event("POT", "RUN", "pot", "starting..."),
                is_status=True,
                is_error=False,
            )
            # [POTManager] gate 모드로 서버 기동 (중복 스폰 가드 내장)
            self._pot_manager.ensure_ready("gate")



    def run_analysis(self):
        url = self.url_input.text().strip()
        if not url:
            return
        self.append_concise_log(
            log_console.emit_event("ANAL", "RUN", "-", "analyzing..."),
            is_status=True,
            is_error=False,
        )

        # 이전 링크의 분석 결과 블록이 마지막에 남아 있으면 철회한다.
        self._discard_analysis_result()

        self.base_anim_url = url

        # Controller가 기존 워커 유기 + 새 워커 생성을 담당 (Zombie Pattern)
        self.ctrl.spawn_analyzer(url, self.cfg)
        self.update_ui_state()

    def stop_analysis_anim(self, ok=True):
        """분석 완료/실패 시 최종 결과 로그를 히스토리에 박제 (마침표 애니메이션 정리 불요)."""
        if not ok:
            return

        data = self.extracted_data or {}
        info = data.get("info") or {}
        v_list = data.get("v_list", [])
        a_list = data.get("a_list", [])
        uploader = (
            info.get("uploader")
            or info.get("channel")
            or info.get("uploader_id")
            or info.get("creator")
            or ""
        )
        title = info.get("title") or data.get("title") or ""
        meta = " · ".join(x for x in (uploader, title) if x)

        # 플랫폼 축약기호 (YT / CHZ 등)
        platform = self._platform_of_url()

        # 해상도: v_list 첫 항목에서 추출
        v_first = v_list[0] if v_list else {}
        res = ""
        if isinstance(v_first, dict):
            h = v_first.get("height") or v_first.get("v_height") or 0
            fps = v_first.get("fps") or v_first.get("v_fps") or 0
            if h:
                res = f"{h}p{fps}" if fps else f"{h}p"

        # ANAL OK 메인 라인: Platform=사이트, Spec=해상도, Msg=stream analyzed · channel · title
        counts = log_console.format_analysis_counts(len(v_list), len(a_list))
        base_msg = f"stream analyzed{counts}"
        if meta:
            base_msg += f" · {meta[:80]}"
        # [버스 v3.3.0] 분석 성공 -> 논리 LogEvent(근원 라벨링). _render_concise가 컬럼화,
        # _mirror_event_full이 F12에 원본 msg 기록. format_log_line 직접 호출 제거.
        import raw_log
        from log_event import LogEvent
        raw_log.raw(
            "anal",
            LogEvent(
                stage="ANAL", status="OK", platform=platform, spec=res,
                msg=base_msg, is_status=True, is_error=False,
            ),
            to_tui=True,
        )

        # 마지막 블록 철회 가드
        self._analysis_block_active = True
        self._analysis_block_count = self.console.last_status_block_count
        self._analysis_last_line = self.console.last_content_block_text()

        # 비디오/오디오 포맷 로그: 별도 줄로 출력 (코덱만 표시, 채널명·제목 제외)
        self._emit_format_logs(v_list, a_list, platform)

    def _emit_format_logs(self, v_list, a_list, platform):
        """스트림 분석 완료 후 비디오/오디오 코덱 사양을 별도 로그로 출력."""
        import raw_log
        from log_event import LogEvent

        v_codecs = list(dict.fromkeys(f.get("vcodec") for f in v_list if f.get("vcodec")))
        a_codecs = list(dict.fromkeys(f.get("acodec") for f in a_list if f.get("acodec")))

        if v_codecs:
            msg = f"video: {', '.join(v_codecs[:4])}"
            raw_log.raw(
                "anal",
                LogEvent(stage="ANAL", status="OK", platform=platform, spec="V-FMT", msg=msg),
                to_tui=True,
            )
        if a_codecs:
            msg = f"audio: {', '.join(a_codecs[:4])}"
            raw_log.raw(
                "anal",
                LogEvent(stage="ANAL", status="OK", platform=platform, spec="A-FMT", msg=msg),
                to_tui=True,
            )

    def _format_analysis_summary(self):
        """분석 완료 요약 — 채널명 · 제목 등 기본 정보 (플레이리스트/치지직 공용)."""
        data = self.extracted_data or {}
        info = data.get("info") or {}
        uploader = (
            info.get("uploader")
            or info.get("channel")
            or info.get("uploader_id")
            or info.get("creator")
            or ""
        )
        title = info.get("title") or data.get("title") or ""
        meta = " · ".join(x for x in (uploader, title) if x)
        if not meta:
            return ""
        return " — " + meta[:80]

    def _discard_analysis_result(self):
        """직전 분석 결과 블록을 철회한다 (마지막 콘텐츠일 때만)."""
        if not getattr(self, "_analysis_block_active", False):
            return
        last_text = self.console.last_content_block_text()
        if last_text != getattr(self, "_analysis_last_line", None):
            self._analysis_block_active = False
            return
        self.console.remove_last_blocks(getattr(self, "_analysis_block_count", 0))
        self._analysis_block_active = False

    def _start_update_check(self):
        """구성요소(yt-dlp/streamlink) 최신 버전 비동기 확인 — 기동 0.5초 후 1회."""
        self.update_worker = UpdateWorker(self, upgrade=False, channel=self.cfg.get("update_channel", "stable"), check_updates=self.cfg.get("auto_update_check", True))
        # 구성요소 확인 라인은 필터 경유 — 루틴 '최신' 라인 간결 생략 + 히스토리 전건
        self.update_worker.check_done.connect(self._on_update_check_done)
        # [응답없음 방지] 낮은 우선순위로 시작해 GIL을 메인 스레드에 양보
        self.update_worker.start(QThread.Priority.LowPriority)

    def _on_update_check_done(self, stale):
        """버전 확인 결과 처리 — 메인에 결론 한 줄, 그 뒤 upgrade 워커로 진행.

        [min profile] 메인 콘솔에 emit되는 DEPS 라인은 정확히 한 줄:
        결론(최신 / 업데이트 가능 / 일시 장애). 패키지별 raw 라인은
        _component_line을 통해 상세로그로만 흘러간다.

        [시그널 교통 정리] check_done(list)은 시그니처가 (bool, str)이 아니므로
        Coordinator에 직결하면 안 된다 — 여기서 결론 라인 출력 + upgrade 워커
        기동 + Coordinator에 deps 완료 보고(report_deps)를 순서대로 수행한다.
        """
        # [결론 라인] — 메인 콘솔에 단 한 줄
        if stale:
            summary = ", ".join(f"{label} {cur}→{latest}" for label, _, cur, latest in stale)
            self.append_concise_log(
                log_console.emit_event(
                    "DEPS", "WARN", "-", f"update — {summary}"
                ),
                is_status=False,
                is_error=False,
            )
            self._stale_updates = True
        else:
            self._stale_updates = False
            # [결론 라인] 최신 상태 — deps ok 단 한 줄 (체크 5줄과 구분되는 결론)
            self.append_concise_log(
                log_console.emit_event("DEPS", "OK", "-", "deps ok"),
                is_status=False,
                is_error=False,
            )
        # [stale case] Dev/Frozen integration — UpdateWorker handles all deps (PyPI + ffmpeg + node)
        # stale로 확인된 패키지만 업그레이드, 나머지는 수급(ensure)만 — 2중 출력 방지
        self.update_worker = UpdateWorker(self, upgrade=True, stale_updates=stale, channel=self.cfg.get("update_channel", "stable"), check_updates=self.cfg.get("auto_update_check", True))
        self.update_worker.upgrade_done.connect(self._startup_coord.report_upgrade)
        self.update_worker.start()
        # [Coordinator 보고] deps 체크 단계 완료 — READY 게이트용 플래그.
        # 결론 라인은 위에서 이미 출력했으므로 Coordinator는 플래그만 세팅한다.
        self._startup_coord.report_deps(not bool(stale), "deps ok" if not stale else "update")
        # [유휴 프리웜] deps 완료 즉시 POT prewarm 시작 — 3초 지연 제거.
        # Popen 없이 디스크 산출물만 준비 (RAM 0MB·포트 미점유). READY 게이트
        # 미포함 — 실패해도 기동 블록 없음. 중복 스폰은 POTManager 가드.
        self._pot_manager.ensure_ready("prewarm")

    def _on_pot_finished(self, ok: bool, msg: str):
        """POT gate 완료 시 대기 중인 다운로드를 한 번만 재개한다."""
        pending = getattr(self, "_pending_download", None)
        if (
            pending is None
            or not ok
            or not self._pot_manager.is_ready()
        ):
            return
        targets, v_id, a_id = pending
        self._pending_download = None
        self._start_download(targets, v_id, a_id)

    def _on_startup_unlocked(self):
        """StartupCoordinator READY 신호 수신 — 입력 잠금을 해제한다."""
        self._startup_completed = True
        self.update_ui_state()

    def _force_unlock_input(self):
        """15초 내 기동 체인이 완료되지 않을 경우 강제 READY 폴백."""
        if self._startup_completed:
            return
        self._startup_coord.force_unlock()

    def _is_stale_analyze_signal(self):
        """유령 분석 결과 판별 — 지운 뒤 "stream analyzed"가 한 번 더 뜨는 버그 차단.

        [경합상태] 워커 스레드의 result_ready/error_occurred는 GUI 이벤트 큐에
        적재(queued connection)된 뒤 전달된다. 유기 패턴의 disconnect()는
        "이후" 방출을 막을 뿐 이미 큐에 있는 전달은 취소하지 못한다 —
        그래서 입력을 지운 직전 큐잉된 결과가 슬롯에 도착해 로그를 오염시켰다.

        [Signal forwarding] Worker 시그널은 Controller.analyze_* 중계 Signal을
        거쳐 View 슬롯에 도달한다 (PySide6 Signal to Signal 직접 연결).
        이 체인에서 self.sender()는 MediaController를 반환하므로 워커 식별이
        불가능하다. state["analyzing"] 플래그 + URL 입력 여부로 대체 검증한다.
        """
        if not self.ctrl.state.get("analyzing"):
            return True  # 분석 상태가 아니면(유기·완료) 모든 큐잉된 시그널 폐기
        if not self.url_input.text().strip():
            return True  # 분석 도중 입력이 비워짐
        return False

    def on_analyze_success(self, data):
        if self._is_stale_analyze_signal():
            return
        self.extracted_data = data
        # PO 필요 여부 판단 후 필요 시에만 서버 가동
        self._ensure_pot_for_info(data.get("info"))
        if data.get("is_playlist"):
            self.stop_analysis_anim()
            self.update_ui_state()
            return
        # [포맷 직접 고르기] 딥 분석 결과 → 메뉴 출력 + 입력 대기
        if getattr(self, "_pick_pending", False):
            self._pick_pending = False
            self._show_pick_menu(data)
            self.update_ui_state()
            return
        self.stop_analysis_anim()
        self.update_ui_state()
        # 콜백은 결과만 보관 — 콤보/버튼이 없으므로 UI 갱신 없음
        # 좌측 패널이 자동 처리 — 별도 UI 갱신 없음

    def on_analyze_error(self, err_msg):
        if self._is_stale_analyze_signal():
            return
        pick_pending = getattr(self, "_pick_pending", False)
        self._pick_pending = False
        if pick_pending:
            self.ctrl.state["picking"] = False
        self.stop_analysis_anim(ok=False)
        self.update_ui_state()
        self.append_concise_log(
            log_console.emit_event("ANAL", "FAIL", "-", err_msg),
            True,   # is_status — analyzing... 을 에러 메시지로 덮어쓰기
            True,   # is_error
        )

    def get_current_app_state(self) -> str:
        """앱의 현재 단일 진실 상태(Single Source of Truth)를 도출한다."""
        if not getattr(self, "_startup_completed", False) or self._pot_manager.is_busy():
            return "STARTUP"
        if self.ctrl.running:
            return "RUNNING"
        if self.ctrl.analyzing:
            return "ANALYZING"
        if self.ctrl.picking:
            return "PICKING"
        return "IDLE"

    def update_ui_state(self):
        """상태 머신 기준 전역 UI 위젯 활성화 및 단축키 라벨 단일 통제."""
        state = self.get_current_app_state()

        # 1. URL 입력창 활성화
        self.url_input.setEnabled(state in ("IDLE", "PICKING"))

        # 2. 버튼별 Enable / Disable 선언적 제어
        self.btn_open.setEnabled(True)  # 저장위치 열기: 상시 허용
        self.btn_change.setEnabled(state == "IDLE")  # 저장위치 변경: IDLE만
        self.btn_settings.setEnabled(state in ("IDLE", "RUNNING"))  # 설정: IDLE, RUNNING 허용
        self.btn_txt.setEnabled(state == "IDLE")  # txt파일 열기: IDLE만

        # 3. ESC (제거/클리어/중단) 동적 라벨 & 활성화
        if state == "STARTUP":
            self.btn_esc.setEnabled(False)
            self.btn_esc.setText("[ ESC: Clear ]")
        elif state == "RUNNING":
            self.btn_esc.setEnabled(True)
            self.btn_esc.setText("[ ESC: Abort ]")
        elif state in ("ANALYZING", "PICKING"):
            self.btn_esc.setEnabled(True)
            self.btn_esc.setText("[ ESC: Cancel ]")
        else:  # IDLE
            self.btn_esc.setEnabled(True)
            self.btn_esc.setText("[ ESC: Clear ]")

        # 4. ENTER (다운로드/선택) 동적 라벨 & 활성화
        if state == "IDLE":
            self.btn_enter.setEnabled(True)
            self.btn_enter.setText("[ ENTER: Start ]")
        elif state == "PICKING":
            self.btn_enter.setEnabled(True)
            self.btn_enter.setText("[ ENTER: Select ]")
        else:  # STARTUP, ANALYZING, RUNNING
            self.btn_enter.setEnabled(False)
            self.btn_enter.setText("[ ENTER: Start ]")

        self.console.reset_status_flag()

    def showEvent(self, event):
        super().showEvent(event)
        # 첫 노출 시 viewport 실측으로 트리 예산 산정 + 라벨/버퍼 reflow.
        if hasattr(self, "console"):
            self.console.on_resize()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # 창 가로 확장 → 예산 갱신 + 기존 로그 전체 reflow (로그가 펼쳐진다).
        if hasattr(self, "console"):
            self.console.on_resize()

    # ── raw_log 버스 구독 슬롯 (v3.3.0) ──────────────────────────────
    def _render_concise(self, event, is_status=False, is_error=False):
        """[TUI 렌더러] 버스 concise 구독 — LogEvent → 컬럼 문자열 변환 후 출력.

        컬럼화는 뷰(메인로그 모듈)의 책임이다. raw 레이어는 운반만 하고,
        발행자가 근원에서 동봉한 라벨(stage/status/platform/spec)을 컬럼에 꽂는다.
        [중복 방지] history는 raw_log.raw가 수행한다 — 여기서 log_history 호출 안 함.
        [레이아웃 플래그] LogEvent 경유분은 컬럼/프리포맷 라인이므로 no_wrap=True —
        _flow_lines의 콘텐츠 판정 없이 래핑을 건너뛴다. bare 문자열은 비컬럼으로
        간주해 기존처럼 폭 예산으로 wrap한다.
        """
        from log_event import LogEvent
        if isinstance(event, LogEvent):
            line = log_console.format_log_line_for_event(event)
            no_wrap = True
        else:
            line = str(event)
            no_wrap = False
        # TUI buffer is bounded independently of the raw history.
        if len(line) > 4096:
            line = line[:4096] + "…"
        self.console.append(line, is_status, is_error, no_wrap=no_wrap)

    def _mirror_event_full(self, event, is_status=False):
        """F12 렌더러 — 구조화 이벤트를 콘솔 포맷터로 복원한다."""
        from log_event import LogEvent
        if isinstance(event, LogEvent):
            # F12는 event.msg만 추출하던 기존 경로를 탈피해 stage/status/spec 등
            # 구조화 컨텍스트를 보존한다. rendered 이벤트는 원문 포맷을 유지한다.
            line = log_console.format_log_line_for_event(event)
            if is_status:
                self._last_status_line = line
            self._mirror_full_log(line, is_status)
        else:
            line = str(event)
            if is_status:
                self._last_status_line = line
            self._mirror_full_log(line, is_status)

    def _mirror_full_log(self, msg, is_status=False):
        """상세 로그 버퍼 누적 + F12 창 미러링."""
        msg = str(msg)
        if len(msg) > 4096:
            msg = msg[:4096] + "…"
        ts = time.strftime("%H:%M:%S")
        stamped = "\n".join(f"[{ts}] {l}" if l else f"[{ts}]" for l in msg.split("\n"))
        if not is_status:
            self._full_log_buf.append(stamped)
        if (
            getattr(self, "verbose_win", None) is not None
            and self.verbose_win.isVisible()
        ):
            try:
                self.verbose_win.append(stamped, is_status)
            except Exception:
                pass

    def append_concise_log(self, msg, is_status=False, is_error=False, fg_color=None):
        # [버스 v3.3.0] UI 액션도 raw_log.raw 단일 경로 — history/F12/TUI 모두 raw_log가 담당.
        # 호출부는 LogEvent(emit_event 결과) 또는 미리 포맷된 문자열을 보낸다.
        # fg_color는 호출부에서 사용되지 않음 — 색상은 _log_line_segments가 status 라벨로 재분류.
        import raw_log
        from log_event import LogEvent
        if isinstance(msg, LogEvent):
            msg.is_status = is_status
            msg.is_error = is_error
            raw_log.raw("ui", msg, to_tui=True)
        else:
            raw_log.raw("ui", msg, is_status=is_status, is_error=is_error, to_tui=True)

    def toggle_verbose_log(self):
        """F12 상세 로그 창 토글 — 최초 진입 시 누적 버퍼로 초기화 후 미러링."""
        if (
            getattr(self, "verbose_win", None) is not None
            and self.verbose_win.isVisible()
        ):
            self.verbose_win.close()
            return
        if self.verbose_win is None:
            self.verbose_win = VerboseLogWindow(self)
            content = "\n".join(self._full_log_buf)
            if not content.strip():
                content = log_console.emit_event(
                    "SYS",
                    "OK",
                    "LOG",
                    "empty buffer",
                )
            self.verbose_win.set_content(content)
        self.verbose_win.show()
        self.verbose_win.raise_()
        self.verbose_win.activateWindow()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_F12:
            self.toggle_verbose_log()
            event.accept()
            return
        if event.key() == Qt.Key.Key_F1:
            self.change_folder()
            event.accept()
            return
        if event.key() == Qt.Key.Key_F2:
            _open_windows_explorer(self.cfg["download_path"])
            event.accept()
            return
        if event.key() == Qt.Key.Key_F3:
            self.open_settings()
            event.accept()
            return
        if event.key() == Qt.Key.Key_F4:
            self.pick_txt()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Escape:
            self._esc_action()
            event.accept()
            return
        super().keyPressEvent(event)

    def toggle_download(self):
        state = self.get_current_app_state()
        if state == "PICKING":
            self._submit_pick()
            return
        if state != "IDLE":
            return
        try:
            targets = MediaController.parse_targets(
                self.url_input.text().strip(),
                dedup=self.cfg.get("remove_duplicates"),
            )
        except ValueError as e:
            self.append_concise_log(
                log_console.emit_event("SYS", "FAIL", "-", f"parse error: {e}"),
                False, True
            )
            return
        if not targets:
            return

        # [포맷 직접 고르기] 1개 타깃 + pick_format 켜짐 → 딥 분석 후 선택 분기
        if self.cfg.get("pick_format") and len(targets) == 1:
            self._start_pick_flow(targets[0])
            return

        # POT 필요 영상이고 POT 기동 중이면 큐에 적재
        info = (self.extracted_data or {}).get("info") or {}
        age_limit = info.get("age_limit") or 0
        availability = info.get("availability") or ""
        needs_pot = age_limit > 0 or (
            isinstance(availability, str) and availability.lower() in (
                "needs_auth", "premium_only", "subscriber_only", "private"
            )
        )
        if needs_pot and self._pot_manager.is_busy():
            # POT 기동 중이면 큐에 넣고 사용자 알림
            self._pending_download = (targets, "auto", "auto")
            self.append_concise_log(
                log_console.emit_event("SYS", "WAIT", "pot", "queued — waiting for POT server"),
                is_status=True, is_error=False
            )
            return
        if needs_pot:
            self._wait_pot_if_needed()
            if not self._pot_manager.is_ready():
                self._pending_download = (targets, "auto", "auto")
                self.append_concise_log(
                    log_console.emit_event("SYS", "WAIT", "pot", "queued — waiting for POT server"),
                    is_status=True, is_error=False,
                )
                return

        self._start_download(targets, "auto", "auto")

    def _start_download(self, targets, v_id, a_id):
        """워커 스폰 공통 루틴 — 자동(해상도 제한 내 최고)/포맷 직접 고르기 공용."""
        self.ctrl.begin_download()

        self.append_concise_log(
            log_console.emit_event("DL", "RUN", "-", "downloading..."),
            is_status=True,
            is_error=False,
        )

        self.update_ui_state()

        live_hint = len(targets) == 1 and bool(
            (self.extracted_data.get("info") or {}).get("is_live")
        )
        # [다운로드 일관성] 분석에서 실증·통과한 클라이언트 그대로 전달 —
        # 시청 기록 다운로드가 봇 게이트/PO 토큰 경로에 재진입해 0%에
        # 머무르는 현상 방지 (auto면 기존 동작 유지).
        self.ctrl.spawn_worker(
            targets,
            self.cfg,
            v_id,
            a_id,
            is_live_hint=live_hint,
            v_spec=None,
            audio_desc="",
            yt_client=self.extracted_data.get("yt_client", "auto"),
        )

    def _wait_pot_if_needed(self):
        """PO Token 필요 영상(연령제한 등)인 경우 POT 서버 기동 트리거.
        논블로킹 — 큐 메커니즘(_pending_download + _on_pot_finished)이 완료 후 실행."""
        info = (self.extracted_data or {}).get("info") or {}
        age_limit = info.get("age_limit") or 0
        availability = info.get("availability") or ""
        needs_pot = age_limit > 0 or (
            isinstance(availability, str) and availability.lower() in (
                "needs_auth", "premium_only", "subscriber_only", "private"
            )
        )
        if not needs_pot:
            return
        
        # POT 서버가 이미 실행 중이면 즉시 ready 승격 — 기존 서버 재사용.
        # 이 경로는 gate 워커를 스폰하지 않으므로 pot_finished가 발행되지 않는다.
        # (use_existing 없이는 _pending_download가 영구 큐잉됨 — P0-4/5 회귀 방지)
        from po_client import server_ping
        if server_ping():
            self._pot_manager.use_existing()
            return
        
        # POT 서버가 없으면 기동만 트리거 (대기는 큐가 처리)
        self.append_concise_log(
            log_console.emit_event("POT", "RUN", "pot", "starting server..."),
            is_status=True,
            is_error=False,
        )
        # [POTManager] gate 모드로 서버 기동 (중복 스폰 가드 내장)
        self._pot_manager.ensure_ready("gate")

    # ── 포맷 직접 고르기 흐름 ──────────────────────────────────────────
    def _start_pick_flow(self, url):
        """딥 분석 스폰 → on_analyze_success에서 _show_pick_menu로 이어진다."""
        self._pick_targets = [url]
        self._pick_pending = True
        self.append_concise_log(
            log_console.emit_event("ANAL", "RUN", "-", "format list analyzing..."),
            is_status=True,
            is_error=False,
        )
        self.ctrl.spawn_analyzer(url, self.cfg, deep=True)
        self.update_ui_state()

    def _show_pick_menu(self, data):
        """포맷 목록을 콘솔에 번호 매겨 출력하고 입력 대기 상태로 전환."""
        v_list = data.get("v_list", [])
        a_list = data.get("a_list", [])
        if not v_list and not a_list:
            self.append_concise_log(
                log_console.emit_event("ANAL", "FAIL", "YT", "no formats for pick"),
                False, True,
            )
            self.update_ui_state()
            return
        lines = log_console.format_pick_menu(v_list, a_list)
        lines.append("enter: 'N' video  /  'N.M' v+a  /  empty=best")
        self.append_concise_log("\n".join(lines), False, False)
        self.ctrl.state["picking"] = True
        self.url_input.setFocus()
        self.update_ui_state()

    def _submit_pick(self):
        """pick 입력 파싱(1-based) 후 다운로드 시작 — v/a 각각 format_id 지정."""
        targets = getattr(self, "_pick_targets", None)
        if not targets:
            self.ctrl.state["picking"] = False
            return
        text = self.url_input.text().strip()
        v_list = self.extracted_data.get("v_list", [])
        a_list = self.extracted_data.get("a_list", [])
        v_id, a_id = "auto", "auto"
        if text:
            parts = re.split(r"[.,\s]+", text)
            try:
                if parts[0]:
                    idx = int(parts[0])
                    if not (1 <= idx <= len(v_list)):
                        raise ValueError
                    v_id = v_list[idx - 1]["id"]
                if len(parts) > 1 and parts[1].strip():
                    idx = int(parts[1])
                    if not (1 <= idx <= len(a_list)):
                        raise ValueError
                    a_id = a_list[idx - 1]["id"]
            except (ValueError, IndexError):
                self.append_concise_log(
                    log_console.emit_event("ANAL", "FAIL", "YT", "pick fail — retry"),
                    False, True,
                )
                return
        self.ctrl.state["picking"] = False
        self.append_concise_log(
            log_console.emit_event("DL", "OK", "YT", f"picked {v_id} · {a_id}"),
            False, False,
        )
        self._start_download(list(targets), v_id, a_id)

    def _cancel_pick(self):
        self.ctrl.state["picking"] = False
        self._pick_pending = False
        self._pick_targets = []
        self.append_concise_log(
            log_console.emit_event("DL", "ABORT", "YT", "format pick canceled"),
            False, True,
        )
        self.update_ui_state()

    def skip_current(self):
        if self.ctrl.running:
            self.ctrl.request_skip()
            self.append_concise_log(
                log_console.emit_event("DL", "SKIP", "-", "skip request"),
                is_status=False,
                is_error=False,
            )

    def add_concise_task_separator(self):
        self.console.add_task_separator()

    def on_download_finished(self, success_count, fail_count):
        # 상태 초기화와 분석 데이터 클리어는 Controller에 위임
        self.ctrl.on_download_finished(success_count, fail_count)

        self.update_ui_state()

        self.add_concise_task_separator()

        if success_count > 0:
            self.url_input.clear()
            if self.cfg.get("play_sound") and winsound:
                try:
                    winsound.MessageBeep(winsound.MB_ICONASTERISK)
                except Exception:
                    pass
            if self.cfg.get("auto_open_folder"):
                _open_windows_explorer(self.cfg["download_path"])


if __name__ == "__main__":
    # [히스토리] 미처리 예외 전체 트레이스백을 히스토리 파일로 유출 — 디버깅 1차 증거
    sys.excepthook = lambda t, v, tb: log_history.exception("미처리 예외", t, v, tb)
    if platform.system() == "Windows":
        import ctypes

        myappid = "chzzktube.subapp.v2"
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    if os.path.exists(ICON_PATH):
        app.setWindowIcon(QIcon(ICON_PATH))

    font_path = os.path.join(BASE_DIR, "CascadiaMono-VariableFont_wght.ttf")
    if os.path.exists(font_path):
        QFontDatabase.addApplicationFont(font_path)

    win = MainWindow()
    win.show()
    sys.exit(app.exec())

```

## File: media.py

```python
﻿### media.py - 순수 미디어 처리 헬퍼 (해상도 라벨 / 임시파일 정리 / FFmpeg 리먹싱 / 코덱 랭킹)
import glob
import os
import re
import subprocess

# 침묵 실패(리먹싱 등)의 증거 기록용 — log_history는 config leaf만 의존(비Qt·스레드 안전)
import log_history

### 사이트 축약기호 매핑 (extractor → 3~4글자 약자)
# 공식 브랜드 축약 우선, 없으면 도메인 앞글자 추출
# 로그 PLATFORM 컬럼에 표시됨 (예: [DEPS] YT, [DL] CHZ)
_EXTRACTOR_SHORT_STATIC = {
    # 영상 플랫폼 (공식/통용 축약)
    "youtube": "YT",
    "twitch": "TW",
    "instagram": "IG",
    "tiktok": "TIKT",
    "facebook": "FB",
    "twitter": "X",
    "x": "X",
    "naver": "NAV",
    "afreecaTV": "AFTV",
    "chzzk": "CHZ",
    "bilibili": "BILI",
    "dailymotion": "DM",
    "vimeo": "VM",
    "rumble": "RM",
    "odysee": "ODY",
    "peertube": "PT",
    # 음악/오디오
    "soundcloud": "SC",
    "spotify": "SP",
    "bandcamp": "BC",
    "mixcloud": "MC",
    # 커뮤니티/포럼 (한국)
    "fmkorea": "FM",
    "theqoo": "TQ",
    "clien": "CL",
    "dcinside": "DC",
    "mlbpark": "MP",
    # 기타
    "reddit": "RD",
    "tumblr": "TB",
    "pornhub": "PH",
    "xvideos": "XV",
    "youku": "YK",
    "iqiyi": "IQ",
}

def platform_short(extractor):
    """yt-dlp extractor 이름 → 3~4글자 축약기호.

    규칙:
    1. 정적 매핑 테이블 우선 (공식 브랜드 축약)
    2. 없으면 추출기명에서 특수문자 제거 후 앞 3~4글자 대문자
    3. 2글자 이하면 그대로 대문자
    """
    if not extractor:
        return "???"
    ext = extractor.strip().lower()
    if ext in _EXTRACTOR_SHORT_STATIC:
        return _EXTRACTOR_SHORT_STATIC[ext]
    # 동적 생성: 언더스코어/하이픈 제거 후 앞 4글자
    clean = re.sub(r"[_\-\s]+", "", ext)
    if len(clean) <= 4:
        return clean.upper()
    return clean[:4].upper()

### 코덱 품질 랭킹 데이터 테이블 (높을수록 우선순위 높음)
_VIDEO_CODEC_RANKS = [
    (("av01", "av1"), 3),
    (("vp09", "vp9"), 2),
    (("avc", "h264", "h.264"), 1),
]
_AUDIO_CODEC_RANKS = [
    (("opus",), 30),
    (("mp4a", "aac", "m4a"), 20),
    (("vorbis",), 10),
]

def get_video_codec_rank(vcodec):
    v = str(vcodec).lower()
    return next(
        (rank for keywords, rank in _VIDEO_CODEC_RANKS if any(k in v for k in keywords)),
        0,
    )

def get_audio_codec_rank(acodec, fid=""):
    a = str(acodec).lower()
    f = str(fid).lower()
    rank = next(
        (rank for keywords, rank in _AUDIO_CODEC_RANKS if any(k in a for k in keywords)),
        0,
    )
    return rank - 1 if "drc" in f else rank

### 코덱 전체명 → 짧은 표기 매핑 (로그/배지용)
_CODEC_SHORT_NAMES = [
    (("av01", "av1"), "AV1"),
    (("vp09", "vp9"), "VP9"),
    (("avc", "h264", "h.264"), "H264"),
    (("opus",), "OPUS"),
    (("mp4a.40.2",), "AAC-LC"),
    (("mp4a.40.5",), "HE-AAC v1"),
    (("mp4a.40.29",), "HE-AAC v2"),
    (("mp4a", "aac", "m4a"), "AAC"),
    (("vorbis",), "VORBIS"),
]

def codec_detail(codec):
    """코덱 상세 문자열('mp4a.40.2', 'avc1.64002A') — 없으면 빈 값."""
    c = str(codec or "").strip()
    if not c or c.lower() == "none":
        return ""
    if short_codec(c) == c.upper():
        return ""  # 'AAC' 등 총칭 — 상세 없음
    return c

def audio_flat(acodec):
    """짧은 이름과 상세를 괄호 없이 결합('AAC-LC mp4a.40.2') — 헤더 가지·배지용."""
    s = short_codec(acodec)
    d = codec_detail(acodec)
    return f"{s} {d}".strip()

def audio_spec(acodec):
    """오디오 코덱 표기의 단일 출처 — 짧은 이름과 상세(mp4a.40.2 등) 결합."""
    s = short_codec(acodec)
    d = codec_detail(acodec)
    return f"{s} ({d})" if d else s

def short_codec(codec):
    raw = str(codec or "")
    c = raw.strip().lower()
    if not c:
        return "?"
    exact = next((name for keys, name in _CODEC_SHORT_NAMES if c in keys), None)
    if exact:
        return exact
    return next(
        (name for keywords, name in _CODEC_SHORT_NAMES if any(k in c for k in keywords)),
        raw.upper(),
    )

def cli_format_desc(f):
    """yt-dlp -F 표(CLI) 컬럼을 한 줄로 재현 — 모든 소스의 포맷 표기 단일 출처."""
    f = f or {}
    vc = f.get("vcodec")
    ac = f.get("acodec")
    has_v = str(vc or "none") not in ("none", "")
    has_a = str(ac or "none") not in ("none", "")
    br = int(f.get("tbr") or f.get("abr") or 0)
    proto = str(f.get("protocol") or "").strip()
    rate_proto = " ".join(x for x in ((f"{br}k" if br else ""), proto) if x)

    parts = [str(f.get("ext") or "?").lower()]
    if has_v or int(f.get("height") or 0):
        res = f.get("resolution") or (
            f"{f.get('height')}p" if f.get("height") else "?"
        )
        fps_s = f" {int(f['fps'])}fps" if f.get("fps") else ""
        parts.append(f"{res}{fps_s}".strip())
        if rate_proto:
            parts.append(rate_proto)
        parts.append(short_codec(vc) if has_v else "?")
        if has_a:
            parts.append(audio_spec(ac))
    else:
        parts.append(audio_spec(ac) if has_a else "?")
    return " | ".join(p for p in parts if p)


# 드롭다운 라벨용 콘텐츠 타입 상수
_CONTENT_TYPE_LIVE = "LIVE"
_CONTENT_TYPE_VOD = "VOD"
_CONTENT_TYPE_SHORTS = "SHORTS"
_CONTENT_TYPE_CLIP = "CLIP"


def _format_bitrate(br):
    """비트레이트를 읽기 좋은 단위로 변환 — 8.4M, 119k 등."""
    br = int(br or 0)
    if br >= 1000:
        val = br / 1000
        # 소수점 첫째 자리까지 표기 (8.4M, 1.2M 등)
        return f"{val:.1f}M" if val != int(val) else f"{int(val)}M"
    return f"{br}k" if br else "?k"


def _format_protocol(f):
    """프로토콜 정보를 'PROTOCOL : TYPE' 형식으로 포맷."""
    proto = str(f.get("protocol") or "").strip().upper()
    ext = str(f.get("ext") or "").strip().upper()
    note = str(f.get("format_note") or "").strip().upper()
    
    # format_note에서 DASH, HLS 등 키워드 추출
    dash = "DASH" if "DASH" in note else ""
    hls = "HLS" if "HLS" in note else ""
    
    parts = []
    if proto:
        parts.append(proto)
    # ext가 protocol과 다르면 추가 (예: HTTPS + M3U8)
    if ext and ext != proto and ext != "?":
        if dash and dash not in parts:
            parts.append(dash)
        elif hls and hls not in parts:
            parts.append(hls)
        elif ext not in parts:
            parts.append(ext)
    elif dash:
        parts.append(dash)
    elif hls:
        parts.append(hls)
    
    return " : ".join(p for p in parts if p) if parts else "?"


def format_dropdown_label(f, content_type=""):
    """Fixed-Column ASCII Pipe Style 드롭다운 라벨 — 모든 소스의 포맷 표기 단일 출처.
    
    포맷: [1080p60]  8.4M  │  HTTPS : DASH  │  LIVE
           [ AUDIO ]  119k  │  HTTPS : DASH  │  VOD
    
    콘텐츠 타입(content_type): LIVE, VOD, SHORTS, CLIP (또는 빈 문자열)
    f: yt-dlp format dict
    """
    f = f or {}
    vc = f.get("vcodec")
    ac = f.get("acodec")
    has_v = str(vc or "none").strip() not in ("none", "", "None")
    has_a = str(ac or "none").strip() not in ("none", "", "None")
    br = int(f.get("tbr") or f.get("abr") or 0)
    height = int(f.get("height") or 0)
    fps = int(f.get("fps") or 0)
    
    # Column 1: 해상도/오디오 표시
    if has_v or height:
        res_str = f"{height}p" if height else "?"
        if fps:
            res_str += str(fps)
        col1 = f"[{res_str}]"
    elif has_a:
        col1 = "[ AUDIO ]"
    else:
        col1 = "[ ? ]"
    
    # Column 2: 비트레이트
    col2 = _format_bitrate(br)
    
    # Column 3: 프로토콜 정보
    col3 = _format_protocol(f)
    
    # Column 4: 콘텐츠 타입 (선택)
    col4 = content_type.upper() if content_type else ""
    
    # 고정 칼럼 조립 (Column 1은 9칸, Column 2은 6칸으로 정렬)
    label = f"{col1:<9} {col2:>5}  │  {col3}"
    if col4:
        label += f"  │  {col4}"
    return label

def format_bytes(size):
    """바이트(Bytes) 수치를 KB, MB, GB 단위로 자동 환산"""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} PB"

def cleanup_temp_files(filepath):
    """작업 중단 시 .part, .ytdl, .f*** 스트림 조각 및 임시 썸네일 일괄 삭제.

    [cleanup.py 통합] .f251 등 yt-dlp 스트림 조각(f코드)과 mp4/webm 등
    출력 확장자를 정규식으로 먼저 벗겨 base 경로를 산정한다 — splitext만
    쓰는 구버전은 '제목.f251.mp4' 형태의 조각을 잡지 못했다.
    """
    if not filepath:
        return
    try:
        dir_name = os.path.dirname(filepath)
        file_name = os.path.basename(filepath)

        # f코드 검출 및 제거 (예: .f251, .f137, .f401)
        file_name_clean = re.sub(r"\.f\d+.*$", "", file_name)

        # 일반 확장자 제거 (예: .part, .ytdl, .webm, .mp4)
        file_name_clean = re.sub(
            r"\.(part|ytdl|temp|mp4|webm|mkv|3gp|flv|ts)$",
            "",
            file_name_clean,
            flags=re.IGNORECASE,
        )

        base_path = os.path.join(dir_name, file_name_clean)
        search_pattern = base_path + "*"

        for target in glob.glob(search_pattern):
            if target.endswith(
                (
                    ".part",
                    ".ytdl",
                    ".temp",
                    "_temp.ts",
                    "_temp_thumb.jpg",
                    ".webp",
                    ".jpg",
                    ".png",
                )
            ):
                if os.path.exists(target):
                    try:
                        os.remove(target)
                    except Exception:
                        pass
    except Exception:
        pass

def remux_live_to_container(ts_path, container_setting="mp4"):
    if not ts_path or not os.path.exists(ts_path):
        return None
    target_ext = container_setting.lower()
    if target_ext not in ["mp4", "mkv"]:
        target_ext = "mp4"

    out_path = os.path.splitext(ts_path)[0] + f".{target_ext}"
    cmd = ["ffmpeg", "-y", "-i", ts_path, "-c", "copy", out_path]

    try:
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
            os.remove(ts_path)
            return out_path
    except Exception as e:
        # [증거 남김] windowed 빌드에선 print가 소멸하므로 히스토리에 기록 —
        # 임시 ts는 실패 시 보존되므로 사용자가 재시도할 수 있다.
        import raw_log
        from log_event import LogEvent
        raw_log.raw(
            "media",
            LogEvent(
                stage="MEDIA", status="FAIL", platform="-",
                msg=f"라이브 리먹싱 실패 — 원본 ts 보존됨 ({os.path.basename(ts_path)}): "
                    f"{type(e).__name__}: {e}",
                is_error=True,
            ),
            to_tui=False,
        )

    return ts_path

```

## File: node_provider.py

```python
"""Node.js 런타임 수급 전용 모듈 (SRP: Node.js 런타임 관리만 담당).

- node_exe / node_major_version / npm_exe : node 실행 파일 탐색
- node_ok / ensure_node_runtime : bgutil 요구 버전 충족 검증·자동 수급
- bundled_npm_ok : 포터블 npm 무결성 검사

서버 기동/빌드/소스 수급은 pot_server.py가 담당.
"""
import os
import re
import sys
import json
import shutil
import zipfile
import tarfile
import platform
import subprocess
import urllib.request

import config
from log_console import emit_component


# ── 상수 (node_provider 전용) ──────────────────────────────────────
NODE_MIN_MAJOR = 22  # bgutil 서버의 Node 요구사항 (require(esm) 기본 지원선)
_NODE_FALLBACK_VER = "v22.23.2"  # nodejs.org index 조회 실패 시 폴백 (v22 LTS)
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_node_ver_cache: dict = {}


# ── 공유 헬퍼 ──────────────────────────────────────────────────────
def get_writable_base():
    """사용자 환경에서 쓰기 권한이 100% 보장되는 로컬 앱 데이터 디렉터리 반환."""
    path = config.writable_base()
    os.makedirs(path, exist_ok=True)
    return path


def _is_portable():
    """PyInstaller(frozen) 패키징 여부."""
    return bool(getattr(sys, "frozen", False))


def _bundle_root():
    """포터블에서 번들 데이터가 풀린 디렉터리 (onedir) _MEIPASS."""
    if _is_portable():
        return getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(sys.executable)))
    return None


# ── Node.js 버전 탐색 ───────────────────────────────────────────────
def node_major_version(node_path, timeout=10):
    """node --version 출력에서 major 버전 추출 (판별 실패 시 None, 결과 캐시)."""
    if not node_path:
        return None
    if node_path in _node_ver_cache:
        return _node_ver_cache[node_path]
    major = None
    try:
        kwargs = {}
        if platform.system() == "Windows":
            kwargs["creationflags"] = _NO_WINDOW
        out = subprocess.run(
            [node_path, "--version"],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=timeout, **kwargs,
        )
        m = re.match(r"v?(\d+)", (out.stdout or "").strip())
        if m:
            major = int(m.group(1))
    except Exception:
        major = None
    _node_ver_cache[node_path] = major
    return major


def latest_lts_node_url(major=NODE_MIN_MAJOR):
    """nodejs.org dist index에서 지정 major의 최신 플랫뷸 URL (조회 실패 시 폴백)."""
    try:
        with urllib.request.urlopen(
            "https://nodejs.org/dist/index.json", timeout=15
        ) as resp:
            entries = json.load(resp)
        ver = next(
            (
                e.get("version")
                for e in entries
                if str(e.get("version", "")).startswith(f"v{major}.")
            ),
            None,
        )
        if ver:
            return _platform_node_url(ver)
    except Exception:
        pass
    return _platform_node_url(_NODE_FALLBACK_VER)


def _platform_node_url(ver):
    """플랫폼별 Node.js 배포 URL 생성 (Windows: zip, macOS: tar.gz)."""
    system = platform.system()
    if system == "Windows":
        return f"https://nodejs.org/dist/{ver}/node-{ver}-win-x64.zip"
    if system == "Darwin":
        arch = "arm64" if platform.machine() == "arm64" else "x64"
        return f"https://nodejs.org/dist/{ver}/node-{ver}-darwin-{arch}.tar.gz"
    arch = "arm64" if platform.machine() == "arm64" else "x64"
    return f"https://nodejs.org/dist/{ver}/node-{ver}-linux-{arch}.tar.gz"


# ── Node.js 실행 파일 탐색 ─────────────────────────────────────────
def npm_exe():
    """현재 사용 중인 node 런타임과 동일한 디렉터리의 npm 스크립트 경로."""
    node = node_exe()
    if not node:
        return None
    base = os.path.dirname(node)
    name = "npm.cmd" if platform.system() == "Windows" else "npm"
    cand = os.path.join(base, name)
    return cand if os.path.isfile(cand) else None


def node_ok():
    """현재 탐색된 node가 bgutil 요구 버전(Node >= 22)을 충족하는지."""
    return (node_major_version(node_exe()) or 0) >= NODE_MIN_MAJOR


def node_exe():
    """PO Token 서버 기동용 node 탐색 — bgutil 요구(Node >= 22) 충족 후보만 유효.

    후보 순서: 시스템 PATH → 캐시된 포터블 node → frozen 번들.
    요구 버전을 충족하는 후보가 없으면 None → ensure_node_runtime 재구성 트리거.
    포터블 빌드 첫 실행시 다른 DEPS와 함께 다운로드됨.
    """
    _exe_suffix = ".exe" if os.name == "nt" else ""

    # 1. 시스템 Node.js 확인 (번들이 아닌 외부 참조)
    system_node = shutil.which("node") or shutil.which("node.exe")
    if system_node:
        maj = node_major_version(system_node)
        if maj is not None and maj >= NODE_MIN_MAJOR:
            return system_node

    cands = []
    local_node_dir = os.path.join(get_writable_base(), "node")
    if os.path.isdir(local_node_dir):
        exe_name = "node.exe" if platform.system() == "Windows" else "node"
        for root, dirs, files in os.walk(local_node_dir):
            if exe_name in files:
                cands.append(os.path.join(root, exe_name))
    # [macOS] 포터블 node 실행 권한 보장 (tar.gz 추출 시 실행 비트 누락 방지)
    if platform.system() != "Windows":
        for c in cands:
            try:
                mode = os.stat(c).st_mode
                if not (mode & 0o111):
                    os.chmod(c, mode | 0o755)
            except Exception:
                pass

    if _is_portable():
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        cands.extend(
            c for c in [
                os.path.join(exe_dir, f"node{_exe_suffix}"),
                os.path.join(exe_dir, "_internal", f"node{_exe_suffix}"),
                os.path.join(exe_dir, "_internal", "node", f"node{_exe_suffix}"),
            ]
            if os.path.isfile(c)
        )
        _me = getattr(sys, "_MEIPASS", None)
        if _me and os.path.isfile(os.path.join(_me, f"node{_exe_suffix}")):
            cands.insert(0, os.path.join(_me, f"node{_exe_suffix}"))

    which_node = shutil.which("node")
    if which_node:
        cands.append(which_node)

    majors = [(c, node_major_version(c)) for c in cands]
    ok = [c for c, m in majors if m is not None and m >= NODE_MIN_MAJOR]
    if ok:
        return ok[0]
    if majors and all(m is None for _, m in majors):
        return majors[0][0]  # 버전 판별 전면 실패 폴백 — 무한 재설치 방지
    return None


def bundled_npm_ok(node_path):
    """번들 Node dir의 npm 무결성 — validate-engines가 require하는 package.json.

    [크로스 플랫폼 레이아웃] 검사 경로는 플랫폼별 릴리스 구조를 모두 커버:
    - Windows zip :  <base>/node_modules/npm/package.json  (node.exe 옆)
    - Unix tarball : <base>/../lib/node_modules/npm/package.json  (macOS·Linux)
    """
    if not node_path:
        return False
    base = os.path.dirname(node_path)
    candidates = (
        os.path.join(base, "node_modules", "npm", "package.json"),
        os.path.join(base, "..", "lib", "node_modules", "npm", "package.json"),
    )
    return any(os.path.isfile(os.path.normpath(p)) for p in candidates)


def ensure_node_runtime(log_func):
    """bgutil 서버 요구(Node >= 22) 충족을 위한 Node.js 런타임 자동 수급/재구성.

    [수정 이력]
    - 구버전은 v20.18.0을 받아 bgutil의 require(esm) 요구를 충족하지
      못해 서버가 ERR_REQUIRE_ESM으로 크래시했다 (PO Token 기동 실패 근본 원인).
    - 자가 치유: node.exe는 살아있어도 번들 npm이 깨진 경우(부분 추출/AV 격리)
      재설치로 수리 — bundled_npm_ok 참조.
    - 번들이 아닌 외부 라이브러리 참조 전환:
      시스템 Node.js 22+ 우선 사용 → 없으면 로컬 포터블 → 마지막으로 다운로드.
      포터블 빌드 첫 실행시 다른 DEPS와 함께 다운로드됨.
    """
    from pot_server import _download_with_progress, _prune_outdated_node_dirs

    # 1. 시스템 Node.js 확인 (번들이 아닌 외부 참조)
    system_node = shutil.which("node")
    if system_node:
        system_major = node_major_version(system_node)
        if system_major is not None and system_major >= NODE_MIN_MAJOR:
            if shutil.which("npm"):
                log_func(f"using system Node.js v{system_major} ({system_node})")
                return True

    # 2. 로컬 포터블 Node.js 확인
    cur = node_exe()
    cur_major = node_major_version(cur) if cur else None
    if cur_major is not None and cur_major >= NODE_MIN_MAJOR and (
        bundled_npm_ok(cur) or shutil.which("npm")
    ):
        return True
    if cur_major is not None and cur_major >= NODE_MIN_MAJOR and not bundled_npm_ok(cur):
        log_func("[~] node ok but bundled npm broken — reinstalling runtime.")
    elif cur_major is not None:
        log_func(
            f"Node.js v{cur_major} is below bgutil requirement "
            f"(Node >= {NODE_MIN_MAJOR}) — reconfiguring to latest runtime."
        )
    else:
        log_func("node.js >= 22 missing — downloading portable runtime")

    node_dir = os.path.join(get_writable_base(), "node")
    os.makedirs(node_dir, exist_ok=True)

    node_url = latest_lts_node_url()
    is_tarball = node_url.endswith(".tar.gz")
    dest_name = "node_portable.tar.gz" if is_tarball else "node_portable.zip"
    archive_dest = os.path.join(get_writable_base(), dest_name)

    try:
        _download_with_progress(node_url, archive_dest, log_func, "node.js runtime downloading")
        log_func("node.js runtime extracting...")
        if is_tarball:
            if os.path.exists(node_dir):
                try:
                    for root, dirs, files in os.walk(node_dir):
                        for d in dirs:
                            try:
                                os.chmod(os.path.join(root, d), 0o755)
                            except (PermissionError, OSError):
                                pass
                        for f in files:
                            try:
                                os.chmod(os.path.join(root, f), 0o755)
                            except (PermissionError, OSError):
                                pass
                except Exception:
                    pass
                shutil.rmtree(node_dir, ignore_errors=True)
            os.makedirs(node_dir, exist_ok=True)
            try:
                result = subprocess.run(
                    ["tar", "-xzf", archive_dest, "-C", node_dir],
                    capture_output=True, text=True, timeout=120,
                )
                if result.returncode != 0:
                    raise RuntimeError(f"tar failed: {result.stderr}")
            except Exception:
                with tarfile.open(archive_dest, "r:gz") as tf:
                    if sys.version_info >= (3, 12):
                        tf.extractall(node_dir, filter="data")
                    else:
                        for member in tf.getmembers():
                            try:
                                tf.extract(member, node_dir)
                            except (PermissionError, OSError):
                                pass
        else:
            if os.path.exists(node_dir):
                try:
                    shutil.rmtree(node_dir, ignore_errors=True)
                except Exception:
                    pass
            os.makedirs(node_dir, exist_ok=True)
            with zipfile.ZipFile(archive_dest, "r") as z:
                z.extractall(node_dir)
        _node_ver_cache.clear()
        new_node = node_exe()
        new_major = node_major_version(new_node) if new_node else None
        if new_major is not None and new_major >= NODE_MIN_MAJOR and bundled_npm_ok(new_node):
            log_func(f"portable Node.js v{new_major} ready.")
            _prune_outdated_node_dirs(node_dir)
            return True
        log_func(
            f"Node.js still below requirement (>= {NODE_MIN_MAJOR}) after configure",
            False, True,
        )
        return False
    except Exception as e:
        log_func(f"Node.js auto-setup failed: {e}", False, True)
        return False
```

## File: playlist.py

```python
##### playlist.py - 유튜브 채널/재생목록 URL 정규화
"""채널 URL을 평탄화(expand_targets)에 적합한 형태로 정규화한다."""
import re


def normalize_youtube_channel_url(url):
    """채널 URL 정규화.

    - `/@handle`      → `/@handle/videos`  (채널 탭 평탄화 기준 탭으로 이동)
    - `/c/...` `/channel/...` → 상위 목록 접미 제거 후 `/videos` 부착
    - 일반 watch/playlist URL은 그대로 반환
    """
    if not url:
        return url
    u = url.strip()
    u_lower = u.lower()
    if "youtube.com" not in u_lower and "youtu.be" not in u_lower:
        return u

    # 채널 계열만 대상 — 일반 동영상/재생목록은 그대로
    if re.search(r"playlist\?list=", u_lower):
        return u
    if "/watch" in u_lower or "/shorts/" in u_lower or "youtu.be/" in u_lower:
        return u
    if "/live/" in u_lower:
        return u

    # 이미 /videos|streams|playlists|shorts|featured|about 탭이면 그대로
    if re.search(r"/(videos|streams|playlists|shorts|featured|about)/?$", u_lower):
        return u

    # /@handle 또는 /channel/UC... — 뒤의 탭 잔여물 제거 후 /videos
    m = re.match(r"(https?://(?:www\.)?youtube\.com/(?:@[^/?#]+|channel/[^/?#]+))", u)
    if m:
        return m.group(1).rstrip("/") + "/videos"

    # 기타 (music.youtube 등) — 그대로
    return u
```

## File: po_client.py

```python
### po_client.py - PO Token 서버 HTTP 클라이언트 (L0 leaf)
"""bgutil PO Token 서버와의 순수 HTTP 통신 계층.

[계층 규약] 서버 프로세스 수급·빌드·스폰(lifecycle)은 pot_server(L1)와
그 수명주기 관리자(POTManager)가 담당하고, 본 모듈은 그 서버에 대한
**순수 HTTP 클라이언트**만 제공한다 — 상위 계층 역참조(lazy import) 없이
표준 라이브러리만으로 완결된다.
- client_opts(L0) / updater(L0) 가 pot_provider(L1)를 역참조하던 계층 역전 해소:
  이제 옵션 빌더·버전 체커는 본 leaf만 본다.
- 의존: 표준 라이브러리만 — Qt/워커 무의존, 어디서 import해도 안전.
"""
import json
import re
import socket
import urllib.error
import urllib.request

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 4416


def server_ping(host=DEFAULT_HOST, port=DEFAULT_PORT, timeout=1):
    """PO token server alive 확인 (L0 순수 HTTP 핑). 성공 시 True.

    [계약] L0 leaf는 표준 라이브러리만 본다 — 상위 계층(pot_server)의 락
    파일을 들여다보던 PID 역참조는 폐기했다. TCP 연결 성공 + HTTP 200은
    Node.js 이벤트 루프가 실제로 I/O를 처리 중이라는 증거이므로 프로토콜
    검증만으로 생존 판정이 충분하다. 좀비 락 회수는 pot_server가 서버
    기동 시 본인의 책임 영역에서 처리한다.
    """
    try:
        url = f"http://{host}:{port}/ping"
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def probe_server(host=DEFAULT_HOST, port=DEFAULT_PORT, timeout=1.5):
    """서버 상태 모니터링 (HTTP /ping 응답 기준)"""
    url = f"http://{host}:{port}/ping"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if 200 <= resp.status < 300:
                return "ok", ""
            return "conflict", f"HTTP {resp.status}"
    except urllib.error.HTTPError as e:
        return "conflict", f"HTTP {e.code}"
    except urllib.error.URLError as e:
        if isinstance(getattr(e, "reason", None), ConnectionRefusedError):
            return "down", ""
    except Exception:
        pass

    # [폴백] HTTPError/URLError 외 (예: OS 레벨 연결 거부 랩핑) 소켓 직접 확인
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return "conflict", "ping no response"
    except OSError:
        return "down", ""


def fetch_po_token(video_id, host=DEFAULT_HOST, port=DEFAULT_PORT, timeout=5):
    """bgutil 독립 서버에서 PO 토큰 직접 패칭 (플러그인 우회).

    POST /get_pot {"content_binding": video_id} → {"poToken": "..."}
    서버 미기동/오류 시 None 반환 — 호출부는 PO 없이 진행.
    """
    url = f"http://{host}:{port}/get_pot"
    try:
        body = json.dumps({"content_binding": video_id}).encode("utf-8")
        req = urllib.request.Request(
            url, data=body, method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        token = data.get("poToken") or ""
        if token:
            return token
    except Exception:
        pass
    return None


def extract_video_id(url):
    """YouTube URL에서 11자리 video ID 추출 (실패 시 None)."""
    m = re.search(
        r"(?:v=|/shorts/|/embed/|youtu\.be/)([a-zA-Z0-9_-]{11})", str(url or "")
    )
    return m.group(1) if m else None
```

## File: pot_manager.py

```python
# POTManager
from PySide6.QtCore import QObject, QThread, QTimer, Signal
import threading
import subprocess
import os
from log_event import LogEvent
import raw_log


class _POTWorker(QThread):
    # [v3.3.0] 로그는 raw 버스 단일 경유 — log_full 시그널 폐기.
    finished_signal = Signal(bool, str)
    
    def __init__(self, parent=None, mode="prewarm"):
        super().__init__()
        self.mode = mode
        self._abort = False
        self._child_procs = []
        self._server_proc = None
        self.outcome = (False, "")
    
    def request_interruption(self):
        self._abort = True
        for proc in self._child_procs:
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
    
    def run(self):
        try:
            self._run()
        except Exception as e:
            self.outcome = (False, f"crash: {e}")
        finally:
            self._cleanup()
            self.finished_signal.emit(self.outcome[0], self.outcome[1])
    
    def _cleanup(self):
        for proc in self._child_procs:
            try: proc.kill()
            except: pass
        self._child_procs.clear()
        if self._server_proc:
            try:
                from pot_server import _kill
                _kill(self._server_proc)
            except: pass
            self._server_proc = None
    
    def _note(self, msg, is_status=False, is_error=False):
        """raw 버스 단일 경유 — 라벨링은 근원에서 LogEvent로 동봉.

        [채널 분기 — 발행자 결정]
        - prewarm 모드: to_tui=False → F12+history 전용 (TUI 오염 방지)
        - gate 모드: to_tui=True → TUI + F12 + history 전부 기록
        """
        if self.mode == "prewarm":
            raw_log.raw("pot", str(msg), is_status=is_status, is_error=is_error)
            return
        stage = "SYS" if is_error else "POT"
        status = "FAIL" if is_error else ("RUN" if is_status else "OK")
        event = LogEvent(stage=stage, status=status, platform="pot",
                         spec="-", msg=str(msg)[:120],
                         is_status=is_status, is_error=is_error)
        raw_log.raw("pot", event, to_tui=True)

    def _dbg(self, msg):
        """raw 버스 단일 경유 — 직접 log_full.emit 금지 (F12 이중 적재 방지).

        [채널 분기 — 발행자 결정]
        - prewarm 모드: to_tui=False → F12+history 전용
        - gate 모드: to_tui=True → TUI + F12 + history 전부 기록
        """
        if self.mode == "prewarm":
            raw_log.raw("pot-DEBUG", str(msg))
        else:
            event = LogEvent(stage="POT", status="RUN", platform="pot",
                             spec="-", msg=str(msg)[:120])
            raw_log.raw("pot", event, to_tui=True)
    
    def _run(self):
        from pot_server import probe_server, latest_server_ver, server_installed_ver
        from pot_server import built_server_js, DEFAULT_HOST, DEFAULT_PORT
        self._dbg(f"POTWorker starting (mode={self.mode})")
        if self.mode == "gate":
            try:
                import components
                self._dbg("entering ffmpeg ensure phase")
                ff_err = components.ensure_ffmpeg(self._note)
                if ff_err:
                    self._note(f"ffmpeg failed: {ff_err}", False, True)
                else:
                    self._dbg("ffmpeg fetch done")
            except Exception as ff_ex:
                self._note(f"ffmpeg ex: {ff_ex}", False, True)
        else:
            self._dbg("ffmpeg ensure skipped (prewarm)")
        try:
            from pot_server import clean_stale_plugin
            if clean_stale_plugin():
                self._dbg("stale removed")
        except Exception as cp_ex:
            self._dbg(f"cleanup failed: {cp_ex}")
        self._note("probing server...", True)
        state, detail = probe_server()
        self._dbg(f"probe: state={state!r}")
        if state == "ok":
            self.outcome = (True, f"pot server bound ({DEFAULT_HOST}:{DEFAULT_PORT})")
            return
        remote = latest_server_ver()
        local = server_installed_ver()
        if self.mode == "prewarm":
            self._dbg("prewarm mode — staging to disk, no spawn")
            from pot_server import acquire_prewarm_lock, release_prewarm_lock
            fd = acquire_prewarm_lock(timeout=0, log_func=self._dbg)
            if fd is None:
                self.outcome = (False, "prewarm skipped — build busy")
                return
            try:
                self._note("pot prewarm staging...", True)
                from pot_server import ensure_node_server, server_home, _SERVER_FALLBACK_VER
                ver = remote or local or _SERVER_FALLBACK_VER
                have_build = built_server_js() is not None
                _, err = ensure_node_server(self._note, self._dbg, ver, rebuild=have_build)
                if err is None and built_server_js():
                    self.outcome = (True, "prewarm staged")
                else:
                    self.outcome = (False, f"prewarm fail: {err}")
            finally:
                release_prewarm_lock(fd, log_func=self._dbg)
            return
        if built_server_js():
            self._note("pot server starting...", True)
            from pot_server import _spawn_existing
            proc = _spawn_existing(self._dbg)
            if proc is not None:
                self._server_proc = proc
                self.outcome = (True, f"pot server bound ({DEFAULT_HOST}:{DEFAULT_PORT})")
                return
        self.outcome = (False, "bind fail — age-only")
    
    def terminate(self):
        self.request_interruption()
        super().terminate()

class POTManager(QObject):
    # [v3.3.0] 로그는 raw 버스 단일 경유 — log_full 릴레이 시그널 폐기.
    pot_status_changed = Signal(str)
    pot_finished = Signal(bool, str)

    def __init__(self):
        super().__init__()
        self._worker = None
        self._mode = "idle"
        self._pending_gate = False
        self._lock = threading.Lock()

    def ensure_ready(self, mode="gate"):
        if mode not in {"prewarm", "gate"}:
            raise ValueError(f"unknown POT mode: {mode}")
        with self._lock:
            worker = self._worker
            if worker is not None and worker.isRunning():
                if mode == "gate" and self._mode == "prewarm":
                    self._pending_gate = True
                return
            self._start_worker_locked(mode)

    def _start_worker_locked(self, mode: str) -> None:
        self._mode = mode
        worker = _POTWorker(mode=mode)
        self._worker = worker
        worker.finished_signal.connect(self._on_worker_finished)
        worker.start()
        self.pot_status_changed.emit("starting" if mode == "gate" else "staging")

    def _on_worker_finished(self, ok: bool, msg: str):
        # Qt may deliver this callback after cancel(); ignore stale workers.
        with self._lock:
            worker = self._worker
            mode = self._mode
            if worker is None or worker is not self._worker:
                return
            if mode == "prewarm":
                if ok and self._pending_gate:
                    self._pending_gate = False
                    self._worker = None
                    self._mode = "staged"
                    QTimer.singleShot(0, self._start_pending_gate)
                    return
                self._worker = None
                self._mode = "staged" if ok else "failed"
            elif mode == "gate":
                self._worker = None
                self._mode = "ready" if ok else "failed"
            else:
                return

        self.pot_status_changed.emit("staged" if ok else "failed")
        # [READY 게이트 계약] pot_finished의 msg는 상태 토큰("staged"/"ready"/"failed")으로만
        # 발행한다 — StartupCoordinator.report_pot이 정확 일치로 READY를 판정한다.
        # 사람이 읽는 상세 메시지("prewarm staged", "pot server bound ...")는
        # 워커가 이미 로그 버스로 남겼으므로 여기서 중복 전달하지 않는다.
        self.pot_finished.emit(ok, self._mode if ok else "failed")

    def _start_pending_gate(self):
        """완료된 prewarm 워커의 Signal 처리 후 gate 워커를 시작한다."""
        with self._lock:
            if self._mode != "staged" or self._worker is not None:
                return
            self._start_worker_locked("gate")

    @property
    def mode(self):
        return self._mode

    def is_ready(self):
        with self._lock:
            return self._mode == "ready" and self._worker is None

    def use_existing(self):
        """외부/기존 POT 서버가 이미 /ping에 응답 중일 때 ready 상태로 승격.

        이 경로로는 gate 워커가 스폰되지 않으므로 pot_finished가 발행되지
        않는다 — _pending_download가 영구 큐잉되는 것을 막기 위해 즉시 ready로
        표시해야 한다 (Main._wait_pot_if_needed → toggle_download가 확인).
        """
        with self._lock:
            self._worker = None
            self._mode = "ready"

    def is_busy(self):
        return self._worker is not None and self._worker.isRunning()

    def cancel(self):
        with self._lock:
            worker = self._worker
            self._worker = None
            self._mode = "idle"
        if worker and worker.isRunning():
            worker.request_interruption()
            if not worker.wait(2000):
                worker.terminate()
                worker.wait(1000)

POTProviderWorker = _POTWorker
```

## File: pot_provider.py

```python
"""pot_provider — PO Token 3개 모듈 재수출 facade.

[구조]
- node_provider.py    : Node.js 런타임 수급 (node_exe, node_ok, ensure_node_runtime 등)
- pot_server.py       : bgutil 서버 빌드/기동 (ensure_node_server, _spawn_existing 등)
- po_client.py        : PO Token HTTP 클라이언트 (L0 leaf, 계층 역전 방지)
- pot_provider.py     : 위 3개 모듈을 재수출(re-export)

[호환성] 기존 `import pot_provider` 코드는 변경 없이 동작.
- update_worker.py: pot_provider.ensure_node_runtime
- updater.py      : pot_provider.node_exe / node_major_version / npm_exe

[제거 이력] POTProviderWorker(QThread)는 POTManager._POTWorker와 중복 선언된
좀비 인터페이스였다 — 런타임 사용 0건(tests/문서 전용), 진실의 근원은
POTManager 단독이다. 서버 수명주기 계약은 POTManager를 본다.
"""

# ── 재수출 (내부 호출 + 외부 역참조 모두 1경로) ──────────────────────────
from po_client import (  # L0 leaf — 계층 역전 방지
    DEFAULT_HOST,
    DEFAULT_PORT,
    extract_video_id,
    fetch_po_token,
    probe_server,
    server_ping,
)
from node_provider import (  # SRP: Node.js 런타임만 담당
    NODE_MIN_MAJOR,
    _NO_WINDOW,
    _node_ver_cache,
    get_writable_base,
    _is_portable,
    _bundle_root,
    node_major_version,
    latest_lts_node_url,
    _platform_node_url,
    npm_exe,
    node_ok,
    node_exe,
    bundled_npm_ok,
    ensure_node_runtime,
)
from pot_server import (  # SRP: bgutil 서버 빌드/기동만 담당
    _SERVER_FALLBACK_VER,
    _TAG_ZIP,
    server_home,
    assign_to_job_object,
    read_server_log_tail,
    latest_server_ver,
    server_installed_ver,
    clean_stale_plugin,
    _wait_port,
    _kill,
    built_server_js,
    pot_readiness,
    acquire_prewarm_lock,
    release_prewarm_lock,
    _spawn_existing,
    download_and_install_source,
    _run_and_stream_log,
    ensure_node_server,
    kill_process_on_port,
)

__all__ = [
    "DEFAULT_HOST", "DEFAULT_PORT", "extract_video_id",
    "fetch_po_token", "probe_server", "server_ping",
    "NODE_MIN_MAJOR", "get_writable_base", "_is_portable", "_bundle_root",
    "node_major_version", "latest_lts_node_url", "_platform_node_url",
    "npm_exe", "node_ok", "node_exe", "bundled_npm_ok", "ensure_node_runtime",
    "server_home", "assign_to_job_object", "read_server_log_tail",
    "latest_server_ver", "server_installed_ver", "clean_stale_plugin",
    "built_server_js", "pot_readiness", "acquire_prewarm_lock",
    "release_prewarm_lock", "_spawn_existing", "download_and_install_source",
    "ensure_node_server", "kill_process_on_port",
]

```

## File: pot_server.py

```python
"""bgutil PO Token 서버 수명 주기 전용 모듈 (SRP: 서버 수급/빌드/기동만 담당).

- latest_server_ver / server_installed_ver : 버전 확인 (GitHub API + 로컬 마커)
- download_and_install_source : 지정 버전 소스 패치
- ensure_node_server : npm ci + tsc 빌드 파이프라인
- _spawn_node_server / _spawn_existing : Node.js HTTP 서버 기동
- _wait_port / _kill : 프로세스 생명주기 헬퍼
- _download_with_progress : 친절한 진행률 다운로드

Node.js 런타임 수급은 node_provider.py가 담당. 공유 헬퍼(get_writable_base,
server_home, assign_to_job_object 등)는 여기 정의 후 node_provider/pot_provider
가서 re-import.
"""
import os
import sys
import time
import json
import shutil
import zipfile
import tarfile
import platform
import subprocess
import urllib.request
import tempfile

import config
from log_console import emit_component
from po_client import DEFAULT_HOST, DEFAULT_PORT, probe_server
from node_provider import NODE_MIN_MAJOR, _NO_WINDOW


_TAG_ZIP = (
    "https://github.com/Brainicism/bgutil-ytdlp-pot-provider/archive/refs/tags/{ver}.zip"
)
_SERVER_FALLBACK_VER = "1.3.2"


# ── 공유 헬퍼 (node_provider에서도 사용) ──────────────────────────────
def get_writable_base():
    """사용자 환경에서 쓰기 권한이 100% 보장되는 로컬 앱 데이터 디렉터리 반환.

    경로 계산은 config.writable_base(단일 출처)에 위임하고 생성만 담당.
    ※ node_provider.get_writable_base와 동일 구현 — 중복을 허용하되
    pot_server가 독립 import 체인을 유지하도록 여기에 정의.
    """
    path = config.writable_base()
    os.makedirs(path, exist_ok=True)
    return path


def _is_portable():
    """PyInstaller(frozen) 패키징 여부."""
    return bool(getattr(sys, "frozen", False))


def _bundle_root():
    """포터블에서 번들 데이터가 풀린 디렉터리 (onedir) _MEIPASS."""
    if _is_portable():
        return getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(sys.executable)))
    return None


def server_home():
    """PO Token 서버 소스/빌드를 둘 위치."""
    writable_path = os.path.join(get_writable_base(), "bgutil-ytdlp-pot-provider")
    if os.path.isdir(writable_path):
        return writable_path

    if _is_portable():
        bundle_path = os.path.join(_bundle_root() or "", "bgutil-ytdlp-pot-provider")
        if os.path.isdir(bundle_path):
            return bundle_path

    os.makedirs(writable_path, exist_ok=True)
    return writable_path


def assign_to_job_object(proc):
    """Windows: 프로세스를 Job Object에 할당해 부모 종료 시 자동 정리."""
    if platform.system() != "Windows":
        return
    try:
        import ctypes
        from ctypes import wintypes

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("ReadOperationCount", ctypes.c_uint64),
                ("WriteOperationCount", ctypes.c_uint64),
                ("OtherOperationCount", ctypes.c_uint64),
                ("ReadTransferCount", ctypes.c_uint64),
                ("WriteTransferCount", ctypes.c_uint64),
                ("OtherTransferCount", ctypes.c_uint64),
            ]

        class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                ("IoInfo", IO_COUNTERS),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        kernel32 = ctypes.windll.kernel32
        h_job = kernel32.CreateJobObjectW(None, None)
        if not h_job:
            return

        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE

        kernel32.SetInformationJobObject(
            h_job, 9, ctypes.byref(info), ctypes.sizeof(info)
        )

        if hasattr(proc, "_handle") and proc._handle:
            kernel32.AssignProcessToJobObject(h_job, proc._handle)
    except Exception:
        pass


def read_server_log_tail(n=10):
    """bgutil_server.log의 마지막 n줄 반환 (디버깅용)."""
    log_file_path = os.path.join(get_writable_base(), "bgutil_server.log")
    if os.path.isfile(log_file_path):
        try:
            with open(log_file_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            return "".join(lines[-n:])
        except Exception:
            pass
    return ""


# ── 서버 버전·소스 관리 ─────────────────────────────────────────────
_SERVER_FALLBACK_VER = "1.3.2"
_TAG_ZIP = (
    "https://github.com/Brainicism/bgutil-ytdlp-pot-provider/archive/refs/tags/{ver}.zip"
)


def latest_server_ver(timeout=3):
    """bgutil 서버 최신 릴리즈 태그 (GitHub API). 실패 시 None — 호출부 폴백.

    [stale 감지용 경량 호출] timeout을 짧게(3초) 유지 — DEPS/프리웜 경로의
    블로킹 최소화. 네트워크 실패는 None으로 흡수해 판정 유지.
    """
    try:
        req = urllib.request.Request(
            "https://api.github.com/repos/Brainicism/bgutil-ytdlp-pot-provider/releases/latest",
            headers={"User-Agent": "ChzzkTube"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return (json.load(resp).get("tag_name") or "").strip() or None
    except Exception:
        return None


def server_installed_ver():
    """로컬에 전개된 bgutil 서버 버전 (.version 마커). 없으면 None."""
    try:
        with open(os.path.join(server_home(), ".version"), encoding="utf-8") as f:
            return f.read().strip() or None
    except OSError:
        return None


def clean_stale_plugin():
    """구버전에서 설치된 bgutil Python 플러그인 제거.

    yt_dlp_plugins/ 아래 getpot_bgutil이 남으면 yt-dlp 플러그인 로더가
    자동 로드해 fetch_po_token과 이중 주입 → 토큰 충돌 위험. 기동 시 1회.
    대상: <writable_base>/yt_dlp_plugins, <components>/yt-dlp/yt_dlp_plugins
    """
    import components
    roots = [
        os.path.join(get_writable_base(), "yt_dlp_plugins"),
        os.path.join(components.components_root(), "yt-dlp", "yt_dlp_plugins"),
    ]
    removed = False
    for d in roots:
        if os.path.isdir(d):
            shutil.rmtree(d, ignore_errors=True)
            removed = True
    return removed


# ── 서버 기동/빌드/수명주기 ─────────────────────────────────────────
def _wait_port(seconds, log_full_func=None):
    """포트가 열릴 때까지 폴링. log_full_func가 있으면 5초마다 진척 로그 출력."""
    deadline = time.time() + seconds
    last_log = 0.0
    while time.time() < deadline:
        if probe_server()[0] == "ok":
            return True
        now = time.time()
        if log_full_func and now - last_log >= 5.0:
            log_full_func(
                f"[pot:spawn] waiting for server... "
                f"{int(seconds - (deadline - now))}s / {seconds}s"
            )
            last_log = now
        time.sleep(0.5)
    return False


def _kill(proc):
    """서버 프로세스 강제 종료 (침묵형)."""
    try:
        proc.kill()
    except Exception:
        pass


def kill_process_on_port(port=DEFAULT_PORT, log_func=None):
    """지정된 포트를 점유한 프로세스 강제 종료 (크로스플랫폼).

    좀비 프로세스 정리용 — server_ping이 True인데 PID가 죽은 경우 호출.
    """
    import platform as _plat
    killed = False
    try:
        if _plat.system() == "Windows":
            # Windows: netstat로 PID 찾기 → taskkill
            import subprocess as _sub
            try:
                out = _sub.check_output(
                    ["netstat", "-ano"], text=True, stderr=_sub.DEVNULL
                )
                for line in out.splitlines():
                    if f":{port} " in line and "LISTENING" in line:
                        parts = line.split()
                        if parts:
                            pid = parts[-1]
                            if pid.isdigit():
                                _sub.run(
                                    ["taskkill", "/F", "/PID", pid],
                                    stdout=_sub.DEVNULL,
                                    stderr=_sub.DEVNULL,
                                )
                                if log_func:
                                    log_func(f"[pot:zombie] killed windows pid={pid} on port {port}")
                                killed = True
            except Exception:
                pass
        else:
            # macOS/Linux: lsof로 PID 찾기 → kill
            import subprocess as _sub
            try:
                out = _sub.check_output(
                    ["lsof", "-ti", f":{port}"], text=True, stderr=_sub.DEVNULL
                )
                for pid_str in out.strip().split():
                    if pid_str.isdigit():
                        pid = int(pid_str)
                        os.kill(pid, 9)  # SIGKILL
                        if log_func:
                            log_func(f"[pot:zombie] killed posix pid={pid} on port {port}")
                        killed = True
            except Exception:
                pass
    except Exception:
        pass
    return killed


def built_server_js():
    """컴파일된 main.js 경로 반환 (build/ 와 dist/ 모두 지원)."""
    base_dir = os.path.join(server_home(), "server")
    for out_dir in ("build", "dist"):
        js_path = os.path.join(base_dir, out_dir, "main.js")
        if os.path.isfile(js_path):
            return js_path
    return None


def pot_readiness(log_func=None, check_stale=False, want_refresh=False):
    """POT 서버 기동 가능성 경량 판정 — 파일시스템 스캔만 (L0, 네트워크·Popen 금지).

    [Lazy 2층 분리] DEPS 단계에서는 바이너리+빌드 산출물의 디스크 준비만
    확인하고 (RAM 0MB·포트 미점유), 실제 Popen은 분석 게이트까지 지연.
    - ready=True  → 게이트 히트 시 즉시 spawn 가능 (0.1~3초)
    - ready=False → reason에 부족분 명시 (node missing / no build / stale vX→vY)
    - stale + want_refresh=True → 자동 리프레시 유도 (reason은 여전히 stale)

    [성능] node_ok()의 subprocess 기동(수백ms)을 피하고 node_exe() 존재만으로
    판정 — UpdateWorker 스레드 블로킹 및 DEPS 1초 예산 초과 방지.
    정확한 버전 판별은 _do_upgrade의 ensure_node_runtime이 담당.
    log_func(msg): 판정 근거를 raw 스택으로 반환 (계층 역전 방지용 콜백).
    check_stale=True → GitHub 최신 태그와 로컬 .version 비교 (네트워크 3초).
    실패(None) 시 판정 유지 — stale 미확인을 FAIL로 승격 금지.
    want_refresh=True → stale 시 ready=True 복귀 + reason에 refresh 표기.
    "lazy는 언제든지 작동 가능한 데에서 의의가 있다"는 원칙에 따라,
    stale 빌드도 "준비 완료(staged/refresh pending)"로 간주.
    """
    from node_provider import node_exe
    try:
        exe = node_exe()
        if not exe:
            if log_func:
                try:
                    log_func("[pot-readiness] not ready: node missing")
                except Exception:
                    pass
            return False, "node missing"
    except Exception:
        return False, "node missing"
    try:
        js = built_server_js()
        if not js:
            if log_func:
                try:
                    log_func("[pot-readiness] not ready: no build")
                except Exception:
                    pass
            return False, "no build"
    except Exception:
        return False, "no build"
    if check_stale:
        # [stale 감지] 로컬 .version vs GitHub 최신 — 불일치면 리프레시 유도.
        # 네트워크 실패(None) 시 판정 유지 (stale 미확인 ≠ FAIL).
        # [auto-refresh] want_refresh=True면 stale이어도 "작동 가능한 준비됨"으로
        # 간주 — 프리웜이 자동으로 리프레시 진행. "lazy는 언제든 작동 가능해야 함"
        # 원칙: stale 빌드를 fail로 닫지 않고 staged/refresh pending으로 열어야 한다.
        try:
            local = server_installed_ver()
            remote = latest_server_ver()
            stale = remote and local and remote != local
            if stale:
                if log_func:
                    try:
                        log_func(f"[pot-readiness] stale build (local {local} → remote {remote})")
                    except Exception:
                        pass
                if want_refresh:
                    return True, f"stale {local}→{remote} (refresh pending)"
                return False, f"stale {local}→{remote}"
        except Exception:
            pass
    if log_func:
        try:
            log_func(f"[pot-readiness] standby (node ok, build {js})")
        except Exception:
            pass
    return True, "standby"


def _spawn_node_server(log_full_func=None):
    """Node.js로 bgutil HTTP 서버 기동하고 45초 내에 /ping 응답 확인."""
    from node_provider import node_exe

    js, node = built_server_js(), node_exe()
    if not js and log_full_func:
        log_full_func("server spawn reason: built main.js missing (server/build)")
    if not node and log_full_func:
        log_full_func(f"server spawn reason: Node.js >= {NODE_MIN_MAJOR} binary missing")
    if not (js and node):
        return None

    log_file_path = os.path.join(get_writable_base(), "bgutil_server.log")
    try:
        log_file = open(log_file_path, "w", encoding="utf-8", errors="replace")
    except Exception:
        log_file = subprocess.DEVNULL

    try:
        env = os.environ.copy()
        node_dir = os.path.dirname(os.path.abspath(node))
        env["PATH"] = node_dir + os.pathsep + env.get("PATH", "")

        kwargs = {}
        if platform.system() == "Windows":
            kwargs["creationflags"] = _NO_WINDOW | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        proc = subprocess.Popen(
            [node, js],
            cwd=os.path.dirname(js),
            stdout=log_file,
            stderr=log_file,
            env=env,
            **kwargs,
        )
        assign_to_job_object(proc)
    except Exception as e:
        if log_full_func:
            log_full_func(f"server Popen failed: {e}")
        return None
    if _wait_port(20, log_full_func):
        return proc
    _kill(proc)
    if log_full_func:
        log_full_func(
            "server spawn reason: /ping not responding in 20s "
            "(crash after startup — see bgutil_server.log)"
        )
    return None


def _spawn_existing(log_full_func=None):
    """기존 빌드가 있으면 재사용, 없으면 _spawn_node_server 위임."""
    return _spawn_node_server(log_full_func)


def _download_with_progress(url, dest_path, log_func, desc):
    """청크 단위 분할 다운로드 및 콘솔에 친절한 진행률 출력."""
    temp_dest = dest_path + ".tmp"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ChzzkTube"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            total_size = int(resp.headers.get("content-length", 0))
            downloaded = 0
            with open(temp_dest, "wb") as f:
                while True:
                    chunk = resp.read(1024 * 1024)  # 1MB
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        pct = int(downloaded / total_size * 100)
                        log_func(f"{desc}... {pct}%", True, False)
            if os.path.exists(temp_dest):
                shutil.move(temp_dest, dest_path)
    finally:
        if os.path.exists(temp_dest):
            try:
                os.remove(temp_dest)
            except Exception:
                pass


def _prewarm_lock_path():
    """프리웜/게이트 npm 빌드 상호배제용 락 파일 경로."""
    return os.path.join(server_home(), ".prewarm.lock")


def _pid_alive(pid):
    """PID 생존 확인 — Windows OpenProcess / POSIX kill(pid, 0).

    [PID-liveness] mtime 단일 기준의 오판(크래시 후 30분 프리웜 양보)을
    막기 위해 프로세스 실존 여부를 직접 확인. 판별 실패(권한 등)는
    보수적으로 살아있음으로 간주 (성급한 회수 금지).
    """
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    try:
        import platform as _plat
        if _plat.system() == "Windows":
            import ctypes as _ct
            from ctypes import wintypes as _wt
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            try:
                _k32 = _ct.WinDLL("kernel32", use_last_error=True)
                _k32.OpenProcess.argtypes = [_wt.DWORD, _wt.BOOL, _wt.DWORD]
                _k32.OpenProcess.restype = _wt.HANDLE
                _k32.CloseHandle.argtypes = [_wt.HANDLE]
                _k32.CloseHandle.restype = _wt.BOOL
                h = _k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
                if not h:
                    return False  # 존재하지 않거나 접근 불가 → 죽음으로 간주
                try:
                    return True
                finally:
                    _k32.CloseHandle(h)
            except Exception:
                return True  # 판별 자체 실패 → 보수적 유지
        else:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return False
            except PermissionError:
                return True  # 존재하나 권한 없음 → 살아있음
            except Exception:
                return True
            return True
    except Exception:
        return True


def _read_lock_info(path):
    """락 파일에서 (pid:int|None, epoch:float|None) 판독."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            parts = f.read().strip().split()
        pid = int(parts[0]) if parts else None
        epoch = float(parts[1]) if len(parts) > 1 else None
        return pid, epoch
    except Exception:
        return None, None


def acquire_prewarm_lock(timeout=0, log_func=None):
    """원자적 락 획득 시도 — O_EXCL 생성으로 상호배제.

    [Zero-Base] msvcrt/filelock 외부 의존 없이 os.open(O_CREAT|O_EXCL)
    원자 생성으로 프로세스·스레드 경계를 모두 차단 (단일 앱 전제).
    stale 락 판정: PID 죽음 AND mtime 30분 초과 → 회수. PID 살아있으면
    mtime 무관하게 대기 (PID 재사용 레이스는 mtime 상한으로 차단).
    timeout=0 → 즉시 반환 (None이면 획득 실패). timeout>0 → 폴링 대기.
    반환: fd(int) 또는 None. 해제는 release_prewarm_lock(fd).
    log_func(msg): 획득/대기/양보/stale 회수 전 분기를 호출자 로그로 반환.
    """
    import time as _time
    path = _prewarm_lock_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
    except OSError:
        pass
    deadline = _time.monotonic() + max(0, timeout)
    waited_note = False
    while True:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            try:
                os.write(fd, f"{os.getpid()} {_time.time()}".encode("utf-8"))
            except OSError:
                pass
            if log_func:
                try:
                    log_func("[prewarm-lock] acquired")
                except Exception:
                    pass
            return fd
        except FileExistsError:
            pid, _epoch = _read_lock_info(path)
            alive = _pid_alive(pid) if pid else True
            try:
                age = _time.time() - os.path.getmtime(path)
            except OSError:
                age = 0
            if not alive and age > 1800:  # PID 죽음 + 30분 stale → 회수
                if log_func:
                    try:
                        log_func(f"[prewarm-lock] stale reclaimed (pid={pid} dead, age={int(age)}s)")
                    except Exception:
                        pass
                try:
                    os.remove(path)
                except OSError:
                    pass
                continue
            if log_func and not waited_note and timeout > 0:
                waited_note = True
                try:
                    log_func(f"[prewarm-lock] waiting (holder pid={pid}, alive={alive})")
                except Exception:
                    pass
        except OSError:
            return None
        if _time.monotonic() >= deadline:
            if log_func:
                try:
                    log_func("[prewarm-lock] busy — acquire timeout")
                except Exception:
                    pass
            return None
        _time.sleep(0.2)


def release_prewarm_lock(fd, log_func=None):
    """락 해제 — fd close + 파일 제거 (best-effort)."""
    try:
        os.close(fd)
    except OSError:
        pass
    try:
        os.remove(_prewarm_lock_path())
    except OSError:
        pass
    if log_func:
        try:
            log_func("[prewarm-lock] released")
        except Exception:
            pass


def download_and_install_source(want_ver, log_func=None):
    """지정된 버전의 bgutil 서버 소스를 다운로드하여 세팅한다."""
    dest_dir = server_home()
    tmp = tempfile.mkdtemp(prefix="chzzktube_bgutil_")
    zpath = os.path.join(tmp, "src.zip")
    try:
        url = _TAG_ZIP.format(ver=want_ver)
        if log_func:
            _download_with_progress(url, zpath, log_func, "bgutil source downloading")
        else:
            urllib.request.urlretrieve(url, zpath)

        with zipfile.ZipFile(zpath) as zf:
            names = zf.namelist()
            root = (names[0].split("/")[0] if names else "") or f"bgutil-ytdlp-pot-provider-{want_ver}"
            zf.extractall(tmp)

        inner = os.path.join(tmp, root)
        if not os.path.isfile(os.path.join(inner, "server", "package.json")):
            raise RuntimeError("downloaded source has no server/ directory")

        os.makedirs(dest_dir, exist_ok=True)
        shutil.copytree(inner, dest_dir, dirs_exist_ok=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _run_and_stream_log(cmd, cwd, log_full_func, env=None, use_no_window=True):
    """서브프로세스 실행 + 출력 스트리밍.

    use_no_window=False로 설정하면 CREATE_NO_WINDOW 플래그를 적용하지 않음.
    tsc 등 콘솔 출력에 의존하는 도구는 이 옵션을 False로 설정해야 함.
    """
    try:
        kwargs = {}
        if platform.system() == "Windows" and use_no_window:
            kwargs["creationflags"] = _NO_WINDOW
        proc = subprocess.Popen(
            cmd, cwd=cwd,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
            env=env, **kwargs,
        )
        stdout, _ = proc.communicate()
        if stdout and log_full_func:
            for line in stdout.splitlines():
                stripped = line.strip()
                if stripped:
                    log_full_func(stripped)
        return proc.returncode
    except Exception as e:
        if log_full_func:
            log_full_func(f"subprocess Popen error: {e}")
        return -1


def _prune_outdated_node_dirs(node_dir):
    """요구 버전 미만의 구형 Node.js 캐시 폴더 정리 (디스크 낭비 방지)."""
    import re as _re
    try:
        for name in os.listdir(node_dir):
            m = _re.match(r"node-v(\d+)\.", name)
            if m and int(m.group(1)) < NODE_MIN_MAJOR:
                shutil.rmtree(os.path.join(node_dir, name), ignore_errors=True)
    except Exception:
        pass


def ensure_node_server(log, log_full, want_ver, rebuild=False):
    """Node.js HTTP 서버 및 빌드 소스 구성을 완료한다.

    [rebuild 플래그]
    - True: 기존 빌드가 있더라도 npm ci / tsc 강제 재실행 (서버 업데이트용)
    - False: 빌드 산출물 존재 시 재사용 (런타임만 확인)

    [흐름]
    1. 빌드 디렉터리(server/) 존재 여부로 분기
       - server/ 없음 → source fetch → npm ci → tsc
       - server/ 있음 + rebuild=False → 기존 빌드 재사용
    2. 빌드 성공 시 server_dir 반환 → 호출부에서 _spawn_existing 기동
    """
    from node_provider import (
        node_exe, node_ok, node_major_version,
        ensure_node_runtime, bundled_npm_ok,
    )

    js = built_server_js()

    # [rebuild 모드] npm ci + tsc 강제 재실행
    if js is None or rebuild:
        server_src_dir = os.path.join(server_home(), "server")
        source_exists = os.path.isdir(server_src_dir) and os.path.isfile(
            os.path.join(server_src_dir, "package.json")
        )
        if not source_exists:
            ver = want_ver or latest_server_ver() or _SERVER_FALLBACK_VER
            log(emit_component("pot", "RUN", "pot", f"bgutil source fetching (v{ver})"))
            try:
                download_and_install_source(ver, log)
            except Exception as ds_ex:
                log_full(f"[pot] source fetch failed: {ds_ex}")
        else:
            log(emit_component("pot", "RUN", "pot", "bgutil source detected — building"))

        if not ensure_node_runtime(log):
            return None, f"Node.js runtime unavailable (>= {NODE_MIN_MAJOR} required)"
        curr_node = node_exe()
        if not curr_node:
            return None, "Node.js executable not found"

        npm_cli = None
        node_base_dir = os.path.dirname(curr_node)
        for root, dirs, files in os.walk(node_base_dir):
            if "npm-cli.js" in files:
                npm_cli = os.path.join(root, "npm-cli.js")
                break

        npm_cmd = [curr_node, npm_cli] if npm_cli else [shutil.which("npm") or "npm"]
        server_dir = os.path.join(server_home(), "server")

        try:
            log(emit_component("pot", "RUN", "pot", "npm install... (first run may take minutes)"))
            env = os.environ.copy()
            node_dir = os.path.dirname(os.path.abspath(curr_node))
            env["PATH"] = node_dir + os.pathsep + env.get("PATH", "")

            cmd_install = npm_cmd + ["ci", "--no-audit", "--no-fund"]
            ret = _run_and_stream_log(cmd_install, server_dir, log_full, env=env)
            if ret != 0:
                return None, f"npm install failed (exit code {ret})"

            log(emit_component("pot", "RUN", "pot", "tsc compiling..."))
            # [tsc incremental 함정 수리]
            if built_server_js() is None:
                tsbi = os.path.join(server_dir, "tsconfig.tsbuildinfo")
                if os.path.isfile(tsbi):
                    try:
                        os.remove(tsbi)
                        log_full("[pot] stale tsbuildinfo purged — forcing full tsc compile")
                    except OSError as tsbi_ex:
                        log_full(f"[pot] tsbuildinfo purge failed: {tsbi_ex}")

            local_tsc = os.path.join(server_dir, "node_modules", "typescript", "bin", "tsc")
            if os.path.isfile(local_tsc):
                cmd_build = [curr_node, local_tsc]
            else:
                cmd_build = [curr_node, npm_cli, "execute", "tsc"] if npm_cli else ["npx", "tsc"]

            ret = _run_and_stream_log(cmd_build, server_dir, log_full, env=env, use_no_window=False)
            if ret != 0:
                return None, f"tsc failed (exit code {ret})"

            if built_server_js() is None:
                return None, "server/build/main.js (or dist/main.js) missing after compile"
            return server_dir, None
        except Exception as e:
            return None, f"{type(e).__name__}: {e}"

    # [재사용 모드] 기존 빌드가 있으면 런타임만 확인 → 즉시 반환
    if not ensure_node_runtime(log):
        return None, "Node.js runtime unavailable"
    if node_ok():
        return os.path.dirname(server_home()), None
    return None, "Node.js runtime check failed"

```

## File: progress_emitter.py

```python
##### progress_emitter.py - DownloadWorker 진행률/헤더 emit 파이프라인
"""다운로드 진행률·완료·헤더 로그의 단일 출처.

- VOD 진행 틱: yt-dlp hook → `_speed_win`(10초 이동평균) → 0.5초 스로틀 컬럼 라인
- 라이브 틱·마감: 릴레이 파이프 계수 → 동일 컬럼 규격 (용량 rjust(9) / 속도 rjust(11))
- 헤더(다운로드/라이브/치지직): 제목·포맷 트리 조판, 통합 포맷은 오디오 가지 미표기
- media.cli_format_desc 가 포맷 표기의 단일 출처.

── Worker Contract ──────────────────────────────────────────────
본 모듈의 함수들이 요구하는 worker 객체의 인터페이스:
  worker.logger           : YtLoggerBridge — raw 버스 직행 (log_full/log_concise 시그널 폐기)
  worker.cfg              : dict  — download_path, container 등 설정
  worker.v_spec           : dict  — height, fps 등 비디오 스펙
  worker.audio_desc       : str   — 오디오 설명
  worker.current_url       : str   — 현재 처리 중인 URL
  worker.current_file      : str|None — 현재 다운로드 파일 경로
  worker._speed_win        : SpeedWindow — 이동평균 속도 (hook 내부에서 add)
  worker.total_count / current_idx : int — 배치 진행 현황
  worker.live_partially_saved : bool — 라이브 부분 저장 플래그
──────────────────────────────────────────────────────────────────
"""
import os
import time

from log_console import (
    emit_event,
    emit_dl,
    emit_err,
)
import raw_log
from media import cli_format_desc, format_bytes
from dl_platform import _dl_platform
from client_opts import _apply_client_opts, _apply_cookie_opts


def _dl_spec(ctx):
    """컨텍스트에서 사양 문자열 추출 (해상도·fps, 오디오 폴백)."""
    v = ctx.v_spec or {}
    h = v.get("height") or 0
    fps = v.get("fps") or 0
    if h:
        return f"{h}p{fps}" if fps else f"{h}p"
    a_desc = ctx.audio_desc or ""
    if a_desc and ("(" in a_desc or "AAC" in a_desc or "OPUS" in a_desc):
        return a_desc
    return ""


def hook(ctx, d):
    """yt-dlp progress_hook 콜백 — downloading→틱, finished→완료 메타."""
    status = d.get("status")
    if status == "downloading":
        return emit_progress_tick(ctx, d)
    if status == "finished":
        fpath = d.get("filename") or ctx.current_file or ""
        return log_success_info(ctx, fpath)
    return None


_TICK_INTERVAL = 0.5  # VOD 틱 0.5초 스로틀


def emit_progress_tick(ctx, d):
    """VOD 진행 틱 — 0.5초 스로틀, SpeedWindow 평균 속도, 컬럼 라인."""
    now = time.monotonic()
    last = ctx._last_tick_t or 0
    if last and now - last < _TICK_INTERVAL:
        return
    ctx._last_tick_t = now

    done = float(d.get("downloaded_bytes") or 0)
    total = float(d.get("total_bytes") or d.get("total_bytes_estimate") or 0)

    ctx.speed_win.add(done)
    rate = ctx.speed_win.speed()
    speed_s = f"{format_bytes(rate)}/s" if rate else "-"

    pct = (done / total * 100.0) if total else 0.0
    # 제목은 이미 ANAL 단계에서 표시되었으므로 제외 (중복 방지)
    title = ""

    raw_log.raw(
        "dl",
        emit_dl(
            status="RUN",
            platform=_dl_platform(ctx.current_url or ""),
            spec=_dl_spec(ctx),
            speed=speed_s,
            pct=pct,
            bar_frac=min(pct / 100.0, 1.0),
            msg=title,
            is_status=True,   # 진행률 틱은 새 줄 금지, 한 줄 덮어쓰기(갱신형)
        ),
        to_tui=True,
    )


def log_success_info(ctx, file_path):
    """개별 파일 완료 — 용량 포함 한 줄."""
    size = 0
    if file_path and os.path.exists(file_path):
        size = os.path.getsize(file_path)
    # [채널명 포함] DL 완료 Msg에 채널명 추가
    channel = _dl_platform(ctx.current_url or "")
    fname = os.path.basename(file_path) if file_path else "done"
    msg = f"{fname} ({format_bytes(size)})" if file_path else "done"
    raw_log.raw("dl", emit_event("DL", "OK", channel, msg), to_tui=True)


# ── 헤더 ───────────────────────────────────────────────────────────────────


def _title_of(info):
    return str(info.get("title") or info.get("videoTitle") or "video")


def emit_download_header(ctx, info):
    """VOD 다운로드 시작 헤더 — 컬럼 포맷 통일."""
    title = _title_of(info)
    fmt = info.get("format") or {}
    fmt_desc = cli_format_desc(fmt) if fmt and isinstance(fmt, dict) else ""
    msg = f"{title}"
    if fmt_desc:
        msg += f" ({fmt_desc})"
    raw_log.raw(
        "dl",
        emit_event("DL", "RUN", _dl_platform(ctx.current_url or ""), msg),
        to_tui=True,
    )
    ctx._meta_logged = True


def emit_live_header(ctx, info, res_label=""):
    """라이브 녹화 시작 헤더 — LIVE 스테이지, 해상도는 SPEC 분리."""
    title = _title_of(info)
    if res_label:
        raw_log.raw(
            "dl",
            emit_dl("RUN", _dl_platform(ctx.current_url or ""),
                    spec=res_label, stage="LIVE", msg=title),
            to_tui=True,
        )
    else:
        raw_log.raw(
            "dl",
            emit_dl("RUN", _dl_platform(ctx.current_url or ""),
                    stage="LIVE", msg=title),
            to_tui=True,
        )
    ctx._meta_logged = True


def emit_chzzk_header(ctx, ch_info, fmt):
    """치지직(클립/VOD) 헤더 — 컬럼 포맷 통일."""
    title = ch_info.get("videoTitle") or ch_info.get("title") or "untitled"
    fmt_desc = cli_format_desc(fmt) if fmt else ""
    msg = f"chzzk — {title}"
    if fmt_desc:
        msg += f" ({fmt_desc})"
    raw_log.raw("dl", emit_event("DL", "RUN", "chzzk", msg), to_tui=True)
    ctx._meta_logged = True


def emit_live_final_stats(ctx, total_bytes, start_time):
    """라이브 종료 통계 — LIVE 스테이지, 용량은 MSG·평균 속도는 SPEED."""
    dur = (time.monotonic() - start_time) if start_time else 0.0
    rate = (total_bytes / dur) if dur > 0 else 0.0
    raw_log.raw(
        "dl",
        emit_dl(
            status="DONE",
            platform="-",
            spec="-",
            speed=f"{format_bytes(rate)}/s",
            pct=100,
            bar_frac=1.0,
            stage="LIVE",
            msg=f"live done ({format_bytes(total_bytes)})",
        ),
        to_tui=True,
    )
    ctx.live_partially_saved = False

```

## File: raw_log.py

```python
﻿"""raw_log — 앱 전체 동작의 단일 진실 공급원 (raw 버스).

[계약 v3.3.0 — 포함관계 모델]
- 진입: raw(tag, msg) — msg는 LogEvent(문자열은 즉시 LogEvent로 정규화).
- 포함관계: history=전량, F12(full)=전량(⊇TUI), TUI(concise)=to_tui=True일 때만.
  → "F12가 안 받는 로그"는 존재하지 않는다.
- 라우팅: 채널은 발행자(raw() 호출점)가 결정한다 — 콘텐츠 정규식 판정 제로.
- 구독 전 호출도 history에 적재되므로 유실 없다.

[계층] 발행 스레드에서는 bounded queue 적재만 수행한다.
파일 I/O와 구독자 호출은 단일 dispatcher 스레드에서 순차 처리하며,
구독자 콜백은 dispatcher lock을 잡지 않은 상태에서 호출한다.
"""
from collections import deque
import queue
import threading
import time
from typing import Callable

from log_event import LogEvent


MAX_QUEUE = 2048
MAX_FULL_EVENTS = 4096
_HISTORY_SUMMARY = "raw_log queue overflow: UI mirror dropped"


class _RawDispatcher:
    """Single-consumer dispatcher; publishers only perform a non-blocking put."""

    def __init__(self) -> None:
        self._queue: queue.Queue[tuple] = queue.Queue(maxsize=MAX_QUEUE)
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._concise_subs: list[Callable] = []
        self._full_subs: list[Callable] = []
        self._full_events: deque[LogEvent] = deque(maxlen=MAX_FULL_EVENTS)
        self._overflowed = False
        self._thread = threading.Thread(target=self._run, name="raw-log-dispatcher", daemon=True)
        self._thread.start()

    def subscribe_concise(self, fn: Callable) -> None:
        with self._lock:
            if fn not in self._concise_subs:
                self._concise_subs.append(fn)

    def subscribe_full(self, fn: Callable) -> None:
        with self._lock:
            if fn not in self._full_subs:
                self._full_subs.append(fn)

    def publish(self, event: LogEvent, to_tui: bool) -> bool:
        try:
            self._queue.put_nowait((event, bool(to_tui)))
            return True
        except queue.Full:
            self._record_overflow()
            return False

    def _record_overflow(self) -> None:
        with self._lock:
            if self._overflowed:
                return
            self._overflowed = True
        event = LogEvent(
            stage="SYS",
            status="WARN",
            platform="raw-log",
            spec="-",
            msg=_HISTORY_SUMMARY,
            is_error=True,
        )
        try:
            self._queue.put_nowait((event, True))
        except queue.Full:
            pass
        try:
            import log_history
            log_history.log(f"[raw-log] {_HISTORY_SUMMARY}", level="WARN")
        except Exception:
            pass

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                event, to_tui = self._queue.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                self._dispatch(event, to_tui)
            except Exception:
                # A subscriber must never kill the log pipeline.
                pass
            finally:
                self._queue.task_done()

    def _dispatch(self, event: LogEvent, to_tui: bool) -> None:
        try:
            import log_history
            log_history.log(
                f"[{getattr(event, 'tag', 'raw')}] {event.msg}",
                level="ERROR" if event.is_error else "INFO",
            )
        except Exception:
            pass

        with self._lock:
            self._full_events.append(event)
            full_subs = tuple(self._full_subs)
            concise_subs = tuple(self._concise_subs) if to_tui else ()

        for fn in full_subs:
            try:
                fn(event, bool(event.is_status))
            except TypeError:
                try:
                    fn(event)
                except Exception:
                    pass
            except Exception:
                pass
        for fn in concise_subs:
            try:
                fn(event, bool(event.is_status), bool(event.is_error))
            except TypeError:
                try:
                    fn(event)
                except Exception:
                    pass
            except Exception:
                pass

    def shutdown(self, timeout: float = 1.0) -> None:
        self._stop.set()
        self._thread.join(timeout=timeout)

    def flush(self, timeout: float = 1.0) -> None:
        """현재 queue와 dispatcher가 처리 중인 이벤트를 순서대로 기다린다."""
        self._queue.join()
        deadline = time.monotonic() + timeout
        while self.pending and time.monotonic() < deadline:
            time.sleep(0.01)

    @property
    def pending(self) -> int:
        return self._queue.qsize()

    @property
    def overflowed(self) -> bool:
        with self._lock:
            return self._overflowed


_dispatcher = _RawDispatcher()


def subscribe_concise(fn):
    """메인로그(TUI) 구독 등록 (중복 방지)."""
    _dispatcher.subscribe_concise(fn)


def subscribe_full(fn):
    """F12 상세로그 구독 등록 (중복 방지)."""
    _dispatcher.subscribe_full(fn)


def raw(tag, msg, is_status=False, is_error=False, to_tui=False):
    """단일 진입점 — 앱의 모든 행동은 여기로 수신된다."""
    if not isinstance(msg, LogEvent):
        msg = LogEvent(
            stage="SYS",
            status="FAIL" if is_error else "OK",
            platform="-",
            spec="-",
            msg=str(msg),
            is_status=is_status,
            is_error=is_error,
            rendered=True,
        )
    else:
        if is_status:
            msg.is_status = True
        if is_error:
            msg.is_error = True
    _dispatcher.publish(msg, to_tui)


def flush(timeout: float = 1.0) -> None:
    """테스트/종료용: 현재 queue가 처리될 때까지 기다린다."""
    _dispatcher.flush(timeout)


def shutdown(timeout: float = 1.0) -> None:
    _dispatcher.shutdown(timeout)


```

## File: smoke_test.py

```python
import os
import sys

# Offscreen QPA 플랫폼 활성화 (headless 환경에서 GUI 실행 가능하게 함)
os.environ["QT_QPA_PLATFORM"] = "offscreen"

# [Windows 리다이렉트 대비] stdout/stderr가 파이프·파일로 리다이렉트되면
# 로케일 인코딩(cp949)으로 떨어져 em-dash(\u2014) 등에서 UnicodeEncodeError가
# 발생한다 — 테스트 자체 결함이 아니라 하네스 결함이므로 UTF-8을 강제한다.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def test_main():
    print("[Smoke Test] PySide6 App 및 MainWindow 초기화 테스트 시작")
    from PySide6.QtWidgets import QApplication
    from dialogs import SettingsDialog
    from main import MainWindow

    app = QApplication(sys.argv)

    # 윈도우 인스턴스 생성
    try:
        win = MainWindow()
        print("[Smoke Test] MainWindow 생성 성공!")
        assert win is not None
        assert win.ctrl is not None
        assert hasattr(win, "_force_unlock_input")
        print("[Smoke Test] dl_state 프로퍼티 확인:", win.dl_state)
        # [다이얼로그 커버] SettingsDialog 실생성 — 콤보/체크박스 초기화가
        # NameError 없이 완료되는지 검증 (QGroupBox 미import·format__flay
        # 오타 잠복 결함을 잡기 위해 도입 — 스모크가 다이얼로그를 안 만들어
        # [TUI 패널 일체화] 결함이 오래 잠복했었다)
        dlg = SettingsDialog(win, is_running=False)
        assert dlg.cb_container.currentData() in ("mp4", "mkv", "webm")
        assert dlg.cb_container.count() == 3
        dlg.update_filename_preview()
        print("[Smoke Test] SettingsDialog 생성 OK — combos", dlg.cb_container.count())
        print("[Smoke Test] PASS")
        return 0
    except Exception as e:
        print("[Smoke Test] FAIL:", e)
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(test_main())

```

## File: speed_window.py

```python
##### speed_window.py - 10초 이동평균 속도계
"""네트워크에서 실제 흐른 바이트만 샘플로 누적해 평균 속도를 계산한다.

라이브=릴레이 파이프 계수, VOD=yt-dlp downloaded_bytes 를 add()에 넘기며,
스트림 전환(비디오→오디오)·타겟 전환 시 reset()으로 윈도우를 비운다.
"""
import time


class SpeedWindow:
    """10초 이동평균 속도계.

    add(총 바이트 누적값)를 계속 공급하면 speed()가 초당 바이트를 반환.
    내부적으로 (타임스탬프, 누적바이트) 표본을 10초 윈도우로 유지한다.
    """

    def __init__(self, window=10.0):
        self._window = float(window)
        self._samples = []
        self._last_total = 0
        self._last_t = 0.0

    def reset(self):
        """윈도우 초기화 — 스트림 전환·타겟 전환 시 호출."""
        self._samples.clear()
        self._last_total = 0
        self._last_t = 0.0

    def add(self, total_bytes, t=None):
        """누적 바이트를 샘플로 추가 (t는 monotonic 초, 기본 now)."""
        now = t if t is not None else time.monotonic()
        self._last_total = total_bytes
        self._last_t = now
        self._samples.append((now, float(total_bytes)))
        cutoff = now - self._window
        if cutoff > 0:
            self._samples = [(tt, b) for tt, b in self._samples if tt >= cutoff]

    def speed(self):
        """초당 바이트. 표본 2개 미만 또는 시간차 없으면 0.0."""
        if len(self._samples) < 2:
            return 0.0
        t0, b0 = self._samples[0]
        t1, b1 = self._samples[-1]
        dt = t1 - t0
        if dt <= 0:
            return 0.0
        return (b1 - b0) / dt
```

## File: startup_coordinator.py

```python
"""시작 시퀀스 단일 책임자 — Signal 경유, POTManager + raw 버스 연동."""

from __future__ import annotations

import threading
from PySide6.QtCore import QObject, Signal

from startup_state import StartupState
from pot_manager import POTManager


class StartupCoordinator(QObject):
    """기동 시퀀스 게이트.

    [Signal 기반]
    - Worker → Coordinator: report_*() (thread-safe)
    - Coordinator → View: ready_emitted / pot_status_changed / ui_unlocked (Qt Signal)
    - Coordinator → raw 버스: raw() (TUI=to_tui + F12 + history 전량)

    [구성 요소]
    - StartupState: 단일 상태 (thread-safe)
    - POTManager: POT 서버 수명주기 (prewarm + gate)
    - raw_log: 로그 라우팅 (라벨링은 여기서 LogEvent로 동봉)
    """

    # ── View로의 Signal ──────────────────────────────────────
    ready_emitted = Signal(str, bool, str)  # (stage, is_status, msg)
    pot_status_changed = Signal(str)
    ui_unlocked = Signal()

    def __init__(self, pot_manager: POTManager, parent=None):
        super().__init__()
        self._pot = pot_manager
        self._state = StartupState()
        self._lock = threading.RLock()
        self._fallback_done = False

        # POTManager 시그널 연결
        self._pot.pot_status_changed.connect(self._on_pot_status)
        self._pot.pot_finished.connect(self._on_pot_finished)

    # ── 버스 발행 (근원 라벨링 단일 경유) ─────────────────────

    def _emit(self, stage, status, msg, is_status=False, is_error=False):
        """READY/READY 경고 등 기동 라인을 LogEvent로 동봉해 버스로 발행."""
        import raw_log
        from log_event import LogEvent
        raw_log.raw(
            "startup",
            LogEvent(stage=stage, status=status, platform="SYS", msg=msg,
                     is_status=is_status, is_error=is_error),
            to_tui=True,
        )

    # ── Worker → Coordinator 보고 ────────────────────────────

    def report_deps(self, ok: bool, msg: str = ""):
        with self._lock:
            self._state.set_deps(ok)
            self._try_emit_ready()

    def report_upgrade(self, ok: bool, summary: str):
        with self._lock:
            self._state.set_upgrade(True)
            if summary:
                self._emit("SYS", "OK" if ok else "FAIL", f"update {summary}",
                           is_error=not ok)
            self._try_emit_ready()

    def report_pot(self, ok: bool, msg: str):
        with self._lock:
            status = msg if ok else "failed"
            # 실제 POTManager 완료 신호는 ``staged``/``ready``만 사용한다.
            # 기존 테스트/호출부의 ``standby`` 보고는 공개 영상용 준비 완료로만
            # 호환 처리하며, 임의의 성공 메시지는 READY 게이트를 열지 않는다.
            ready = ok and (status == "staged" or status == "ready" or status == "standby")
            self._state.set_pot(status, ready=ready)
            self._try_emit_ready()

    def report_ready(self, ok: bool = True, msg: str = "ready"):
        with self._lock:
            if self._state.ready_emitted:
                return
            self._state.mark_ready_emitted()
            self._emit("SYS", "READY" if ok else "WARN", msg)
            self.ready_emitted.emit("SYS", False, msg)
            self.ui_unlocked.emit()

    # ── POTManager 시그널 핸들러 ──────────────────────────────

    def _on_pot_status(self, status: str):
        self.pot_status_changed.emit(status)

    def _on_pot_finished(self, ok: bool, msg: str):
        self.report_pot(ok, msg)

    # ── 강제 READY (15초 폴백) ────────────────────────────────

    def force_unlock(self):
        with self._lock:
            if self._fallback_done:
                return
            self._fallback_done = True
        self._pot.cancel()
        self.report_ready(True, "ready (fallback timeout)")

    # ── READY 발산 게이트 ────────────────────────────────────

    def _try_emit_ready(self):
        with self._lock:
            if self._state.can_emit_ready():
                self._state.mark_ready_emitted()
                self._emit("SYS", "READY", "ready")
                self.ready_emitted.emit("SYS", False, "ready")
                self.ui_unlocked.emit()

    # ── 테스트 호환 프로퍼티 ──────────────────────────────────

    @property
    def _ready_emitted(self):
        return self._state.ready_emitted

    @_ready_emitted.setter
    def _ready_emitted(self, value):
        self._state.ready_emitted = value
```

## File: startup_state.py

```python
"""startup_state.py — 앱 시작 시퀀스 상태 단일 공급원 (SRP: 상태만 관리)

[구조] StartupCoordinator, POTManager, MainWindow가 공유하는 불변 상태 컨테이너.
스레드 안전성을 위해 RLock으로 보호하며, 상태 전이 메서드만 제공.
단계별 순차 비교(phase.value >) 대신 플래그 조합으로 동시성 안전성 확보.
"""
import threading
from dataclasses import dataclass, field


@dataclass(slots=True)
class StartupState:
    """앱 시작 시퀀스 상태 단일 공급원."""
    
    # 단계별 완료 플래그
    deps_ok: bool = False
    upgrade_done: bool = False
    pot_status: str = "unknown"   # unknown/running/standby/staged/failed
    pot_ready: bool = False
    ready_emitted: bool = False
    
    # 내부 동기화
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    # ── 상태 변경 메서드 (RLock 보호) ──────────────────────────
    
    def set_deps(self, ok: bool) -> None:
        with self._lock:
            self.deps_ok = ok

    def set_upgrade(self, done: bool) -> None:
        with self._lock:
            self.upgrade_done = done

    def set_pot(self, status: str, ready: bool | None = None) -> None:
        with self._lock:
            self.pot_status = status
            if ready is not None:
                self.pot_ready = ready

    def mark_ready_emitted(self) -> None:
        with self._lock:
            self.ready_emitted = True

    # ── 판정 메서드 ────────────────────────────────────────
    
    def can_emit_ready(self) -> bool:
        """READY 발산 조건 충족 여부."""
        with self._lock:
            return (
                self.deps_ok
                and self.upgrade_done
                and self.pot_ready
                and not self.ready_emitted
            )

    def is_ready(self) -> bool:
        with self._lock:
            return self.ready_emitted

    def snapshot(self) -> dict:
        """디버깅용 상태 스냅샷."""
        with self._lock:
            return {
                "deps_ok": self.deps_ok,
                "upgrade_done": self.upgrade_done,
                "pot_status": self.pot_status,
                "pot_ready": self.pot_ready,
                "ready_emitted": self.ready_emitted,
            }
```

## File: sync_mirrors.py

```python
# sync_mirrors.py - .py 소스 → mirrors/*.md 미러 자동 동기화 스크립트
"""
사용법:
    python sync_mirrors.py              # 변경된 미러 파일 및 chzzktube_codebase.md 일괄 동기화
    python sync_mirrors.py --check      # 변경 여부만 확인 (쓰지 않음)
    python sync_mirrors.py main utils   # 특정 모듈만 대상 지정 (파일명 기준)
"""

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MIRRORS_DIR = ROOT / "mirrors"

# 미러 대상 (확장자 제외). .py → mirrors/*.md 로 복사된다.
# 새 .py 모듈 추가 시 이 목록에도 반드시 추가할 것.
MIRROR_MODULES = [
    "analyze_worker",
    "bump_version",
    "chzzk_api",
    "client_opts",
    "components",
    "config",
    "controller",
    "cookies",
    "dialogs",
    "dl_platform",
    "dl_context",
    "downloader",
    "finalizer",
    "live_recorder",
    "log_console",
    "log_event",
    "log_history",
    "main",
    "media",
    "node_provider",
    "playlist",
    "po_client",
    "pot_manager",
    "pot_provider",
    "pot_server",
    "progress_emitter",
    "raw_log",
    "smoke_test",
    "speed_window",
    "startup_coordinator",
    "startup_state",
    "sync_mirrors",
    "target_downloader",
    "theme",
    "update_worker",
    "updater",
    "utils",
    "yt_logger_bridge",
]


def sync_module(name: str, dry_run: bool = False) -> int:
    """단일 모듈의 .py → mirrors/*.md 미러를 갱신한다. (변경 시 1, 동일 시 0, 누락 시 2)"""
    clean_name = name.removesuffix(".py")

    src = ROOT / f"{clean_name}.py"
    dst = MIRRORS_DIR / f"{clean_name}.md"

    if not src.exists():
        print(f"[skip] {src.name} 없음 — 대상 미러 확인 불가")
        return 2

    content = src.read_bytes()
    if dst.exists() and dst.read_bytes() == content:
        print(f"[동일] mirrors/{clean_name}.md 최신 상태")
        return 0

    action = "확인" if dry_run else "갱신"
    print(
        f"[{action}] {clean_name}.py -> mirrors/{clean_name}.md ({len(content)} bytes)"
    )
    if not dry_run:
        MIRRORS_DIR.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(content)
    return 1


def build_codebase_bundle():
    """모든 .py 소스를 mirrors/chzzktube_codebase.md 단일 합본으로 번들링한다."""
    bundle_path = MIRRORS_DIR / "chzzktube_codebase.md"
    exclude_dirs = {
        ".git",
        ".github",
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        "build",
        "dist",
        "tests",
        "mirrors",
    }

    MIRRORS_DIR.mkdir(parents=True, exist_ok=True)
    with open(bundle_path, "w", encoding="utf-8") as outfile:
        outfile.write("# ChzzkTube Project Full Codebase\n\n")
        for root, dirs, files in os.walk(ROOT):
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            for file in sorted(files):
                if file.endswith(".py"):
                    rel = os.path.relpath(os.path.join(root, file), ROOT)
                    outfile.write(f"\n## File: {rel}\n\n```python\n")
                    with open(
                        os.path.join(root, file), "r", encoding="utf-8", errors="ignore"
                    ) as infile:
                        outfile.write(infile.read())
                    outfile.write("\n```\n")
    print(f"[생성] mirrors/{bundle_path.name} 합본 생성 완료")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="ChzzkTube .py 소스의 .md 미러 파일을 동기화한다."
    )
    parser.add_argument(
        "modules",
        nargs="*",
        help="대상 모듈(예: main downloader). 미지정 시 전체 대상.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="변경될 파일만 나열하고 실제 쓰기는 하지 않는다.",
    )
    args = parser.parse_args()

    targets = args.modules or MIRROR_MODULES
    results = [sync_module(m, dry_run=args.check) for m in targets]

    changed = sum(1 for r in results if r == 1)
    missing = sum(1 for r in results if r == 2)

    print("-" * 40)
    print(f"총 {len(targets)}개 중 변경 {changed}개 / 누락 {missing}개")

    # --check 모드가 아닐 때 단일 합본 파일도 함께 생성/최신화
    if not args.check:
        build_codebase_bundle()

    return 0


if __name__ == "__main__":
    sys.exit(main())

```

## File: target_downloader.py

```python
##### target_downloader.py - 개별 URL 다운로드 / 대상 평탄화
"""DownloadWorker 의 다운로드 실행부 분할 모듈.

- expand_targets : 재생목록/채널 URL 을 개별 동영상 URL 로 평탄화
- download_target : 개별 URL 을 타입별로 분기해 실제 다운로드
  chzzk(clip/vod) → 직접 HTTP 스트림, youtube VOD → yt-dlp,
  youtube live → _download_youtube_live(ffmpeg), stream → streamlink

── Worker Contract ──────────────────────────────────────────────
본 모듈의 함수들이 요구하는 worker 객체의 인터페이스:
  worker.cfg              : dict  — download_path, max_video_res, container,
                                     audio_only, fast_download, yt_player_client 등
  worker.v_sel / a_sel    : str   — 선택된 비디오/오디오 format_id ("auto" 가능)
  worker.v_spec           : dict  — height, fps 등 비디오 스펙 (v_list[0]에서 추출)
  worker.audio_desc       : str   — 오디오 설명 (a_list[0]에서 추출)
  worker.logger           : YtLoggerBridge — raw 버스 직행 (log_full/log_concise 시그널 폐기)
  worker.current_url       : str   — 현재 처리 중인 URL
  worker.current_file      : str|None — 현재 다운로드 파일 경로
  worker.state             : dict  — canceled, skip 플래그 (UI→워커 단방향 쓰기)
  worker._speed_win        : SpeedWindow — 이동평균 속도
  worker.total_count / current_idx : int — 배치 진행 현황
  worker.is_live_hint      : bool — 라이브 스트림 힌트
  worker.live_partially_saved : bool — 라이브 부분 저장 플래그
──────────────────────────────────────────────────────────────────
"""
import functools
import os
import re

import yt_dlp

from chzzk_api import analyze_chzzk_clip_api, analyze_chzzk_vod_api
from utils import get_filename_template
from dl_platform import detect_content_type
from client_opts import (
    _apply_client_opts,
    _apply_cookie_opts,
    _apply_ejs_opts,
    _apply_ffmpeg_opts,
    _apply_light_analysis_opts,
    _apply_pot_opts,
)
from log_console import emit_err as _emit_err
import raw_log
import progress_emitter as _pe
import live_recorder as _lr


def _make_ytdl_opts(ctx, fmt, url):
    """yt-dlp 다운로드 옵션 — outtmpl/훅/병합/쿠키/player_client 주입."""
    opts = {
        "logger": ctx.logger,
        "noplaylist": True,
        # [Thin Wrapper 제거 후속] progress hook은 모듈 함수(ctx 선결 바인딩)
        "progress_hooks": [functools.partial(_pe.hook, ctx)],
        "outtmpl": os.path.join(
            ctx.cfg.get("download_path") or ".",
            get_filename_template(ctx.cfg),
        ),
        "format": fmt,
        "merge_output_format": ctx.cfg.get("container", "mp4"),
        "retries": 3,
        "socket_timeout": 30,
        # [0% 스톨 픽스] PO 토큰 불일치 시 googlevideo가 "묵살 스로틀"
        # (연결 수락 + 데이터 거의 안 보냄) → speed < 50KB/s 3초 지속되면
        # yt-dlp가 ThrottledDownload raise → 재추출+재시도.
        # [주의] dest가 throttledratelimit (camelCase 아님, yt-dlp 옵션 표준)
        # 100KB/s → 50KB/s로 완화: 초기 버퍼링 구간에서 오탐 방지
        "throttledratelimit": 50_000,
    }
    if ctx.cfg.get("fast_download"):
        opts["concurrent_fragment_downloads"] = 4
    _apply_cookie_opts(opts, ctx.cfg)
    _apply_client_opts(opts, ctx.cfg, forced=ctx.yt_client)
    _apply_ejs_opts(opts)
    _apply_pot_opts(opts, _extract_yt_id(url),
                    client=(ctx.yt_client if ctx.yt_client != "auto" else "web_embedded"))
    _apply_ffmpeg_opts(opts)
    return opts


def _extract_yt_id(url):
    """YouTube URL에서 video ID 추출 (PO 토큰 content_binding용)."""
    from po_client import extract_video_id
    return extract_video_id(url)


def _format_selector(ctx):
    """yt-dlp format 선택 문자열 — 자동(해상도 제한 내 최고)/포맷 직접 고르기 대응."""
    if ctx.cfg.get("audio_only"):
        return "bestaudio/best"

    # [포맷 직접 고르기] 분석 목록에서 사용자가 선택한 format_id 우선
    v_id = str(ctx.v_sel or "").strip()
    a_id = str(ctx.a_sel or "").strip()
    if v_id and v_id != "auto":
        if a_id and a_id != "auto":
            return f"{v_id}+{a_id}"
        return f"{v_id}+bestaudio"

    # [자동 경로] 해상도 제한 내 최고 품질
    res = str(ctx.cfg.get("max_video_res") or "none").strip()
    if res.isdigit():
        return f"bv*[height<={res}]+ba/b"
    return "bv*+ba/b"  # 기본 최고 품질 (명시/통합 동일)


def _http_download(ctx, url, out_path):
    """치지직 progressive MP4 직접 스트림 다운로드 + 진행률 틱."""
    import urllib.request

    ctx.speed_win.reset()
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as resp, open(out_path, "wb") as f:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = resp.read(262144)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            ctx.speed_win.add(done)
    return out_path


def _download_chzzk(ctx, url, content_type):
    """치지직 클립/VOD — API 포맷의 progressive MP4 직접 스트림 다운로드."""
    ch_info = (
        analyze_chzzk_clip_api(url)
        if content_type == "clip"
        else analyze_chzzk_vod_api(url)
    )
    formats = ch_info.get("formats") or []
    if not formats:
        raise RuntimeError("chzzk stream fail (cookie)")
    fmt = formats[0]  # 최고 품질 우선 (API 가 정렬)
    stream_url = fmt.get("url") or ""
    if not stream_url:
        raise RuntimeError("chzzk URL missing")

    if not ctx._meta_logged:
        _pe.emit_chzzk_header(ctx, ch_info, fmt)

    out_path = os.path.join(
        ctx.cfg["download_path"], _chzzk_filename(ch_info, fmt, ctx.cfg)
    )
    real = _http_download(ctx, stream_url, out_path)
    _pe.log_success_info(ctx, real)
    ctx.speed_win.reset()
    return True


def _download_youtube_live(ctx, url):
    """유튜브 라이브 — ffmpeg 녹화 파이프라인 (live_recorder)."""
    return _lr.download_youtube_live(ctx, url)


def _download_streamlink(ctx, url):
    """streamlink 대상 — 자식 프로세스 녹화 파이프라인."""
    out_file = os.path.join(
        ctx.cfg["download_path"], "streamlink_live.mp4"
    )
    temp_ts, thumb, _ = _lr.prepare_live_paths(ctx, out_file, None)
    cmd = ["streamlink", url, "best", "-O"]
    return _lr.record_live_stream(ctx, cmd, temp_ts, out_file, thumb)


def _download_vod(ctx, url):
    """유튜브 VOD — yt-dlp 다운로드 (progress_hook → hook/틱)."""
    fmt = _format_selector(ctx)
    opts = _make_ytdl_opts(ctx, fmt, url)
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
    if not info:
        raise RuntimeError("info extract fail")

    if not ctx._meta_logged:
        _pe.emit_download_header(ctx, info)

    # 병합(chzzk 무관) 후 실제 산출 파일 완료 로그
    for dl in info.get("requested_downloads") or []:
        _pe.log_success_info(
            ctx,
            dl.get("filepath") or dl.get("_filename") or ""
        )
        
    ctx.speed_win.reset()
    return True


def _emit_error_log(ctx, url, reason, failed_targets):
    """에러 로그 출력 및 실패 목록에 추가. (버스 단일 경유)"""
    url_short = url[:40] + ("..." if len(url) > 40 else "")
    raw_log.raw("dl", _emit_err(f"{url_short} — {reason}"), to_tui=True)
    failed_targets.append((url, reason))


def _is_youtube_live_url(ctx, url):
    """유튜브 URL이 라이브인지 경량 프리체크 (yt-dlp extract_info 사용).

    배치(txt) 입력 시 is_live_hint가 없어 VOD 경로로 가는 문제를 해결하기 위해
    다운로드 전에 스트림 정보만 추출하여 is_live 여부를 확인한다.
    """
    try:
        opts = {
            "logger": ctx.logger,
            "noplaylist": True,
            "skip_download": True,
            "extract_flat": False,
        }
        _apply_cookie_opts(opts, ctx.cfg)
        _apply_client_opts(opts, ctx.cfg, forced=ctx.yt_client)
        _apply_light_analysis_opts(opts)
        _apply_ejs_opts(opts)
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return bool(info and info.get("is_live"))
    except Exception:
        return False


def download_target(ctx, url, failed_targets):
    """개별 URL 다운로드 — 콘텐츠 타입 분기 및 정밀한 예외 식별."""
    try:
        ct = detect_content_type(url)
        if ct in ("clip", "vod"):
            return _download_chzzk(ctx, url, ct)
        if ct == "live":
            return _download_youtube_live(ctx, url)
        if ct == "stream":
            return _download_streamlink(ctx, url)
        # youtube video — 라이브 힌트가 있거나 경량 프리체크로 라이브 확인 시 라이브 분기로
        if ctx.is_live_hint or _is_youtube_live_url(ctx, url):
            return _download_youtube_live(ctx, url)
        return _download_vod(ctx, url)

    except yt_dlp.utils.DownloadError as de:
        # [MSG 태그 규격 §1.1-4] 오류 사유는 1~3단어 소문자 영문 CLI 태그.
        # 원문 detail은 _emit_error_log가 상세(F12)로 남긴다.
        err_str = str(de).lower()
        if "challenge solving failed" in err_str or "sign in" in err_str or "the page needs to be reloaded" in err_str:
            reason = "age/bot restricted"
        elif "requested format not available" in err_str:
            reason = "format missing"
        elif "video unavailable" in err_str or "this video is not available" in err_str:
            reason = "video unavailable"
        elif "private video" in err_str:
            reason = "video private"
        else:
            reason = f"download blocked ({str(de)[:60]})"
        _emit_error_log(ctx, url, reason, failed_targets)
        return False

    except KeyError as ke:
        # 치지직 JSON 구조 변경 등 데이터 파싱 오류
        reason = f"parse error ({ke})"
        _emit_error_log(ctx, url, reason, failed_targets)
        return False

    except (ConnectionError, TimeoutError, OSError) as net_ex:
        # 네트워크 계열 오류 세분화
        reason = f"network error ({type(net_ex).__name__})"
        _emit_error_log(ctx, url, reason, failed_targets)
        return False

    except Exception as ex:
        # 최후의 범용 에러 캐치
        reason = f"unknown error ({type(ex).__name__}: {str(ex)[:50]})"
        _emit_error_log(ctx, url, reason, failed_targets)
        return False


# ── 대상 평탄화 ────────────────────────────────────────────────────────────


def _flatten(ctx, url):
    """yt-dlp extract_flat 으로 재생목록/채널 항목 URL 집합."""
    opts = {
        "logger": ctx.logger,
        "extract_flat": True,
        "skip_download": True,
    }
    _apply_cookie_opts(opts, ctx.cfg)
    _apply_client_opts(opts, ctx.cfg, forced=ctx.yt_client)
    _apply_light_analysis_opts(opts)
    _apply_ejs_opts(opts)
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    entries = info.get("entries") or []
    urls = []
    for e in entries:
        if not e:
            continue
        u = e.get("url") or e.get("webpage_url")
        if u:
            urls.append(u)
    return urls


def expand_targets(ctx):
    """재생목록/채널 URL 을 개별 동영상 URL 로 펼친다."""
    expanded = []
    for url in ctx.targets:
        try:
            urls = None
            if detect_content_type(url) == "playlist":
                urls = _flatten(ctx, url)
            else:
                u = url.lower()
                if "/@" in u or "/channel/" in u or "/c/" in u:
                    from playlist import normalize_youtube_channel_url

                    urls = _flatten(ctx, normalize_youtube_channel_url(url))
            expanded.extend(urls or [url])
        except Exception as ex:
            url_short = url[:40] + ("..." if len(url) > 40 else "")
            raw_log.raw("dl", _emit_err(f"{url_short} — {str(ex)}"), to_tui=True)
    return expanded or ctx.targets
```

## File: theme.py

```python
### theme.py - TUI-inspired fzf 스타일 테마 (Dark Terminal Palette)
""" UI 스킨 문자열은 이 모듈에서만 정의한다. main.py / dialogs.py / log_console.py 는 여기서 임포트해 사용한다. """

### 색상 팔레트 (fzf-inspired dark terminal)
BG_WINDOW = "#0d0d0d"        # 메인/다이얼로그 콘솔 톤
BG_SURFACE = "#252525"       # 패널 배경
BG_CONSOLE = "#0d0d0d"       # 콘솔 배경
BG_HOVER = "#2a2a2a"         # 호버 배경
FG_TEXT = "#e3e3e3"          # 기본 전경
FG_DIM = "#888888"           # 딤 텍스트
BORDER = "#444444"           # 테두리
ACCENT = "#4ec9b0"           # 액센트 (청록)
ACCENT_ALT = "#ce9178"       # 보조 액센트 (주황)
ERROR = "#e06c75"            # 에러 레드 (soft pastel — Atom One Dark)
WARN = "#e5c07b"             # 경고 옐로
SUCCESS = "#6a9955"          # 성공 그린

### MainWindow 전역 스타일 (fzf border-line aesthetic)
MAIN_WINDOW_QSS = f"""
QMainWindow, QDialog {{ background-color: {BG_WINDOW}; color: {FG_TEXT}; font-family: 'Cascadia Mono', monospace; font-size: 11px; }}
QLabel {{ color: {FG_TEXT}; font-family: 'Cascadia Mono', monospace; }}
QPushButton {{ background-color: {BG_SURFACE}; color: {FG_TEXT}; border: 1px solid {BORDER}; border-radius: 0px; padding: 4px 12px; font-family: 'Cascadia Mono', monospace; font-size: 11px; }}
QPushButton:hover {{ background-color: {BG_HOVER}; border-color: {ACCENT}; }}
QPushButton:pressed {{ background-color: #333333; }}
QPushButton:disabled {{ background-color: #1a1a1a; color: #555555; border-color: #333333; }}
QLineEdit {{ background-color: {BG_SURFACE}; color: {FG_TEXT}; border: 1px solid {BORDER}; border-radius: 0px; padding: 6px 10px; font-family: 'Cascadia Mono', monospace; font-size: 11px; }}
QLineEdit:focus {{ border: 1px solid {ACCENT}; }}
QProgressBar {{ text-align: center; border: none; background-color: {BG_SURFACE}; height: 4px; color: transparent; }}
QProgressBar::chunk {{ background-color: {ACCENT}; }}
QScrollBar:vertical {{ border: none; background: transparent; width: 6px; }}
QScrollBar::handle:vertical {{ background: {BORDER}; min-height: 20px; border-radius: 0px; }}
QScrollBar::handle:vertical:hover {{ background: #555555; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
QListWidget {{ background-color: {BG_CONSOLE}; color: {FG_TEXT}; border: 1px solid {BORDER}; border-radius: 0px; font-family: 'Cascadia Mono', monospace; font-size: 11px; outline: none; }}
QListWidget::item {{ padding: 3px 6px; border: none; }}
QListWidget::item:hover {{ background-color: {BG_HOVER}; }}
QListWidget::item:selected {{ background-color: #1d3a34; color: {ACCENT}; }}
QSplitter::handle {{ background-color: {BORDER}; }}
"""

### fzf-style 보더 프레임 (타이틀을 보더 위 중앙 배치)
def groupbox_qss(title=""):
    """fzf-style QGroupBox — 타이틀을 보더 위 중앙에 배치."""
    return f"""
QGroupBox {{
    border: 1px solid {BORDER};
    border-radius: 0px;
    margin-top: 8px;
    padding-top: 12px;
    font-family: 'Cascadia Mono', monospace;
    font-size: 11px;
    color: {FG_DIM};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top center;
    padding: 0 6px;
    background-color: {BG_WINDOW};
    color: {ACCENT};
}}
"""

FRAME_QSS = f"""
QFrame {{
    border: 1px solid {BORDER};
    border-radius: 0px;
    background-color: {BG_SURFACE};
}}
"""
### 콘솔 로그 영역
CONSOLE_LOG_QSS = f"""
QTextEdit {{
    background-color: {BG_CONSOLE};
    color: {FG_TEXT};
    border: 1px solid {BORDER};
    border-radius: 0px;
    font-family: 'Cascadia Mono', monospace;
    font-size: 11px;
    padding: 4px;
}}
QScrollBar:vertical {{ border: none; background: transparent; width: 6px; }}
QScrollBar::handle:vertical {{ background: {BORDER}; min-height: 20px; border-radius: 0px; }}
QScrollBar::handle:vertical:hover {{ background: #555555; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
"""

### 간결 로그 색 위계
LOG_COLOR_SUCCESS = SUCCESS
LOG_COLOR_ERROR = ERROR
LOG_COLOR_WARN = WARN
LOG_COLOR_INFO = "#b0b6bc"   # 회백 — 정보성 헤더
LOG_COLOR_STRUCT = "#5f6a72"  # 트리 글리프·라벨 (딤 그레이)
LOG_COLOR_VALUE = "#e8eaed"   # 트리 값·일반 텍스트
LOG_COLOR_DIM = FG_DIM
LOG_COLOR_ACCENT = ACCENT
LOG_COLOR_ACCENT_ALT = ACCENT_ALT

### 버튼 QSS — 새 팔레트 단일 출처
BTN_ACTION_QSS = f"""QPushButton {{ background-color: {BG_SURFACE}; color: {ACCENT}; border: 1px solid {ACCENT}; border-radius: 0px; padding: 6px 16px; font-family: 'Cascadia Mono', monospace; font-size: 11px; }}
QPushButton:hover {{ background-color: #2a3a35; }}
QPushButton:pressed {{ background-color: #1a2a25; }}
QPushButton:disabled {{ background-color: #1a1a1a; color: #555555; border-color: #333333; }}
"""

BTN_DANGER_QSS = f"""QPushButton {{ background-color: {BG_SURFACE}; color: {ERROR}; border: 1px solid {ERROR}; border-radius: 0px; padding: 6px 16px; font-family: 'Cascadia Mono', monospace; font-size: 11px; }}
QPushButton:hover {{ background-color: #3a2525; }}
QPushButton:pressed {{ background-color: #2a1515; }}
QPushButton:disabled {{ background-color: #1a1a1a; color: #555555; border-color: #333333; }}
"""

BTN_NEUTRAL_QSS = f"""QPushButton {{ background-color: {BG_SURFACE}; color: {FG_TEXT}; border: 1px solid {BORDER}; border-radius: 0px; padding: 6px 16px; font-family: 'Cascadia Mono', monospace; font-size: 11px; }}
QPushButton:hover {{ background-color: {BG_HOVER}; }}
QPushButton:disabled {{ background-color: #1a1a1a; color: #555555; border-color: #333333; }}
"""
### 다이얼로그 QSS
MSGBOX_QSS = f"""
QMessageBox {{ background-color: {BG_WINDOW}; }}
QLabel {{ color: {FG_TEXT}; font-size: 12px; font-family: 'Cascadia Mono', monospace; padding: 8px 16px; }}
QPushButton {{ background-color: {BG_SURFACE}; color: {FG_TEXT}; border: 1px solid {BORDER}; border-radius: 0px; padding: 6px 16px; font-family: 'Cascadia Mono', monospace; min-width: 70px; }}
QPushButton:hover {{ background-color: {BG_HOVER}; border-color: {ACCENT}; }}
QTextEdit {{ background-color: {BG_CONSOLE}; color: {FG_TEXT}; border: 1px solid {BORDER}; border-radius: 0px; font-family: 'Cascadia Mono', monospace; font-size: 11px; padding: 4px; }}
"""

### 설정 다이얼로그 — 모던 TUI 패널
SETTINGS_TUI_QSS = """
QGroupBox.tui-panel {
    border: 1px solid #2a2a2a;
    border-radius: 6px;
    margin-top: 10px;
    padding: 8px;
    background-color: #0d0d0d;
}
QGroupBox.tui-panel::title {
    subcontrol-origin: margin;
    subcontrol-position: top center;
    padding: 0 8px;
    background-color: #0d0d0d;
    color: #4ec9b0;
    font-size: 11px;
    font-weight: bold;
}
QLabel { color: #cccccc; font-size: 11px; }
QCheckBox { color: #d4d4d4; spacing: 6px; }
QCheckBox::indicator {
    width: 14px; height: 14px;
    border: 1px solid #2a2a2a;
    background: #161616;
    border-radius: 2px;
}
QCheckBox::indicator:checked {
    background: #4ec9b0;
    border-color: #4ec9b0;
}
QPushButton {
    background: #161616;
    color: #d4d4d4;
    border: 1px solid #2a2a2a;
    padding: 4px 12px;
    font-size: 11px;
}
QPushButton:hover {
    border-color: #4ec9b0;
    color: #4ec9b0;
}
"""

DIALOG_BG_QSS = f"background-color: {BG_WINDOW}; color: {FG_TEXT}; font-family: 'Cascadia Mono', monospace;"
TE_CONTENT_QSS = CONSOLE_LOG_QSS

DLG_SECTION_TITLE_QSS = f"font-weight: bold; font-size: 12px; border: none; background: transparent; color: {ACCENT}; font-family: 'Cascadia Mono', monospace;"
DLG_STATUS_QSS = f"color: {FG_DIM}; font-size: 11px; border: none; background: transparent; font-family: 'Cascadia Mono', monospace;"
DLG_GHOST_BTN_QSS = f"""
QPushButton {{ background-color: {BG_SURFACE}; color: {FG_TEXT}; border: 1px solid {BORDER}; border-radius: 0px; padding: 4px 10px; font-size: 11px; font-family: 'Cascadia Mono', monospace; }}
QPushButton:hover {{ background-color: {BG_HOVER}; border-color: {ACCENT}; }}
QPushButton:disabled {{ background-color: #1a1a1a; color: #555555; border-color: #333333; }}
"""

SETTINGS_SCROLL_QSS = f"""
QScrollArea {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 6px; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 0px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: #555555; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
"""

### MainWindow TUI 스타일 (Hyper-Minimal Modern TUI — flat, borderless, mono)
### ──────────────────────────────────────────────────────────────
TUI_STYLE = """
/* Core Dark Palette & Monospace Typography — Cascadia Mono unified */
QWidget, QMainWindow {
    background-color: #0d0d0d;
    color: #cccccc;
    font-family: 'Cascadia Mono', monospace;
    font-size: 11px;
}

/* ── Flat Panels: no border, no radius ── */
QGroupBox.tui-panel {
    border: none;
    border-radius: 0px;
    margin-top: 0px;
    padding: 8px 0px 8px 0px;
    background-color: #0d0d0d;
}

QGroupBox.tui-panel::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0px;
    background-color: transparent;
    color: transparent;
    font-size: 1px;
}

/* ── Section separators (1px subtle lines) ── */
QFrame.tui-separator {
    background-color: #1a1a1a;
    max-height: 1px;
    min-height: 1px;
    border: none;
}

QPushButton[class="tui-tag"] {
    background-color: transparent;
    border: none;
    color: #ce9178;
    font-family: 'Cascadia Mono', monospace;
    font-size: 11px;
    padding: 2px 6px;
}

QPushButton[class="tui-tag"]:hover {
    color: #ffffff;
    background-color: #252526;
    border-radius: 3px;
}

QPushButton[class="tui-tag"]:pressed {
    color: #4ec9b0;
}

/* ── URL Input: flat underline style ── */
QLineEdit#url_input::placeholder { color: #555555; }

QLineEdit#url_input {
    background-color: transparent;
    border: none;
    border-bottom: 1px solid #333333;
    color: #dcdcdc;
    font-family: 'Cascadia Mono', monospace;
    font-size: 11px;
    padding: 4px 0px 4px 0px;
    selection-background-color: #264f78;
}

QLineEdit#url_input:focus {
    border-bottom: 1px solid #4ec9b0;
}

QPlainTextEdit#console_log, QTextEdit#console_log {
    background-color: #0d0d0d;
    border: none;
    color: #d4d4d4;
    font-family: 'Cascadia Mono', monospace;
    font-size: 11px;
    line-height: 1.3;
}

QScrollBar:vertical {
    border: none;
    background: #121212;
    width: 6px;
}

QScrollBar::handle:vertical {
    background: #333333;
    border-radius: 3px;
    min-height: 20px;
}

QScrollBar::handle:vertical:hover {
    background: #555555;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
"""




### 호환 참조 (main.py / dialogs.py 가 참조하는 이름 — 새 팔레트로 연결)
BAR_PANEL_QSS = f"background-color: {BG_SURFACE}; border: 1px solid {BORDER}; border-radius: 0px;"
LBL_STREAM_QSS = f"color: {FG_DIM}; font-size: 11px; border: none; background: transparent; font-family: 'Cascadia Mono', monospace;"
LBL_META_QSS = f"color: {ACCENT_ALT}; font-size: 11px; border: none; background: transparent; font-family: 'Cascadia Mono', monospace;"
CONSOLE_INIT_QSS = CONSOLE_LOG_QSS

BTN_PRIMARY_QSS = BTN_ACTION_QSS        # 다운로드 시작 (액센트 아웃라인)
BTN_INFO_QSS = BTN_NEUTRAL_QSS          # 건너뛰기 (중립)
BTN_SETTINGS_FONT_QSS = BTN_NEUTRAL_QSS # 설정 (중립)
BTN_EXIT_DANGER_QSS = BTN_DANGER_QSS    # 종료 확인 (에러 아웃라인)
BTN_GRID_QSS = BTN_NEUTRAL_QSS          # 쿠키 소스 그리드
BTN_CLOSE_QSS = BTN_NEUTRAL_QSS         # 다이얼로그 닫기
```

## File: update_worker.py

```python
### update_worker.py - DEPS 체크/자동 업그레이드 워커
"""시작 시퀀스의 의존성 확인·수급을 담당하는 백그라운드 워커 (UpdateWorker).

- _do_check : updater.check_deps() 결과를 DEPS 이벤트로(TUI 5줄), CLI 원문을
  raw 문자열로(F12) 버스 단일 경유 전송. stale 패키지는 check_done(list)으로 반환.
- _do_upgrade: PyPI(yt-dlp/streamlink) + ffmpeg + node 순차 수급.
  각 수급의 실제 진행 여부를 _had_action 판별해 '요약 결론' 1줄만 남긴다.
- [분리] dialogs.py에서 추출 — 대화상자 컬렉션과 워커의 수명·계층이 다르다.
- [시그널 계약] check_done(list) → main._on_update_check_done,
  upgrade_done(bool,str) → StartupCoordinator.report_upgrade.
- [v3.3.0] 로그는 raw 버스(raw_log.raw) 단일 경유 — line/full 시그널 폐기.
"""
import os
import traceback

import updater
import raw_log
from log_event import LogEvent
from PySide6.QtCore import QThread, Signal
from log_console import emit_component

# CLI 원문 캡처 대상 — (label, args). _do_check에서 updater.cli_raw로 실행된다.
_RAW_VERSION_CMDS = (
    ("ytdlp", ("--version",)),
    ("streamlink", ("--version",)),
    ("ffmpeg", ("-version",)),
    ("node", ("--version",)),
    ("npm", ("--version",)),
)


class UpdateWorker(QThread):
    check_done = Signal(list)
    upgrade_done = Signal(bool, str)

    def __init__(self, parent=None, upgrade=False, stale_updates=None, channel='stable', check_updates=True):
        super().__init__(parent)
        self.upgrade = upgrade
        self.stale_updates = stale_updates or []
        self.channel = channel
        self.check_updates = check_updates

    def run(self):
        try:
            if self.upgrade:
                self._do_upgrade(self.stale_updates)
            else:
                self._do_check()
        except Exception as e:
            import traceback
            traceback.print_exc()
            raw_log.raw("deps", LogEvent(stage="SYS", status="FAIL", platform="deps",
                                         msg=f"worker crash: {e}", is_error=True), to_tui=True)
            self.check_done.emit([])

    def _do_check(self):
        """버전 확인 — 메인 콘솔(deps 상태 5줄) + F12(CLI 원문). 버스 단일 경유.

        [min profile] 메인 콘솔에는 상태 라인 5개 — fzf/lazygit 톤은 공백이 곧 정보.
        F12에는 실제 CLI를 실행해 셸에서 칠 때 보이는 원문 출력 그대로를
        적재한다. TUI 상태와 CLI 원문을 겹쳐 띄우지 않는다(교체 원칙).
        """
        stale = []
        # [단일 호출] check_deps 내부 pot_readiness에 log_func 직접 전달 —
        # 판정+로그 1회 (별도 호출 시 standby 2중 출력).
        for label, status, ver in updater.check_deps(
            log_func=lambda m: raw_log.raw(
                "pot-readiness",
                LogEvent(stage="POT", status="RUN", platform="pot", spec="-", msg=str(m)),
            )
        ):
            raw_log.raw("deps", emit_component("DEPS", status, label, ver), to_tui=True)
        # [raw] 실제 CLI 실행 — 터미널에서 직접 친 것과 동일한 원문을 F12에 기록.
        # ffmpeg -version 원문은 configuration: 1줄이 500자 — 6줄+160자 절단.
        for label, args in _RAW_VERSION_CMDS:
            cmdline, out = updater.cli_raw(label, *args, max_lines=6, max_width=160)
            if cmdline and out:
                raw_log.raw("deps-cli", f"$ {cmdline}")
                for line in out.splitlines():
                    raw_log.raw("deps-cli", line)
        # 수동 체크용 stale 생성 (outdated_packages) — 사용자 채널 반영.
        # auto_update_check off 면 PyPI 폴링 스킵 (stale 미생성 → upgrade 워커는 수급만)
        if self.check_updates:
            for label, pypi_name, cur, latest in updater.outdated_packages(channel=self.channel):
                stale.append((label, pypi_name, cur, latest))
                raw_log.raw("pypi", f"[stale] {label} {cur} → {latest}")
        else:
            raw_log.raw("pypi", "pypi update check: disabled (auto_update_check=off)")
        self.check_done.emit(stale)

    def _provision_cb(self, msg, is_status=False, is_error=False):
        """설치/수급 진행 로그 — F12는 항상 원문, TUI는 상태/진행만 (버스 단일 경유).

        components/node_provider의 콜백은 LogEvent(emit_component 빌더) 또는
        문자열을 넘긴다 — 둘 다 LogEvent로 정규화해 버스로 보낸다.
        is_status=True면 TUI에서도 마지막 줄을 덮어써 설치 진행률이 한 줄로 갱신된다.
        """
        if isinstance(msg, LogEvent):
            event = msg
            if is_status:
                event.is_status = True
            if is_error:
                event.is_error = True
        else:
            event = LogEvent(
                stage="DEPS",
                status="FAIL" if is_error else ("RUN" if is_status else "OK"),
                platform="deps", msg=str(msg),
                is_status=is_status, is_error=is_error,
            )
        show = bool(event.is_status or event.is_error
                    or event.status in ("FAIL", "WARN", "ABORT"))
        raw_log.raw("deps", event, to_tui=show)

    @staticmethod
    def _had_action(tui_line):
        """실제 수급 작업(다운로드/설치/추출 등)이 있었는지 — RUN 진행 동사 판별."""
        from log_event import LogEvent
        text = tui_line.msg if isinstance(tui_line, LogEvent) else str(tui_line)
        verb = ("downloading", "fetching", "installing", "extracting",
                "reinstalling", "reconfiguring", "brew install")
        return any(v in text.lower() for v in verb)

    def _do_upgrade(self, stale_updates=None):
        import components
        import pot_provider
        ok_overall = True
        summaries = []

        # 1. PyPI packages (yt-dlp, streamlink) — stale로 확인된 것만
        stale_updates = stale_updates or []
        if stale_updates:
            for _label, name, cur, latest in stale_updates:
                raw_log.raw("pypi", f"[stale] {name}: {cur} → {latest}")
            pypi_names = [p[1] for p in stale_updates]
            code, tail = updater.upgrade_packages(pypi_names, channel=self.channel)
            for l in tail.splitlines():
                if l.strip():
                    # raw 출력(pip/다운로드)은 F12 원문으로 — TUI 콘솔 오염 방지
                    raw_log.raw("pip", l.strip())
            if code != 0:
                ok_overall = False
                summaries.append(f"pypi ({', '.join(pypi_names)}) failed")
            else:
                summaries.append(f"{', '.join(pypi_names)} updated")
        else:
            raw_log.raw("pypi", "pypi: all up-to-date")

        # 2. ffmpeg auto-provisioning — 실제 수급이 없으면 간결 무표기
        ffmpeg_acted = [False]
        def _ffmpeg_cb(msg, is_status=False, is_error=False, *a):
            if self._had_action(msg):
                ffmpeg_acted[0] = True
            self._provision_cb(msg, is_status, is_error)

        ff_err = components.ensure_ffmpeg(_ffmpeg_cb)
        if ff_err:
            ok_overall = False
            summaries.append(f"ffmpeg: {ff_err}")
            raw_log.raw("deps", emit_component("DEPS", "FAIL", "ffmpeg", ff_err, is_error=True),
                        to_tui=True)
        elif ffmpeg_acted[0]:
            summaries.append("ffmpeg provisioned")
        else:
            raw_log.raw("ffmpeg", "ffmpeg: ok (no action needed)")

        # 3. node auto-provisioning (POT server runtime)
        node_acted = [False]
        def _node_cb(msg, is_status=True, is_error=False):
            if self._had_action(msg):
                node_acted[0] = True
            # [버스 단일 경유] TUI 틱(갱신형) + F12 원문 — emit_component 재포장 폐기
            if isinstance(msg, LogEvent):
                raw_log.raw("deps", msg, to_tui=True)
            else:
                raw_log.raw(
                    "deps",
                    LogEvent(stage="DEPS", status="RUN", platform="node", msg=str(msg),
                             is_status=is_status, is_error=is_error),
                    to_tui=True,
                )

        try:
            node_ok = pot_provider.ensure_node_runtime(_node_cb)
            if node_ok:
                if node_acted[0]:
                    summaries.append("node provisioned")
                else:
                    raw_log.raw("node", "node: ok (no action needed)")
            else:
                ok_overall = False
                summaries.append("node setup failed")
                raw_log.raw("deps", emit_component("DEPS", "FAIL", "node", "setup failed", is_error=True),
                            to_tui=True)
        except Exception as e:
            ok_overall = False
            summaries.append(f"node: {e}")
            raw_log.raw("deps", emit_component("DEPS", "FAIL", "node", str(e), is_error=True),
                        to_tui=True)

        summary = "; ".join(summaries) if summaries else ""
        self.upgrade_done.emit(ok_overall, summary)
```

## File: updater.py

```python
##### updater.py - pip component (yt-dlp / streamlink) version check and update helper
"""PyPI metadata query for latest versions, optional pip upgrade on demand.
*  Version check: PyPI JSON API (lightweight, no pip needed)
*  Upgrade:
    - Stable channel: python -m pip install -U <pkg>
    - Nightly channel: python -m pip install -U yt-dlp-nightly (yt-dlp only)
*  frozen(PyInstaller) builds — pip이 없으므로 직접 다운로드:
    - yt-dlp: PyPI/GitHub release에서 yt-dlp.exe 다운로드 후 교체
    - streamlink: PyPI에서 whl 다운로드 후 importlib로 설치
    - 업데이트 실패 시 기존 버전 유지, 다음 실행 시 재시도
*  네트워크 의존은 이 앱에서 본질적이다 (웹 미디어 추출기). """
import concurrent.futures
import importlib.metadata as im
import json
import os
import shutil
import subprocess
import sys
import tempfile
import socket
import urllib.request

# (log_label, pypi_name, pypi_nightly) — log_label is shown in the DEPS PLATFORM column
# pypi_nightly: Nightly 채널 사용 시 설치할 PyPI 패키지명 (None이면 Stable only)
# [전환] bgutil-ytdlp-pot-provider 제외: 플러그인(pip)에서 독립 Node 서버로
# 이동 — 버전 관리 주체는 pot_provider(latest_server_ver)가 담당.
PACKAGES = [("ytdlp", "yt-dlp", "yt-dlp-nightly"), ("streamlink", "streamlink", None)]
# [주의] socket.setdefaulttimeout() 절대 사용 금지 — 프로세스 전체의 소켓 기본
# 타임아웃을 오염시켜 yt-dlp 미디어 스트림 재시도 루프(0.0% 스톨)를 유발.
# DNS hang 방어는 아래 latest_version의 ThreadPoolExecutor + urlopen(timeout)으로 충분.

_PYPI_API = "https://pypi.org/pypi/{pkg}/json"
_NIGHTLY_API = "https://github.com/yt-dlp/yt-dlp-nightly-builds/releases/latest/download/yt-dlp{_ext}"

def installed_version(pypi_name):
    """Installed version string, or None if not installed / failure."""
    try:
        return im.version(pypi_name)
    except Exception:
        return None

def latest_version(pypi_name, timeout=1.5):
    """Latest stable version from PyPI, or None on failure.

    [v3.1.0 변경] 타임아웃 2초→1.5초로 단축. DEPS 로그 표시 시간을
    줄이기 위해. PyPI JSON API는 충분히 빠르므로 1.5초면 충분.
    ThreadPoolExecutor는 DNS 레벨까지 카운트다운하므로 urlopen timeout
    보다 0.5초만 버퍼로 부여.

    [DNS hang defence] socket.setdefaulttimeout does not cover getaddrinfo;
    ThreadPoolExecutor + future.result cuts at DNS level too.
    """
    def _fetch():
        with urllib.request.urlopen(_PYPI_API.format(pkg=pypi_name), timeout=timeout) as resp:
            return json.load(resp)
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(_fetch)
            data = fut.result(timeout=timeout + 0.5)
            return (data.get("info") or {}).get("version")
    except Exception:
        return None

def _ver_tuple(version):
    """'2026.8.19' -> (2026, 8, 19) comparable tuple (non-digit chars dropped)."""
    parts = []
    for p in str(version).split("."):
        digits = "".join(ch for ch in p if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)

def is_outdated(current, latest):
    """True if latest > current (numeric tuple compare avoids string pitfalls)."""
    try:
        return _ver_tuple(latest) > _ver_tuple(current)
    except Exception:
        return False

def outdated_packages(channel="stable"):
    """List of (label, pypi_name, cur, latest) needing update or not installed.
    channel: stable / nightly (yt-dlp-nightly / GitHub builds).

    [downgrade support] stable channel with yt-dlp-nightly installed (user
    switched Nightly->Stable): force stale target=stable -- nightly version
    string compares higher so plain version check would be never-stale.
    """
    stale = []
    for label, pypi_name, pypi_nightly in PACKAGES:
        if channel == "nightly" and pypi_nightly:
            cur = installed_version(pypi_nightly) or installed_version(pypi_name)
            latest = latest_version(pypi_nightly)
            if not cur:
                stale.append((label, pypi_name, "not installed", latest or "unknown"))
            elif latest and is_outdated(cur, latest):
                stale.append((label, pypi_name, cur, latest))
            continue
        # stable channel: leftover nightly -> downgrade target
        if pypi_nightly and installed_version(pypi_nightly):
            stale.append((label, pypi_name, str(installed_version(pypi_nightly)) + " (nightly)", "stable"))
            continue
        cur = installed_version(pypi_name)
        latest = latest_version(pypi_name)
        if not cur:
            stale.append((label, pypi_name, "not installed", latest or "unknown"))
        elif latest and is_outdated(cur, latest):
            stale.append((label, pypi_name, cur, latest))
    return stale


def check_deps(log_func=None):
    """모든 의존성 체크 결과 리스트 반환.
    각 요소: (label, status, version_or_path)
    status: 표준 status (OK / FAIL 등) — `format_log_line`의 표준 사용.
    log_func(msg): POT readiness 판정 근거를 raw 스택으로 반환 (단일 호출).
    """
    import os
    import shutil
    results = []

    # 1. PyPI 패키지 (yt-dlp, streamlink) — nightly 채널 설치물 인지
    #    yt-dlp-nightly 는 dist 명이 달라 im.version("yt-dlp") 가 실패하므로
    #    nightly 설치물로 폴백 표기 (정상 설치 판정 유지)
    for label, pypi_name, pypi_nightly in PACKAGES:
        ver = installed_version(pypi_name)
        if not ver and pypi_nightly:
            nver = installed_version(pypi_nightly)
            if nver:
                ver = f"{nver} (nightly)"
        results.append((label, "OK" if ver else "FAIL", ver or "not installed"))

    # 2. 외부 실행 파일 (ffmpeg, node) — msg에는 버전/경로 같은 실질 정보만
    for label in ("ffmpeg", "node"):
        path = shutil.which(label)
        if not path and label == "node":
            # [포터블 폴백] 시스템 PATH 밖의 로컬 포터블 node (writable_base/node)도
            # DEPS 후보 — 없을 때만 'not found'.
            try:
                import pot_provider
                path = pot_provider.node_exe()
            except Exception:
                path = None
        if path:
            if label == "node":
                try:
                    import pot_provider
                    maj = pot_provider.node_major_version(path)
                except Exception:
                    maj = None
                msg = f"v{maj}" if maj else os.path.basename(path)
            elif label == "ffmpeg":
                msg = _ffmpeg_version(path) or os.path.basename(path)
            results.append((label, "OK", msg))
        else:
            # [v3.1.0 정책] 표준 status 사용. msg는 명시적 문자열.
            results.append((label, "FAIL", "not found"))

    # 3. PO token 서버 — [Lazy 2층 분리] liveness가 아니라 readiness.
    # 바이너리+빌드 산출물의 디스크 준비만 판정 (RAM 0MB·포트 미점유).
    # Popen은 분석 게이트(_ensure_pot_for_info)까지 지연. FAIL 오경보 금지:
    # 미기동 정상 상태는 SKIP standby, 산출물 미비는 SKIP + 사유.
    # [단일 호출] log_func 콜백을 내부 pot_readiness에 직접 전달 — 판정+로그
    # 1회로 해결 (별도 _pot_readiness 호출 시 standby 2중 출력 결함).
    try:
        from po_client import server_ping
        from pot_server import pot_readiness
        if server_ping():
            results.append(("pot", "OK", "running"))
        else:
            ready, reason = pot_readiness(log_func=log_func)
            if ready:
                results.append(("pot", "SKIP", "standby"))
            else:
                results.append(("pot", "SKIP", reason))
    except Exception:
        results.append(("pot", "SKIP", "unknown"))

    return results

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _cli_base(label):
    """라벨 → 실제 CLI 명령 배열 (없으면 None). F12 상세 로그용 원문 실행.

    importlib.metadata/shutil.which 로 대체하지 않는 이유: '터미널에서 직접
    쳤을 때 보이는 원문 출력'을 있는 그대로 남기는 것이 목적이므로, 판별이
    아닌 실제 실행이 필요하다.
    """
    if label == "ytdlp":
        if getattr(sys, "frozen", False):
            p = shutil.which("yt-dlp") or shutil.which("yt-dlp.exe")
            return [p] if p else None
        # dev: 앱이 실제로 쓰는 venv 파이썬으로 실행 (PATH 무관)
        return [sys.executable, "-m", "yt_dlp"]
    if label == "streamlink":
        if getattr(sys, "frozen", False):
            p = shutil.which("streamlink")
            return [p] if p else None
        return [sys.executable, "-m", "streamlink"]
    if label == "ffmpeg":
        p = shutil.which("ffmpeg")
        if not p:
            try:
                from components import ffmpeg_exe
                p = ffmpeg_exe()
            except Exception:
                p = None
        return [p] if p else None
    if label == "node":
        try:
            import pot_provider
            p = pot_provider.node_exe()
        except Exception:
            p = None
        p = p or shutil.which("node")
        return [p] if p else None
    if label == "npm":
        try:
            import pot_provider
            p = pot_provider.npm_exe()
        except Exception:
            p = None
        p = p or shutil.which("npm")
        return [p] if p else None
    return None


def _cli_env(label):
    """npm 시스 스크립트가 'env node'로 node를 찾도록 PATH 보강 (npm만)."""
    if label != "npm":
        return None
    try:
        import pot_provider
        node = pot_provider.node_exe()
    except Exception:
        node = None
    if not node:
        return None
    env = os.environ.copy()
    ndir = os.path.dirname(node)
    env["PATH"] = ndir + os.pathsep + env.get("PATH", "")
    return env


def cli_raw(label, *args, timeout=15, max_lines=0, max_width=160):
    """실제 CLI를 실행해 '터미널에서 친 것과 동일한 원문 출력'을 반환.

    반환: (cmdline, output) — 도구 없으면 (None, None), 실행 예외면
    (cmdline, "[Type] msg"). 출력은 stdout+stderr 합본 원문.
    호출부(F12 상세 로그)가 '$ <cmd>' + 원문 라인을 그대로 적재한다.
    max_lines>0 → 앞 N줄만 + '… (M lines truncated)' 꼬리.
    over-long 단일 줄은 max_width로 절단 (ffmpeg configuration: 대책).
    """
    cmd = _cli_base(label)
    if not cmd:
        return None, None
    full_cmd = cmd + list(args)
    env = _cli_env(label)
    try:
        proc = subprocess.run(
            full_cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=env,
            creationflags=_NO_WINDOW if os.name == "nt" else 0,
        )
    except Exception as e:
        return " ".join(full_cmd), f"[{type(e).__name__}] {e}"
    out = ((proc.stdout or "") + (proc.stderr or "")).strip()
    if not out:
        return " ".join(full_cmd), None
    lines = out.splitlines()
    # [F12 가독성] 장문 단일 줄 절단 (ffmpeg 'configuration:' 500자 대책)
    if max_width and max_width > 0:
        lines = [l if len(l) <= max_width else l[:max_width] + "…" for l in lines]
    if max_lines and max_lines > 0 and len(lines) > max_lines:
        kept = lines[:max_lines]
        kept.append(f"… ({len(lines) - max_lines} lines truncated)")
        return " ".join(full_cmd), "\n".join(kept)
    return " ".join(full_cmd), "\n".join(lines)


def _ffmpeg_version(path, timeout=3):
    """`ffmpeg -version` 첫 줄에서 버전 추출 (예: '7.1.1'). 실패 시 None."""
    try:
        import re
        out = subprocess.run(
            [path, "-version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=_NO_WINDOW if os.name == "nt" else 0,
        )
        line = (out.stdout or out.stderr or "").splitlines()[0]
        m = re.search(r"version\s+([0-9][0-9.]*)", line)
        return m.group(1) if m else None
    except Exception:
        return None

def _exe_suffix():
    return ".exe" if sys.platform == "win32" else ""

def _download_to(url, dest, timeout=120):
    """Download url to dest file. Returns True on success."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp, open(dest, "wb") as f:
            shutil.copyfileobj(resp, f)
        return True
    except Exception:
        return False

def _get_pypi_whl_url(pypi_name):
    """PyPI에서 최신 whl 다운로드 URL을 조회. 실패 시 None."""
    try:
        with urllib.request.urlopen(_PYPI_API.format(pkg=pypi_name), timeout=10) as resp:
            data = json.load(resp)
        urls = data.get("urls") or []
        # manylinux/macosx/windows whl 우선순호
        preferred = [f for f in urls if "whl" in f.get("filename", "")]
        if preferred:
            return preferred[0].get("url")
    except Exception:
        pass
    return None

def _extract_from_whl(whl_path, dest_dir):
    """whl 파일(zip)을 dest_dir에 압축 해제."""
    import zipfile
    try:
        with zipfile.ZipFile(whl_path) as zf:
            zf.extractall(dest_dir)
        return True
    except Exception:
        return False

def _frozen_upgrade_ytdlp(channel="stable"):
    """PyInstaller frozen build: yt-dlp를 직접 다운로드하여 교체.
    Stable: PyPI release whl에서 yt-dlp.exe 추출.
    Nightly: GitHub nightly-builds release에서 yt-dlp.exe 다운로드.
    """
    suffix = _exe_suffix()
    try:
        import yt_dlp
        ytdlp_dir = os.path.dirname(yt_dlp.__file__)
    except Exception:
        return 1, "yt-dlp not found"
    dest = os.path.join(os.path.dirname(ytdlp_dir), f"yt-dlp{suffix}")

    if channel == "nightly":
        url = _NIGHTLY_API.format(_ext=suffix)
    else:
        url = _get_pypi_whl_url("yt-dlp")
        if not url:
            return 1, "No whl found on PyPI"
        # whl에서 yt-dlp.exe 추출
        try:
            with tempfile.TemporaryDirectory() as tmp:
                whl_path = os.path.join(tmp, "yt-dlp.whl")
                if not _download_to(url, whl_path):
                    return 1, "whl download failed"
                import zipfile
                with zipfile.ZipFile(whl_path) as zf:
                    for name in zf.namelist():
                        if name.endswith(f"yt-dlp{suffix}"):
                            with zf.open(name) as src, open(dest, "wb") as dst:
                                shutil.copyfileobj(src, dst)
                            return 0, f"updated to {channel}"
            return 1, "yt-dlp binary not found in whl"
        except Exception as e:
            return 1, f"whl extract failed: {e}"

    if _download_to(url, dest):
        return 0, f"updated to {channel}"
    return 1, "download failed"

def _frozen_upgrade_streamlink():
    """PyInstaller frozen build: streamlink를 직접 다운로드하여 교체.
    PyPI whl에서 패키지 전체를 site-packages에 압축 해제.
    """
    try:
        import streamlink
        pkg_dir = os.path.dirname(streamlink.__file__)
    except Exception:
        return 1, "streamlink not found"

    whl_url = _get_pypi_whl_url("streamlink")
    if not whl_url:
        return 1, "No whl found on PyPI"

    try:
        with tempfile.TemporaryDirectory() as tmp:
            whl_path = os.path.join(tmp, "streamlink.whl")
            if not _download_to(whl_url, whl_path):
                return 1, "whl download failed"
            if _extract_from_whl(whl_path, pkg_dir):
                return 0, "updated to latest"
        return 1, "whl extract failed"
    except Exception as e:
        return 1, f"streamlink update failed: {e}"

def upgrade_packages(packages, channel="stable"):
    """직접 다운로드 방식으로 패키지 업데이트 (Dev/Frozen 통합).

    [v3.1.0 변경] Dev 환경에서도 pip 대신 직접 다운로드 경로 사용.
    이유: 포터블 빌드와 Dev에서 동일한 코드 경로를 타야 디버깅이 가능.
    pip install은 빌드 시에만 사용 (PyInstaller 번들 시점).

    Returns (returncode, output tail). Worker thread only.
    """
    is_frozen = getattr(sys, "frozen", False)

    # yt-dlp: Dev/Frozen 통합 - 직접 다운로드
    if "yt-dlp" in packages:
        return _frozen_upgrade_ytdlp(channel)

    # streamlink: Dev/Frozen 통합 - whl 직접 다운로드
    if "streamlink" in packages:
        return _frozen_upgrade_streamlink()

```

## File: utils.py

```python
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

```

## File: yt_logger_bridge.py

```python
### yt_logger_bridge.py - yt-dlp 로거 어댑터 (Analyze/Download 공용)
"""yt-dlp logger 콜백을 raw_log 버스로 연결하는 공용 어댑터.

- ANSI 제거는 utils.clean_ansi()만 사용한다.
- \r progress tick은 한 청크로 조립해 최신 meaningful tick만 발행한다.
- 일반 info/warning/error는 원문을 F12/history에 보존한다.
"""
import os
import re
import threading
import time

from utils import clean_ansi


_PROGRESS_RE = re.compile(r"^\s*\[download\].*?(\d+(?:\.\d+)?)%(?:\s|$)")
_MERGE_TEXT = "Merging formats into"
_ALREADY_DOWNLOADED = "has already been downloaded"


class YtLoggerBridge:
    """yt-dlp logger → raw_log bus adapter."""

    _MAX_CARRIAGE_CHARS = 4096

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._carriage_buffer = ""
        self._last_progress = None
        self._last_progress_at = 0.0

    @staticmethod
    def _is_progress(msg: str) -> bool:
        return bool(_PROGRESS_RE.match(msg))

    def _emit_progress(self, msg: str) -> None:
        now = time.monotonic()
        with self._lock:
            # yt-dlp progress callbacks are often far faster than 2 Hz.
            if self._last_progress is not None and now - self._last_progress_at < 0.5:
                return
            self._last_progress = msg
            self._last_progress_at = now
        import raw_log
        from log_event import LogEvent
        raw_log.raw(
            "ytdlp",
            LogEvent(
                stage="YTDLP",
                status="RUN",
                platform="-",
                msg=msg,
                is_status=True,
            ),
            to_tui=True,
        )

    def _emit_non_progress(self, clean_msg: str, level: str) -> None:
        import raw_log
        from log_event import LogEvent
        status = {
            "warning": "WARN",
            "error": "FAIL",
            "info": "OK",
            "debug": "OK",
        }.get(level, "OK")
        raw_log.raw(
            "ytdlp",
            LogEvent(
                stage="YTDLP",
                status=status,
                platform="-",
                msg=clean_msg,
                is_error=level == "error",
            ),
        )
        if _MERGE_TEXT in clean_msg:
            raw_log.raw(
                "dl",
                LogEvent(stage="MERG", status="RUN", platform="-", msg="merging"),
                to_tui=True,
            )
        if _ALREADY_DOWNLOADED in clean_msg:
            fname = (
                clean_msg.replace("[download]", "")
                .replace(_ALREADY_DOWNLOADED, "")
                .strip()
            )
            raw_log.raw(
                "dl",
                LogEvent(
                    stage="DL",
                    status="OK",
                    platform="-",
                    msg=f"skip — exists ({os.path.basename(fname)})",
                ),
                to_tui=True,
            )

    def _flush_carriage(self, msg: str, level: str) -> None:
        clean_msg = clean_ansi(msg)
        if not clean_msg:
            return

        # warning/error는 progress buffer에 갇히지 않고 즉시 보존한다.
        if level in {"warning", "error"}:
            clean_msg = clean_msg.replace("\r", " ").replace("\n", " ").strip()
            if clean_msg:
                self._emit_non_progress(clean_msg, level)
            return

        with self._lock:
            parts = clean_msg.replace("\n", "\r").split("\r")
            if len(parts) > 1:
                # 같은 콜백 안 \r 반복 = 같은 줄 덮어쓰기 스냅샷 → 마지막이 최신.
                candidate = parts[-1] or (parts[-2] if len(parts) > 1 else "")
                if clean_msg.endswith("\r"):
                    # 줄이 아직 진행 중 → 다음 청크와 연결하기 위해 이월 보류.
                    self._carriage_buffer = candidate[-self._MAX_CARRIAGE_CHARS:]
                    return
                self._carriage_buffer = ""
                clean_msg = candidate
            elif self._carriage_buffer:
                # \r 없는 청크 = 직전 이월 조각의 이어짐 → 합쳐 한 줄로 재구성.
                clean_msg = (
                    self._carriage_buffer + parts[-1]
                )[-self._MAX_CARRIAGE_CHARS:]
                self._carriage_buffer = ""
            else:
                clean_msg = parts[-1]

        clean_msg = clean_msg.strip()
        if not clean_msg:
            return
        if self._is_progress(clean_msg):
            self._emit_progress(clean_msg)
            return
        self._emit_non_progress(clean_msg, level)

    def debug(self, msg):
        self._flush_carriage(msg, "debug")

    def info(self, msg):
        self._flush_carriage(msg, "info")

    def warning(self, msg):
        self._flush_carriage(msg, "warning")

    def error(self, msg):
        self._flush_carriage(msg, "error")

```

## File: src/chzzktube/__init__.py

```python
def main() -> None:
    print("Hello from chzzktube!")

```
