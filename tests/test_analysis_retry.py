"""분석 회전·EJS 런타임 계약 — 일반/멤버십 영상 분석 실패 근본 수정.

[배경] yt-dlp의 기본 JS 런타임은 'deno'뿐(PATH 탐색)인데 앱은 포터블 node를
PATH 밖(writable_base()/node)에 수급하므로 n-challenge가 실패했고, 회전
후보 'ios'는 쿠키 미지원(SUPPORTS_COOKIES=False)이라 쿠키 사용 중 yt-dlp가
클라이언트 자체를 스킵 → "No video formats found"로 즉사했다. 이 오류는
bot-block 판정에 없어 마지막 폴백까지 도달하지도 못했다.

[계약]
1. _apply_ejs_opts는 node_exe()가 찾은 node를 js_runtimes로 명시 주입한다.
2. node가 없으면 js_runtimes를 건드리지 않는다(기본 deno 유지).
3. ejs:github remote_component는 항상 허용된다.
4. 회전 후보에 쿠키 미지원 클라이언트(ios)가 없다.
5. "No video formats found" / "Requested format is not available"는 회전
   지속 판정(bot-block) 대상이다.
6. 회전 중 파생 오류가 나도 마지막 후보까지 시도하고 마지막 오류를 보고한다.
"""
import pytest

import chzzktube.core.client_opts as client_opts
import chzzktube.workers.analyze_worker as aw


def _worker():
    return aw.AnalyzeWorker(
        "https://www.youtube.com/watch?v=abc", {"yt_player_client": "auto"}, deep=False
    )


def test_ejs_opts_injects_node_runtime(monkeypatch):
    monkeypatch.setattr(
        "chzzktube.infra.node_provider.node_exe", lambda: "/fake/bin/node"
    )
    opts = client_opts._apply_ejs_opts({})
    assert opts["js_runtimes"]["node"]["path"] == "/fake/bin/node"
    assert opts["remote_components"] == ["ejs:github"]


def test_ejs_opts_without_node_keeps_defaults(monkeypatch):
    monkeypatch.setattr("chzzktube.infra.node_provider.node_exe", lambda: None)
    opts = client_opts._apply_ejs_opts({})
    assert "js_runtimes" not in opts
    assert opts["remote_components"] == ["ejs:github"]


def test_retry_clients_cookie_compatible():
    # [계약 4] 쿠키 사용 중 ios는 yt-dlp가 스킵 → 즉사. 후보에서 배제.
    assert "ios" not in aw.AnalyzeWorker._RETRY_CLIENTS


def test_bot_block_covers_no_format_derivatives():
    # [계약 5] 회전 중 파생 오류도 회전 지속 판정 대상.
    assert aw.AnalyzeWorker._is_bot_block(Exception("No video formats found!"))
    assert aw.AnalyzeWorker._is_bot_block(
        Exception("Requested format is not available.")
    )
    assert aw.AnalyzeWorker._is_bot_block(Exception("The page needs to be reloaded."))
    assert aw.AnalyzeWorker._is_bot_block(Exception("n challenge solving failed: x"))


class _FailThenYDL:
    """fail_times번째 시도까지 실패하고 이후 성공하는 YoutubeDL 대역."""

    failures: list = []
    fail_times: int = 0
    seen_clients: list = []

    def __init__(self, opts):
        self.opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def extract_info(self, url, download=False):
        ea = self.opts.get("extractor_args") or {}
        client = (ea.get("youtube") or {}).get("player_client", ["auto"])[0]
        _FailThenYDL.seen_clients.append(client)
        if len(_FailThenYDL.seen_clients) <= _FailThenYDL.fail_times:
            raise RuntimeError(_FailThenYDL.failures[0])
        return {"formats": [{"id": "f1"}], "title": "t"}


def test_rotation_runs_to_last_candidate_on_derived_error(monkeypatch):
    # [계약 6] 중간 파생 오류("No video formats found")여도 마지막 후보까지 회전.
    _FailThenYDL.failures = ["ERROR: [youtube] x: No video formats found!"]
    _FailThenYDL.fail_times = 99
    _FailThenYDL.seen_clients = []
    monkeypatch.setattr(aw.yt_dlp, "YoutubeDL", _FailThenYDL)
    w = _worker()
    with pytest.raises(RuntimeError):
        w._extract_youtube("u", flat=False)
    assert _FailThenYDL.seen_clients == ["auto", "tv", "web_safari"]


def test_rotation_succeeds_on_candidate(monkeypatch):
    _FailThenYDL.failures = ["ERROR: [youtube] x: The page needs to be reloaded."]
    _FailThenYDL.fail_times = 1
    _FailThenYDL.seen_clients = []
    monkeypatch.setattr(aw.yt_dlp, "YoutubeDL", _FailThenYDL)
    w = _worker()
    info = w._extract_youtube("u", flat=False)
    assert info["formats"] == [{"id": "f1"}]
    # 통과한 클라이언트 기록 — 다운로드가 같은 클라이언트를 쓰도록 강제하는 값.
    assert w.client_used == "tv"
