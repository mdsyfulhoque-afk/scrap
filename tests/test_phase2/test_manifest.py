"""Unit tests for Phase 2 manifest generation."""

from __future__ import annotations

import hashlib
import json
from unittest.mock import MagicMock

import pytest

from data_fetcher.models import (
    DatasetBuild,
    DatasetRecord,
    DatasetSpecification,
    ValidationReport,
)
from data_fetcher.phase2.manifest import ManifestBuilder, PIPELINE_VERSION


def _make_build() -> DatasetBuild:
    return DatasetBuild(
        id="build-123",
        specification_id="spec-1",
        specification_hash="abc123hash",
        status="accepted",
        records_considered=100,
        records_accepted=80,
        records_rejected=20,
        started_at="2026-01-01T00:00:00Z",
        finished_at="2026-01-01T00:01:00Z",
        error_message=None,
    )


def _make_spec() -> DatasetSpecification:
    spec_dict = {
        "dataset": {"name": "my-dataset", "version": 1},
        "output": {"format": "jsonl"},
    }
    from data_fetcher.phase2.specification import DatasetSpecificationManager
    sm = DatasetSpecificationManager(MagicMock())
    return DatasetSpecification(
        id="spec-1",
        name="my-dataset",
        version=1,
        specification_hash=sm.compute_hash(spec_dict),
        canonical_specification=spec_dict,
        status="active",
        description="Test dataset",
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
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


def _make_validation() -> ValidationReport:
    return ValidationReport(
        id="val-1",
        build_id="build-123",
        status="pass",
        overall_status="valid",
        checks=[
            {"check_name": "schema_validity", "severity": "error", "passed": True, "message": "ok", "details": {}},
        ],
        error_count=0,
        warning_count=0,
        info_count=1,
        created_at="2026-01-01T00:01:00Z",
    )


class TestManifestBuilder:
    def test_manifest_has_required_fields(self):
        builder = ManifestBuilder()
        manifest = builder.build(_make_build(), _make_spec(), _make_records(2))
        assert manifest["dataset_name"] == "my-dataset"
        assert manifest["dataset_version"] == 1
        assert manifest["dataset_build_id"] == "build-123"
        assert manifest["dataset_spec_hash"] == "abc123hash"
        assert manifest["pipeline_version"] == PIPELINE_VERSION
        assert manifest["source_snapshot"] == f"spec-{_make_build().specification_hash[:12]}"
        assert "created_at" in manifest
        assert manifest["records_considered"] == 100
        assert manifest["records_accepted"] == 2
        assert manifest["records_rejected"] == 20

    def test_manifest_export_format_from_spec(self):
        builder = ManifestBuilder()
        spec = _make_spec()
        manifest = builder.build(_make_build(), spec, _make_records(1))
        assert manifest["export_format"] == "jsonl"

    def test_manifest_with_validation(self):
        builder = ManifestBuilder()
        val = _make_validation()
        manifest = builder.build(_make_build(), _make_spec(), _make_records(2), validation=val)
        assert manifest["validation_status"] == "pass"
        assert "validation_report" in manifest
        assert manifest["validation_report"]["status"] == "pass"

    def test_manifest_without_validation(self):
        builder = ManifestBuilder()
        manifest = builder.build(_make_build(), _make_spec(), _make_records(2))
        assert manifest["validation_status"] == "not_validated"
        assert "validation_report" not in manifest

    def test_manifest_specification_section(self):
        builder = ManifestBuilder()
        spec = _make_spec()
        manifest = builder.build(_make_build(), spec, _make_records(1))
        assert manifest["specification"]["name"] == "my-dataset"
        assert manifest["specification"]["version"] == 1
        assert manifest["specification"]["hash"] == spec.specification_hash
        assert manifest["specification"]["canonical_specification"] == spec.canonical_specification

    def test_manifest_build_section(self):
        builder = ManifestBuilder()
        build = _make_build()
        manifest = builder.build(build, _make_spec(), _make_records(1))
        assert manifest["build"]["id"] == "build-123"
        assert manifest["build"]["specification_id"] == "spec-1"
        assert manifest["build"]["status"] == "accepted"

    def test_manifest_record_checksums(self):
        builder = ManifestBuilder()
        records = _make_records(3)
        manifest = builder.build(_make_build(), _make_spec(), records)
        assert "record_checksums" in manifest
        assert manifest["record_checksums"]["canonical_record_count"] == 3
        assert "sha256" in manifest["record_checksums"]

    def test_manifest_record_count_matches(self):
        builder = ManifestBuilder()
        records = _make_records(5)
        manifest = builder.build(_make_build(), _make_spec(), records)
        assert manifest["records_accepted"] == 5

    def test_manifest_contains_pipeline_version(self):
        builder = ManifestBuilder()
        manifest = builder.build(_make_build(), _make_spec(), _make_records(1))
        assert "pipeline_version" in manifest
        assert isinstance(manifest["pipeline_version"], str)

    def test_manifest_serializable(self):
        builder = ManifestBuilder()
        manifest = builder.build(_make_build(), _make_spec(), _make_records(2), validation=_make_validation())
        json_str = json.dumps(manifest, default=str)
        parsed = json.loads(json_str)
        assert parsed["dataset_name"] == "my-dataset"
