from __future__ import annotations

from data_fetcher.demo import main


def test_main_requires_url(capsys):
    exit_code = main([])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "usage:" in captured.err
    assert "url" in captured.err
