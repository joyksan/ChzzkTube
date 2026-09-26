"""cleanup 모듈 테스트."""
from chzzktube.core import config
from chzzktube.infra import cleanup, components


def test_cleanup_provisioning_artifacts(monkeypatch, tmp_path):
    """프로비저닝 아티팩트 정리 테스트."""
    # 임시 디렉터리를 writable_base로 설정
    test_base = tmp_path / "chzzktube_test"
    test_base.mkdir()
    
    # ffmpeg .part 파일 생성
    ffmpeg_dir = test_base / "ffmpeg"
    ffmpeg_dir.mkdir()
    (ffmpeg_dir / "ffmpeg.part").write_text("temp")
    
    # node 아카이브 생성
    (test_base / "node_portable.zip").write_text("archive")
    (test_base / "node_portable.tar.gz").write_text("archive")
    
    # pot prewarm 락 생성
    pot_dir = test_base / "pot"
    pot_dir.mkdir()
    (pot_dir / ".prewarm.lock").write_text("lock")
    
    # components 루트 .part 파일 생성 (CHZZKTUBE_COMPONENTS_DIR로 설정)
    components_root = test_base / "components"
    components_root.mkdir()
    (components_root / "ffmpeg.part").write_text("temp")
    (components_root / "ffmpeg.tar.xz").write_text("archive")
    (components_root / "ffmpeg.zip").write_text("archive")
    
    # 전역 .part 파일
    (test_base / "random.part").write_text("temp")
    
    # config.writable_base를 모킹
    monkeypatch.setattr(config, "writable_base", lambda: str(test_base))
    # components_root도 모킹
    monkeypatch.setattr(components, "components_root", lambda: str(components_root))
    
    # cleanup 실행
    cleanup.cleanup_provisioning_artifacts()
    
    # 모든 아티팩트가 정리되었는지 확인
    assert not (ffmpeg_dir / "ffmpeg.part").exists()
    assert not (test_base / "node_portable.zip").exists()
    assert not (test_base / "node_portable.tar.gz").exists()
    assert not (pot_dir / ".prewarm.lock").exists()
    assert not (components_root / "ffmpeg.part").exists()
    assert not (components_root / "ffmpeg.tar.xz").exists()
    assert not (components_root / "ffmpeg.zip").exists()
    assert not (test_base / "random.part").exists()


def test_cleanup_on_startup(monkeypatch, tmp_path):
    """기동 시 정리 테스트."""
    test_base = tmp_path / "chzzktube_test"
    test_base.mkdir()
    (test_base / "test.part").write_text("temp")
    
    monkeypatch.setattr(config, "writable_base", lambda: str(test_base))
    
    cleanup.cleanup_on_startup()
    
    assert not (test_base / "test.part").exists()


def test_cleanup_on_shutdown(monkeypatch, tmp_path):
    """종료 시 정리 테스트."""
    test_base = tmp_path / "chzzktube_test"
    test_base.mkdir()
    (test_base / "test.part").write_text("temp")
    
    monkeypatch.setattr(config, "writable_base", lambda: str(test_base))
    
    cleanup.cleanup_on_shutdown()
    
    assert not (test_base / "test.part").exists()