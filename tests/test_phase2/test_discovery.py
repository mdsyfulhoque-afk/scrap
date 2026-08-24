"""Unit tests for Phase 2 format discovery."""

from __future__ import annotations

import hashlib
from unittest.mock import MagicMock, patch

import pytest

from data_fetcher.phase2.discovery import DiscoveryConfig, DiscoveryError, FormatDiscovery
from data_fetcher.phase2.inventory import InventoryConfig


@pytest.fixture
def discovery():
    return FormatDiscovery(DiscoveryConfig())


class TestFormatDetection:
    """Test format detection."""

    def test_detect_html_from_content_type(self, discovery):
        fmt, confidence, evidence = discovery.detect_format(
            b"<html></html>", "text/html", "http://example.com/page.html"
        )
        assert fmt == "html"
        assert confidence in ("high", "medium")
        assert any(s["source"] == "mime" for s in evidence["sources"])

    def test_detect_json_from_content_type(self, discovery):
        fmt, confidence, evidence = discovery.detect_format(
            b'{"key": "value"}', "application/json", "http://example.com/data.json"
        )
        assert fmt == "json"
        assert confidence in ("high", "medium")

    def test_detect_plain_text_fallback(self, discovery):
        fmt, confidence, evidence = discovery.detect_format(
            b"hello world", None, None
        )
        assert fmt == "plain_text"
        assert confidence == "low"

    def test_detect_from_url_extension(self, discovery):
        fmt, confidence, evidence = discovery.detect_format(
            b"hello", "application/octet-stream", "http://example.com/data.csv"
        )
        assert fmt == "csv"
        assert confidence == "low"

    def test_detect_from_magic_bytes_html(self, discovery):
        fmt, confidence, evidence = discovery.detect_format(
            b"<!DOCTYPE html><html><head><title>Test</title></head><body><div>Hello</div><img src='test'></body></html>", None, None
        )
        assert fmt == "html"
        assert confidence == "high"

    def test_detect_from_magic_bytes_json(self, discovery):
        fmt, confidence, evidence = discovery.detect_format(
            b'[{"a": 1}]', None, None
        )
        assert fmt == "json"
        assert confidence == "high"

    def test_detect_csv_from_content(self, discovery):
        csv_data = b"a,b,c\n1,2,3\n4,5,6\n7,8,9\n"
        fmt, confidence, evidence = discovery.detect_format(csv_data, None, None)
        assert fmt == "csv"

    def test_detect_markdown_from_content(self, discovery):
        md_data = b"# Title\n\nSome paragraph\n\n- item1\n- item2\n"
        fmt, confidence, evidence = discovery.detect_format(md_data, None, None)
        assert fmt == "markdown"

    def test_detect_html_from_content_inspection(self, discovery):
        html_data = b"<html><head><title>Test</title></head><body>Hello</body></html>"
        fmt, confidence, evidence = discovery.detect_format(html_data, None, None)
        assert fmt == "html"

    def test_unknown_format_binary_data(self, discovery):
        fmt, confidence, evidence = discovery.detect_format(
            b"\x00\x01\x02\x03\x04", None, None
        )
        assert fmt is None
        assert confidence == "unknown"


class TestEncodingDetection:
    """Test encoding detection."""

    def test_detect_utf8(self, discovery):
        enc, confidence = discovery.detect_encoding(b"hello world")
        assert enc == "utf-8"
        assert confidence == "high"

    def test_detect_utf8_bom(self, discovery):
        enc, confidence = discovery.detect_encoding(b"\xef\xbb\xbfhello")
        assert enc == "utf-8-sig"
        assert confidence == "high"

    def test_detect_latin1_fallback(self, discovery):
        data = b"\xff\xfehello"
        enc, confidence = discovery.detect_encoding(data)
        assert enc == "latin-1"
        assert confidence == "low"

    def test_detect_empty_data(self, discovery):
        enc, confidence = discovery.detect_encoding(b"")
        assert enc is None
        assert confidence == "unknown"


class TestStructuralType:
    """Test structural type classification."""

    def test_html_article_like(self, discovery):
        html = b"<html><article><p>Content</p></article></html>"
        stype = discovery.classify_structural_type(html, "html")
        assert stype == "article-like"

    def test_html_navigation_heavy(self, discovery):
        html = b"<html><nav><ul><li>Link</li></ul></nav></html>"
        stype = discovery.classify_structural_type(html, "html")
        assert stype == "navigation-heavy"

    def test_html_document(self, discovery):
        html = b"<html><body><p>Just a page</p></body></html>"
        stype = discovery.classify_structural_type(html, "html")
        assert stype == "document"

    def test_json_object(self, discovery):
        stype = discovery.classify_structural_type(b'{"key": "value"}', "json")
        assert stype == "object"

    def test_json_array_of_records(self, discovery):
        stype = discovery.classify_structural_type(b'[{"a": 1}, {"a": 2}]', "json")
        assert stype == "array-of-records"

    def test_csv_tabular(self, discovery):
        csv_data = b"a,b,c\n1,2,3\n"
        stype = discovery.classify_structural_type(csv_data, "csv")
        assert stype == "tabular"

    def test_markdown_headings(self, discovery):
        md = b"# Title\n## Subtitle\n"
        stype = discovery.classify_structural_type(md, "markdown")
        assert stype == "headings-paragraphs"

    def test_plain_text_multi_line(self, discovery):
        text = b"line1\nline2\nline3\n"
        stype = discovery.classify_structural_type(text, "plain_text")
        assert stype == "multi-line"


class TestDocumentTypeInference:
    """Test document type inference."""

    def test_html_article(self, discovery):
        html = b"<article><p>Content</p></article>"
        types = discovery.infer_document_type(html, "html", "article-like")
        assert "article" in types

    def test_html_form(self, discovery):
        html = b"<form><input name='q'></form>"
        types = discovery.infer_document_type(html, "html", "document")
        assert "form" in types

    def test_json_api_response(self, discovery):
        json_data = b'{"api": "v1", "endpoint": "/users"}'
        types = discovery.infer_document_type(json_data, "json", "object")
        assert "api-response" in types

    def test_json_error_log(self, discovery):
        json_data = b'{"error": "not found", "message": "details"}'
        types = discovery.infer_document_type(json_data, "json", "object")
        assert "error-log" in types

    def test_csv_tabular_data(self, discovery):
        csv_data = b"a,b,c\n1,2,3\n"
        types = discovery.infer_document_type(csv_data, "csv", "tabular")
        assert "tabular-data" in types

    def test_plain_text(self, discovery):
        types = discovery.infer_document_type(b"hello world", "plain_text", "single-line")
        assert "text" in types


class TestSchemaInference:
    """Test schema inference."""

    def test_json_array_of_records_schema(self, discovery):
        json_data = b'[{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}]'
        schema = discovery.infer_schema(json_data, "json")
        assert schema is not None
        assert schema["type"] == "array-of-records"
        assert "fields" in schema
        assert schema["record_count"] == 2

    def test_json_object_schema(self, discovery):
        json_data = b'{"name": "test", "version": "1.0"}'
        schema = discovery.infer_schema(json_data, "json")
        assert schema is not None
        assert schema["type"] == "object"

    def test_csv_schema(self, discovery):
        csv_data = b"name,age,city\nAlice,30,NYC\nBob,25,LA\n"
        schema = discovery.infer_schema(csv_data, "csv")
        assert schema is not None
        assert schema["type"] == "tabular"
        assert schema["column_count"] == 3
        assert schema["row_count"] == 2

    def test_xml_schema(self, discovery):
        xml_data = b'<root><item id="1"/><item id="2"/></root>'
        schema = discovery.infer_schema(xml_data, "xml")
        assert schema is not None
        assert schema["type"] == "hierarchy"
        assert schema["root_tag"] == "root"

    def test_unsupported_format_schema(self, discovery):
        schema = discovery.infer_schema(b"hello", "plain_text")
        assert schema is None


class TestMetadataAvailability:
    """Test metadata availability assessment."""

    def test_with_content_type_and_url(self, discovery):
        availability = discovery.assess_metadata_availability("text/html", "http://example.com", b"<html><title>Test</title></html>")
        assert availability["content_type_present"] is True
        assert availability["url_present"] is True
        assert availability["title_indicators"] is True

    def test_without_metadata(self, discovery):
        availability = discovery.assess_metadata_availability(None, None, b"hello")
        assert availability["content_type_present"] is False
        assert availability["url_present"] is False


class TestContentStatistics:
    """Test content statistics computation."""

    def test_basic_statistics(self, discovery):
        stats = discovery.compute_content_statistics(b"hello world\nfoo bar", "plain_text", "utf-8")
        assert stats["byte_count"] == 19
        assert stats["character_count"] == 19
        assert stats["line_count"] == 2
        assert stats["word_count_estimate"] == 4

    def test_json_statistics(self, discovery):
        json_data = b'[{"a": 1}, {"a": 2}, {"a": 3}]'
        stats = discovery.compute_content_statistics(json_data, "json", "utf-8")
        assert stats["record_count"] == 3

    def test_csv_statistics(self, discovery):
        csv_data = b"a,b,c\n1,2,3\n4,5,6\n"
        stats = discovery.compute_content_statistics(csv_data, "csv", "utf-8")
        assert stats["column_count"] == 3
        assert stats["row_count"] == 2

    def test_empty_data_statistics(self, discovery):
        stats = discovery.compute_content_statistics(b"", "plain_text", "utf-8")
        assert stats["byte_count"] == 0
        assert stats["character_count"] == 0


class TestExtractionSuitability:
    """Test extraction suitability assessment."""

    def test_supported_format_suitable(self, discovery):
        assert discovery.assess_extraction_suitability("html", "document") == "suitable"
        assert discovery.assess_extraction_suitability("json", "object") == "suitable"
        assert discovery.assess_extraction_suitability("csv", "tabular") == "suitable"

    def test_unknown_format(self, discovery):
        assert discovery.assess_extraction_suitability(None, None) == "unknown"


class TestFullCharacterization:
    """Test full characterization pipeline."""

    def test_characterize_html_artifact(self, discovery):
        raw_data = b"<!DOCTYPE html><html><head><title>Test</title></head><body><article><p>Content</p></article></body></html>"
        result = discovery.characterize(
            raw_data=raw_data,
            content_type="text/html",
            url="http://example.com/page.html",
            artifact_id="artifact-123",
        )
        assert result.artifact_id == "artifact-123"
        assert result.detected_format == "html"
        assert result.format_confidence in ("high", "medium")
        assert result.structural_type == "article-like"
        assert result.encoding == "utf-8"
        assert result.extraction_suitability == "suitable"
        assert result.is_deterministic is True

    def test_characterize_json_artifact(self, discovery):
        raw_data = b'{"name": "test", "items": [1, 2, 3]}'
        result = discovery.characterize(
            raw_data=raw_data,
            content_type="application/json",
            url="http://example.com/data.json",
            artifact_id="artifact-456",
        )
        assert result.detected_format == "json"
        assert result.encoding == "utf-8"
        assert result.structural_type == "object"
        assert result.extraction_suitability == "suitable"

    def test_characterize_csv_artifact(self, discovery):
        raw_data = b"name,age,city\nAlice,30,NYC\nBob,25,LA\n"
        result = discovery.characterize(
            raw_data=raw_data,
            content_type="text/csv",
            url="http://example.com/data.csv",
            artifact_id="artifact-789",
        )
        assert result.detected_format == "csv"
        assert result.structural_type == "tabular"
        assert result.extraction_suitability == "suitable"

    def test_characterize_unknown_format(self, discovery):
        raw_data = b"\x00\x01\x02\x03\x04"
        result = discovery.characterize(
            raw_data=raw_data,
            content_type="application/octet-stream",
            url="http://example.com/data.bin",
            artifact_id="artifact-000",
        )
        assert result.detected_format is None
        assert result.extraction_suitability == "unknown"
        assert len(result.warnings) > 0

    def test_characterize_with_custom_config(self, discovery):
        raw_data = b"hello world"
        result = discovery.characterize(
            raw_data=raw_data,
            content_type=None,
            url=None,
            artifact_id="artifact-custom",
            config={"characterization_version": "2.0.0", "max_preview_bytes": 1024},
        )
        assert result.characterization_version == "2.0.0"
        assert result.detected_format == "plain_text"


class TestAnalysisScope:
    """Test characterization scope metadata."""

    def test_preview_scope_for_large_artifact(self, discovery):
        large_data = b"x" * 100000
        stats = discovery.compute_content_statistics(large_data, "plain_text", "utf-8")
        assert stats["byte_count"] == 100000
        assert stats["preview_byte_count"] == 65536
        assert stats["bytes_analyzed"] == 65536
        assert stats["analysis_scope"] == "preview"

    def test_full_scope_for_small_artifact(self, discovery):
        small_data = b"hello world"
        stats = discovery.compute_content_statistics(small_data, "plain_text", "utf-8")
        assert stats["byte_count"] == 11
        assert stats["preview_byte_count"] == 11
        assert stats["bytes_analyzed"] == 11
        assert stats["analysis_scope"] == "full"

    def test_empty_artifact_scope(self, discovery):
        stats = discovery.compute_content_statistics(b"", "plain_text", "utf-8")
        assert stats["byte_count"] == 0
        assert stats["bytes_analyzed"] == 0
        assert stats["analysis_scope"] == "none"


class TestDeterministicRepeat:
    """Test deterministic repeated characterization."""

    def test_repeat_characterization_produces_same_result(self, discovery):
        raw_data = b"<!DOCTYPE html><html><head><title>Test</title></head><body><article><p>Content</p></article></body></html>"
        result1 = discovery.characterize(
            raw_data=raw_data,
            content_type="text/html",
            url="http://example.com/page.html",
            artifact_id="artifact-repeat",
        )
        result2 = discovery.characterize(
            raw_data=raw_data,
            content_type="text/html",
            url="http://example.com/page.html",
            artifact_id="artifact-repeat",
        )
        assert result1.detected_format == result2.detected_format
        assert result1.format_confidence == result2.format_confidence
        assert result1.structural_type == result2.structural_type
        assert result1.encoding == result2.encoding
        assert result1.content_statistics == result2.content_statistics
