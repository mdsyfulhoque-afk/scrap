"""Phase 2: Manifest and Reproducibility - produces build manifests."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any

from data_fetcher.models import (
    DatasetBuild,
    DatasetRecord,
    DatasetSpecification,
    ValidationReport,
)

logger = logging.getLogger(__name__)


PIPELINE_VERSION = "2.0.0"


class ManifestBuilder:
    """Builds reproducible dataset manifests."""

    def build(
        self,
        build: DatasetBuild,
        spec: DatasetSpecification,
        records: list[DatasetRecord],
        validation: ValidationReport | None = None,
    ) -> dict[str, Any]:
        """
        Build a manifest dictionary for a dataset export.

        Args:
            build: The dataset build record
            spec: The dataset specification
            records: Accepted dataset records
            validation: Optional validation report

        Returns:
            Manifest dictionary with all provenance and metadata fields
        """
        now = datetime.now(timezone.utc).isoformat()

        spec_dict = spec.canonical_specification

        manifest: dict[str, Any] = {
            "dataset_name": spec.name,
            "dataset_version": spec.version,
            "dataset_build_id": build.id,
            "dataset_spec_hash": build.specification_hash,
            "pipeline_version": PIPELINE_VERSION,
            "source_snapshot": f"spec-{build.specification_hash[:12]}",
            "created_at": now,
            "records_considered": build.records_considered,
            "records_accepted": len(records),
            "records_rejected": build.records_rejected,
            "validation_status": validation.status if validation else "not_validated",
            "export_format": spec_dict.get("output", {}).get("format", "jsonl"),
            "specification": {
                "name": spec.name,
                "version": spec.version,
                "hash": spec.specification_hash,
                "canonical_specification": spec_dict,
            },
            "build": {
                "id": build.id,
                "specification_id": build.specification_id,
                "status": build.status,
                "started_at": build.started_at,
                "finished_at": build.finished_at,
                "error_message": build.error_message,
            },
        }

        if validation:
            manifest["validation_report"] = {
                "id": validation.id,
                "status": validation.status,
                "overall_status": validation.overall_status,
                "error_count": validation.error_count,
                "warning_count": validation.warning_count,
                "info_count": validation.info_count,
                "checks": validation.checks,
            }

        manifest["record_checksums"] = {
            "canonical_record_count": len(records),
            "sha256": hashlib.sha256(
                json.dumps(
                    [str(r.normalized_record_id) for r in sorted(records, key=lambda r: str(r.normalized_record_id))],
                    sort_keys=True,
                ).encode("utf-8")
            ).hexdigest(),
        }

        return manifest
