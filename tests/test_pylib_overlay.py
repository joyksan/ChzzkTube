"""프로젝트 로컬 pip 오버레이(.pylib) 계약 테스트 — 네트워크 없음.

[계약]
- pylib_overlay_path()는 SSOT: 환경변수 > Frozen(writable_base) > Dev(repo root)
- _pylib_root()는 하위 호환 별칭 (Dev 기본값만 반환)
- bootstrap()은 sys.path 선두 1회 삽입, 중복 안전
- _extract_pylib_whl()은 prefix dist-info만 정리 (venv 무관)
"""
import os
import sys
import zipfile


def _make_fake_whl(path, code_dir, version, tmp_path):
    """.whl(사실상 zip) 최소 골격 생성: <code_dir>/__init__.py + <code_dir>-<version>.dist-info."""
    code = f"{code_dir}/__init__.py"
    dist = f"{code_dir}-{version}.dist-info/METADATA"
    with zipfile.ZipFile(str(path), "w") as zf:
        zf.writestr(code, "# fake\n")
        zf.writestr(dist, f"Name: {code_dir}\nVersion: {version}\n")
    return str(path)


def test_pylib_overlay_path_is_project_local(tmp_path, monkeypatch):
    from chzzktube.core.config import _repo_root, pylib_overlay_path

    monkeypatch.delenv("CHZZKTUBE_PYLIB_DIR", raising=False)
    path = os.path.abspath(pylib_overlay_path())
    assert os.path.basename(path) == ".pylib"
    # chzzktube/core 바로 위 2단 = 저장소 루트 기준 (<repo>/.pylib 계약)
    assert os.path.dirname(path) == _repo_root()
    assert os.path.isfile(os.path.join(_repo_root(), "main.py"))


def test_pylib_overlay_env_override(tmp_path, monkeypatch):
    from chzzktube.core.config import pylib_overlay_path

    monkeypatch.setenv("CHZZKTUBE_PYLIB_DIR", str(tmp_path / "custom"))
    assert os.path.abspath(pylib_overlay_path()) == os.path.abspath(
        str(tmp_path / "custom")
    )


def test_pylib_overlay_frozen_mode_uses_writable_base(tmp_path, monkeypatch):
    """Frozen 모드에서 pylib_overlay_path()가 writable_base()/.pylib 반환하는지 검증."""
    from chzzktube.core.config import _repo_root, pylib_overlay_path, writable_base

    monkeypatch.delenv("CHZZKTUBE_PYLIB_DIR", raising=False)
    # sys.frozen 시뮬레이션
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    path = os.path.abspath(pylib_overlay_path())
    expected = os.path.join(writable_base(), ".pylib")
    assert path == os.path.abspath(expected)
    assert path != _repo_root()  # Dev 경로와 달라야 함


def test_pylib_overlay_frozen_mode_env_override_priority(tmp_path, monkeypatch):
    """Frozen 모드에서도 환경변수 오버라이드가 최우선 적용되는지 검증."""
    from chzzktube.core.config import pylib_overlay_path

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("CHZZKTUBE_PYLIB_DIR", str(tmp_path / "custom_frozen"))

    path = os.path.abspath(pylib_overlay_path())
    assert path == os.path.abspath(str(tmp_path / "custom_frozen"))


def test_pylib_bootstrap_inserts_first(tmp_path, monkeypatch):
    from chzzktube.infra.pylib_bootstrap import bootstrap

    target = os.path.abspath(str(tmp_path / "ov"))
    monkeypatch.setenv("CHZZKTUBE_PYLIB_DIR", target)
    got = bootstrap(clear_caches=False)
    assert os.path.abspath(got) == target
    assert sys.path[0] == target
    sys.path.remove(target)


def test_pylib_bootstrap_frozen_mode_creates_writable_base_pylib(tmp_path, monkeypatch):
    """Frozen 모드에서 bootstrap()이 writable_base()/.pylib 생성하고 sys.path에 삽입하는지 검증."""
    from chzzktube.core.config import writable_base
    from chzzktube.infra.pylib_bootstrap import bootstrap

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.delenv("CHZZKTUBE_PYLIB_DIR", raising=False)

    expected_path = os.path.join(writable_base(), ".pylib")
    # 기존 경로 정리
    if expected_path in sys.path:
        sys.path.remove(expected_path)
    if os.path.exists(expected_path):
        import shutil
        shutil.rmtree(expected_path, ignore_errors=True)

    got = bootstrap(clear_caches=False)
    assert os.path.abspath(got) == os.path.abspath(expected_path)
    assert sys.path[0] == os.path.abspath(expected_path)
    assert os.path.isdir(expected_path)
    sys.path.remove(os.path.abspath(expected_path))


def test_extract_pylib_whl_cleans_old_distinfo(tmp_path):
    from chzzktube.infra.updater import _extract_pylib_whl

    root = tmp_path / "pylib"
    root.mkdir()
    (root / "streamlink").mkdir()
    old = root / "streamlink-8.5.0.dist-info"
    old.mkdir()
    whl = _make_fake_whl(tmp_path / "s.whl", "streamlink", "8.6.0", tmp_path)
    assert _extract_pylib_whl(whl, str(root), "streamlink-") is True
    assert (root / "streamlink-8.6.0.dist-info").is_dir()
    assert not (root / "streamlink-8.5.0.dist-info").exists()


def test_extract_pylib_whl_invalid_zip(tmp_path):
    from chzzktube.infra.updater import _extract_pylib_whl

    bad = tmp_path / "bad.whl"
    bad.write_bytes(b"not-a-zip")
    assert _extract_pylib_whl(str(bad), str(tmp_path), "streamlink-") is False