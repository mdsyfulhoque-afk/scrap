"""Phase 2: CLI commands for data inventory and inspection."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

from data_fetcher.config import load_config
from data_fetcher.database import Database, DatabaseError
from data_fetcher.phase2.discovery import DiscoveryConfig, FormatDiscovery
from data_fetcher.phase2.extraction import ExtractionConfig, ExtractionError, Extractor, create_processing_job_for_extraction
from data_fetcher.phase2.inventory import ArtifactAvailability, DataInventory, InventoryConfig, InventoryError
from data_fetcher.models import CanonicalDocument, DuplicateGroup, DuplicateMembership
from data_fetcher.storage import MinioStorage, StorageError
from data_fetcher.phase2.language import LanguageResult, detect_language
from data_fetcher.phase2.normalization import NormalizationConfig, Normalizer
from data_fetcher.phase2.quality import QualityAnalyzer, QualityConfig, QualityResult
from data_fetcher.phase2.deduplication import DocumentReference, DuplicateDetectionConfig, DuplicateDetectionResult, DuplicateDetector
from data_fetcher.phase2.feasibility import FeasibilityEngine, FeasibilityError

logger = logging.getLogger(__name__)


def _print_inventory(report: dict[str, Any]) -> None:
    """Print inventory report to stdout."""
    print("PHASE 2 DATA INVENTORY")
    print("=" * 60)
    print()

    stats = report.get("global_statistics", {})
    total = report.get("total_artifacts", 0)
    characterized = report.get("characterized_count", 0)
    failed = report.get("failed_count", 0)
    raw_available = report.get("raw_available", 0)
    raw_unavailable = report.get("raw_unavailable", 0)

    print("SOURCE AVAILABILITY")
    print("-" * 40)
    print(f"  Database artifacts:     {total}")
    print(f"  Raw artifacts available: {raw_available}")
    print(f"  Raw artifacts unavailable: {raw_unavailable}")
    print(f"  Characterized:          {characterized}")
    print(f"  Failed:                 {failed}")
    print(f"  Coverage:               {report.get('characterization_coverage', 0):.1%}")
    print()

    total_bytes = stats.get("total_bytes", 0)
    if total_bytes >= 1_073_741_824:
        size_str = f"{total_bytes / 1_073_741_824:.1f} GB"
    elif total_bytes >= 1_048_576:
        size_str = f"{total_bytes / 1_048_576:.1f} MB"
    elif total_bytes >= 1024:
        size_str = f"{total_bytes / 1024:.1f} KB"
    else:
        size_str = f"{total_bytes} B"
    print(f"Total raw data: {size_str}")
    print()

    print("Formats (detected, characterized only)")
    print("-" * 40)
    for fmt, count in sorted(report.get("format_distribution", {}).items(), key=lambda x: -x[1]):
        print(f"  {fmt:<20} {count}")
    print()

    print("MIME Types (declared, all artifacts)")
    print("-" * 40)
    for mime, count in sorted(report.get("mime_type_distribution", {}).items(), key=lambda x: -x[1])[:10]:
        print(f"  {mime:<40} {count}")
    print()

    format_conflicts = report.get("format_conflicts", [])
    if format_conflicts:
        print("FORMAT CONFLICTS")
        print("-" * 40)
        for conflict in format_conflicts[:10]:
            print(f"  {conflict['artifact_id']}")
            print(f"    Declared: {conflict['declared_mime']}")
            print(f"    Detected: {conflict['detected_format']} ({conflict['confidence']})")
        print()

    print("Domains")
    print("-" * 40)
    for domain, count in sorted(report.get("domain_distribution", {}).items(), key=lambda x: -x[1])[:10]:
        print(f"  {domain:<40} {count}")
    print()

    print("Size Distribution")
    print("-" * 40)
    for bucket, count in report.get("size_distribution", {}).items():
        print(f"  {bucket:<20} {count}")
    print()

    print("Encodings")
    print("-" * 40)
    for enc, count in sorted(report.get("encoding_distribution", {}).items(), key=lambda x: -x[1]):
        print(f"  {enc:<20} {count}")
    print()

    print("Structural Types")
    print("-" * 40)
    for stype, count in sorted(report.get("structural_type_distribution", {}).items(), key=lambda x: -x[1]):
        print(f"  {stype:<20} {count}")
    print()

    print("Extraction Suitability")
    print("-" * 40)
    for suit, count in sorted(report.get("extraction_suitability_distribution", {}).items(), key=lambda x: -x[1]):
        print(f"  {suit:<20} {count}")
    print()

    warnings = report.get("warnings_summary", [])
    if warnings:
        print("Warnings")
        print("-" * 40)
        for w in warnings[:10]:
            print(f"  {w['warning']:<40} {w['count']}")
        print()

    errors = report.get("errors_summary", [])
    if errors:
        print("Errors")
        print("-" * 40)
        for e in errors[:10]:
            print(f"  {e['error']:<40} {e['count']}")
        print()

    failed_list = report.get("failed_artifacts", [])
    if failed_list:
        print("Unavailable / Failed Artifacts")
        print("-" * 40)
        for f in failed_list[:10]:
            avail = f.get("availability", "unknown")
            print(f"  {f['artifact_id']} - {avail}")
        print()

    print("Characterization coverage:")
    print(f"  {characterized}/{total} ({report.get('characterization_coverage', 0):.1%})")
    print()


def _print_inspect(artifact: dict[str, Any], characterization: Any) -> None:
    """Print detailed artifact inspection to stdout."""
    print("ARTIFACT")
    print("-" * 40)
    print(f"ID:               {artifact.get('id', 'unknown')}")
    print(f"URL:              {artifact.get('resource_url', 'unknown')}")
    print(f"Domain:           {artifact.get('domain', 'unknown')}")
    print(f"MIME type:        {artifact.get('content_type', 'unknown')}")
    print(f"Size:             {artifact.get('size_bytes', 0)} bytes")
    print(f"Checksum:         {artifact.get('checksum_sha256', 'unknown')}")
    print(f"Created at:       {artifact.get('created_at', 'unknown')}")
    print()

    print("SOURCE AVAILABILITY")
    print("-" * 40)
    print(f"Raw data available:    yes (characterization succeeded)")
    print()

    print("ANALYSIS SCOPE")
    print("-" * 40)
    stats = characterization.content_statistics or {}
    total_bytes = stats.get("byte_count", 0)
    preview_bytes = stats.get("preview_byte_count", total_bytes)
    if total_bytes > preview_bytes:
        print(f"Total artifact bytes:  {total_bytes}")
        print(f"Bytes analyzed:        {preview_bytes}")
        print(f"Analysis scope:        preview ({preview_bytes} of {total_bytes} bytes)")
    else:
        print(f"Total artifact bytes:  {total_bytes}")
        print(f"Bytes analyzed:        {total_bytes}")
        print(f"Analysis scope:        full document")
    print()

    print("FORMAT DISCOVERY")
    print("-" * 40)
    print(f"Detected format:  {characterization.detected_format or 'unknown'}")
    print(f"Confidence:       {characterization.format_confidence or 'unknown'}")
    evidence = characterization.format_evidence
    sources = evidence.get("sources", []) if isinstance(evidence, dict) else []
    if sources:
        print("Evidence:")
        for src in sources:
            print(f"  - {src.get('source', 'unknown')}: {src.get('format', 'unknown')} ({src.get('confidence', 'unknown')})")
    print()

    print("STRUCTURE")
    print("-" * 40)
    print(f"Structural type:  {characterization.structural_type or 'unknown'}")
    if characterization.schema_summary:
        print("Schema summary:")
        print(f"  {json.dumps(characterization.schema_summary, indent=2)}")
    print()

    print("CONTENT (preview-based statistics)")
    print("-" * 40)
    stats = characterization.content_statistics or {}
    print(f"Characters:       {stats.get('character_count', 0)}")
    print(f"Lines:            {stats.get('line_count', 0)}")
    print(f"Words (estimate): {stats.get('word_count_estimate', 0)}")
    if "record_count" in stats:
        print(f"Records:          {stats['record_count']}")
    if "field_count" in stats:
        print(f"Fields:           {stats['field_count']}")
    if "column_count" in stats:
        print(f"Columns:          {stats['column_count']}")
    if "row_count" in stats:
        print(f"Rows:             {stats['row_count']}")
    print()

    print("PROVENANCE")
    print("-" * 40)
    print(f"Resource:         {artifact.get('resource_url', 'unknown')}")
    print(f"Fetch ID:         {artifact.get('fetch_id_val', 'unknown')}")
    print(f"HTTP status:      {artifact.get('http_status', 'unknown')}")
    print(f"Bucket:           {artifact.get('bucket_name', 'unknown')}")
    print(f"Object key:       {artifact.get('object_key', 'unknown')}")
    print()

    if characterization.document_type_candidates:
        print("DOCUMENT TYPES")
        print("-" * 40)
        for dt in characterization.document_type_candidates:
            print(f"  - {dt}")
        print()

    print("EXTRACTION SUITABILITY")
    print("-" * 40)
    print(f"Suitability:      {characterization.extraction_suitability or 'unknown'}")
    print()

    if characterization.warnings:
        print("WARNINGS")
        print("-" * 40)
        for w in characterization.warnings:
            print(f"  - {w}")
        print()

    if characterization.errors:
        print("ERRORS")
        print("-" * 40)
        for e in characterization.errors:
            if isinstance(e, dict):
                print(f"  - {e.get('category', 'unknown')}: {e.get('message', 'unknown')}")
            else:
                print(f"  - {e}")
        print()



def _print_quality(
    artifact: dict[str, Any],
    canonical_doc: dict[str, Any],
    quality_result: QualityResult,
    normalization_result: Any = None,
    language_result: LanguageResult | None = None,
) -> None:
    """Print quality analysis result to stdout."""
    print("ARTIFACT")
    print("-" * 40)
    print(f"ID:               {artifact.get('id', 'unknown')}")
    print(f"URL:              {artifact.get('resource_url', 'unknown')}")
    print(f"MIME type:        {artifact.get('content_type', 'unknown')}")
    print(f"Size:             {artifact.get('size_bytes', 0)} bytes")
    print()

    print("CANONICAL DOCUMENT")
    print("-" * 40)
    print(f"Extraction version: {canonical_doc.get('extraction_version', 'unknown')}")
    print(f"Canonical checksum: {canonical_doc.get('canonical_checksum', 'unknown')}")
    print(f"Detected format:    {canonical_doc.get('detected_format', 'unknown')}")
    print()

    if normalization_result:
        print("NORMALIZATION")
        print("-" * 40)
        print(f"Version:            {normalization_result.normalization_version}")
        print(f"Content changed:    {normalization_result.content_changed}")
        print(f"Operations:         {len(normalization_result.normalization_operations)}")
        if normalization_result.normalization_operations:
            for op in normalization_result.normalization_operations[:5]:
                print(f"  - {op.get('operation', 'unknown')}: {op.get('description', '')}")
        print(f"Normalized checksum: {normalization_result.normalized_checksum}")
        print()

    if language_result:
        print("LANGUAGE")
        print("-" * 40)
        print(f"Detected language:  {language_result.language}")
        print(f"Confidence:         {language_result.confidence}")
        print(f"Method:             {language_result.method}")
        print()

    print("TEXT METRICS")
    print("-" * 40)
    tm = quality_result.text_metrics
    print(f"Characters:         {tm.get('character_count', 0)}")
    print(f"Words:              {tm.get('word_count', 0)}")
    print(f"Lines:              {tm.get('line_count', 0)}")
    print(f"Estimated tokens:   {tm.get('estimated_token_count', 0)}")
    print(f"Avg word length:    {tm.get('avg_word_length', 0.0):.1f}")
    print(f"Avg line length:    {tm.get('avg_line_length', 0.0):.1f}")
    print()

    print("CONTENT COMPOSITION")
    print("-" * 40)
    cc = quality_result.content_composition
    print(f"Alphabetic ratio:   {cc.get('alphabetic_ratio', 0.0):.2%}")
    print(f"Numeric ratio:      {cc.get('numeric_ratio', 0.0):.2%}")
    print(f"Whitespace ratio:   {cc.get('whitespace_ratio', 0.0):.2%}")
    print(f"Punctuation ratio:  {cc.get('punctuation_ratio', 0.0):.2%}")
    print(f"Symbol ratio:       {cc.get('symbol_ratio', 0.0):.2%}")
    print(f"Unique char ratio:  {cc.get('unique_char_ratio', 0.0):.2%}")
    print()

    print("QUALITY SIGNALS")
    print("-" * 40)
    rs = quality_result.repetition_signals
    cs = quality_result.completeness_signals
    print(f"Repeated line ratio:    {rs.get('repeated_line_ratio', 0.0):.2%}")
    print(f"Repeated phrase ratio:  {rs.get('repeated_phrase_ratio', 0.0):.2%}")
    print(f"Vocabulary diversity:   {rs.get('vocabulary_diversity', 0.0):.2%}")
    print(f"Suspicious repetition:  {rs.get('suspicious_repetition', False)}")
    print(f"Is empty:               {cs.get('is_empty', False)}")
    print(f"Is short:               {cs.get('is_short', False)}")
    print(f"Has truncation:         {cs.get('has_truncation', False)}")
    print(f"Has malformed:          {cs.get('has_malformed_content', False)}")
    print(f"Extraction warnings:    {cs.get('extraction_warnings_count', 0)}")
    print()

    if quality_result.structured_data_signals:
        print("STRUCTURED DATA")
        print("-" * 40)
        sds = quality_result.structured_data_signals
        for key, value in sds.items():
            if key not in ("type", "format"):
                print(f"  {key}: {value}")
        print()

    if quality_result.warnings:
        print("WARNINGS")
        print("-" * 40)
        for w in quality_result.warnings:
            print(f"  - {w}")
        print()

    if quality_result.errors:
        print("ERRORS")
        print("-" * 40)
        for e in quality_result.errors:
            if isinstance(e, dict):
                print(f"  - {e.get('category', 'unknown')}: {e.get('message', 'unknown')}")
            else:
                print(f"  - {e}")
        print()


def _print_extract(artifact: dict[str, Any], result: ExtractionResult, canonical_doc: CanonicalDocument | None = None) -> None:
    """Print extraction result to stdout."""
    print("ARTIFACT")
    print("-" * 40)
    print(f"ID:               {artifact.get('id', 'unknown')}")
    print(f"URL:              {artifact.get('resource_url', 'unknown')}")
    print(f"MIME type:        {artifact.get('content_type', 'unknown')}")
    print(f"Size:             {artifact.get('size_bytes', 0)} bytes")
    print()

    print("EXTRACTION")
    print("-" * 40)
    print(f"Detected format:  {result.detected_format or 'unknown'}")
    print(f"Method:           {result.extraction_method}")
    print(f"Status:           {result.extraction_status}")
    print(f"Version:          {result.extraction_method}")
    print()

    if result.canonical_text is not None:
        text_len = len(result.canonical_text)
        print("CANONICAL TEXT")
        print("-" * 40)
        print(f"Characters:       {text_len}")
        print(f"Checksum:         {result.canonical_checksum}")
        preview = result.canonical_text[:500]
        if len(result.canonical_text) > 500:
            preview += "..."
        print(f"Preview:")
        print(f"  {preview}")
        print()

    if result.structured_data is not None:
        print("STRUCTURED DATA")
        print("-" * 40)
        print(f"Type:             {type(result.structured_data).__name__}")
        preview = json.dumps(result.structured_data, default=str, ensure_ascii=False)[:500]
        if len(json.dumps(result.structured_data, default=str, ensure_ascii=False)) > 500:
            preview += "..."
        print(f"Preview:")
        print(f"  {preview}")
        print()

    if result.structure:
        print("STRUCTURE")
        print("-" * 40)
        print(f"  {json.dumps(result.structure, default=str, ensure_ascii=False)[:300]}")
        print()

    if canonical_doc:
        print("STORED")
        print("-" * 40)
        print(f"Canonical document ID: {canonical_doc.id}")
        print(f"Saved at:              {canonical_doc.created_at}")
        print()

    if result.warnings:
        print("WARNINGS")
        print("-" * 40)
        for w in result.warnings:
            print(f"  - {w}")
        print()

    if result.errors:
        print("ERRORS")
        print("-" * 40)
        for e in result.errors:
            if isinstance(e, dict):
                print(f"  - {e.get('category', 'unknown')}: {e.get('message', 'unknown')}")
            else:
                print(f"  - {e}")
        print()



def _format_bytes(size: int) -> str:
    if size >= 1_073_741_824:
        return f"{size / 1_073_741_824:.1f} GB"
    elif size >= 1_048_576:
        return f"{size / 1_048_576:.1f} MB"
    elif size >= 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size} B"


def _print_feasibility(report, stages) -> None:
    """Print feasibility report to stdout."""
    print("PHASE 2 FEASIBILITY ANALYSIS")
    print("=" * 60)
    print()
    
    print("SPECIFICATION")
    print("-" * 40)
    print(f"Specification ID:   {report.specification_id}")
    print(f"Specification hash: {report.specification_hash}")
    print(f"Source snapshot:    {report.source_snapshot}")
    print(f"Feasibility:        {report.feasibility.upper()}")
    print()
    
    print("SUMMARY")
    print("-" * 40)
    print(f"Records considered: {report.records_considered}")
    print(f"Eligible records:   {report.eligible_count}")
    print(f"Estimated size:     {_format_bytes(report.estimated_output_size_bytes)}")
    print()
    
    if stages:
        print("STAGE RESULTS")
        print("-" * 40)
        for stage in stages:
            rejected = sum(stage.rejection_reasons.values())
            print(f"  {stage.stage:<12} input={stage.input_count:<6} output={stage.output_count:<6} rejected={rejected}")
        print()
    
    if report.rejection_counts:
        print("REJECTIONS")
        print("-" * 40)
        for reason, count in sorted(report.rejection_counts.items(), key=lambda x: -x[1]):
            print(f"  {reason:<40} {count}")
        print()
    
    if report.language_distribution:
        print("LANGUAGE DISTRIBUTION")
        print("-" * 40)
        for lang, count in sorted(report.language_distribution.items(), key=lambda x: -x[1]):
            print(f"  {lang:<20} {count}")
        print()
    
    if report.quality_distribution and report.quality_distribution.get("count", 0) > 0:
        print("QUALITY DISTRIBUTION")
        print("-" * 40)
        qd = report.quality_distribution
        print(f"  Count:            {qd.get('count', 0)}")
        print(f"  Avg chars:        {qd.get('avg_character_count', 0)}")
        print(f"  Total chars:      {qd.get('total_characters', 0)}")
        print()
    
    if report.dedup_impact and report.dedup_impact.get("mode") != "none":
        print("DEDUP IMPACT")
        print("-" * 40)
        di = report.dedup_impact
        print(f"  Mode:             {di.get('mode', 'unknown')}")
        print(f"  Estimated groups: {di.get('estimated_groups', 0)}")
        print(f"  Duplicate count:  {di.get('estimated_duplicate_count', 0)}")
        print()
    
    if report.blockers:
        print("BLOCKERS")
        print("-" * 40)
        for b in report.blockers:
            print(f"  - {b}")
        print()
    
    if report.warnings:
        print("WARNINGS")
        print("-" * 40)
        for w in report.warnings:
            print(f"  - {w}")
        print()


def cmd_inventory(args: list[str]) -> int:
    """Execute 'data-fetcher phase2 inventory'."""
    try:
        config = load_config()
    except EnvironmentError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1

    try:
        db = Database(config.postgres_dsn)
        storage = MinioStorage(
            endpoint_url=config.minio_endpoint,
            access_key=config.minio_access_key,
            secret_key=config.minio_secret_key,
            bucket_name=config.minio_bucket,
        )
    except Exception as exc:
        print(f"Failed to initialize: {exc}", file=sys.stderr)
        return 1

    discovery = FormatDiscovery(DiscoveryConfig())
    inventory = DataInventory(db, discovery, storage, InventoryConfig())

    try:
        report = inventory.inventory()
    except InventoryError as exc:
        print(f"Inventory failed: {exc}", file=sys.stderr)
        return 1

    _print_inventory(report)
    return 0


def cmd_inspect(args: list[str]) -> int:
    """Execute 'data-fetcher phase2 inspect <artifact-id>'."""
    if not args:
        print("Error: artifact-id is required", file=sys.stderr)
        print("Usage: data-fetcher phase2 inspect <artifact-id>", file=sys.stderr)
        return 2

    artifact_id = args[0]
    try:
        config = load_config()
    except EnvironmentError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1

    try:
        db = Database(config.postgres_dsn)
        storage = MinioStorage(
            endpoint_url=config.minio_endpoint,
            access_key=config.minio_access_key,
            secret_key=config.minio_secret_key,
            bucket_name=config.minio_bucket,
        )
    except Exception as exc:
        print(f"Failed to initialize: {exc}", file=sys.stderr)
        return 1

    discovery = FormatDiscovery(DiscoveryConfig())
    inventory = DataInventory(db, discovery, storage, InventoryConfig())

    try:
        artifact = inventory.get_artifact(artifact_id)
    except InventoryError as exc:
        print(f"Failed to retrieve artifact: {exc}", file=sys.stderr)
        return 1

    if not artifact:
        print(f"Artifact not found: {artifact_id}", file=sys.stderr)
        return 1

    try:
        characterization, availability = inventory.characterize_artifact(artifact)
    except InventoryError as exc:
        print(f"Characterization failed: {exc}", file=sys.stderr)
        return 1

    if not characterization:
        print(f"Failed to characterize artifact: {artifact_id}", file=sys.stderr)
        print(f"Availability: {availability.value}", file=sys.stderr)
        if availability == ArtifactAvailability.UNAVAILABLE:
            print("The raw object for this artifact is not available in object storage.", file=sys.stderr)
            print("The artifact record exists in PostgreSQL but the corresponding", file=sys.stderr)
            print("MinIO/S3 object could not be found or accessed.", file=sys.stderr)
        return 1

    try:
        inventory.save_characterization(characterization)
    except InventoryError as exc:
        print(f"Warning: failed to save characterization: {exc}", file=sys.stderr)

    _print_inspect(artifact, characterization)
    return 0


def _update_processing_job_status(db: Database, job_id: str, status: str, error_message: str | None = None, error_category: str | None = None) -> None:
    """Update processing job status."""
    import json
    with db.connect() as conn:
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


def cmd_extract(args: list[str]) -> int:
    """Execute 'data-fetcher phase2 extract <artifact-id>'."""
    if not args:
        print("Error: artifact-id is required", file=sys.stderr)
        print("Usage: data-fetcher phase2 extract <artifact-id>", file=sys.stderr)
        return 2

    artifact_id = args[0]
    try:
        config = load_config()
    except EnvironmentError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1

    try:
        db = Database(config.postgres_dsn)
        storage = MinioStorage(
            endpoint_url=config.minio_endpoint,
            access_key=config.minio_access_key,
            secret_key=config.minio_secret_key,
            bucket_name=config.minio_bucket,
        )
    except Exception as exc:
        print(f"Failed to initialize: {exc}", file=sys.stderr)
        return 1

    # Get artifact
    from data_fetcher.phase2.inventory import DataInventory, InventoryConfig
    discovery = FormatDiscovery(DiscoveryConfig())
    inventory = DataInventory(db, discovery, storage, InventoryConfig())
    
    try:
        artifact = inventory.get_artifact(artifact_id)
    except InventoryError as exc:
        print(f"Failed to retrieve artifact: {exc}", file=sys.stderr)
        return 1

    if not artifact:
        print(f"Artifact not found: {artifact_id}", file=sys.stderr)
        return 1

    # Get characterization
    characterization_data = db.get_characterization(artifact_id)
    if not characterization_data:
        print(f"No characterization found for artifact: {artifact_id}", file=sys.stderr)
        print("Run 'data-fetcher phase2 inventory' first.", file=sys.stderr)
        return 1
    from data_fetcher.models import ArtifactCharacterization
    characterization = ArtifactCharacterization(**characterization_data)

    # Create processing job
    try:
        job = create_processing_job_for_extraction(db, artifact_id, {"extraction_version": "1.0.0"})
    except Exception as exc:
        print(f"Failed to create processing job: {exc}", file=sys.stderr)
        return 1

    # Fetch raw data
    try:
        raw_data = storage.get_object(artifact["object_key"])
    except StorageError as exc:
        print(f"Failed to retrieve raw object: {exc}", file=sys.stderr)
        return 1

    # Extract
    extractor = Extractor(ExtractionConfig())
    try:
        result = extractor.extract(raw_data, characterization, job.id)
    except ExtractionError as exc:
        print(f"Extraction failed: {exc}", file=sys.stderr)
        return 1

    # Update processing job status
    try:
        if result.extraction_status == "completed":
            _update_processing_job_status(db, job.id, "completed")
        elif result.extraction_status in ("failed", "unsupported", "partial"):
            error_msg = "; ".join(e.get("message", str(e)) if isinstance(e, dict) else str(e) for e in result.errors)
            _update_processing_job_status(db, job.id, "failed", error_msg, result.extraction_status)
        else:
            _update_processing_job_status(db, job.id, "failed", "Unknown extraction status", "extraction_error")
    except Exception as exc:
        print(f"Warning: failed to update processing job status: {exc}", file=sys.stderr)

    # Build canonical document
    original_checksum = artifact.get("checksum_sha256", "")
    canonical_doc = CanonicalDocument(
        id="",
        artifact_id=artifact_id,
        processing_job_id=job.id,
        source_url=artifact.get("resource_url", ""),
        source_mime_type=artifact.get("content_type"),
        detected_format=characterization.detected_format,
        extraction_status=result.extraction_status,
        canonical_text=result.canonical_text,
        structured_data=result.structured_data,
        metadata=result.metadata,
        structure=result.structure,
        extraction_method=result.extraction_method,
        extraction_version="1.0.0",
        warnings=result.warnings,
        errors=result.errors,
        original_checksum=original_checksum,
        canonical_checksum=result.canonical_checksum,
        provenance={
            "artifact_id": artifact_id,
            "processing_job_id": str(job.id),
            "fetch_id": str(artifact.get("fetch_id_val")) if artifact.get("fetch_id_val") else None,
            "resource_id": str(artifact.get("resource_id")) if artifact.get("resource_id") else None,
            "resource_url": artifact.get("resource_url"),
            "bucket_name": artifact.get("bucket_name"),
            "object_key": artifact.get("object_key"),
        },
        created_at="",
        updated_at="",
    )

    # Persist
    try:
        saved_doc = db.save_canonical_document(canonical_doc)
    except Exception as exc:
        print(f"Failed to save canonical document: {exc}", file=sys.stderr)
        return 1

    _print_extract(artifact, result, saved_doc)
    return 0


def cmd_quality(args: list[str]) -> int:
    """Execute 'data-fetcher phase2 quality <artifact-id>'."""
    if not args:
        print("Error: artifact-id is required", file=sys.stderr)
        print("Usage: data-fetcher phase2 quality <artifact-id>", file=sys.stderr)
        return 2

    artifact_id = args[0]
    try:
        config = load_config()
    except EnvironmentError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1

    try:
        db = Database(config.postgres_dsn)
        storage = MinioStorage(
            endpoint_url=config.minio_endpoint,
            access_key=config.minio_access_key,
            secret_key=config.minio_secret_key,
            bucket_name=config.minio_bucket,
        )
    except Exception as exc:
        print(f"Failed to initialize: {exc}", file=sys.stderr)
        return 1

    # Get artifact
    discovery = FormatDiscovery(DiscoveryConfig())
    inventory = DataInventory(db, discovery, storage, InventoryConfig())
    
    try:
        artifact = inventory.get_artifact(artifact_id)
    except InventoryError as exc:
        print(f"Failed to retrieve artifact: {exc}", file=sys.stderr)
        return 1

    if not artifact:
        print(f"Artifact not found: {artifact_id}", file=sys.stderr)
        return 1

    # Get canonical document
    canonical_data = db.get_canonical_document(artifact_id)
    if not canonical_data:
        print(f"No canonical document found for artifact: {artifact_id}", file=sys.stderr)
        print("Run 'data-fetcher phase2 extract' first.", file=sys.stderr)
        return 1

    from data_fetcher.models import CanonicalDocument, DuplicateGroup, DuplicateMembership
    canonical_doc = CanonicalDocument(
        id=canonical_data["id"],
        artifact_id=canonical_data["artifact_id"],
        processing_job_id=canonical_data.get("processing_job_id"),
        source_url=canonical_data["source_url"],
        source_mime_type=canonical_data.get("source_mime_type"),
        detected_format=canonical_data.get("detected_format"),
        extraction_status=canonical_data["extraction_status"],
        canonical_text=canonical_data.get("canonical_text"),
        structured_data=canonical_data.get("structured_data"),
        metadata=canonical_data.get("metadata", {}),
        structure=canonical_data.get("structure"),
        extraction_method=canonical_data["extraction_method"],
        extraction_version=canonical_data["extraction_version"],
        warnings=canonical_data.get("warnings", []),
        errors=canonical_data.get("errors", []),
        original_checksum=canonical_data["original_checksum"],
        canonical_checksum=canonical_data.get("canonical_checksum"),
        provenance=canonical_data.get("provenance", {}),
        created_at=str(canonical_data.get("created_at", "")),
        updated_at=str(canonical_data.get("updated_at", "")),
    )

    # Run quality analysis
    analyzer = QualityAnalyzer(QualityConfig())
    quality_result = analyzer.analyze(canonical_doc)

    # Run language detection
    language_result = detect_language(canonical_doc.canonical_text or "")

    # Run normalization
    normalizer = Normalizer(NormalizationConfig())
    normalization_result = normalizer.normalize(canonical_doc)

    # Create processing job
    try:
        job = create_processing_job_for_extraction(db, artifact_id, {"quality_version": "1.0.0"})
    except Exception as exc:
        print(f"Failed to create processing job: {exc}", file=sys.stderr)
        return 1

    # Save normalized document
    from data_fetcher.models import NormalizedDocument
    normalized_doc = NormalizedDocument(
        id="",
        canonical_document_id=canonical_doc.id,
        artifact_id=artifact_id,
        processing_job_id=job.id,
        source_url=artifact.get("resource_url", ""),
        detected_format=canonical_doc.detected_format,
        normalization_version=normalization_result.normalization_version,
        normalization_operations=normalization_result.normalization_operations,
        normalized_text=normalization_result.normalized_text,
        original_checksum=normalization_result.original_checksum,
        normalized_checksum=normalization_result.normalized_checksum,
        content_changed=normalization_result.content_changed,
        quality_signals={
            "text_metrics": quality_result.text_metrics,
            "content_composition": quality_result.content_composition,
            "repetition_signals": quality_result.repetition_signals,
            "completeness_signals": quality_result.completeness_signals,
            "structured_data_signals": quality_result.structured_data_signals,
            "language": {
                "code": language_result.language,
                "confidence": language_result.confidence,
                "method": language_result.method,
                "method_version": language_result.method_version,
                "warnings": language_result.warnings,
                "errors": language_result.errors,
                "detected_at": datetime.now(timezone.utc).isoformat(),
            },
        },
        warnings=quality_result.warnings + normalization_result.warnings,
        errors=quality_result.errors + normalization_result.errors,
        provenance=normalization_result.provenance,
        created_at="",
        updated_at="",
    )

    try:
        saved_normalized = db.save_normalized_document(normalized_doc)
    except Exception as exc:
        print(f"Failed to save normalized document: {exc}", file=sys.stderr)
        return 1

    # Update canonical document quality signals
    try:
        db.update_canonical_quality_signals(
            artifact_id,
            {
                "text_metrics": quality_result.text_metrics,
                "content_composition": quality_result.content_composition,
                "repetition_signals": quality_result.repetition_signals,
                "completeness_signals": quality_result.completeness_signals,
                "structured_data_signals": quality_result.structured_data_signals,
                "language": {
                    "code": language_result.language,
                    "confidence": language_result.confidence,
                    "method": language_result.method,
                    "method_version": language_result.method_version,
                    "warnings": language_result.warnings,
                    "errors": language_result.errors,
                    "detected_at": datetime.now(timezone.utc).isoformat(),
                },
            },
        )
    except Exception as exc:
        print(f"Warning: failed to update canonical document quality signals: {exc}", file=sys.stderr)

    # Update processing job to completed
    try:
        _update_processing_job_status(db, job.id, "completed")
    except Exception as exc:
        print(f"Warning: failed to update processing job status: {exc}", file=sys.stderr)

    _print_quality(artifact, canonical_data, quality_result, normalization_result, language_result)
    print()
    print(f"Normalized document ID: {saved_normalized.id}")
    print(f"Saved at:               {saved_normalized.created_at}")
    return 0


def _print_deduplication(result: DuplicateDetectionResult) -> None:
    """Print deduplication result to stdout."""
    print("PHASE 2 DUPLICATE DETECTION")
    print("=" * 60)
    print()
    
    print("ALGORITHM")
    print("-" * 40)
    print(f"Version:            {result.algorithm_version}")
    print(f"Config:             {result.algorithm_config}")
    print()
    
    print("SUMMARY")
    print("-" * 40)
    print(f"Documents analyzed: {result.total_documents_analyzed}")
    print(f"Documents skipped:  {result.documents_skipped}")
    print(f"Raw exact groups:   {len(result.raw_exact_groups)}")
    print(f"Normalized exact groups: {len(result.normalized_exact_groups)}")
    print(f"Near-duplicate groups:   {len(result.near_duplicate_groups)}")
    print(f"Total groups:       {len(result.all_groups)}")
    print()
    
    if result.warnings:
        print("WARNINGS")
        print("-" * 40)
        for w in result.warnings:
            print(f"  - {w}")
        print()
    
    if result.errors:
        print("ERRORS")
        print("-" * 40)
        for e in result.errors:
            if isinstance(e, dict):
                print(f"  - {e.get('category', 'unknown')}: {e.get('message', 'unknown')}")
            else:
                print(f"  - {e}")
        print()
    
    print("DUPLICATE GROUPS")
    print("-" * 40)
    for i, group in enumerate(result.all_groups, 1):
        print(f"\nGroup {i}: [{group.duplicate_method}] (size: {group.group_size})")
        print(f"  Algorithm version: {group.algorithm_version}")
        print(f"  Group ID:          {group.id}")
        
        if group.representative_normalized_document_id:
            print(f"  Representative:    normalized_document {group.representative_normalized_document_id}")
        elif group.representative_canonical_document_id:
            print(f"  Representative:    canonical_document {group.representative_canonical_document_id}")
        else:
            print(f"  Representative:    (none)")
        
        if group.similarity_stats:
            print(f"  Similarity stats:  {group.similarity_stats}")
        
        # Show members
        group_members = [m for m in result.memberships if m.group_id == group.id]
        for membership in group_members:
            doc_label = "(unknown)"
            if membership.normalized_document_id:
                doc_label = f"normalized_document {membership.normalized_document_id}"
            elif membership.canonical_document_id:
                doc_label = f"canonical_document {membership.canonical_document_id}"
            elif membership.artifact_id:
                doc_label = f"artifact {membership.artifact_id}"
            
            rep_marker = " [REPRESENTATIVE]" if membership.is_representative else ""
            sim_score = f" (similarity: {membership.similarity_score:.2f})" if membership.similarity_score is not None else ""
            print(f"    - {doc_label}{rep_marker}{sim_score}")
    
    print()
    print("REPRESENTATIVE SELECTION")
    print("-" * 40)
    representative_count = sum(1 for m in result.memberships if m.is_representative)
    print(f"Total representatives: {representative_count}")
    print(f"Records if one per group: {len(result.all_groups)}")


def cmd_deduplicate(args: list[str]) -> int:
    """Execute 'data-fetcher phase2 deduplicate'."""
    # Parse optional threshold
    threshold = 0.85
    if args and args[0] == "--threshold":
        if len(args) < 2:
            print("Error: --threshold requires a value", file=sys.stderr)
            return 2
        try:
            threshold = float(args[1])
        except ValueError:
            print("Error: --threshold must be a float", file=sys.stderr)
            return 2
        args = args[2:]
    
    try:
        config = load_config()
    except EnvironmentError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1

    try:
        db = Database(config.postgres_dsn)
        storage = MinioStorage(
            endpoint_url=config.minio_endpoint,
            access_key=config.minio_access_key,
            secret_key=config.minio_secret_key,
            bucket_name=config.minio_bucket,
        )
    except Exception as exc:
        print(f"Failed to initialize: {exc}", file=sys.stderr)
        return 1

    # Clear previous duplicate data for idempotent re-runs
    try:
        db.clear_duplicate_data()
    except Exception as exc:
        print(f"Warning: failed to clear previous duplicate data: {exc}", file=sys.stderr)

    # Load all artifacts
    discovery = FormatDiscovery(DiscoveryConfig())
    inventory = DataInventory(db, discovery, storage, InventoryConfig())
    
    try:
        all_artifacts = inventory.get_all_artifacts()
    except InventoryError as exc:
        print(f"Failed to load artifacts: {exc}", file=sys.stderr)
        return 1

    # Build document references from normalized documents
    documents: list[DocumentReference] = []
    errors: list[str] = []
    
    for artifact in all_artifacts:
        artifact_id = artifact.get("id")
        if not artifact_id:
            continue
        
        # Get canonical document
        canonical_data = db.get_canonical_document(artifact_id)
        if not canonical_data:
            errors.append(f"No canonical document for artifact {artifact_id}")
            continue
        
        # Get normalized document
        normalized_data = db.get_normalized_document(canonical_data.get("id"))
        if not normalized_data:
            errors.append(f"No normalized document for artifact {artifact_id}")
            continue
        
        # Build quality score from quality_signals
        quality_score = 0.0
        warning_count = 0
        quality_signals = canonical_data.get("quality_signals", {})
        if quality_signals:
            text_metrics = quality_signals.get("text_metrics", {})
            if text_metrics:
                char_count = text_metrics.get("character_count", 0)
                quality_score = min(char_count / 1000.0, 1.0)  # Normalize to 0-1
            
            completeness = quality_signals.get("completeness_signals", {})
            if completeness:
                extraction_warnings = completeness.get("extraction_warnings_count", 0)
                warning_count += extraction_warnings
        
        doc = DocumentReference(
            document_id=artifact_id,
            document_type="normalized_document",
            normalized_checksum=normalized_data.get("normalized_checksum"),
            canonical_checksum=canonical_data.get("canonical_checksum"),
            raw_checksum=artifact.get("checksum_sha256"),
            normalized_text=normalized_data.get("normalized_text"),
            quality_score=quality_score,
            warning_count=warning_count,
            source_url=artifact.get("resource_url", ""),
            artifact_id=artifact_id,
            canonical_document_id=canonical_data.get("id"),
            normalized_document_id=normalized_data.get("id"),
        )
        documents.append(doc)
    
    if not documents:
        print("No documents available for duplicate detection.", file=sys.stderr)
        return 1
    
    # Run detection
    detector = DuplicateDetector(
        DuplicateDetectionConfig(
            algorithm_version="trigram-jaccard-1.0.0",
            jaccard_threshold=threshold,
        )
    )
    result = detector.detect(documents)
    result.created_at = ""
    result.errors.extend(errors)
    
    # Create processing job
    try:
        job = create_processing_job_for_extraction(db, None, {"deduplication_version": "1.0.0"})
    except Exception as exc:
        print(f"Failed to create processing job: {exc}", file=sys.stderr)
        return 1
    
    # Persist groups and memberships
    saved_groups: list[DuplicateGroup] = []
    saved_memberships: list[DuplicateMembership] = []
    
    # Create a mapping from temp group IDs to real IDs
    temp_to_real_group_id: dict[str, str] = {}
    
    for group in result.all_groups:
        try:
            saved_group = db.save_duplicate_group(group)
            temp_to_real_group_id[group.id] = saved_group.id
            
            # Update group with real ID and representative
            group.id = saved_group.id
            if saved_group.representative_normalized_document_id:
                group.representative_normalized_document_id = saved_group.representative_normalized_document_id
            if saved_group.representative_canonical_document_id:
                group.representative_canonical_document_id = saved_group.representative_canonical_document_id
            
            saved_groups.append(saved_group)
        except Exception as exc:
            result.errors.append(f"Failed to save group: {exc}")
    
    # Save memberships with real group IDs
    for membership in result.memberships:
        real_group_id = temp_to_real_group_id.get(membership.group_id)
        if not real_group_id:
            continue
        
        membership.group_id = real_group_id
        try:
            saved_membership = db.save_duplicate_membership(membership)
            saved_memberships.append(saved_membership)
        except Exception as exc:
            result.errors.append(f"Failed to save membership: {exc}")
    
    # Update processing job to completed
    try:
        _update_processing_job_status(db, job.id, "completed")
    except Exception as exc:
        print(f"Warning: failed to update processing job status: {exc}", file=sys.stderr)
    
    _print_deduplication(result)
    return 0



def cmd_feasibility(args: list[str]) -> int:
    """Execute 'data-fetcher phase2 feasibility <spec-name> [version]'."""
    if not args:
        print("Error: specification name is required", file=sys.stderr)
        print("Usage: data-fetcher phase2 feasibility <spec-name> [version]", file=sys.stderr)
        return 2

    spec_name = args[0]
    version = int(args[1]) if len(args) > 1 else 1

    try:
        config = load_config()
    except EnvironmentError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1

    try:
        db = Database(config.postgres_dsn)
    except Exception as exc:
        print(f"Failed to initialize: {exc}", file=sys.stderr)
        return 1

    from data_fetcher.phase2.specification import DatasetSpecificationManager, SpecificationError
    
    spec_manager = DatasetSpecificationManager(db)
    try:
        spec = spec_manager.get_specification_by_name_version(spec_name, version)
    except SpecificationError as exc:
        print(f"Failed to retrieve specification: {exc}", file=sys.stderr)
        return 1

    if not spec:
        print(f"Specification not found: {spec_name} v{version}", file=sys.stderr)
        return 1

    engine = FeasibilityEngine(db, spec_manager)
    try:
        report = engine.analyze(spec)
    except FeasibilityError as exc:
        print(f"Feasibility analysis failed: {exc}", file=sys.stderr)
        return 1

    # Persist report
    try:
        persisted = db.create_feasibility_report(report)
    except Exception as exc:
        print(f"Warning: failed to persist report: {exc}", file=sys.stderr)
        persisted = report

    stages = getattr(engine, '_last_stages', [])
    _print_feasibility(persisted, stages)
    return 0


def _init_dataset_services() -> tuple[Any, Any] | None:
    """Open a database handle and specification manager, or None on failure."""
    from data_fetcher.phase2.specification import DatasetSpecificationManager

    try:
        config = load_config()
    except EnvironmentError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return None

    try:
        db = Database(config.postgres_dsn)
    except Exception as exc:
        print(f"Failed to initialize database: {exc}", file=sys.stderr)
        return None

    return db, DatasetSpecificationManager(db)


def _resolve_specification(spec_manager: Any, name: str, version: int) -> Any | None:
    """Look up a specification by name and version, reporting failures to stderr."""
    from data_fetcher.phase2.specification import SpecificationError

    try:
        spec = spec_manager.get_specification_by_name_version(name, version)
    except SpecificationError as exc:
        print(f"Failed to retrieve specification: {exc}", file=sys.stderr)
        return None

    if not spec:
        print(f"Specification not found: {name} v{version}", file=sys.stderr)
        return None

    return spec


def _take_option(args: list[str], *names: str) -> tuple[str | None, list[str]]:
    """Extract the value of the first matching option, returning it and the rest."""
    remaining: list[str] = []
    value: str | None = None
    index = 0
    while index < len(args):
        token = args[index]
        if token in names:
            if index + 1 >= len(args):
                raise ValueError(f"{token} requires a value")
            value = args[index + 1]
            index += 2
            continue
        remaining.append(token)
        index += 1
    return value, remaining


def _print_specification(spec: Any) -> None:
    """Print a specification summary to stdout."""
    print(f"  id:          {spec.id}")
    print(f"  name:        {spec.name}")
    print(f"  version:     {spec.version}")
    print(f"  status:      {spec.status}")
    print(f"  hash:        {spec.specification_hash}")
    if spec.description:
        print(f"  description: {spec.description}")
    print(f"  created_at:  {spec.created_at}")


def cmd_spec(args: list[str]) -> int:
    """Execute 'data-fetcher phase2 spec <create|list|show> ...'."""
    if not args:
        print("Error: spec action required (create, list, show)", file=sys.stderr)
        return 2

    action, rest = args[0], args[1:]
    if action == "create":
        return _cmd_spec_create(rest)
    if action == "list":
        return _cmd_spec_list(rest)
    if action == "show":
        return _cmd_spec_show(rest)

    print(f"Error: unknown spec action '{action}'", file=sys.stderr)
    print("Actions: create, list, show", file=sys.stderr)
    return 2


def _cmd_spec_create(args: list[str]) -> int:
    """Create a specification from a JSON file."""
    from data_fetcher.phase2.specification import SpecificationError, SpecificationValidator

    try:
        spec_file, args = _take_option(args, "--file", "-f")
        description, args = _take_option(args, "--description")
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    if not args:
        print("Error: specification name is required", file=sys.stderr)
        print("Usage: data-fetcher phase2 spec create <name> --file <spec.json>", file=sys.stderr)
        return 2

    name = args[0]
    if not spec_file:
        print("Error: --file <spec.json> is required", file=sys.stderr)
        return 2

    try:
        with open(spec_file, "r", encoding="utf-8") as fh:
            spec_dict = json.load(fh)
    except OSError as exc:
        print(f"Error: cannot read {spec_file}: {exc}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print(f"Error: {spec_file} is not valid JSON: {exc}", file=sys.stderr)
        return 1

    errors = SpecificationValidator().validate(spec_dict)
    if errors:
        print("Specification validation failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    services = _init_dataset_services()
    if services is None:
        return 1
    _db, spec_manager = services

    try:
        spec = spec_manager.create_specification(name, spec_dict, description=description)
    except SpecificationError as exc:
        print(f"Failed to create specification ({exc.category}): {exc}", file=sys.stderr)
        return 1

    print("SPECIFICATION CREATED")
    print("=" * 60)
    _print_specification(spec)
    return 0


def _cmd_spec_list(args: list[str]) -> int:
    """List stored specifications."""
    from data_fetcher.phase2.specification import SpecificationError

    try:
        status, _rest = _take_option(args, "--status")
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    services = _init_dataset_services()
    if services is None:
        return 1
    _db, spec_manager = services

    try:
        specs = spec_manager.list_specifications(status)
    except SpecificationError as exc:
        print(f"Failed to list specifications: {exc}", file=sys.stderr)
        return 1

    print("DATASET SPECIFICATIONS")
    print("=" * 60)
    if not specs:
        print("  (none)")
        return 0

    print(f"  {'NAME':<28} {'VER':<5} {'STATUS':<12} HASH")
    print("  " + "-" * 58)
    for spec in specs:
        print(
            f"  {spec.name:<28} {spec.version:<5} {spec.status:<12} "
            f"{spec.specification_hash[:16]}"
        )
    print()
    print(f"Total: {len(specs)}")
    return 0


def _cmd_spec_show(args: list[str]) -> int:
    """Show a single specification including its canonical body."""
    if not args:
        print("Error: specification name is required", file=sys.stderr)
        print("Usage: data-fetcher phase2 spec show <name> [version]", file=sys.stderr)
        return 2

    name = args[0]
    try:
        version = int(args[1]) if len(args) > 1 else 1
    except ValueError:
        print("Error: version must be an integer", file=sys.stderr)
        return 2

    services = _init_dataset_services()
    if services is None:
        return 1
    _db, spec_manager = services

    spec = _resolve_specification(spec_manager, name, version)
    if spec is None:
        return 1

    print("DATASET SPECIFICATION")
    print("=" * 60)
    _print_specification(spec)
    print()
    print("Canonical specification")
    print("-" * 40)
    print(json.dumps(spec.canonical_specification, indent=2, sort_keys=True))
    return 0


def _print_build(build: Any, statistics: dict[str, Any]) -> None:
    """Print a dataset build summary to stdout."""
    print("DATASET BUILD")
    print("=" * 60)
    print(f"  build_id:           {build.id}")
    print(f"  specification_id:   {build.specification_id}")
    print(f"  specification_hash: {build.specification_hash}")
    print(f"  status:             {build.status}")
    print(f"  records considered: {build.records_considered}")
    print(f"  records accepted:   {build.records_accepted}")
    print(f"  records rejected:   {build.records_rejected}")
    if build.error_message:
        print(f"  error:              {build.error_message}")
    print()

    reasons = statistics.get("rejection_reason_counts") or {}
    if reasons:
        print("Rejection reasons")
        print("-" * 40)
        for reason, count in sorted(reasons.items(), key=lambda item: -item[1]):
            print(f"  {reason:<32} {count}")
        print()

    rate = statistics.get("acceptance_rate")
    if rate is not None:
        print(f"Acceptance rate: {rate:.1%}" if isinstance(rate, float) else f"Acceptance rate: {rate}")
        print()


def _print_validation(report: Any) -> None:
    """Print a validation report to stdout."""
    print("VALIDATION REPORT")
    print("=" * 60)
    print(f"  status:         {report.status}")
    print(f"  overall_status: {report.overall_status}")
    print(f"  errors:         {report.error_count}")
    print(f"  warnings:       {report.warning_count}")
    print(f"  info:           {report.info_count}")
    print()
    print("Checks")
    print("-" * 40)
    for check in report.checks:
        marker = "PASS" if check.get("passed") else check.get("severity", "fail").upper()
        print(f"  [{marker:<7}] {check.get('check_name')}: {check.get('message')}")
    print()


def _print_export(result: Any) -> None:
    """Print an export result to stdout."""
    print("EXPORT COMPLETE")
    print("=" * 60)
    print(f"  build_id:   {result.build_id}")
    print(f"  output_dir: {result.output_dir}")
    print(f"  accepted:   {result.accepted_count}")
    print(f"  rejected:   {result.rejected_count}")
    print()
    print("Files")
    print("-" * 40)
    for name, path in result.files.items():
        print(f"  {name:<24} {path}")
    print()


def cmd_build(args: list[str]) -> int:
    """Execute 'data-fetcher phase2 build <spec-name> [version]'."""
    from data_fetcher.phase2.dataset_builder import DatasetBuilder, DatasetBuilderError

    if not args:
        print("Error: specification name is required", file=sys.stderr)
        print("Usage: data-fetcher phase2 build <spec-name> [version]", file=sys.stderr)
        return 2

    name = args[0]
    try:
        version = int(args[1]) if len(args) > 1 else 1
    except ValueError:
        print("Error: version must be an integer", file=sys.stderr)
        return 2

    services = _init_dataset_services()
    if services is None:
        return 1
    db, spec_manager = services

    spec = _resolve_specification(spec_manager, name, version)
    if spec is None:
        return 1

    try:
        result = DatasetBuilder(db, spec_manager).build(spec)
    except DatasetBuilderError as exc:
        print(f"Build failed ({exc.category}): {exc}", file=sys.stderr)
        return 1

    _print_build(result.build, result.statistics)
    print(f"Next: data-fetcher phase2 validate {result.build.id}")
    return 0


def cmd_validate(args: list[str]) -> int:
    """Execute 'data-fetcher phase2 validate <build-id>'."""
    from data_fetcher.phase2.validation import DatasetValidator, ValidationError

    if not args:
        print("Error: build id is required", file=sys.stderr)
        print("Usage: data-fetcher phase2 validate <build-id>", file=sys.stderr)
        return 2

    build_id = args[0]
    services = _init_dataset_services()
    if services is None:
        return 1
    db, _spec_manager = services

    build, records, _decisions = _load_build(db, build_id)
    if build is None:
        return 1

    try:
        report = DatasetValidator(db).validate(build, records)
    except ValidationError as exc:
        print(f"Validation failed ({exc.category}): {exc}", file=sys.stderr)
        return 1

    _print_validation(report)
    if report.overall_status == "invalid":
        return 1
    return 0


def _load_build(db: Any, build_id: str) -> tuple[Any | None, list[Any], list[Any]]:
    """Load a build with its records and decisions. Returns (None, [], []) on failure."""
    try:
        build = db.get_dataset_build(build_id)
    except DatabaseError as exc:
        print(f"Failed to load build: {exc}", file=sys.stderr)
        return None, [], []

    if not build:
        print(f"Build not found: {build_id}", file=sys.stderr)
        return None, [], []

    try:
        records = db.get_dataset_records(build_id)
        decisions = db.get_decision_records(build_id)
    except DatabaseError as exc:
        print(f"Failed to load build contents: {exc}", file=sys.stderr)
        return None, [], []

    return build, records, decisions


def cmd_export(args: list[str]) -> int:
    """Execute 'data-fetcher phase2 export <build-id> --output <dir>'."""
    from data_fetcher.phase2.export import DatasetExporter, ExportError

    try:
        output_dir, args = _take_option(args, "--output", "-o")
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    if not args:
        print("Error: build id is required", file=sys.stderr)
        print("Usage: data-fetcher phase2 export <build-id> --output <dir>", file=sys.stderr)
        return 2

    build_id = args[0]
    if not output_dir:
        print("Error: --output <dir> is required", file=sys.stderr)
        return 2

    services = _init_dataset_services()
    if services is None:
        return 1
    db, spec_manager = services

    build, records, decisions = _load_build(db, build_id)
    if build is None:
        return 1

    rejected = [d for d in decisions if d.decision != "accepted"]

    validation = None
    try:
        reports = db.get_validation_reports(build_id)
        if reports:
            validation = reports[-1]
    except DatabaseError as exc:
        print(f"Warning: failed to load validation report: {exc}", file=sys.stderr)

    if validation is None:
        print(
            "Warning: no validation report found for this build; "
            "validation_report.json will record 'not_validated'",
            file=sys.stderr,
        )

    try:
        specification = spec_manager.get_specification(build.specification_id)
    except Exception as exc:
        print(f"Warning: failed to load specification: {exc}", file=sys.stderr)
        specification = None

    try:
        result = DatasetExporter(db, spec_manager).export(
            build=build,
            output_dir=output_dir,
            records=records,
            rejected_decisions=rejected,
            validation=validation,
            specification=specification,
        )
    except ExportError as exc:
        print(f"Export failed ({exc.category}): {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"Export failed: {exc}", file=sys.stderr)
        return 1

    _print_export(result)
    return 0


def cmd_run(args: list[str]) -> int:
    """Execute 'data-fetcher phase2 run <spec-name> [version] --output <dir>'.

    Chains feasibility -> build -> validate -> export in one pass.
    """
    from data_fetcher.phase2.dataset_builder import DatasetBuilder, DatasetBuilderError
    from data_fetcher.phase2.export import DatasetExporter, ExportError
    from data_fetcher.phase2.validation import DatasetValidator, ValidationError

    try:
        output_dir, args = _take_option(args, "--output", "-o")
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    allow_invalid = "--allow-invalid" in args
    skip_feasibility = "--skip-feasibility" in args
    args = [a for a in args if a not in ("--allow-invalid", "--skip-feasibility")]

    if not args:
        print("Error: specification name is required", file=sys.stderr)
        print(
            "Usage: data-fetcher phase2 run <spec-name> [version] --output <dir> "
            "[--skip-feasibility] [--allow-invalid]",
            file=sys.stderr,
        )
        return 2

    name = args[0]
    try:
        version = int(args[1]) if len(args) > 1 else 1
    except ValueError:
        print("Error: version must be an integer", file=sys.stderr)
        return 2

    if not output_dir:
        print("Error: --output <dir> is required", file=sys.stderr)
        return 2

    services = _init_dataset_services()
    if services is None:
        return 1
    db, spec_manager = services

    spec = _resolve_specification(spec_manager, name, version)
    if spec is None:
        return 1

    if not skip_feasibility:
        print("STAGE 1/4 — FEASIBILITY")
        engine = FeasibilityEngine(db, spec_manager)
        try:
            report = engine.analyze(spec)
        except FeasibilityError as exc:
            print(f"Feasibility analysis failed: {exc}", file=sys.stderr)
            return 1
        try:
            report = db.create_feasibility_report(report)
        except Exception as exc:
            print(f"Warning: failed to persist feasibility report: {exc}", file=sys.stderr)
        _print_feasibility(report, getattr(engine, "_last_stages", []))
        if report.feasibility in ("fail", "blocked") and not allow_invalid:
            print(
                f"Specification is not feasible ({report.feasibility}); aborting. "
                "Re-run with --allow-invalid to build anyway.",
                file=sys.stderr,
            )
            return 1

    print("STAGE 2/4 — BUILD")
    try:
        result = DatasetBuilder(db, spec_manager).build(spec)
    except DatasetBuilderError as exc:
        print(f"Build failed ({exc.category}): {exc}", file=sys.stderr)
        return 1
    _print_build(result.build, result.statistics)

    print("STAGE 3/4 — VALIDATE")
    try:
        validation = DatasetValidator(db).validate(result.build, result.accepted)
    except ValidationError as exc:
        print(f"Validation failed ({exc.category}): {exc}", file=sys.stderr)
        return 1
    _print_validation(validation)

    if validation.overall_status == "invalid" and not allow_invalid:
        print(
            "Dataset failed validation; export skipped. "
            "Re-run with --allow-invalid to export anyway.",
            file=sys.stderr,
        )
        return 1

    print("STAGE 4/4 — EXPORT")
    try:
        export_result = DatasetExporter(db, spec_manager).export(
            build=result.build,
            output_dir=output_dir,
            records=result.accepted,
            rejected_decisions=result.rejected,
            validation=validation,
            specification=spec,
        )
    except (ExportError, OSError) as exc:
        print(f"Export failed: {exc}", file=sys.stderr)
        return 1
    _print_export(export_result)

    return 0


_PHASE2_SUBCOMMANDS = (
    "inventory, inspect, extract, quality, deduplicate, "
    "spec, feasibility, build, validate, export, run"
)


def run_phase2(args: list[str]) -> int:
    """
    Dispatch Phase 2 subcommands.
    
    Args:
        args: Arguments after 'phase2', e.g. ['inventory'] or ['inspect', '<id>']
    """
    if not args:
        print("Error: phase2 subcommand required", file=sys.stderr)
        print(f"Subcommands: {_PHASE2_SUBCOMMANDS}", file=sys.stderr)
        return 2

    subcommand = args[0]
    sub_args = args[1:]

    if subcommand == "inventory":
        return cmd_inventory(sub_args)
    elif subcommand == "inspect":
        return cmd_inspect(sub_args)
    elif subcommand == "extract":
        return cmd_extract(sub_args)
    elif subcommand == "quality":
        return cmd_quality(sub_args)
    elif subcommand == "deduplicate":
        return cmd_deduplicate(sub_args)
    elif subcommand == "spec":
        return cmd_spec(sub_args)
    elif subcommand == "feasibility":
        return cmd_feasibility(sub_args)
    elif subcommand == "build":
        return cmd_build(sub_args)
    elif subcommand == "validate":
        return cmd_validate(sub_args)
    elif subcommand == "export":
        return cmd_export(sub_args)
    elif subcommand == "run":
        return cmd_run(sub_args)
    else:
        print(f"Error: unknown subcommand '{subcommand}'", file=sys.stderr)
        print(f"Subcommands: {_PHASE2_SUBCOMMANDS}", file=sys.stderr)
        return 2
