"""Phase 2: JSONL Export Package - exports datasets to a directory."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from data_fetcher.models import (
    DatasetBuild,
    DatasetRecord,
    DatasetSpecification,
    DecisionRecord,
    ExportResult,
    ValidationReport,
)

logger = logging.getLogger(__name__)


class ExportError(Exception):
    """Export-specific errors."""

    def __init__(self, category: str, message: str):
        self.category = category
        super().__init__(message)


class DatasetExporter:
    """Exports governed datasets to a JSONL package."""

    def __init__(self, db: Any | None = None, spec_manager: Any | None = None) -> None:
        self.db = db
        self.spec_manager = spec_manager

    def export(
        self,
        build: DatasetBuild,
        output_dir: str,
        records: list[DatasetRecord] | None = None,
        rejected_decisions: list[DecisionRecord] | None = None,
        validation: ValidationReport | None = None,
        manifest: dict[str, Any] | None = None,
        specification: DatasetSpecification | None = None,
    ) -> ExportResult:
        """
        Export a dataset build to a directory.

        Produces the following files in *output_dir*:
        - data.jsonl       — accepted records
        - manifest.json    — dataset manifest
        - statistics.json  — build statistics
        - rejected.jsonl   — rejected records with decisions
        - provenance.jsonl — per-record provenance
        - validation_report.json — validation report

        Returns an ExportResult with file paths and counts.
        """
        out = Path(output_dir)

        if not out.exists():
            out.mkdir(parents=True, exist_ok=True)

        now = datetime.now(timezone.utc).isoformat()

        accepted_records = records or []

        accepted_count = self._write_jsonl(
            out / "data.jsonl",
            [self._record_to_dict(r) for r in accepted_records],
        )

        rejected_records = rejected_decisions or []
        rejected_count = self._write_jsonl(
            out / "rejected.jsonl",
            [self._decision_to_dict(d) for d in rejected_records],
        )

        provenance_count = self._write_jsonl(
            out / "provenance.jsonl",
            [self._provenance_to_dict(r) for r in accepted_records],
        )

        stats = self._build_statistics(
            build, accepted_records, rejected_records
        )
        stats_path = out / "statistics.json"
        with open(stats_path, "w", encoding="utf-8") as fh:
            json.dump(stats, fh, indent=2, ensure_ascii=False, default=str)

        if manifest is None:
            from data_fetcher.phase2.manifest import ManifestBuilder
            manifest_builder = ManifestBuilder()
            manifest = manifest_builder.build(
                build,
                specification or DatasetSpecification(
                    id=build.specification_id,
                    name="",
                    version=0,
                    specification_hash=build.specification_hash,
                    canonical_specification={},
                    status="unknown",
                    description=None,
                    created_at="",
                    updated_at="",
                ),
                accepted_records,
                validation,
            )

        manifest_path = out / "manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, indent=2, ensure_ascii=False, default=str)

        val_path = out / "validation_report.json"
        if validation is not None:
            with open(val_path, "w", encoding="utf-8") as fh:
                json.dump(self._validation_to_dict(validation), fh, indent=2, ensure_ascii=False, default=str)
        else:
            with open(val_path, "w", encoding="utf-8") as fh:
                json.dump({"status": "not_validated", "overall_status": "not_validated"}, fh, indent=2)

        files: dict[str, str] = {
            "data.jsonl": str(out / "data.jsonl"),
            "manifest.json": str(manifest_path),
            "statistics.json": str(stats_path),
            "rejected.jsonl": str(out / "rejected.jsonl"),
            "provenance.jsonl": str(out / "provenance.jsonl"),
            "validation_report.json": str(val_path),
        }

        return ExportResult(
            build_id=build.id,
            output_dir=str(out),
            accepted_count=accepted_count,
            rejected_count=rejected_count,
            files=files,
            exported_at=now,
        )

    def _write_jsonl(self, path: Path, records: list[dict[str, Any]]) -> int:
        """Write a list of dicts to a JSONL file. Returns count of records written."""
        count = 0
        with open(path, "w", encoding="utf-8") as fh:
            for record in records:
                fh.write(json.dumps(record, ensure_ascii=False, default=str))
                fh.write("\n")
                count += 1
        return count

    def _record_to_dict(self, record: DatasetRecord) -> dict[str, Any]:
        """Convert a DatasetRecord to a serializable dict."""
        return {
            "id": record.id,
            "build_id": record.build_id,
            "specification_id": record.specification_id,
            "source_record_id": record.source_record_id,
            "normalized_record_id": record.normalized_record_id,
            "canonical_record_id": record.canonical_record_id,
            "raw_artifact_id": record.raw_artifact_id,
            "source_url": record.source_url,
            "text": record.text,
            "language": record.language,
            "quality_score": record.quality_score,
            "dedup_group_id": record.dedup_group_id,
            "selection_reason": record.selection_reason,
            "created_at": record.created_at,
        }

    def _decision_to_dict(self, decision: DecisionRecord) -> dict[str, Any]:
        """Convert a DecisionRecord to a serializable dict."""
        return {
            "id": decision.id,
            "build_id": decision.build_id,
            "record_id": decision.record_id,
            "decision": decision.decision,
            "reason_codes": decision.reason_codes,
            "actual_values": decision.actual_values,
            "thresholds": decision.thresholds,
            "representative_record_id": decision.representative_record_id,
            "source_url": decision.source_url,
            "created_at": decision.created_at,
        }

    def _provenance_to_dict(self, record: DatasetRecord) -> dict[str, Any]:
        """Extract provenance information from a DatasetRecord."""
        return {
            "record_id": record.id,
            "source_record_id": record.source_record_id,
            "normalized_record_id": record.normalized_record_id,
            "canonical_record_id": record.canonical_record_id,
            "raw_artifact_id": record.raw_artifact_id,
            "source_url": record.source_url,
            "language": record.language,
            "quality_score": record.quality_score,
            "selection_reason": record.selection_reason,
            "dedup_group_id": record.dedup_group_id,
        }

    def _validation_to_dict(self, validation: ValidationReport) -> dict[str, Any]:
        """Convert a ValidationReport to a serializable dict."""
        return {
            "id": validation.id,
            "build_id": validation.build_id,
            "status": validation.status,
            "overall_status": validation.overall_status,
            "checks": validation.checks,
            "error_count": validation.error_count,
            "warning_count": validation.warning_count,
            "info_count": validation.info_count,
            "created_at": validation.created_at,
        }

    def _build_statistics(
        self,
        build: DatasetBuild,
        accepted_records: list[DatasetRecord],
        rejected_decisions: list[DecisionRecord],
    ) -> dict[str, Any]:
        """Build statistics dictionary for the export."""
        reason_counts: dict[str, int] = {}
        for d in rejected_decisions:
            for code in d.reason_codes:
                reason_counts[code] = reason_counts.get(code, 0) + 1

        total_chars = sum(len(r.text) for r in accepted_records)
        quality_scores = [r.quality_score for r in accepted_records if r.quality_score is not None]
        languages: dict[str, int] = {}
        for r in accepted_records:
            lang = r.language or "unknown"
            languages[lang] = languages.get(lang, 0) + 1

        return {
            "build_id": build.id,
            "specification_id": build.specification_id,
            "specification_hash": build.specification_hash,
            "build_status": build.status,
            "records_considered": build.records_considered,
            "records_accepted": len(accepted_records),
            "records_rejected": len(rejected_decisions),
            "rejection_reason_counts": reason_counts,
            "total_characters": total_chars,
            "average_characters": round(total_chars / max(len(accepted_records), 1), 2),
            "average_quality_score": round(sum(quality_scores) / max(len(quality_scores), 1), 4) if quality_scores else None,
            "language_distribution": languages,
            "exported_at": datetime.now(timezone.utc).isoformat(),
        }
