"""Phase 2: Deterministic normalization of canonical documents."""

from __future__ import annotations

import hashlib
import unicodedata
import logging
from dataclasses import dataclass, field
from typing import Any

from data_fetcher.models import CanonicalDocument

logger = logging.getLogger(__name__)


class NormalizationError(Exception):
    """Normalization-specific errors."""
    def __init__(self, category: str, message: str):
        self.category = category
        super().__init__(message)


@dataclass
class NormalizationConfig:
    """Configuration for normalization."""
    normalization_version: str = "1.0.0"
    enable_unicode_normalization: bool = True
    enable_line_ending_normalization: bool = True
    enable_whitespace_normalization: bool = True
    enable_control_character_removal: bool = True
    max_normalized_text_bytes: int = 10485760  # 10MB


@dataclass
class NormalizationResult:
    """Result of normalizing a canonical document."""
    canonical_document_id: str
    artifact_id: str
    normalization_version: str
    normalized_text: str | None
    normalization_operations: list[dict[str, Any]]
    original_checksum: str
    normalized_checksum: str | None
    content_changed: bool
    warnings: list[str]
    errors: list[str]
    provenance: dict[str, Any]
    created_at: str
    updated_at: str


class Normalizer:
    """Deterministic, versioned, non-destructive normalizer."""

    def __init__(self, config: NormalizationConfig | None = None) -> None:
        self.config = config or NormalizationConfig()

    def normalize(self, canonical_document: CanonicalDocument) -> NormalizationResult:
        """
        Normalize a canonical document deterministically.
        
        Args:
            canonical_document: P2.3 canonical document
            
        Returns:
            NormalizationResult with normalized text and metadata
        """
        operations: list[dict[str, Any]] = []
        warnings: list[str] = []
        errors: list[str] = []
        
        text = canonical_document.canonical_text or ""
        original_text = text
        original_checksum = canonical_document.original_checksum
        
        provenance = {
            "canonical_document_id": str(canonical_document.id),
            "artifact_id": str(canonical_document.artifact_id),
            "source_url": canonical_document.source_url,
            "detected_format": canonical_document.detected_format,
            "extraction_version": canonical_document.extraction_version,
            "canonical_checksum": canonical_document.canonical_checksum,
            "processing_job_id": str(canonical_document.processing_job_id) if canonical_document.processing_job_id else None,
        }
        
        # Operation 1: Unicode normalization (NFC)
        if self.config.enable_unicode_normalization and text:
            original = text
            text = unicodedata.normalize("NFC", text)
            if text != original:
                operations.append({
                    "operation": "unicode_normalization",
                    "version": self.config.normalization_version,
                    "description": "Applied Unicode NFC normalization",
                })
        
        # Operation 2: Line ending normalization
        if self.config.enable_line_ending_normalization and text:
            original = text
            text = text.replace("\r\n", "\n").replace("\r", "\n")
            if text != original:
                operations.append({
                    "operation": "line_ending_normalization",
                    "version": self.config.normalization_version,
                    "description": "Normalized line endings to LF",
                })
        
        # Operation 3: Whitespace normalization
        if self.config.enable_whitespace_normalization and text:
            original = text
            lines = text.split('\n')
            normalized_lines = [line.rstrip() for line in lines]
            text = "\n".join(normalized_lines)
            if text != original:
                operations.append({
                    "operation": "whitespace_normalization",
                    "version": self.config.normalization_version,
                    "description": "Stripped trailing whitespace from each line",
                })
        
        # Operation 4: Control character removal
        if self.config.enable_control_character_removal and text:
            original = text
            # Remove control characters except newline (0x0A), tab (0x09), carriage return (0x0D)
            allowed_controls = {"\n", "\t", "\r"}
            cleaned = "".join(c for c in text if c in allowed_controls or not unicodedata.category(c).startswith("C"))
            if cleaned != original:
                text = cleaned
                operations.append({
                    "operation": "control_character_removal",
                    "version": self.config.normalization_version,
                    "description": "Removed disallowed control characters",
                })
        
        # Ensure text ends with newline if non-empty
        if text and not text.endswith("\n"):
            text += "\n"
            operations.append({
                "operation": "trailing_newline",
            })
        
        content_changed = len(operations) > 0
        
        # Compute checksum
        normalized_checksum = hashlib.sha256(text.encode("utf-8")).hexdigest()
        
        # Warn if text exceeds limit
        if len(text.encode("utf-8")) > self.config.max_normalized_text_bytes:
            warnings.append(f"Normalized text exceeds {self.config.max_normalized_text_bytes} bytes")
            text = text[: self.config.max_normalized_text_bytes]
            content_changed = True
        
        return NormalizationResult(
            canonical_document_id=canonical_document.id,
            artifact_id=canonical_document.artifact_id,
            normalization_version=self.config.normalization_version,
            normalized_text=text,
            normalization_operations=operations,
            original_checksum=original_checksum,
            normalized_checksum=normalized_checksum,
            content_changed=content_changed,
            warnings=warnings,
            errors=errors,
            provenance=provenance,
            created_at="",
            updated_at="",
        )
