from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ResourceRecord:
    id: str
    url: str
    normalized_url: str
    domain: str
    resource_type: str | None
    metadata: dict[str, Any]


@dataclass
class CrawlJobRecord:
    id: str
    name: str
    status: str
    config: dict[str, Any]
    started_at: str | None
    finished_at: str | None



@dataclass
class FetchRecord:
    id: str
    resource_id: str
    crawl_job_id: str | None
    status: str
    http_status: int | None
    content_type: str | None
    content_length: int | None
    headers: dict[str, Any]
    error_message: str | None
    started_at: str | None
    completed_at: str | None


@dataclass
class ArtifactRecord:
    id: str
    fetch_id: str
    storage_backend: str
    bucket_name: str
    object_key: str
    content_type: str | None
    size_bytes: int
    checksum_sha256: str
    metadata: dict[str, Any]
    license: str | None = None
    commercial_use_permitted: bool | None = None
    redistribution_permitted: bool | None = None
    attribution_required: bool | None = None
    rights_basis: str | None = None
    review_status: str = "requires_review"
    reviewed_by: str | None = None
    reviewed_at: str | None = None
    rights_notes: str | None = None


@dataclass
class FetchResult:
    url: str
    normalized_url: str
    domain: str
    status_code: int
    content_type: str | None
    resource_type: str
    content_length: int
    headers: dict[str, str]
    body: bytes
    checksum_sha256: str
    elapsed_seconds: float
    redirect_chain: list[str]


# Phase 2 Models

@dataclass
class ProcessingJobRecord:
    id: str
    name: str
    status: str
    config: dict[str, Any]
    source_artifact_id: str | None
    started_at: str | None
    finished_at: str | None
    error_message: str | None
    error_category: str | None
    created_at: str
    updated_at: str


@dataclass
class MaterializationResult:
    processing_job_id: str
    artifact_id: str
    resource_id: str
    fetch_id: str
    source_url: str
    raw_object_key: str
    raw_data: bytes
    checksum_sha256: str
    checksum_verified: bool
    materialized_at: str

@dataclass
class ArtifactCharacterization:
    id: str
    artifact_id: str
    characterization_version: str
    characterization_config: dict[str, Any]
    detected_format: str | None
    format_confidence: str | None
    format_evidence: dict[str, Any]
    mime_type: str | None
    file_extension: str | None
    encoding: str | None
    structural_type: str | None
    document_type_candidates: list[str]
    schema_summary: dict[str, Any] | None
    content_statistics: dict[str, Any]
    metadata_availability: dict[str, Any]
    extraction_suitability: str | None
    warnings: list[str]
    errors: list[str]
    is_deterministic: bool
    characterized_at: str
    created_at: str

@dataclass
class CanonicalDocument:
    id: str
    artifact_id: str
    processing_job_id: str | None
    source_url: str
    source_mime_type: str | None
    detected_format: str | None
    extraction_status: str
    canonical_text: str | None
    structured_data: dict[str, Any] | None
    metadata: dict[str, Any]
    structure: dict[str, Any] | None
    extraction_method: str
    extraction_version: str
    warnings: list[str]
    errors: list[str]
    original_checksum: str
    canonical_checksum: str | None
    provenance: dict[str, Any]
    created_at: str
    updated_at: str


@dataclass
class NormalizedDocument:
    id: str
    canonical_document_id: str
    artifact_id: str
    processing_job_id: str | None
    source_url: str
    detected_format: str | None
    normalization_version: str
    normalization_operations: list[dict[str, Any]]
    normalized_text: str | None
    original_checksum: str
    normalized_checksum: str | None
    content_changed: bool
    quality_signals: dict[str, Any]
    warnings: list[str]
    errors: list[str]
    provenance: dict[str, Any]
    created_at: str
    updated_at: str


@dataclass
class LanguageResult:
    language: str
    confidence: str
    method: str
    method_version: str
    warnings: list[str]
    errors: list[str]


@dataclass
class QualityResult:
    canonical_document_id: str
    artifact_id: str
    analysis_version: str
    text_metrics: dict[str, Any]
    content_composition: dict[str, Any]
    repetition_signals: dict[str, Any]
    completeness_signals: dict[str, Any]
    structured_data_signals: dict[str, Any] | None
    warnings: list[str]
    errors: list[str]
    created_at: str


@dataclass
class DuplicateGroup:
    id: str
    duplicate_method: str
    algorithm_version: str
    algorithm_config: dict[str, Any]
    representative_normalized_document_id: str | None
    representative_canonical_document_id: str | None
    group_size: int
    similarity_stats: dict[str, Any]
    warnings: list[str]
    errors: list[str]
    provenance: dict[str, Any]
    created_at: str
    updated_at: str


@dataclass
class DuplicateMembership:
    id: str
    group_id: str
    normalized_document_id: str | None
    canonical_document_id: str | None
    artifact_id: str | None
    comparison_method: str
    similarity_score: float | None
    is_representative: bool
    selection_basis: str | None
    warnings: list[str]
    errors: list[str]
    provenance: dict[str, Any]
    created_at: str
    updated_at: str


@dataclass
class DuplicateComparison:
    """Result of comparing two documents for duplication."""
    document_a_id: str
    document_b_id: str
    document_a_type: str
    document_b_type: str
    comparison_method: str
    similarity_score: float | None
    is_duplicate: bool
    duplicate_type: str | None
    jaccard_similarity: float | None
    min_hash_sketch_a: list[str] | None
    min_hash_sketch_b: list[str] | None
    shared_bands: int | None
    warnings: list[str]
    errors: list[str]


@dataclass
class DatasetSpecification:
    """Phase 2 dataset specification."""
    id: str
    name: str
    version: int
    specification_hash: str
    canonical_specification: dict[str, Any]
    status: str
    description: str | None
    created_at: str
    updated_at: str
@dataclass
class FeasibilityReport:
    id: str
    specification_id: str
    specification_hash: str
    source_snapshot: str
    records_considered: int
    eligible_count: int
    rejection_counts: dict[str, int]
    language_distribution: dict[str, int]
    quality_distribution: dict[str, Any]
    dedup_impact: dict[str, Any]
    blockers: list[str]
    warnings: list[str]
    feasibility: str
    estimated_output_size_bytes: int
    created_at: str


@dataclass
class FeasibilityStageResult:
    stage: str
    input_count: int
    output_count: int
    rejection_reasons: dict[str, int]
    details: dict[str, Any]



@dataclass
class DatasetBuild:
    id: str
    specification_id: str
    specification_hash: str
    status: str
    records_considered: int
    records_accepted: int
    records_rejected: int
    started_at: str
    finished_at: str | None
    error_message: str | None


@dataclass
class DatasetRecord:
    id: str
    build_id: str
    specification_id: str
    source_record_id: str
    normalized_record_id: str
    canonical_record_id: str
    raw_artifact_id: str
    source_url: str
    text: str
    language: str | None
    quality_score: float | None
    dedup_group_id: str | None
    selection_reason: str
    created_at: str


@dataclass
class DecisionRecord:
    id: str
    build_id: str
    record_id: str
    decision: str
    reason_codes: list[str]
    actual_values: dict[str, Any]
    thresholds: dict[str, Any]
    representative_record_id: str | None
    source_url: str
    created_at: str


@dataclass
class ValidationReport:
    id: str
    build_id: str
    status: str
    overall_status: str
    checks: list[dict[str, Any]]
    error_count: int
    warning_count: int
    info_count: int
    created_at: str


@dataclass
class DatasetBuildResult:
    build: DatasetBuild
    accepted: list[DatasetRecord]
    rejected: list[DecisionRecord]
    statistics: dict[str, Any]


@dataclass
class ExportResult:
    build_id: str
    output_dir: str
    accepted_count: int
    rejected_count: int
    files: dict[str, str]
    exported_at: str
