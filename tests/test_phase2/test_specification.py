"""Unit tests for Phase 2 dataset specifications."""

from __future__ import annotations

import hashlib
import json
from unittest.mock import MagicMock

import pytest

from data_fetcher.database import Database, DatabaseError
from data_fetcher.models import DatasetSpecification
from data_fetcher.phase2.specification import (
    DatasetSpecificationManager,
    SpecificationError,
    SpecificationValidator,
)


@pytest.fixture
def mock_db():
    return MagicMock(spec=Database)


@pytest.fixture
def validator():
    return SpecificationValidator()


@pytest.fixture
def manager(mock_db):
    return DatasetSpecificationManager(mock_db)


def _make_spec(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    spec: dict[str, Any] = {
        "dataset": {
            "name": "test-dataset",
            "version": 1,
        },
        "source": {
            "allowed_formats": ["html", "json"],
        },
        "content": {
            "minimum_characters": 100,
            "maximum_characters": 10000,
        },
        "quality": {
            "minimum_score": 0.5,
        },
        "deduplication": {
            "mode": "normalized",
            "similarity_threshold": 0.85,
        },
        "selection": {
            "maximum_records": 1000,
        },
        "output": {
            "format": "jsonl",
        },
    }
    if overrides:
        spec.update(overrides)
    return spec


class TestSpecificationValidator:
    """Test SpecificationValidator."""

    def test_valid_specification(self, validator):
        spec = _make_spec()
        errors = validator.validate(spec)
        assert errors == []

    def test_missing_dataset_section(self, validator):
        spec: dict[str, Any] = {}
        errors = validator.validate(spec)
        assert "Missing 'dataset' section" in errors

    def test_missing_name(self, validator):
        spec = _make_spec({"dataset": {"version": 1}})
        errors = validator.validate(spec)
        assert any("dataset.name" in e for e in errors)

    def test_empty_name(self, validator):
        spec = _make_spec({"dataset": {"name": "   ", "version": 1}})
        errors = validator.validate(spec)
        assert any("dataset.name" in e for e in errors)

    def test_non_string_name(self, validator):
        spec = _make_spec({"dataset": {"name": 123, "version": 1}})
        errors = validator.validate(spec)
        assert any("dataset.name" in e for e in errors)

    def test_invalid_version_zero(self, validator):
        spec = _make_spec({"dataset": {"name": "test", "version": 0}})
        errors = validator.validate(spec)
        assert any("dataset.version" in e for e in errors)

    def test_invalid_version_negative(self, validator):
        spec = _make_spec({"dataset": {"name": "test", "version": -1}})
        errors = validator.validate(spec)
        assert any("dataset.version" in e for e in errors)

    def test_invalid_version_float(self, validator):
        spec = _make_spec({"dataset": {"name": "test", "version": 1.5}})
        errors = validator.validate(spec)
        assert any("dataset.version" in e for e in errors)

    def test_invalid_allowed_format(self, validator):
        spec = _make_spec({"source": {"allowed_formats": ["html", "docx"]}})
        errors = validator.validate(spec)
        assert any("Unsupported format" in e for e in errors)

    def test_allowed_formats_not_list(self, validator):
        spec = _make_spec({"source": {"allowed_formats": "html"}})
        errors = validator.validate(spec)
        assert any("must be a list" in e for e in errors)

    def test_minimum_characters_negative(self, validator):
        spec = _make_spec({"content": {"minimum_characters": -1, "maximum_characters": 100}})
        errors = validator.validate(spec)
        assert any("minimum_characters must be >= 0" in e for e in errors)

    def test_maximum_characters_zero(self, validator):
        spec = _make_spec({"content": {"minimum_characters": 0, "maximum_characters": 0}})
        errors = validator.validate(spec)
        assert any("maximum_characters must be > 0" in e for e in errors)

    def test_maximum_characters_negative(self, validator):
        spec = _make_spec({"content": {"minimum_characters": 0, "maximum_characters": -1}})
        errors = validator.validate(spec)
        assert any("maximum_characters must be > 0" in e for e in errors)

    def test_min_greater_than_max(self, validator):
        spec = _make_spec({"content": {"minimum_characters": 1000, "maximum_characters": 100}})
        errors = validator.validate(spec)
        assert any("minimum_characters must be less than maximum_characters" in e for e in errors)

    def test_minimum_score_out_of_range_high(self, validator):
        spec = _make_spec({"quality": {"minimum_score": 1.5}})
        errors = validator.validate(spec)
        assert any("minimum_score must be between 0.0 and 1.0" in e for e in errors)

    def test_minimum_score_out_of_range_negative(self, validator):
        spec = _make_spec({"quality": {"minimum_score": -0.1}})
        errors = validator.validate(spec)
        assert any("minimum_score must be between 0.0 and 1.0" in e for e in errors)

    def test_minimum_score_string(self, validator):
        spec = _make_spec({"quality": {"minimum_score": "high"}})
        errors = validator.validate(spec)
        assert any("minimum_score must be a number" in e for e in errors)

    def test_invalid_deduplication_mode(self, validator):
        spec = _make_spec({"deduplication": {"mode": "fuzzy"}})
        errors = validator.validate(spec)
        assert any("Unsupported deduplication mode" in e for e in errors)

    def test_similarity_threshold_out_of_range(self, validator):
        spec = _make_spec({"deduplication": {"similarity_threshold": 1.5}})
        errors = validator.validate(spec)
        assert any("similarity_threshold must be between 0.0 and 1.0" in e for e in errors)

    def test_similarity_threshold_string(self, validator):
        spec = _make_spec({"deduplication": {"similarity_threshold": "high"}})
        errors = validator.validate(spec)
        assert any("similarity_threshold must be a number" in e for e in errors)

    def test_invalid_maximum_records(self, validator):
        spec = _make_spec({"selection": {"maximum_records": -1}})
        errors = validator.validate(spec)
        assert any("maximum_records must be a positive integer" in e for e in errors)

    def test_maximum_records_zero(self, validator):
        spec = _make_spec({"selection": {"maximum_records": 0}})
        errors = validator.validate(spec)
        assert any("maximum_records must be a positive integer" in e for e in errors)

    def test_invalid_output_format(self, validator):
        spec = _make_spec({"output": {"format": "excel"}})
        errors = validator.validate(spec)
        assert any("Unsupported output format" in e for e in errors)


class TestDatasetSpecificationManager:
    """Test DatasetSpecificationManager."""

    def test_create_specification_success(self, manager, mock_db):
        spec = _make_spec()
        mock_db.get_dataset_specification_by_name_version.return_value = None
        expected_hash = manager.compute_hash(spec)
        mock_db.create_dataset_specification.return_value = DatasetSpecification(
            id="spec-123",
            name="test-dataset",
            version=1,
            specification_hash=expected_hash,
            canonical_specification=spec,
            status="draft",
            description="test desc",
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
        )
        result = manager.create_specification("test-dataset", spec, description="test desc")
        assert result.name == "test-dataset"
        assert result.status == "draft"
        mock_db.create_dataset_specification.assert_called_once()
        call_args = mock_db.create_dataset_specification.call_args
        assert call_args.kwargs["name"] == "test-dataset"
        assert call_args.kwargs["status"] == "draft"

    def test_create_specification_validation_failure(self, manager):
        spec = _make_spec({"dataset": {"name": "", "version": 1}})
        with pytest.raises(SpecificationError) as exc_info:
            manager.create_specification("test-dataset", spec)
        assert exc_info.value.category == "validation_failed"

    def test_create_specification_duplicate_name_version(self, manager, mock_db):
        spec = _make_spec()
        mock_db.get_dataset_specification_by_name_version.return_value = DatasetSpecification(
            id="spec-123",
            name="test-dataset",
            version=1,
            specification_hash="abc",
            canonical_specification=spec,
            status="draft",
            description=None,
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
        )
        with pytest.raises(SpecificationError) as exc_info:
            manager.create_specification("test-dataset", spec)
        assert exc_info.value.category == "duplicate_name_version"

    def test_get_specification(self, manager, mock_db):
        mock_db.get_dataset_specification.return_value = DatasetSpecification(
            id="spec-123",
            name="test-dataset",
            version=1,
            specification_hash="abc",
            canonical_specification={},
            status="active",
            description=None,
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
        )
        result = manager.get_specification("spec-123")
        assert result is not None
        assert result.id == "spec-123"
        assert result.status == "active"

    def test_get_specification_not_found(self, manager, mock_db):
        mock_db.get_dataset_specification.return_value = None
        result = manager.get_specification("missing-id")
        assert result is None

    def test_list_specifications(self, manager, mock_db):
        mock_db.list_dataset_specifications.return_value = [
            DatasetSpecification(
                id="spec-1",
                name="ds1",
                version=1,
                specification_hash="h1",
                canonical_specification={},
                status="draft",
                description=None,
                created_at="2026-01-01T00:00:00Z",
                updated_at="2026-01-01T00:00:00Z",
            ),
            DatasetSpecification(
                id="spec-2",
                name="ds2",
                version=1,
                specification_hash="h2",
                canonical_specification={},
                status="active",
                description=None,
                created_at="2026-01-02T00:00:00Z",
                updated_at="2026-01-02T00:00:00Z",
            ),
        ]
        result = manager.list_specifications()
        assert len(result) == 2

    def test_list_specifications_filtered_by_status(self, manager, mock_db):
        mock_db.list_dataset_specifications.return_value = [
            DatasetSpecification(
                id="spec-1",
                name="ds1",
                version=1,
                specification_hash="h1",
                canonical_specification={},
                status="draft",
                description=None,
                created_at="2026-01-01T00:00:00Z",
                updated_at="2026-01-01T00:00:00Z",
            ),
        ]
        result = manager.list_specifications(status="draft")
        assert len(result) == 1
        mock_db.list_dataset_specifications.assert_called_once_with("draft")

    def test_compute_hash_deterministic(self, manager):
        spec = _make_spec()
        hash1 = manager.compute_hash(spec)
        hash2 = manager.compute_hash(spec)
        assert hash1 == hash2
        assert len(hash1) == 64

    def test_compute_hash_changes_with_content(self, manager):
        spec1 = _make_spec()
        spec2 = _make_spec({"content": {"minimum_characters": 200, "maximum_characters": 10000}})
        hash1 = manager.compute_hash(spec1)
        hash2 = manager.compute_hash(spec2)
        assert hash1 != hash2

    def test_compute_hash_sha256_format(self, manager):
        spec = _make_spec()
        hash_val = manager.compute_hash(spec)
        assert all(c in "0123456789abcdef" for c in hash_val)


class TestHashComputation:
    """Test hash computation edge cases."""

    def test_empty_spec_hash(self):
        manager = DatasetSpecificationManager(MagicMock(spec=Database))
        hash_val = manager.compute_hash({})
        assert len(hash_val) == 64

    def test_nested_spec_hash_stable(self):
        manager = DatasetSpecificationManager(MagicMock(spec=Database))
        spec = {
            "dataset": {"name": "x", "version": 1},
            "content": {"minimum_characters": 0, "maximum_characters": 1},
        }
        h1 = manager.compute_hash(spec)
        h2 = manager.compute_hash(spec)
        assert h1 == h2

    def test_key_order_does_not_affect_hash(self):
        manager = DatasetSpecificationManager(MagicMock(spec=Database))
        spec1 = {"dataset": {"name": "x", "version": 1}}
        spec2 = {"dataset": {"version": 1, "name": "x"}}
        assert manager.compute_hash(spec1) == manager.compute_hash(spec2)
