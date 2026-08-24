"""Unit tests for Phase 2 feasibility analysis."""

from __future__ import annotations
import uuid

import json
from unittest.mock import MagicMock, patch

import pytest

from data_fetcher.database import Database
from data_fetcher.models import (
    DatasetSpecification,
    FeasibilityReport,
    FeasibilityStageResult,
    NormalizedDocument,
)
from data_fetcher.phase2.feasibility import FeasibilityEngine, FeasibilityError
from data_fetcher.phase2.specification import DatasetSpecificationManager, SpecificationError


@pytest.fixture
def mock_db():
    return MagicMock(spec=Database)


@pytest.fixture
def spec_manager(mock_db):
    return DatasetSpecificationManager(mock_db)


@pytest.fixture
def engine(mock_db, spec_manager):
    return FeasibilityEngine(mock_db, spec_manager)


def _make_spec(overrides=None):
    spec = {
        "dataset": {"name": "test-dataset", "version": 1},
        "source": {
            "allowed_formats": ["html", "json"],
            "allowed_languages": ["English"],
        },
        "content": {"minimum_characters": 100, "maximum_characters": 10000},
        "quality": {"minimum_score": 0.3},
        "deduplication": {"mode": "normalized", "similarity_threshold": 0.85},
        "selection": {"maximum_records": 1000, "minimum_records": 10},
        "output": {"format": "jsonl"},
    }
    if overrides:
        spec.update(overrides)
    return spec


def _make_normalized_doc(overrides=None):
    doc = {
        "id": "nd-1",
        "canonical_document_id": "cd-1",
        "artifact_id": "a-1",
        "processing_job_id": "job-1",
        "source_url": "http://example.com/page.html",
        "detected_format": "html",
        "normalization_version": "1.0.0",
        "normalized_text": "This is a test document with enough characters to pass length filters." * 5,
        "original_checksum": "abc123",
        "normalized_checksum": "def456",
        "content_changed": False,
        "quality_signals": {
            "text_metrics": {"character_count": 350, "word_count": 60, "line_count": 5},
            "content_composition": {"alphabetic_ratio": 0.9},
            "repetition_signals": {"suspicious_repetition": False},
            "completeness_signals": {"is_empty": False, "is_short": False},
            "language": {"code": "English", "confidence": "high", "method": "bigram-profile", "method_version": "1.0.0", "warnings": [], "errors": []},
        },
        "warnings": [],
        "errors": [],
        "provenance": {},
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "source_mime_type": "text/html",
        "extraction_status": "completed",
        "canonical_checksum": "canon-abc",
        "canonical_quality_signals": {
            "text_metrics": {"character_count": 350},
        },
        "artifact_content_type": "text/html",
        "size_bytes": 500,
        "raw_checksum": "raw-abc",
    }
    if overrides:
        doc.update(overrides)
    return doc


class TestFeasibilityEngine:
    """Test FeasibilityEngine."""

    def test_feasibility_pass_scenario(self, engine, mock_db):
        spec = _make_spec({"selection": {"maximum_records": 1000}})
        mock_spec = DatasetSpecification(
            id="spec-1",
            name="test-dataset",
            version=1,
            specification_hash="hash123",
            canonical_specification=spec,
            status="draft",
            description=None,
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
        )
        mock_db.connect.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_db.connect.return_value.__exit__ = MagicMock(return_value=False)
        
        with patch.object(engine, '_get_all_normalized_documents', return_value=[_make_normalized_doc()]):
            report = engine.analyze(mock_spec)
        
        assert report.feasibility == "pass"
        assert report.eligible_count == 1
        assert report.records_considered == 1
        assert len(report.blockers) == 0

    def test_feasibility_fail_insufficient_records(self, engine, mock_db):
        spec = _make_spec({"selection": {"minimum_records": 100, "maximum_records": 1000}})
        mock_spec = DatasetSpecification(
            id="spec-1",
            name="test-dataset",
            version=1,
            specification_hash="hash123",
            canonical_specification=spec,
            status="draft",
            description=None,
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
        )
        
        with patch.object(engine, '_get_all_normalized_documents', return_value=[_make_normalized_doc()]):
            report = engine.analyze(mock_spec)
        
        assert report.feasibility == "fail"
        assert len(report.blockers) > 0
        assert any("minimum" in b.lower() for b in report.blockers)

    def test_feasibility_blocked_no_documents(self, engine, mock_db):
        spec = _make_spec()
        mock_spec = DatasetSpecification(
            id="spec-1",
            name="test-dataset",
            version=1,
            specification_hash="hash123",
            canonical_specification=spec,
            status="draft",
            description=None,
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
        )
        
        with patch.object(engine, '_get_all_normalized_documents', return_value=[]):
            report = engine.analyze(mock_spec)
        
        assert report.feasibility == "blocked"
        assert any("No normalized documents" in b for b in report.blockers)

    def test_format_filtering(self, engine):
        spec = _make_spec({"source": {"allowed_formats": ["json"]}})
        html_doc = _make_normalized_doc({"detected_format": "html", "artifact_content_type": "text/html"})
        json_doc = _make_normalized_doc({"detected_format": "json", "artifact_content_type": "application/json", "id": "nd-2"})
        
        passed, rejections = engine._apply_format_filter(spec, [html_doc, json_doc])
        
        assert len(passed) == 1
        assert passed[0]["id"] == "nd-2"
        assert sum(rejections.values()) == 1

    def test_language_filtering(self, engine):
        spec = _make_spec({"source": {"allowed_languages": ["English", "Spanish"]}})
        en_doc = _make_normalized_doc()
        es_doc = _make_normalized_doc({
            "id": "nd-2",
            "quality_signals": {
                "language": {"code": "Spanish", "confidence": "high", "method": "bigram-profile", "method_version": "1.0.0", "warnings": [], "errors": []},
                "text_metrics": {"character_count": 300},
            }
        })
        fr_doc = _make_normalized_doc({
            "id": "nd-3",
            "quality_signals": {
                "language": {"code": "French", "confidence": "high", "method": "bigram-profile", "method_version": "1.0.0", "warnings": [], "errors": []},
                "text_metrics": {"character_count": 300},
            }
        })
        
        passed, rejections = engine._apply_language_filter(spec, [en_doc, es_doc, fr_doc])
        
        assert len(passed) == 2
        assert sum(rejections.values()) == 1

    def test_length_filtering(self, engine):
        spec = _make_spec({"content": {"minimum_characters": 200, "maximum_characters": 5000}})
        short_doc = _make_normalized_doc({"normalized_text": "Short"})
        long_doc = _make_normalized_doc({"normalized_text": "x" * 6000, "id": "nd-2"})
        ok_doc = _make_normalized_doc({"normalized_text": "x" * 500, "id": "nd-3"})
        
        passed, rejections = engine._apply_length_filter(spec, [short_doc, long_doc, ok_doc])
        
        assert len(passed) == 1
        assert passed[0]["id"] == "nd-3"
        assert sum(rejections.values()) == 2

    def test_quality_filtering(self, engine):
        spec = _make_spec({"quality": {"minimum_score": 0.3}})
        good_doc = _make_normalized_doc({
            "canonical_quality_signals": {"text_metrics": {"character_count": 500}}
        })
        bad_doc = _make_normalized_doc({
            "id": "nd-2",
            "canonical_quality_signals": {"text_metrics": {"character_count": 100}}
        })
        
        passed, rejections = engine._apply_quality_filter(spec, [good_doc, bad_doc])
        
        assert len(passed) == 1
        assert passed[0]["id"] == "nd-1"
        assert sum(rejections.values()) == 1

    def test_dedup_impact_estimation(self, engine):
        spec = _make_spec({"deduplication": {"mode": "normalized", "similarity_threshold": 0.85}})
        doc1 = _make_normalized_doc({"normalized_checksum": "checksum-a"})
        doc2 = _make_normalized_doc({"normalized_checksum": "checksum-a", "id": "nd-2"})
        doc3 = _make_normalized_doc({"normalized_checksum": "checksum-b", "id": "nd-3"})
        
        passed, impact = engine._apply_dedup_filter(spec, [doc1, doc2, doc3])
        
        assert impact["mode"] == "normalized"
        assert impact["estimated_duplicate_count"] == 1
        assert impact["estimated_group_count"] == 1

    def test_dedup_none_mode(self, engine):
        spec = _make_spec({"deduplication": {"mode": "none"}})
        docs = [_make_normalized_doc(), _make_normalized_doc({"id": "nd-2"})]
        
        passed, impact = engine._apply_dedup_filter(spec, docs)
        
        assert impact["mode"] == "none"
        assert impact["estimated_duplicate_count"] == 0
        assert len(passed) == 2

    def test_stage_by_stage_reporting(self, engine):
        spec = _make_spec()
        mock_spec = DatasetSpecification(
            id="spec-1",
            name="test-dataset",
            version=1,
            specification_hash="hash123",
            canonical_specification=spec,
            status="draft",
            description=None,
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
        )
        docs = [_make_normalized_doc()]
        with patch.object(engine, '_get_all_normalized_documents', return_value=docs):
            report = engine.analyze(mock_spec)
        
        stages = engine._last_stages
        assert len(stages) == 5
        assert stages[0].stage == "format"
        assert stages[1].stage == "language"
        assert stages[2].stage == "length"
        assert stages[3].stage == "quality"
        assert stages[4].stage == "dedup"

    def test_blockers_and_warnings(self, engine, mock_db):
        spec = _make_spec({"selection": {"maximum_records": 1}, "source": {"allowed_languages": []}})
        mock_spec = DatasetSpecification(
            id="spec-1",
            name="test-dataset",
            version=1,
            specification_hash="hash123",
            canonical_specification=spec,
            status="draft",
            description=None,
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
        )
        doc1 = _make_normalized_doc()
        doc2 = _make_normalized_doc({"id": "nd-2"})
        with patch.object(engine, '_get_all_normalized_documents', return_value=[doc1, doc2]):
            report = engine.analyze(mock_spec)
        
        assert any("exceeds maximum" in w for w in report.warnings)

    def test_language_distribution(self, engine):
        spec = _make_spec({"source": {"allowed_languages": ["English", "Spanish"]}})
        en_doc = _make_normalized_doc()
        es_doc = _make_normalized_doc({
            "id": "nd-2",
            "quality_signals": {
                "language": {"code": "Spanish", "confidence": "high", "method": "bigram-profile", "method_version": "1.0.0", "warnings": [], "errors": []},
                "text_metrics": {"character_count": 300},
            }
        })
        
        dist = engine._compute_language_distribution([en_doc, es_doc])
        assert dist.get("English") == 1
        assert dist.get("Spanish") == 1

    def test_quality_distribution(self, engine):
        docs = [_make_normalized_doc(), _make_normalized_doc({"id": "nd-2"})]
        dist = engine._compute_quality_distribution(docs)
        assert dist["count"] == 2
        assert dist["avg_character_count"] > 0

    def test_estimate_output_size(self, engine):
        doc = _make_normalized_doc({"normalized_text": "x" * 100})
        size = engine._estimate_output_size([doc])
        assert size == 100

    def test_no_language_rules_passes_all(self, engine):
        spec = _make_spec({"source": {"allowed_formats": ["html"], "allowed_languages": []}})
        en_doc = _make_normalized_doc()
        es_doc = _make_normalized_doc({
            "id": "nd-2",
            "quality_signals": {
                "language": {"code": "Spanish", "confidence": "high", "method": "bigram-profile", "method_version": "1.0.0", "warnings": [], "errors": []},
                "text_metrics": {"character_count": 300},
            }
        })
        
        passed, rejections = engine._apply_language_filter(spec, [en_doc, es_doc])
        assert len(passed) == 2
        assert len(rejections) == 0


@pytest.fixture
def db():
    from data_fetcher.config import load_config
    cfg = load_config()
    return Database(cfg.postgres_dsn)


class TestDatabaseFeasibilityMethods:
    """Test database feasibility report methods."""

    def _create_spec(self, db):
        import uuid
        from data_fetcher.models import DatasetSpecification
        name = f"feasibility-test-spec-{uuid.uuid4().hex[:8]}"
        return db.create_dataset_specification(
            name=name,
            version=1,
            specification_hash="test-hash",
            canonical_specification={"dataset": {"name": name, "version": 1}},
            status="draft",
            description="Test spec for feasibility",
        )

    def test_create_feasibility_report(self, db):
        spec = self._create_spec(db)
        from data_fetcher.models import FeasibilityReport
        report = FeasibilityReport(
            id="",
            specification_id=spec.id,
            specification_hash="hash123",
            source_snapshot="current",
            records_considered=100,
            eligible_count=50,
            rejection_counts={"format:unknown": 50},
            language_distribution={"English": 50},
            quality_distribution={"count": 50, "avg_character_count": 500},
            dedup_impact={"mode": "normalized", "estimated_groups": 45, "estimated_duplicate_count": 5},
            blockers=[],
            warnings=[],
            feasibility="pass",
            estimated_output_size_bytes=25000,
            created_at="",
        )
        saved = db.create_feasibility_report(report)
        assert saved.id is not None
        assert saved.specification_id == spec.id
        assert saved.eligible_count == 50

    def test_get_feasibility_report(self, db):
        spec = self._create_spec(db)
        saved = db.create_feasibility_report(
            FeasibilityReport(
                id="", specification_id=spec.id, specification_hash="h1",
                source_snapshot="current", records_considered=10, eligible_count=5,
                rejection_counts={}, language_distribution={}, quality_distribution={},
                dedup_impact={}, blockers=[], warnings=[], feasibility="pass",
                estimated_output_size_bytes=1000, created_at="",
            )
        )
        retrieved = db.get_feasibility_report(saved.id)
        assert retrieved is not None
        assert retrieved.id == saved.id
        assert retrieved.eligible_count == 5

    def test_get_feasibility_report_not_found(self, db):
        result = db.get_feasibility_report("00000000-0000-0000-0000-000000000000")
        assert result is None

    def test_list_feasibility_reports(self, db):
        spec1 = self._create_spec(db)
        spec2 = db.create_dataset_specification(
            name=f"feasibility-test-spec-2-{uuid.uuid4().hex[:8]}",
            version=1,
            specification_hash="test-hash-2",
            canonical_specification={"dataset": {"name": f"feasibility-test-spec-2-{uuid.uuid4().hex[:8]}", "version": 1}},
            status="draft",
            description="Test spec 2",
        )
        db.create_feasibility_report(
            FeasibilityReport(
                id="", specification_id=spec1.id, specification_hash="h1",
                source_snapshot="current", records_considered=10, eligible_count=5,
                rejection_counts={}, language_distribution={}, quality_distribution={},
                dedup_impact={}, blockers=[], warnings=[], feasibility="pass",
                estimated_output_size_bytes=1000, created_at="",
            )
        )
        db.create_feasibility_report(
            FeasibilityReport(
                id="", specification_id=spec2.id, specification_hash="h2",
                source_snapshot="current", records_considered=20, eligible_count=15,
                rejection_counts={}, language_distribution={}, quality_distribution={},
                dedup_impact={}, blockers=[], warnings=[], feasibility="pass",
                estimated_output_size_bytes=5000, created_at="",
            )
        )
        reports = db.list_feasibility_reports(specification_id=spec1.id)
        assert len(reports) == 1
        reports_spec2 = db.list_feasibility_reports(specification_id=spec2.id)
        assert len(reports_spec2) == 1

    def test_list_feasibility_reports_filtered(self, db):
        spec = self._create_spec(db)
        db.create_feasibility_report(
            FeasibilityReport(
                id="", specification_id=spec.id, specification_hash="h1",
                source_snapshot="current", records_considered=10, eligible_count=5,
                rejection_counts={}, language_distribution={}, quality_distribution={},
                dedup_impact={}, blockers=[], warnings=[], feasibility="pass",
                estimated_output_size_bytes=1000, created_at="",
            )
        )
        db.create_feasibility_report(
            FeasibilityReport(
                id="", specification_id=spec.id, specification_hash="h1-2",
                source_snapshot="current", records_considered=15, eligible_count=8,
                rejection_counts={}, language_distribution={}, quality_distribution={},
                dedup_impact={}, blockers=[], warnings=[], feasibility="fail",
                estimated_output_size_bytes=2000, created_at="",
            )
        )
        reports = db.list_feasibility_reports(specification_id=spec.id)
        assert len(reports) == 2
        reports_other = db.list_feasibility_reports(specification_id="87654321-4321-4321-4321-cba987654321")
        assert len(reports_other) == 0
