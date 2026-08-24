"""Phase 2: Format discovery and artifact characterization."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from email.parser import HeaderParser
from typing import Any

from data_fetcher.models import ArtifactCharacterization

logger = logging.getLogger(__name__)


class DiscoveryError(Exception):
    """Discovery-specific errors."""
    def __init__(self, category: str, message: str):
        self.category = category
        super().__init__(message)


@dataclass
class DiscoveryConfig:
    """Configuration for format discovery."""
    max_preview_bytes: int = 65536
    enable_encoding_detection: bool = True
    enable_schema_inference: bool = True
    characterization_version: str = "1.0.0"


class FormatDiscovery:
    """Discover format, structure, and characteristics of artifacts."""

    def __init__(self, config: DiscoveryConfig | None = None) -> None:
        self.config = config or DiscoveryConfig()

    def _preview(self, raw_data: bytes) -> bytes:
        """Get preview bytes for inspection."""
        return raw_data[: self.config.max_preview_bytes]

    def _detect_from_content_type(self, content_type: str | None) -> tuple[str | None, str]:
        """Detect format from HTTP Content-Type."""
        if not content_type:
            return None, "missing"
        main_type = content_type.split(";")[0].strip().lower()
        mapping = {
            "text/html": "html",
            "application/xhtml+xml": "html",
            "text/plain": "plain_text",
            "text/markdown": "markdown",
            "text/x-markdown": "markdown",
            "application/json": "json",
            "application/ld+json": "json",
            "application/xml": "xml",
            "text/xml": "xml",
            "application/csv": "csv",
            "text/csv": "csv",
        }
        if main_type in mapping:
            return mapping[main_type], "mime"
        if main_type.startswith("text/"):
            return "plain_text", "mime-fallback"
        return None, "unknown-mime"

    def _detect_from_url(self, url: str | None) -> tuple[str | None, str]:
        """Detect format from URL extension."""
        if not url:
            return None, "missing"
        path = url.split("?")[0].split("#")[0]
        ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
        mapping = {
            "html": "html",
            "htm": "html",
            "json": "json",
            "xml": "xml",
            "csv": "csv",
            "md": "markdown",
            "markdown": "markdown",
            "txt": "plain_text",
        }
        if ext in mapping:
            return mapping[ext], "url-extension"
        return None, "no-extension"

    def _detect_from_magic_bytes(self, raw_data: bytes) -> tuple[str | None, str]:
        """Detect format from magic bytes / content signature."""
        preview = self._preview(raw_data)
        stripped = preview.lstrip()
        if stripped.startswith(b"<!DOCTYPE") or stripped.startswith(b"<html") or stripped.startswith(b"<HTML"):
            return "html", "magic-bytes"
        if stripped.startswith(b"<?xml") or stripped.startswith(b"<xml"):
            return "xml", "magic-bytes"
        if stripped.startswith(b"{") or stripped.startswith(b"["):
            try:
                json.loads(preview)
                return "json", "magic-bytes"
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass
        if b"," in preview and preview.count(b",") >= 2:
            lines = preview.split(b"\n")
            if len(lines) >= 2 and lines[0].count(b",") == lines[1].count(b","):
                return "csv", "magic-bytes"
        if preview.startswith(b"#") or re.match(rb"^#+\s", preview[:20]):
            return "markdown", "magic-bytes"
        return None, "no-magic-match"

    def _detect_from_content_inspection(self, raw_data: bytes) -> tuple[str | None, str]:
        """Detect format by attempting to parse content."""
        preview = self._preview(raw_data)

        # Reject obvious binary data early
        if preview and not all(32 <= b <= 126 or b in (9, 10, 13) for b in preview[:32]):
            return None, "non-text"

        try:
            preview_str = preview.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            return None, "non-text"

        # Try JSON
        try:
            json.loads(preview_str)
            return "json", "content-parse"
        except (json.JSONDecodeError, ValueError):
            pass

        # Try XML
        if preview_str.strip().startswith("<?xml") or preview_str.strip().startswith("<"):
            try:
                import xml.etree.ElementTree as ET
                ET.fromstring(preview_str)
                return "xml", "content-parse"
            except ET.ParseError:
                if "<html" in preview_str.lower() or "<body" in preview_str.lower():
                    return "html", "content-parse"

        # Try CSV
        if b"," in preview and preview.count(b",") >= 2:
            lines = preview.split(b"\n")
            if len(lines) >= 2:
                header_commas = lines[0].count(b",")
                if header_commas >= 1 and all(line.count(b",") == header_commas for line in lines[:min(5, len(lines))] if line.strip()):
                    return "csv", "content-parse"

        # Markdown heuristics
        if re.search(r"^#{1,6}\s", preview_str, re.MULTILINE) or re.search(r"^\s*[-*+]\s", preview_str, re.MULTILINE):
            return "markdown", "content-parse"

        # HTML heuristics
        if re.search(r"<[a-zA-Z][^>]*>", preview_str):
            return "html", "content-parse"

        return "plain_text", "content-fallback"

    def detect_format(self, raw_data: bytes, content_type: str | None, url: str | None) -> tuple[str | None, str, dict[str, Any]]:
        """
        Detect format using multiple evidence sources.
        
        Returns:
            (format, confidence, evidence)
            confidence: 'high', 'medium', 'low', 'unknown'
        """
        evidence: dict[str, Any] = {
            "sources": [],
            "mime_type": content_type,
            "url": url,
        }

        # Collect evidence from all sources
        mime_format, mime_evidence = self._detect_from_content_type(content_type)
        if mime_format:
            evidence["sources"].append({"source": "mime", "format": mime_format, "confidence": "high" if mime_evidence == "mime" else "medium"})

        url_format, url_evidence = self._detect_from_url(url)
        if url_format:
            evidence["sources"].append({"source": "url", "format": url_format, "confidence": "medium"})

        magic_format, magic_evidence = self._detect_from_magic_bytes(raw_data)
        if magic_format:
            evidence["sources"].append({"source": "magic-bytes", "format": magic_format, "confidence": "high"})

        content_format, content_evidence = self._detect_from_content_inspection(raw_data)
        if content_format:
            evidence["sources"].append({"source": "content", "format": content_format, "confidence": "medium"})

        # Resolve format from evidence
        formats = [s["format"] for s in evidence["sources"]]
        if not formats:
            return None, "unknown", evidence

        # Count format occurrences
        from collections import Counter
        counts = Counter(formats)
        best_format, best_count = counts.most_common(1)[0]

        # Determine confidence
        high_confidence_sources = [s for s in evidence["sources"] if s["confidence"] == "high"]
        if best_count >= 2 and high_confidence_sources:
            confidence = "high"
        elif best_count >= 2:
            confidence = "medium"
        elif high_confidence_sources:
            confidence = "medium"
        else:
            confidence = "low"

        evidence["resolved_format"] = best_format
        evidence["vote_count"] = best_count
        evidence["high_confidence_sources"] = len(high_confidence_sources)
        evidence["resolution_method"] = "majority-vote"

        return best_format, confidence, evidence

    def detect_encoding(self, raw_data: bytes) -> tuple[str | None, str]:
        """
        Detect text encoding.
        
        Returns:
            (encoding, confidence)
        """
        if not raw_data:
            return None, "unknown"

        # Try UTF-8 with BOM first
        if raw_data.startswith(b"\xef\xbb\xbf"):
            return "utf-8-sig", "high"

        # Try UTF-8
        try:
            raw_data.decode("utf-8")
            return "utf-8", "high"
        except UnicodeDecodeError:
            pass

        # Try Latin-1 (always succeeds)
        try:
            raw_data.decode("latin-1")
            return "latin-1", "low"
        except UnicodeDecodeError:
            pass

        return None, "unknown"

    def classify_structural_type(self, raw_data: bytes, detected_format: str | None) -> str | None:
        """Classify structural type of the artifact."""
        if not detected_format or not raw_data:
            return None

        preview = self._preview(raw_data)
        try:
            text = preview.decode("utf-8", errors="replace")
        except Exception:
            return None

        if detected_format == "html":
            if re.search(r"<article\b", text, re.IGNORECASE) or re.search(r"<main\b", text, re.IGNORECASE):
                return "article-like"
            if re.search(r"<nav\b", text, re.IGNORECASE) or re.search(r"<menu\b", text, re.IGNORECASE):
                return "navigation-heavy"
            if re.search(r"<table\b", text, re.IGNORECASE):
                return "structured-page"
            return "document"

        elif detected_format == "json":
            try:
                data = json.loads(text)
                if isinstance(data, dict):
                    return "object"
                elif isinstance(data, list):
                    if len(data) > 0 and isinstance(data[0], dict):
                        return "array-of-records"
                    return "array"
            except (json.JSONDecodeError, ValueError):
                pass
            return "unknown-structured"

        elif detected_format == "csv":
            lines = text.strip().split("\n")
            if len(lines) >= 2:
                return "tabular"
            return "unknown-structured"

        elif detected_format == "xml":
            if re.search(r"<record\b", text, re.IGNORECASE) or re.search(r"<item\b", text, re.IGNORECASE):
                return "repeated-records"
            return "hierarchy"

        elif detected_format == "markdown":
            if re.search(r"^#{1,6}\s", text, re.MULTILINE):
                return "headings-paragraphs"
            if re.search(r"^\s*[-*+]\s", text, re.MULTILINE):
                return "list-structured"
            if re.search(r"```", text):
                return "code-document"
            return "prose"

        elif detected_format == "plain_text":
            if "\n" in text and text.count("\n") > 1:
                return "multi-line"
            return "single-line"

        return None

    def infer_document_type(self, raw_data: bytes, detected_format: str | None, structural_type: str | None) -> list[str]:
        """Infer document type candidates."""
        candidates: list[str] = []
        if not detected_format:
            return candidates

        preview = self._preview(raw_data)
        try:
            text = preview.decode("utf-8", errors="replace")
        except Exception:
            return candidates

        if detected_format == "html":
            if re.search(r"<article\b", text, re.IGNORECASE):
                candidates.append("article")
            if re.search(r"<form\b", text, re.IGNORECASE):
                candidates.append("form")
            if re.search(r"<table\b", text, re.IGNORECASE):
                candidates.append("data-table")
            if re.search(r"<pre\b", text, re.IGNORECASE) or re.search(r"<code\b", text, re.IGNORECASE):
                candidates.append("code-documentation")
            if not candidates:
                candidates.append("webpage")

        elif detected_format == "json":
            if re.search(r"\"api\"|\"endpoint\"|\"route\"", text, re.IGNORECASE):
                candidates.append("api-response")
            if re.search(r"\"error\"|\"message\"|\"stack\"", text, re.IGNORECASE):
                candidates.append("error-log")
            if re.search(r"\"config\"|\"settings\"", text, re.IGNORECASE):
                candidates.append("configuration")
            if not candidates:
                candidates.append("structured-data")

        elif detected_format == "csv":
            candidates.append("tabular-data")

        elif detected_format == "xml":
            if re.search(r"<rss\b|<feed\b", text, re.IGNORECASE):
                candidates.append("feed")
            if re.search(r"<sitemap\b", text, re.IGNORECASE):
                candidates.append("sitemap")
            candidates.append("structured-data")

        elif detected_format == "markdown":
            if re.search(r"^#{1,6}\s", text, re.MULTILINE):
                candidates.append("documentation")
            candidates.append("text")

        elif detected_format == "plain_text":
            candidates.append("text")

        return candidates

    def infer_schema(self, raw_data: bytes, detected_format: str | None) -> dict[str, Any] | None:
        """Infer schema summary for structured data."""
        if not detected_format or not raw_data:
            return None

        if detected_format not in ("json", "csv", "xml"):
            return None

        preview = self._preview(raw_data)
        try:
            text = preview.decode("utf-8", errors="replace")
        except Exception:
            return None

        if detected_format == "json":
            try:
                data = json.loads(text)
                if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
                    fields = {}
                    for key, value in data[0].items():
                        fields[key] = type(value).__name__
                    return {
                        "type": "array-of-records",
                        "record_count": len(data),
                        "fields": fields,
                    }
                elif isinstance(data, dict):
                    return {
                        "type": "object",
                        "top_level_keys": list(data.keys()),
                    }
            except (json.JSONDecodeError, ValueError):
                pass

        elif detected_format == "csv":
            lines = text.strip().split("\n")
            if len(lines) >= 1:
                header = lines[0].split(",")
                return {
                    "type": "tabular",
                    "column_count": len(header),
                    "columns": header,
                    "row_count": len(lines) - 1,
                    "sample_rows": min(3, len(lines) - 1),
                }

        elif detected_format == "xml":
            try:
                import xml.etree.ElementTree as ET
                root = ET.fromstring(text)
                children = list(root)
                return {
                    "type": "hierarchy",
                    "root_tag": root.tag,
                    "child_count": len(children),
                    "child_tags": list({child.tag for child in children}),
                }
            except ET.ParseError:
                pass

        return None

    def assess_metadata_availability(self, content_type: str | None, url: str | None, raw_data: bytes) -> dict[str, Any]:
        """Assess what metadata is available for the artifact."""
        availability: dict[str, Any] = {
            "content_type_present": content_type is not None,
            "url_present": url is not None,
            "size_bytes": len(raw_data),
            "has_http_headers": False,  # Not available at discovery time
            "encoding_declarations": False,
            "title_indicators": False,
        }

        preview = self._preview(raw_data)
        try:
            text = preview.decode("utf-8", errors="replace")
        except Exception:
            return availability

        if detected_format := self._detect_from_content_inspection(raw_data)[0]:
            if detected_format in ("html", "xml"):
                if re.search(r"<title\b", text, re.IGNORECASE):
                    availability["title_indicators"] = True
                if re.search(r'charset\s*=\s*["\']?([^"\';>\s]+)', text, re.IGNORECASE):
                    availability["encoding_declarations"] = True
                availability["has_http_headers"] = content_type is not None

        return availability

    def compute_content_statistics(self, raw_data: bytes, detected_format: str | None, encoding: str | None) -> dict[str, Any]:
        """Compute deterministic content statistics."""
        stats: dict[str, Any] = {
            "byte_count": len(raw_data),
            "preview_byte_count": min(len(raw_data), self.config.max_preview_bytes),
            "bytes_analyzed": min(len(raw_data), self.config.max_preview_bytes),
            "analysis_scope": "preview" if len(raw_data) > self.config.max_preview_bytes else "full",
        }

        if not detected_format or not raw_data:
            stats["character_count"] = 0
            stats["line_count"] = 0
            stats["word_count_estimate"] = 0
            stats["bytes_analyzed"] = 0
            stats["analysis_scope"] = "none"
            return stats

        preview = self._preview(raw_data)
        try:
            text = preview.decode(encoding or "utf-8", errors="replace")
        except Exception:
            text = preview.decode("latin-1", errors="replace")

        stats["character_count"] = len(text)
        stats["line_count"] = text.count("\n") + (1 if text and not text.endswith("\n") else 0)
        stats["word_count_estimate"] = len(text.split())
        stats["non_ascii_ratio"] = sum(1 for c in text if ord(c) > 127) / max(len(text), 1)

        if detected_format == "csv":
            lines = text.strip().split("\n")
            stats["row_count"] = max(0, len(lines) - 1)
            if lines:
                stats["column_count"] = lines[0].count(",") + 1

        elif detected_format == "json":
            try:
                data = json.loads(text)
                if isinstance(data, list):
                    stats["record_count"] = len(data)
                elif isinstance(data, dict):
                    stats["field_count"] = len(data)
            except (json.JSONDecodeError, ValueError):
                pass

        elif detected_format == "xml":
            try:
                import xml.etree.ElementTree as ET
                root = ET.fromstring(text)
                stats["element_count"] = sum(1 for _ in root.iter())
            except ET.ParseError:
                pass

        return stats

    def assess_extraction_suitability(self, detected_format: str | None, structural_type: str | None) -> str:
        """Assess whether artifact is suitable for extraction."""
        if not detected_format:
            return "unknown"
        if detected_format in ("html", "json", "xml", "csv", "markdown", "plain_text"):
            return "suitable"
        return "unsuitable"

    def characterize(
        self,
        raw_data: bytes,
        content_type: str | None,
        url: str | None,
        artifact_id: str,
        config: dict[str, Any] | None = None,
    ) -> ArtifactCharacterization:
        """
        Perform full characterization of an artifact.
        
        Args:
            raw_data: Raw artifact bytes
            content_type: HTTP Content-Type header
            url: Source URL
            artifact_id: Phase 1 artifact UUID
            config: Characterization configuration overrides
            
        Returns:
            ArtifactCharacterization with all discovered properties
        """
        if config:
            self.config = DiscoveryConfig(**config)

        warnings: list[str] = []
        errors: list[str] = []

        # Format detection
        detected_format, format_confidence, format_evidence = self.detect_format(raw_data, content_type, url)
        if not detected_format:
            warnings.append("Unable to determine format")
            errors.append({"category": "unknown_format", "message": "Format detection failed"})

        # Encoding detection
        encoding, encoding_confidence = self.detect_encoding(raw_data)
        if not encoding:
            warnings.append("Unable to determine encoding")

        # Structural type
        structural_type = self.classify_structural_type(raw_data, detected_format)

        # Document type
        document_type_candidates = self.infer_document_type(raw_data, detected_format, structural_type)

        # Schema inference
        schema_summary = self.infer_schema(raw_data, detected_format)

        # Metadata availability
        metadata_availability = self.assess_metadata_availability(content_type, url, raw_data)

        # Content statistics
        content_statistics = self.compute_content_statistics(raw_data, detected_format, encoding)

        # File extension from URL
        file_extension = None
        if url:
            path = url.split("?")[0].split("#")[0]
            if "." in path:
                ext = path.rsplit(".", 1)[-1].lower()
                if ext and len(ext) <= 10:
                    file_extension = ext

        # Extraction suitability
        extraction_suitability = self.assess_extraction_suitability(detected_format, structural_type)

        # Build evidence dict for JSON serialization
        serializable_evidence = {}
        for key, value in format_evidence.items():
            if isinstance(value, list):
                serializable_evidence[key] = value
            elif isinstance(value, dict):
                serializable_evidence[key] = value
            else:
                serializable_evidence[key] = str(value) if value is not None else None

        return ArtifactCharacterization(
            id="",  # Assigned by database
            artifact_id=artifact_id,
            characterization_version=self.config.characterization_version,
            characterization_config={
                "max_preview_bytes": self.config.max_preview_bytes,
                "enable_encoding_detection": self.config.enable_encoding_detection,
                "enable_schema_inference": self.config.enable_schema_inference,
            },
            detected_format=detected_format,
            format_confidence=format_confidence,
            format_evidence=serializable_evidence,
            mime_type=content_type,
            file_extension=file_extension,
            encoding=encoding,
            structural_type=structural_type,
            document_type_candidates=document_type_candidates,
            schema_summary=schema_summary,
            content_statistics=content_statistics,
            metadata_availability=metadata_availability,
            extraction_suitability=extraction_suitability,
            warnings=warnings,
            errors=errors,
            is_deterministic=True,
            characterized_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
            created_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        )
