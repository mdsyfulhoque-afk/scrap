"""Dedupe plugin backed by :class:`data_fetcher.phase2.deduplication.DuplicateDetector`.

Wraps the trigram + Jaccard near-duplicate detector (with min-hash banding for
candidate generation) as a ``data_fetcher_deduplicate`` hook implementation.
"""

from __future__ import annotations

from typing import Any

from data_fetcher.phase2.deduplication import DuplicateDetectionConfig, DuplicateDetector
from data_fetcher.plugin_base import DataFetcherPlugin, hookimpl


class TrigramJaccardDedupePlugin(DataFetcherPlugin):
    """Trigram + Jaccard near-duplicate detector."""

    name = "trigram_jaccard_dedupe"
    stage = "dedupe"
    version = "1.0.0"
    description = "Trigram/Jaccard near-duplicate detection with min-hash banding."

    def __init__(self, config: DuplicateDetectionConfig | None = None) -> None:
        self._detector = DuplicateDetector(config)

    def capabilities(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "algorithm": "trigram-jaccard",
            "jaccard_threshold": self._detector.config.jaccard_threshold,
            "min_hash_sketch_size": self._detector.config.min_hash_sketch_size,
            "band_count": self._detector.config.band_count,
            "detects": ["raw_exact", "normalized_exact", "near_duplicate"],
        }

    @hookimpl
    def data_fetcher_deduplicate(self, documents: list[Any], config: dict[str, Any] | None = None) -> Any:
        return self._detector.detect(documents)
