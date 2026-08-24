"""Unit tests for Phase 2 dataset builder."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from data_fetcher.database import Database
from data_fetcher.models import (
    DatasetBuild,
    DatasetRecord,
    DatasetSpecification,
    DecisionRecord,
)
from data_fetcher.phase2.dataset_builder import DatasetBuilder, DatasetBuilderError
from data_fetcher.phase2.specification import DatasetSpecificationManager


@pytest.fixture
def mock_db():
    return MagicMock(spec=Database)


@pytest.fixture
def spec_manager(mock_db):
    return DatasetSpecificationManager(mock_db)


@pytest.fixture
def builder(mock_db, spec_manager):
    return DatasetBuilder(mock_db, spec_manager)


def _make_spec(overrides: dict | None = None) -> dict:
    spec = {
        "dataset": {"name": "test-dataset", "version": 1},
        "source": {
            "allowed_formats": ["html", "json"],
            "allowed_languages": ["English"],
        },
        "content": {"minimum_characters": 100, "maximum_characters": 10000},
        "quality": {"minimum_score": 0.5},
        "deduplication": {"mode": "none"},
        "selection": {"maximum_records": 1000},
        "output": {"format": "jsonl"},
    }
    if overrides:
        spec.update(overrides)
    return spec


def _make_dataset_spec(overrides: dict | None = None) -> DatasetSpecification:
    spec_dict = _make_spec(overrides)
    spec_manager = DatasetSpecificationManager(MagicMock(spec=Database))
    spec_hash = spec_manager.compute_hash(spec_dict)
    return DatasetSpecification(
        id="spec-123",
        name="test-dataset",
        version=1,
        specification_hash=spec_hash,
        canonical_specification=spec_dict,
        status="active",
        description=None,
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )


def _make_normalized_doc(overrides: dict | None = None) -> dict:
    doc = {
        "id": "nd-1",
        "canonical_document_id": "cd-1",
        "artifact_id": "a-1",
        "processing_job_id": "job-1",
        "source_url": "http://example.com/page.html",
        "detected_format": "html",
        "normalization_version": "1.0.0",
        "normalized_text": "This is a test document with enough characters to pass length filters. " * 5,
        "original_checksum": "abc123",
        "normalized_checksum": "def456",
        "content_changed": False,
        "quality_signals": {
            "text_metrics": {"character_count": 350, "word_count": 60, "line_count": 5},
            "content_composition": {"alphabetic_ratio": 0.9},
            "repetition_signals": {"suspicious_repetition": False},
            "completeness_signals": {"is_empty": False, "is_short": False},
            "language": {"code": "English", "confidence": "high", "method": "bigram-profile",
                         "method_version": "1.0.0", "warnings": [], "errors": []},
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
            "text_metrics": {"character_count": 600},
        },
        "artifact_content_type": "text/html",
        "size_bytes": 500,
        "raw_checksum": "raw-abc",
    }
    if overrides:
        doc.update(overrides)
    return doc


class TestLoadCandidates:
    def test_load_candidates_returns_rows(self, builder, mock_db):
        rows = [_make_normalized_doc()]
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [MagicMock()]
        mock_conn = MagicMock()
        mock_conn.__enter__.return_value = mock_conn
        mock_cur_ctx = MagicMock()
        mock_cur_ctx.__enter__.return_value = mock_cursor
        mock_conn.cursor.return_value = mock_cur_ctx
        mock_cursor.fetchall.return_value = [
            {
                "id": "nd-1",
                "canonical_document_id": "cd-1",
                "artifact_id": "a-1",
                "source_url": "http://example.com",
                "detected_format": "html",
                "normalized_text": "text",
                "normalized_checksum": "def456",
                "canonical_checksum": "canon-abc",
                "canonical_quality_signals": {"text_metrics": {"character_count": 100}},
                "quality_signals": {"language": {"code": "English"}},
                "warnings": [],
                "errors": [],
                "size_bytes": 500,
                "raw_checksum": "raw-abc",
                "extraction_status": "completed",
                "artifact_content_type": "text/html",
            }
        ]
        mock_db.connect.return_value.__enter__.return_value = mock_conn
        candidates = builder._load_candidates(_make_dataset_spec())
        assert len(candidates) == 1
        assert candidates[0]["id"] == "nd-1"


class TestApplyRules:
    def test_accepted_record_passes_all_filters(self, builder):
        spec = _make_spec()
        candidates = [_make_normalized_doc()]
        accepted, rejected = builder._apply_rules(spec, candidates)
        assert len(accepted) == 1
        assert len(rejected) == 0
        assert accepted[0]["_reason_codes"] == []

    def test_wrong_language_rejected(self, builder):
        spec = _make_spec()
        doc = _make_normalized_doc({
            "id": "nd-2",
            "quality_signals": {
                "language": {"code": "Spanish", "confidence": "high", "method": "bigram-profile",
                             "method_version": "1.0.0", "warnings": [], "errors": []},
            },
            "canonical_quality_signals": {"text_metrics": {"character_count": 350}},
        })
        accepted, rejected = builder._apply_rules(spec, [doc])
        assert len(accepted) == 0
        assert len(rejected) == 1
        assert "wrong_language" in rejected[0]["_reason_codes"]

    def test_quality_below_threshold_rejected(self, builder):
        spec = _make_spec({"quality": {"minimum_score": 0.5}})
        doc = _make_normalized_doc({
            "id": "nd-3",
            "canonical_quality_signals": {"text_metrics": {"character_count": 100}},
        })
        accepted, rejected = builder._apply_rules(spec, [doc])
        assert len(accepted) == 0
        assert len(rejected) == 1
        assert "quality_below_threshold" in rejected[0]["_reason_codes"]

    def test_content_too_short_rejected(self, builder):
        spec = _make_spec({"content": {"minimum_characters": 500, "maximum_characters": 10000}})
        doc = _make_normalized_doc({"normalized_text": "short text here"})
        accepted, rejected = builder._apply_rules(spec, [doc])
        assert len(accepted) == 0
        assert len(rejected) == 1
        assert "content_too_short" in rejected[0]["_reason_codes"]

    def test_content_too_long_rejected(self, builder):
        spec = _make_spec({"content": {"minimum_characters": 0, "maximum_characters": 10}})
        doc = _make_normalized_doc({"normalized_text": "x" * 100})
        accepted, rejected = builder._apply_rules(spec, [doc])
        assert len(accepted) == 0
        assert len(rejected) == 1
        assert "content_too_long" in rejected[0]["_reason_codes"]

    def test_unsupported_format_rejected(self, builder):
        spec = _make_spec({"source": {"allowed_formats": ["json"], "allowed_languages": ["English"]}})
        doc = _make_normalized_doc({"detected_format": "xml", "artifact_content_type": "application/xml"})
        accepted, rejected = builder._apply_rules(spec, [doc])
        assert len(accepted) == 0
        assert len(rejected) == 1
        assert "unsupported_format" in rejected[0]["_reason_codes"]

    def test_no_format_restriction_passes_all(self, builder):
        spec = _make_spec({"source": {"allowed_formats": [], "allowed_languages": ["English"]}})
        doc = _make_normalized_doc({"detected_format": "xml", "artifact_content_type": "application/xml"})
        accepted, rejected = builder._apply_rules(spec, [doc])
        assert len(accepted) == 1
        assert len(rejected) == 0

    def test_no_language_restriction_passes_all(self, builder):
        spec = _make_spec({"source": {"allowed_formats": ["html"], "allowed_languages": []}})
        doc = _make_normalized_doc({
            "quality_signals": {"language": {"code": "French"}},
        })
        accepted, rejected = builder._apply_rules(spec, [doc])
        assert len(accepted) == 1
        assert len(rejected) == 0

    def test_no_quality_threshold_passes_all(self, builder):
        spec = _make_spec({"quality": {"minimum_score": None}})
        doc = _make_normalized_doc({
            "canonical_quality_signals": {"text_metrics": {"character_count": 10}},
        })
        accepted, rejected = builder._apply_rules(spec, [doc])
        assert len(accepted) == 1
        assert len(rejected) == 0

    def test_multiple_rejection_reasons(self, builder):
        spec = _make_spec({"quality": {"minimum_score": 0.5}})
        doc = _make_normalized_doc({
            "id": "nd-bad",
            "detected_format": "xml",
            "artifact_content_type": "application/xml",
            "quality_signals": {"language": {"code": "French"}},
            "canonical_quality_signals": {"text_metrics": {"character_count": 10}},
            "normalized_text": "short",
        })
        accepted, rejected = builder._apply_rules(spec, [doc])
        assert len(accepted) == 0
        assert len(rejected) == 1
        assert "unsupported_format" in rejected[0]["_reason_codes"]
        assert "wrong_language" in rejected[0]["_reason_codes"]
        assert "content_too_short" in rejected[0]["_reason_codes"]
        assert "quality_below_threshold" in rejected[0]["_reason_codes"]

    def test_record_limit_reached(self, builder):
        spec = _make_spec({"selection": {"maximum_records": 2}})
        docs = [_make_normalized_doc({
            "id": f"nd-{i}",
            "normalized_text": "x" * 300,
            "canonical_quality_signals": {"text_metrics": {"character_count": 600}},
        }) for i in range(5)]
        accepted, rejected = builder._apply_rules(spec, docs)
        assert len(accepted) == 2
        assert len(rejected) == 3
        for r in rejected:
            assert "record_limit_reached" in r["_reason_codes"]

    def test_dedup_mode_none_skips_dedup(self, builder):
        spec = _make_spec({"deduplication": {"mode": "none"}})
        docs = [_make_normalized_doc({"id": f"nd-{i}"}) for i in range(3)]
        accepted, rejected = builder._apply_rules(spec, docs)
        assert len(accepted) == 3
        assert len(rejected) == 0


class TestSelectRepresentatives:
    def test_none_mode_returns_all(self, builder):
        spec = _make_spec({"deduplication": {"mode": "none"}})
        candidates = [_make_normalized_doc({"id": f"nd-{i}"}) for i in range(3)]
        result = builder._select_representatives(spec, candidates)
        assert len(result) == 3

    def test_empty_candidates_returns_empty(self, builder):
        spec = _make_spec({"deduplication": {"mode": "normalized", "similarity_threshold": 0.85}})
        result = builder._select_representatives(spec, [])
        assert result == []


class TestBuildEndToEnd:
    def test_build_success(self, builder, mock_db, spec_manager):
        spec = _make_dataset_spec()

        mock_db.create_dataset_build.return_value = DatasetBuild(
            id="build-123",
            specification_id=spec.id,
            specification_hash=spec.specification_hash,
            status="building",
            records_considered=0,
            records_accepted=0,
            records_rejected=0,
            started_at="2026-01-01T00:00:00Z",
            finished_at=None,
            error_message=None,
        )
        mock_db.create_dataset_record.return_value = DatasetRecord(
            id="rec-1",
            build_id="build-123",
            specification_id=spec.id,
            source_record_id="nd-1",
            normalized_record_id="nd-1",
            canonical_record_id="cd-1",
            raw_artifact_id="a-1",
            source_url="http://example.com/page.html",
            text="test text",
            language="English",
            quality_score=0.35,
            dedup_group_id=None,
            selection_reason="accepted",
            created_at="2026-01-01T00:00:00Z",
        )
        mock_db.create_decision_record.return_value = DecisionRecord(
            id="dec-1",
            build_id="build-123",
            record_id="nd-1",
            decision="accepted",
            reason_codes=["accepted"],
            actual_values={},
            thresholds={},
            representative_record_id=None,
            source_url="http://example.com/page.html",
            created_at="2026-01-01T00:00:00Z",
        )
        mock_db.get_dataset_build.return_value = DatasetBuild(
            id="build-123",
            specification_id=spec.id,
            specification_hash=spec.specification_hash,
            status="accepted",
            records_considered=1,
            records_accepted=1,
            records_rejected=0,
            started_at="2026-01-01T00:00:00Z",
            finished_at="2026-01-01T00:00:00Z",
            error_message=None,
        )

        with patch.object(builder, '_load_candidates', return_value=[_make_normalized_doc()]):
            result = builder.build(spec)

        assert result.build.status == "accepted"
        assert len(result.accepted) == 1
        assert result.statistics["records_considered"] == 1
        assert result.statistics["records_accepted"] == 1
        assert result.statistics["records_rejected"] == 0

    def test_build_updates_status_on_failure(self, builder, mock_db):
        spec = _make_dataset_spec()
        mock_db.create_dataset_build.return_value = DatasetBuild(
            id="build-fail",
            specification_id=spec.id,
            specification_hash=spec.specification_hash,
            status="building",
            records_considered=0,
            records_accepted=0,
            records_rejected=0,
            started_at="2026-01-01T00:00:00Z",
            finished_at=None,
            error_message=None,
        )
        mock_db.get_dataset_build.return_value = DatasetBuild(
            id="build-fail",
            specification_id=spec.id,
            specification_hash=spec.specification_hash,
            status="failed",
            records_considered=0,
            records_accepted=0,
            records_rejected=0,
            started_at="2026-01-01T00:00:00Z",
            finished_at=None,
            error_message="test error",
        )

        with patch.object(builder, '_load_candidates', side_effect=Exception("DB failure")):
            with pytest.raises(DatasetBuilderError) as exc_info:
                builder.build(spec)
            assert exc_info.value.category == "build_failed"
            mock_db.update_dataset_build_status.assert_called()


class TestDecisionRecordPersistence:
    def test_decision_record_has_reason_codes(self, builder):
        spec = _make_spec()
        doc = _make_normalized_doc({
            "id": "nd-bad",
            "detected_format": "xml",
            "artifact_content_type": "application/xml",
            "quality_signals": {"language": {"code": "French"}},
            "canonical_quality_signals": {"text_metrics": {"character_count": 10}},
            "normalized_text": "short",
        })
        accepted, rejected = builder._apply_rules(spec, [doc])
        assert len(rejected) == 1
        assert rejected[0]["_reason_codes"] == ["unsupported_format", "wrong_language",
                                                  "content_too_short", "quality_below_threshold"]
        assert rejected[0]["_actual_values"]["detected_format"] == "xml"
