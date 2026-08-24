"""Unit tests for Phase 2 materialization."""

from __future__ import annotations

import hashlib
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from data_fetcher.database import Database, DatabaseError
from data_fetcher.models import ArtifactRecord, MaterializationResult
from data_fetcher.phase2.materialization import MaterializationError, Materializer, MaterializerConfig
from data_fetcher.storage import MinioStorage, StorageError


@pytest.fixture
def mock_database():
    """Mock database connection."""
    return MagicMock(spec=Database)


@pytest.fixture
def mock_storage():
    """Mock MinIO storage."""
    return MagicMock(spec=MinioStorage)


@pytest.fixture
def sample_artifact():
    """Sample artifact record."""
    return ArtifactRecord(
        id="artifact-123",
        fetch_id="fetch-456",
        storage_backend="minio",
        bucket_name="raw",
        object_key="web/example.com/20260813/payload.bin",
        content_type="text/html",
        size_bytes=1024,
        checksum_sha256="2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824",
        metadata={"redirect_chain": ["http://example.com"]},
    )


@pytest.fixture
def sample_provenance():
    """Sample provenance data."""
    return {
        "fetch_id": "fetch-456",
        "resource_id": "resource-789",
        "resource_url": "http://example.com",
        "normalized_url": "http://example.com",
        "domain": "example.com",
        "http_status": 200,
        "content_type": "text/html",
        "content_length": 1024,
        "headers": {"Content-Type": "text/html"},
        "error_message": None,
        "started_at": "2026-08-13T12:00:00Z",
        "completed_at": "2026-08-13T12:00:01Z",
        "bucket_name": "raw",
        "object_key": "web/example.com/20260813/payload.bin",
        "checksum_sha256": "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824",
    }


@pytest.fixture
def sample_raw_data():
    """Sample raw data."""
    return b"hello world"


@pytest.fixture
def sample_raw_data_checksum():
    """Checksum for sample raw data."""
    return hashlib.sha256(b"hello world").hexdigest()


class TestMaterializer:
    """Test Materializer class."""
    
    @patch('data_fetcher.phase2.materialization.Materializer._create_processing_job')
    @patch('data_fetcher.phase2.materialization.Materializer._get_artifact')
    @patch('data_fetcher.phase2.materialization.Materializer._get_provenance_for_artifact')
    def test_materialize_success(
        self, mock_get_provenance, mock_get_artifact, mock_create_job, 
        mock_database, mock_storage, sample_raw_data, sample_raw_data_checksum
    ):
        """Test successful materialization."""
        mock_create_job.return_value = MagicMock(
            id="job-123",
            started_at="2026-08-13T12:00:00Z"
        )
        mock_get_artifact.return_value = ArtifactRecord(
            id="artifact-123",
            fetch_id="fetch-456",
            storage_backend="minio",
            bucket_name="raw",
            object_key="web/example.com/20260813/payload.bin",
            content_type="text/html",
            size_bytes=1024,
            checksum_sha256=sample_raw_data_checksum,
            metadata={}
        )
        mock_get_provenance.return_value = {
            "fetch_id": "fetch-456",
            "resource_id": "resource-789",
            "resource_url": "http://example.com",
            "normalized_url": "http://example.com",
            "domain": "example.com",
            "http_status": 200,
            "content_type": "text/html",
            "content_length": 1024,
            "headers": {},
            "error_message": None,
            "started_at": "2026-08-13T12:00:00Z",
            "completed_at": "2026-08-13T12:00:01Z",
            "bucket_name": "raw",
            "object_key": "web/example.com/20260813/payload.bin",
            "checksum_sha256": sample_raw_data_checksum,
        }
        mock_storage.get_object.return_value = sample_raw_data
        
        materializer = Materializer(mock_database, mock_storage, MaterializerConfig(verify_checksum=False))
        result = materializer.materialize("artifact-123")
        
        assert isinstance(result, MaterializationResult)
        assert result.artifact_id == "artifact-123"
        assert result.resource_id == "resource-789"
        assert result.fetch_id == "fetch-456"
        assert result.source_url == "http://example.com"
        assert result.raw_object_key == "web/example.com/20260813/payload.bin"
        assert result.raw_data == sample_raw_data
        assert result.checksum_sha256 == sample_raw_data_checksum
        assert result.checksum_verified is False
        mock_storage.get_object.assert_called_once_with("web/example.com/20260813/payload.bin")
    
    @patch('data_fetcher.phase2.materialization.Materializer._create_processing_job')
    @patch('data_fetcher.phase2.materialization.Materializer._get_artifact')
    def test_materialize_artifact_not_found(self, mock_get_artifact, mock_create_job, mock_database, mock_storage):
        """Test materialization when artifact not found."""
        mock_create_job.return_value = MagicMock(id="job-123", started_at="2026-08-13T12:00:00Z")
        mock_get_artifact.side_effect = MaterializationError("artifact_not_found", "Artifact not found")
        
        materializer = Materializer(mock_database, mock_storage, MaterializerConfig(verify_checksum=False))
        
        with pytest.raises(MaterializationError) as exc_info:
            materializer.materialize("artifact-123")
        
        assert exc_info.value.category == "artifact_not_found"
    
    @patch('data_fetcher.phase2.materialization.Materializer._create_processing_job')
    @patch('data_fetcher.phase2.materialization.Materializer._get_artifact')
    @patch('data_fetcher.phase2.materialization.Materializer._get_provenance_for_artifact')
    def test_materialize_storage_error(self, mock_get_provenance, mock_get_artifact, mock_create_job, 
                                     mock_database, mock_storage, sample_raw_data_checksum):
        """Test materialization when storage retrieval fails."""
        mock_create_job.return_value = MagicMock(id="job-123", started_at="2026-08-13T12:00:00Z")
        mock_get_artifact.return_value = ArtifactRecord(
            id="artifact-123",
            fetch_id="fetch-456",
            storage_backend="minio",
            bucket_name="raw",
            object_key="web/example.com/20260813/payload.bin",
            content_type="text/html",
            size_bytes=1024,
            checksum_sha256=sample_raw_data_checksum,
            metadata={}
        )
        mock_get_provenance.return_value = {
            "fetch_id": "fetch-456",
            "resource_id": "resource-789",
            "resource_url": "http://example.com",
            "normalized_url": "http://example.com",
            "domain": "example.com",
            "http_status": 200,
            "content_type": "text/html",
            "content_length": 1024,
            "headers": {},
            "error_message": None,
            "started_at": "2026-08-13T12:00:00Z",
            "completed_at": "2026-08-13T12:00:01Z",
            "bucket_name": "raw",
            "object_key": "web/example.com/20260813/payload.bin",
            "checksum_sha256": sample_raw_data_checksum,
        }
        mock_storage.get_object.side_effect = StorageError("object retrieval failed")
        
        materializer = Materializer(mock_database, mock_storage)
        
        with pytest.raises(MaterializationError) as exc_info:
            materializer.materialize("artifact-123")
        
        assert exc_info.value.category == "storage_error"
    
    @patch('data_fetcher.phase2.materialization.Materializer._create_processing_job')
    @patch('data_fetcher.phase2.materialization.Materializer._get_artifact')
    @patch('data_fetcher.phase2.materialization.Materializer._get_provenance_for_artifact')
    def test_materialize_checksum_mismatch(self, mock_get_provenance, mock_get_artifact, mock_create_job,
                                         mock_database, mock_storage, sample_raw_data):
        """Test materialization with checksum mismatch."""
        wrong_checksum = "wrong_checksum_1234567890abcdef"
        mock_create_job.return_value = MagicMock(id="job-123", started_at="2026-08-13T12:00:00Z")
        mock_get_artifact.return_value = ArtifactRecord(
            id="artifact-123",
            fetch_id="fetch-456",
            storage_backend="minio",
            bucket_name="raw",
            object_key="web/example.com/20260813/payload.bin",
            content_type="text/html",
            size_bytes=1024,
            checksum_sha256=wrong_checksum,
            metadata={}
        )
        mock_get_provenance.return_value = {
            "fetch_id": "fetch-456",
            "resource_id": "resource-789",
            "resource_url": "http://example.com",
            "normalized_url": "http://example.com",
            "domain": "example.com",
            "http_status": 200,
            "content_type": "text/html",
            "content_length": 1024,
            "headers": {},
            "error_message": None,
            "started_at": "2026-08-13T12:00:00Z",
            "completed_at": "2026-08-13T12:00:01Z",
            "bucket_name": "raw",
            "object_key": "web/example.com/20260813/payload.bin",
            "checksum_sha256": wrong_checksum,
        }
        mock_storage.get_object.return_value = sample_raw_data
        
        materializer = Materializer(mock_database, mock_storage, MaterializerConfig(verify_checksum=True))
        
        with pytest.raises(MaterializationError) as exc_info:
            materializer.materialize("artifact-123")
        
        assert exc_info.value.category == "checksum_mismatch"
    
    @patch('data_fetcher.phase2.materialization.Materializer._create_processing_job')
    @patch('data_fetcher.phase2.materialization.Materializer._get_artifact')
    @patch('data_fetcher.phase2.materialization.Materializer._get_provenance_for_artifact')
    def test_materialize_checksum_verification_disabled(self, mock_get_provenance, mock_get_artifact, mock_create_job,
                                                   mock_database, mock_storage, sample_raw_data):
        """Test materialization with checksum verification disabled."""
        wrong_checksum = "wrong_checksum_1234567890abcdef"
        mock_create_job.return_value = MagicMock(id="job-123", started_at="2026-08-13T12:00:00Z")
        mock_get_artifact.return_value = ArtifactRecord(
            id="artifact-123",
            fetch_id="fetch-456",
            storage_backend="minio",
            bucket_name="raw",
            object_key="web/example.com/20260813/payload.bin",
            content_type="text/html",
            size_bytes=1024,
            checksum_sha256=wrong_checksum,
            metadata={}
        )
        mock_get_provenance.return_value = {
            "fetch_id": "fetch-456",
            "resource_id": "resource-789",
            "resource_url": "http://example.com",
            "normalized_url": "http://example.com",
            "domain": "example.com",
            "http_status": 200,
            "content_type": "text/html",
            "content_length": 1024,
            "headers": {},
            "error_message": None,
            "started_at": "2026-08-13T12:00:00Z",
            "completed_at": "2026-08-13T12:00:01Z",
            "bucket_name": "raw",
            "object_key": "web/example.com/20260813/payload.bin",
            "checksum_sha256": wrong_checksum,
        }
        mock_storage.get_object.return_value = sample_raw_data
        
        materializer = Materializer(mock_database, mock_storage, MaterializerConfig(verify_checksum=False))
        
        result = materializer.materialize("artifact-123")
        assert result.checksum_verified is False
    
    @patch('data_fetcher.phase2.materialization.Materializer._create_processing_job')
    @patch('data_fetcher.phase2.materialization.Materializer._get_artifact')
    @patch('data_fetcher.phase2.materialization.Materializer._get_provenance_for_artifact')
    def test_materialize_custom_job_name_and_config(self, mock_get_provenance, mock_get_artifact, mock_create_job,
                                                  mock_database, mock_storage, sample_raw_data, sample_raw_data_checksum):
        """Test materialization with custom job name and config."""
        mock_create_job.return_value = MagicMock(id="job-123", started_at="2026-08-13T12:00:00Z")
        mock_get_artifact.return_value = ArtifactRecord(
            id="artifact-123",
            fetch_id="fetch-456",
            storage_backend="minio",
            bucket_name="raw",
            object_key="web/example.com/20260813/payload.bin",
            content_type="text/html",
            size_bytes=1024,
            checksum_sha256=sample_raw_data_checksum,
            metadata={}
        )
        mock_get_provenance.return_value = {
            "fetch_id": "fetch-456",
            "resource_id": "resource-789",
            "resource_url": "http://example.com",
            "normalized_url": "http://example.com",
            "domain": "example.com",
            "http_status": 200,
            "content_type": "text/html",
            "content_length": 1024,
            "headers": {},
            "error_message": None,
            "started_at": "2026-08-13T12:00:00Z",
            "completed_at": "2026-08-13T12:00:01Z",
            "bucket_name": "raw",
            "object_key": "web/example.com/20260813/payload.bin",
            "checksum_sha256": sample_raw_data_checksum,
        }
        mock_storage.get_object.return_value = sample_raw_data
        
        materializer = Materializer(mock_database, mock_storage, MaterializerConfig(verify_checksum=False))
        
        result = materializer.materialize(
            "artifact-123",
            job_name="custom-job-name",
            job_config={"custom": "config"}
        )
        
        assert result.processing_job_id == "job-123"
        assert result.checksum_verified is False
