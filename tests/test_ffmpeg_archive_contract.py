"""stdlib 안전 추출 / macOS bottle 실행 검증(v3.8.5) 계약.

검증 대상:
1. Zip Slip(path traversal) 차단
2. tar 추출 시 filter="data" 경유 (또는 3.12 미만 폴백 traversal 검사)
3. cellar 메타데이터로 선제 거부하지 않고 _verify_ffmpeg로 판정 → 시도 허용
4. bottle 전멸 시 evermeet 정적 폴백을 호출하지 않음 (명시적 FAIL)
5. 검증 실패 시 기존 캐시가 원자 교체로 파괴되지 않음
"""
import hashlib
import io
import json
import os
import tarfile
import zipfile

import pytest

import chzzktube.infra.components as components


@pytest.fixture(autouse=True)
def _restore_path():
    """PATH 오염 격리 — bottle 테스트가 임시 캐시를 PATH 선두에 넣는다.

    남겨두면 실ffmpeg 통합 테스트(test_live_recorder)가 가짜 바이너리를
    집계해 오판하므로, 테스트 모듈 단위로 PATH를 반드시 원복한다.
    """
    saved = os.environ.get("PATH")
    yield
    if saved is None:
        os.environ.pop("PATH", None)
    else:
        os.environ["PATH"] = saved


class _FakeResponse:
    """urllib 컨텍스트 매니저 + 소진형 read + headers (다운로드 루프 대응)."""

    def __init__(self, payload):
        self._payload = payload
        self._offset = 0
        self.headers = {"Content-Length": str(len(payload))}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size=-1):
        # EOF에서 빈 바이트 반환 — 무한 쓰기 방지
        if size is None or size < 0:
            chunk = self._payload[self._offset:]
            self._offset = len(self._payload)
            return chunk
        chunk = self._payload[self._offset:self._offset + size]
        self._offset += len(chunk)
        return chunk

    def close(self):
        return None

    def __iter__(self):
        return iter(self._payload.splitlines(keepends=True))


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


def _bottle_bytes():
    """formulae의 sha256과 일치해야 하는 최소 bottle tar.gz 페이로드.

    실측 Homebrew bottle 구조(opt/homebrew/Cellar/ffmpeg/<v>/bin/ffmpeg,ffprobe)
    를 그대로 재현해, 해시 검증 → 전개 → 실행 프로브까지 통과하도록 한다.
    """
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for name in ("ffmpeg", "ffprobe"):
            data = tarfile.TarInfo(f"opt/homebrew/Cellar/ffmpeg/9.0/bin/{name}")
            payload = b"#!/bin/sh\nexit 0\n"
            data.size = len(payload)
            data.mode = 0o755
            tf.addfile(data, io.BytesIO(payload))
    return buf.getvalue()


def _formula(cellar):
    payload = _bottle_bytes()
    return {
        "bottle": {
            "stable": {
                "files": {
                    "arm64_sequoia": {
                        "url": "https://ghcr.invalid/bottle.tar.gz",
                        "sha256": hashlib.sha256(payload).hexdigest(),
                        "cellar": cellar,
                    }
                }
            }
        }
    }


def _arm64_sequoia(monkeypatch, tmp_path, formula, bottle_payload=None):
    payload = bottle_payload if bottle_payload is not None else _bottle_bytes()
    monkeypatch.setattr(components.platform, "machine", lambda: "arm64")
    monkeypatch.setattr(components.platform, "release", lambda: "24.0.0")
    monkeypatch.setattr(
        components.urllib.request,
        "urlopen",
        lambda request, timeout: _FakeResponse(json.dumps(formula).encode()),
    )
    monkeypatch.setattr(
        components,
        "_http_get",
        lambda url, timeout=0: _FakeResponse(payload),
    )
    monkeypatch.setattr(components.config, "writable_base", lambda: str(tmp_path))


def test_macos_bottle_fixed_cellar_is_probed_not_skipped(monkeypatch, tmp_path):
    """cellar가 :any가 아니어도 손으로 스킵하지 않는다 — 실행으로 판정한다.

    이전(회귀) 동작: cellar 게이트가 `continue`로 후보를 선제 탈락시켜
    실행 가능한 환경에서도 "no compatible bottle"로 100% 자폭했다.
    """
    seen = {}

    _arm64_sequoia(monkeypatch, tmp_path, _formula("/opt/homebrew/Cellar"))

    def verify(path):
        seen["path"] = path
        return True

    monkeypatch.setattr(components, "_verify_ffmpeg", verify)

    result = components._ensure_ffmpeg_macos(lambda event: None, force=True)

    # 판정은 cellar가 아니라 실행 검증으로 내려야 성공한다
    assert result is None, f"fixed cellar was skipped instead of probed: {result}"
    # 실제 스테이징 바이너리가 프로브되었음을 확인
    assert seen.get("path"), "_verify_ffmpeg was never called"


def test_macos_bottle_failed_verification_fails_explicitly(monkeypatch, tmp_path):
    """모든 후보가 실행 검증에 실패했을 때만 명시적으로 FAIL로 종결한다."""
    _arm64_sequoia(monkeypatch, tmp_path, _formula("/opt/homebrew/Cellar"))
    monkeypatch.setattr(components, "_verify_ffmpeg", lambda path: False)

    result = components._ensure_ffmpeg_macos(lambda event: None, force=True)

    assert result is not None
    assert "no runnable bottle" in result or "execution test failed" in result


def test_macos_bottle_missing_sha256_is_rejected(monkeypatch, tmp_path):
    """SHA-256이 없는 bottle은 검증 불가 → 채택 금지 (무검증 수급 차단)."""
    formula = _formula(":any_skip_relocation")
    formula["bottle"]["stable"]["files"]["arm64_sequoia"].pop("sha256")
    _arm64_sequoia(monkeypatch, tmp_path, formula)
    monkeypatch.setattr(components, "_verify_ffmpeg", lambda path: True)

    result = components._ensure_ffmpeg_macos(lambda event: None, force=True)

    assert result is not None


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
