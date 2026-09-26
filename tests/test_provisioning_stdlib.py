"""Provisioning bootstrap — stdlib-only HTTP contract tests."""
import asyncio
import hashlib
import importlib
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chzzktube.infra.provisioning.resolver import ComponentSpec, ComponentType, Mirror, get_platform_asset_filters
from chzzktube.infra.node_provider import _platform_node_url


def _import_without_httpx(module_name):
    """httpx가 설치되지 않은 frozen/bootstrap 환경을 모사해 모듈을 import한다."""
    real_import = __import__

    def import_without_httpx(name, *args, **kwargs):
        if name == "httpx" or name.startswith("httpx."):
            raise ModuleNotFoundError("No module named 'httpx'")
        return real_import(name, *args, **kwargs)

    sys.modules.pop("httpx", None)
    sys.modules.pop(module_name, None)
    with patch("builtins.__import__", side_effect=import_without_httpx):
        return importlib.import_module(module_name)


def _response(body, *, status=200, headers=None):
    response = MagicMock()
    response.status = status
    response.headers = headers or {}
    response.read.side_effect = [body, b""]
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    return response


class TestParallelDownloaderStdlib:
    def test_imports_and_downloads_without_httpx(self, tmp_path):
        downloader_module = _import_without_httpx(
            "chzzktube.infra.provisioning.downloader"
        )
        payload = b"bootstrap payload"
        destination = tmp_path / "package.whl"
        task = downloader_module.DownloadTask(
            component="test",
            url="https://packages.invalid/package.whl",
            dest=destination,
            expected_sha256=hashlib.sha256(payload).hexdigest(),
        )
        progress = []

        async def record_progress(component, downloaded, total, speed_bps=0.0, eta_sec=0.0):
            progress.append((component, downloaded, total))

        async def run_download():
            downloader = downloader_module.ParallelDownloader(
                max_retries=1,
                progress_cb=record_progress,
            )
            with patch(
                "chzzktube.infra.provisioning.downloader.urllib.request.urlopen",
                return_value=_response(
                    payload, headers={"Content-Length": str(len(payload))}
                ),
            ):
                return await downloader.download_all([task])

        results = asyncio.run(run_download())

        assert len(results) == 1
        assert results[0].success is True
        assert results[0].bytes_downloaded == len(payload)
        assert results[0].sha256 == hashlib.sha256(payload).hexdigest()
        assert destination.read_bytes() == payload
        assert not destination.with_name(destination.name + ".part").exists()
        assert progress[-1] == ("test", len(payload), len(payload))

    def test_hash_mismatch_is_failure_and_removes_part_file(self, tmp_path):
        downloader_module = _import_without_httpx(
            "chzzktube.infra.provisioning.downloader"
        )
        destination = tmp_path / "package.whl"
        task = downloader_module.DownloadTask(
            component="test",
            url="https://packages.invalid/package.whl",
            dest=destination,
            expected_sha256="0" * 64,
        )

        async def run_download():
            downloader = downloader_module.ParallelDownloader(max_retries=1)
            with patch(
                "chzzktube.infra.provisioning.downloader.urllib.request.urlopen",
                return_value=_response(b"tampered"),
            ):
                return await downloader.download_all([task])

        results = asyncio.run(run_download())
        part_path = destination.with_name(destination.name + ".part")

        assert results[0].success is False
        assert "SHA256 mismatch" in results[0].error
        assert not destination.exists()
        assert not part_path.exists()

    def test_http_and_network_failures_are_results_and_clean_part_file(self, tmp_path):
        downloader_module = _import_without_httpx(
            "chzzktube.infra.provisioning.downloader"
        )
        destination = tmp_path / "package.whl"
        task = downloader_module.DownloadTask(
            component="test",
            url="https://packages.invalid/package.whl",
            dest=destination,
        )

        async def run_download(side_effect):
            downloader = downloader_module.ParallelDownloader(max_retries=1)
            with patch(
                "chzzktube.infra.provisioning.downloader.urllib.request.urlopen",
                side_effect=side_effect,
            ):
                return await downloader.download_all([task])

        http_results = asyncio.run(run_download(OSError("HTTP Error 503")))
        network_results = asyncio.run(run_download(ConnectionError("offline")))

        assert http_results[0].success is False
        assert "HTTP Error 503" in http_results[0].error
        assert network_results[0].success is False
        assert "offline" in network_results[0].error
        assert not destination.exists()
        assert not destination.with_name(destination.name + ".part").exists()


_test_platform_token = get_platform_asset_filters()[0]
_test_node_url = _platform_node_url("v22.1.0")
_test_node_file = _test_node_url.split("/")[-1]
_test_node_archive = "tar.gz" if "darwin" in _test_node_url else "zip"


class TestProvisioningManagerStdlib:
    def test_manager_imports_without_httpx(self):
        manager_module = _import_without_httpx(
            "chzzktube.infra.provisioning.manager"
        )
        assert hasattr(manager_module, "ProvisioningManager")

    @pytest.mark.parametrize(
        ("method_name", "payload", "expected"),
        [
            (
                "_fetch_from_pypi",
                {
                    "info": {"version": "1.2.3"},
                    "releases": {
                        "1.2.3": [
                            {"filename": "demo-1.2.3-py3-none-any.whl", "url": "https://packages.invalid/demo.whl", "digests": {"sha256": "a" * 64}},
                        ]
                    },
                },
                (
                    "1.2.3",
                    "https://packages.invalid/demo.whl",
                    "a" * 64,
                    "pypi",
                    "whl",
                ),
            ),
            (
                "_fetch_from_github",
                {
                    "tag_name": "v1.2.3",
                    "assets": [
                        {"name": f"demo-1.2.3-{_test_platform_token}.zip", "browser_download_url": "https://releases.invalid/demo.zip"},
                    ],
                },
                (
                    "1.2.3",
                    "https://releases.invalid/demo.zip",
                    None,
                    "github",
                    "zip",
                ),
            ),
            (
                "_fetch_from_nodejs",
                [{"version": "v22.1.0"}],
                (
                    "v22.1.0",
                    _test_node_url,
                    "93904abf2b6afd0dc2a7c2947a83e10ed65cc39171db17663edb6f763aaa5a57",
                    "nodejs.org",
                    _test_node_archive,
                ),
            ),
        ],
    )
    def test_metadata_fetchers_work_without_httpx(
        self, method_name, payload, expected
    ):
        # 이제 Planner 클래스에서 테스트 (리팩토링 후)
        planner_module = _import_without_httpx(
            "chzzktube.infra.provisioning.planner"
        )
        planner = planner_module.Planner.__new__(planner_module.Planner)
        from pathlib import Path
        planner.base_dir = Path("/tmp")
        from chzzktube.infra.provisioning.manifest import ProvisionManifest
        planner.manifest = ProvisionManifest()
        planner.overlay_root = Path("/tmp/.pylib")
        method = getattr(planner, method_name)
        spec = SimpleNamespace(name="demo", asset_filters=())
        mirror = SimpleNamespace(
            name="github" if method_name == "_fetch_from_github" else (
                "nodejs.org" if method_name == "_fetch_from_nodejs" else "pypi"
            ),
            url_template="https://metadata.invalid/{pkg}.json",
        )

        async def run_fetch():
            planner._fetch_json = AsyncMock(return_value=payload)
            planner._fetch_text = AsyncMock(return_value=f"93904abf2b6afd0dc2a7c2947a83e10ed65cc39171db17663edb6f763aaa5a57  {_test_node_file}")
            return await method(spec, mirror)

        assert asyncio.run(run_fetch()) == expected

    def test_fetch_latest_falls_back_to_next_mirror(self):
        # Planner.resolve() 메서드 테스트 (리팩토링 후)
        planner_module = _import_without_httpx(
            "chzzktube.infra.provisioning.planner"
        )
        planner = planner_module.Planner.__new__(planner_module.Planner)
        from pathlib import Path
        planner.base_dir = Path("/tmp")
        from chzzktube.infra.provisioning.manifest import ProvisionManifest
        planner.manifest = ProvisionManifest()
        planner.overlay_root = Path("/tmp/.pylib")
        mirrors = (
            Mirror(
                name="pypi",
                url_template="https://metadata.invalid/{pkg}.json",
                priority=0,
            ),
            Mirror(
                name="github",
                url_template="https://metadata.invalid/releases/latest",
                priority=1,
            ),
        )
        spec = ComponentSpec(
            name="demo",
            type=ComponentType.PYTHON_PKG,
            mirrors=mirrors,
            verify_cmd=(),
            install_rel_path=".pylib",
            asset_filters=(),
        )

        async def run_resolve():
            async def fetch_from_pypi(spec, mirror):
                assert mirror is mirrors[0]
                return None

            async def fetch_from_github(spec, mirror):
                assert mirror is mirrors[1]
                return (
                    "1.2.3",
                    "https://packages.invalid/demo.whl",
                    None,
                    "github",
                    "zip",
                )

            planner._fetch_from_pypi = fetch_from_pypi
            planner._fetch_from_github = fetch_from_github
            return await planner._fetch_latest(spec)

        assert asyncio.run(run_resolve()) == (
            "1.2.3",
            "https://packages.invalid/demo.whl",
            None,
            "github",
            "zip",
        )