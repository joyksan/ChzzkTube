"""pot_server._run_and_stream_log 타임아웃 계약 회귀 테스트 (v3.5.2 P3c).

[배경]
npm ci / tsc 러너에 상한이 없으면(무제한 communicate()) 무응답 시 프리웜 워커가
영구 점유되어 is_busy()가 고정되고, POT 게이트 다운로드가 큐에서 풀리지 않는다.
상한 초과 시 직접 자식만 강제 종료하고 -1로 실패 토큰 경로를 타야 한다.
"""
import subprocess

from chzzktube.infra import pot_server


class _TimeoutProc:
    """communicate가 TimeoutExpired를 던지는 가짜 프로세스."""

    def __init__(self):
        self.killed = 0

    def communicate(self, timeout=None):
        raise subprocess.TimeoutExpired(cmd="npm ci", timeout=timeout)

    def kill(self):
        self.killed += 1


class _OkProc:
    """정상 종료 + 원문 출력을 돌려주는 가짜 프로세스."""

    returncode = 0

    def __init__(self):
        self.killed = 0

    def communicate(self, timeout=None):
        return ("line1\n\n  line2  \n", None)

    def kill(self):
        self.killed += 1


def test_timeout_constants_defined():
    assert pot_server._NPM_CI_TIMEOUT > 0
    assert pot_server._TSC_TIMEOUT > 0


def test_timeout_kills_child_and_returns_minus_one(monkeypatch):
    proc = _TimeoutProc()
    monkeypatch.setattr(pot_server.subprocess, "Popen", lambda *a, **k: proc)
    logs = []
    ret = pot_server._run_and_stream_log(
        ["node", "npm-cli.js", "ci"], ".", logs.append,
        timeout=pot_server._NPM_CI_TIMEOUT,
    )
    assert ret == -1
    assert proc.killed == 1
    assert any("timeout" in line for line in logs)


def test_success_streams_stripped_lines(monkeypatch):
    proc = _OkProc()
    monkeypatch.setattr(pot_server.subprocess, "Popen", lambda *a, **k: proc)
    logs = []
    ret = pot_server._run_and_stream_log(["x"], ".", logs.append, timeout=5)
    assert ret == 0
    assert logs == ["line1", "line2"]
    assert proc.killed == 0


def test_popen_error_returns_minus_one(monkeypatch):
    def _boom(*a, **k):
        raise OSError("no such tool")

    monkeypatch.setattr(pot_server.subprocess, "Popen", _boom)
    logs = []
    assert pot_server._run_and_stream_log(["x"], ".", logs.append) == -1
    assert any("Popen error" in line for line in logs)
