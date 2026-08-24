"""Phase 2: Dataset Validation - validates datasets before export."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from psycopg.rows import class_row

from data_fetcher.database import Database, DatabaseError
from data_fetcher.models import (
    DatasetBuild,
    DatasetRecord,
    DatasetSpecification,
    ValidationReport,
)

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Validation-specific errors."""

    def __init__(self, category: str, message: str):
        self.category = category
        super().__init__(message)


class DatasetValidator:
    """Validates datasets before export."""

    def __init__(self, db: Database | None = None) -> None:
        self.db = db

    def validate(
        self,
        build: DatasetBuild,
        records: list[DatasetRecord],
    ) -> ValidationReport:
        """Validate a dataset build and its records.

        Runs all validation checks and returns a ValidationReport.
        """
        checks: list[dict[str, Any]] = []
        spec = self._load_specification(build.specification_id) if self.db else None
        spec_dict = spec.canonical_specification if spec else {}

        now = datetime.now(timezone.utc).isoformat()

        checks.append(self._check_schema_validity(records))
        checks.append(self._check_required_fields(records))
        checks.append(self._check_record_counts(build, records))
        checks.append(self._check_duplicate_leakage(records))
        checks.append(self._check_language_compliance(records, spec_dict))
        checks.append(self._check_quality_compliance(records, spec_dict))
        checks.append(self._check_content_length(records, spec_dict))
        checks.append(self._check_provenance_completeness(records))
        checks.append(self._check_specification_compliance(build, spec))
        checks.append(self._check_rejection_accounting(build, records))

        error_count = sum(1 for c in checks if c["severity"] == "error" and not c["passed"])
        warning_count = sum(1 for c in checks if c["severity"] == "warning" and not c["passed"])
        info_count = sum(1 for c in checks if c["severity"] == "info" and not c["passed"])

        if error_count > 0:
            status = "fail"
            overall_status = "invalid"
        elif warning_count > 0:
            status = "warn"
            overall_status = "warnings"
        else:
            status = "pass"
            overall_status = "valid"

        report = ValidationReport(
            id="",
            build_id=build.id,
            status=status,
            overall_status=overall_status,
            checks=checks,
            error_count=error_count,
            warning_count=warning_count,
            info_count=info_count,
            created_at=now,
        )

        if self.db:
            try:
                persisted = self.db.create_validation_report(report)
                if isinstance(persisted, ValidationReport):
                    report = persisted
            except DatabaseError as exc:
                logger.warning("Failed to persist validation report: %s", exc)

        return report

    def _load_specification(self, spec_id: str) -> DatasetSpecification | None:
        """Load the specification for a build."""
        try:
            return self.db.get_dataset_specification(spec_id)
        except DatabaseError as exc:
            raise ValidationError("database_error", f"Failed to load specification: {exc}") from exc

    def _check_schema_validity(self, records: list[DatasetRecord]) -> dict[str, Any]:
        """Check that all records have valid schema (required fields present and correct types)."""
        failures: list[str] = []
        required_fields = [
            "id", "build_id", "specification_id", "source_record_id",
            "normalized_record_id", "canonical_record_id", "raw_artifact_id",
            "source_url", "text", "quality_score", "selection_reason", "created_at",
        ]

        for record in records:
            for field_name in required_fields:
                value = getattr(record, field_name, None)
                if field_name in ("quality_score",) and value is None:
                    continue
                if field_name in ("dedup_group_id", "language") and value is None:
                    continue
                if value is None or (isinstance(value, str) and field_name not in ("language",) and not value):
                    failures.append(f"Record {record.id}: missing required field '{field_name}'")

        return {
            "check_name": "schema_validity",
            "severity": "error",
            "passed": len(failures) == 0,
            "message": f"All records have valid schema" if not failures else f"{len(failures)} schema violations found",
            "details": failures[:20],
        }

    def _check_required_fields(self, records: list[DatasetRecord]) -> dict[str, Any]:
        """Check that all required identifier fields are non-null."""
        failures: list[str] = []
        required_refs = ["source_record_id", "normalized_record_id", "canonical_record_id", "raw_artifact_id"]

        for record in records:
            for field_name in required_refs:
                value = getattr(record, field_name, None)
                if not value:
                    failures.append(f"Record {record.id}: required field '{field_name}' is null/empty")

        return {
            "check_name": "required_fields",
            "severity": "error",
            "passed": len(failures) == 0,
            "message": "All required identifier fields populated" if not failures else f"{len(failures)} missing identifiers",
            "details": failures[:20],
        }

    def _check_record_counts(
        self, build: DatasetBuild, records: list[DatasetRecord]
    ) -> dict[str, Any]:
        """Check that build record counts match actual record count."""
        actual_count = len(records)
        expected_count = build.records_accepted

        passed = actual_count == expected_count
        return {
            "check_name": "record_counts",
            "severity": "error",
            "passed": passed,
            "message": (
                f"Record count matches: {actual_count} = {expected_count}"
                if passed
                else f"Record count mismatch: build reports {expected_count}, actual {actual_count}"
            ),
            "details": {"expected": expected_count, "actual": actual_count},
        }

    def _check_duplicate_leakage(self, records: list[DatasetRecord]) -> dict[str, Any]:
        """Check that no duplicate records exist in the dataset."""
        seen_normalized: dict[str, int] = {}
        duplicates: list[str] = []

        for record in records:
            key = record.normalized_record_id
            if key in seen_normalized:
                duplicates.append(key)
            seen_normalized[key] = seen_normalized.get(key, 0) + 1

        passed = len(duplicates) == 0
        return {
            "check_name": "duplicate_leakage",
            "severity": "error",
            "passed": passed,
            "message": "No duplicate records found" if passed else f"{len(duplicates)} duplicate records detected",
            "details": {"duplicate_ids": duplicates[:20]},
        }

    def _check_language_compliance(
        self, records: list[DatasetRecord], spec: dict[str, Any]
    ) -> dict[str, Any]:
        """Check that all records comply with language requirements."""
        allowed_languages = spec.get("source", {}).get("allowed_languages")
        if not allowed_languages:
            return {
                "check_name": "language_compliance",
                "severity": "info",
                "passed": True,
                "message": "No language restrictions in specification",
                "details": {},
            }

        violations: list[str] = []
        for record in records:
            if record.language:
                if record.language.lower() not in [l.lower() for l in allowed_languages]:
                    violations.append(f"Record {record.id}: language '{record.language}' not in allowed list")

        passed = len(violations) == 0
        return {
            "check_name": "language_compliance",
            "severity": "error",
            "passed": passed,
            "message": f"All {len(records)} records comply with language requirements" if passed else f"{len(violations)} language violations",
            "details": {"allowed_languages": allowed_languages, "violations": violations[:20]},
        }

    def _check_quality_compliance(
        self, records: list[DatasetRecord], spec: dict[str, Any]
    ) -> dict[str, Any]:
        """Check that all records meet quality threshold."""
        min_score = spec.get("quality", {}).get("minimum_score")
        if min_score is None:
            return {
                "check_name": "quality_compliance",
                "severity": "info",
                "passed": True,
                "message": "No quality threshold in specification",
                "details": {},
            }

        violations: list[str] = []
        for record in records:
            if record.quality_score is not None and record.quality_score < min_score:
                violations.append(f"Record {record.id}: quality {record.quality_score:.4f} < {min_score}")

        passed = len(violations) == 0
        return {
            "check_name": "quality_compliance",
            "severity": "error",
            "passed": passed,
            "message": f"All {len(records)} records meet quality threshold ({min_score})" if passed else f"{len(violations)} quality violations",
            "details": {"minimum_score": min_score, "violations": violations[:20]},
        }

    def _check_content_length(
        self, records: list[DatasetRecord], spec: dict[str, Any]
    ) -> dict[str, Any]:
        """Check that all records comply with content length requirements."""
        content = spec.get("content", {})
        min_chars = content.get("minimum_characters")
        max_chars = content.get("maximum_characters")

        if min_chars is None and max_chars is None:
            return {
                "check_name": "content_length",
                "severity": "info",
                "passed": True,
                "message": "No content length restrictions in specification",
                "details": {},
            }

        violations: list[str] = []
        for record in records:
            char_count = len(record.text)
            if min_chars is not None and char_count < min_chars:
                violations.append(f"Record {record.id}: {char_count} chars < minimum {min_chars}")
            if max_chars is not None and char_count > max_chars:
                violations.append(f"Record {record.id}: {char_count} chars > maximum {max_chars}")

        passed = len(violations) == 0
        return {
            "check_name": "content_length",
            "severity": "error",
            "passed": passed,
            "message": f"All {len(records)} records comply with content length" if passed else f"{len(violations)} content length violations",
            "details": {"violation_count": len(violations), "violations": violations[:20]},
        }

    def _check_provenance_completeness(self, records: list[DatasetRecord]) -> dict[str, Any]:
        """Check that all records have complete provenance."""
        incomplete: list[str] = []

        for record in records:
            if not record.source_url:
                incomplete.append(f"Record {record.id}: missing source_url")
            if not record.raw_artifact_id:
                incomplete.append(f"Record {record.id}: missing raw_artifact_id")
            if not record.canonical_record_id:
                incomplete.append(f"Record {record.id}: missing canonical_record_id")

        passed = len(incomplete) == 0
        return {
            "check_name": "provenance_completeness",
            "severity": "warning",
            "passed": passed,
            "message": "All records have complete provenance" if passed else f"{len(incomplete)} provenance gaps",
            "details": {"incomplete": incomplete[:20]},
        }

    def _check_specification_compliance(
        self, build: DatasetBuild, spec: DatasetSpecification | None
    ) -> dict[str, Any]:
        """Check that build metadata complies with specification."""
        spec_hash = spec.specification_hash if spec else ""

        passed = build.specification_hash == spec_hash or not spec_hash
        return {
            "check_name": "specification_compliance",
            "severity": "error",
            "passed": passed,
            "message": "Build matches specification hash" if passed else f"Specification hash mismatch: build={build.specification_hash}, spec={spec_hash}",
            "details": {"build_hash": build.specification_hash, "spec_hash": spec_hash},
        }

    def _check_rejection_accounting(
        self, build: DatasetBuild, records: list[DatasetRecord]
    ) -> dict[str, Any]:
        """Check that rejected + accepted = records_considered."""
        accounted = build.records_accepted + build.records_rejected
        expected = build.records_considered

        passed = accounted == expected
        return {
            "check_name": "rejection_accounting",
            "severity": "warning",
            "passed": passed,
            "message": (
                f"Rejection accounting consistent: {build.records_accepted} + {build.records_rejected} = {accounted} = {expected}"
                if passed
                else f"Rejection accounting inconsistent: {build.records_accepted} + {build.records_rejected} = {accounted} != {expected}"
            ),
            "details": {
                "records_considered": expected,
                "records_accepted": build.records_accepted,
                "records_rejected": build.records_rejected,
                "accounted": accounted,
            },
        }
