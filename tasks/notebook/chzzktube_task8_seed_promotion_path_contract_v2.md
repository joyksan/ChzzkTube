# 🤖 [Code LM 전용] TASK 8: SSOT 경로 계약 최적화 및 시드 승격 하이브리드 안전망 (v3.12.5 개정판)

> **문서 버전**: v2.0 (2026-09-26)  
> **적용 코드베이스**: ChzzkTube v3.12.5  
> **핵심 목표**: v3.8.2 이후 정립된 SSOT(Single Source of Truth) 경로 단일화 규약과 v3.11.0~v3.12.5 프로비저닝 파이프라인(Planner/Executor/Committer)을 완벽히 정합시켜, **오프라인 초도 실행 불능(Zero-Offline Disaster)**, **Node.js/FFmpeg 탐색 시 os.walk I/O 성능 병목**, 및 **캐시 루트 네임스페이스 파편화**를 원천 차단하는 **시드 승격 하이브리드 경로 계약(Seed-Promotion Hybrid Path Contract)**을 수립함.

---

## 📌 1. 개요 및 배경

v3.8.2부터 ChzzkTube는 `if is_frozen():` 조건문이 호출부 곳곳에 산재하는 문제를 해결하기 위해 `config.pylib_overlay_path()` 및 `config.writable_base()`를 단일 진실 공급원(SSOT)으로 정립했습니다.

그러나 v3.11.0~v3.12.5 대규모 프로비저닝 리팩토링 및 실무 배포 환경에서는 다음 3가지 핵심 과제가 제기되었습니다:
1. **오프라인 포터블 초도 실행 (Zero-Offline Disaster)**:
   인터넷 연결이 차단된 상태에서 포터블 ZIP을 받아 처음 기동할 경우, `<writable_base>/components/`가 비어 있어 온라인 다운로드 수급에 실패(`DEPS FAIL`)하는 문제.
2. **I/O 성능 병목 (TTI 지연)**:
   `node_exe()` 또는 `ffmpeg_exe()`가 매 기동 시마다 `node_modules`나 `cz_*` 임시 폴더 수천 개를 `os.walk()`로 순회하여 백신 실시간 감시 지연 및 기동 프레임을 갉아먹는 문제.
3. **네임스페이스 파편화**:
   `<writable_base>/ffmpeg/`, `<writable_base>/node/`, `<writable_base>/bgutil-ytdlp-pot-provider/` 등 최상위 캐시 경로가 산재해 관리 및 백업/삭제 시 혼선을 초과하던 문제.

---

## 🛠️ 2. 핵심 아키텍처 규약 (v3.12.5)

### 1) [I/O 성능 최적화] Fast-Path 우선 검사 (0ms Lookup)
- 정규 설치 위치(`bin/node` / `node.exe` 또는 `bin/ffmpeg` / `ffmpeg.exe`)를 `os.path.isfile()`로 1회 최우선 단일 검사(Fast-Path)하여 **I/O 오버헤드를 0ms로 단축**.
- 정규 경로 체크 실패 시에만 중첩 전개 대응용 `os.walk()` (Slow-Path)를 제한적으로 수행하며, 이때 `cz_*`, `.tmp`, `temp` 등 임시 디렉터리는 탐색 대상에서 즉시 제외.

### 2) [오프라인 구원책] 번들 시드 승격 (Seed Promotion)
- 런타임 코드가 `_MEIPASS`를 직접 참조해 로직을 오염시키는 행위(Isolation 위반)는 100% 금지함.
- 대신, `<writable_base>/components/`가 비어있고 번들(`bundle_root()`)에 동봉된 시드 자산(`seed_node`, `seed_ffmpeg` 등)이 존재할 경우, 최초 1회 `<writable_base>/components/` 하위로 원자적 복사(`shutil.copytree`)하여 **캐시 자산으로 승격(Seed Promotion)**시킴.

### 3) [네임스페이스 단일화 & cleanup 연동]
- 모든 의존성 컴포넌트의 캐시 루트를 `components_root()` (`<writable_base>/components/`) 하위로 일원화함.
  - Node.js: `<writable_base>/components/node/` (또는 `<writable_base>/node/`)
  - FFmpeg: `<writable_base>/components/ffmpeg/` (`bin/ffmpeg` 배치)
  - POT Server: `<writable_base>/bgutil-ytdlp-pot-provider/` (또는 `<writable_base>/components/pot/`)
  - 독립 실행형 yt-dlp: `<writable_base>/bin/` (`yt_dlp_binary.py` 전담)
  - Python 패키지 오버레이: `config.pylib_overlay_path()` (`<writable_base>/.pylib`)
- **자동 정리 (cleanup.py)**: 기동(`cleanup_on_startup()`) 및 종료(`cleanup_on_shutdown()`) 시 `cz_*` 임시 디렉터리, `.part` 다운로드 파편, `.prewarm.lock` 락 파일 자동 소거.

---

## 💻 3. 모듈별 상세 구현 명세 (v3.12.5)

### ① `chzzktube/infra/paths.py` - 네임스페이스 및 번들 헬퍼
```python
# chzzktube/infra/paths.py - 공통 경로/런타임 헬퍼 (v3.12.5)
from __future__ import annotations
import os
import sys
from chzzktube.core import config

def get_writable_base() -> str:
    """사용자 환경에서 쓰기 권한이 100% 보장되는 로컬 앱 데이터 디렉터리 반환."""
    path = config.writable_base()
    os.makedirs(path, exist_ok=True)
    return path

def is_portable() -> bool:
    """PyInstaller(frozen) 패키징 여부."""
    return bool(getattr(sys, "frozen", False))

def bundle_root() -> str | None:
    """포터블에서 번들 데이터가 풀린 디렉터리 (onedir) _MEIPASS."""
    if is_portable():
        return getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(sys.executable)))
    return None

def components_root() -> str:
    """의존성 컴포넌트 통합 최상위 디렉터리 (<writable_base>/components)."""
    env = os.environ.get("CHZZKTUBE_COMPONENTS_DIR")
    if env:
        return env
    return os.path.join(get_writable_base(), "components")

def get_component_dir(name: str) -> str:
    """하위 컴포넌트 전용 경로 리졸버 (예: components/node, components/ffmpeg)."""
    return os.path.join(components_root(), name)
```

### ② `chzzktube/infra/node_provider.py` - Fast-Path & 시드 승격
```python
# chzzktube/infra/node_provider.py - Node.js 런타임 수급 (v3.12.5)
import os
import shutil
from chzzktube.infra.platform import exe_suffix, is_windows as _np_is_win
from chzzktube.infra.paths import bundle_root, get_writable_base, components_root

NODE_MIN_MAJOR = 22

def node_exe() -> str | None:
    """PO Token 서버 기동용 node 탐색 - Fast-path 우선 + cz_* 예외 + 시드 승격."""
    _exe_s = exe_suffix()
    exe_name = f"node{_exe_s}"
    
    # 1. [Fast-Path] 정규 전개 위치 최우선 검사 (I/O 병목 0ms)
    local_node_dirs = [
        os.path.join(get_writable_base(), "components", "node"),
        os.path.join(get_writable_base(), "node"),
    ]
    
    cands = []
    for node_dir in local_node_dirs:
        if os.path.isdir(node_dir):
            direct_bin = os.path.join(node_dir, exe_name)
            if os.path.isfile(direct_bin):
                cands.append(direct_bin)
            direct_subbin = os.path.join(node_dir, "bin", exe_name)
            if os.path.isfile(direct_subbin):
                cands.append(direct_subbin)

    # Fast-Path 성공 시 요구 버전 체크 후 즉시 반환
    majors = [(c, node_major_version(c)) for c in cands]
    ok = [c for c, m in majors if m is not None and m >= NODE_MIN_MAJOR]
    if ok:
        return ok[0]

    # 2. [Slow-Path / Fallback] 중첩 디렉터리 대응 os.walk (cz_* 임시 폴더 탐색 제외)
    for node_dir in local_node_dirs:
        if os.path.isdir(node_dir):
            for root, dirs, files in os.walk(node_dir):
                dirs[:] = [d for d in dirs if not d.startswith(("cz_", ".tmp", "temp"))]
                if exe_name in files:
                    p = os.path.join(root, exe_name)
                    if p not in cands:
                        cands.append(p)

    majors = [(c, node_major_version(c)) for c in cands]
    ok = [c for c, m in majors if m is not None and m >= NODE_MIN_MAJOR]
    if ok:
        return ok[0]

    # 3. [오프라인 구원책: 번들 시드 승격 (Seed Promotion)]
    b_root = bundle_root()
    if b_root:
        bundled_seed = os.path.join(b_root, "seed_node")
        if os.path.isdir(bundled_seed):
            target_node_dir = os.path.join(components_root(), "node")
            shutil.copytree(bundled_seed, target_node_dir, dirs_exist_ok=True)
            return node_exe()  # 승격 후 재참조

    return None
```

### ③ `chzzktube/infra/components.py` 및 `executor.py` - FFmpeg 수급 & macOS 호스트 승격
```python
# chzzktube/infra/components.py - FFmpeg 수급 (v3.12.5)
import os
import sys
import shutil
from pathlib import Path
from chzzktube.infra.platform import exe_suffix, strip_macos_quarantine
from chzzktube.infra.paths import bundle_root, components_root

def ffmpeg_exe() -> str | None:
    """FFmpeg 바이너리 탐색 - Fast-Path + 호스트 승격 + 시드 승격."""
    exe_name = f"ffmpeg{exe_suffix()}"
    ffmpeg_dir = os.path.join(components_root(), "ffmpeg")

    # 1. [Fast-Path] 정규 bin 디렉터리 검사 (0ms)
    fast_bin = os.path.join(ffmpeg_dir, "bin", exe_name)
    if os.path.isfile(fast_bin) and os.access(fast_bin, os.X_OK):
        return fast_bin

    # 2. [Slow-Path] 중첩 폴더 재귀 탐색
    if os.path.isdir(ffmpeg_dir):
        for root, dirs, files in os.walk(ffmpeg_dir):
            dirs[:] = [d for d in dirs if not d.startswith(("cz_", ".tmp", "temp"))]
            if exe_name in files:
                target = os.path.join(root, exe_name)
                if os.access(target, os.X_OK):
                    return target

    # 3. [macOS 호스트 승격 (Bootstrap)] AMFI 커널 트랩 방지
    if sys.platform == "darwin":
        for host_bin in (Path("/opt/homebrew/bin/ffmpeg"), Path("/usr/local/bin/ffmpeg")):
            if host_bin.is_file():
                dest_bin_dir = Path(ffmpeg_dir) / "bin"
                dest_bin_dir.mkdir(parents=True, exist_ok=True)
                dest_ffmpeg = dest_bin_dir / "ffmpeg"
                shutil.copy2(host_bin, dest_ffmpeg)
                dest_ffmpeg.chmod(0o755)
                strip_macos_quarantine(str(dest_ffmpeg))
                return str(dest_ffmpeg)

    # 4. [시드 승격] 번들 시드 존재 시 원자적 복사
    b_root = bundle_root()
    if b_root:
        bundled_seed = os.path.join(b_root, "seed_ffmpeg")
        if os.path.isdir(bundled_seed):
            shutil.copytree(bundled_seed, ffmpeg_dir, dirs_exist_ok=True)
            return ffmpeg_exe()

    return None
```

---

## 🧪 4. 검증 시나리오 (Verification Checklist)

1. **Fast-Path I/O 검증**:
   - `node_exe()` 및 `ffmpeg_exe()` 호출 시 `os.walk` 순회 없이 Fast-Path(`os.path.isfile`)로 0ms 내에 즉시 반환되는지 확인.
2. **오프라인 시드 승격 검증**:
   - `<writable_base>/components`를 강제 삭제한 오프라인 환경에서 기동 시 번들의 `seed_node` 및 `seed_ffmpeg`가 캐시 디렉터리로 원자적 승격 기동되는지 검증.
3. **프로비저닝 파이프라인 연동 검증**:
   - `uv run pytest tests/` 스위트 통과 (386 passed).
   - `smoke_test.py` 1초 내 완벽 통과 (ALL PASS).
