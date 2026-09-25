with open('tests/test_provisioning_stdlib.py', 'r') as f:
    content = f.read()

old = '''class TestProvisioningManagerStdlib:
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
                                       ",
                    "assets": [
                        {"name": "demo-1.2.3-darwin-arm64.zip", "browser_download_url": "https://releases.invalid/demo.zip"},
                    ],
                },
                (
                    "v1.2.3",
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
                    "https://nodejs.org/dist/v22.1.0/node-v22.1.0-darwin-arm64.tar.gz",
                    "93904abf2b6afd0dc2a7c2947a83e10ed65cc39171db17663edb6f763aaa5a57",
                    "nodejs.org",
                    "tar.gz",
                ),
            ),
        ],
    )
    def test_metadata_fetchers_work_without_httpx(
        self, method_name, payload, expected
    ):
        manager_module = _import_without_httpx(
            "chzzktube.infra.provisioning.manager"
        )
        manager = manager_module.ProvisioningManager.__new__(
            manager_module.ProvisioningManager
        )
        method = getattr(manager, method_name)
        spec = SimpleNamespace(name="demo", asset_filters=())
        mirror = SimpleNamespace(
            name="github" if method_name == "_fetch_from_github" else (
                "nodejs.org" if method_name == "_fetch_from_nodejs" else "pypi"
            ),
            url_template="https://metadata.invalid/{pkg}.json",
        )

        async def run_fetch():
            manager._fetch_json = AsyncMock(return_value=payload)
            manager._fetch_text = AsyncMock(return_value="93904abf2b6afd0dc2a7c2947a83e10ed65cc39171db17663edb6f763aaa5a57  node-v22.1.0-darwin-arm64.tar.gz")
            return await method(spec, mirror)

        assert asyncio.run(run_fetch()) == expected

    def test_fetch_latest_falls_back_to_next_mirror(self):
        manager_module = _import_without_httpx(
            "chzzktube.infra.provisioning.manager"
        )
        manager = manager_module.ProvisioningManager.__new__(
            manager_module.ProvisioningManager
        )
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

            manager._fetch_from_pypi = fetch_from_pypi
            manager._fetch_from_github = fetch_from_github
            return await manager._fetch_latest(spec)

        assert asyncio.run(run_resolve()) == (
            "1.2.3",
            "https://packages.invalid/demo.whl",
            None,
            "github",
            "zip",
        )'''

new = '''class TestProvisioningManagerStdlib:
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
                        {"name": "demo-1.2.3-darwin-arm64.zip", "browser_download_url": "https://releases.invalid/demo.zip"},
                    ],
                },
                (
                    "v1.2.3",
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
                    "https://nodejs.org/dist/v22.1.0/node-v22.1.0-darwin-arm64.tar.gz",
                    "93904abf2b6afd0dc2a7c2947a83e10ed65cc39171db17663edb6f763aaa5a57",
                    "nodejs.org",
                    "tar.gz",
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
            planner._fetch_text = AsyncMock(return_value="93904abf2b6afd0dc2a7c2947a83e10ed65cc39171db17663edb6f763aaa5a57  node-v22.1.0-darwin-arm64.tar.gz")
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
        )'''

if old in content:
    content = content.replace(old, new)
    with open('tests/test_provisioning_stdlib.py', 'w') as f:
        f.write(content)
    print('Fixed')
else:
    print('NOT FOUND - trying alternative')
    # Try with slightly different spacing
    import re
    # Find the class definition
    match = re.search(r'class TestProvisioningManagerStdlib:.*?(?=\nclass |\Z)', content, re.DOTALL)
    if match:
        print(f'Found at position {match.start()}')
        print(content[match.start():match.start()+200])
    else:
        print('Class not found with regex')
