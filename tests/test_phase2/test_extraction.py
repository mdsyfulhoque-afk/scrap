"""Unit tests for Phase 2 extraction."""

from __future__ import annotations

import hashlib
from unittest.mock import MagicMock, patch

import pytest

from data_fetcher.models import ArtifactCharacterization, CanonicalDocument
from data_fetcher.phase2.extraction import (
    ExtractionConfig,
    ExtractionError,
    ExtractionResult,
    Extractor,
    _extract_csv,
    _extract_html,
    _extract_json,
    _extract_markdown,
    _extract_plain_text,
    _extract_xml,
)
from data_fetcher.phase2.inventory import InventoryConfig


@pytest.fixture
def sample_characterization():
    return ArtifactCharacterization(
        id="char-123",
        artifact_id="artifact-123",
        characterization_version="1.0.0",
        characterization_config={"max_preview_bytes": 65536},
        detected_format="html",
        format_confidence="high",
        format_evidence={"url": "http://example.com/page.html", "original_checksum": "abc123"},
        mime_type="text/html",
        file_extension="html",
        encoding="utf-8",
        structural_type="document",
        document_type_candidates=["webpage"],
        schema_summary=None,
        content_statistics={"byte_count": 100, "character_count": 80, "line_count": 5, "word_count_estimate": 12, "bytes_analyzed": 100, "analysis_scope": "full"},
        metadata_availability={"content_type_present": True, "url_present": True},
        extraction_suitability="suitable",
        warnings=[],
        errors=[],
        is_deterministic=True,
        characterized_at="2026-08-17T10:00:00Z",
        created_at="2026-08-17T10:00:00Z",
    )


class TestHTMLExtraction:
    """Test HTML extraction."""

    def test_basic_html_extraction(self):
        html = b"<html><head><title>Test Page</title></head><body><p>Hello world</p></body></html>"
        result = _extract_html(html, "utf-8")
        assert result.extraction_status == "completed"
        assert "Hello world" in result.canonical_text
        assert result.structure is not None
        assert result.structure["title"] == "Test Page"
        assert result.canonical_checksum is not None

    def test_html_extracts_links(self):
        html = b"<html><body><a href='/page1'>Link 1</a><a href='/page2'>Link 2</a></body></html>"
        result = _extract_html(html, "utf-8")
        assert result.extraction_status == "completed"
        assert len(result.structure["links"]) == 2

    def test_html_skips_script_style(self):
        html = b"<html><head><script>var x=1;</script><style>body{}</style></head><body><p>Visible</p></body></html>"
        result = _extract_html(html, "utf-8")
        assert result.extraction_status == "completed"
        assert "Visible" in result.canonical_text
        assert "var x=1" not in result.canonical_text

    def test_html_empty_content(self):
        html = b"<html><head><title>Empty</title></head><body></body></html>"
        result = _extract_html(html, "utf-8")
        assert result.extraction_status == "completed"
        assert "Empty" in result.canonical_text

    def test_html_malformed(self):
        html = b"<html><body><p>Unclosed"
        result = _extract_html(html, "utf-8")
        assert result.extraction_status in ("completed", "partial")

    def test_html_encoding_error(self):
        # Invalid UTF-8 that can't be replaced
        html = b"\xff\xfe<html>"
        result = _extract_html(html, "utf-8")
        assert result.extraction_status == "completed"  # html.parser is tolerant


class TestJSONExtraction:
    """Test JSON extraction."""

    def test_basic_json_object(self):
        data = b'{"name": "test", "value": 42}'
        result = _extract_json(data, "utf-8")
        assert result.extraction_status == "completed"
        assert result.structured_data == {"name": "test", "value": 42}
        assert result.canonical_checksum is not None

    def test_json_array_of_records(self):
        data = b'[{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]'
        result = _extract_json(data, "utf-8")
        assert result.extraction_status == "completed"
        assert result.structure["record_type"] == "array-of-records"
        assert result.structure["item_count"] == 2

    def test_json_nested_structure(self):
        data = b'{"users": [{"name": "Alice", "tags": ["admin", "user"]}]}'
        result = _extract_json(data, "utf-8")
        assert result.extraction_status == "completed"
        assert result.structured_data["users"][0]["tags"] == ["admin", "user"]

    def test_json_invalid(self):
        data = b'{"name": "test", invalid json}'
        with pytest.raises(ExtractionError) as exc_info:
            _extract_json(data, "utf-8")
        assert exc_info.value.category == "corrupted_format"

    def test_json_deterministic_output(self):
        data = b'{"b": 2, "a": 1}'
        result1 = _extract_json(data, "utf-8")
        result2 = _extract_json(data, "utf-8")
        assert result1.canonical_text == result2.canonical_text
        assert result1.canonical_checksum == result2.canonical_checksum


class TestXMLExtraction:
    """Test XML extraction."""

    def test_basic_xml(self):
        xml = b'<root><item id="1">Hello</item><item id="2">World</item></root>'
        result = _extract_xml(xml, "utf-8")
        assert result.extraction_status == "completed"
        assert result.structure["root_tag"] == "root"
        assert result.structure["child_count"] == 2

    def test_xml_preserves_structure(self):
        xml = b'<data><record><name>Alice</name><age>30</age></record></data>'
        result = _extract_xml(xml, "utf-8")
        assert result.extraction_status == "completed"
        assert result.structured_data["tag"] == "data"
        assert len(result.structured_data["children"]) == 1

    def test_xml_malformed(self):
        xml = b'<root><item>Unclosed'
        with pytest.raises(ExtractionError) as exc_info:
            _extract_xml(xml, "utf-8")
        assert exc_info.value.category == "corrupted_format"


class TestCSVExtraction:
    """Test CSV extraction."""

    def test_basic_csv(self):
        csv_data = b"name,age,city\nAlice,30,NYC\nBob,25,LA\n"
        result = _extract_csv(csv_data, "utf-8")
        assert result.extraction_status == "completed"
        assert result.structure["row_count"] == 2
        assert result.structure["column_count"] == 3
        assert result.structured_data["headers"] == ["name", "age", "city"]

    def test_csv_empty(self):
        csv_data = b""
        with pytest.raises(ExtractionError) as exc_info:
            _extract_csv(csv_data, "utf-8")
        assert exc_info.value.category == "empty_content"

    def test_csv_single_row(self):
        csv_data = b"name,age\nAlice,30\n"
        result = _extract_csv(csv_data, "utf-8")
        assert result.extraction_status == "completed"
        assert result.structure["row_count"] == 1


class TestMarkdownExtraction:
    """Test Markdown extraction."""

    def test_basic_markdown(self):
        md = b"# Title\n\nSome paragraph text.\n"
        result = _extract_markdown(md, "utf-8")
        assert result.extraction_status == "completed"
        assert result.structure["heading_count"] == 1
        assert result.structure["type"] == "markdown"

    def test_markdown_code_blocks(self):
        md = b"# Title\n\n```python\nprint('hello')\n```\n"
        result = _extract_markdown(md, "utf-8")
        assert result.extraction_status == "completed"
        assert result.structure["code_block_count"] == 1
        assert "python" in result.structure["code_languages"]

    def test_markdown_preserves_text(self):
        md = b"# Heading\n\nParagraph with **bold** and *italic*.\n"
        result = _extract_markdown(md, "utf-8")
        assert result.extraction_status == "completed"
        assert "Heading" in result.canonical_text
        assert "Paragraph" in result.canonical_text


class TestPlainTextExtraction:
    """Test plain text extraction."""

    def test_basic_plain_text(self):
        text = b"Hello world\nThis is line 2\n"
        result = _extract_plain_text(text, "utf-8")
        assert result.extraction_status == "completed"
        assert result.canonical_text == "Hello world\nThis is line 2\n"
        assert result.structure["line_count"] == 2

    def test_plain_text_normalizes_line_endings(self):
        text = b"Hello\r\nWorld\r\n"
        result = _extract_plain_text(text, "utf-8")
        assert result.extraction_status == "completed"
        assert "\r\n" not in result.canonical_text
        assert result.canonical_text == "Hello\nWorld\n"

    def test_plain_text_strips_trailing_whitespace(self):
        text = b"Hello   \nWorld   \n"
        result = _extract_plain_text(text, "utf-8")
        assert result.extraction_status == "completed"
        assert result.canonical_text == "Hello\nWorld\n"

    def test_plain_text_deterministic(self):
        text = b"Line1\nLine2\n"
        result1 = _extract_plain_text(text, "utf-8")
        result2 = _extract_plain_text(text, "utf-8")
        assert result1.canonical_text == result2.canonical_text
        assert result1.canonical_checksum == result2.canonical_checksum


class TestExtractorDispatch:
    """Test format dispatch."""

    def test_dispatch_html(self):
        extractor = Extractor()
        char = ArtifactCharacterization(
            id="c1", artifact_id="a1", characterization_version="1.0.0", characterization_config={},
            detected_format="html", format_confidence="high", format_evidence={}, mime_type="text/html",
            file_extension="html", encoding="utf-8", structural_type="document", document_type_candidates=[],
            schema_summary=None, content_statistics={}, metadata_availability={}, extraction_suitability="suitable",
            warnings=[], errors=[], is_deterministic=True, characterized_at="2026-01-01", created_at="2026-01-01",
        )
        result = extractor.extract(b"<html><body>test</body></html>", char)
        assert result.extraction_status == "completed"
        assert result.detected_format == "html"

    def test_dispatch_json(self):
        extractor = Extractor()
        char = ArtifactCharacterization(
            id="c1", artifact_id="a1", characterization_version="1.0.0", characterization_config={},
            detected_format="json", format_confidence="high", format_evidence={}, mime_type="application/json",
            file_extension="json", encoding="utf-8", structural_type="object", document_type_candidates=[],
            schema_summary=None, content_statistics={}, metadata_availability={}, extraction_suitability="suitable",
            warnings=[], errors=[], is_deterministic=True, characterized_at="2026-01-01", created_at="2026-01-01",
        )
        result = extractor.extract(b'{"key": "value"}', char)
        assert result.extraction_status == "completed"
        assert result.detected_format == "json"

    def test_dispatch_unsupported_format(self):
        extractor = Extractor()
        char = ArtifactCharacterization(
            id="c1", artifact_id="a1", characterization_version="1.0.0", characterization_config={},
            detected_format="pdf", format_confidence="medium", format_evidence={}, mime_type="application/pdf",
            file_extension="pdf", encoding="utf-8", structural_type="unknown", document_type_candidates=[],
            schema_summary=None, content_statistics={}, metadata_availability={}, extraction_suitability="unsuitable",
            warnings=[], errors=[], is_deterministic=True, characterized_at="2026-01-01", created_at="2026-01-01",
        )
        result = extractor.extract(b"%PDF-1.4...", char)
        assert result.extraction_status == "unsupported"
        assert len(result.errors) > 0

    def test_dispatch_unknown_format(self):
        extractor = Extractor()
        char = ArtifactCharacterization(
            id="c1", artifact_id="a1", characterization_version="1.0.0", characterization_config={},
            detected_format=None, format_confidence="unknown", format_evidence={}, mime_type=None,
            file_extension=None, encoding=None, structural_type=None, document_type_candidates=[],
            schema_summary=None, content_statistics={}, metadata_availability={}, extraction_suitability="unknown",
            warnings=[], errors=[], is_deterministic=True, characterized_at="2026-01-01", created_at="2026-01-01",
        )
        result = extractor.extract(b"\x00\x01\x02", char)
        assert result.extraction_status == "failed"
        assert len(result.errors) > 0

    def test_dispatch_unsuitable_format(self):
        extractor = Extractor()
        char = ArtifactCharacterization(
            id="c1", artifact_id="a1", characterization_version="1.0.0", characterization_config={},
            detected_format="html", format_confidence="low", format_evidence={}, mime_type="text/html",
            file_extension="html", encoding="utf-8", structural_type="document", document_type_candidates=[],
            schema_summary=None, content_statistics={}, metadata_availability={}, extraction_suitability="unsuitable",
            warnings=[], errors=[], is_deterministic=True, characterized_at="2026-01-01", created_at="2026-01-01",
        )
        result = extractor.extract(b"<html></html>", char)
        assert result.extraction_status == "unsupported"


class TestDeterministicExtraction:
    """Test deterministic extraction."""

    def test_html_deterministic(self):
        extractor = Extractor()
        char = ArtifactCharacterization(
            id="c1", artifact_id="a1", characterization_version="1.0.0", characterization_config={},
            detected_format="html", format_confidence="high", format_evidence={}, mime_type="text/html",
            file_extension="html", encoding="utf-8", structural_type="document", document_type_candidates=[],
            schema_summary=None, content_statistics={}, metadata_availability={}, extraction_suitability="suitable",
            warnings=[], errors=[], is_deterministic=True, characterized_at="2026-01-01", created_at="2026-01-01",
        )
        r1 = extractor.extract(b"<html><body><p>Test</p></body></html>", char)
        r2 = extractor.extract(b"<html><body><p>Test</p></body></html>", char)
        assert r1.canonical_text == r2.canonical_text
        assert r1.canonical_checksum == r2.canonical_checksum

    def test_json_deterministic(self):
        extractor = Extractor()
        char = ArtifactCharacterization(
            id="c1", artifact_id="a1", characterization_version="1.0.0", characterization_config={},
            detected_format="json", format_confidence="high", format_evidence={}, mime_type="application/json",
            file_extension="json", encoding="utf-8", structural_type="object", document_type_candidates=[],
            schema_summary=None, content_statistics={}, metadata_availability={}, extraction_suitability="suitable",
            warnings=[], errors=[], is_deterministic=True, characterized_at="2026-01-01", created_at="2026-01-01",
        )
        r1 = extractor.extract(b'{"b": 2, "a": 1}', char)
        r2 = extractor.extract(b'{"b": 2, "a": 1}', char)
        assert r1.canonical_text == r2.canonical_text
        assert r1.canonical_checksum == r2.canonical_checksum


class TestStructuredDataPreservation:
    """Test structured data preservation."""

    def test_json_preserves_structure(self):
        extractor = Extractor()
        char = ArtifactCharacterization(
            id="c1", artifact_id="a1", characterization_version="1.0.0", characterization_config={},
            detected_format="json", format_confidence="high", format_evidence={}, mime_type="application/json",
            file_extension="json", encoding="utf-8", structural_type="object", document_type_candidates=[],
            schema_summary=None, content_statistics={}, metadata_availability={}, extraction_suitability="suitable",
            warnings=[], errors=[], is_deterministic=True, characterized_at="2026-01-01", created_at="2026-01-01",
        )
        result = extractor.extract(b'{"users": [{"id": 1, "active": true}]}', char)
        assert result.structured_data["users"][0]["active"] is True

    def test_csv_preserves_structure(self):
        extractor = Extractor()
        char = ArtifactCharacterization(
            id="c1", artifact_id="a1", characterization_version="1.0.0", characterization_config={},
            detected_format="csv", format_confidence="high", format_evidence={}, mime_type="text/csv",
            file_extension="csv", encoding="utf-8", structural_type="tabular", document_type_candidates=[],
            schema_summary=None, content_statistics={}, metadata_availability={}, extraction_suitability="suitable",
            warnings=[], errors=[], is_deterministic=True, characterized_at="2026-01-01", created_at="2026-01-01",
        )
        result = extractor.extract(b"name,age\nAlice,30\n", char)
        assert result.structured_data["headers"] == ["name", "age"]
        assert result.structured_data["rows"] == [["Alice", "30"]]

    def test_xml_preserves_structure(self):
        extractor = Extractor()
        char = ArtifactCharacterization(
            id="c1", artifact_id="a1", characterization_version="1.0.0", characterization_config={},
            detected_format="xml", format_confidence="high", format_evidence={}, mime_type="application/xml",
            file_extension="xml", encoding="utf-8", structural_type="hierarchy", document_type_candidates=[],
            schema_summary=None, content_statistics={}, metadata_availability={}, extraction_suitability="suitable",
            warnings=[], errors=[], is_deterministic=True, characterized_at="2026-01-01", created_at="2026-01-01",
        )
        result = extractor.extract(b'<root attr="1"><child>text</child></root>', char)
        assert result.structured_data["tag"] == "root"
        assert result.structured_data["attributes"] == {"attr": "1"}
        assert result.structured_data["children"][0]["tag"] == "child"


class TestAuditRegressionTests:
    """Regression tests for P2.3 audit findings."""

    def test_structured_data_checksum_populated(self):
        extractor = Extractor()
        char = ArtifactCharacterization(
            id="c1", artifact_id="a1", characterization_version="1.0.0", characterization_config={},
            detected_format="json", format_confidence="high", format_evidence={}, mime_type="application/json",
            file_extension="json", encoding="utf-8", structural_type="object", document_type_candidates=[],
            schema_summary=None, content_statistics={}, metadata_availability={}, extraction_suitability="suitable",
            warnings=[], errors=[], is_deterministic=True, characterized_at="2026-01-01", created_at="2026-01-01",
        )
        result = extractor.extract(b'{"name": "test"}', char)
        assert result.extraction_status == "completed"
        assert result.metadata.get("structured_data_checksum") is not None
        assert result.metadata.get("structured_data_size_bytes") is not None

    def test_html_boilerplate_warning(self):
        extractor = Extractor()
        char = ArtifactCharacterization(
            id="c1", artifact_id="a1", characterization_version="1.0.0", characterization_config={},
            detected_format="html", format_confidence="high", format_evidence={}, mime_type="text/html",
            file_extension="html", encoding="utf-8", structural_type="document", document_type_candidates=[],
            schema_summary=None, content_statistics={}, metadata_availability={}, extraction_suitability="suitable",
            warnings=[], errors=[], is_deterministic=True, characterized_at="2026-01-01", created_at="2026-01-01",
        )
        # HTML with lots of boilerplate (script, style) relative to content
        html = b"<html><head><script>var x=1;</script><style>body{}</style></head><body><p>Hello</p></body></html>"
        result = extractor.extract(html, char)
        assert result.extraction_status == "completed"
        assert any("boilerplate" in w.lower() for w in result.warnings)

    def test_extraction_versioning_schema(self):
        from uuid import uuid4
        from data_fetcher.database import Database
        from psycopg.rows import class_row
        
        db = Database("postgresql://datafetcher:DataFetcher-Postgres-2026!@localhost:5432/data_catalog")
        
        resource = db.ensure_resource(
            url="http://example.com/test-versioning",
            normalized_url="http://example.com/test-versioning",
            domain="example.com",
            resource_type="text/html",
            metadata={"test": "versioning"},
        )
        fetch = db.create_fetch(
            resource_id=resource.id,
            crawl_job_id=None,
            status="success",
            http_status=200,
            content_type="text/html",
            content_length=100,
            headers={"Content-Type": "text/html"},
            error_message=None,
            started_at=None,
            completed_at=None,
        )
        artifact = db.create_artifact(
            fetch_id=fetch.id,
            storage_backend="minio",
            bucket_name="raw",
            object_key=f"tests/test-artifact-{uuid4()}.bin",
            content_type="text/html",
            size_bytes=100,
            checksum_sha256="abc123",
            metadata={"test": "versioning"},
        )
        test_artifact_id = str(artifact.id)
        
        doc1 = CanonicalDocument(
            id="", artifact_id=test_artifact_id, processing_job_id=None,
            source_url="http://example.com", source_mime_type="text/html", detected_format="html",
            extraction_status="completed", canonical_text="v1", structured_data=None,
            metadata={}, structure=None, extraction_method="extractor-1.0.0",
            extraction_version="1.0.0", warnings=[], errors=[],
            original_checksum="abc", canonical_checksum="def",
            provenance={}, created_at="", updated_at="",
        )
        saved1 = db.save_canonical_document(doc1)
        
        doc2 = CanonicalDocument(
            id="", artifact_id=test_artifact_id, processing_job_id=None,
            source_url="http://example.com", source_mime_type="text/html", detected_format="html",
            extraction_status="completed", canonical_text="v2", structured_data=None,
            metadata={}, structure=None, extraction_method="extractor-1.1.0",
            extraction_version="1.1.0", warnings=[], errors=[],
            original_checksum="abc", canonical_checksum="ghi",
            provenance={}, created_at="", updated_at="",
        )
        saved2 = db.save_canonical_document(doc2)
        
        # Both versions should exist
        assert saved1.id != saved2.id
        with db.connect() as conn:
            with conn.cursor(row_factory=class_row(dict)) as cur:
                cur.execute(
                    "SELECT * FROM canonical_documents WHERE artifact_id = %s ORDER BY extraction_version",
                    (test_artifact_id,),
                )
                docs = cur.fetchall()
        assert len(docs) == 2
        versions = [d['extraction_version'] for d in docs]
        assert '1.0.0' in versions
        assert '1.1.0' in versions
