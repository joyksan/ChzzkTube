"""format_desc.py - 포맷 표기 헬퍼 (DownloadWorker에서 사용)."""
from media import short_codec, codec_detail, audio_spec


def get_unified_video_desc(info):
    """비디오 코덱 + 해상도 통합 표기."""
    if not info:
        return ""
    v = info.get("vcodec") or "?"
    h = info.get("height") or 0
    fps = info.get("fps") or 0
    codec = short_codec(v)
    detail = codec_detail(info)
    if h:
        base = f"{h}p"
        if fps:
            base += f"{fps}"
        if detail:
            return f"{base} ({detail})"
        return base
    return detail if detail else codec


def get_unified_audio_desc(info):
    """오디오 코덱 통합 표기."""
    if not info:
        return ""
    acodec = info.get("acodec") or info.get("audio_codec") or ""
    return audio_spec({"acodec": acodec})
