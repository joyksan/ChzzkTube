"""pot_provider — PO Token 3개 모듈 재수출 facade.

[구조]
- node_provider.py    : Node.js 런타임 수급 (node_exe, node_ok, ensure_node_runtime 등)
- pot_server.py       : bgutil 서버 빌드/기동 (ensure_node_server, _spawn_existing 등)
- po_client.py        : PO Token HTTP 클라이언트 (L0 leaf, 계층 역전 방지)
- pot_provider.py     : 위 3개 모듈을 재수출(re-export)

[호환성] 기존 `import pot_provider` 코드는 변경 없이 동작.
- update_worker.py: pot_provider.ensure_node_runtime
- updater.py      : pot_provider.node_exe / node_major_version / npm_exe

[제거 이력] POTProviderWorker(QThread)는 POTManager._POTWorker와 중복 선언된
좀비 인터페이스였다 — 런타임 사용 0건(tests/문서 전용), 진실의 근원은
POTManager 단독이다. 서버 수명주기 계약은 POTManager를 본다.
"""

# ── 재수출 (내부 호출 + 외부 역참조 모두 1경로) ──────────────────────────
from chzzktube.infra.node_provider import (  # SRP: Node.js 런타임만 담당
    _NO_WINDOW,  # noqa: F401 — 하위 호환 별칭 — 실체는 platform.spawn_kwargs()
    NODE_MIN_MAJOR,
    _node_ver_cache,  # noqa: F401 — 내부 캐시 참조용
    _platform_node_url,
    bundled_npm_ok,
    ensure_node_runtime,
    latest_lts_node_url,
    node_exe,
    node_major_version,
    node_ok,
    npm_exe,
)
from chzzktube.infra.paths import (  # 공통 경로 헬퍼
    bundle_root,  # noqa: F401 — 외부 재수출용
    get_writable_base,
    is_portable,
)
from chzzktube.infra.po_client import (  # L0 leaf — 계층 역전 방지
    DEFAULT_HOST,
    DEFAULT_PORT,
    extract_video_id,
    fetch_po_token,
    probe_server,
    server_ping,
)
from chzzktube.infra.pot_server import (  # SRP: bgutil 서버 빌드/기동만 담당
    _SERVER_FALLBACK_VER,  # noqa: F401 — 상수 재수출
    _TAG_ZIP,  # noqa: F401 — 상수 재수출
    _kill,  # noqa: F401 — 내부 헬퍼 재수출
    _run_and_stream_log,  # noqa: F401 — 내부 헬퍼 재수출
    _spawn_existing,
    _wait_port,  # noqa: F401 — 내부 헬퍼 재수출
    acquire_prewarm_lock,
    assign_to_job_object,
    built_server_js,
    clean_stale_plugin,
    download_and_install_source,
    ensure_node_server,
    kill_process_on_port,
    latest_server_ver,
    pot_readiness,
    read_server_log_tail,
    release_prewarm_lock,
    server_home,
    server_installed_ver,
)

__all__ = [
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "NODE_MIN_MAJOR",
    "_platform_node_url",
    "_spawn_existing",
    "acquire_prewarm_lock",
    "assign_to_job_object",
    "built_server_js",
    "bundled_npm_ok",
    "clean_stale_plugin",
    "download_and_install_source",
    "ensure_node_runtime",
    "ensure_node_server",
    "extract_video_id",
    "fetch_po_token",
    "get_writable_base",
    "is_portable",
    "kill_process_on_port",
    "latest_lts_node_url",
    "latest_server_ver",
    "node_exe",
    "node_major_version",
    "node_ok",
    "npm_exe",
    "pot_readiness",
    "probe_server",
    "read_server_log_tail",
    "release_prewarm_lock",
    "server_home",
    "server_installed_ver",
    "server_ping",
]
