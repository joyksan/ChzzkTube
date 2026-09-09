"""po_client 단위 테스트 — 순수 HTTP 클라이언트 계층."""
import json
from unittest.mock import patch, MagicMock

import pytest

from po_client import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    extract_video_id,
    fetch_po_token,
    probe_server,
    server_ping,
)


class TestServerPing:
    @patch("po_client.urllib.request.urlopen")
    def test_ping_success(self, mock_urlopen):
        resp = MagicMock()
        resp.status = 200
        mock_urlopen.return_value.__enter__ = MagicMock(return_value=resp)
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)
        assert server_ping() is True

    @patch("po_client.urllib.request.urlopen")
    def test_ping_failure(self, mock_urlopen):
        mock_urlopen.side_effect = Exception("connection refused")
        assert server_ping() is False


class TestExtractVideoId:
    @pytest.mark.parametrize(
        "url,expected",
        [
            ("https://www.youtube.com/watch?v=imTeMjjlHUs", "imTeMjjlHUs"),
            ("https://youtu.be/WAQZR0Dsm7k", "WAQZR0Dsm7k"),
            ("https://www.youtube.com/shorts/WAQZR0Dsm7k", "WAQZR0Dsm7k"),
            ("https://www.youtube.com/embed/abcd1234efg", "abcd1234efg"),
            ("https://example.com/notvideo", None),
            ("", None),
        ],
    )
    def test_extract(self, url, expected):
        assert extract_video_id(url) == expected


class TestFetchPoToken:
    @patch("po_client.urllib.request.urlopen")
    def test_fetch_success(self, mock_urlopen):
        resp = MagicMock()
        resp.read.return_value = json.dumps({"poToken": "test_token_123"}).encode()
        mock_urlopen.return_value.__enter__ = MagicMock(return_value=resp)
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)
        assert fetch_po_token("imTeMjjlHUs") == "test_token_123"

    @patch("po_client.urllib.request.urlopen")
    def test_fetch_no_token(self, mock_urlopen):
        resp = MagicMock()
        resp.read.return_value = json.dumps({"poToken": ""}).encode()
        mock_urlopen.return_value.__enter__ = MagicMock(return_value=resp)
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)
        assert fetch_po_token("imTeMjjlHUs") is None

    @patch("po_client.urllib.request.urlopen")
    def test_fetch_error(self, mock_urlopen):
        mock_urlopen.side_effect = Exception("server down")
        assert fetch_po_token("imTeMjjlHUs") is None


class TestDefaults:
    def test_default_host_port(self):
        assert DEFAULT_HOST == "127.0.0.1"
        assert DEFAULT_PORT == 4416