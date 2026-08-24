"""Integration tests for Phase 2 dataset builder database methods."""

from __future__ import annotations

import uuid

import pytest

from data_fetcher.config import load_config
from data_fetcher.database import Database
from data_fetcher.models import (
    DatasetBuild,
    DecisionRecord,
    DatasetRecord,
    ValidationReport,
)


@pytest.fixture
def db():
    cfg = load_config()
    return Database(cfg.postgres_dsn)


class TestDatasetBuildDB:
    """Test dataset_builds table operations."""

    def _create_spec(self, db):
        name = f"builder-db-spec-{uuid.uuid4().hex[:8]}"
        return db.create_dataset_specification(
            name=name,
            version=1,
            specification_hash=f"hash-{uuid.uuid4().hex[:8]}",
            canonical_specification={"dataset": {"name": name, "version": 1}},
            status="active",
            description="Test spec for builder DB tests",
        )

    def test_create_dataset_build(self, db):
        spec = self._create_spec(db)
        build = db.create_dataset_build(
            specification_id=spec.id,
            specification_hash=spec.specification_hash,
            status="building",
            records_considered=0,
            records_accepted=0,
            records_rejected=0,
            error_message=None,
        )
        assert build.id is not None
        assert build.specification_id == spec.id
        assert build.status == "building"
        assert build.records_considered == 0

    def test_get_dataset_build(self, db):
        spec = self._create_spec(db)
        build = db.create_dataset_build(
            specification_id=spec.id,
            specification_hash=spec.specification_hash,
            status="building",
            records_considered=0,
            records_accepted=0,
            records_rejected=0,
            error_message=None,
        )
        retrieved = db.get_dataset_build(build.id)
        assert retrieved is not None
        assert retrieved.id == build.id
        assert retrieved.status == "building"

    def test_get_dataset_build_not_found(self, db):
        result = db.get_dataset_build("00000000-0000-0000-0000-000000000000")
        assert result is None

    def test_update_dataset_build_status(self, db):
        spec = self._create_spec(db)
        build = db.create_dataset_build(
            specification_id=spec.id,
            specification_hash=spec.specification_hash,
            status="building",
            records_considered=10,
            records_accepted=0,
            records_rejected=0,
            error_message=None,
        )
        db.update_dataset_build_status(
            build_id=build.id,
            status="accepted",
            records_considered=10,
            records_accepted=8,
            records_rejected=2,
        )
        updated = db.get_dataset_build(build.id)
        assert updated.status == "accepted"
        assert updated.records_accepted == 8
        assert updated.records_rejected == 2

    def test_update_dataset_build_status_building(self, db):
        spec = self._create_spec(db)
        build = db.create_dataset_build(
            specification_id=spec.id,
            specification_hash=spec.specification_hash,
            status="draft",
            records_considered=0,
            records_accepted=0,
            records_rejected=0,
            error_message=None,
        )
        db.update_dataset_build_status(build_id=build.id, status="building")
        updated = db.get_dataset_build(build.id)
        assert updated.status == "building"


class TestDatasetRecordDB:
    def _create_build(self, db):
        name = f"record-test-spec-{uuid.uuid4().hex[:8]}"
        spec = db.create_dataset_specification(
            name=name, version=1, specification_hash="h1",
            canonical_specification={"dataset": {"name": name, "version": 1}},
            status="active", description=None,
        )
        return db.create_dataset_build(
            specification_id=spec.id,
            specification_hash=spec.specification_hash,
            status="building",
            records_considered=0,
            records_accepted=0,
            records_rejected=0,
            error_message=None,
        )

    def test_create_and_get_dataset_records(self, db):
        build = self._create_build(db)
        record = DatasetRecord(
            id="", build_id=build.id, specification_id=build.specification_id,
            source_record_id="00000000-0000-0000-0000-000000000001",
            normalized_record_id="00000000-0000-0000-0000-000000000002",
            canonical_record_id="00000000-0000-0000-0000-000000000003",
            raw_artifact_id="00000000-0000-0000-0000-000000000004",
            source_url="http://example.com", text="test text", language="English",
            quality_score=0.8, dedup_group_id=None, selection_reason="accepted",
            created_at="2026-01-01T00:00:00Z",
        )
        saved = db.create_dataset_record(record)
        assert saved.id is not None

        records = db.get_dataset_records(build.id)
        assert len(records) == 1
        assert records[0].source_url == "http://example.com"
        assert records[0].quality_score == 0.8


class TestDecisionRecordDB:
    def _create_build(self, db):
        name = f"decision-test-spec-{uuid.uuid4().hex[:8]}"
        spec = db.create_dataset_specification(
            name=name, version=1, specification_hash="h1",
            canonical_specification={"dataset": {"name": name, "version": 1}},
            status="active", description=None,
        )
        return db.create_dataset_build(
            specification_id=spec.id,
            specification_hash=spec.specification_hash,
            status="building",
            records_considered=0,
            records_accepted=0,
            records_rejected=0,
            error_message=None,
        )

    def test_create_and_get_decision_records(self, db):
        build = self._create_build(db)
        decision = DecisionRecord(
            id="", build_id=build.id, record_id="00000000-0000-0000-0000-000000000001",
            decision="rejected", reason_codes=["wrong_language"],
            actual_values={"language": "French"}, thresholds={"min_score": 0.5},
            representative_record_id=None, source_url="http://example.com",
            created_at="2026-01-01T00:00:00Z",
        )
        saved = db.create_decision_record(decision)
        assert saved.id is not None
        assert saved.decision == "rejected"
        assert "wrong_language" in saved.reason_codes

        decisions = db.get_decision_records(build.id)
        assert len(decisions) == 1
        assert decisions[0].decision == "rejected"


class TestValidationReportDB:
    def _create_build(self, db):
        name = f"validation-test-spec-{uuid.uuid4().hex[:8]}"
        spec = db.create_dataset_specification(
            name=name, version=1, specification_hash="h1",
            canonical_specification={"dataset": {"name": name, "version": 1}},
            status="active", description=None,
        )
        return db.create_dataset_build(
            specification_id=spec.id,
            specification_hash=spec.specification_hash,
            status="building",
            records_considered=0,
            records_accepted=0,
            records_rejected=0,
            error_message=None,
        )

    def test_create_and_get_validation_report(self, db):
        build = self._create_build(db)
        report = ValidationReport(
            id="", build_id=build.id, status="pass", overall_status="valid",
            checks=[{"check_name": "test", "severity": "info", "passed": True,
                     "message": "ok", "details": {}}],
            error_count=0, warning_count=0, info_count=1,
            created_at="2026-01-01T00:00:00Z",
        )
        saved = db.create_validation_report(report)
        assert saved.id is not None
        assert saved.status == "pass"

        reports = db.get_validation_reports(build.id)
        assert len(reports) == 1
        assert reports[0].overall_status == "valid"
