##### live_recorder.py - 라이브 녹화 파이프라인 (streamlink/ffmpeg)
"""유튜브·치지직 라이브를 ffmpeg 자식 프로세스로 녹화한다.

- yt-dlp/streamlink 로 포맷 URL만 추출하고, 실제 수신은 ffmpeg로 위임
- **릴레이 계측**: ffmpeg stdout(파이프) 을 Python 이 256KB 청크로 읽어
  최종 파일에 실기록하며, 그 바이트 수 = 네트워크 실수신량 → ctx.speed_win(add) 로 속도 측정
- stderr 는 별도 스레드로 상세 로그 유지
- 취소 시 kill + stdout 큐 drain (이후 'truncated' 오탐 방지)
- **출력 소유권 단일화**: FFmpeg는 stdout 파이프로만 출력, Python이 파일 소유자로서 기록
"""
import os
import subprocess
import threading
import time
from contextlib import suppress

import yt_dlp

from chzzktube.core import raw_log
from chzzktube.core.dl_platform import _dl_platform
from chzzktube.core.media import (
    cleanup_temp_files,
    format_bytes,
    remux_live_to_container,
)
from chzzktube.core.utils import get_filename_template
from chzzktube.pipeline.progress_emitter import (
    emit_dl,
    emit_live_final_stats,
    log_success_info,
)

# FFmpeg stdout 읽기 청크 크기 (256KB)
_READ_CHUNK = 256 * 1024
# 진행 로그 발행 간격 (초)
_TICK_INTERVAL = 1.0


def download_youtube_live(ctx, url):
    """유튜브 라이브 — yt-dlp로 통합 포맷 URL만 추출 후 ffmpeg로 녹화.

    Args:
        ctx: DownloadContext (worker 대신 컨텍스트만 받음)
        url: 라이브 스트림 URL
    """
    opts = {
        "logger": ctx.logger,
        "noplaylist": True,
        "format": "bv*+ba/b",
        "skip_download": True,
        "extract_flat": False,
    }
    from chzzktube.core.client_opts import (
        _apply_client_opts,
        _apply_cookie_opts,
        _apply_ejs_opts,
        _apply_ffmpeg_opts,
    )

    _apply_cookie_opts(opts, ctx.cfg)
    _apply_client_opts(opts, ctx.cfg, forced=ctx.yt_client)
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
        ctx.cfg["download_path"],
        get_filename_template(ctx.cfg) % info,
    )

    # FFmpeg는 stdout 파이프로 출력, Python이 out_file에 직접 기록
    cmd = ["ffmpeg", "-y", "-i", stream_url, "-c", "copy", "-f", "mpegts", "pipe:1"]
    return record_live_stream(ctx, cmd, out_file, info.get("thumbnail"))


def prepare_live_paths(ctx, out_file, thumb_url=None):
    """라이브 녹화용 임시 TS 파일 및 썸네일 경로 도출."""
    base, _ = os.path.splitext(out_file)
    temp_ts = f"{base}_temp.ts"
    thumb_file = f"{base}_temp_thumb.jpg" if thumb_url else None
    return temp_ts, thumb_file, out_file


def handle_stream_finish(ctx, is_live, temp_file, proc_code=0):
    """스트림 종료 후처리 — 컨테이너 리먹싱 + 임시 파일 정리 + 완료 로그."""
    if proc_code not in (0, None):
        if ctx.state.get("canceled"):
            ctx.live_partially_saved = True
        else:
            raw_log.raw(
                "dl",
                emit_dl(
                    status="FAIL",
                    scope=_dl_platform(ctx.current_url or ""),
                    stage="LIVE",
                    msg="exit code error",
                    is_error=True,
                ),
                to_tui=True,
            )
        cleanup_temp_files(temp_file)
        return False

    out_path = remux_live_to_container(temp_file, ctx.cfg.get("container", "mp4"))
    if out_path and os.path.exists(out_path):
        size = os.path.getsize(out_path)
        raw_log.raw(
            "dl",
            emit_dl(
                status="DONE",
                scope=_dl_platform(ctx.current_url or ""),
                pct=100,
                bar_frac=1.0,
                stage="LIVE",
                msg=f"saved · {os.path.basename(out_path)} ({format_bytes(size)})",
            ),
            to_tui=True,
        )
        log_success_info(ctx, out_path)
    cleanup_temp_files(temp_file)
    return True

_READ_CHUNK = 256 * 1024
_TICK_INTERVAL = 0.5


def record_live_stream(ctx, cmd, temp_ts_file, out_file, thumb_file, log_tag="Streamlink"):
    """ffmpeg/streamlink 자식 프로세스 녹화 — 릴레이 계측 + stderr 로그 + 취소 처리."""
    from chzzktube.infra.platform import spawn_kwargs

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=False,
        **spawn_kwargs(),
    )

    # 컨텍스트에 프로세스 핸들 저장 (앱 종료 시 정리용)
    ctx._live_proc = proc

    ctx.speed_win.reset()
    total_bytes = 0
    start_t = time.monotonic()
    last_tick = 0.0

    def _drain_stderr():
        # stderr 는 별도 스레드로 실시간 상세 로그 유지 (버스 단일 경유)
        from chzzktube.core.log_event import LogEvent
        for raw in iter(proc.stderr.readline, b""):
            if raw:
                with suppress(Exception):
                    raw_log.raw("ffmpeg",
                                LogEvent(stage="LIVE", status="RUN",
                                         scope="FFMP",
                                         msg=raw.decode("utf-8", "replace").strip(),
                        ),
                    )

    stderr_t = threading.Thread(target=_drain_stderr, daemon=True)
    stderr_t.start()

    returncode = -1
    try:
        with open(out_file, "wb") as out_f:
            while True:
                chunk = proc.stdout.read(_READ_CHUNK)
                if not chunk:
                    break
                out_f.write(chunk)
                total_bytes += len(chunk)
                ctx.speed_win.add(total_bytes)

                now = time.monotonic()
                if now - last_tick >= _TICK_INTERVAL:
                    last_tick = now
                    rate = ctx.speed_win.speed()
                    fname = os.path.basename(out_file)
                    raw_log.raw(
                        "dl",
                        emit_dl(
                            status="RUN",
                            scope=_dl_platform(ctx.current_url or ""),
                            speed=f"{format_bytes(rate)}/s" if rate else "-",
                            stage="LIVE",
                            msg=f"recording · {fname}",
                            is_status=True,  # 진행률 틱은 한 줄 덮어쓰기(갱신형)
                        ),
                        to_tui=True,
                    )

                # 취소 요청 — 자식 죽이고 stdout queue drain ('truncated' 오탐 방지)
                if ctx.state.get("canceled") and proc.poll() is None:
                    with suppress(ProcessLookupError, OSError):
                        proc.kill()
                    with suppress(ValueError, OSError):
                        while proc.stdout.read(_READ_CHUNK):
                            pass

        ctx.speed_win.add(total_bytes)
        returncode = proc.wait()
        if returncode not in (0, None) and not ctx.state.get("canceled"):
            raise RuntimeError(f"{log_tag} process exit code {returncode}")
        emit_live_final_stats(ctx, total_bytes, start_t)
    except Exception as ex:  # noqa: BLE001
        if proc.poll() is None:
            with suppress(ProcessLookupError, OSError):
                proc.kill()
        raw_log.raw(
            "dl",
            emit_dl(
                status="FAIL",
                scope=_dl_platform(ctx.current_url or ""),
                stage="LIVE",
                msg=f"{log_tag} fail — {type(ex).__name__}: {ex}",
                is_error=True,
            ),
            to_tui=True,
        )
    finally:
        stderr_t.join(timeout=1.0)

    return handle_stream_finish(ctx, True, temp_ts_file, returncode)