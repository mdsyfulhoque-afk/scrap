"""Phase 2: Dataset Builder - constructs governed datasets from processed corpus."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from psycopg.rows import class_row

from data_fetcher.database import Database, DatabaseError
from data_fetcher.models import (
    DatasetBuild,
    DatasetBuildResult,
    DatasetRecord,
    DatasetSpecification,
    DecisionRecord,
)
from data_fetcher.phase2.specification import DatasetSpecificationManager

logger = logging.getLogger(__name__)


class DatasetBuilderError(Exception):
    """Dataset builder-specific errors."""

    def __init__(self, category: str, message: str):
        self.category = category
        super().__init__(message)


class DatasetBuilder:
    """Builds governed datasets from processed corpus."""

    def __init__(
        self,
        db: Database,
        spec_manager: DatasetSpecificationManager,
        dedup_engine: Any | None = None,
    ) -> None:
        self.db = db
        self.spec_manager = spec_manager
        self.dedup_engine = dedup_engine

    def build(self, specification: DatasetSpecification) -> DatasetBuildResult:
        """
        Build a dataset according to specification.

        Returns DatasetBuildResult with accepted, rejected, statistics.
        """
        spec = specification.canonical_specification
        now = datetime.now(timezone.utc).isoformat()

        build = self.db.create_dataset_build(
            specification_id=specification.id,
            specification_hash=specification.specification_hash,
            status="building",
            records_considered=0,
            records_accepted=0,
            records_rejected=0,
            error_message=None,
        )

        try:
            candidates = self._load_candidates(specification)
            accepted_candidates, rejected_candidates = self._apply_rules(spec, candidates)

            self.db.update_dataset_build_status(
                build_id=build.id,
                status="validating",
            )

            accepted: list[DatasetRecord] = []
            decisions: list[DecisionRecord] = []
            reason_counts: dict[str, int] = {}

            for candidate in accepted_candidates:
                record = DatasetRecord(
                    id="",
                    build_id=build.id,
                    specification_id=specification.id,
                    source_record_id=candidate.get("id", ""),
                    normalized_record_id=candidate.get("id", ""),
                    canonical_record_id=candidate.get("canonical_document_id", ""),
                    raw_artifact_id=candidate.get("artifact_id", ""),
                    source_url=candidate.get("source_url", ""),
                    text=candidate.get("normalized_text") or "",
                    language=self._extract_language(candidate),
                    quality_score=self._compute_quality_score(candidate),
                    dedup_group_id=candidate.get("_dedup_group_id"),
                    selection_reason=candidate.get("_selection_reason", "accepted"),
                    created_at=now,
                )
                saved_record = self.db.create_dataset_record(record)
                accepted.append(saved_record)

                decision = DecisionRecord(
                    id="",
                    build_id=build.id,
                    record_id=candidate.get("id", ""),
                    decision="accepted",
                    reason_codes=["accepted"],
                    actual_values=self._extract_actual_values(candidate),
                    thresholds=self._extract_thresholds(spec),
                    representative_record_id=None,
                    source_url=candidate.get("source_url", ""),
                    created_at=now,
                )
                saved_decision = self.db.create_decision_record(decision)
                decisions.append(saved_decision)
                reason_counts["accepted"] = reason_counts.get("accepted", 0) + 1

            for candidate in rejected_candidates:
                decision = DecisionRecord(
                    id="",
                    build_id=build.id,
                    record_id=candidate.get("id", ""),
                    decision="rejected",
                    reason_codes=candidate.get("_reason_codes", []),
                    actual_values=candidate.get("_actual_values", self._extract_actual_values(candidate)),
                    thresholds=self._extract_thresholds(spec),
                    representative_record_id=candidate.get("_representative_record_id"),
                    source_url=candidate.get("source_url", ""),
                    created_at=now,
                )
                saved_decision = self.db.create_decision_record(decision)
                decisions.append(saved_decision)
                for code in candidate.get("_reason_codes", []):
                    reason_counts[code] = reason_counts.get(code, 0) + 1

            total_rejected = len(decisions) - len(accepted)
            statistics = {
                "records_considered": len(candidates),
                "records_accepted": len(accepted),
                "records_rejected": total_rejected,
                "reason_counts": reason_counts,
                "acceptance_rate": round(len(accepted) / max(len(candidates), 1), 4),
            }

            self.db.update_dataset_build_status(
                build_id=build.id,
                status="accepted",
                records_considered=len(candidates),
                records_accepted=len(accepted),
                records_rejected=total_rejected,
            )

            final_build = self.db.get_dataset_build(build.id)
            return DatasetBuildResult(
                build=final_build,
                accepted=accepted,
                rejected=[d for d in decisions if d.decision == "rejected"],
                statistics=statistics,
            )

        except Exception as exc:
            self.db.update_dataset_build_status(
                build_id=build.id,
                status="failed",
                error_message=str(exc),
            )
            raise DatasetBuilderError("build_failed", str(exc)) from exc

    def _load_candidates(self, specification: DatasetSpecification) -> list[dict]:
        """Query normalized documents as candidates."""
        try:
            with self.db.connect() as conn:
                with conn.cursor(row_factory=class_row(dict)) as cur:
                    cur.execute(
                        "SELECT nd.id, nd.canonical_document_id, nd.artifact_id, "
                        "nd.processing_job_id, nd.source_url, nd.detected_format, "
                        "nd.normalization_version, nd.normalized_text, "
                        "nd.original_checksum, nd.normalized_checksum, "
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
        except DatabaseError as exc:
            raise DatasetBuilderError("database_error", f"Failed to load candidates: {exc}") from exc

    def _apply_rules(
        self, spec: dict[str, Any], candidates: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Apply all eligibility rules, return (accepted, rejected).

        Each candidate is checked against ALL conditions (format, language,
        content length, quality) so that every applicable reason code is
        accumulated.  Candidates with no reason codes proceed to dedup.
        """
        thresholds = self._extract_thresholds(spec)

        source = spec.get("source", {})
        allowed_formats = source.get("allowed_formats")
        allowed_languages = source.get("allowed_languages")
        content = spec.get("content", {})
        min_chars = content.get("minimum_characters")
        max_chars = content.get("maximum_characters")
        quality = spec.get("quality", {})
        min_score = quality.get("minimum_score")
        selection = spec.get("selection", {})
        max_records = selection.get("maximum_records")

        accepted: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []

        for candidate in candidates:
            reason_codes: list[str] = []

            detected_format = candidate.get("detected_format") or ""
            artifact_content_type = candidate.get("artifact_content_type") or ""
            normalized_detected = (detected_format or "").lower()
            normalized_mime = (artifact_content_type or "").lower()

            if allowed_formats:
                matched = False
                for fmt in allowed_formats:
                    fmt_lower = fmt.lower()
                    if fmt_lower in normalized_detected or fmt_lower in normalized_mime:
                        matched = True
                        break
                if not matched:
                    reason_codes.append("unsupported_format")

            detected_language = self._extract_language_code(candidate)
            if allowed_languages:
                matched = any(
                    lang.lower() == detected_language
                    for lang in allowed_languages
                )
                if not matched:
                    reason_codes.append("wrong_language")

            normalized_text = candidate.get("normalized_text") or ""
            char_count = len(normalized_text)
            if min_chars is not None and char_count < min_chars:
                reason_codes.append("content_too_short")
            if max_chars is not None and char_count > max_chars:
                reason_codes.append("content_too_long")

            quality_score = self._compute_quality_score(candidate)
            if min_score is not None and quality_score is not None and quality_score < min_score:
                reason_codes.append("quality_below_threshold")

            candidate["_quality_score"] = quality_score
            candidate["_reason_codes"] = reason_codes
            candidate["_actual_values"] = self._extract_actual_values(candidate)
            candidate["_thresholds"] = thresholds

            if reason_codes:
                rejected.append(candidate)
            else:
                accepted.append(candidate)

        accepted = self._apply_dedup_rules(spec, accepted, rejected)

        accepted = [
            c for c in accepted
            if not c.get("_reason_codes")
        ]
        for candidate in accepted:
            candidate["_selection_reason"] = candidate.get("_selection_reason", "accepted")

        if max_records is not None and len(accepted) > max_records:
            sorted_accepted = sorted(
                accepted,
                key=lambda c: (
                    -(c.get("_quality_score", 0.0) or 0.0),
                    c.get("id", ""),
                ),
            )
            excess = sorted_accepted[max_records:]
            for candidate in excess:
                candidate["_reason_codes"] = ["record_limit_reached"]
                candidate["_actual_values"] = self._extract_actual_values(candidate)
                rejected.append(candidate)
            accepted = sorted_accepted[:max_records]

        return accepted, rejected

    def _apply_dedup_rules(
        self,
        spec: dict[str, Any],
        candidates: list[dict[str, Any]],
        rejected: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Apply deduplication rules and select representatives.

        Modifies candidates in place: non-representatives get _reason_codes set
        and are appended to *rejected*. Representatives are returned in the
        resulting accepted list.
        """
        dedup = spec.get("deduplication", {})
        mode = dedup.get("mode", "none")

        if mode == "none" or not candidates:
            for candidate in candidates:
                candidate["_quality_score"] = self._compute_quality_score(candidate)
            return candidates

        if self.dedup_engine is not None:
            return self._dedup_with_engine(spec, candidates, rejected)
        else:
            return self._dedup_with_db(spec, candidates, rejected)

    def _dedup_with_engine(
        self,
        spec: dict[str, Any],
        candidates: list[dict[str, Any]],
        rejected: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Run dedup_engine on candidates and select representatives."""
        from data_fetcher.phase2.deduplication import (
            DocumentReference,
            DuplicateDetectionConfig,
            DuplicateDetector,
        )

        dedup = spec.get("deduplication", {})
        similarity_threshold = dedup.get("similarity_threshold", 0.85)

        config = DuplicateDetectionConfig(jaccard_threshold=similarity_threshold)
        if not isinstance(self.dedup_engine, DuplicateDetector):
            detector = DuplicateDetector(config)
        else:
            detector = self.dedup_engine

        documents: list[DocumentReference] = []
        candidate_map: dict[str, dict[str, Any]] = {}

        for candidate in candidates:
            doc_id = candidate.get("id", "")
            candidate_map[doc_id] = candidate
            quality_score = self._compute_quality_score(candidate) or 0.0
            warning_count = len(candidate.get("warnings") or [])
            documents.append(DocumentReference(
                document_id=doc_id,
                document_type="normalized_document",
                normalized_checksum=candidate.get("normalized_checksum"),
                canonical_checksum=candidate.get("canonical_checksum"),
                raw_checksum=candidate.get("raw_checksum"),
                normalized_text=candidate.get("normalized_text"),
                quality_score=quality_score,
                warning_count=warning_count,
                source_url=candidate.get("source_url", ""),
                artifact_id=candidate.get("artifact_id", ""),
                canonical_document_id=candidate.get("canonical_document_id"),
                normalized_document_id=doc_id,
            ))

        result = detector.detect(documents)

        rep_ids: set[str] = set()
        rejected_ids: set[str] = set()
        member_to_group: dict[str, str] = {}
        group_method: dict[str, str] = {}

        for group in result.all_groups:
            group_method[group.id] = group.duplicate_method

        for membership in result.memberships:
            member_id = (
                membership.normalized_document_id
                or membership.canonical_document_id
                or membership.artifact_id
            )
            if member_id and member_id in candidate_map:
                member_to_group[member_id] = membership.group_id
                if membership.is_representative:
                    rep_ids.add(member_id)
                else:
                    rejected_ids.add(member_id)

        accepted: list[dict[str, Any]] = []
        for candidate in candidates:
            doc_id = candidate.get("id", "")
            candidate["_quality_score"] = self._compute_quality_score(candidate)

            if doc_id in rejected_ids:
                group_id = member_to_group.get(doc_id)
                method = group_method.get(group_id, "near_duplicate")
                reason = (
                    "exact_duplicate"
                    if method == "raw_exact"
                    else "normalized_duplicate"
                    if method == "normalized_exact"
                    else "near_duplicate"
                )
                candidate["_reason_codes"] = [reason]
                candidate["_actual_values"] = self._extract_actual_values(candidate)
                candidate["_dedup_group_id"] = group_id
                candidate["_representative_record_id"] = None
                rejected.append(candidate)
            elif doc_id in rep_ids:
                group_id = member_to_group.get(doc_id)
                candidate["_dedup_group_id"] = group_id
                candidate["_selection_reason"] = "dedup_representative"
                accepted.append(candidate)
            else:
                candidate["_selection_reason"] = "dedup_unique"
                accepted.append(candidate)

        return accepted

    def _dedup_with_db(
        self,
        spec: dict[str, Any],
        candidates: list[dict[str, Any]],
        rejected: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Read existing duplicate groups from database and select representatives."""
        candidate_ids = {c.get("id", "") for c in candidates if c.get("id")}

        groups: list[dict[str, Any]] = []
        memberships: list[dict[str, Any]] = []

        try:
            with self.db.connect() as conn:
                with conn.cursor(row_factory=class_row(dict)) as cur:
                    cur.execute("SELECT * FROM duplicate_groups ORDER BY created_at")
                    groups = [dict(row) for row in cur.fetchall()]
                    cur.execute("SELECT * FROM duplicate_memberships ORDER BY created_at")
                    memberships = [dict(row) for row in cur.fetchall()]
        except DatabaseError:
            groups = []
            memberships = []

        rep_ids: set[str] = set()
        rejected_ids: set[str] = set()
        member_to_group: dict[str, str] = {}
        group_method: dict[str, str] = {}

        for group in groups:
            group_method[group["id"]] = group.get("duplicate_method", "near_duplicate")

        for membership in memberships:
            member_id = (
                membership.get("normalized_document_id")
                or membership.get("canonical_document_id")
                or membership.get("artifact_id")
            )
            if member_id and str(member_id) in candidate_ids:
                member_to_group[str(member_id)] = str(membership["group_id"])
                if membership.get("is_representative"):
                    rep_ids.add(str(member_id))
                else:
                    method = group_method.get(str(membership["group_id"]), "near_duplicate")
                    reason = (
                        "exact_duplicate"
                        if method == "raw_exact"
                        else "normalized_duplicate"
                        if method == "normalized_exact"
                        else "near_duplicate"
                    )
                    rejected_ids.add(str(member_id))
                    candidate = next((c for c in candidates if c.get("id") == str(member_id)), None)
                    if candidate:
                        candidate["_reason_codes"] = [reason]
                        candidate["_actual_values"] = self._extract_actual_values(candidate)
                        candidate["_dedup_group_id"] = str(membership["group_id"])
                        candidate["_representative_record_id"] = membership.get("representative_record_id") if "representative_record_id" in membership else None

        accepted: list[dict[str, Any]] = []
        for candidate in candidates:
            doc_id = candidate.get("id", "")
            candidate["_quality_score"] = self._compute_quality_score(candidate)

            if doc_id in rejected_ids:
                continue
            elif doc_id in rep_ids:
                group_id = member_to_group.get(doc_id)
                candidate["_dedup_group_id"] = group_id
                candidate["_selection_reason"] = "dedup_representative"
                accepted.append(candidate)
            else:
                candidate["_selection_reason"] = "dedup_unique"
                accepted.append(candidate)

        return accepted

    def _select_representatives(
        self, spec: dict[str, Any], candidates: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Select deterministic representatives from duplicate groups."""
        dedup = spec.get("deduplication", {})
        mode = dedup.get("mode", "none")

        if mode == "none" or not candidates:
            return list(candidates)

        if self.dedup_engine is not None:
            return self._select_representatives_with_engine(spec, candidates)
        else:
            return self._select_representatives_with_db(candidates)

    def _select_representatives_with_engine(
        self, spec: dict[str, Any], candidates: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Select representatives using the dedup engine."""
        from data_fetcher.phase2.deduplication import (
            DocumentReference,
            DuplicateDetectionConfig,
            DuplicateDetector,
        )

        dedup = spec.get("deduplication", {})
        similarity_threshold = dedup.get("similarity_threshold", 0.85)
        config = DuplicateDetectionConfig(jaccard_threshold=similarity_threshold)
        detector = self.dedup_engine if isinstance(self.dedup_engine, DuplicateDetector) else DuplicateDetector(config)

        documents: list[DocumentReference] = []
        for candidate in candidates:
            quality_score = self._compute_quality_score(candidate) or 0.0
            warning_count = len(candidate.get("warnings") or [])
            documents.append(DocumentReference(
                document_id=candidate.get("id", ""),
                document_type="normalized_document",
                normalized_checksum=candidate.get("normalized_checksum"),
                canonical_checksum=candidate.get("canonical_checksum"),
                raw_checksum=candidate.get("raw_checksum"),
                normalized_text=candidate.get("normalized_text"),
                quality_score=quality_score,
                warning_count=warning_count,
                source_url=candidate.get("source_url", ""),
                artifact_id=candidate.get("artifact_id", ""),
                canonical_document_id=candidate.get("canonical_document_id"),
                normalized_document_id=candidate.get("id", ""),
            ))

        result = detector.detect(documents)

        rep_ids: set[str] = set()
        for group in result.all_groups:
            group_memberships = [m for m in result.memberships if m.group_id == group.id]
            doc_map = {d.document_id: d for d in documents}

            def sort_key(doc_id: str) -> tuple[int, int, int, str]:
                doc = doc_map.get(doc_id)
                if not doc:
                    return (0, 0, 0, doc_id)
                has_normalized = 1 if doc.normalized_text else 0
                quality = int(-doc.quality_score * 10000)
                warnings = doc.warning_count
                return (has_normalized, quality, warnings, doc_id)

            member_ids = []
            for membership in group_memberships:
                mid = (
                    membership.normalized_document_id
                    or membership.canonical_document_id
                    or membership.artifact_id
                )
                if mid:
                    member_ids.append(mid)

            member_ids.sort(key=sort_key)
            if member_ids:
                rep_ids.add(member_ids[0])

        accepted: list[dict[str, Any]] = []
        for candidate in candidates:
            doc_id = candidate.get("id", "")
            if doc_id in rep_ids:
                candidate["_selection_reason"] = "dedup_representative"
                candidate["_quality_score"] = self._compute_quality_score(candidate)
                accepted.append(candidate)
        return accepted

    def _select_representatives_with_db(
        self, candidates: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Select representatives by reading DB duplicate groups."""
        candidate_ids = {c.get("id", "") for c in candidates if c.get("id")}

        rep_ids: set[str] = set()

        try:
            with self.db.connect() as conn:
                with conn.cursor(row_factory=class_row(dict)) as cur:
                    id_list = list(candidate_ids)
                    cur.execute(
                        "SELECT normalized_document_id, canonical_document_id, "
                        "artifact_id, is_representative "
                        "FROM duplicate_memberships WHERE "
                        "normalized_document_id = ANY(%s::UUID[]) "
                        "OR canonical_document_id = ANY(%s::UUID[]) "
                        "OR artifact_id = ANY(%s::UUID[])",
                        (id_list, id_list, id_list),
                    )
                    for row in cur.fetchall():
                        member_id = (
                            str(row.get("normalized_document_id"))
                            if row.get("normalized_document_id")
                            else str(row.get("canonical_document_id"))
                            if row.get("canonical_document_id")
                            else str(row.get("artifact_id"))
                        )
                        if member_id in candidate_ids and row.get("is_representative"):
                            rep_ids.add(member_id)
        except (DatabaseError, Exception):
            rep_ids = set()

        accepted: list[dict[str, Any]] = []
        for candidate in candidates:
            doc_id = candidate.get("id", "")
            if doc_id in rep_ids:
                candidate["_selection_reason"] = "dedup_representative"
            else:
                candidate["_selection_reason"] = "dedup_unique"
            candidate["_quality_score"] = self._compute_quality_score(candidate)
            accepted.append(candidate)

        return accepted

    def _compute_quality_score(self, candidate: dict[str, Any]) -> float | None:
        """Compute quality score for a candidate."""
        canonical_quality = candidate.get("canonical_quality_signals") or {}
        text_metrics = canonical_quality.get("text_metrics") or {}
        char_count = text_metrics.get("character_count", 0)
        if char_count:
            return min(char_count / 1000.0, 1.0)
        return 0.0

    def _extract_language_code(self, candidate: dict[str, Any]) -> str:
        """Extract language code from candidate quality signals."""
        quality_signals = candidate.get("quality_signals") or {}
        language_info = quality_signals.get("language", {})
        return (language_info.get("code") or "").lower()

    def _extract_language(self, candidate: dict[str, Any]) -> str | None:
        """Extract full language name from candidate."""
        quality_signals = candidate.get("quality_signals") or {}
        language_info = quality_signals.get("language", {})
        lang = language_info.get("code")
        return lang if lang else None

    def _extract_actual_values(self, candidate: dict[str, Any]) -> dict[str, Any]:
        """Extract actual measured values for a candidate."""
        quality_score = self._compute_quality_score(candidate)
        language = self._extract_language(candidate)
        normalized_text = candidate.get("normalized_text") or ""
        return {
            "character_count": len(normalized_text),
            "language": language,
            "quality_score": quality_score,
            "detected_format": candidate.get("detected_format"),
            "canonical_checksum": candidate.get("canonical_checksum"),
            "normalized_checksum": candidate.get("normalized_checksum"),
            "extraction_status": candidate.get("extraction_status"),
            "size_bytes": candidate.get("size_bytes"),
        }

    def _extract_thresholds(self, spec: dict[str, Any]) -> dict[str, Any]:
        """Extract thresholds from specification."""
        source = spec.get("source", {})
        content = spec.get("content", {})
        quality = spec.get("quality", {})
        dedup = spec.get("deduplication", {})
        selection = spec.get("selection", {})
        return {
            "allowed_formats": source.get("allowed_formats"),
            "allowed_languages": source.get("allowed_languages"),
            "minimum_characters": content.get("minimum_characters"),
            "maximum_characters": content.get("maximum_characters"),
            "minimum_score": quality.get("minimum_score"),
            "deduplication_mode": dedup.get("mode", "none"),
            "similarity_threshold": dedup.get("similarity_threshold"),
            "maximum_records": selection.get("maximum_records"),
            "minimum_records": selection.get("minimum_records"),
        }
