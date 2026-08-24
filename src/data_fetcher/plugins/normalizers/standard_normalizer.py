"""Normalizer plugin backed by :class:`data_fetcher.phase2.normalization.Normalizer`.

Wraps the deterministic, versioned normalizer (Unicode NFC, line-ending,
whitespace and control-character normalization) as a ``data_fetcher_normalize``
hook implementation.
"""

from __future__ import annotations

from typing import Any

from data_fetcher.phase2.normalization import NormalizationConfig, Normalizer
from data_fetcher.plugin_base import DataFetcherPlugin, hookimpl


class StandardNormalizerPlugin(DataFetcherPlugin):
    """Deterministic canonical-document normalizer."""

    name = "standard_normalizer"
    stage = "normalizer"
    version = "1.0.0"
    description = "Deterministic Unicode/whitespace/control-char normalization."

    def __init__(self, config: NormalizationConfig | None = None) -> None:
        self._normalizer = Normalizer(config)

    def capabilities(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "operations": [
                "unicode_nfc",
                "line_ending_normalization",
                "whitespace_normalization",
                "control_character_removal",
            ],
            "non_destructive": True,
        }

    @hookimpl
    def data_fetcher_normalize(self, canonical_document: Any, config: dict[str, Any] | None = None) -> Any:
        return self._normalizer.normalize(canonical_document)
