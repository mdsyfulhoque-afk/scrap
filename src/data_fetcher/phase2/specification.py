"""Phase 2: Dataset specification and validation."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from data_fetcher.database import Database, DatabaseError
from data_fetcher.models import DatasetSpecification

logger = logging.getLogger(__name__)


class SpecificationError(Exception):
    """Specification-specific errors."""
    def __init__(self, category: str, message: str):
        self.category = category
        super().__init__(message)


SUPPORTED_FORMATS = ["html", "json", "xml", "csv", "markdown", "plain_text", "text"]
SUPPORTED_OUTPUT_FORMATS = ["jsonl", "csv", "parquet"]
SUPPORTED_DEDUPLICATION_MODES = ["exact", "normalized", "near", "none"]


class SpecificationValidator:
    """Validates dataset specifications."""

    def validate(self, spec: dict[str, Any]) -> list[str]:
        """Return list of validation errors (empty if valid)."""
        errors: list[str] = []

        dataset = spec.get("dataset")
        if dataset is None:
            errors.append("Missing 'dataset' section")
        else:
            name = dataset.get("name")
            if not isinstance(name, str) or not name.strip():
                errors.append("dataset.name must be a non-empty string")

            version = dataset.get("version")
            if not isinstance(version, int) or version <= 0:
                errors.append("dataset.version must be a positive integer")

        source = spec.get("source")
        if source is not None:
            allowed_formats = source.get("allowed_formats")
            if allowed_formats is not None:
                if not isinstance(allowed_formats, list):
                    errors.append("source.allowed_formats must be a list")
                else:
                    for fmt in allowed_formats:
                        if fmt not in SUPPORTED_FORMATS:
                            errors.append(
                                f"Unsupported format: {fmt}. "
                                f"Supported: {', '.join(SUPPORTED_FORMATS)}"
                            )

        content = spec.get("content")
        if content is not None:
            min_chars = content.get("minimum_characters")
            max_chars = content.get("maximum_characters")

            if min_chars is not None:
                if not isinstance(min_chars, int) or min_chars < 0:
                    errors.append("content.minimum_characters must be >= 0")

            if max_chars is not None:
                if not isinstance(max_chars, int) or max_chars <= 0:
                    errors.append("content.maximum_characters must be > 0")

            if min_chars is not None and max_chars is not None:
                if isinstance(min_chars, int) and isinstance(max_chars, int):
                    if min_chars >= max_chars:
                        errors.append(
                            "content.minimum_characters must be less than maximum_characters"
                        )

        quality = spec.get("quality")
        if quality is not None:
            min_score = quality.get("minimum_score")
            if min_score is not None:
                if not isinstance(min_score, (int, float)):
                    errors.append("quality.minimum_score must be a number")
                elif not (0.0 <= float(min_score) <= 1.0):
                    errors.append("quality.minimum_score must be between 0.0 and 1.0")

        dedup = spec.get("deduplication")
        if dedup is not None:
            mode = dedup.get("mode")
            if mode is not None:
                if mode not in SUPPORTED_DEDUPLICATION_MODES:
                    errors.append(
                        f"Unsupported deduplication mode: {mode}. "
                        f"Supported: {', '.join(SUPPORTED_DEDUPLICATION_MODES)}"
                    )

            threshold = dedup.get("similarity_threshold")
            if threshold is not None:
                if not isinstance(threshold, (int, float)):
                    errors.append("deduplication.similarity_threshold must be a number")
                elif not (0.0 <= float(threshold) <= 1.0):
                    errors.append(
                        "deduplication.similarity_threshold must be between 0.0 and 1.0"
                    )

        selection = spec.get("selection")
        if selection is not None:
            max_records = selection.get("maximum_records")
            if max_records is not None:
                if not isinstance(max_records, int) or max_records <= 0:
                    errors.append("selection.maximum_records must be a positive integer")

        output = spec.get("output")
        if output is not None:
            fmt = output.get("format")
            if fmt is not None:
                if fmt not in SUPPORTED_OUTPUT_FORMATS:
                    errors.append(
                        f"Unsupported output format: {fmt}. "
                        f"Supported: {', '.join(SUPPORTED_OUTPUT_FORMATS)}"
                    )

        return errors


class DatasetSpecificationManager:
    """Manages dataset specification lifecycle."""

    def __init__(self, db: Database) -> None:
        self.db = db
        self.validator = SpecificationValidator()

    def create_specification(
        self,
        name: str,
        specification: dict[str, Any],
        description: str | None = None,
    ) -> DatasetSpecification:
        """Create a new dataset specification."""
        validation_errors = self.validator.validate(specification)
        if validation_errors:
            raise SpecificationError(
                "validation_failed",
                "; ".join(validation_errors),
            )

        spec_hash = self.compute_hash(specification)
        canonical = json.dumps(specification, sort_keys=True, separators=(",", ":"))

        existing = self.db.get_dataset_specification_by_name_version(name, 1)
        if existing:
            raise SpecificationError(
                "duplicate_name_version",
                f"Specification '{name}' version 1 already exists",
            )

        try:
            return self.db.create_dataset_specification(
                name=name,
                version=1,
                specification_hash=spec_hash,
                canonical_specification=specification,
                status="draft",
                description=description,
            )
        except DatabaseError as exc:
            raise SpecificationError(
                "database_error",
                f"Failed to create specification: {exc}",
            ) from exc

    def get_specification(self, spec_id: str) -> DatasetSpecification | None:
        """Retrieve a specification by ID."""
        try:
            return self.db.get_dataset_specification(spec_id)
        except DatabaseError as exc:
            raise SpecificationError(
                "database_error",
                f"Failed to retrieve specification: {exc}",
            ) from exc

    def get_specification_by_name_version(
        self,
        name: str,
        version: int = 1,
    ) -> DatasetSpecification | None:
        """Retrieve a specification by its name and version."""
        try:
            return self.db.get_dataset_specification_by_name_version(name, version)
        except DatabaseError as exc:
            raise SpecificationError(
                "database_error",
                f"Failed to retrieve specification: {exc}",
            ) from exc

    def list_specifications(self, status: str | None = None) -> list[DatasetSpecification]:
        """List specifications, optionally filtered by status."""
        try:
            return self.db.list_dataset_specifications(status)
        except DatabaseError as exc:
            raise SpecificationError(
                "database_error",
                f"Failed to list specifications: {exc}",
            ) from exc

    def compute_hash(self, specification: dict[str, Any]) -> str:
        """Compute canonical SHA-256 hash of specification."""
        canonical = json.dumps(specification, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
