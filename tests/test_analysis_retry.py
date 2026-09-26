"""분석 회전·EJS 런타임 계약 — 일반/멤버십 영상 분석 실패 근본 수정.

[배경] yt-dlp의 기본 JS 런타임은 'deno'뿐(PATH 탐색)인데 앱은 포터블 node를
PATH 밖(writable_base()/node)에 수급하므로 n-challenge가 실패했고, 회전
후보 'ios'는 쿠키 미지원(SUPPORTS_COOKIES=False)이라 쿠키 사용 중 yt-dlp가
클라이언트 자체를 스킵 → "No video formats found"로 즉사했다. 이 오류는
bot-block 판정에 없어 마지막 폴백까지 도달하지도 못했다.

[계약 — v3.8.0 순정 위임 개정]
1. _apply_ejs_opts는 node_exe()가 찾은 node를 js_runtimes로 명시 주입한다.
2. node가 없으면 js_runtimes를 건드리지 않는다(기본 deno 유지).
3. ejs:github remote_component는 항상 허용된다.
4. [개정] 앱 레벨 회전 체인(_RETRY_CLIENTS)은 폐기 — yt-dlp 순정 단일 auto
   호출로 완전 위임한다. 클라이언트 로테이션은 yt-dlp 내부
   _DEFAULT_CLIENTS가 담당한다.
5. "No video formats found" / "Requested format is not available"는
   봇 차단/포맷 상실 판정(다운로드 POT 승격) 대상이다.
6. [개정] 회전이 없으므로 '마지막 후보까지 회전' 계약은 소멸 — 분석은
   단일 auto 호출 1회이며, 실패 시 뷰의 POT 재시도(_maybe_retry_analysis)가
   후속한다.
"""
from typing import ClassVar

import pytest

import chzzktube.workers.analyze_worker as aw
from chzzktube.core import client_opts


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


def test_retry_clients_deprecated_to_stainless_chain():
    # [계약 4 개정] 앱 레벨 회전 체인 폐기 — 순정 위임 (v3.8.0).
    assert aw.AnalyzeWorker._RETRY_CLIENTS == []


def test_bot_block_covers_no_format_derivatives():
    # [계약 5] 봇 차단/포맷 상실 판정(다운로드 POT 승격 트리거) 대상.
    assert aw.AnalyzeWorker._is_bot_block(Exception("No video formats found!"))
    assert aw.AnalyzeWorker._is_bot_block(
        Exception("Requested format is not available.")
    )
    assert aw.AnalyzeWorker._is_bot_block(Exception("The page needs to be reloaded."))
    assert aw.AnalyzeWorker._is_bot_block(Exception("n challenge solving failed: x"))


class _FailThenYDL:
    """fail_times번째 시도까지 실패하고 이후 성공하는 YoutubeDL 대역."""

    failures: ClassVar[list] = []
    fail_times: ClassVar[int] = 0
    seen_clients: ClassVar[list] = []

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


def test_stainless_single_call_no_rotation(monkeypatch):
    # [계약 6 개정] 분석은 순정 단일 auto 호출 1회 — 앱 레벨 회전 없음.
    # 실패 시 예외가 그대로 상승하고, 뷰의 POT 재시도 인터락이 후속한다.
    _FailThenYDL.failures = ["ERROR: [youtube] x: No video formats found!"]
    _FailThenYDL.fail_times = 99
    _FailThenYDL.seen_clients = []
    monkeypatch.setattr(aw, "YoutubeDL", _FailThenYDL)
    w = _worker()
    with pytest.raises(RuntimeError):
        w._extract_youtube("u", flat=False)
    assert _FailThenYDL.seen_clients == ["auto"]


def test_stainless_call_success(monkeypatch):
    _FailThenYDL.failures = []
    _FailThenYDL.fail_times = 0
    _FailThenYDL.seen_clients = []
    monkeypatch.setattr(aw, "YoutubeDL", _FailThenYDL)
    w = _worker()
    info = w._extract_youtube("u", flat=False)
    assert info["formats"] == [{"id": "f1"}]
    # 순정 위임 — 클라 기록은 항상 auto (다운로드도 auto로 위임)
    assert w.client_used == "auto"


# ── [TUI 규격] 최종 analysis error 메시지 축약 ──────────────────────────
# [배경] yt-dlp 원문은 "please report this issue on ..." 보일러플레이트가
# 뒤에 붙어 TUI MSG 컬럼을 넘쳤다. 핵심 구문 추출 + 60자 절단이 계약.


def _minimal(msg: str) -> str:
    msg = aw.clean_ansi(str(msg))
    m = aw.re.search(r"ERROR:\s*\[[^\]]+\]\s*[^:]+:\s*(.+)", msg)
    if m:
        msg = m.group(1).strip()
    msg = aw.re.split(r";\s*please report|;\s*filling out|\.\s*[Uu]se --list-formats", msg)[0]
    return f"analysis error: {msg[:60]}"


def test_minimal_error_strips_report_boilerplate():
    raw = (
        "ERROR: [youtube] 0VxDq_vzXcg: No video formats found!; please report "
        "this issue on  https://github.com/yt-dlp/yt-dlp/issues?q= , filling "
        "out the appropriate issue template. Confirm you are on the latest "
        "version using  yt-dlp -U"
    )
    assert _minimal(raw) == "analysis error: No video formats found!"


def test_minimal_error_truncates_to_tui_budget():
    raw = "ERROR: [youtube] x: Requested format is not available. Use --list-formats for a list of available formats"
    assert _minimal(raw) == "analysis error: Requested format is not available"
    raw2 = "Only images are available for download. use --list-formats to see them"
    assert _minimal(raw2) == "analysis error: Only images are available for download"
