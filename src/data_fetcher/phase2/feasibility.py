"""Phase 2: Dataset feasibility analysis."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from data_fetcher.database import Database, DatabaseError
from psycopg.rows import class_row
from data_fetcher.models import (
    DatasetSpecification,
    FeasibilityReport,
    FeasibilityStageResult,
    NormalizedDocument,
)
from data_fetcher.phase2.specification import SpecificationError

logger = logging.getLogger(__name__)


class FeasibilityError(Exception):
    """Feasibility-specific errors."""
    def __init__(self, category: str, message: str):
        self.category = category
        super().__init__(message)


class FeasibilityEngine:
    """Evaluates whether a dataset specification can be satisfied."""

    def __init__(self, db: Database, spec_manager: Any) -> None:
        self.db = db
        self.spec_manager = spec_manager

    def analyze(self, specification: DatasetSpecification) -> FeasibilityReport:
        """
        Run feasibility analysis for a dataset specification.

        Returns a FeasibilityReport with stage-by-stage counts.
        """
        spec = specification.canonical_specification
        spec_hash = specification.specification_hash
        stages: list[FeasibilityStageResult] = []
        blockers: list[str] = []
        warnings: list[str] = []
        rejection_counts: dict[str, int] = {}

        # Stage 1: Load all normalized documents
        candidates = self._get_all_normalized_documents()
        input_count = len(candidates)
        if input_count == 0:
            blockers.append("No normalized documents available in the database")

        # Stage 2: Format filter
        format_candidates, format_rejections = self._apply_format_filter(spec, candidates)
        stages.append(FeasibilityStageResult(
            stage="format",
            input_count=input_count,
            output_count=len(format_candidates),
            rejection_reasons=format_rejections,
            details={"allowed_formats": spec.get("source", {}).get("allowed_formats", [])},
        ))
        rejection_counts.update(format_rejections)
        candidates = format_candidates

        # Stage 3: Language filter
        lang_candidates, lang_rejections = self._apply_language_filter(spec, candidates)
        stages.append(FeasibilityStageResult(
            stage="language",
            input_count=stages[-1].output_count,
            output_count=len(lang_candidates),
            rejection_reasons=lang_rejections,
            details={"allowed_languages": spec.get("source", {}).get("allowed_languages", [])},
        ))
        rejection_counts.update(lang_rejections)
        candidates = lang_candidates

        # Stage 4: Length filter
        length_candidates, length_rejections = self._apply_length_filter(spec, candidates)
        stages.append(FeasibilityStageResult(
            stage="length",
            input_count=stages[-1].output_count,
            output_count=len(length_candidates),
            rejection_reasons=length_rejections,
            details={
                "minimum_characters": spec.get("content", {}).get("minimum_characters"),
                "maximum_characters": spec.get("content", {}).get("maximum_characters"),
            },
        ))
        rejection_counts.update(length_rejections)
        candidates = length_candidates

        # Stage 5: Quality filter
        quality_candidates, quality_rejections = self._apply_quality_filter(spec, candidates)
        stages.append(FeasibilityStageResult(
            stage="quality",
            input_count=stages[-1].output_count,
            output_count=len(quality_candidates),
            rejection_reasons=quality_rejections,
            details={"minimum_score": spec.get("quality", {}).get("minimum_score")},
        ))
        rejection_counts.update(quality_rejections)
        candidates = quality_candidates

        # Stage 6: Dedup impact estimation
        dedup_candidates, dedup_impact = self._apply_dedup_filter(spec, candidates)
        stages.append(FeasibilityStageResult(
            stage="dedup",
            input_count=stages[-1].output_count,
            output_count=len(dedup_candidates),
            rejection_reasons={},
            details=dedup_impact,
        ))
        candidates = dedup_candidates

        # Stage 7: Selection constraints
        selection = spec.get("selection", {})
        max_records = selection.get("maximum_records")
        min_records = selection.get("minimum_records")
        eligible_count = len(candidates)

        if min_records is not None and eligible_count < min_records:
            blockers.append(
                f"Insufficient records: {eligible_count} eligible, "
                f"minimum required is {min_records}"
            )

        if max_records is not None and eligible_count > max_records:
            warnings.append(
                f"Record count exceeds maximum: {eligible_count} eligible, "
                f"maximum is {max_records}"
            )

        # Compute distributions
        language_distribution = self._compute_language_distribution(candidates)
        quality_distribution = self._compute_quality_distribution(candidates)
        estimated_size = self._estimate_output_size(candidates)

        # Determine feasibility
        feasibility = "pass"
        if blockers:
            feasibility = "blocked" if any("No normalized documents" in b for b in blockers) else "fail"

        report = FeasibilityReport(
            id="",
            specification_id=specification.id,
            specification_hash=spec_hash,
            source_snapshot="current",
            records_considered=input_count,
            eligible_count=eligible_count,
            rejection_counts=rejection_counts,
            language_distribution=language_distribution,
            quality_distribution=quality_distribution,
            dedup_impact=dedup_impact,
            blockers=blockers,
            warnings=warnings,
            feasibility=feasibility,
            estimated_output_size_bytes=estimated_size,
            created_at="",
        )
        self._last_stages = stages
        return report

    def _get_all_normalized_documents(self) -> list[dict[str, Any]]:
        """Retrieve all normalized documents with provenance."""
        with self.db.connect() as conn:
            with conn.cursor(row_factory=class_row(dict)) as cur:
                cur.execute(
                    "SELECT nd.id, nd.canonical_document_id, nd.artifact_id, nd.processing_job_id, "
                    "nd.source_url, nd.detected_format, nd.normalization_version, "
                    "nd.normalized_text, nd.original_checksum, nd.normalized_checksum, "
                    "nd.content_changed, nd.quality_signals, nd.warnings, nd.errors, "
                    "nd.provenance, nd.created_at, nd.updated_at, "
                    "cd.source_mime_type, cd.extraction_status, cd.canonical_checksum, "
                    "cd.quality_signals AS canonical_quality_signals, "
                    "a.content_type AS artifact_content_type, a.size_bytes, "
                    "a.checksum_sha256 AS raw_checksum "
                    "FROM normalized_documents nd "
                    "JOIN canonical_documents cd ON nd.canonical_document_id = cd.id "
                    "JOIN artifacts a ON nd.artifact_id = a.id "
                    "ORDER BY nd.created_at"
                )
                return [dict(row) for row in cur.fetchall()]

    def _apply_format_filter(
        self, spec: dict[str, Any], candidates: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], dict[str, int]]:
        """Filter by allowed formats."""
        source = spec.get("source", {})
        allowed_formats = source.get("allowed_formats")
        if not allowed_formats:
            return candidates, {}

        rejection_reasons: dict[str, int] = {}
        passed: list[dict[str, Any]] = []

        for doc in candidates:
            detected_format = doc.get("detected_format") or ""
            artifact_content_type = doc.get("artifact_content_type") or ""
            normalized_detected = (detected_format or "").lower()
            normalized_mime = (artifact_content_type or "").lower()

            matched = False
            for fmt in allowed_formats:
                fmt_lower = fmt.lower()
                if fmt_lower in normalized_detected or fmt_lower in normalized_mime:
                    matched = True
                    break

            if matched:
                passed.append(doc)
            else:
                key = f"format:{detected_format or artifact_content_type or 'unknown'}"
                rejection_reasons[key] = rejection_reasons.get(key, 0) + 1

        return passed, rejection_reasons

    def _apply_language_filter(
        self, spec: dict[str, Any], candidates: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], dict[str, int]]:
        """Filter by language requirements."""
        source = spec.get("source", {})
        allowed_languages = source.get("allowed_languages")
        if not allowed_languages:
            return candidates, {}

        rejection_reasons: dict[str, int] = {}
        passed: list[dict[str, Any]] = []

        for doc in candidates:
            quality_signals = doc.get("quality_signals") or {}
            language_info = quality_signals.get("language", {})
            detected_language = (language_info.get("code") or "").lower()

            matched = False
            for lang in allowed_languages:
                if lang.lower() == detected_language:
                    matched = True
                    break

            if matched:
                passed.append(doc)
            else:
                key = f"language:{detected_language or 'unknown'}"
                rejection_reasons[key] = rejection_reasons.get(key, 0) + 1

        return passed, rejection_reasons

    def _apply_length_filter(
        self, spec: dict[str, Any], candidates: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], dict[str, int]]:
        """Filter by content length."""
        content = spec.get("content", {})
        min_chars = content.get("minimum_characters")
        max_chars = content.get("maximum_characters")

        if min_chars is None and max_chars is None:
            return candidates, {}

        rejection_reasons: dict[str, int] = {}
        passed: list[dict[str, Any]] = []

        for doc in candidates:
            normalized_text = doc.get("normalized_text") or ""
            char_count = len(normalized_text)

            rejected = False
            reason = ""
            if min_chars is not None and char_count < min_chars:
                rejected = True
                reason = f"below_minimum:{min_chars}"
            elif max_chars is not None and char_count > max_chars:
                rejected = True
                reason = f"above_maximum:{max_chars}"

            if rejected:
                rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1
            else:
                passed.append(doc)

        return passed, rejection_reasons

    def _apply_quality_filter(
        self, spec: dict[str, Any], candidates: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], dict[str, int]]:
        """Filter by quality threshold."""
        quality = spec.get("quality", {})
        min_score = quality.get("minimum_score")

        if min_score is None:
            return candidates, {}

        rejection_reasons: dict[str, int] = {}
        passed: list[dict[str, Any]] = []

        for doc in candidates:
            canonical_quality = doc.get("canonical_quality_signals") or {}
            text_metrics = canonical_quality.get("text_metrics") or {}
            char_count = text_metrics.get("character_count", 0)
            quality_score = min(char_count / 1000.0, 1.0) if char_count else 0.0

            if quality_score < min_score:
                key = f"below_threshold:{quality_score:.2f}"
                rejection_reasons[key] = rejection_reasons.get(key, 0) + 1
            else:
                passed.append(doc)

        return passed, rejection_reasons

    def _apply_dedup_filter(
        self, spec: dict[str, Any], candidates: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Estimate deduplication impact."""
        dedup = spec.get("deduplication", {})
        mode = dedup.get("mode", "none")

        if mode == "none":
            return candidates, {"mode": "none", "estimated_groups": len(candidates), "estimated_duplicate_count": 0}

        # Group by normalized_checksum for exact duplicate estimation
        checksum_groups: dict[str, list[dict[str, Any]]] = {}
        for doc in candidates:
            checksum = doc.get("normalized_checksum")
            if checksum:
                checksum_groups.setdefault(checksum, []).append(doc)

        duplicate_count = sum(len(group) - 1 for group in checksum_groups.values() if len(group) > 1)
        group_count = sum(1 for group in checksum_groups.values() if len(group) > 1)

        dedup_impact = {
            "mode": mode,
            "estimated_groups": len(candidates) - duplicate_count,
            "estimated_duplicate_count": duplicate_count,
            "estimated_group_count": group_count,
            "similarity_threshold": dedup.get("similarity_threshold"),
        }

        return candidates, dedup_impact

    def _compute_language_distribution(self, candidates: list[dict[str, Any]]) -> dict[str, int]:
        """Compute language distribution of eligible candidates."""
        distribution: dict[str, int] = {}
        for doc in candidates:
            quality_signals = doc.get("quality_signals") or {}
            language_info = quality_signals.get("language", {})
            lang = language_info.get("code") or "unknown"
            distribution[lang] = distribution.get(lang, 0) + 1
        return distribution

    def _compute_quality_distribution(self, candidates: list[dict[str, Any]]) -> dict[str, Any]:
        """Compute quality distribution of eligible candidates."""
        if not candidates:
            return {"count": 0, "avg_character_count": 0}

        total_chars = 0
        for doc in candidates:
            canonical_quality = doc.get("canonical_quality_signals") or {}
            text_metrics = canonical_quality.get("text_metrics") or {}
            total_chars += text_metrics.get("character_count", 0)

        return {
            "count": len(candidates),
            "avg_character_count": total_chars // max(len(candidates), 1),
            "total_characters": total_chars,
        }

    def _estimate_output_size(self, candidates: list[dict[str, Any]]) -> int:
        """Estimate output size in bytes."""
        total_bytes = 0
        for doc in candidates:
            normalized_text = doc.get("normalized_text") or ""
            total_bytes += len(normalized_text.encode("utf-8"))
        return total_bytes
