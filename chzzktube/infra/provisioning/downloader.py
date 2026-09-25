"""Parallel Downloader — stdlib-only async parallel download & retry."""
import asyncio
import hashlib
import random
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable, Optional


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


class ParallelDownloader:
    """urllib 요청을 worker thread로 위임하는 비동기 다운로더."""

    def __init__(
        self,
        max_concurrent: int = 3,
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
                if attempt < self.max_retries - 1:
                    wait_time = (2**attempt) + random.uniform(0, 1)
                    await asyncio.sleep(wait_time)

        return DownloadResult(
            task=task,
            success=False,
            error=str(last_error) if last_error else "Unknown error",
        )

    async def _download_once(self, task: DownloadTask) -> DownloadResult:
        """Worker thread에서 urllib/file I/O를 수행하고 progress를 회수한다."""
        task.dest.parent.mkdir(parents=True, exist_ok=True)
        part_path = task.dest.with_suffix(task.dest.suffix + ".part")
        headers = {"User-Agent": _USER_AGENT}
        if "ghcr.io" in task.url:
            try:
                import json as _json
                repo = "homebrew/core/ffmpeg"
                if "/v2/" in task.url and "/blobs/" in task.url:
                    repo = task.url.split("/v2/")[1].split("/blobs/")[0]
                tok_url = f"https://ghcr.io/token?scope=repository:{repo}:pull"
                tok_req = urllib.request.Request(tok_url, headers={"User-Agent": _USER_AGENT})
                with urllib.request.urlopen(tok_req, timeout=10.0) as tok_resp:
                    tok_data = _json.load(tok_resp)
                    tok = tok_data.get("token")
                    if tok:
                        headers["Authorization"] = f"Bearer {tok}"
            except Exception:
                pass
        loop = asyncio.get_running_loop()
        request = urllib.request.Request(task.url, headers=headers)

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

                    report(downloaded, total, is_final=True)

                computed_sha256 = hasher.hexdigest() if hasher is not None else None
                if hasher is not None and computed_sha256 != task.expected_sha256:
                    raise ValueError(
                        f"SHA256 mismatch: {computed_sha256} != {task.expected_sha256}"
                    )
                part_path.replace(task.dest)
                return DownloadResult(
                    task=task,
                    success=True,
                    bytes_downloaded=downloaded,
                    sha256=computed_sha256,
                )
            except BaseException:
                self._remove_part_file(task)
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
