"""Unit tests for Phase 2 quality signals and normalization."""

from __future__ import annotations

import hashlib
import json
from unittest.mock import MagicMock, patch

import pytest

from data_fetcher.models import CanonicalDocument, NormalizedDocument
from data_fetcher.phase2.language import detect_language, _extract_bigrams
from data_fetcher.phase2.normalization import NormalizationConfig, Normalizer, NormalizationResult
from data_fetcher.phase2.quality import QualityAnalyzer, QualityConfig, QualityResult


@pytest.fixture
def sample_canonical_document():
    return CanonicalDocument(
        id="canon-123",
        artifact_id="artifact-123",
        processing_job_id="job-123",
        source_url="http://example.com/page.html",
        source_mime_type="text/html",
        detected_format="html",
        extraction_status="completed",
        canonical_text="""Hello world
This is a test.
Hello world again.
""",
        structured_data={"links": [{"href": "/page2"}], "headings": [{"level": "h1", "text": "Title"}]},
        metadata={},
        structure={"title": "Test", "text": """Hello world
This is a test.
Hello world again.
""",},
        extraction_method="extractor-1.0.0",
        extraction_version="1.0.0",
        warnings=[],
        errors=[],
        original_checksum="abc123",
        canonical_checksum="def456",
        provenance={"artifact_id": "artifact-123"},
        created_at="2026-01-01",
        updated_at="2026-01-01",
    )


class TestNormalization:
    """Test normalization."""

    def test_unicode_normalization(self):
        normalizer = Normalizer(NormalizationConfig(enable_unicode_normalization=True))
        doc = CanonicalDocument(
            id="c1", artifact_id="a1", processing_job_id=None,
            source_url="http://example.com", source_mime_type="text/html", detected_format="html",
            extraction_status="completed", canonical_text="café", structured_data=None,
            metadata={}, structure=None, extraction_method="extractor-1.0.0",
            extraction_version="1.0.0", warnings=[], errors=[],
            original_checksum="abc", canonical_checksum="def",
            provenance={}, created_at="", updated_at="",
        )
        result = normalizer.normalize(doc)
        assert result.content_changed is True
        assert "unicode_normalization" in [op["operation"] for op in result.normalization_operations]

    def test_line_ending_normalization(self):
        normalizer = Normalizer(NormalizationConfig(enable_line_ending_normalization=True))
        doc = CanonicalDocument(
            id="c1", artifact_id="a1", processing_job_id=None,
            source_url="http://example.com", source_mime_type="text/html", detected_format="html",
            extraction_status="completed", canonical_text="Hello\r\nWorld\r\n", structured_data=None,
            metadata={}, structure=None, extraction_method="extractor-1.0.0",
            extraction_version="1.0.0", warnings=[], errors=[],
            original_checksum="abc", canonical_checksum="def",
            provenance={}, created_at="", updated_at="",
        )
        result = normalizer.normalize(doc)
        assert "\r" not in result.normalized_text
        assert result.content_changed is True

    def test_whitespace_normalization(self):
        normalizer = Normalizer(NormalizationConfig(enable_whitespace_normalization=True))
        doc = CanonicalDocument(
            id="c1", artifact_id="a1", processing_job_id=None,
            source_url="http://example.com", source_mime_type="text/html", detected_format="html",
            extraction_status="completed", canonical_text="""Hello   
World   
""", structured_data=None,
            metadata={}, structure=None, extraction_method="extractor-1.0.0",
            extraction_version="1.0.0", warnings=[], errors=[],
            original_checksum="abc", canonical_checksum="def",
            provenance={}, created_at="", updated_at="",
        )
        result = normalizer.normalize(doc)
        assert result.normalized_text == """Hello
World
"""
        assert result.content_changed is True

    def test_no_changes_when_already_normalized(self):
        normalizer = Normalizer()
        doc = CanonicalDocument(
            id="c1", artifact_id="a1", processing_job_id=None,
            source_url="http://example.com", source_mime_type="text/html", detected_format="html",
            extraction_status="completed", canonical_text="""Hello
World
""", structured_data=None,
            metadata={}, structure=None, extraction_method="extractor-1.0.0",
            extraction_version="1.0.0", warnings=[], errors=[],
            original_checksum="abc", canonical_checksum="def",
            provenance={}, created_at="", updated_at="",
        )
        result = normalizer.normalize(doc)
        assert result.content_changed is False
        assert len(result.normalization_operations) == 0

    def test_deterministic_normalization(self):
        normalizer = Normalizer()
        doc = CanonicalDocument(
            id="c1", artifact_id="a1", processing_job_id=None,
            source_url="http://example.com", source_mime_type="text/html", detected_format="html",
            extraction_status="completed", canonical_text="""Hello
World
""", structured_data=None,
            metadata={}, structure=None, extraction_method="extractor-1.0.0",
            extraction_version="1.0.0", warnings=[], errors=[],
            original_checksum="abc", canonical_checksum="def",
            provenance={}, created_at="", updated_at="",
        )
        r1 = normalizer.normalize(doc)
        r2 = normalizer.normalize(doc)
        assert r1.normalized_text == r2.normalized_text
        assert r1.normalized_checksum == r2.normalized_checksum

    def test_empty_content_normalization(self):
        normalizer = Normalizer()
        doc = CanonicalDocument(
            id="c1", artifact_id="a1", processing_job_id=None,
            source_url="http://example.com", source_mime_type="text/html", detected_format="html",
            extraction_status="completed", canonical_text="", structured_data=None,
            metadata={}, structure=None, extraction_method="extractor-1.0.0",
            extraction_version="1.0.0", warnings=[], errors=[],
            original_checksum="abc", canonical_checksum="def",
            provenance={}, created_at="", updated_at="",
        )
        result = normalizer.normalize(doc)
        assert result.normalized_text == ""
        assert result.content_changed is False


class TestQualitySignals:
    """Test quality signal computation."""

    def test_text_metrics(self, sample_canonical_document):
        analyzer = QualityAnalyzer()
        result = analyzer.analyze(sample_canonical_document)
        tm = result.text_metrics
        assert tm["character_count"] > 0
        assert tm["word_count"] > 0
        assert tm["line_count"] == 3

    def test_content_composition(self, sample_canonical_document):
        analyzer = QualityAnalyzer()
        result = analyzer.analyze(sample_canonical_document)
        cc = result.content_composition
        assert cc["alphabetic_ratio"] > 0
        assert cc["whitespace_ratio"] > 0
        assert cc["numeric_ratio"] >= 0

    def test_repetition_signals(self, sample_canonical_document):
        analyzer = QualityAnalyzer()
        result = analyzer.analyze(sample_canonical_document)
        rs = result.repetition_signals
        assert "repeated_line_ratio" in rs
        assert "vocabulary_diversity" in rs
        assert rs["suspicious_repetition"] is False

    def test_completeness_signals(self, sample_canonical_document):
        analyzer = QualityAnalyzer()
        result = analyzer.analyze(sample_canonical_document)
        cs = result.completeness_signals
        assert cs["is_empty"] is False
        assert cs["character_count"] > 0

    def test_empty_document_signals(self):
        doc = CanonicalDocument(
            id="c1", artifact_id="a1", processing_job_id=None,
            source_url="http://example.com", source_mime_type="text/html", detected_format="html",
            extraction_status="completed", canonical_text="", structured_data=None,
            metadata={}, structure=None, extraction_method="extractor-1.0.0",
            extraction_version="1.0.0", warnings=[], errors=[],
            original_checksum="abc", canonical_checksum="def",
            provenance={}, created_at="", updated_at="",
        )
        analyzer = QualityAnalyzer()
        result = analyzer.analyze(doc)
        assert result.text_metrics["character_count"] == 0
        assert result.completeness_signals["is_empty"] is True
        assert any("empty" in w.lower() for w in result.warnings)

    def test_short_document_signals(self):
        doc = CanonicalDocument(
            id="c1", artifact_id="a1", processing_job_id=None,
            source_url="http://example.com", source_mime_type="text/html", detected_format="html",
            extraction_status="completed", canonical_text="Hi", structured_data=None,
            metadata={}, structure=None, extraction_method="extractor-1.0.0",
            extraction_version="1.0.0", warnings=[], errors=[],
            original_checksum="abc", canonical_checksum="def",
            provenance={}, created_at="", updated_at="",
        )
        analyzer = QualityAnalyzer(QualityConfig(short_content_threshold=50))
        result = analyzer.analyze(doc)
        assert result.completeness_signals["is_short"] is True
        assert any("short" in w.lower() for w in result.warnings)

    def test_structured_data_signals_json(self):
        doc = CanonicalDocument(
            id="c1", artifact_id="a1", processing_job_id=None,
            source_url="http://example.com", source_mime_type="application/json", detected_format="json",
            extraction_status="completed", canonical_text="{}", structured_data={"type": "dict", "field_count": 2, "top_level_keys": ["a", "b"]},
            metadata={}, structure=None, extraction_method="extractor-1.0.0",
            extraction_version="1.0.0", warnings=[], errors=[],
            original_checksum="abc", canonical_checksum="def",
            provenance={}, created_at="", updated_at="",
        )
        analyzer = QualityAnalyzer()
        result = analyzer.analyze(doc)
        assert result.structured_data_signals is not None
        assert result.structured_data_signals["type"] == "json"
        assert result.structured_data_signals["field_count"] == 2

    def test_structured_data_signals_csv(self):
        doc = CanonicalDocument(
            id="c1", artifact_id="a1", processing_job_id=None,
            source_url="http://example.com", source_mime_type="text/csv", detected_format="csv",
            extraction_status="completed", canonical_text=""""a,b
1,2
""", structured_data={"type": "csv", "headers": ["a", "b"], "rows": [["1", "2"]], "row_count": 1, "column_count": 2},
            metadata={}, structure=None, extraction_method="extractor-1.0.0",
            extraction_version="1.0.0", warnings=[], errors=[],
            original_checksum="abc", canonical_checksum="def",
            provenance={}, created_at="", updated_at="",
        )
        analyzer = QualityAnalyzer()
        result = analyzer.analyze(doc)
        assert result.structured_data_signals is not None
        assert result.structured_data_signals["type"] == "csv"
        assert result.structured_data_signals["column_count"] == 2

    def test_inherited_warnings(self, sample_canonical_document):
        doc = CanonicalDocument(
            id="c1", artifact_id="a1", processing_job_id=None,
            source_url="http://example.com", source_mime_type="text/html", detected_format="html",
            extraction_status="completed", canonical_text="Hello world",
            structured_data=None, metadata={}, structure=None,
            extraction_method="extractor-1.0.0", extraction_version="1.0.0",
            warnings=["HTML boilerplate removal"], errors=[],
            original_checksum="abc", canonical_checksum="def",
            provenance={}, created_at="", updated_at="",
        )
        analyzer = QualityAnalyzer()
        result = analyzer.analyze(doc)
        assert result.completeness_signals["extraction_warnings_count"] == 1
        assert "HTML boilerplate removal" in result.completeness_signals["inherited_warnings"]


class TestLanguageDetection:
    """Test language detection."""

    def test_detect_english(self):
        text = "This is a test document about data pipelines and engineering concepts."
        result = detect_language(text)
        assert result.language == "English"
        assert result.confidence in ("high", "medium", "low")

    def test_detect_spanish(self):
        text = "Este es un documento de prueba sobre conceptos de ingeniería de datos."
        result = detect_language(text)
        assert result.language == "Spanish"

    def test_detect_french(self):
        text = "Ceci est un document de test sur les concepts d'ingénierie de données."
        result = detect_language(text)
        assert result.language == "French"

    def test_detect_german(self):
        text = "Dies ist ein Testdokument über Datenverarbeitungskonzepte und Engineering."
        result = detect_language(text)
        assert result.language in ("German", "Dutch", "English")

    def test_detect_empty_text(self):
        result = detect_language("")
        assert result.language == "unknown"
        assert result.confidence == "unknown"

    def test_detect_short_text(self):
        result = detect_language("Hi")
        assert result.language == "unknown" or result.confidence in ("low", "unknown")

    def test_deterministic_detection(self):
        text = "This is a deterministic language detection test."
        r1 = detect_language(text)
        r2 = detect_language(text)
        assert r1.language == r2.language
        assert r1.confidence == r2.confidence

    def test_bigram_extraction(self):
        bigrams = _extract_bigrams("hello world")
        assert "he" in bigrams
        assert "el" in bigrams
        assert "ll" in bigrams
        assert "lo" in bigrams
        assert "ow" in bigrams
        assert "or" in bigrams
        assert "rl" in bigrams
        assert "ld" in bigrams
