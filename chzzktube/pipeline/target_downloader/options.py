##### target_downloader/options.py - yt-dlp 옵션 빌더
"""yt-dlp 다운로드 옵션 생성 — 포맷 선택/병합/쿠키/PO 토큰 주입."""
import functools
import os

import chzzktube.pipeline.progress_emitter as _pe
from chzzktube.core.client_opts import (
    _apply_client_opts,
    _apply_cookie_opts,
    _apply_ejs_opts,
    _apply_ffmpeg_opts,
    _apply_post_opts,
    _apply_pot_opts,
    _concurrent_fragments,
)
from chzzktube.core.utils import get_filename_template
from chzzktube.pipeline.target_downloader.utils import _extract_yt_id


def _format_selector(ctx):
    """yt-dlp format 선택 문자열 — 자동(해상도 제한 내 최고)/포맷 직접 고르기 대응.

    [결함 1 수리] tv 클라이언트 대비: 비디오+오디오 분리 포맷이 없을 때
    단일 포맷(b)으로 폴백하지 않고 명시적 에러 유도 → 상위에서 폴백 체인 계속.
    """
    if ctx.cfg.get("audio_only"):
        return "bestaudio/best"

    v_id = str(ctx.v_sel or "").strip()
    a_id = str(ctx.a_sel or "").strip()
    if v_id and v_id != "auto":
        if a_id and a_id != "auto":
            return f"{v_id}+{a_id}"
        return f"{v_id}+bestaudio"

    res = str(ctx.cfg.get("max_video_res") or "none").strip()
    if res.isdigit():
        return f"bv*[height<={res}]+ba"
    # [결함 1 수리] "bv*+ba/b" → "bv*+ba" (단일 포맷 폴백 제거)
    return "bv*+ba"


def _make_ytdl_opts(ctx, fmt, url, forced_client=None, inject_pot=False):
    """yt-dlp 다운로드 옵션 — outtmpl/훅/병합/쿠키/player_client/PO 토큰 주입.

    Args:
        forced_client: 강제 사용할 player_client (None이면 "auto"로 순정 위임).
        inject_pot: True면 PO token 강제 주입 (POT 서버 기동 후 재시도용).
    """
    opts = {
        "logger": ctx.logger,
        "noplaylist": True,
        "progress_hooks": [functools.partial(_pe.hook, ctx)],
        "postprocessor_hooks": [functools.partial(_pe.pp_hook, ctx)],
        "outtmpl": os.path.join(
            ctx.cfg.get("download_path", ""),
            get_filename_template(cfg=ctx.cfg),
        ),
        "format": _format_selector(ctx),
        "merge_output_format": ctx.cfg.get("container", "mp4"),
        "socket_timeout": 30,
        "retries": ctx.cfg.get("retries", 10),
        "fragment_retries": ctx.cfg.get("fragment_retries", 10),
        "concurrent_fragment_downloads": _concurrent_fragments(ctx.cfg),
    }

    _apply_cookie_opts(opts, ctx.cfg)
    _apply_client_opts(opts, ctx.cfg, forced=forced_client)
    _apply_ffmpeg_opts(opts)
    _apply_post_opts(opts, ctx.cfg)
    _apply_ejs_opts(opts)

    # PO 토큰 강제 주입 (POT 서버 재시도 시)
    if inject_pot:
        video_id = _extract_yt_id(url)
        if video_id:
            _apply_pot_opts(opts, video_id, client=forced_client or "auto")

    return opts