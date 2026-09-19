##### live_recorder.py - 라이브 녹화 파이프라인 (streamlink/ffmpeg)
"""유튜브·치지직 라이브를 ffmpeg 자식 프로세스로 녹화한다.

- yt-dlp/streamlink 로 포맷 URL만 추출하고, 실제 수신은 ffmpeg로 위임
- **릴레이 계측**: ffmpeg stdout(파이프) 을 Python 이 256KB 청크로 읽어
  최종 파일에 실기록하며, 그 바이트 수 = 네트워크 실수신량 → ctx.speed_win(add) 로 속도 측정
- stderr 는 별도 스레드로 상세 로그 유지
- 취소 시 kill + stdout 큐 drain (이후 'truncated' 오탐 방지)
- **출력 소유권 단일화**: FFmpeg는 stdout 파이프로만 출력, Python이 파일 소유자로서 기록
- **논블로킹 읽기**: reader 스레드 + Queue로 1초 타임아웃 폴링 → 취소/워치독 하트비트 체크 가능
"""
import os
import queue
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
# [결함 2 수리] 논블로킹 읽기 셀렉터 타임아웃 (초) — 취소/워치독 체크 주기
_SELECTOR_TIMEOUT = 1.0
# [결함 5 수리] 워치독 하트비트 발행 간격 (초)
_WATCHDOG_HEARTBEAT_INTERVAL = 5.0


def download_youtube_live(ctx, url):
    """유튜브 라이브 — yt-dlp로 포맷 URL만 추출 후 Python이 파일을 기록한다.

    FFmpeg는 MPEG-TS를 stdout으로만 출력한다. Python이 최종 출력 파일의 유일한
    작성자가 되어 FFmpeg와 파일 소유권을 공유하지 않는다.
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
    _apply_client_opts(opts, ctx.cfg, forced=None)  # 순정 위임
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

    temp_ts, _, _ = prepare_live_paths(ctx, out_file)
    cmd = ["ffmpeg", "-y", "-i", stream_url, "-c", "copy", "-f", "mpegts", "pipe:1"]
    return record_live_stream(ctx, cmd, temp_ts, log_tag="FFmpeg")


def prepare_live_paths(ctx, out_file, thumb_url=None):
    """릴레이 기록용 임시 TS 및 썸네일·최종 출력 경로를 도출한다."""
    base, _ = os.path.splitext(out_file)
    temp_ts = f"{base}_temp.ts"
    thumb_file = f"{base}_temp_thumb.jpg" if thumb_url else None
    return temp_ts, thumb_file, out_file


def _remux_live_output(ctx, out_file):
    """TS를 별도 파일로 변환한 뒤 교체한다. 실패하면 원본을 보존한다."""
    from chzzktube.infra.platform import spawn_kwargs

    if not out_file or not os.path.isfile(out_file) or not os.path.getsize(out_file):
        return None
    target_ext = str(ctx.cfg.get("container", "mp4") or "mp4").lower()
    if target_ext not in ("mp4", "mkv"):
        target_ext = "mp4"
    base = os.path.splitext(out_file)[0].removesuffix("_temp")
    out_path = base + f".{target_ext}"
    # 기존 최종 파일과 원본 TS는 변환 성공 전까지 건드리지 않는다.
    import tempfile
    fd, staging = tempfile.mkstemp(suffix=f".{target_ext}", dir=os.path.dirname(out_file) or ".")
    os.close(fd)
    cmd = ["ffmpeg", "-y", "-i", out_file, "-c", "copy", staging]
    try:
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       check=True, timeout=120, **spawn_kwargs())
        if not os.path.getsize(staging):
            raise RuntimeError("empty remux output")
        os.replace(staging, out_path)
        if os.path.abspath(out_file) != os.path.abspath(out_path):
            os.remove(out_file)
        return out_path
    except Exception as ex:
        raw_log.raw(
            "media",
            emit_dl(status="FAIL", scope=_dl_platform(ctx.current_url or ""),
                    stage="LIVE", msg=f"live remux failed — {ex}; source retained: {out_file}",
                    is_error=True),
            to_tui=False,
        )
        return None
    finally:
        with suppress(OSError):
            os.remove(staging)



def handle_stream_finish(ctx, is_live, temp_file, proc_code=0):
    """성공한 변환만 완료 처리하고, 취소/실패한 원본 녹화는 보존한다."""
    has_data = bool(temp_file and os.path.isfile(temp_file) and os.path.getsize(temp_file))
    if ctx.state.get("canceled"):
        ctx.live_partially_saved = has_data
        if has_data:
            raw_log.raw("dl", emit_dl(status="ABORT", stage="LIVE",
                        msg=f"partial recording retained: {temp_file}"), to_tui=True)
        return False
    if not has_data:
        raw_log.raw("dl", emit_dl(status="FAIL", stage="LIVE",
                    msg="empty or missing recording", is_error=True), to_tui=True)
        return False
    if proc_code not in (0, None):
        raw_log.raw("dl", emit_dl(status="FAIL", stage="LIVE",
                    msg=f"exit code {proc_code}; source retained: {temp_file}",
                    is_error=True), to_tui=True)
        return False

    out_path = _remux_live_output(ctx, temp_file)
    if not out_path:
        return False
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
_TICK_INTERVAL = 1.0


def record_live_stream(ctx, cmd, out_file, log_tag="Streamlink"):
    """ffmpeg/streamlink 자식 프로세스 녹화 — 릴레이 계측 + stderr 로그 + 취소 처리.

    [결함 2 수리] reader 스레드 + Queue로 논블로킹 릴레이
    - Windows 파이프에서 selectors/select 미지원 문제 회피
    - 네트워크 단절 시에도 메인 루프가 1초마다 취소/워치독 체크
    [결함 5 수리] 5초마다 워치독 하트비트 호출
    """
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

    # [결함 2 수리] stdout 읽기를 별도 스레드로 분리
    # - 메인 루프는 queue.get(timeout=1.0)으로 논블로킹
    # - reader 스레드가 블로킹 read를 담당하므로 네트워크 멈춤도 메인 UI를 막지 않음
    stdout_queue = queue.Queue()
    def _read_stdout():
        try:
            while True:
                chunk = proc.stdout.read(_READ_CHUNK)
                stdout_queue.put(chunk)
                if not chunk:
                    break
        except Exception:
            # reader 스레드 예외도 메인 루프가 종료할 수 있도록 EOF sentinel 주입
            stdout_queue.put(b"")

    reader_t = threading.Thread(target=_read_stdout, daemon=True)
    reader_t.start()

    ctx.speed_win.reset()
    total_bytes = 0
    start_t = time.monotonic()
    last_tick = 0.0
    last_watchdog_heartbeat = 0.0

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
                try:
                    chunk = stdout_queue.get(timeout=_SELECTOR_TIMEOUT)
                except queue.Empty:
                    # [결함 2 수리] 1초 타임아웃마다 취소/워치독/프로세스 상태 체크
                    if ctx.state.get("canceled") and proc.poll() is None:
                        with suppress(ProcessLookupError, OSError):
                            proc.kill()
                        break
                    # [결함 5 연동] 워치독 하트비트 (ctx에 워치독 참조가 있다면)
                    _try_watchdog_heartbeat(ctx, last_watchdog_heartbeat)
                    last_watchdog_heartbeat = time.monotonic()
                    continue

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
                            is_status=True,
                        ),
                        to_tui=True,
                    )

                # [결함 2 수리] 취소 요청 즉시 처리
                if ctx.state.get("canceled") and proc.poll() is None:
                    with suppress(ProcessLookupError, OSError):
                        proc.kill()
                    break

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
        reader_t.join(timeout=1.0)
        stderr_t.join(timeout=1.0)

    return handle_stream_finish(ctx, True, out_file, returncode)


def _try_watchdog_heartbeat(ctx, last_heartbeat_time):
    """컨텍스트에서 사용 가능한 워치독에 하트비트 시도 (5초 간격)."""
    now = time.monotonic()
    if now - last_heartbeat_time < _WATCHDOG_HEARTBEAT_INTERVAL:
        return
    for attr in ("_download_watchdog", "_gate_watchdog", "_live_watchdog", "_analysis_watchdog"):
        wd = getattr(ctx, attr, None)
        if wd and hasattr(wd, "heartbeat"):
            try:
                wd.heartbeat()
            except Exception:
                pass
            break
