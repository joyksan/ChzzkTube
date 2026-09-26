"""Parallel Downloader — stdlib-only async parallel download & retry."""
import asyncio
import hashlib
import random
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable, Optional

from chzzktube.core.raw_log import log_f12_net


_CHUNK_SIZE = 64 * 1024
_USER_AGENT = "ChzzkTube-Provisioner/1.0"
_READ_TIMEOUT = 30.0  # per-read timeout in seconds


@dataclass(frozen=True)
class DownloadTask:
    component: str
    url: str
    dest: Path
    expected_sha256: Optional[str] = None
    mirror_name: str = ""


@dataclass(frozen=True)
class DownloadResult:
    task: DownloadTask
    success: bool
    error: Optional[str] = None
    bytes_downloaded: int = 0
    sha256: Optional[str] = None


ProgressCallback = Callable[[str, int, int, float, float], Awaitable[None]]


def _format_network_error(exc: BaseException) -> str:
    """네트워크/수급 에러를 사용자가 쉽게 파악할 수 있는 안내 문구로 변환."""
    if isinstance(exc, urllib.error.HTTPError):
        if exc.code == 404:
            return f"HTTP 404 Not Found (asset removed or unavailable at mirror) — check update/mirror"
        if exc.code == 403 or exc.code == 429:
            return f"HTTP {exc.code} Rate Limited by host — please try again in a few minutes"
        if exc.code >= 500:
            return f"HTTP {exc.code} Server Error (mirror domain down) — try again later or restart app"
        return f"HTTP {exc.code} {exc.reason} — mirror request failed"
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return "download timed out (connection stalled) — check internet speed and restart app"
    if isinstance(exc, urllib.error.URLError):
        reason = getattr(exc, "reason", str(exc))
        return f"network connection failed ({reason}) — check internet connection and restart app"
    if isinstance(exc, ConnectionError):
        return f"connection dropped ({exc}) — check network stability and restart app"
    if isinstance(exc, ValueError) and "SHA256 mismatch" in str(exc):
        return f"{exc} — corrupted download file removed, retry recommended"
    return f"{type(exc).__name__}: {exc}"


class ParallelDownloader:
    """urllib 요청을 worker thread로 위임하는 비동기 다운로더."""

    def __init__(
        self,
        max_concurrent: int = 5,
        max_retries: int = 3,
        base_timeout: float = 120.0,
        progress_cb: Optional[ProgressCallback] = None,
    ):
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.max_retries = max_retries
        self.base_timeout = base_timeout
        self.progress_cb = progress_cb

    async def download_all(self, tasks: list[DownloadTask]) -> list[DownloadResult]:
        """모든 태스크를 세마포어 제한 아래 병렬 다운로드한다."""

        async def _download_one(task: DownloadTask) -> DownloadResult:
            async with self.semaphore:
                return await self._download_with_retry(task)

        return await asyncio.gather(*[_download_one(task) for task in tasks])

    async def _download_with_retry(self, task: DownloadTask) -> DownloadResult:
        last_error: Optional[BaseException] = None

        for attempt in range(self.max_retries):
            try:
                return await self._download_once(task)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                last_error = exc
                self._remove_part_file(task)
                log_f12_net(
                    f"download attempt {attempt + 1}/{self.max_retries} failed for {task.component}: {exc}",
                    is_error=True,
                )
                if attempt < self.max_retries - 1:
                    wait_time = (2**attempt) + random.uniform(0, 1)
                    await asyncio.sleep(wait_time)

        err_msg = _format_network_error(last_error) if last_error else "Unknown error"
        return DownloadResult(
            task=task,
            success=False,
            error=err_msg,
        )

    @staticmethod
    def _fetch_ghcr_token(url: str) -> str | None:
        """ghcr.io 익명 pull 토큰 조회 (동기 — 반드시 worker thread에서 호출)."""
        try:
            import json as _json
            repo = "homebrew/core/ffmpeg"
            if "/v2/" in url and "/blobs/" in url:
                repo = url.split("/v2/")[1].split("/blobs/")[0]
            tok_url = f"https://ghcr.io/token?scope=repository:{repo}:pull"
            tok_req = urllib.request.Request(tok_url, headers={"User-Agent": _USER_AGENT})
            with urllib.request.urlopen(tok_req, timeout=10.0) as tok_resp:
                return _json.load(tok_resp).get("token")
        except Exception:
            return None

    async def _download_once(self, task: DownloadTask) -> DownloadResult:
        """Worker thread에서 urllib/file I/O를 수행하고 progress를 회수한다."""
        task.dest.parent.mkdir(parents=True, exist_ok=True)
        part_path = task.dest.with_suffix(task.dest.suffix + ".part")
        headers = {"User-Agent": _USER_AGENT}
        if "ghcr.io" in task.url:
            # 블로킹 토큰 조회는 worker thread로 위임 (이벤트 루프 블로킹 금지)
            tok = await asyncio.to_thread(self._fetch_ghcr_token, task.url)
            if tok:
                headers["Authorization"] = f"Bearer {tok}"
        loop = asyncio.get_running_loop()
        request = urllib.request.Request(task.url, headers=headers)
        log_f12_net(f"HTTP GET {task.url}")

        def sync_download() -> DownloadResult:
            hasher = hashlib.sha256() if task.expected_sha256 else None
            try:
                with urllib.request.urlopen(
                    request, timeout=self.base_timeout
                ) as response, part_path.open("wb") as output:
                    # Set per-read timeout on the underlying socket
                    try:
                        sock = response.fp.raw._sock
                        if sock is not None:
                            sock.settimeout(_READ_TIMEOUT)
                    except AttributeError:
                        pass  # socket not accessible, continue without per-read timeout

                    total = int(response.headers.get("Content-Length", 0))
                    status_code = getattr(response, "status", 200)
                    log_f12_net(f"HTTP {status_code} for {task.component} (Content-Length: {total} bytes)")
                    downloaded = 0
                    start_time = time.monotonic()
                    last_cb_time = 0.0
                    last_cb_pct = -1

                    def report(d_bytes: int, t_bytes: int, is_final: bool = False):
                        nonlocal last_cb_time, last_cb_pct
                        if self.progress_cb is None:
                            return
                        now = time.monotonic()
                        pct = int(d_bytes * 100 / t_bytes) if t_bytes > 0 else 0
                        if not is_final:
                            # 0.15초 이내이면서 퍼센트 변화도 없으면 스킵
                            if (now - last_cb_time < 0.15) and (pct == last_cb_pct):
                                return
                        elapsed = now - start_time
                        speed_bps = d_bytes / elapsed if elapsed > 0 else 0.0
                        eta_sec = (t_bytes - d_bytes) / speed_bps if (speed_bps > 0 and t_bytes > d_bytes) else 0.0
                        last_cb_time = now
                        last_cb_pct = pct
                        if asyncio.iscoroutinefunction(self.progress_cb):
                            asyncio.run_coroutine_threadsafe(
                                self.progress_cb(task.component, d_bytes, t_bytes, speed_bps, eta_sec),
                                loop,
                            )
                        else:
                            self.progress_cb(task.component, d_bytes, t_bytes, speed_bps, eta_sec)

                    while True:
                        chunk = response.read(_CHUNK_SIZE)
                        if not chunk:
                            break
                        output.write(chunk)
                        downloaded += len(chunk)
                        if hasher is not None:
                            hasher.update(chunk)
                        report(downloaded, total)

                    effective_total = total if total > 0 else downloaded
                    report(downloaded, effective_total, is_final=True)

                computed_sha256 = hasher.hexdigest() if hasher is not None else None
                if hasher is not None and computed_sha256 != task.expected_sha256:
                    log_f12_net(
                        f"SHA256 mismatch for {task.component}: got {computed_sha256}, expected {task.expected_sha256}",
                        is_error=True,
                    )
                    raise ValueError(
                        f"SHA256 mismatch: {computed_sha256} != {task.expected_sha256}"
                    )
                part_path.replace(task.dest)
                log_f12_net(
                    f"downloaded {task.component} -> {task.dest} "
                    f"({downloaded / (1024 * 1024):.1f} MB, sha256: {computed_sha256[:16] if computed_sha256 else 'none'}...)"
                )
                return DownloadResult(
                    task=task,
                    success=True,
                    bytes_downloaded=downloaded,
                    sha256=computed_sha256,
                )
            except BaseException as e:
                self._remove_part_file(task)
                log_f12_net(f"download stream error for {task.component}: {e}", is_error=True)
                raise

        return await asyncio.to_thread(sync_download)

    @staticmethod
    def _remove_part_file(task: DownloadTask) -> None:
        part_path = task.dest.with_suffix(task.dest.suffix + ".part")
        try:
            part_path.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass
