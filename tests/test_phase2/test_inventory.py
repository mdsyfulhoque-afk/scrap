"""Unit tests for Phase 2 data inventory."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from data_fetcher.database import Database, DatabaseError
from data_fetcher.models import ArtifactCharacterization
from data_fetcher.phase2.discovery import DiscoveryConfig, DiscoveryError, FormatDiscovery
from data_fetcher.phase2.inventory import (
    ArtifactAvailability,
    DataInventory,
    InventoryConfig,
    InventoryError,
)
from data_fetcher.storage import MinioStorage, StorageError


@pytest.fixture
def mock_database():
    return MagicMock(spec=Database)


@pytest.fixture
def mock_storage():
    return MagicMock(spec=MinioStorage)


@pytest.fixture
def mock_discovery():
    discovery = MagicMock(spec=FormatDiscovery)
    discovery.config = DiscoveryConfig()
    return discovery


@pytest.fixture
def sample_characterization():
    return ArtifactCharacterization(
        id="char-123",
        artifact_id="artifact-123",
        characterization_version="1.0.0",
        characterization_config={"max_preview_bytes": 65536},
        detected_format="html",
        format_confidence="high",
        format_evidence={"sources": [{"source": "mime", "format": "html", "confidence": "high"}]},
        mime_type="text/html",
        file_extension="html",
        encoding="utf-8",
        structural_type="document",
        document_type_candidates=["webpage"],
        schema_summary=None,
        content_statistics={"byte_count": 100, "character_count": 80, "line_count": 5, "word_count_estimate": 12, "bytes_analyzed": 100, "analysis_scope": "full"},
        metadata_availability={"content_type_present": True, "url_present": True},
        extraction_suitability="suitable",
        warnings=[],
        errors=[],
        is_deterministic=True,
        characterized_at="2026-08-17T10:00:00Z",
        created_at="2026-08-17T10:00:00Z",
    )


class TestDataInventory:
    """Test DataInventory class."""

    def test_get_all_artifacts_success(self, mock_database, mock_storage, mock_discovery):
        mock_database.get_all_artifacts.return_value = [
            {"id": "a1", "resource_url": "http://example.com/1", "content_type": "text/html", "size_bytes": 100, "object_key": "key1", "domain": "example.com"},
            {"id": "a2", "resource_url": "http://example.com/2", "content_type": "application/json", "size_bytes": 200, "object_key": "key2", "domain": "example.com"},
        ]
        inventory = DataInventory(mock_database, mock_discovery, mock_storage)
        artifacts = inventory.get_all_artifacts()
        assert len(artifacts) == 2
        mock_database.get_all_artifacts.assert_called_once()

    def test_get_all_artifacts_database_error(self, mock_database, mock_storage, mock_discovery):
        mock_database.get_all_artifacts.side_effect = DatabaseError("db failed")
        inventory = DataInventory(mock_database, mock_discovery, mock_storage)
        with pytest.raises(InventoryError) as exc_info:
            inventory.get_all_artifacts()
        assert exc_info.value.category == "database_error"

    def test_get_artifact_success(self, mock_database, mock_storage, mock_discovery):
        mock_database.get_artifact.return_value = {"id": "a1", "resource_url": "http://example.com/1"}
        inventory = DataInventory(mock_database, mock_discovery, mock_storage)
        artifact = inventory.get_artifact("a1")
        assert artifact["id"] == "a1"

    def test_get_artifact_not_found(self, mock_database, mock_storage, mock_discovery):
        mock_database.get_artifact.return_value = None
        inventory = DataInventory(mock_database, mock_discovery, mock_storage)
        artifact = inventory.get_artifact("missing")
        assert artifact is None

    def test_characterize_artifact_success(self, mock_database, mock_storage, mock_discovery, sample_characterization):
        mock_storage.get_object.return_value = b"<html>test</html>"
        mock_discovery.characterize.return_value = sample_characterization
        artifact = {"id": "a1", "object_key": "key1", "content_type": "text/html", "resource_url": "http://example.com"}
        inventory = DataInventory(mock_database, mock_discovery, mock_storage)
        result, availability = inventory.characterize_artifact(artifact)
        assert result == sample_characterization
        assert availability == ArtifactAvailability.AVAILABLE
        mock_storage.get_object.assert_called_once_with("key1")

    def test_characterize_artifact_unavailable(self, mock_database, mock_storage, mock_discovery):
        mock_storage.get_object.side_effect = StorageError("object retrieval failed")
        mock_storage.object_exists.return_value = False
        artifact = {"id": "a1", "object_key": "key1", "content_type": "text/html", "resource_url": "http://example.com"}
        inventory = DataInventory(mock_database, mock_discovery, mock_storage)
        result, availability = inventory.characterize_artifact(artifact)
        assert result is None
        assert availability == ArtifactAvailability.UNAVAILABLE

    def test_characterize_artifact_storage_error(self, mock_database, mock_storage, mock_discovery):
        mock_storage.get_object.side_effect = StorageError("object retrieval failed")
        mock_storage.object_exists.return_value = True
        artifact = {"id": "a1", "object_key": "key1", "content_type": "text/html", "resource_url": "http://example.com"}
        inventory = DataInventory(mock_database, mock_discovery, mock_storage)
        result, availability = inventory.characterize_artifact(artifact)
        assert result is None
        assert availability == ArtifactAvailability.CORRUPTED

    def test_characterize_artifact_discovery_error(self, mock_database, mock_storage, mock_discovery):
        mock_storage.get_object.return_value = b"<html>test</html>"
        mock_discovery.characterize.side_effect = DiscoveryError("discovery_failed", "test error")
        artifact = {"id": "a1", "object_key": "key1", "content_type": "text/html", "resource_url": "http://example.com"}
        inventory = DataInventory(mock_database, mock_discovery, mock_storage)
        result, availability = inventory.characterize_artifact(artifact)
        assert result is None
        assert availability == ArtifactAvailability.CHARACTERIZATION_FAILED

    def test_save_characterization_success(self, mock_database, mock_storage, mock_discovery, sample_characterization):
        mock_database.save_artifact_characterization.return_value = sample_characterization
        inventory = DataInventory(mock_database, mock_discovery, mock_storage)
        result = inventory.save_characterization(sample_characterization)
        assert result == sample_characterization
        mock_database.save_artifact_characterization.assert_called_once_with(sample_characterization)

    def test_save_characterization_database_error(self, mock_database, mock_storage, mock_discovery, sample_characterization):
        mock_database.save_artifact_characterization.side_effect = DatabaseError("save failed")
        inventory = DataInventory(mock_database, mock_discovery, mock_storage)
        with pytest.raises(InventoryError) as exc_info:
            inventory.save_characterization(sample_characterization)
        assert exc_info.value.category == "database_error"

    def test_build_inventory_multiple_artifacts(self, mock_database, mock_storage, mock_discovery, sample_characterization):
        mock_database.get_all_artifacts.return_value = [
            {"id": "a1", "resource_url": "http://example.com/1", "content_type": "text/html", "size_bytes": 100, "object_key": "key1", "domain": "example.com", "created_at": "2026-01-01"},
            {"id": "a2", "resource_url": "http://example.com/2", "content_type": "application/json", "size_bytes": 200, "object_key": "key2", "domain": "example.com", "created_at": "2026-01-02"},
        ]
        mock_storage.get_object.return_value = b"test data"
        mock_discovery.characterize.return_value = sample_characterization
        mock_database.save_artifact_characterization.return_value = sample_characterization

        inventory = DataInventory(mock_database, mock_discovery, mock_storage, InventoryConfig(save_results=True))
        report = inventory.build_inventory()

        assert report["total_artifacts"] == 2
        assert report["characterized_count"] == 2
        assert report["failed_count"] == 0
        assert report["raw_available"] == 2
        assert report["raw_unavailable"] == 0
        assert "global_statistics" in report
        assert "format_distribution" in report
        assert "domain_distribution" in report
        assert "size_distribution" in report

    def test_build_inventory_with_unavailable_artifacts(self, mock_database, mock_storage, mock_discovery, sample_characterization):
        mock_database.get_all_artifacts.return_value = [
            {"id": "a1", "resource_url": "http://example.com/1", "content_type": "text/html", "size_bytes": 100, "object_key": "key1", "domain": "example.com", "created_at": "2026-01-01"},
            {"id": "a2", "resource_url": "http://example.com/2", "content_type": "application/json", "size_bytes": 200, "object_key": "key2", "domain": "example.com", "created_at": "2026-01-02"},
        ]
        mock_storage.get_object.side_effect = [StorageError("not found"), b"test data"]
        mock_storage.object_exists.side_effect = [False, True]
        mock_discovery.characterize.return_value = sample_characterization
        mock_database.save_artifact_characterization.return_value = sample_characterization

        inventory = DataInventory(mock_database, mock_discovery, mock_storage, InventoryConfig(save_results=True))
        report = inventory.build_inventory()

        assert report["total_artifacts"] == 2
        assert report["characterized_count"] == 1
        assert report["failed_count"] == 1
        assert report["raw_available"] == 1
        assert report["raw_unavailable"] == 1
        assert report["availability_counts"]["unavailable"] == 1
        assert report["availability_counts"]["available"] == 1

    def test_build_inventory_detects_format_conflicts(self, mock_database, mock_storage, mock_discovery):
        mock_database.get_all_artifacts.return_value = [
            {"id": "a1", "resource_url": "http://example.com/1", "content_type": "text/html", "size_bytes": 100, "object_key": "key1", "domain": "example.com", "created_at": "2026-01-01"},
        ]
        mock_storage.get_object.return_value = b"plain text content here"
        char = ArtifactCharacterization(
            id="c1", artifact_id="a1", characterization_version="1.0.0", characterization_config={},
            detected_format="plain_text", format_confidence="high", format_evidence={}, mime_type="text/html",
            file_extension="html", encoding="utf-8", structural_type="single-line", document_type_candidates=[],
            schema_summary=None, content_statistics={"byte_count": 21, "character_count": 21, "line_count": 1, "word_count_estimate": 4, "bytes_analyzed": 21, "analysis_scope": "full"},
            metadata_availability={}, extraction_suitability="suitable",
            warnings=[], errors=[], is_deterministic=True, characterized_at="2026-01-01", created_at="2026-01-01",
        )
        mock_discovery.characterize.return_value = char
        mock_database.save_artifact_characterization.return_value = char

        inventory = DataInventory(mock_database, mock_discovery, mock_storage, InventoryConfig(save_results=True))
        report = inventory.build_inventory()

        assert len(report["format_conflicts"]) == 1
        assert report["format_conflicts"][0]["artifact_id"] == "a1"
        assert report["format_conflicts"][0]["declared_mime"] == "text/html"
        assert report["format_conflicts"][0]["detected_format"] == "plain_text"

    def test_format_distribution(self, mock_database, mock_storage, mock_discovery):
        char1 = ArtifactCharacterization(
            id="c1", artifact_id="a1", characterization_version="1.0.0", characterization_config={},
            detected_format="html", format_confidence="high", format_evidence={}, mime_type="text/html",
            file_extension="html", encoding="utf-8", structural_type="document", document_type_candidates=[],
            schema_summary=None, content_statistics={}, metadata_availability={}, extraction_suitability="suitable",
            warnings=[], errors=[], is_deterministic=True, characterized_at="2026-01-01", created_at="2026-01-01",
        )
        char2 = ArtifactCharacterization(
            id="c2", artifact_id="a2", characterization_version="1.0.0", characterization_config={},
            detected_format="json", format_confidence="high", format_evidence={}, mime_type="application/json",
            file_extension="json", encoding="utf-8", structural_type="object", document_type_candidates=[],
            schema_summary=None, content_statistics={}, metadata_availability={}, extraction_suitability="suitable",
            warnings=[], errors=[], is_deterministic=True, characterized_at="2026-01-01", created_at="2026-01-01",
        )
        inventory = DataInventory(mock_database, mock_discovery, mock_storage)
        dist = inventory._format_distribution([char1, char2])
        assert dist["html"] == 1
        assert dist["json"] == 1

    def test_domain_distribution(self, mock_database, mock_storage, mock_discovery):
        artifacts = [
            {"domain": "example.com", "id": "a1", "content_type": None, "size_bytes": 100, "resource_url": "http://example.com/1", "created_at": "2026-01-01"},
            {"domain": "example.com", "id": "a2", "content_type": None, "size_bytes": 200, "resource_url": "http://example.com/2", "created_at": "2026-01-02"},
            {"domain": "test.org", "id": "a3", "content_type": None, "size_bytes": 300, "resource_url": "http://test.org/1", "created_at": "2026-01-03"},
        ]
        inventory = DataInventory(mock_database, mock_discovery, mock_storage)
        dist = inventory._domain_distribution(artifacts)
        assert dist["example.com"] == 2
        assert dist["test.org"] == 1

    def test_size_distribution(self, mock_database, mock_storage, mock_discovery):
        artifacts = [
            {"id": "a1", "content_type": None, "size_bytes": 500, "resource_url": "http://example.com/1", "created_at": "2026-01-01"},
            {"id": "a2", "content_type": None, "size_bytes": 5000, "resource_url": "http://example.com/2", "created_at": "2026-01-02"},
            {"id": "a3", "content_type": None, "size_bytes": 50000, "resource_url": "http://example.com/3", "created_at": "2026-01-03"},
            {"id": "a4", "content_type": None, "size_bytes": 500000, "resource_url": "http://example.com/4", "created_at": "2026-01-04"},
            {"id": "a5", "content_type": None, "size_bytes": 2000000, "resource_url": "http://example.com/5", "created_at": "2026-01-05"},
        ]
        inventory = DataInventory(mock_database, mock_discovery, mock_storage)
        dist = inventory._size_distribution(artifacts)
        assert dist["<1KB"] == 1
        assert dist["1KB-10KB"] == 1
        assert dist["10KB-100KB"] == 1
        assert dist["100KB-1MB"] == 1
        assert dist[">1MB"] == 1
