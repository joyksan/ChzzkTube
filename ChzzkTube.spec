# -*- mode: python ; coding: utf-8 -*-

import json
import os
import shutil


def _plugin_dir():
    """yt_dlp_plugins 네임스페이스 플러그인 폴더(site-packages 바로 아래)를 찾는다.

    frozen 빌드에서 PEP420 네임스페이스 패키지는 PYZ 내 find_spec 이 실패하는
    사례가 많으므로, 폴더째 datas 로 심어 _MEIPASS(sys.path) 파일시스템
    탐색으로 로드되도록 한다. (yt-dlp 플러그인 로더도 동일 경로로 탐색)
    """
    try:
        import importlib.util
        spec = importlib.util.find_spec("yt_dlp_plugins.extractor.getpot_bgutil")
        if spec and spec.origin:
            # .../site-packages/yt_dlp_plugins/extractor/getpot_bgutil.py → yt_dlp_plugins 폴더
            d = os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.abspath(spec.origin))))
            if os.path.isdir(os.path.join(d, "yt_dlp_plugins")):
                return os.path.join(d, "yt_dlp_plugins")
    except Exception:
        pass
    try:
        import importlib.metadata as im
        dist = im.distribution("bgutil-ytdlp-pot-provider")
        for f in (dist.files or []):
            if f.path and f.path.startswith("yt_dlp_plugins/"):
                return os.path.dirname(os.path.dirname(f.locate()))
    except Exception:
        pass
    return None


def _bundle_node_exe():
    """시스템 node 실행 파일 경로. (번들용 — 미설치 시 None)

    node.exe 단일 실행 파일만으로 서버 기동이 가능하므로 이 바이너리 하나를
    _internal/node.exe 로 심는다. (npm/npx 가 필요한 자동 빌드는 원본 실행 전용)
    """
    return shutil.which("node")


def _stage_pruned_server(stage_root):
    """번들용 서버 스테이징: build/ + package.json + node_modules(런타임 deps만).

    npm ci 는 devDependencies(typescript, @swc, prettier, jsdom, canvas 등
    100MB 이상)까지 설치하므로, package.json 의 dependencies /
    optionalDependencies / peerDependencies 를 시작점으로 노드 모듈 의존
    그래프를 고정점까지 추적해 런타임에 필요한 패키지만 복사한다.
    반환: 스테이징된 bgutil-ytdlp-pot-provider 폴더 경로 (실패 시 None)
    """
    srv_src = os.path.join(_server_src, "server")
    srv_dst = os.path.join(stage_root, "bgutil-ytdlp-pot-provider", "server")
    try:
        if os.path.isdir(stage_root):
            shutil.rmtree(stage_root, ignore_errors=True)
        os.makedirs(srv_dst, exist_ok=True)
        shutil.copytree(os.path.join(srv_src, "build"),
                        os.path.join(srv_dst, "build"))
        shutil.copy2(os.path.join(srv_src, "package.json"),
                     os.path.join(srv_dst, "package.json"))
        with open(os.path.join(srv_src, "package.json"), encoding="utf-8") as fh:
            pj = json.load(fh)
        nm_src = os.path.join(srv_src, "node_modules")
        if not os.path.isdir(nm_src):
            return None
        keep = set(pj.get("dependencies") or {})
        keep |= set(pj.get("optionalDependencies") or {})
        keep |= set(pj.get("peerDependencies") or {})
        nm_dst = os.path.join(srv_dst, "node_modules")
        queue = sorted(keep)
        while queue:
            name = queue.pop(0)
            src = os.path.join(nm_src, *name.split("/"))
            if not os.path.isdir(src):
                continue  # 미설치 optional 등 — 무시
            dst = os.path.join(nm_dst, *name.split("/"))
            if not os.path.isdir(dst):
                shutil.copytree(src, dst)
            try:
                with open(os.path.join(src, "package.json"), encoding="utf-8") as fh:
                    d = json.load(fh)
            except Exception:
                continue
            for key in ("dependencies", "optionalDependencies", "peerDependencies"):
                for dep in d.get(key) or {}:
                    if dep not in keep:
                        keep.add(dep)
                        queue.append(dep)
        return os.path.dirname(srv_dst)
    except Exception:
        shutil.rmtree(stage_root, ignore_errors=True)
        return None


# --- PO Token(bgutil) 포터블 무결 번들 -------------------------------------------------
# pot_provider.server_home() 은 포터블에서 <exe>/_internal/bgutil-ytdlp-pot-provider 를
# 사용하므로, 서버 빌드물을 이 위치로 심어야 자동 기동된다. exe 폴더 밖은 쓰지 않는다.
_server_src = os.path.join(os.path.expanduser("~"), "bgutil-ytdlp-pot-provider")
_datas = [("icon.ico", ".")]
if os.path.isfile(os.path.join(_server_src, "server", "build", "main.js")):
    # 런타임 deps 만 프루닝한 서버 빌드물 (node_modules 포함 — 빌드 생략 가능)
    _staged = _stage_pruned_server(os.path.join(SPECPATH, "_pot_stage"))
    if _staged:
        _datas.append((_staged, "bgutil-ytdlp-pot-provider"))
        print("[spec] bgutil 서버 번들(런타임 deps 프루닝):", _staged)

_node_bundle = _bundle_node_exe()
if _node_bundle:
    # 번들 node.exe → _internal/node.exe (pot_provider.node_exe() 가 최우선으로 찾음)
    _datas.append((_node_bundle, "."))
    print("[spec] 번들 node.exe:", _node_bundle)

_plugin_src = _plugin_dir()
if _plugin_src and os.path.isdir(_plugin_src):
    # yt_dlp_plugins 네임스페이스 플러그인(getpot_bgutil*) — yt-dlp PO Provider Framework
    _datas.append((_plugin_src, "yt_dlp_plugins"))
    print("[spec] 플러그인 번들:", _plugin_src)

_hiddenimports = [
    "yt_dlp_plugins.extractor.getpot_bgutil",
    "yt_dlp_plugins.extractor.getpot_bgutil_http",
    "yt_dlp_plugins.extractor.getpot_bgutil_script",
]


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=_datas,
    hiddenimports=_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ChzzkTube',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['icon.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ChzzkTube',
)