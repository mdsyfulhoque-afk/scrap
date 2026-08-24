"""Unit tests for Phase 2 JSONL export package."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from data_fetcher.models import (
    DatasetBuild,
    DatasetRecord,
    DatasetSpecification,
    DecisionRecord,
    ExportResult,
    ValidationReport,
)
from data_fetcher.phase2.export import DatasetExporter, ExportError


def _make_build() -> DatasetBuild:
    return DatasetBuild(
        id="build-123",
        specification_id="spec-1",
        specification_hash="hash123",
        status="accepted",
        records_considered=100,
        records_accepted=80,
        records_rejected=20,
        started_at="2026-01-01T00:00:00Z",
        finished_at="2026-01-01T00:01:00Z",
        error_message=None,
    )


def _make_records(count: int = 3) -> list[DatasetRecord]:
    records = []
    for i in range(count):
        records.append(DatasetRecord(
            id=f"rec-{i}",
            build_id="build-123",
            specification_id="spec-1",
            source_record_id=f"nd-{i}",
            normalized_record_id=f"nd-{i}",
            canonical_record_id=f"cd-{i}",
            raw_artifact_id=f"art-{i}",
            source_url=f"http://example.com/{i}",
            text=f"Test document {i} with text content.",
            language="English",
            quality_score=0.8,
            dedup_group_id=None,
            selection_reason="accepted",
            created_at="2026-01-01T00:00:00Z",
        ))
    return records


def _make_decisions(count: int = 2) -> list[DecisionRecord]:
    decisions = []
    for i in range(count):
        decisions.append(DecisionRecord(
            id=f"dec-{i}",
            build_id="build-123",
            record_id=f"nd-{i}",
            decision="rejected",
            reason_codes=["wrong_language"],
            actual_values={"language": "French"},
            thresholds={"allowed_languages": ["English"]},
            representative_record_id=None,
            source_url=f"http://example.com/rej-{i}",
            created_at="2026-01-01T00:00:00Z",
        ))
    return decisions


def _make_validation() -> ValidationReport:
    return ValidationReport(
        id="val-1",
        build_id="build-123",
        status="pass",
        overall_status="valid",
        checks=[{"check_name": "schema_validity", "severity": "error", "passed": True,
                 "message": "ok", "details": {}}],
        error_count=0,
        warning_count=0,
        info_count=1,
        created_at="2026-01-01T00:01:00Z",
    )


class TestDatasetExporter:
    def test_export_creates_all_files(self, tmp_path):
        exporter = DatasetExporter()
        build = _make_build()
        records = _make_records(3)
        result = exporter.export(build, str(tmp_path), records=records)

        assert (tmp_path / "data.jsonl").exists()
        assert (tmp_path / "manifest.json").exists()
        assert (tmp_path / "statistics.json").exists()
        assert (tmp_path / "rejected.jsonl").exists()
        assert (tmp_path / "provenance.jsonl").exists()
        assert (tmp_path / "validation_report.json").exists()

    def test_export_returns_export_result(self, tmp_path):
        exporter = DatasetExporter()
        result = exporter.export(_make_build(), str(tmp_path), records=_make_records(3))
        assert isinstance(result, ExportResult)
        assert result.build_id == "build-123"
        assert result.accepted_count == 3
        assert result.rejected_count == 0

    def test_export_data_jsonl_content(self, tmp_path):
        exporter = DatasetExporter()
        records = _make_records(2)
        exporter.export(_make_build(), str(tmp_path), records=records)

        lines = (tmp_path / "data.jsonl").read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2
        for line in lines:
            obj = json.loads(line)
            assert "id" in obj
            assert "source_url" in obj
            assert "text" in obj

    def test_export_rejected_jsonl_content(self, tmp_path):
        exporter = DatasetExporter()
        decisions = _make_decisions(2)
        exporter.export(_make_build(), str(tmp_path),
                        records=[], rejected_decisions=decisions)

        lines = (tmp_path / "rejected.jsonl").read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2
        for line in lines:
            obj = json.loads(line)
            assert obj["decision"] == "rejected"
            assert "reason_codes" in obj

    def test_export_provenance_jsonl(self, tmp_path):
        exporter = DatasetExporter()
        records = _make_records(2)
        exporter.export(_make_build(), str(tmp_path), records=records)

        lines = (tmp_path / "provenance.jsonl").read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2
        for line in lines:
            obj = json.loads(line)
            assert "source_record_id" in obj
            assert "canonical_record_id" in obj
            assert "raw_artifact_id" in obj

    def test_export_manifest_json(self, tmp_path):
        exporter = DatasetExporter()
        build = _make_build()
        records = _make_records(3)
        exporter.export(build, str(tmp_path), records=records)

        manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["dataset_build_id"] == "build-123"
        assert manifest["records_accepted"] == 3

    def test_export_statistics_json(self, tmp_path):
        exporter = DatasetExporter()
        build = _make_build()
        records = _make_records(3)
        decisions = _make_decisions(2)
        exporter.export(build, str(tmp_path), records=records, rejected_decisions=decisions)

        stats = json.loads((tmp_path / "statistics.json").read_text(encoding="utf-8"))
        assert stats["records_accepted"] == 3
        assert stats["records_rejected"] == 2
        assert "total_characters" in stats
        assert "language_distribution" in stats
        assert "rejection_reason_counts" in stats

    def test_export_validation_report_json(self, tmp_path):
        exporter = DatasetExporter()
        validation = _make_validation()
        exporter.export(_make_build(), str(tmp_path),
                        records=[], validation=validation)

        report = json.loads((tmp_path / "validation_report.json").read_text(encoding="utf-8"))
        assert report["status"] == "pass"
        assert report["overall_status"] == "valid"
        assert "checks" in report

    def test_export_creates_output_dir(self, tmp_path):
        exporter = DatasetExporter()
        nested = tmp_path / "nested" / "output"
        exporter.export(_make_build(), str(nested), records=[])
        assert nested.exists()

    def test_export_with_manifest_param(self, tmp_path):
        exporter = DatasetExporter()
        manifest = {"custom": "manifest"}
        result = exporter.export(_make_build(), str(tmp_path),
                                 records=[], manifest=manifest)
        saved = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
        assert saved["custom"] == "manifest"

    def test_export_files_dict(self, tmp_path):
        exporter = DatasetExporter()
        result = exporter.export(_make_build(), str(tmp_path), records=_make_records(1))
        assert "data.jsonl" in result.files
        assert "manifest.json" in result.files
        assert "statistics.json" in result.files
        assert "rejected.jsonl" in result.files
        assert "provenance.jsonl" in result.files

    def test_export_empty_records(self, tmp_path):
        exporter = DatasetExporter()
        result = exporter.export(_make_build(), str(tmp_path), records=[])
        assert result.accepted_count == 0
        assert (tmp_path / "data.jsonl").exists()

    def test_export_files_returned_in_result(self, tmp_path):
        exporter = DatasetExporter()
        result = exporter.export(_make_build(), str(tmp_path), records=_make_records(2))
        assert "data.jsonl" in result.files
        assert result.files["data.jsonl"].endswith("data.jsonl")


class TestDatasetExporterFull:
    def test_full_export_with_manifest_and_validation(self, tmp_path):
        exporter = DatasetExporter()
        build = _make_build()
        records = _make_records(5)
        decisions = _make_decisions(3)
        validation = _make_validation()

        from data_fetcher.phase2.manifest import ManifestBuilder
        spec = DatasetSpecification(
            id="spec-1",
            name="test-dataset",
            version=1,
            specification_hash="hash123",
            canonical_specification={"dataset": {"name": "test-dataset", "version": 1},
                                     "output": {"format": "jsonl"}},
            status="active",
            description=None,
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
        )
        manifest_builder = ManifestBuilder()
        manifest = manifest_builder.build(build, spec, records, validation)

        result = exporter.export(
            build, str(tmp_path),
            records=records,
            rejected_decisions=decisions,
            validation=validation,
            manifest=manifest,
            specification=spec,
        )

        assert result.accepted_count == 5
        assert result.rejected_count == 3
        assert (tmp_path / "data.jsonl").exists()
        assert (tmp_path / "rejected.jsonl").exists()
        assert (tmp_path / "manifest.json").exists()
        assert (tmp_path / "statistics.json").exists()
        assert (tmp_path / "provenance.jsonl").exists()
        assert (tmp_path / "validation_report.json").exists()
