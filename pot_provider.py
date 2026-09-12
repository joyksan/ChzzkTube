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
from po_client import (  # L0 leaf — 계층 역전 방지
    DEFAULT_HOST,
    DEFAULT_PORT,
    extract_video_id,
    fetch_po_token,
    probe_server,
    server_ping,
)
from node_provider import (  # SRP: Node.js 런타임만 담당
    NODE_MIN_MAJOR,
    _NO_WINDOW,
    _node_ver_cache,
    get_writable_base,
    _is_portable,
    _bundle_root,
    node_major_version,
    latest_lts_node_url,
    _platform_node_url,
    npm_exe,
    node_ok,
    node_exe,
    bundled_npm_ok,
    ensure_node_runtime,
)
from pot_server import (  # SRP: bgutil 서버 빌드/기동만 담당
    _SERVER_FALLBACK_VER,
    _TAG_ZIP,
    server_home,
    assign_to_job_object,
    read_server_log_tail,
    latest_server_ver,
    server_installed_ver,
    clean_stale_plugin,
    _wait_port,
    _kill,
    built_server_js,
    pot_readiness,
    acquire_prewarm_lock,
    release_prewarm_lock,
    _spawn_existing,
    download_and_install_source,
    _run_and_stream_log,
    ensure_node_server,
    kill_process_on_port,
)

__all__ = [
    "DEFAULT_HOST", "DEFAULT_PORT", "extract_video_id",
    "fetch_po_token", "probe_server", "server_ping",
    "NODE_MIN_MAJOR", "get_writable_base", "_is_portable", "_bundle_root",
    "node_major_version", "latest_lts_node_url", "_platform_node_url",
    "npm_exe", "node_ok", "node_exe", "bundled_npm_ok", "ensure_node_runtime",
    "server_home", "assign_to_job_object", "read_server_log_tail",
    "latest_server_ver", "server_installed_ver", "clean_stale_plugin",
    "built_server_js", "pot_readiness", "acquire_prewarm_lock",
    "release_prewarm_lock", "_spawn_existing", "download_and_install_source",
    "ensure_node_server", "kill_process_on_port",
]
