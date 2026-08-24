from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any

import psycopg
from psycopg.rows import class_row

from data_fetcher.models import ArtifactCharacterization, CanonicalDocument, DatasetSpecification, DatasetBuild, DatasetRecord, DecisionRecord, ValidationReport, FeasibilityReport, FeasibilityStageResult, NormalizedDocument, QualityResult, DuplicateGroup, DuplicateMembership, ArtifactRecord, CrawlJobRecord, FetchRecord, ResourceRecord


class DatabaseError(Exception):
    pass


class Database:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    @contextmanager
    def connect(self):
        try:
            with psycopg.connect(self.dsn, autocommit=False) as conn:
                yield conn
        except psycopg.Error as exc:
            raise DatabaseError("database connection failed") from exc

    def create_crawl_job(self, name: str, status: str, config: dict[str, Any]) -> CrawlJobRecord:
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO crawl_jobs (name, status, config, started_at)"
                    " VALUES (%s, %s, %s, NOW()) RETURNING id, name, status, config, started_at, finished_at",
                    (name, status, json.dumps(config)),
                )
                row = cur.fetchone()
                conn.commit()
                return CrawlJobRecord(
                    id=row[0],
                    name=row[1],
                    status=row[2],
                    config=row[3],
                    started_at=row[4].isoformat() if row[4] else None,
                    finished_at=row[5].isoformat() if row[5] else None,
                )

    def update_crawl_job_status(self, crawl_job_id: str, status: str) -> None:
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE crawl_jobs SET status = %s, updated_at = NOW(), finished_at = NOW() WHERE id = %s",
                    (status, crawl_job_id),
                )
                conn.commit()

    def update_fetch_status(self, fetch_id: str, status: str, error_message: str | None = None) -> None:
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE fetches SET status = %s, error_message = %s, completed_at = NOW() WHERE id = %s",
                    (status, error_message, fetch_id),
                )
                conn.commit()

    def complete_fetch(self, fetch_id: str, status: str, http_status: int | None, content_type: str | None, content_length: int | None, headers: dict[str, Any], error_message: str | None = None) -> None:
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE fetches SET status = %s, http_status = %s, content_type = %s, content_length = %s, headers = %s, error_message = %s, completed_at = NOW() WHERE id = %s",
                    (
                        status,
                        http_status,
                        content_type,
                        content_length,
                        json.dumps(headers),
                        error_message,
                        fetch_id,
                    ),
                )
                conn.commit()

    def ensure_resource(self, url: str, normalized_url: str, domain: str, resource_type: str | None, metadata: dict[str, Any]) -> ResourceRecord:
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, url, normalized_url, domain, resource_type, metadata"
                    " FROM resources WHERE url = %s",
                    (url,),
                )
                row = cur.fetchone()
                if row:
                    return ResourceRecord(
                        id=row[0],
                        url=row[1],
                        normalized_url=row[2] or normalized_url,
                        domain=row[3] or domain,
                        resource_type=row[4],
                        metadata=row[5] or metadata,
                    )
                cur.execute(
                    "INSERT INTO resources (url, normalized_url, domain, resource_type, metadata)"
                    " VALUES (%s, %s, %s, %s, %s) RETURNING id",
                    (url, normalized_url, domain, resource_type, json.dumps(metadata)),
                )
                resource_id = cur.fetchone()[0]
                conn.commit()
                return ResourceRecord(
                    id=resource_id,
                    url=url,
                    normalized_url=normalized_url,
                    domain=domain,
                    resource_type=resource_type,
                    metadata=metadata,
                )

    def create_fetch(self, resource_id: str, crawl_job_id: str | None, status: str, http_status: int | None, content_type: str | None, content_length: int | None, headers: dict[str, Any], error_message: str | None, started_at: str | None, completed_at: str | None) -> FetchRecord:
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO fetches (resource_id, crawl_job_id, status, http_status, content_type, content_length, headers, error_message, started_at, completed_at)"
                    " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                    (
                        resource_id,
                        crawl_job_id,
                        status,
                        http_status,
                        content_type,
                        content_length,
                        json.dumps(headers),
                        error_message,
                        started_at,
                        completed_at,
                    ),
                )
                fetch_id = cur.fetchone()[0]
                conn.commit()
                return FetchRecord(
                    id=fetch_id,
                    resource_id=resource_id,
                    crawl_job_id=crawl_job_id,
                    status=status,
                    http_status=http_status,
                    content_type=content_type,
                    content_length=content_length,
                    headers=headers,
                    error_message=error_message,
                    started_at=started_at,
                    completed_at=completed_at,
                )

    def create_artifact(self, fetch_id: str, storage_backend: str, bucket_name: str, object_key: str, content_type: str | None, size_bytes: int, checksum_sha256: str, metadata: dict[str, Any]) -> ArtifactRecord:
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO artifacts (fetch_id, storage_backend, bucket_name, object_key, content_type, size_bytes, checksum_sha256, metadata)"
                    " VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                    (
                        fetch_id,
                        storage_backend,
                        bucket_name,
                        object_key,
                        content_type,
                        size_bytes,
                        checksum_sha256,
                        json.dumps(metadata),
                    ),
                )
                artifact_id = cur.fetchone()[0]
                conn.commit()
                return ArtifactRecord(
                    id=artifact_id,
                    fetch_id=fetch_id,
                    storage_backend=storage_backend,
                    bucket_name=bucket_name,
                    object_key=object_key,
                    content_type=content_type,
                    size_bytes=size_bytes,
                    checksum_sha256=checksum_sha256,
                    metadata=metadata,
                )

    def get_provenance(self, fetch_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            with conn.cursor(row_factory=class_row(dict)) as cur:
                cur.execute(
                    "SELECT f.id AS fetch_id, f.resource_id, r.url AS resource_url, r.normalized_url, r.domain,"
                    " f.http_status, f.content_type, f.content_length, f.headers, f.error_message,"
                    " f.started_at, f.completed_at, a.bucket_name, a.object_key, a.checksum_sha256"
                    " FROM fetches f"
                    " JOIN resources r ON f.resource_id = r.id"
                    " JOIN artifacts a ON a.fetch_id = f.id"
                    " WHERE f.id = %s",
                    (fetch_id,),
                )
                result = cur.fetchone()
                return dict(result) if result else None

    def get_all_artifacts(self) -> list[dict[str, Any]]:
        """Retrieve all artifacts with fetch and resource provenance."""
        with self.connect() as conn:
            with conn.cursor(row_factory=class_row(dict)) as cur:
                cur.execute(
                    "SELECT a.id, a.fetch_id, a.storage_backend, a.bucket_name, a.object_key, "
                    "a.content_type, a.size_bytes, a.checksum_sha256, a.metadata, a.created_at, "
                    "f.id AS fetch_id_val, f.resource_id, f.http_status, f.content_type AS fetch_content_type, "
                    "f.content_length, f.headers, f.started_at, f.completed_at, "
                    "r.url AS resource_url, r.normalized_url, r.domain, r.metadata AS resource_metadata "
                    "FROM artifacts a "
                    "JOIN fetches f ON a.fetch_id = f.id "
                    "JOIN resources r ON f.resource_id = r.id "
                    "ORDER BY a.created_at"
                )
                return [dict(row) for row in cur.fetchall()]

    def get_artifact(self, artifact_id: str) -> dict[str, Any] | None:
        """Retrieve a single artifact with provenance."""
        with self.connect() as conn:
            with conn.cursor(row_factory=class_row(dict)) as cur:
                cur.execute(
                    "SELECT a.id, a.fetch_id, a.storage_backend, a.bucket_name, a.object_key, "
                    "a.content_type, a.size_bytes, a.checksum_sha256, a.metadata, a.created_at, "
                    "f.id AS fetch_id_val, f.resource_id, f.http_status, f.content_type AS fetch_content_type, "
                    "f.content_length, f.headers, f.started_at, f.completed_at, "
                    "r.url AS resource_url, r.normalized_url, r.domain, r.metadata AS resource_metadata "
                    "FROM artifacts a "
                    "JOIN fetches f ON a.fetch_id = f.id "
                    "JOIN resources r ON f.resource_id = r.id "
                    "WHERE a.id = %s",
                    (artifact_id,),
                )
                row = cur.fetchone()
                return dict(row) if row else None

    def save_artifact_characterization(self, characterization: ArtifactCharacterization) -> ArtifactCharacterization:
        """Persist an artifact characterization result."""
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO artifact_characterization "
                    "(artifact_id, characterization_version, characterization_config, detected_format, "
                    "format_confidence, format_evidence, mime_type, file_extension, encoding, "
                    "structural_type, document_type_candidates, schema_summary, content_statistics, "
                    "metadata_availability, extraction_suitability, warnings, errors, is_deterministic, characterized_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT (artifact_id, characterization_version) DO UPDATE SET "
                    "detected_format = EXCLUDED.detected_format, "
                    "format_confidence = EXCLUDED.format_confidence, "
                    "format_evidence = EXCLUDED.format_evidence, "
                    "mime_type = EXCLUDED.mime_type, "
                    "file_extension = EXCLUDED.file_extension, "
                    "encoding = EXCLUDED.encoding, "
                    "structural_type = EXCLUDED.structural_type, "
                    "document_type_candidates = EXCLUDED.document_type_candidates, "
                    "schema_summary = EXCLUDED.schema_summary, "
                    "content_statistics = EXCLUDED.content_statistics, "
                    "metadata_availability = EXCLUDED.metadata_availability, "
                    "extraction_suitability = EXCLUDED.extraction_suitability, "
                    "warnings = EXCLUDED.warnings, "
                    "errors = EXCLUDED.errors, "
                    "is_deterministic = EXCLUDED.is_deterministic, "
                    "characterized_at = EXCLUDED.characterized_at "
                    "RETURNING id, artifact_id, characterization_version, detected_format, "
                    "format_confidence, format_evidence, mime_type, file_extension, encoding, "
                    "structural_type, document_type_candidates, schema_summary, content_statistics, "
                    "metadata_availability, extraction_suitability, warnings, errors, is_deterministic, "
                    "characterized_at, created_at",
                    (
                        characterization.artifact_id,
                        characterization.characterization_version,
                        json.dumps(characterization.characterization_config),
                        characterization.detected_format,
                        characterization.format_confidence,
                        json.dumps(characterization.format_evidence),
                        characterization.mime_type,
                        characterization.file_extension,
                        characterization.encoding,
                        characterization.structural_type,
                        json.dumps(characterization.document_type_candidates),
                        json.dumps(characterization.schema_summary) if characterization.schema_summary else None,
                        json.dumps(characterization.content_statistics),
                        json.dumps(characterization.metadata_availability),
                        characterization.extraction_suitability,
                        json.dumps(characterization.warnings),
                        json.dumps(characterization.errors),
                        characterization.is_deterministic,
                        characterization.characterized_at,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return ArtifactCharacterization(
                    id=row[0],
                    artifact_id=row[1],
                    characterization_version=row[2],
                    characterization_config=characterization.characterization_config,
                    detected_format=row[3],
                    format_confidence=row[4],
                    format_evidence=row[5],
                    mime_type=row[6],
                    file_extension=row[7],
                    encoding=row[8],
                    structural_type=row[9],
                    document_type_candidates=row[10],
                    schema_summary=row[11],
                    content_statistics=row[12],
                    metadata_availability=row[13],
                    extraction_suitability=row[14],
                    warnings=row[15],
                    errors=row[16],
                    is_deterministic=row[17],
                    characterized_at=row[18],
                    created_at=row[19].isoformat() if row[19] else None,
                )

    def get_characterization(self, artifact_id: str) -> dict[str, Any] | None:
        """Get the latest characterization for an artifact."""
        with self.connect() as conn:
            with conn.cursor(row_factory=class_row(dict)) as cur:
                cur.execute(
                    "SELECT * FROM artifact_characterization "
                    "WHERE artifact_id = %s "
                    "ORDER BY characterized_at DESC LIMIT 1",
                    (artifact_id,),
                )
                row = cur.fetchone()
                return dict(row) if row else None

    def get_inventory_stats(self) -> dict[str, Any]:
        """Get aggregate inventory statistics."""
        with self.connect() as conn:
            with conn.cursor(row_factory=class_row(dict)) as cur:
                cur.execute(
                    "SELECT "
                    "COUNT(*) AS total_artifacts, "
                    "SUM(a.size_bytes) AS total_bytes, "
                    "COUNT(ac.id) AS characterized_count, "
                    "COUNT(CASE WHEN ac.detected_format IS NULL THEN 1 END) AS unknown_format_count, "
                    "COUNT(CASE WHEN ac.extraction_suitability = 'suitable' THEN 1 END) AS suitable_count, "
                    "COUNT(CASE WHEN ac.extraction_suitability = 'partial' THEN 1 END) AS partial_count, "
                    "COUNT(CASE WHEN ac.extraction_suitability = 'unsuitable' THEN 1 END) AS unsuitable_count "
                    "FROM artifacts a "
                    "LEFT JOIN artifact_characterization ac ON a.id = ac.artifact_id "
                    "AND ac.characterization_version = '1.0.0'"
                )
                return dict(cur.fetchone())
    def save_canonical_document(self, document: CanonicalDocument) -> CanonicalDocument:
        """Persist a canonical document extraction result."""
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO canonical_documents "
                    "(artifact_id, processing_job_id, source_url, source_mime_type, detected_format, "
                    "extraction_status, canonical_text, structured_data, metadata, structure, "
                    "extraction_method, extraction_version, warnings, errors, original_checksum, "
                    "canonical_checksum, provenance, updated_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW()) "
                    "ON CONFLICT (artifact_id, extraction_version) DO UPDATE SET "
                    "processing_job_id = EXCLUDED.processing_job_id, "
                    "source_url = EXCLUDED.source_url, "
                    "source_mime_type = EXCLUDED.source_mime_type, "
                    "detected_format = EXCLUDED.detected_format, "
                    "extraction_status = EXCLUDED.extraction_status, "
                    "canonical_text = EXCLUDED.canonical_text, "
                    "structured_data = EXCLUDED.structured_data, "
                    "metadata = EXCLUDED.metadata, "
                    "structure = EXCLUDED.structure, "
                    "extraction_method = EXCLUDED.extraction_method, "
                    "extraction_version = EXCLUDED.extraction_version, "
                    "warnings = EXCLUDED.warnings, "
                    "errors = EXCLUDED.errors, "
                    "canonical_checksum = EXCLUDED.canonical_checksum, "
                    "provenance = EXCLUDED.provenance, "
                    "updated_at = NOW() "
                    "RETURNING id, artifact_id, processing_job_id, source_url, source_mime_type, "
                    "detected_format, extraction_status, canonical_text, structured_data, metadata, "
                    "structure, extraction_method, extraction_version, warnings, errors, "
                    "original_checksum, canonical_checksum, provenance, created_at, updated_at",
                    (
                        document.artifact_id,
                        document.processing_job_id,
                        document.source_url,
                        document.source_mime_type,
                        document.detected_format,
                        document.extraction_status,
                        document.canonical_text,
                        json.dumps(document.structured_data) if document.structured_data else None,
                        json.dumps(document.metadata),
                        json.dumps(document.structure) if document.structure else None,
                        document.extraction_method,
                        document.extraction_version,
                        json.dumps(document.warnings),
                        json.dumps(document.errors),
                        document.original_checksum,
                        document.canonical_checksum,
                        json.dumps(document.provenance),
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return CanonicalDocument(
                    id=row[0],
                    artifact_id=row[1],
                    processing_job_id=row[2],
                    source_url=row[3],
                    source_mime_type=row[4],
                    detected_format=row[5],
                    extraction_status=row[6],
                    canonical_text=row[7],
                    structured_data=row[8],
                    metadata=row[9],
                    structure=row[10],
                    extraction_method=row[11],
                    extraction_version=row[12],
                    warnings=row[13],
                    errors=row[14],
                    original_checksum=row[15],
                    canonical_checksum=row[16],
                    provenance=row[17],
                    created_at=row[18].isoformat() if row[18] else None,
                    updated_at=row[19].isoformat() if row[19] else None,
                )

    def get_canonical_document(self, artifact_id: str) -> dict[str, Any] | None:
        """Get the canonical document for an artifact."""
        with self.connect() as conn:
            with conn.cursor(row_factory=class_row(dict)) as cur:
                cur.execute(
                    "SELECT * FROM canonical_documents WHERE artifact_id = %s",
                    (artifact_id,),
                )
                row = cur.fetchone()
                return dict(row) if row else None
    def save_normalized_document(self, document: NormalizedDocument) -> NormalizedDocument:
        """Persist a normalized document."""
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO normalized_documents "
                    "(canonical_document_id, artifact_id, processing_job_id, source_url, "
                    "detected_format, normalization_version, normalization_operations, "
                    "normalized_text, original_checksum, normalized_checksum, content_changed, "
                    "quality_signals, warnings, errors, provenance, updated_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW()) "
                    "ON CONFLICT (canonical_document_id, normalization_version) DO UPDATE SET "
                    "processing_job_id = EXCLUDED.processing_job_id, "
                    "source_url = EXCLUDED.source_url, "
                    "detected_format = EXCLUDED.detected_format, "
                    "normalization_operations = EXCLUDED.normalization_operations, "
                    "normalized_text = EXCLUDED.normalized_text, "
                    "normalized_checksum = EXCLUDED.normalized_checksum, "
                    "content_changed = EXCLUDED.content_changed, "
                    "quality_signals = EXCLUDED.quality_signals, "
                    "warnings = EXCLUDED.warnings, "
                    "errors = EXCLUDED.errors, "
                    "provenance = EXCLUDED.provenance, "
                    "updated_at = NOW() "
                    "RETURNING id, canonical_document_id, artifact_id, processing_job_id, "
                    "source_url, detected_format, normalization_version, normalization_operations, "
                    "normalized_text, original_checksum, normalized_checksum, content_changed, "
                    "quality_signals, warnings, errors, provenance, created_at, updated_at",
                    (
                        document.canonical_document_id,
                        document.artifact_id,
                        document.processing_job_id,
                        document.source_url,
                        document.detected_format,
                        document.normalization_version,
                        json.dumps(document.normalization_operations),
                        document.normalized_text,
                        document.original_checksum,
                        document.normalized_checksum,
                        document.content_changed,
                        json.dumps(document.quality_signals),
                        json.dumps(document.warnings),
                        json.dumps(document.errors),
                        json.dumps(document.provenance),
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return NormalizedDocument(
                    id=row[0],
                    canonical_document_id=row[1],
                    artifact_id=row[2],
                    processing_job_id=row[3],
                    source_url=row[4],
                    detected_format=row[5],
                    normalization_version=row[6],
                    normalization_operations=row[7],
                    normalized_text=row[8],
                    original_checksum=row[9],
                    normalized_checksum=row[10],
                    content_changed=row[11],
                    quality_signals=row[12],
                    warnings=row[13],
                    errors=row[14],
                    provenance=row[15],
                    created_at=row[16].isoformat() if row[16] else None,
                    updated_at=row[17].isoformat() if row[17] else None,
                )

    def get_normalized_document(self, canonical_document_id: str, normalization_version: str = "1.0.0") -> dict[str, Any] | None:
        """Get a normalized document by canonical document ID and version."""
        with self.connect() as conn:
            with conn.cursor(row_factory=class_row(dict)) as cur:
                cur.execute(
                    "SELECT * FROM normalized_documents "
                    "WHERE canonical_document_id = %s AND normalization_version = %s",
                    (canonical_document_id, normalization_version),
                )
                row = cur.fetchone()
                return dict(row) if row else None

    def update_canonical_quality_signals(self, artifact_id: str, quality_signals: dict[str, Any]) -> None:
        """Update quality signals on the canonical document."""
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE canonical_documents "
                    "SET quality_signals = %s, updated_at = NOW() "
                    "WHERE artifact_id = %s",
                    (json.dumps(quality_signals), artifact_id),
                )
                conn.commit()

    def save_duplicate_group(self, group: DuplicateGroup) -> DuplicateGroup:
        """Persist a duplicate group."""
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO duplicate_groups "
                    "(duplicate_method, algorithm_version, algorithm_config, "
                    "representative_normalized_document_id, representative_canonical_document_id, "
                    "group_size, similarity_stats, warnings, errors, provenance) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                    "RETURNING id, duplicate_method, algorithm_version, algorithm_config, "
                    "representative_normalized_document_id, representative_canonical_document_id, "
                    "group_size, similarity_stats, warnings, errors, provenance, created_at, updated_at",
                    (
                        group.duplicate_method,
                        group.algorithm_version,
                        json.dumps(group.algorithm_config),
                        group.representative_normalized_document_id,
                        group.representative_canonical_document_id,
                        group.group_size,
                        json.dumps(group.similarity_stats),
                        json.dumps(group.warnings),
                        json.dumps(group.errors),
                        json.dumps(group.provenance),
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return DuplicateGroup(
                    id=row[0],
                    duplicate_method=row[1],
                    algorithm_version=row[2],
                    algorithm_config=row[3],
                    representative_normalized_document_id=row[4],
                    representative_canonical_document_id=row[5],
                    group_size=row[6],
                    similarity_stats=row[7],
                    warnings=row[8],
                    errors=row[9],
                    provenance=row[10],
                    created_at=row[11].isoformat() if row[11] else None,
                    updated_at=row[12].isoformat() if row[12] else None,
                )

    def save_duplicate_membership(self, membership: DuplicateMembership) -> DuplicateMembership:
        """Persist a duplicate membership."""
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO duplicate_memberships "
                    "(group_id, normalized_document_id, canonical_document_id, artifact_id, "
                    "comparison_method, similarity_score, is_representative, selection_basis, "
                    "warnings, errors, provenance) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                    "RETURNING id, group_id, normalized_document_id, canonical_document_id, artifact_id, "
                    "comparison_method, similarity_score, is_representative, selection_basis, "
                    "warnings, errors, provenance, created_at, updated_at",
                    (
                        membership.group_id,
                        membership.normalized_document_id,
                        membership.canonical_document_id,
                        membership.artifact_id,
                        membership.comparison_method,
                        membership.similarity_score,
                        membership.is_representative,
                        membership.selection_basis,
                        json.dumps(membership.warnings),
                        json.dumps(membership.errors),
                        json.dumps(membership.provenance),
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return DuplicateMembership(
                    id=row[0],
                    group_id=row[1],
                    normalized_document_id=row[2],
                    canonical_document_id=row[3],
                    artifact_id=row[4],
                    comparison_method=row[5],
                    similarity_score=row[6],
                    is_representative=row[7],
                    selection_basis=row[8],
                    warnings=row[9],
                    errors=row[10],
                    provenance=row[11],
                    created_at=row[12].isoformat() if row[12] else None,
                    updated_at=row[13].isoformat() if row[13] else None,
                )

    def get_duplicate_group(self, group_id: str) -> dict[str, Any] | None:
        """Get a duplicate group by ID."""
        with self.connect() as conn:
            with conn.cursor(row_factory=class_row(dict)) as cur:
                cur.execute(
                    "SELECT * FROM duplicate_groups WHERE id = %s",
                    (group_id,),
                )
                row = cur.fetchone()
                return dict(row) if row else None

    def get_duplicate_memberships(self, group_id: str) -> list[dict[str, Any]]:
        """Get all memberships for a duplicate group."""
        with self.connect() as conn:
            with conn.cursor(row_factory=class_row(dict)) as cur:
                cur.execute(
                    "SELECT * FROM duplicate_memberships WHERE group_id = %s ORDER BY created_at",
                    (group_id,),
                )
                return [dict(row) for row in cur.fetchall()]

    def get_all_duplicate_groups(self, duplicate_method: str | None = None) -> list[dict[str, Any]]:
        """Get all duplicate groups, optionally filtered by method."""
        with self.connect() as conn:
            with conn.cursor(row_factory=class_row(dict)) as cur:
                if duplicate_method:
                    cur.execute(
                        "SELECT * FROM duplicate_groups WHERE duplicate_method = %s ORDER BY created_at",
                        (duplicate_method,),
                    )
                else:
                    cur.execute("SELECT * FROM duplicate_groups ORDER BY created_at")
                return [dict(row) for row in cur.fetchall()]

    def clear_duplicate_data(self) -> None:
        """Clear all duplicate groups and memberships (for re-runs)."""
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM duplicate_memberships")
                cur.execute("DELETE FROM duplicate_groups")
                conn.commit()

    def create_dataset_specification(
        self,
        name: str,
        version: int,
        specification_hash: str,
        canonical_specification: dict[str, Any],
        status: str,
        description: str | None,
    ) -> DatasetSpecification:
        """Create a new dataset specification."""
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO dataset_specifications "
                    "(name, version, specification_hash, canonical_specification, status, description) "
                    "VALUES (%s, %s, %s, %s, %s, %s) "
                    "RETURNING id, name, version, specification_hash, canonical_specification, "
                    "status, description, created_at, updated_at",
                    (
                        name,
                        version,
                        specification_hash,
                        json.dumps(canonical_specification),
                        status,
                        description,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return DatasetSpecification(
                    id=row[0],
                    name=row[1],
                    version=row[2],
                    specification_hash=row[3],
                    canonical_specification=row[4],
                    status=row[5],
                    description=row[6],
                    created_at=row[7].isoformat() if row[7] else None,
                    updated_at=row[8].isoformat() if row[8] else None,
                )

    def get_dataset_specification(self, spec_id: str) -> DatasetSpecification | None:
        """Retrieve a specification by ID."""
        with self.connect() as conn:
            with conn.cursor(row_factory=class_row(dict)) as cur:
                cur.execute(
                    "SELECT * FROM dataset_specifications WHERE id = %s",
                    (spec_id,),
                )
                row = cur.fetchone()
                if row is None:
                    return None
                return DatasetSpecification(
                    id=row["id"],
                    name=row["name"],
                    version=row["version"],
                    specification_hash=row["specification_hash"],
                    canonical_specification=row["canonical_specification"],
                    status=row["status"],
                    description=row["description"],
                    created_at=row["created_at"].isoformat() if row["created_at"] else None,
                    updated_at=row["updated_at"].isoformat() if row["updated_at"] else None,
                )

    def list_dataset_specifications(self, status: str | None = None) -> list[DatasetSpecification]:
        """List specifications, optionally filtered by status."""
        with self.connect() as conn:
            with conn.cursor(row_factory=class_row(dict)) as cur:
                if status:
                    cur.execute(
                        "SELECT * FROM dataset_specifications WHERE status = %s ORDER BY created_at",
                        (status,),
                    )
                else:
                    cur.execute("SELECT * FROM dataset_specifications ORDER BY created_at")
                rows = cur.fetchall()
                return [
                    DatasetSpecification(
                        id=row["id"],
                        name=row["name"],
                        version=row["version"],
                        specification_hash=row["specification_hash"],
                        canonical_specification=row["canonical_specification"],
                        status=row["status"],
                        description=row["description"],
                        created_at=row["created_at"].isoformat() if row["created_at"] else None,
                        updated_at=row["updated_at"].isoformat() if row["updated_at"] else None,
                    )
                    for row in rows
                ]

    def get_dataset_specification_by_name_version(
        self, name: str, version: int
    ) -> DatasetSpecification | None:
        """Retrieve a specification by name and version."""
        with self.connect() as conn:
            with conn.cursor(row_factory=class_row(dict)) as cur:
                cur.execute(
                    "SELECT * FROM dataset_specifications WHERE name = %s AND version = %s",
                    (name, version),
                )
                row = cur.fetchone()
                if row is None:
                    return None
                return DatasetSpecification(
                    id=row["id"],
                    name=row["name"],
                    version=row["version"],
                    specification_hash=row["specification_hash"],
                    canonical_specification=row["canonical_specification"],
                    status=row["status"],
                    description=row["description"],
                    created_at=row["created_at"].isoformat() if row["created_at"] else None,
                    updated_at=row["updated_at"].isoformat() if row["updated_at"] else None,
                )

    def create_feasibility_report(self, report: FeasibilityReport) -> FeasibilityReport:
        """Persist a feasibility report."""
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO feasibility_reports "
                    "(specification_id, specification_hash, source_snapshot, records_considered, "
                    "eligible_count, rejection_counts, language_distribution, quality_distribution, "
                    "dedup_impact, blockers, warnings, feasibility, estimated_output_size_bytes) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                    "RETURNING id, specification_id, specification_hash, source_snapshot, "
                    "records_considered, eligible_count, rejection_counts, language_distribution, "
                    "quality_distribution, dedup_impact, blockers, warnings, feasibility, "
                    "estimated_output_size_bytes, created_at",
                    (
                        report.specification_id,
                        report.specification_hash,
                        report.source_snapshot,
                        report.records_considered,
                        report.eligible_count,
                        json.dumps(report.rejection_counts),
                        json.dumps(report.language_distribution),
                        json.dumps(report.quality_distribution),
                        json.dumps(report.dedup_impact),
                        json.dumps(report.blockers),
                        json.dumps(report.warnings),
                        report.feasibility,
                        report.estimated_output_size_bytes,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return FeasibilityReport(
                    id=row[0],
                    specification_id=row[1],
                    specification_hash=row[2],
                    source_snapshot=row[3],
                    records_considered=row[4],
                    eligible_count=row[5],
                    rejection_counts=row[6],
                    language_distribution=row[7],
                    quality_distribution=row[8],
                    dedup_impact=row[9],
                    blockers=row[10],
                    warnings=row[11],
                    feasibility=row[12],
                    estimated_output_size_bytes=row[13],
                    created_at=row[14].isoformat() if row[14] else None,
                )

    def get_feasibility_report(self, report_id: str) -> FeasibilityReport | None:
        """Retrieve a feasibility report by ID."""
        with self.connect() as conn:
            with conn.cursor(row_factory=class_row(dict)) as cur:
                cur.execute(
                    "SELECT * FROM feasibility_reports WHERE id = %s",
                    (report_id,),
                )
                row = cur.fetchone()
                if row is None:
                    return None
                return FeasibilityReport(
                    id=row["id"],
                    specification_id=row["specification_id"],
                    specification_hash=row["specification_hash"],
                    source_snapshot=row["source_snapshot"],
                    records_considered=row["records_considered"],
                    eligible_count=row["eligible_count"],
                    rejection_counts=row["rejection_counts"],
                    language_distribution=row["language_distribution"],
                    quality_distribution=row["quality_distribution"],
                    dedup_impact=row["dedup_impact"],
                    blockers=row["blockers"],
                    warnings=row["warnings"],
                    feasibility=row["feasibility"],
                    estimated_output_size_bytes=row["estimated_output_size_bytes"],
                    created_at=row["created_at"].isoformat() if row["created_at"] else None,
                )

    def list_feasibility_reports(self, specification_id: str | None = None) -> list[FeasibilityReport]:
        """List feasibility reports, optionally filtered by specification ID."""
        with self.connect() as conn:
            with conn.cursor(row_factory=class_row(dict)) as cur:
                if specification_id:
                    cur.execute(
                        "SELECT * FROM feasibility_reports WHERE specification_id = %s ORDER BY created_at",
                        (specification_id,),
                    )
                else:
                    cur.execute("SELECT * FROM feasibility_reports ORDER BY created_at")
                rows = cur.fetchall()
                return [
                    FeasibilityReport(
                        id=row["id"],
                        specification_id=row["specification_id"],
                        specification_hash=row["specification_hash"],
                        source_snapshot=row["source_snapshot"],
                        records_considered=row["records_considered"],
                        eligible_count=row["eligible_count"],
                        rejection_counts=row["rejection_counts"],
                        language_distribution=row["language_distribution"],
                        quality_distribution=row["quality_distribution"],
                        dedup_impact=row["dedup_impact"],
                        blockers=row["blockers"],
                        warnings=row["warnings"],
                        feasibility=row["feasibility"],
                        estimated_output_size_bytes=row["estimated_output_size_bytes"],
                        created_at=row["created_at"].isoformat() if row["created_at"] else None,
                    )
                    for row in rows
                ]

    def create_dataset_build(
        self,
        specification_id: str,
        specification_hash: str,
        status: str,
        records_considered: int,
        records_accepted: int,
        records_rejected: int,
        error_message: str | None,
    ) -> DatasetBuild:
        """Create or update a dataset build record."""
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO dataset_builds "
                    "(specification_id, specification_hash, status, records_considered, "
                    "records_accepted, records_rejected, error_message, started_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, NOW()) "
                    "RETURNING id, specification_id, specification_hash, status, "
                    "records_considered, records_accepted, records_rejected, "
                    "error_message, started_at, finished_at, created_at, updated_at",
                    (
                        specification_id,
                        specification_hash,
                        status,
                        records_considered,
                        records_accepted,
                        records_rejected,
                        error_message,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return DatasetBuild(
                    id=row[0],
                    specification_id=row[1],
                    specification_hash=row[2],
                    status=row[3],
                    records_considered=row[4],
                    records_accepted=row[5],
                    records_rejected=row[6],
                    error_message=row[7],
                    started_at=row[8].isoformat() if row[8] else None,
                    finished_at=row[9].isoformat() if row[9] else None,
                )

    def get_dataset_build(self, build_id: str) -> DatasetBuild | None:
        """Retrieve a dataset build by ID."""
        with self.connect() as conn:
            with conn.cursor(row_factory=class_row(dict)) as cur:
                cur.execute(
                    "SELECT * FROM dataset_builds WHERE id = %s",
                    (build_id,),
                )
                row = cur.fetchone()
                if row is None:
                    return None
                return DatasetBuild(
                    id=row["id"],
                    specification_id=row["specification_id"],
                    specification_hash=row["specification_hash"],
                    status=row["status"],
                    records_considered=row["records_considered"],
                    records_accepted=row["records_accepted"],
                    records_rejected=row["records_rejected"],
                    error_message=row["error_message"],
                    started_at=row["started_at"].isoformat() if row["started_at"] else None,
                    finished_at=row["finished_at"].isoformat() if row["finished_at"] else None,
                )

    def update_dataset_build_status(
        self,
        build_id: str,
        status: str,
        records_considered: int | None = None,
        records_accepted: int | None = None,
        records_rejected: int | None = None,
        error_message: str | None = None,
    ) -> None:
        """Update a dataset build's status and counts."""
        with self.connect() as conn:
            with conn.cursor() as cur:
                if status in ("accepted", "failed"):
                    cur.execute(
                        "UPDATE dataset_builds "
                        "SET status = %s, records_considered = %s, records_accepted = %s, "
                        "records_rejected = %s, error_message = %s, finished_at = NOW(), "
                        "updated_at = NOW() "
                        "WHERE id = %s",
                        (
                            status,
                            records_considered if records_considered is not None else 0,
                            records_accepted if records_accepted is not None else 0,
                            records_rejected if records_rejected is not None else 0,
                            error_message,
                            build_id,
                        ),
                    )
                else:
                    updates: list[str] = ["status = %s", "updated_at = NOW()"]
                    values: list[Any] = [status]
                    if records_considered is not None:
                        updates.append("records_considered = %s")
                        values.append(records_considered)
                    if records_accepted is not None:
                        updates.append("records_accepted = %s")
                        values.append(records_accepted)
                    if records_rejected is not None:
                        updates.append("records_rejected = %s")
                        values.append(records_rejected)
                    if error_message is not None:
                        updates.append("error_message = %s")
                        values.append(error_message)
                    cur.execute(
                        f"UPDATE dataset_builds SET {', '.join(updates)} WHERE id = %s",
                        (*values, build_id),
                    )
                conn.commit()

    def create_dataset_record(self, record: DatasetRecord) -> DatasetRecord:
        """Persist a dataset record."""
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO dataset_records "
                    "(build_id, specification_id, source_record_id, normalized_record_id, "
                    "canonical_record_id, raw_artifact_id, source_url, text, language, "
                    "quality_score, dedup_group_id, selection_reason) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                    "RETURNING id, build_id, specification_id, source_record_id, "
                    "normalized_record_id, canonical_record_id, raw_artifact_id, "
                    "source_url, text, language, quality_score, dedup_group_id, "
                    "selection_reason, created_at",
                    (
                        record.build_id,
                        record.specification_id,
                        record.source_record_id,
                        record.normalized_record_id,
                        record.canonical_record_id,
                        record.raw_artifact_id,
                        record.source_url,
                        record.text,
                        record.language,
                        record.quality_score,
                        record.dedup_group_id,
                        record.selection_reason,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return DatasetRecord(
                    id=row[0],
                    build_id=row[1],
                    specification_id=row[2],
                    source_record_id=row[3],
                    normalized_record_id=row[4],
                    canonical_record_id=row[5],
                    raw_artifact_id=row[6],
                    source_url=row[7],
                    text=row[8],
                    language=row[9],
                    quality_score=row[10],
                    dedup_group_id=row[11],
                    selection_reason=row[12],
                    created_at=row[13].isoformat() if row[13] else None,
                )

    def get_dataset_records(self, build_id: str) -> list[DatasetRecord]:
        """Retrieve all dataset records for a build."""
        with self.connect() as conn:
            with conn.cursor(row_factory=class_row(dict)) as cur:
                cur.execute(
                    "SELECT * FROM dataset_records WHERE build_id = %s ORDER BY created_at",
                    (build_id,),
                )
                rows = cur.fetchall()
                return [
                    DatasetRecord(
                        id=row["id"],
                        build_id=row["build_id"],
                        specification_id=row["specification_id"],
                        source_record_id=row["source_record_id"],
                        normalized_record_id=row["normalized_record_id"],
                        canonical_record_id=row["canonical_record_id"],
                        raw_artifact_id=row["raw_artifact_id"],
                        source_url=row["source_url"],
                        text=row["text"],
                        language=row["language"],
                        quality_score=row["quality_score"],
                        dedup_group_id=row["dedup_group_id"],
                        selection_reason=row["selection_reason"],
                        created_at=row["created_at"].isoformat() if row["created_at"] else None,
                    )
                    for row in rows
                ]

    def create_decision_record(self, decision: DecisionRecord) -> DecisionRecord:
        """Persist a decision record."""
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO decision_records "
                    "(build_id, record_id, decision, reason_codes, actual_values, "
                    "thresholds, representative_record_id, source_url) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
                    "RETURNING id, build_id, record_id, decision, reason_codes, "
                    "actual_values, thresholds, representative_record_id, source_url, created_at",
                    (
                        decision.build_id,
                        decision.record_id,
                        decision.decision,
                        json.dumps(decision.reason_codes),
                        json.dumps(decision.actual_values),
                        json.dumps(decision.thresholds),
                        decision.representative_record_id,
                        decision.source_url,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return DecisionRecord(
                    id=row[0],
                    build_id=row[1],
                    record_id=row[2],
                    decision=row[3],
                    reason_codes=row[4],
                    actual_values=row[5],
                    thresholds=row[6],
                    representative_record_id=row[7],
                    source_url=row[8],
                    created_at=row[9].isoformat() if row[9] else None,
                )

    def get_decision_records(self, build_id: str) -> list[DecisionRecord]:
        """Retrieve all decision records for a build."""
        with self.connect() as conn:
            with conn.cursor(row_factory=class_row(dict)) as cur:
                cur.execute(
                    "SELECT * FROM decision_records WHERE build_id = %s ORDER BY created_at",
                    (build_id,),
                )
                rows = cur.fetchall()
                return [
                    DecisionRecord(
                        id=row["id"],
                        build_id=row["build_id"],
                        record_id=row["record_id"],
                        decision=row["decision"],
                        reason_codes=row["reason_codes"],
                        actual_values=row["actual_values"],
                        thresholds=row["thresholds"],
                        representative_record_id=row["representative_record_id"],
                        source_url=row["source_url"],
                        created_at=row["created_at"].isoformat() if row["created_at"] else None,
                    )
                    for row in rows
                ]

    def create_validation_report(self, report: ValidationReport) -> ValidationReport:
        """Persist a validation report."""
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO validation_reports "
                    "(build_id, status, overall_status, checks, "
                    "error_count, warning_count, info_count) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s) "
                    "RETURNING id, build_id, status, overall_status, checks, "
                    "error_count, warning_count, info_count, created_at",
                    (
                        report.build_id,
                        report.status,
                        report.overall_status,
                        json.dumps(report.checks),
                        report.error_count,
                        report.warning_count,
                        report.info_count,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return ValidationReport(
                    id=row[0],
                    build_id=row[1],
                    status=row[2],
                    overall_status=row[3],
                    checks=row[4],
                    error_count=row[5],
                    warning_count=row[6],
                    info_count=row[7],
                    created_at=row[8].isoformat() if row[8] else None,
                )

    def get_validation_reports(self, build_id: str) -> list[ValidationReport]:
        """Retrieve validation reports for a build."""
        with self.connect() as conn:
            with conn.cursor(row_factory=class_row(dict)) as cur:
                cur.execute(
                    "SELECT * FROM validation_reports WHERE build_id = %s ORDER BY created_at",
                    (build_id,),
                )
                rows = cur.fetchall()
                return [
                    ValidationReport(
                        id=row["id"],
                        build_id=row["build_id"],
                        status=row["status"],
                        overall_status=row["overall_status"],
                        checks=row["checks"],
                        error_count=row["error_count"],
                        warning_count=row["warning_count"],
                        info_count=row["info_count"],
                        created_at=row["created_at"].isoformat() if row["created_at"] else None,
                    )
                    for row in rows
                ]
