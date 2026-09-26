"""Task 2-3: ChzzkAuthError 발생·매핑 계약 (v3.9.0 신규).

HANDOVER §6 'except 뭉뚱그리기 금지' — 401/403은 인증 에러로 명시 분리,
그 외 HTTP 에러는 그대로 전파. 분석 워커는 쿠키 만료 메시지로 매핑.
"""
import urllib.error

import pytest

from chzzktube.core.chzzk_api import ChzzkAuthError, _get_json_with_auth_check


def _http_error(code):
    return urllib.error.HTTPError(
        url="https://api.chzzk.naver.com/x",
        code=code,
        msg=f"HTTP {code}",
        hdrs=None,
        fp=None,
    )


@pytest.mark.parametrize("code", [401, 403])
def test_auth_check_raises_chzzk_auth_error(monkeypatch, code):
    import chzzktube.core.chzzk_api as api

    def _boom(req, timeout=15):
        raise _http_error(code)

    monkeypatch.setattr(api.urllib.request, "urlopen", _boom)
    with pytest.raises(ChzzkAuthError) as ei:
        _get_json_with_auth_check("https://api.chzzk.naver.com/x", {})
    assert ei.value.status_code == code


def test_auth_check_passes_through_other_http_errors(monkeypatch):
    import chzzktube.core.chzzk_api as api

    def _boom(req, timeout=15):
        raise _http_error(500)

    monkeypatch.setattr(api.urllib.request, "urlopen", _boom)
    with pytest.raises(urllib.error.HTTPError):
        _get_json_with_auth_check("https://api.chzzk.naver.com/x", {})


def test_analyze_worker_maps_auth_error_to_cookie_message(monkeypatch):
    import chzzktube.workers.analyze_worker as aw

    def _raise_auth_error(url, cookies=None):
        raise ChzzkAuthError(401, "Unauthorized")

    monkeypatch.setattr(aw, "analyze_chzzk_vod_api", _raise_auth_error)

    worker = aw.AnalyzeWorker(
        target_url="https://chzzk.naver.com/video/12345",
        cfg={},
    )
    captured = []
    worker.error_occurred.connect(captured.append)

    worker.run()

    assert len(captured) == 1
    assert "chzzk cookie expired" in captured[0].lower()
