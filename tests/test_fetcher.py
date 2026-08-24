from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from requests.exceptions import HTTPError, Timeout

from data_fetcher.fetcher import Fetcher, FetchError


def _mock_response(status=200, content=b"hello", content_type="text/plain", url="http://example.com/"):
    mock_resp = MagicMock()
    mock_resp.status_code = status
    mock_resp.headers = {"Content-Type": content_type}
    mock_resp.url = url
    mock_resp.history = []
    mock_resp.iter_content.return_value = iter([content])
    if status >= 400:
        mock_resp.raise_for_status.side_effect = HTTPError(response=mock_resp)
    else:
        mock_resp.raise_for_status.return_value = None
    return mock_resp


def test_fetcher_success():
    fetcher = Fetcher(
        connect_timeout_seconds=5,
        read_timeout_seconds=5,
        max_size_bytes=1024,
        max_retries=0,
        backoff_seconds=0,
        max_redirects=3,
        allowed_domains=["example.com"],
        allowed_content_types=["*/*"],
    )
    with patch("requests.Session") as MockSession:
        mock_session = MagicMock()
        MockSession.return_value = mock_session
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session.get.return_value = _mock_response(
            url="http://example.com/ok",
            content=b"hello",
            content_type="text/plain",
        )
        result = fetcher.fetch("http://example.com/ok")

    assert result.status_code == 200
    assert result.content_length == 5
    assert result.body == b"hello"
    assert result.checksum_sha256 == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
    assert result.content_type == "text/plain"


def test_fetcher_not_found():
    fetcher = Fetcher(
        connect_timeout_seconds=5,
        read_timeout_seconds=5,
        max_size_bytes=1024,
        max_retries=0,
        backoff_seconds=0,
        max_redirects=3,
        allowed_domains=["example.com"],
        allowed_content_types=["*/*"],
    )
    with patch("requests.Session") as MockSession:
        mock_session = MagicMock()
        MockSession.return_value = mock_session
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_resp = _mock_response(status=404, url="http://example.com/missing")
        mock_session.get.return_value = mock_resp
        with pytest.raises(FetchError) as exc_info:
            fetcher.fetch("http://example.com/missing")
    assert exc_info.value.category == "HTTP"


def test_fetcher_domain_not_allowed():
    fetcher = Fetcher(
        connect_timeout_seconds=5,
        read_timeout_seconds=5,
        max_size_bytes=1024,
        max_retries=0,
        backoff_seconds=0,
        max_redirects=3,
        allowed_domains=["allowed.com"],
        allowed_content_types=["*/*"],
    )
    with pytest.raises(FetchError) as exc_info:
        fetcher.fetch("http://example.com/ok")
    assert exc_info.value.category == "network/DNS"


def test_fetcher_content_type_rejected():
    fetcher = Fetcher(
        connect_timeout_seconds=5,
        read_timeout_seconds=5,
        max_size_bytes=1024,
        max_retries=0,
        backoff_seconds=0,
        max_redirects=3,
        allowed_domains=["example.com"],
        allowed_content_types=["text/plain"],
    )
    with patch("requests.Session") as MockSession:
        mock_session = MagicMock()
        MockSession.return_value = mock_session
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        json_body = b'{"ok": true}'
        mock_resp = _mock_response(
            url="http://example.com/json",
            content=json_body,
            content_type="application/json",
        )
        mock_session.get.return_value = mock_resp
        with pytest.raises(FetchError) as exc_info:
            fetcher.fetch("http://example.com/json")
    assert exc_info.value.category == "content-type"


def test_fetcher_response_size_exceeded():
    fetcher = Fetcher(
        connect_timeout_seconds=5,
        read_timeout_seconds=5,
        max_size_bytes=1024,
        max_retries=0,
        backoff_seconds=0,
        max_redirects=3,
        allowed_domains=["example.com"],
        allowed_content_types=["*/*"],
    )
    with patch("requests.Session") as MockSession:
        mock_session = MagicMock()
        MockSession.return_value = mock_session
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_resp = _mock_response(
            url="http://example.com/large",
            content=b"x" * 2048,
            content_type="text/plain",
        )
        mock_session.get.return_value = mock_resp
        with pytest.raises(FetchError) as exc_info:
            fetcher.fetch("http://example.com/large")
    assert exc_info.value.category == "response-size"


def test_fetcher_timeout_retries():
    fetcher = Fetcher(
        connect_timeout_seconds=1,
        read_timeout_seconds=1,
        max_size_bytes=1024,
        max_retries=1,
        backoff_seconds=0,
        max_redirects=3,
        allowed_domains=["example.com"],
        allowed_content_types=["*/*"],
    )
    with patch("requests.Session") as MockSession:
        mock_session = MagicMock()
        MockSession.return_value = mock_session
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session.get.side_effect = Timeout("request timed out")
        with pytest.raises(FetchError) as exc_info:
            fetcher.fetch("http://example.com/timeout")
    assert exc_info.value.category == "timeout"
