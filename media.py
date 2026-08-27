# media.py - 순수 미디어 처리 헬퍼 (해상도 라벨 / 임시파일 정리 / FFmpeg 리먹싱 / 코덱 랭킹)

import glob
import os
import subprocess


# 코덱 품질 랭킹 데이터 테이블 (높을수록 우선순위 높음)
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


# 코덱 전체명 → 짧은 표기 매핑 (로그/배지용)
# AAC 프로파일 세분화: mp4a.40.2=AAC-LC, 40.5=HE-AAC v1, 40.29=HE-AAC v2.
# 특정 프로파일이 generic 'AAC'보다 먼저 매칭되야 하므로 순서 유의.
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
    """코덱 상세 문자열('mp4a.40.2', 'avc1.64002A') — 없으면 빈 값.

    치지직 API는 'AAC' 같은 총칭만 주므로 상세가 없다. 이미 짧은 표기와
    동일한 총칭이면 상세 나열이 무의미하므로 공백 처리한다.
    """
    c = str(codec or "").strip()
    if not c or c.lower() == "none":
        return ""
    if short_codec(c) == c.upper():
        return ""  # 'AAC' 등 총칭 — 상세 없음
    return c


def audio_flat(acodec):
    """짧은 이름과 상세를 괄호 없이 결합('AAC-LC mp4a.40.2') — 헤더 가지·배지용.

    값에 이미 콜론(ID 등)과 괄호를 붙여 나르는 헤더 문법상 이중 괄호는
    소음이다. 드롭다운 라벨처럼 독립 문구인 경우만 audio_spec(괄호 버전)을 쓴다.
    """
    s = short_codec(acodec)
    d = codec_detail(acodec)
    return f"{s} {d}".strip()


def audio_spec(acodec):
    """오디오 코덱 표기의 단일 출처 — 짧은 이름과 상세(mp4a.40.2 등) 결합.

    메타 배지·드롭다운 항목·헤더 오디오 가지가 모두 같은 문구를 쓰도록
    하는 공용 헬퍼다. 상세가 없는 총칭('AAC' 등)은 짧은 이름만 반환한다.
    """
    s = short_codec(acodec)
    d = codec_detail(acodec)
    return f"{s} ({d})" if d else s


def short_codec(codec):
    """'avc1.640028' 같은 코덱 전체명을 'H264' 같은 짧은 표기로 변환.

    1) 전체 문자열과 키워드의 **정확 일치**를 먼저 본다 — 'mp4a.40.2'가
       'mp4a.40.29'(HE-AAC v2)의 접두사라서 부분 문자열 매칭만 쓰면
       v2가 항상 AAC-LC로 오분류된다.
    2) 정확 일치가 없으면 기존대로 부분 문자열 폴백('avc1.64002A'→'H264').
    """
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
    """yt-dlp -F 표(CLI) 컬럼을 한 줄로 재현 — 모든 소스의 포맷 표기 단일 출처.

    비디오: 'mp4 | 1920x1080 60fps | 8190k https | H264 | AAC-LC (mp4a.40.2)'
            (비디오+오디오 통합 포맷은 -F 표처럼 오디오 코덱까지 한 줄에 표기.
             헤더에서 별도 '오디오' 가지를 뽑으면 중복이므로 금지.)
    오디오: 'webm | 160k https | OPUS (opus)'
    (ID: …) 문법은 폐지 — 길이가 간결 로그의 줄바꿈(wrap)을 유발하는 소음이었다.

    조각(fps/비트레이트/프로토콜)은 존재할 때만 붙인다 — 치지직 API처럼
    필드가 적은 소스에서도 안전하게 동일 규격으로 조판된다.
    """
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
        # 오디오 전용은 비트레이트/프로토콜 노이즈 없이 코드만 — 사용자 피드백:
        # '129k https' 같은 찌꺼기가 코덱 표기를 흐린다. 컨테이너 + 코덱으로 정리.
        parts.append(audio_spec(ac) if has_a else "?")
    return " | ".join(p for p in parts if p)


# 해상도 매핑 테이블 (height → 라벨)



# 해상도 매핑 테이블 (height → 라벨)
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
        # 파일 경로에서 확장자를 뗀 순수 베이스 파일명 추출
        base_path = os.path.splitext(filepath)[0]
        directory = os.path.dirname(filepath) or "."

        # 파일명 기본 패턴 (예: "C:/.../video_title*")
        # .f251.webm.part, .f399.mp4.part, .webp, .jpg 등 모든 연관 임시 파일 검색
        search_pattern = base_path + "*"

        for target in glob.glob(search_pattern):
            # 완제품 mp4/mkv/mp3 등을 제외한 임시/후처리 파일 대상 삭제
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
    """MPEG-TS 스트림을 사용자가 지정한 컨테이너(MP4/MKV)로 초고속 리먹싱"""
    cmd = ["ffmpeg", "-y", "-i", ts_path]

    # 썸네일 커버 내장
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

    # MP4일 경우에만 빠른 재생용 faststart 인덱스 추가, 그 외(MKV 등)는 무재인코딩 스트림 카피
    if output_path.lower().endswith(".mp4"):
        cmd.extend(["-c", "copy", "-movflags", "+faststart", output_path])
    else:
        cmd.extend(["-c", "copy", output_path])

    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 임시 수신 파이프 파일 및 썸네일 정리
    for path in [ts_path, thumb_path]:
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass


def remux_live_to_container(ts_path, container_setting="mp4"):
    """
    라이브 녹화 임시 파일(.ts 등)을 사용자가 설정한 컨테이너(mp4, mkv)로 리먹싱.
    webm이 선택된 경우 자동으로 mp4로 안전하게 폴백(Fallback)시킵니다.
    """
    if not ts_path or not os.path.exists(ts_path):
        return None

    # 1. webm이거나 지원하지 않는 포맷일 경우 mp4로 강제 폴백 매핑
    target_ext = container_setting.lower()
    if target_ext not in ["mp4", "mkv"]:
        target_ext = "mp4"  # webm 선택 시 안전한 mp4로 자동 전환

    out_path = os.path.splitext(ts_path)[0] + f".{target_ext}"

    # 2. 인코딩 없이 컨테이너만 빠르게 포장하는 FFmpeg 리먹싱 명령어 (스트림 복사 -c copy)
    cmd = ["ffmpeg", "-y", "-i", ts_path, "-c", "copy", out_path]

    try:
        # Windows 환경에서 인코딩 충돌 방지를 위해 파이프라인 명시
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)

        # 변환이 성공적으로 완료되었다면 원본 임시 파일은 깔끔하게 삭제
        if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
            os.remove(ts_path)
            return out_path
    except Exception as e:
        print(f"Live Remuxing error: {e}")

    return ts_path  # 변환 실패 시 원본 경로 반환