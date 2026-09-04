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

from media import cleanup_temp_files, format_bytes, remux_live_to_container
from utils import get_filename_template
from dl_platform import _dl_platform
from progress_emitter import emit_dl, emit_live_final_stats

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
    temp_ts, thumb, _ = worker._prepare_live_paths(out_file, info.get("thumbnail"))

    cmd = ["ffmpeg", "-y", "-i", stream_url, "-c", "copy", "-f", "mpegts", temp_ts]
    return worker._record_live_stream(cmd, temp_ts, out_file, thumb)


def handle_stream_finish(worker, is_live, temp_file, proc_code=0):
    """스트림 종료 후처리 — 컨테이너 리먹싱 + 임시 파일 정리 + 완료 로그."""
    if proc_code not in (0, None):
        if worker.state.get("canceled"):
            worker.live_partially_saved = True
        else:
            worker.log_concise.emit(
                emit_dl(
                    status="FAIL",
                    platform="-",
                    spec="-",
                    speed="-",
                    pct=None,
                    bar_frac=None,
                    stage="LIVE",
                    msg="exit code error",
                ),
                is_status=False,
                is_error=True,
            )
        cleanup_temp_files(temp_file)
        return False

    out_path = remux_live_to_container(temp_file, worker.cfg.get("container", "mp4"))
    if out_path and os.path.exists(out_path):
        size = os.path.getsize(out_path)
        worker.log_concise.emit(
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
            is_status=False,
            is_error=False,
        )
        worker.log_success_info(out_path)
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

    worker._speed_win.reset()
    total_bytes = 0
    start_t = time.monotonic()
    last_tick = 0.0

    def _drain_stderr():
        # stderr 는 별도 스레드로 실시간 상세 로그 유지
        for raw in iter(proc.stderr.readline, b""):
            if raw:
                try:
                    worker.log_full.emit(raw.decode("utf-8", "replace").strip())
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
                    worker.log_concise.emit(
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
                        ),
                        is_status=False,
                        is_error=False,
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
        worker.log_concise.emit(
            emit_dl(
                status="FAIL",
                platform="-",
                spec="-",
                speed="-",
                pct=None,
                bar_frac=None,
                stage="LIVE",
                msg=f"{log_tag} fail",
            ),
            is_status=False,
            is_error=True,
        )
    finally:
        stderr_t.join(timeout=1.0)
        return worker.handle_stream_finish(True, temp_ts_file, returncode)