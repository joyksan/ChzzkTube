"""stdlib 안전 추출 / macOS bottle relocatable 계약.

검증 대상:
1. Zip Slip(path traversal) 차단
2. tar 추출 시 filter="data" 경유 (또는 3.12 미만 폴백 traversal 검사)
3. relocatable(:any_skip_relocation) 아닌 bottle은 채택 금지 → dyld 실패 위장 차단
4. bottle 전멸 시 evermeet 정적 폴백을 호출하지 않음 (명시적 FAIL)
"""
import hashlib
import io
import json
import tarfile
import zipfile

import pytest

import chzzktube.infra.components as components


class _FakeResponse:
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


def test_safe_zip_extraction_rejects_path_traversal(tmp_path):
    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("../escape", b"bad")

    with pytest.raises(ValueError):
        components._safe_extract(archive, "zip", tmp_path / "dest")


def test_safe_tar_extraction_rejects_path_traversal(tmp_path):
    archive = tmp_path / "unsafe.tar"
    with tarfile.open(archive, "w") as tf:
        info = tarfile.TarInfo("../escape")
        info.size = 3
        tf.addfile(info, io.BytesIO(b"bad"))

    with pytest.raises(ValueError):
        components._safe_extract(archive, "tar", tmp_path / "dest")


def test_safe_tar_extraction_preserves_nested_bin(tmp_path):
    archive = tmp_path / "safe.tar"
    with tarfile.open(archive, "w") as tf:
        data = tarfile.TarInfo("Cellar/ffmpeg/9.0.2/bin/ffmpeg")
        data.size = 3
        tf.addfile(data, io.BytesIO(b"bin"))

    dest = components._safe_extract(archive, "tar", tmp_path / "dest")

    assert (dest / "Cellar" / "ffmpeg" / "9.0.2" / "bin" / "ffmpeg").read_bytes() == b"bin"


def _formula(cellar):
    bottle_bytes = b"bottle"
    return {
        "bottle": {
            "stable": {
                "files": {
                    "arm64_sequoia": {
                        "url": "https://ghcr.invalid/bottle.tar.gz",
                        "sha256": hashlib.sha256(bottle_bytes).hexdigest(),
                        "cellar": cellar,
                    }
                }
            }
        }
    }


def _arm64_sequoia(monkeypatch, tmp_path, formula):
    monkeypatch.setattr(components.platform, "machine", lambda: "arm64")
    monkeypatch.setattr(components.platform, "release", lambda: "24.0.0")
    monkeypatch.setattr(
        components.urllib.request,
        "urlopen",
        lambda request, timeout: _FakeResponse(json.dumps(formula).encode()),
    )
    monkeypatch.setattr(components.config, "writable_base", lambda: str(tmp_path))


def test_macos_bottle_rejects_non_relocatable_cellar(monkeypatch, tmp_path):
    """/opt/homebrew/Cellar bottle은 dyld 실패 확정 → 채택하지 않는다."""
    _arm64_sequoia(monkeypatch, tmp_path, _formula("/opt/homebrew/Cellar"))
    monkeypatch.setattr(components, "_verify_ffmpeg", lambda path: True)

    result = components._ensure_ffmpeg_macos(lambda event: None, force=True)

    assert result is not None
    assert "relocatable" in result


def test_macos_bottle_failure_does_not_invoke_evermeet(monkeypatch, tmp_path):
    """bottle 전멸 시 evermeet 정적 폴백을 시도하지 않는다 (v3.8.4)."""
    assert not hasattr(components, "_ensure_ffmpeg_macos_static")
    assert not hasattr(components, "_FFMPEG_EVERMEET_URLS")

    _arm64_sequoia(monkeypatch, tmp_path, _formula(":any_skip_relocation"))
    monkeypatch.setattr(components, "_verify_ffmpeg", lambda path: False)

    result = components._ensure_ffmpeg_macos(lambda event: None, force=True)

    assert result is not None
    assert "exhausted" in result or "failed" in result


def test_macos_bottle_missing_sha256_is_rejected(monkeypatch, tmp_path):
    """SHA-256이 없는 bottle은 검증 불가 → 채택 금지."""
    formula = _formula(":any_skip_relocation")
    formula["bottle"]["stable"]["files"]["arm64_sequoia"].pop("sha256")
    _arm64_sequoia(monkeypatch, tmp_path, formula)
    monkeypatch.setattr(components, "_verify_ffmpeg", lambda path: True)

    result = components._ensure_ffmpeg_macos(lambda event: None, force=True)

    assert result is not None
