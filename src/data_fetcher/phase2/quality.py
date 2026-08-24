"""Phase 2: Quality signals for canonical documents."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from data_fetcher.models import CanonicalDocument

logger = logging.getLogger(__name__)


class QualityError(Exception):
    """Quality-specific errors."""
    def __init__(self, category: str, message: str):
        self.category = category
        super().__init__(message)


@dataclass
class QualityConfig:
    """Configuration for quality analysis."""
    analysis_version: str = "1.0.0"
    max_repetition_sample_size: int = 1000
    vocabulary_diversity_threshold: float = 0.3
    short_content_threshold: int = 50
    empty_content_threshold: int = 0


@dataclass
class QualityResult:
    """Result of quality analysis."""
    canonical_document_id: str
    artifact_id: str
    analysis_version: str
    text_metrics: dict[str, Any]
    content_composition: dict[str, Any]
    repetition_signals: dict[str, Any]
    completeness_signals: dict[str, Any]
    structured_data_signals: dict[str, Any] | None
    warnings: list[str]
    errors: list[str]
    created_at: str


class QualityAnalyzer:
    """Analyze quality signals of canonical documents."""

    def __init__(self, config: QualityConfig | None = None) -> None:
        self.config = config or QualityConfig()

    def analyze(self, canonical_document: CanonicalDocument) -> QualityResult:
        """
        Analyze quality signals of a canonical document.
        
        Args:
            canonical_document: P2.3 canonical document
            
        Returns:
            QualityResult with measured signals
        """
        text = canonical_document.canonical_text or ""
        structured_data = canonical_document.structured_data
        warnings: list[str] = []
        errors: list[str] = []
        
        # Text metrics
        text_metrics = self._compute_text_metrics(text)
        
        # Content composition
        content_composition = self._compute_content_composition(text)
        
        # Repetition signals
        repetition_signals = self._compute_repetition_signals(text, warnings)
        
        # Completeness signals
        completeness_signals = self._compute_completeness_signals(text, canonical_document, warnings)
        
        # Structured data signals
        structured_data_signals = None
        if structured_data is not None:
            structured_data_signals = self._compute_structured_data_signals(structured_data, canonical_document.detected_format)
        
        return QualityResult(
            canonical_document_id=canonical_document.id,
            artifact_id=canonical_document.artifact_id,
            analysis_version=self.config.analysis_version,
            text_metrics=text_metrics,
            content_composition=content_composition,
            repetition_signals=repetition_signals,
            completeness_signals=completeness_signals,
            structured_data_signals=structured_data_signals,
            warnings=warnings,
            errors=errors,
            created_at="",
        )

    def _compute_text_metrics(self, text: str) -> dict[str, Any]:
        """Compute basic text metrics."""
        if not text:
            return {
                "character_count": 0,
                "word_count": 0,
                "line_count": 0,
                "estimated_token_count": 0,
                "avg_word_length": 0.0,
                "avg_line_length": 0.0,
                "min_line_length": 0,
                "max_line_length": 0,
            }
        
        lines = text.splitlines()
        words = text.split()
        
        line_lengths = [len(line) for line in lines] if lines else [0]
        word_lengths = [len(word) for word in words] if words else [0]
        
        return {
            "character_count": len(text),
            "word_count": len(words),
            "line_count": len(lines),
            "estimated_token_count": max(len(words), len(text) // 4),
            "avg_word_length": sum(word_lengths) / max(len(word_lengths), 1),
            "avg_line_length": sum(line_lengths) / max(len(line_lengths), 1),
            "min_line_length": min(line_lengths) if line_lengths else 0,
            "max_line_length": max(line_lengths) if line_lengths else 0,
        }

    def _compute_content_composition(self, text: str) -> dict[str, Any]:
        """Compute content composition ratios."""
        if not text:
            return {
                "alphabetic_ratio": 0.0,
                "numeric_ratio": 0.0,
                "whitespace_ratio": 0.0,
                "punctuation_ratio": 0.0,
                "symbol_ratio": 0.0,
                "unique_char_ratio": 0.0,
            }
        
        total = len(text)
        if total == 0:
            return {
                "alphabetic_ratio": 0.0,
                "numeric_ratio": 0.0,
                "whitespace_ratio": 0.0,
                "punctuation_ratio": 0.0,
                "symbol_ratio": 0.0,
                "unique_char_ratio": 0.0,
            }
        
        alphabetic = sum(1 for c in text if c.isalpha())
        numeric = sum(1 for c in text if c.isdigit())
        whitespace = sum(1 for c in text if c.isspace())
        punctuation = sum(1 for c in text if unicodedata.category(c).startswith("P"))
        symbol = sum(1 for c in text if unicodedata.category(c).startswith("S"))
        unique_chars = len(set(text))
        
        return {
            "alphabetic_ratio": round(alphabetic / total, 4),
            "numeric_ratio": round(numeric / total, 4),
            "whitespace_ratio": round(whitespace / total, 4),
            "punctuation_ratio": round(punctuation / total, 4),
            "symbol_ratio": round(symbol / total, 4),
            "unique_char_ratio": round(unique_chars / total, 4),
        }

    def _compute_repetition_signals(self, text: str, warnings: list[str]) -> dict[str, Any]:
        """Compute repetition and low-information signals."""
        if not text:
            return {
                "repeated_line_ratio": 0.0,
                "repeated_phrase_ratio": 0.0,
                "vocabulary_diversity": 0.0,
                "max_line_repetition": 0,
                "suspicious_repetition": False,
            }
        
        lines = text.splitlines()
        if not lines:
            return {
                "repeated_line_ratio": 0.0,
                "repeated_phrase_ratio": 0.0,
                "vocabulary_diversity": 0.0,
                "max_line_repetition": 0,
                "suspicious_repetition": False,
            }
        
        # Repeated lines
        line_counts: dict[str, int] = {}
        for line in lines:
            stripped = line.strip()
            if stripped:
                line_counts[stripped] = line_counts.get(stripped, 0) + 1
        
        max_line_repetition = max(line_counts.values()) if line_counts else 0
        repeated_lines = sum(1 for c in line_counts.values() if c > 1)
        repeated_line_ratio = repeated_lines / max(len(line_counts), 1)
        
        # Repeated phrases (bigrams)
        words = text.split()
        if len(words) >= 2:
            phrase_counts: dict[str, int] = {}
            for i in range(len(words) - 1):
                phrase = f"{words[i]} {words[i + 1]}"
                phrase_counts[phrase] = phrase_counts.get(phrase, 0) + 1
            
            repeated_phrases = sum(1 for c in phrase_counts.values() if c > 1)
            repeated_phrase_ratio = repeated_phrases / max(len(phrase_counts), 1)
        else:
            repeated_phrase_ratio = 0.0
        
        # Vocabulary diversity (unique words / total words)
        unique_words = len(set(words))
        vocabulary_diversity = unique_words / max(len(words), 1)
        
        suspicious_repetition = (
            repeated_line_ratio > 0.5 or
            repeated_phrase_ratio > 0.5 or
            vocabulary_diversity < self.config.vocabulary_diversity_threshold
        )
        
        if suspicious_repetition:
            warnings.append("Suspicious repetition detected")
        
        return {
            "repeated_line_ratio": round(repeated_line_ratio, 4),
            "repeated_phrase_ratio": round(repeated_phrase_ratio, 4),
            "vocabulary_diversity": round(vocabulary_diversity, 4),
            "max_line_repetition": max_line_repetition,
            "suspicious_repetition": suspicious_repetition,
        }

    def _compute_completeness_signals(self, text: str, canonical_document: CanonicalDocument, warnings: list[str]) -> dict[str, Any]:
        """Compute completeness signals."""
        char_count = len(text)
        is_empty = char_count == 0
        is_short = char_count < self.config.short_content_threshold and not is_empty
        
        # Inherited extraction warnings
        extraction_warnings = canonical_document.warnings or []
        extraction_warnings_count = len(extraction_warnings)
        
        # Check for truncation indicators
        has_truncation = any("truncat" in w.lower() for w in extraction_warnings)
        
        # Check for malformed content indicators
        has_malformed = any("malformed" in w.lower() or "error" in w.lower() for w in extraction_warnings + (canonical_document.errors or []))
        
        if is_empty:
            warnings.append("Document is empty")
        elif is_short:
            warnings.append(f"Document is very short ({char_count} characters)")
        
        return {
            "is_empty": is_empty,
            "is_short": is_short,
            "character_count": char_count,
            "extraction_warnings_count": extraction_warnings_count,
            "has_truncation": has_truncation,
            "has_malformed_content": has_malformed,
            "inherited_warnings": extraction_warnings[:5],
        }

    def _compute_structured_data_signals(self, structured_data: dict[str, Any], detected_format: str | None) -> dict[str, Any] | None:
        """Compute quality signals for structured data."""
        if not structured_data:
            return None
        
        signals: dict[str, Any] = {"format": detected_format}
        
        if detected_format == "json":
            signals.update(self._json_signals(structured_data))
        elif detected_format == "csv":
            signals.update(self._csv_signals(structured_data))
        elif detected_format == "xml":
            signals.update(self._xml_signals(structured_data))
        elif detected_format == "html":
            signals.update(self._html_signals(structured_data))
        
        return signals

    def _json_signals(self, data: dict[str, Any]) -> dict[str, Any]:
        """Compute JSON-specific quality signals."""
        signals: dict[str, Any] = {"type": "json"}
        
        if "type" in data and data["type"] == "dict":
            signals["field_count"] = data.get("field_count", 0)
            signals["top_level_keys"] = len(data.get("top_level_keys", []))
        elif "type" in data and data["type"] == "list":
            signals["item_count"] = data.get("item_count", 0)
            signals["record_type"] = data.get("record_type", "unknown")
        
        # Compute null/empty ratios if we have raw data
        raw = data.get("raw", data)
        if isinstance(raw, dict):
            values = raw.values()
            total_fields = len(values)
            if total_fields > 0:
                null_count = sum(1 for v in values if v is None)
                empty_str_count = sum(1 for v in values if v == "")
                signals["null_ratio"] = round(null_count / total_fields, 4)
                signals["empty_string_ratio"] = round(empty_str_count / total_fields, 4)
        
        return signals

    def _csv_signals(self, data: dict[str, Any]) -> dict[str, Any]:
        """Compute CSV-specific quality signals."""
        signals: dict[str, Any] = {"type": "csv"}
        
        headers = data.get("headers", [])
        rows = data.get("rows", [])
        
        signals["column_count"] = data.get("column_count", len(headers))
        signals["row_count"] = data.get("row_count", len(rows))
        
        # Missing value analysis
        total_cells = len(rows) * len(headers) if headers else 0
        empty_cells = 0
        if total_cells > 0:
            for row in rows:
                empty_cells += sum(1 for cell in row if not cell.strip())
        
        signals["missing_value_ratio"] = round(empty_cells / max(total_cells, 1), 4)
        signals["empty_cell_count"] = empty_cells
        
        return signals

    def _xml_signals(self, data: dict[str, Any]) -> dict[str, Any]:
        """Compute XML-specific quality signals."""
        signals: dict[str, Any] = {"type": "xml"}
        
        signals["root_tag"] = data.get("tag", "unknown")
        signals["child_count"] = len(data.get("children", []))
        signals["has_attributes"] = bool(data.get("attributes"))
        
        # Count empty text nodes
        children = data.get("children", [])
        empty_nodes = sum(1 for child in children if not child.get("text", "").strip())
        signals["empty_node_ratio"] = round(empty_nodes / max(len(children), 1), 4)
        
        return signals

    def _html_signals(self, data: dict[str, Any]) -> dict[str, Any]:
        """Compute HTML-specific quality signals."""
        signals: dict[str, Any] = {"type": "html"}
        
        text = data.get("text", "")
        original_length = data.get("_original_length", len(text))
        
        if original_length > 0:
            signals["extracted_ratio"] = round(len(text) / original_length, 4)
        else:
            signals["extracted_ratio"] = 0.0
        
        signals["link_count"] = len(data.get("links", []))
        signals["heading_count"] = len(data.get("headings", []))
        
        # Link density
        if text:
            signals["link_density"] = round(signals["link_count"] / max(len(text.split()), 1), 4)
        else:
            signals["link_density"] = 0.0
        
        return signals


def analyze_quality(canonical_document: CanonicalDocument, config: QualityConfig | None = None) -> QualityResult:
    """Convenience function to analyze quality of a canonical document."""
    analyzer = QualityAnalyzer(config)
    return analyzer.analyze(canonical_document)
