"""Phase 2: Canonical representation and extraction."""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from io import StringIO
from typing import Any
from xml.etree import ElementTree as ET

from data_fetcher.database import Database
from data_fetcher.models import ArtifactCharacterization, CanonicalDocument, ProcessingJobRecord

logger = logging.getLogger(__name__)


class ExtractionError(Exception):
    """Extraction-specific errors."""
    def __init__(self, category: str, message: str):
        self.category = category
        super().__init__(message)


@dataclass
class ExtractionConfig:
    """Configuration for extraction."""
    extraction_version: str = "1.0.0"
    max_canonical_text_bytes: int = 10485760  # 10MB
    enable_structured_preservation: bool = True
    enable_html_extraction: bool = True
    html_extract_links: bool = True
    html_extract_headings: bool = True


@dataclass
class ExtractionResult:
    """Internal extraction result before persistence."""
    artifact_id: str = ""
    processing_job_id: str | None = None
    source_url: str = ""
    source_mime_type: str | None = None
    detected_format: str | None = None
    extraction_status: str = "pending"
    canonical_text: str | None = None
    structured_data: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    structure: dict[str, Any] | None = None
    extraction_method: str = ""
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    original_checksum: str = ""
    canonical_checksum: str | None = None


class _HTMLTextExtractor(HTMLParser):
    """Extract readable text and structure from HTML."""
    
    def __init__(self) -> None:
        super().__init__()
        self.text_parts: list[str] = []
        self.links: list[dict[str, str]] = []
        self.headings: list[dict[str, str]] = []
        self.skip_tags = {"script", "style", "noscript", "nav", "footer", "header"}
        self.current_tag: str | None = None
        self.skip_depth = 0
        self.title: str | None = None
        self._title_found = False
        self._in_title = False
    
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.current_tag = tag
        if tag == "title":
            self._in_title = True
            self.title = ""
        elif tag in self.skip_tags:
            self.skip_depth += 1
        elif tag == "a" and attrs:
            href = dict(attrs).get("href", "")
            if href and not href.startswith(("#", "javascript:")):
                self.links.append({"href": href})
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6") and not self._title_found:
            pass
    
    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        if tag in self.skip_tags and self.skip_depth > 0:
            self.skip_depth -= 1
        self.current_tag = None
    
    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title = (self.title or "") + data
        if self.skip_depth > 0:
            return
        text = data.strip()
        if text:
            self.text_parts.append(text)
            if self.current_tag in ("h1", "h2", "h3", "h4", "h5", "h6") and not self._title_found:
                self.headings.append({"level": self.current_tag, "text": text})
                if not self.title:
                    self.title = text
                self._title_found = True
    
    def get_result(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "text": "\n".join(self.text_parts),
            "links": self.links[:50],  # limit links
            "headings": self.headings[:20],  # limit headings
            "link_count": len(self.links),
            "heading_count": len(self.headings),
        }


def _extract_html(raw_data: bytes, encoding: str | None) -> ExtractionResult:
    """Extract canonical representation from HTML."""
    try:
        text = raw_data.decode(encoding or "utf-8", errors="replace")
    except Exception as exc:
        raise ExtractionError("encoding_error", f"Failed to decode HTML: {exc}") from exc
    
    extractor = _HTMLTextExtractor()
    try:
        extractor.feed(text)
    except Exception as exc:
        raise ExtractionError("parser_error", f"HTML parsing failed: {exc}") from exc
    
    result = extractor.get_result()
    canonical_text = result["text"]
    warnings: list[str] = []
    
    if not canonical_text.strip():
        warnings.append("HTML document contained no readable text content")
        return ExtractionResult(
            extraction_status="partial",
            canonical_text="",
            structured_data=None,
            structure=result,
            warnings=warnings,
            errors=[],
        )
    
    # Warn if significant boilerplate was removed
    original_length = len(text)
    extracted_length = len(canonical_text)
    if original_length > 0 and extracted_length < original_length * 0.5:
        warnings.append(
            f"HTML boilerplate removal: extracted {extracted_length} chars from {original_length} "
            f"({extracted_length/original_length:.1%} retained)"
        )
    
    canonical_checksum = hashlib.sha256(canonical_text.encode("utf-8")).hexdigest()
    
    return ExtractionResult(
        extraction_status="completed",
        canonical_text=canonical_text,
        structured_data={"links": result["links"][:10], "headings": result["headings"][:10]},
        structure=result,
        warnings=warnings,
        canonical_checksum=canonical_checksum,
    )


def _extract_json(raw_data: bytes, encoding: str | None) -> ExtractionResult:
    """Extract canonical representation from JSON."""
    try:
        text = raw_data.decode(encoding or "utf-8", errors="strict")
    except Exception as exc:
        raise ExtractionError("encoding_error", f"Failed to decode JSON: {exc}") from exc
    
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ExtractionError("corrupted_format", f"Invalid JSON: {exc}") from exc
    
    # Preserve structured data
    structured_data = data
    
    # Deterministic canonical text
    canonical_text = json.dumps(data, sort_keys=True, ensure_ascii=False, indent=2)
    canonical_checksum = hashlib.sha256(canonical_text.encode("utf-8")).hexdigest()
    
    # Build structure summary
    structure: dict[str, Any] = {"type": type(data).__name__}
    if isinstance(data, dict):
        structure["top_level_keys"] = list(data.keys())[:20]
        structure["field_count"] = len(data)
    elif isinstance(data, list):
        structure["item_count"] = len(data)
        if data and isinstance(data[0], dict):
            structure["first_item_keys"] = list(data[0].keys())[:20]
            structure["record_type"] = "array-of-records"
        else:
            structure["record_type"] = "array"
    
    return ExtractionResult(
        extraction_status="completed",
        canonical_text=canonical_text,
        structured_data=structured_data,
        structure=structure,
        warnings=[],
        canonical_checksum=canonical_checksum,
    )


def _extract_xml(raw_data: bytes, encoding: str | None) -> ExtractionResult:
    """Extract canonical representation from XML."""
    try:
        text = raw_data.decode(encoding or "utf-8", errors="replace")
    except Exception as exc:
        raise ExtractionError("encoding_error", f"Failed to decode XML: {exc}") from exc
    
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ExtractionError("corrupted_format", f"Invalid XML: {exc}") from exc
    
    # Extract all text content
    text_parts: list[str] = []
    for elem in root.iter():
        if elem.text and elem.text.strip():
            text_parts.append(elem.text.strip())
    
    canonical_text = "\n".join(text_parts)
    canonical_checksum = hashlib.sha256(canonical_text.encode("utf-8")).hexdigest()
    
    # Preserve structure
    structure: dict[str, Any] = {
        "root_tag": root.tag,
        "child_count": len(list(root)),
        "child_tags": list({child.tag for child in root}),
        "attributes": dict(root.attrib) if root.attrib else {},
    }
    
    # Preserve full tree as structured data (limited depth)
    def _element_to_dict(elem: ET.Element, max_depth: int = 5, _depth: int = 0) -> dict[str, Any]:
        if _depth >= max_depth:
            return {"tag": elem.tag, "text": (elem.text or "").strip()[:200]}
        node: dict[str, Any] = {"tag": elem.tag}
        if elem.text and elem.text.strip():
            node["text"] = elem.text.strip()[:500]
        if elem.attrib:
            node["attributes"] = dict(elem.attrib)
        children = list(elem)
        if children:
            node["children"] = [_element_to_dict(c, max_depth, _depth + 1) for c in children[:50]]
        return node
    
    structured_data = _element_to_dict(root)
    
    return ExtractionResult(
        extraction_status="completed",
        canonical_text=canonical_text,
        structured_data=structured_data,
        structure=structure,
        warnings=[],
        canonical_checksum=canonical_checksum,
    )


def _extract_csv(raw_data: bytes, encoding: str | None) -> ExtractionResult:
    """Extract canonical representation from CSV."""
    try:
        text = raw_data.decode(encoding or "utf-8", errors="replace")
    except Exception as exc:
        raise ExtractionError("encoding_error", f"Failed to decode CSV: {exc}") from exc
    
    if not text.strip():
        raise ExtractionError("empty_content", "CSV content is empty")
    
    try:
        reader = csv.reader(StringIO(text))
        rows = list(reader)
    except Exception as exc:
        raise ExtractionError("parser_error", f"CSV parsing failed: {exc}") from exc
    
    if not rows:
        raise ExtractionError("empty_content", "CSV contains no rows")
    
    headers = rows[0]
    data_rows = rows[1:]
    
    # Build structured data
    structured_data = {
        "headers": headers,
        "rows": data_rows[:1000],  # limit rows for memory
        "row_count": len(data_rows),
        "column_count": len(headers),
    }
    
    # Canonical text: headers + rows as TSV-like text
    canonical_lines = ["\t".join(headers)]
    for row in data_rows[:1000]:
        canonical_lines.append("\t".join(row))
    canonical_text = "\n".join(canonical_lines)
    canonical_checksum = hashlib.sha256(canonical_text.encode("utf-8")).hexdigest()
    
    structure: dict[str, Any] = {
        "type": "tabular",
        "headers": headers,
        "row_count": len(data_rows),
        "column_count": len(headers),
        "sample_rows": min(3, len(data_rows)),
    }
    
    return ExtractionResult(
        extraction_status="completed",
        canonical_text=canonical_text,
        structured_data=structured_data,
        structure=structure,
        warnings=[] if len(data_rows) <= 1000 else [f"Truncated to first 1000 rows (total: {len(data_rows)})"],
        canonical_checksum=canonical_checksum,
    )


def _extract_markdown(raw_data: bytes, encoding: str | None) -> ExtractionResult:
    """Extract canonical representation from Markdown."""
    try:
        text = raw_data.decode(encoding or "utf-8", errors="replace")
    except Exception as exc:
        raise ExtractionError("encoding_error", f"Failed to decode Markdown: {exc}") from exc
    
    lines = text.splitlines()
    
    # Extract structure
    headings: list[dict[str, str]] = []
    code_blocks: list[tuple[str, str]] = []
    links: list[dict[str, str]] = []
    
    in_code_block = False
    code_lang = ""
    code_lines: list[str] = []
    
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            if in_code_block:
                code_blocks.append((code_lang, "\n".join(code_lines)))
                code_lines = []
                in_code_block = False
            else:
                in_code_block = True
                code_lang = stripped[3:].strip()
        elif in_code_block:
            code_lines.append(line)
        elif re.match(r"^#{1,6}\s", stripped):
            level = len(stripped) - len(stripped.lstrip("#"))
            headings.append({"level": level, "text": stripped.lstrip("#").strip()})
        elif re.match(r"^\s*[-*+]\s", stripped):
            pass  # list item, included in text
    
    # Canonical text: normalize whitespace but preserve structure
    canonical_text = text
    canonical_checksum = hashlib.sha256(canonical_text.encode("utf-8")).hexdigest()
    
    structure: dict[str, Any] = {
        "type": "markdown",
        "heading_count": len(headings),
        "code_block_count": len(code_blocks),
        "line_count": len(lines),
        "headings": headings[:20],
        "code_languages": list({lang for lang, _ in code_blocks if lang})[:10],
    }
    
    return ExtractionResult(
        extraction_status="completed",
        canonical_text=canonical_text,
        structured_data={
            "headings": headings[:20],
            "code_blocks": [(lang, content) for lang, content in code_blocks[:10]],
        },
        structure=structure,
        warnings=[],
        canonical_checksum=canonical_checksum,
    )


def _extract_plain_text(raw_data: bytes, encoding: str | None) -> ExtractionResult:
    """Extract canonical representation from plain text."""
    try:
        text = raw_data.decode(encoding or "utf-8", errors="strict")
    except Exception:
        try:
            text = raw_data.decode("utf-8", errors="replace")
        except Exception:
            text = raw_data.decode("latin-1", errors="replace")
    
    # Normalize line endings and strip trailing whitespace
    canonical_text = text.replace("\r\n", "\n").replace("\r", "\n")
    canonical_text = "\n".join(line.rstrip() for line in canonical_text.splitlines())
    if not canonical_text.endswith("\n") and canonical_text:
        canonical_text += "\n"
    
    canonical_checksum = hashlib.sha256(canonical_text.encode("utf-8")).hexdigest()
    
    lines = canonical_text.splitlines()
    structure: dict[str, Any] = {
        "type": "plain_text",
        "line_count": len(lines),
        "character_count": len(canonical_text),
        "non_empty_line_count": sum(1 for line in lines if line.strip()),
    }
    
    return ExtractionResult(
        extraction_status="completed",
        canonical_text=canonical_text,
        structured_data=None,
        structure=structure,
        warnings=[],
        canonical_checksum=canonical_checksum,
    )


class Extractor:
    """Format-aware canonical extractor."""
    
    def __init__(self, config: ExtractionConfig | None = None) -> None:
        self.config = config or ExtractionConfig()
        self._extractors = {
            "html": self._extract_html_wrapper,
            "json": _extract_json,
            "xml": _extract_xml,
            "csv": _extract_csv,
            "markdown": _extract_markdown,
            "plain_text": _extract_plain_text,
            "text": _extract_plain_text,
        }
    
    def _extract_html_wrapper(self, raw_data: bytes, encoding: str | None) -> ExtractionResult:
        if not self.config.enable_html_extraction:
            return ExtractionResult(
                extraction_status="failed",
                canonical_text=None,
                structured_data=None,
                structure=None,
                extraction_method="disabled",
                warnings=[],
                errors=[{"category": "unsupported_format", "message": "HTML extraction disabled in config"}],
                canonical_checksum=None,
            )
        return _extract_html(raw_data, encoding)
    
    def extract(
        self,
        raw_data: bytes,
        characterization: ArtifactCharacterization,
        processing_job_id: str | None = None,
    ) -> ExtractionResult:
        """
        Extract canonical representation from raw artifact data.
        
        Args:
            raw_data: Raw artifact bytes
            characterization: P2.2 artifact characterization
            processing_job_id: Optional processing job ID for provenance
            
        Returns:
            ExtractionResult with canonical representation
        """
        detected_format = characterization.detected_format
        extraction_method = f"extractor-{self.config.extraction_version}"
        
        if not detected_format:
            return ExtractionResult(
                extraction_status="failed",
                canonical_text=None,
                structured_data=None,
                structure=None,
                extraction_method=extraction_method,
                warnings=[],
                errors=[{"category": "unknown_format", "message": "No detected format from characterization"}],
                canonical_checksum=None,
            )
        
        if characterization.extraction_suitability == "unsuitable":
            return ExtractionResult(
                extraction_status="unsupported",
                canonical_text=None,
                structured_data=None,
                structure=None,
                extraction_method=extraction_method,
                warnings=[],
                errors=[{"category": "unsupported_format", "message": "Characterization marked format as unsuitable"}],
                canonical_checksum=None,
            )
        
        extractor = self._extractors.get(detected_format)
        if not extractor:
            return ExtractionResult(
                extraction_status="unsupported",
                canonical_text=None,
                structured_data=None,
                structure=None,
                extraction_method=extraction_method,
                warnings=[],
                errors=[{"category": "unsupported_format", "message": f"No extractor for format: {detected_format}"}],
                canonical_checksum=None,
            )
        
        try:
            result = extractor(raw_data, characterization.encoding)
        except ExtractionError as exc:
            return ExtractionResult(
                extraction_status="failed",
                canonical_text=None,
                structured_data=None,
                structure=None,
                extraction_method=extraction_method,
                warnings=[],
                errors=[{"category": exc.category, "message": exc}],
                canonical_checksum=None,
            )
        except Exception as exc:
            return ExtractionResult(
                extraction_status="failed",
                canonical_text=None,
                structured_data=None,
                structure=None,
                extraction_method=extraction_method,
                warnings=[],
                errors=[{"category": "extraction_error", "message": str(exc)}],
                canonical_checksum=None,
            )
        
        result.extraction_method = extraction_method
        result.artifact_id = characterization.artifact_id
        result.processing_job_id = processing_job_id
        result.source_url = characterization.format_evidence.get("url") or ""
        result.source_mime_type = characterization.mime_type
        result.detected_format = detected_format
        result.original_checksum = characterization.format_evidence.get("original_checksum", "")
        result.metadata = {
            "characterization_version": characterization.characterization_version,
            "format_confidence": characterization.format_confidence,
            "structural_type": characterization.structural_type,
            "document_type_candidates": characterization.document_type_candidates,
            "encoding": characterization.encoding,
        }
        
        if result.extraction_status == "completed" and result.canonical_text:
            if len(result.canonical_text.encode("utf-8")) > self.config.max_canonical_text_bytes:
                result.warnings.append(f"Canonical text exceeds {self.config.max_canonical_text_bytes} bytes")
                result.canonical_text = result.canonical_text[: self.config.max_canonical_text_bytes]
            
            # Compute checksum for structured data if present
            if result.structured_data is not None:
                import json as _json
                structured_bytes = _json.dumps(result.structured_data, sort_keys=True, default=str, ensure_ascii=False).encode("utf-8")
                result.metadata["structured_data_checksum"] = hashlib.sha256(structured_bytes).hexdigest()
                result.metadata["structured_data_size_bytes"] = len(structured_bytes)
        
        return result


def create_processing_job_for_extraction(
    database: Database,
    artifact_id: str | None = None,
    config: dict[str, Any] | None = None,
) -> ProcessingJobRecord:
    """Create a processing job for extraction."""
    import json
    
    config = config or {}
    
    name = f"extract-{artifact_id}" if artifact_id else "deduplication"
    
    with database.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO processing_jobs "
                "(name, status, config, source_artifact_id, started_at) "
                "VALUES (%s, %s, %s, %s, NOW()) "
                "RETURNING id, name, status, config, source_artifact_id, "
                "started_at, finished_at, error_message, error_category, created_at, updated_at",
                (
                    name,
                    "running",
                    json.dumps(config),
                    artifact_id,
                ),
            )
            row = cur.fetchone()
            conn.commit()
            return ProcessingJobRecord(
                id=row[0],
                name=row[1],
                status=row[2],
                config=row[3],
                source_artifact_id=row[4],
                started_at=row[5].isoformat() if row[5] else None,
                finished_at=row[6].isoformat() if row[6] else None,
                error_message=row[7],
                error_category=row[8],
                created_at=row[9].isoformat() if row[9] else None,
                updated_at=row[10].isoformat() if row[10] else None,
            )
