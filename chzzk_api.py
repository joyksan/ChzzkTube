### chzzk_api.py - 치지직 공개 API 통신 (클립/VOD/LIVE 메타데이터 + 스트림 목록)
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
                stage="ANAL", status="WARN", scope="CHZ",
                msg=f"chzzk clip detail api failed (clip {clip_id}): {type(e).__name__}: {e}",
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
                stage="ANAL", status="WARN", scope="CHZ",
                msg=f"chzzk clip play-info api failed (clip {clip_id}): {type(e).__name__}: {e}",
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
                stage="ANAL", status="WARN", scope="CHZ",
                msg=f"chzzk vod api failed (video/{video_no}): {type(e).__name__}: {e}",
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
                stage="ANAL", status="WARN", scope="CHZ",
                msg=f"chzzk live api failed (live/{live_id}): {type(e).__name__}: {e}",
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
                    stage="ANAL", status="WARN", scope="CHZ",
                    msg=f"chzzk live offline ({live_status}) - live/{live_id}",
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
