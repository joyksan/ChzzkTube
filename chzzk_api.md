# chzzk_api.py - 치지직 공개 API 통신 (클립/VOD 메타데이터 + 스트림 목록)

import datetime
import json
import re
import urllib.request

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
    """치지직 클립 — detail(제목/생성일) + play-info(rmcnmv MP4 목록)."""
    clean_url = target_url.split("?")[0].rstrip("/")
    clip_id = clean_url.split("/")[-1]

    headers = _chzzk_headers()

    clip_title = clip_id
    created_date = datetime.date.today().strftime("%Y-%m-%d")

    detail_url = f"https://api.chzzk.naver.com/service/v1/clips/{clip_id}/detail"
    try:
        d_data = _get_json(detail_url, headers).get("content", {})
        if d_data.get("clipTitle"):
            clip_title = d_data.get("clipTitle")
        if d_data.get("createdDate"):
            created_date = d_data.get("createdDate").split(" ")[0]
    except Exception:
        pass

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
                # height: API가 encodingOption.height로 직접 제공한다(실측).
                # name 기반 정규식은 '720P'의 대문자 P를 놓치므로 폴백용으로만.
                height = int(enc.get("height") or 0)
                if not height:
                    h_match = re.search(r"(\d+)p", encoding_opt, re.IGNORECASE)
                    if h_match:
                        height = int(h_match.group(1))
                # bitrate: rmcnmv v2.0은 이미 kbps 단위(실측 video 563.0,
                # audio 192.0) — bps로 착각해 /1000하면 0이 된다.
                br = v.get("bitrate", {})
                bitrate_kbps = (
                    int(br.get("video", 0) or 0)
                    if isinstance(br, dict)
                    else int(br or 0)
                )
                source_url = v.get("source", "")
                v_codec = enc.get("vcodec", "H.264")
                # 클립 VOD는 오디오 내장 H.264/AAC MP4 단일 스트림(audios 목록
                # 별도 미제공) — API가 코덱 필드를 주지 않으므로 통합 포맷
                # 판별·배지 표기용으로 AAC를 명시한다.
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
    except Exception:
        pass

    video_formats.sort(
        key=lambda x: (x["height"], get_video_codec_rank(x["vcodec"]), x["bitrate"]),
        reverse=True,
    )
    return {
        "title": clip_title,
        "date": created_date,
        "clip_id": clip_id,
        "formats": video_formats,
    }


def analyze_chzzk_vod_api(target_url):
    """치지직 VOD(다시보기) — 메타 + progressive MP4 포맷 목록.

    2026년부터 재생 API(neonplayer vodplay v2)는 MPD 문서를 **JSON 직렬화**
    형태로 돌려줘서 yt-dlp의 XML(SMIL/MPD) 파서가 깨진다 — 대표 증상이
    KeyError('sourceURL')(yt-dlp common.py SMIL 파서의 속성 탐색 실패).
    실측 결과 첫 adaptationSet의 representation들이 전체 progressive MP4
    URL(클립과 동일 VOD_ALPHA CDN, 1080p60 약 8.2Mbps)을 baseURL로 직접
    제공하므로, 클립과 동일한 자체 다운로드 파이프라인으로 처리한다.
    """
    m = re.search(r"chzzk\.naver\.com/(?:video|live)/(\d+)", target_url)
    if not m:
        return {"title": None, "date": None, "duration": None, "formats": []}
    video_no = m.group(1)
    headers = _chzzk_headers()

    title, date, duration = video_no, None, None
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
        # 실제 응답의 videoTitle이 '0823 카론컵.mp4'처럼 컨테이너 확장자를
        # 포함해 내려오는 경우가 있다 — 파일명 템플릿 오염을 막기 위해 제거.
        title = re.sub(r"\.(mp4|mkv|ts|webm|mov)$", "", title, flags=re.IGNORECASE)
        date = (meta.get("publishDate") or "").split(" ")[0] or None
        duration = meta.get("duration")
        vid, inkey = meta.get("videoId"), meta.get("inKey")

        if vid and inkey:
            pb = _get_json(
                f"https://apis.naver.com/neonplayer/vodplay/v2/playback/{vid}"
                f"?key={inkey}&env=real&country=KR&platform=web",
                headers,
            )
            for period in pb.get("period") or []:
                for aset in period.get("adaptationSet") or []:
                    for rep in aset.get("representation") or []:
                        # progressive MP4만 — .mp4 baseURL이 곧 전체 파일이다.
                        # (HLS/m3u 폴백 representation과 세그먼트형은 건너뛴다)
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
                                # bandwidth는 bps(실측 8190000) → kbps로 통일.
                                "bitrate": int(rep.get("bandwidth") or 0) // 1000,
                                "url": url,
                                "vcodec": codecs[0] if codecs else "H.264",
                                "acodec": codecs[1] if len(codecs) > 1 else "AAC",
                            }
                        )
    except Exception:
        pass

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
    }