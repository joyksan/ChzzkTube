"""Parallel Downloader — 병렬 다운로드 & 재시도/폴백.

- httpx + asyncio 기반
- 세마포어로 동시성 제어
- 지수 백오프 + 지터 재시도
- 진행률 하트비트 콜백
- .part 원자적 쓰기
"""
import asyncio
import hashlib
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Awaitable, Optional

import httpx


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


ProgressCallback = Callable[[str, int, int], Awaitable[None]]


class ParallelDownloader:
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
        """모든 태스크 병렬 다운로드."""
        # httpx 클라이언트 공유
        limits = httpx.Limits(max_connections=max_concurrent, max_keepalive_connections=max_concurrent)
        timeout = httpx.Timeout(self.base_timeout, connect=10.0)
        
        async with httpx.AsyncClient(
            limits=limits,
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": "ChzzkTube-Provisioner/1.0"},
        ) as client:
            async def _download_one(task: DownloadTask) -> DownloadResult:
                async with self.semaphore:
                    return await self._download_with_retry(client, task)
            
            return await asyncio.gather(*[_download_one(t) for t in tasks])

    async def _download_with_retry(self, client: httpx.AsyncClient, task: DownloadTask) -> DownloadResult:
        last_error = None
        
        for attempt in range(self.max_retries):
            try:
                async with client.stream("GET", task.url) as resp:
                    resp.raise_for_status()
                    total = int(resp.headers.get("content-length", 0))
                    
                    task.dest.parent.mkdir(parents=True, exist_ok=True)
                    part_path = task.dest.with_suffix(task.dest.suffix + ".part")
                    
                    downloaded = 0
                    sha256 = hashlib.sha256()
                    
                    async with part_path.open("wb") as f:
                        async for chunk in resp.aiter_bytes(1024 * 512):
                            f.write(chunk)
                            sha256.update(chunk)
                            downloaded += len(chunk)
                            if self.progress_cb and total > 0:
                                await self.progress_cb(task.component, downloaded, total)
                    
                    computed_sha256 = sha256.hexdigest()
                    
                    # 해시 검증
                    if task.expected_sha256:
                        if computed_sha256 != task.expected_sha256:
                            raise ValueError(f"SHA256 mismatch: {computed_sha256} != {task.expected_sha256}")
                    
                    # 원자적 이동
                    part_path.replace(task.dest)
                    
                    return DownloadResult(
                        task=task,
                        success=True,
                        bytes_downloaded=downloaded,
                        sha256=computed_sha256,
                    )
                    
            except Exception as e:
                last_error = e
                # part 파일 정리
                part_path = task.dest.with_suffix(task.dest.suffix + ".part")
                if part_path.exists():
                    try:
                        part_path.unlink()
                    except Exception:
                        pass
                
                if attempt < self.max_retries - 1:
                    # 지수 백오프 + 지터
                    wait_time = (2 ** attempt) + random.uniform(0, 1)
                    await asyncio.sleep(wait_time)
        
        return DownloadResult(
            task=task,
            success=False,
            error=str(last_error) if last_error else "Unknown error",
        )