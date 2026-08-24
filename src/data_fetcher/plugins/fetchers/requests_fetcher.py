"""Fetcher plugin backed by :class:`data_fetcher.fetcher.Fetcher`.

This wrapper adapts the provenance-preserving HTTP fetcher from the existing
``data_fetcher.fetcher`` module to the ``data_fetcher_fetch`` hook so it can be
selected and invoked through the plugin manager.
"""

from __future__ import annotations

from typing import Any

from data_fetcher.config import load_config
from data_fetcher.fetcher import FetchError, Fetcher
from data_fetcher.plugin_base import DataFetcherPlugin, hookimpl


class RequestsFetcherPlugin(DataFetcherPlugin):
    """HTTP(S) fetcher implemented with the ``requests`` library."""

    name = "requests_fetcher"
    stage = "fetcher"
    version = "1.0.0"
    description = "Provenance-preserving HTTP fetcher built on requests."

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config
        self._fetcher: Fetcher | None = None

    def _build_fetcher(self) -> Fetcher:
        cfg = self._config or {}
        if "fetcher" in cfg:
            fc = cfg["fetcher"]
        else:
            try:
                fc = load_config()
            except Exception as exc:  # pragma: no cover - depends on env
                raise FetchError("config", f"unable to load fetcher config: {exc}") from exc
        return Fetcher(
            connect_timeout_seconds=fc.fetch_connect_timeout_seconds,
            read_timeout_seconds=fc.fetch_read_timeout_seconds,
            max_size_bytes=fc.fetch_max_size_bytes,
            max_retries=fc.fetch_max_retries,
            backoff_seconds=fc.fetch_backoff_seconds,
            max_redirects=fc.fetch_max_redirects,
            allowed_domains=fc.fetch_allowed_domains,
            allowed_content_types=fc.fetch_allowed_content_types,
        )

    def _get_fetcher(self) -> Fetcher:
        if self._fetcher is None:
            self._fetcher = self._build_fetcher()
        return self._fetcher

    def capabilities(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "transport": "http/https",
            "supports_redirects": True,
            "supports_retries": True,
            "supports_content_type_filtering": True,
        }

    @hookimpl
    def data_fetcher_fetch(self, url: str, config: dict[str, Any] | None = None) -> Any:
        merged = {**(self._config or {}), **(config or {})}
        if merged:
            self._config = merged
            self._fetcher = None
        return self._get_fetcher().fetch(url)
