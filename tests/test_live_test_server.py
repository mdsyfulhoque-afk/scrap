from __future__ import annotations

from data_fetcher.live_test_server import build_test_url


def test_build_test_url_defaults():
    assert build_test_url("/ok") == "http://127.0.0.1:8765/ok"
