"""Phase 2: Raw materialization bridge between Phase 1 and Phase 2."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any

from data_fetcher.database import Database, DatabaseError
from data_fetcher.models import (
    ArtifactRecord,
    MaterializationResult,
    ProcessingJobRecord,
)
from data_fetcher.storage import MinioStorage, StorageError

logger = logging.getLogger(__name__)


class MaterializationError(Exception):
    """Materialization-specific errors."""
    def __init__(self, category: str, message: str):
        self.category = category
        super().__init__(message)


@dataclass
class MaterializerConfig:
    """Configuration for materialization."""
    verify_checksum: bool = True
    max_retries: int = 2
    retry_backoff_seconds: int = 1


class Materializer:
    """Bridge between Phase 1 artifacts and Phase 2 processing."""
    
    def __init__(
        self,
        database: Database,
        storage: MinioStorage,
        config: MaterializerConfig | None = None,
    ) -> None:
        self.database = database
        self.storage = storage
        self.config = config or MaterializerConfig()
    
    def _get_artifact(self, artifact_id: str) -> ArtifactRecord:
        """Retrieve artifact metadata from PostgreSQL."""
        with self.database.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, fetch_id, storage_backend, bucket_name, object_key, "
                    "content_type, size_bytes, checksum_sha256, metadata "
                    "FROM artifacts WHERE id = %s",
                    (artifact_id,),
                )
                row = cur.fetchone()
                if not row:
                    raise MaterializationError(
                        "artifact_not_found",
                        f"Artifact {artifact_id} not found in database"
                    )
                return ArtifactRecord(
                    id=row[0],
                    fetch_id=row[1],
                    storage_backend=row[2],
                    bucket_name=row[3],
                    object_key=row[4],
                    content_type=row[5],
                    size_bytes=row[6],
                    checksum_sha256=row[7],
                    metadata=row[8] or {},
                )
    
    def _create_processing_job(
        self,
        name: str,
        source_artifact_id: str,
        config: dict[str, Any],
    ) -> ProcessingJobRecord:
        """Create a Phase 2 processing job."""
        with self.database.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO processing_jobs "
                    "(name, status, config, source_artifact_id, started_at) "
                    "VALUES (%s, %s, %s, %s, NOW()) "
                    "RETURNING id, name, status, config, source_artifact_id, "
                    "started_at, finished_at, error_message, error_category, created_at, updated_at",
                    (name, "running", json.dumps(config), source_artifact_id),
                )
                row = cur.fetchone()
                conn.commit()
                return ProcessingJobRecord(
                    id=row[0],
                    name=row[1],
                    status=row[2],
                    config=row[3],
                    source_artifact_id=row[4],
                    started_at=row[5].isoformat() if row[5] else None,
                    finished_at=row[6].isoformat() if row[6] else None,
                    error_message=row[7],
                    error_category=row[8],
                    created_at=row[9].isoformat() if row[9] else None,
                    updated_at=row[10].isoformat() if row[10] else None,
                )
    
    def _update_processing_job(
        self,
        job_id: str,
        status: str,
        error_message: str | None = None,
        error_category: str | None = None,
    ) -> None:
        """Update processing job status."""
        with self.database.connect() as conn:
            with conn.cursor() as cur:
                if status in ("completed", "failed", "cancelled"):
                    cur.execute(
                        "UPDATE processing_jobs "
                        "SET status = %s, error_message = %s, error_category = %s, "
                        "finished_at = NOW(), updated_at = NOW() "
                        "WHERE id = %s",
                        (status, error_message, error_category, job_id),
                    )
                else:
                    cur.execute(
                        "UPDATE processing_jobs "
                        "SET status = %s, error_message = %s, error_category = %s, updated_at = NOW() "
                        "WHERE id = %s",
                        (status, error_message, error_category, job_id),
                    )
                conn.commit()
    
    def _get_provenance_for_artifact(self, artifact_id: str) -> dict[str, Any]:
        """Get full provenance for an artifact."""
        with self.database.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT f.id AS fetch_id, f.resource_id, r.url AS resource_url, "
                    "r.normalized_url, r.domain, f.http_status, f.content_type, "
                    "f.content_length, f.headers, f.error_message, f.started_at, f.completed_at, "
                    "a.bucket_name, a.object_key, a.checksum_sha256 "
                    "FROM fetches f "
                    "JOIN resources r ON f.resource_id = r.id "
                    "JOIN artifacts a ON a.fetch_id = f.id "
                    "WHERE a.id = %s",
                    (artifact_id,),
                )
                row = cur.fetchone()
                if not row:
                    raise MaterializationError(
                        "provenance_not_found",
                        f"Provenance for artifact {artifact_id} not found"
                    )
                return {
                    "fetch_id": row[0],
                    "resource_id": row[1],
                    "resource_url": row[2],
                    "normalized_url": row[3],
                    "domain": row[4],
                    "http_status": row[5],
                    "content_type": row[6],
                    "content_length": row[7],
                    "headers": row[8],
                    "error_message": row[9],
                    "started_at": row[10].isoformat() if row[10] else None,
                    "completed_at": row[11].isoformat() if row[11] else None,
                    "bucket_name": row[12],
                    "object_key": row[13],
                    "checksum_sha256": row[14],
                }
    
    def _verify_checksum(self, data: bytes, expected_checksum: str) -> bool:
        """Verify SHA-256 checksum of data."""
        actual_checksum = hashlib.sha256(data).hexdigest()
        return actual_checksum == expected_checksum
    
    def materialize(
        self,
        artifact_id: str,
        job_name: str | None = None,
        job_config: dict[str, Any] | None = None,
    ) -> MaterializationResult:
        """
        Materialize a Phase 1 artifact for Phase 2 processing.
        
        Args:
            artifact_id: Phase 1 artifact ID to materialize
            job_name: Name for the processing job (auto-generated if None)
            job_config: Configuration for the processing job
        
        Returns:
            MaterializationResult with raw data and provenance
        
        Raises:
            MaterializationError: If materialization fails
        """
        if job_name is None:
            job_name = f"materialize-{artifact_id}"
        
        if job_config is None:
            job_config = {}
        
        # Create processing job
        try:
            job = self._create_processing_job(job_name, artifact_id, job_config)
        except DatabaseError as exc:
            raise MaterializationError("database_error", f"Failed to create processing job: {exc}") from exc
        
        # Get artifact metadata
        try:
            artifact = self._get_artifact(artifact_id)
        except MaterializationError:
            self._update_processing_job(job.id, "failed", "Artifact not found", "artifact_not_found")
            raise
        
        # Get provenance
        try:
            provenance = self._get_provenance_for_artifact(artifact_id)
        except MaterializationError:
            self._update_processing_job(job.id, "failed", "Provenance not found", "provenance_not_found")
            raise
        
        # Retrieve raw object from MinIO
        try:
            raw_data = self.storage.get_object(artifact.object_key)
        except StorageError as exc:
            self._update_processing_job(job.id, "failed", str(exc), "storage_error")
            raise MaterializationError("storage_error", f"Failed to retrieve object: {exc}") from exc
        
        # Verify checksum if configured
        checksum_verified = False
        if self.config.verify_checksum and artifact.checksum_sha256:
            checksum_verified = self._verify_checksum(raw_data, artifact.checksum_sha256)
            if not checksum_verified:
                self._update_processing_job(
                    job.id,
                    "failed",
                    "Checksum mismatch",
                    "checksum_mismatch"
                )
                raise MaterializationError(
                    "checksum_mismatch",
                    f"Checksum mismatch for artifact {artifact_id}"
                )
        
        # Mark job as completed
        self._update_processing_job(job.id, "completed")
        
        logger.info(
            "Materialization complete",
            extra={
                "processing_job_id": job.id,
                "artifact_id": artifact_id,
                "checksum_verified": checksum_verified,
            }
        )
        
        return MaterializationResult(
            processing_job_id=job.id,
            artifact_id=artifact.id,
            resource_id=provenance["resource_id"],
            fetch_id=provenance["fetch_id"],
            source_url=provenance["resource_url"],
            raw_object_key=artifact.object_key,
            raw_data=raw_data,
            checksum_sha256=artifact.checksum_sha256,
            checksum_verified=checksum_verified,
            materialized_at=job.started_at,
        )
