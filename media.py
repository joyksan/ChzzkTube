### media.py - 순수 미디어 처리 헬퍼 (해상도 라벨 / 임시파일 정리 / FFmpeg 리먹싱 / 코덱 랭킹)
import glob
import os
import subprocess
import unicodedata

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

### 해상도 매핑 테이블 (height → 라벨)
_RESOLUTION_MAP = {
    2160: "4K",
    1440: "2K",
    1080: "1080p",
    720: "720p",
    480: "480p",
    360: "360p",
}

def map_res(res, height):
    h = int(height or 0)
    res_str = str(res)
    return next(
        (
            label
            for height_val, label in _RESOLUTION_MAP.items()
            if h == height_val or str(height_val) in res_str
        ),
        res_str,
    )

def display_width(text):
    """터미널/고정폭 폰트 기준 렌더링 폭 — CJK(전각)는 2칸, 나머지는 1칸.
    컬럼 정렬 로그(TUI 스타일)의 정렬 기준이 되는 단일 출처."""
    return sum(
        2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
        for ch in str(text)
    )


def format_title(title, max_len=25):
    """제목을 고정 폭으로 절단 — CJK 전각 문자 폭을 반영해 '…'로 끝내며
    전체 렌더링 폭이 max_len(표시 셀)을 넘지 않게 한다. 컬럼 어긋남 방지용."""
    title = str(title or "").strip()
    max_len = max(4, int(max_len))
    width = display_width(title)
    if width <= max_len:
        return title

    out, used = [], 0
    for ch in title:
        w = 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
        if used + w + 1 > max_len:  # 1칸은 '…' 예약
            break
        out.append(ch)
        used += w
    return "".join(out).rstrip() + "…"


def format_bytes(size):
    """바이트(Bytes) 수치를 KB, MB, GB 단위로 자동 환산"""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} PB"

def cleanup_temp_files(filepath):
    """작업 중단 시 .part, .ytdl, .f*** 스트림 조각 및 임시 썸네일 일괄 삭제"""
    if not filepath:
        return
    try:
        base_path = os.path.splitext(filepath)[0]
        directory = os.path.dirname(filepath) or "."
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

def remux_stream(ts_path, output_path, thumb_path=None):
    cmd = ["ffmpeg", "-y", "-i", ts_path]
    if thumb_path and os.path.exists(thumb_path):
        cmd.extend(
            [
                "-i",
                thumb_path,
                "-map",
                "0",
                "-map",
                "1",
                "-disposition:v:1",
                "attached_pic",
            ]
        )

    if output_path.lower().endswith(".mp4"):
        cmd.extend(["-c", "copy", "-movflags", "+faststart", output_path])
    else:
        cmd.extend(["-c", "copy", output_path])

    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    for path in [ts_path, thumb_path]:
        if path and os.path.exists(path):
            try:
                os.remove(path)
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
        print(f"Live Remuxing error: {e}")

    return ts_path
