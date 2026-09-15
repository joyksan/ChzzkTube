"""프로젝트 로컬 pip 오버레이(.pylib) 계약 테스트 — 네트워크 없음.

[계약]
- _pylib_root()는 <repo>/.pylib 고정 (CHZZKTUBE_PYLIB_DIR로만 오버라이드)
- bootstrap()은 sys.path 선두 1회 삽입, 중복 안전
- _extract_pylib_whl()은 prefix dist-info만 정리 (venv 무관)
"""
import os
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


def test_pylib_bootstrap_inserts_first(tmp_path, monkeypatch):
    import sys

    from chzzktube.infra.pylib_bootstrap import bootstrap

    target = os.path.abspath(str(tmp_path / "ov"))
    monkeypatch.setenv("CHZZKTUBE_PYLIB_DIR", target)
    got = bootstrap(clear_caches=False)
    assert os.path.abspath(got) == target
    assert sys.path[0] == target
    sys.path.remove(target)


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