"""BtbN resolver and checksum contracts (stdlib-only 수급 계약)."""
import hashlib
import json

import pytest

import chzzktube.infra.components as components


class _FakeResponse:
    """urllib 컨텍스트 매니저 계약을 만족하는 최소 응답 스텁."""

    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, *_args, **_kwargs):
        return self._payload

    def close(self):
        return None


def _asset(name, digest=""):
    return {
        "name": name,
        "browser_download_url": f"https://assets.invalid/{name}",
        "digest": digest,
    }


def test_btbn_resolver_selects_static_platform_asset_and_ignores_github_digest(monkeypatch):
    """GitHub API digest 필드는 사용하지 않고 checksums.sha256 매니페스트만 신뢰한다."""
    release = {
        "tag_name": "latest",
        "assets": [
            _asset("checksums.sha256"),
            _asset(
                "ffmpeg-master-latest-win64-gpl-shared.zip",
                digest="sha256:" + "1" * 64,
            ),
            _asset(
                "ffmpeg-master-latest-win64-gpl.zip",
                digest="sha256:" + "2" * 64,
            ),
            _asset(
                "ffmpeg-master-latest-linux64-gpl.tar.xz",
                digest="sha256:" + "3" * 64,
            ),
        ],
    }
    expected = hashlib.sha256(b"target").hexdigest()

    monkeypatch.setattr(components.platform, "system", lambda: "Windows")
    monkeypatch.setattr(components.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(
        components.urllib.request,
        "urlopen",
        lambda request, timeout: _FakeResponse(json.dumps(release).encode()),
    )
    monkeypatch.setattr(
        components,
        "_fetch_btbn_checksums",
        lambda url, timeout: f"{expected}  ffmpeg-master-latest-win64-gpl.zip\n",
    )

    result = components._resolve_btbn_ffmpeg()

    assert result["asset_name"] == "ffmpeg-master-latest-win64-gpl.zip"
    assert result["sha256"] == expected
    assert result["archive_type"] == "zip"


def test_btbn_resolver_maps_linux_arm64_to_linuxarm64(monkeypatch):
    release = {
        "tag_name": "latest",
        "assets": [
            _asset("checksums.sha256"),
            _asset("ffmpeg-master-latest-linux64-gpl.tar.xz"),
            _asset("ffmpeg-master-latest-linuxarm64-gpl.tar.xz"),
        ],
    }
    expected = hashlib.sha256(b"arm").hexdigest()

    monkeypatch.setattr(components.platform, "system", lambda: "Linux")
    monkeypatch.setattr(components.platform, "machine", lambda: "aarch64")
    monkeypatch.setattr(
        components.urllib.request,
        "urlopen",
        lambda request, timeout: _FakeResponse(json.dumps(release).encode()),
    )
    monkeypatch.setattr(
        components,
        "_fetch_btbn_checksums",
        lambda url, timeout: f"{expected}  ffmpeg-master-latest-linuxarm64-gpl.tar.xz\n",
    )

    result = components._resolve_btbn_ffmpeg()

    assert result["asset_name"] == "ffmpeg-master-latest-linuxarm64-gpl.tar.xz"
    assert result["archive_type"] == "tar.xz"
    assert result["architecture"] == "arm64"


def test_btbn_checksum_parser_requires_exact_asset_name_and_valid_hash():
    target = "ffmpeg-master-latest-linux64-gpl.tar.xz"
    expected = "a" * 64
    manifest = (
        f"{'b' * 64}  {target}-wrong\n"
        f"{expected}  {target}\n"
        "not-a-hash  checksums.sha256\n"
    )

    assert components._parse_btbn_checksums(manifest, target) == expected

    with pytest.raises(ValueError):
        components._parse_btbn_checksums("bad  checksums.sha256\n", target)


def test_btbn_resolver_rejects_unsupported_architecture(monkeypatch):
    monkeypatch.setattr(components.platform, "system", lambda: "Windows")
    monkeypatch.setattr(components.platform, "machine", lambda: "riscv64")

    with pytest.raises(ValueError, match="unsupported architecture"):
        components._resolve_btbn_ffmpeg()
