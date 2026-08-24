"""Extractor plugin backed by :class:`data_fetcher.phase2.extraction.Extractor`.

Wraps the existing format-aware canonical extractor (HTML, JSON, XML, CSV,
Markdown and plain text) as a ``data_fetcher_extract`` hook implementation.
"""

from __future__ import annotations

from typing import Any

from data_fetcher.phase2.extraction import ExtractionConfig, Extractor
from data_fetcher.plugin_base import DataFetcherPlugin, hookimpl


class HeuristicExtractorPlugin(DataFetcherPlugin):
    """Format-aware canonical extractor."""

    name = "heuristic_extractor"
    stage = "extractor"
    version = "1.0.0"
    description = "Heuristic canonical extractor for HTML/JSON/XML/CSV/Markdown/text."

    def __init__(self, config: ExtractionConfig | None = None) -> None:
        self._extractor = Extractor(config)

    def capabilities(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "formats": ["html", "json", "xml", "csv", "markdown", "plain_text", "text"],
            "preserves_structure": True,
        }

    @hookimpl
    def data_fetcher_extract(
        self,
        raw_data: bytes,
        characterization: Any,
        config: dict[str, Any] | None = None,
    ) -> Any:
        processing_job_id = (config or {}).get("processing_job_id")
        return self._extractor.extract(raw_data, characterization, processing_job_id)
