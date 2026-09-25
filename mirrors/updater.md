##### updater.py - pip component (yt-dlp) version check and update helper
"""PyPI metadata query for latest versions, optional pip upgrade on demand.
*  Version check: PyPI JSON API (lightweight, no pip needed)
*  Upgrade:
    - Stable channel: python -m pip install -U <pkg>
    - Nightly channel: python -m pip install -U yt-dlp-nightly (yt-dlp only)
*  frozen(PyInstaller) builds — pip이 없으므로 직접 다운로드:
    - yt-dlp: GitHub release에서 yt-dlp 바이너리 직접 다운로드 후 교체 (yt_dlp_binary 위임, .pylib 미사용)
    - 업데이트 실패 시 기존 버전 유지, 다음 실행 시 재시도
*  네트워크 의존은 이 앱에서 본질적이다 (웹 미디어 추출기). """
import concurrent.futures
import json
import os
import shutil
import subprocess
import sys
import tempfile
import socket
import urllib.request
from chzzktube.infra.platform import spawn_kwargs

# (log_label, pypi_name, pypi_nightly) — log_label is shown in the DEPS PLATFORM column
# pypi_nightly: Nightly 채널 사용 시 설치할 PyPI 패키지명 (None이면 Stable only)
# [v3.10.0] streamlink 제거 — 라이브 녹화는 yt-dlp 단일 경로로 통합.
# [전환] bgutil-ytdlp-pot-provider 제외: 플러그인(pip)에서 독립 Node 서버로
# 이동 — 버전 관리 주체는 pot_provider(latest_server_ver)가 담당.
PACKAGES = [("ytdlp", "yt-dlp", "yt-dlp-nightly")]
# [주의] socket.setdefaulttimeout() 절대 사용 금지 — 프로세스 전체의 소켓 기본
# 타임아웃을 오염시켜 yt-dlp 미디어 스트림 재시도 루프(0.0% 스톨)를 유발.
# DNS hang 방어는 아래 latest_version의 ThreadPoolExecutor + urlopen(timeout)으로 충분.

_PYPI_API = "https://pypi.org/pypi/{pkg}/json"

def installed_version(pypi_name):
    """Installed version string from binary (yt-dlp) or .pylib overlay (others).

    SSOT: yt-dlp는 yt_dlp_binary.yt_dlp_version() 사용 (바이너리 전용), 나머지는 .pylib 내부 dist-info만 스캔.
    .venv나 시스템 site-packages에 존재하더라도 무시한다.
    """
    # yt-dlp는 독립 실행형 바이너리 사용
    if pypi_name == "yt-dlp":
        from chzzktube.infra.yt_dlp_binary import yt_dlp_version, yt_dlp_path
        exe = yt_dlp_path()
        if exe:
            ver = yt_dlp_version(exe)
            if ver:
                return ".".join(map(str, ver))
        return None

    import glob
    import os
    from chzzktube.core.config import pylib_overlay_path

    pylib_root = pylib_overlay_path()
    if not os.path.isdir(pylib_root):
        return None

    # 패키지명 정규화: yt-dlp -> yt_dlp
    pkg_dir = pypi_name.replace("-", "_")
    dist_info_pattern = os.path.join(pylib_root, f"{pkg_dir}-*.dist-info")

    for dist_info in glob.glob(dist_info_pattern):
        metadata_path = os.path.join(dist_info, "METADATA")
        if os.path.isfile(metadata_path):
            try:
                with open(metadata_path, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.startswith("Version:"):
                            return line.split(":", 1)[1].strip()
            except Exception as e:
                import chzzktube.core.raw_log as raw_log
                raw_log.raw("DEPS", f"installed_version metadata read error: {type(e).__name__}: {e}", is_error=True, to_tui=False)
                continue
    return None

def latest_version(pypi_name, timeout=1.5):
    """Latest stable version from PyPI, or None on failure.

    [v3.1.0 변경] 타임아웃 2초→1.5초로 단축. DEPS 로그 표시 시간을
    줄이기 위해. PyPI JSON API는 충분히 빠르므로 1.5초면 충분.
    ThreadPoolExecutor는 DNS 레벨까지 카운트다운하므로 urlopen timeout
    보다 0.5초만 버퍼로 부여.

    [DNS hang defence] socket.setdefaulttimeout does not cover getaddrinfo;
    ThreadPoolExecutor + future.result cuts at DNS level too.
    """
    def _fetch():
        with urllib.request.urlopen(_PYPI_API.format(pkg=pypi_name), timeout=timeout) as resp:
            return json.load(resp)
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(_fetch)
            data = fut.result(timeout=timeout + 0.5)
            return (data.get("info") or {}).get("version")
    except Exception as e:
        import chzzktube.core.raw_log as raw_log
        raw_log.raw("DEPS", f"latest_version PyPI fetch error: {type(e).__name__}: {e}", is_error=True, to_tui=False)
        return None

def _ver_tuple(version):
    """'2026.8.19' -> (2026, 8, 19) comparable tuple (non-digit chars dropped)."""
    parts = []
    for p in str(version).split("."):
        digits = "".join(ch for ch in p if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)

def is_outdated(current, latest):
    """True if latest > current (numeric tuple compare avoids string pitfalls)."""
    try:
        return _ver_tuple(latest) > _ver_tuple(current)
    except Exception as e:
        import chzzktube.core.raw_log as raw_log
        raw_log.raw("DEPS", f"is_outdated version compare error: {type(e).__name__}: {e}", is_error=True, to_tui=False)
        return False

def outdated_packages(channel="stable"):
    """List of (label, pypi_name, cur, latest) needing update.
    channel: stable / nightly (yt-dlp-nightly / GitHub builds).
    미설치 상태는 check_deps가 FAIL로 처리하므로 stale 목록에 포함하지 않는다.
    """
    stale = []
    for label, pypi_name, pypi_nightly in PACKAGES:
        if channel == "nightly" and pypi_nightly:
            cur = installed_version(pypi_nightly) or installed_version(pypi_name)
            latest = latest_version(pypi_nightly)
            if cur and latest and is_outdated(cur, latest):
                stale.append((label, pypi_name, cur, latest))
            continue
        # stable channel: leftover nightly -> downgrade target
        if pypi_nightly and installed_version(pypi_nightly):
            stale.append((label, pypi_name, str(installed_version(pypi_nightly)) + " (nightly)", "stable"))
            continue
        cur = installed_version(pypi_name)
        latest = latest_version(pypi_name)
        if cur and latest and is_outdated(cur, latest):
            stale.append((label, pypi_name, cur, latest))
    return stale


def check_deps(log_func=None):
    """모든 의존성 체크 결과 리스트 반환.
    각 요소: (label, status, msg)
    label: "ytdlp" | "ffmpeg" | "node" | "pot"
    status: "OK" | "FAIL" | "SKIP"
    msg: "vX.Y.Z at <path>" | "not installed" | "<reason>"
    log_func(msg): POT readiness 판정 근거를 raw 스택으로 반환 (단일 호출).
    """
    import os
    results = []

    # 1. yt-dlp (독립 실행형 바이너리) — 앱 전용 경로 확인
    # yt-dlp-nightly는 dist 명이 달라 .pylib 체크가 실패하므로
    # nightly 설치물로 폴백 표기 (정상 설치 판정 유지)
    label = "ytdlp"
    pypi_name = "yt-dlp"
    pypi_nightly = "yt-dlp-nightly"
    
    # yt-dlp는 독립 실행형 바이너리 사용 (yt_dlp_binary 모듈)
    from chzzktube.infra.yt_dlp_binary import yt_dlp_version, yt_dlp_path
    exe = yt_dlp_path()
    if exe:
        ver_tuple = yt_dlp_version(exe)
        if ver_tuple:
            ver = ".".join(map(str, ver_tuple))
        else:
            ver = None
    else:
        ver = None
    
    # nightly 채널 설치물 인지 (pypi overlay 체크)
    if not ver and pypi_nightly:
        nver = installed_version(pypi_nightly)
        if nver:
            ver = f"{nver} (nightly)"
    
    if ver:
        results.append((label, "OK", f"{ver} at {exe}"))
    else:
        results.append((label, "FAIL", "not installed"))

    # 2. ffmpeg — 앱 전용 캐시 단일 참조 (시스템 PATH 탐색 철폐)
    try:
        from chzzktube.infra.components import ffmpeg_exe
        path = ffmpeg_exe()
    except Exception:
        path = None
    if path:
        ver_str = _ffmpeg_version(path) or "unknown"
        results.append(("ffmpeg", "OK", f"{ver_str} at {path}"))
    else:
        results.append(("ffmpeg", "FAIL", "not installed"))

    # 3. node — 앱 전용 포터블 런타임 단일 참조
    try:
        import chzzktube.infra.pot_provider as pot_provider
        path = pot_provider.node_exe()
        maj = pot_provider.node_major_version(path)
    except Exception:
        path, maj = None, None
    if path and maj:
        results.append(("node", "OK", f"v{maj} at {path}"))
    else:
        results.append(("node", "FAIL", "not installed"))

    # 4. bgutil 소스코드 무결성 검증 (POT 기동/readiness는 staging에서 별도 판정)
    try:
        from chzzktube.infra.pot_server import server_installed_ver, server_home
        ver = server_installed_ver()
        if ver:
            results.append(("bgutil", "OK", f"v{ver} at {server_home()}"))
        else:
            results.append(("bgutil", "FAIL", "not installed"))
    except Exception:
        results.append(("bgutil", "FAIL", "unknown"))

    return results


def verify_deps_integrity() -> tuple[bool, list[str]]:
    """런타임 의존성 무결성 검증 — 주요 deps 존재/실행 가능 여부 확인.

    Returns:
        (ok, missing_list): ok=True면 모든 필수 deps 정상, False면 누락/실패 목록 반환
    """
    from chzzktube.core import config
    import chzzktube.infra.components as components
    import chzzktube.infra.pot_provider as pot_provider
    import subprocess
    from chzzktube.infra.platform import spawn_kwargs

    missing = []

    # 1. yt-dlp (독립 실행형 바이너리) — 앱 전용 경로에서 실행 확인
    from chzzktube.infra.yt_dlp_binary import yt_dlp_path, yt_dlp_version
    exe = yt_dlp_path()
    if not exe:
        missing.append("yt-dlp (not found in app binary path)")
    else:
        # 실행 테스트
        result = subprocess.run(
            [exe, "--version"],
            capture_output=True,
            timeout=5,
            **spawn_kwargs(),
        )
        if result.returncode != 0:
            missing.append("yt-dlp (execution failed)")

    # 2. ffmpeg — 격리 캐시에서 실행 가능 확인
    try:
        ffmpeg_path = components.ffmpeg_exe()
        if not ffmpeg_path:
            missing.append("ffmpeg (not found in cache)")
        else:
            # 실행 테스트
            result = subprocess.run(
                [ffmpeg_path, "-version"],
                capture_output=True,
                timeout=5,
                **{**{}, **__import__("chzzktube.infra.platform").spawn_kwargs()}
            )
            if result.returncode != 0:
                missing.append("ffmpeg (execution failed)")
    except Exception as e:
        missing.append(f"ffmpeg (check error: {e})")

    # 3. node — 격리 캐시에서 실행 가능 확인
    try:
        node_path = pot_provider.node_exe()
        if not node_path:
            missing.append("node (not found in cache)")
        else:
            result = subprocess.run(
                [node_path, "--version"],
                capture_output=True,
                timeout=5,
                **{**{}, **__import__("chzzktube.infra.platform").spawn_kwargs()}
            )
            if result.returncode != 0:
                missing.append("node (execution failed)")
    except Exception as e:
        missing.append(f"node (check error: {e})")

    # 4. bgutil 소스코드 무결성 검증
    try:
        from chzzktube.infra.pot_server import server_installed_ver
        if not server_installed_ver():
            missing.append("bgutil (not installed)")
    except Exception:
        missing.append("bgutil (check error)")

    return len(missing) == 0, missing


_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _cli_base(label):
    """라벨 → 실제 CLI 명령 배열 (없으면 None). F12 상세 로그용 원문 실행.

    [v3.8.0 격리] 실행체 해석은 앱 전용 저장소 단일 경로로 일원화:
    - ytdlp: dev/frozen 공통 — OS 표준 경로(%LOCALAPPDATA%/ChzzkTube/bin/ 등)에
      설치된 yt-dlp 바이너리 직접 실행. 시스템 PATH의 yt-dlp는 절대 참조하지 않는다.
    - ffmpeg/node/npm: components.ffmpeg_exe / pot_provider.node_exe·npm_exe
      (writable_base 격리 캐시) 단일 참조 — shutil.which 폴백 철폐.
    """
    if label == "ytdlp":
        # dev/frozen 공통: OS 표준 경로에 설치된 yt-dlp 바이너리 직접 실행
        from chzzktube.infra.yt_dlp_binary import yt_dlp_path
        p = yt_dlp_path()
        return [p] if p else None
    if label == "ffmpeg":
        try:
            from chzzktube.infra.components import ffmpeg_exe
            p = ffmpeg_exe()
        except Exception:
            p = None
        return [p] if p else None
    if label == "node":
        try:
            import chzzktube.infra.pot_provider as pot_provider
            p = pot_provider.node_exe()
        except Exception:
            p = None
        return [p] if p else None
    if label == "npm":
        try:
            import chzzktube.infra.pot_provider as pot_provider
            p = pot_provider.npm_exe()
        except Exception:
            p = None
        return [p] if p else None
    return None


def _cli_env(label):
    """npm 시스 스크립트가 'env node'로 node를 찾도록 PATH 보강 (npm만)."""
    if label != "npm":
        return None
    try:
        import chzzktube.infra.pot_provider as pot_provider
        node = pot_provider.node_exe()
    except Exception:
        node = None
    if not node:
        return None
    env = os.environ.copy()
    ndir = os.path.dirname(node)
    env["PATH"] = ndir + os.pathsep + env.get("PATH", "")
    return env


def cli_raw(label, *args, timeout=15):
    """실제 CLI를 실행해 '터미널에서 친 것과 동일한 원문 출력'을 반환.

    반환: (cmdline, output) — 도구 없으면 (None, None), 실행 예외면
    (cmdline, "[Type] msg"). 출력은 stdout+stderr 합본 원문 전체.

    [레이어 원칙] 수집층은 절대 절단하지 않는다. 원문은 history에 전량
    기록되며, F12 적재 시점의 절취는 호출부(truncate_for_full_log)가 담당.
    수집에서 자르면 원본이 영구 소실되어 복원 불가.
    """
    cmd = _cli_base(label)
    if not cmd:
        return None, None
    full_cmd = cmd + list(args)
    env = _cli_env(label)
    try:
        proc = subprocess.run(
            full_cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=env,
            **spawn_kwargs(),
        )
    except Exception as e:
        return " ".join(full_cmd), f"[{type(e).__name__}] {e}"
    out = ((proc.stdout or "") + (proc.stderr or "")).strip()
    if not out:
        return " ".join(full_cmd), None
    return " ".join(full_cmd), out


def truncate_for_full_log(out, max_lines=6, max_width=160):
    """F12 적재 시점 절취 — history는 원문 전량을 이미 기록했으므로 뷰만 자른다.

    max_lines>0 → 앞 N줄만 + '… (M lines truncated)' 꼬리.
    over-long 단일 줄은 max_width로 절단 (ffmpeg configuration: 500자 대책).
    ffmpeg configuration: 라인 및 이어지는 빌드 설정 줄들은 제거.
    """
    import re
    text = str(out or "")
    if not text:
        return ""
    # ffmpeg -version의 configuration: 부터 끝까지 제거 (빌드 설정 10+줄 방지)
    text = re.sub(r"(?m)^configuration:.*\n(?:^ .*\n)*", "", text)
    lines = text.splitlines()
    if max_width and max_width > 0:
        lines = [l if len(l) <= max_width else l[:max_width] + "…" for l in lines]
    if max_lines and max_lines > 0 and len(lines) > max_lines:
        kept = lines[:max_lines]
        kept.append(f"… ({len(lines) - max_lines} lines truncated)")
        return "\n".join(kept)
    return "\n".join(lines)


def _ffmpeg_version(path, timeout=3):
    """`ffmpeg -version`에서 숫자 코어 버전(MAJOR.MINOR[.PATCH]) 추출. 실패 시 None.

    - 표준/홈브루: 'ffmpeg version 9.0.1' → 9.0.1
    - extra version/빌드 태그/일자(YYYMMDD) 접미는 정규식으로 절단:
      '9.0.1_1'·'7.1.1-20240815-g…' → 9.0.1 · 7.1.1
      (homebrew bottle Cellar/ffmpeg/9.0.1_1 처럼 configuration 줄에만
      extra version이 드러나는 경우도 그대로 대응)
    - 첫 줄 미매치(N-일자 빌드 등) 시 configuration 줄 폴백: '…/ffmpeg/9.0.1_1'
    """
    try:
        import re
        out = subprocess.run(
            [path, "-version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            **spawn_kwargs(),
        )
        text = (out.stdout or out.stderr or "")
        # 1) 표준 첫 줄 — 숫자 코어 3단만 (extra version 접미부 미포함)
        m = re.search(r"ffmpeg version\s+(\d+(?:\.\d+){1,2})", text)
        if not m:
            # 2) configuration 줄 폴백 — --prefix=…/ffmpeg/9.0.1_1
            m = re.search(r"ffmpeg[/\\\-](\d+(?:\.\d+){1,2})(?![0-9.])", text)
        return m.group(1) if m else None
    except Exception:
        return None

def _exe_suffix():
    return ".exe" if sys.platform == "win32" else ""

def _download_to(url, dest, timeout=120):
    """Download url to dest file. Returns True on success."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp, open(dest, "wb") as f:
            shutil.copyfileobj(resp, f)
        return True
    except Exception:
        return False

def _get_pypi_whl_url(pypi_name):
    """PyPI에서 최신 whl 다운로드 URL을 조회. 실패 시 None."""
    try:
        with urllib.request.urlopen(_PYPI_API.format(pkg=pypi_name), timeout=10) as resp:
            data = json.load(resp)
        urls = data.get("urls") or []
        # manylinux/macosx/windows whl 우선순호
        preferred = [f for f in urls if "whl" in f.get("filename", "")]
        if preferred:
            return preferred[0].get("url")
    except Exception:
        pass
    return None

def _extract_from_whl(whl_path, dest_dir):
    """whl 파일(zip)을 dest_dir에 압축 해제."""
    import zipfile
    try:
        with zipfile.ZipFile(whl_path) as zf:
            zf.extractall(dest_dir)
        return True
    except Exception:
        return False

def _frozen_upgrade_ytdlp(channel="stable"):
    """yt-dlp 업그레이드: yt_dlp_binary.upgrade_yt_dlp()에 위임.

    dev/frozen 공통: venv(site-packages, uv 소유)는 절대 건드리지 않는다.
    yt-dlp 바이너리는 OS 표준 경로(%LOCALAPPDATA%/ChzzkTube/bin/ 등)에 직접 교체.
    """
    from chzzktube.infra.yt_dlp_binary import upgrade_yt_dlp
    return upgrade_yt_dlp(channel)

def _extract_pylib_whl(whl_path, pylib_root, prefix):
    """프로젝트 오버레이(.pylib/)에 whl 해제 + 구 dist-info 정리 (순수·테스트 가능).

    venv(site-packages, uv 소유)는 절대 건드리지 않는다. 해제 후
    sys.path 선두(.pylib/)의 오버레이 복사가 venv보다 항상 우선한다.
    prefix: "yt_dlp-" — 구 dist-info(glob) 스캔용.
    """
    import zipfile
    keep_dist = None
    try:
        with zipfile.ZipFile(whl_path) as zf:
            # [정확 판정] whl(zip)에는 디렉터리 엔트리가 없다 — 파일 경로의
            # 첫 세그먼트로 dist-info 이름을 얻어야 한다. (과거 "…/"
            # endswith 판정은 항상 None이 되어 구 dist-info 정리가
            # 통째로 스킵 → 버전 메타데이터가 옛 값으로 남아 무한 업데이트)
            for name in zf.namelist():
                if name.startswith(prefix) and ".dist-info/" in name:
                    keep_dist = name.split("/", 1)[0]
                    break
        if not _extract_from_whl(whl_path, pylib_root):
            return False
        if keep_dist:
            import glob
            for old in glob.glob(os.path.join(pylib_root, f"{prefix}*.dist-info")):
                if os.path.basename(old) != keep_dist:
                    shutil.rmtree(old, ignore_errors=True)
        return True
    except Exception:
        return False


def _overlay_root():
    """인앱 업데이트 해제 대상 — 프로젝트 오버레이(.pylib/).

    venv는 uv 소유 → 손대지 않는다. 부트스트랩이 이 경로를 sys.path 선두에
    두므로 오버레이가 항상 우선 적용된다.
    """
    try:
        from chzzktube.core.config import pylib_overlay_path

        return os.path.abspath(pylib_overlay_path())
    except Exception:
        return ""


def _refresh_overlay_sys_path():
    try:
        path = _overlay_root()
        if not path:
            return
        if path not in sys.path:
            sys.path.insert(0, path)
        import importlib

        importlib.invalidate_caches()
    except Exception:
        pass




def upgrade_packages(packages, channel="stable"):
    """직접 다운로드 방식으로 패키지 업데이트 (Dev/Frozen 통합).

    [v3.4.0 변경] 해제 대상은 프로젝트 오버레이(.pylib/) -- venv(site-packages,
    uv 소유)는 절대 건드리지 않는다. 요약 문자열에 "(overlay)" 표기.
    이유: 포터블 빌드와 Dev에서 동일한 코드 경로를 타야 디버깅이 가능.
    pip install은 빌드 시에만 사용 (PyInstaller 번들 시점).

    Returns (returncode, output tail). Worker thread only.
    """
    # yt-dlp: Dev/Frozen 통합 - 직접 다운로드 (yt_dlp_binary 위임)
    if "yt-dlp" in packages:
        return _frozen_upgrade_ytdlp(channel)
