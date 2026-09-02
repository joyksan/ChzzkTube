##### downloader_helpers/client_opts.py - yt-dlp 옵션 빌더
"""yt-dlp 옵션에 player_client/쿠키 설정을 주입하는 순수 헬퍼."""
import os


def _apply_client_opts(opts, cfg):
    """유튜브 player_client 수동 지정을 ydl_opts에 반영 (성인제한 대응)."""
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
