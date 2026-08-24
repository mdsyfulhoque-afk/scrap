"""End-to-end Scenario B: Database -> Dataset."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.chdir("/run/media/farhan/New Volume/Projects/Data_Fetcher_Ubuntu_Phase2")
sys.path.insert(0, "src")

from data_fetcher.config import load_config
from data_fetcher.database import Database
from data_fetcher.storage import MinioStorage
from psycopg.rows import class_row
from data_fetcher.phase2.specification import DatasetSpecificationManager, SpecificationValidator
from data_fetcher.phase2.feasibility import FeasibilityEngine
from data_fetcher.phase2.dataset_builder import DatasetBuilder
from data_fetcher.phase2.validation import DatasetValidator
from data_fetcher.phase2.export import DatasetExporter
from data_fetcher.phase2.manifest import ManifestBuilder


def main() -> None:
    print("=" * 60)
    print("STEP 1: SETUP")
    print("=" * 60)

    config = load_config()
    db = Database(config.postgres_dsn)
    storage = MinioStorage(
        endpoint_url=config.minio_endpoint,
        access_key=config.minio_access_key,
        secret_key=config.minio_secret_key,
        bucket_name=config.minio_bucket,
    )
    spec_manager = DatasetSpecificationManager(db)
    feasibility_engine = FeasibilityEngine(db, spec_manager)
    dataset_builder = DatasetBuilder(db, spec_manager)
    dataset_validator = DatasetValidator(db)
    dataset_exporter = DatasetExporter(db, spec_manager)
    manifest_builder = ManifestBuilder()

    print(f"Database DSN: {config.postgres_dsn}")
    print(f"MinIO endpoint: {config.minio_endpoint}")
    print(f"MinIO bucket: {config.minio_bucket}")
    print("Setup complete.\n")

    print("=" * 60)
    print("STEP 2: LIST EXISTING DATABASE RECORDS")
    print("=" * 60)

    with db.connect() as conn:
        with conn.cursor(row_factory=class_row(dict)) as cur:
            cur.execute(
                "SELECT nd.id, nd.detected_format, LENGTH(nd.normalized_text) as text_len, "
                "cd.source_url, cd.extraction_status, cd.quality_signals "
                "FROM normalized_documents nd "
                "JOIN canonical_documents cd ON nd.canonical_document_id = cd.id "
                "ORDER BY nd.created_at"
            )
            normalized_docs = [dict(row) for row in cur.fetchall()]

    print(f"Existing normalized documents: {len(normalized_docs)}")
    for doc in normalized_docs:
        print(f"  id={doc['id']}, format={doc['detected_format']}, text_len={doc['text_len']}, status={doc['extraction_status']}")
    print()

    print("=" * 60)
    print("STEP 3: CREATE DATASET SPECIFICATION")
    print("=" * 60)

    spec_dict = {
        "dataset": {"name": "e2e-test-db", "version": 1},
        "source": {"allowed_formats": ["html", "plain_text", "text"]},
        "content": {"minimum_characters": 10, "maximum_characters": 50000},
        "quality": {"minimum_score": 0.5},
        "deduplication": {"mode": "normalized", "similarity_threshold": 0.85},
        "selection": {"maximum_records": 100},
        "output": {"format": "jsonl"},
    }

    validator = SpecificationValidator()
    errors = validator.validate(spec_dict)
    if errors:
        print(f"Specification validation errors: {errors}")
        sys.exit(1)
    print("Specification validated successfully.")

    specification = spec_manager.create_specification("e2e-test-db", spec_dict)
    print(f"Created specification: id={specification.id}, name={specification.name}, version={specification.version}")
    print(f"Specification hash: {specification.specification_hash}")
    print()

    print("=" * 60)
    print("STEP 4: RUN FEASIBILITY ANALYSIS")
    print("=" * 60)

    report = feasibility_engine.analyze(specification)
    print(f"Feasibility: {report.feasibility}")
    print(f"Records considered: {report.records_considered}")
    print(f"Eligible count: {report.eligible_count}")
    print(f"Rejection counts: {report.rejection_counts}")
    print(f"Blockers: {report.blockers}")
    print(f"Warnings: {report.warnings}")
    print(f"Language distribution: {report.language_distribution}")
    print(f"Quality distribution: {report.quality_distribution}")
    print(f"Dedup impact: {report.dedup_impact}")
    print()

    print("=" * 60)
    print("STEP 5: BUILD DATASET")
    print("=" * 60)

    build_result = dataset_builder.build(specification)
    print(f"Build ID: {build_result.build.id}")
    print(f"Build status: {build_result.build.status}")
    print(f"Statistics: {json.dumps(build_result.statistics, indent=2)}")
    print()

    print("=" * 60)
    print("STEP 6: VALIDATE DATASET")
    print("=" * 60)

    validation_report = dataset_validator.validate(build_result.build, build_result.accepted)
    print(f"Validation status: {validation_report.status}")
    print(f"Overall status: {validation_report.overall_status}")
    print(f"Error count: {validation_report.error_count}")
    print(f"Warning count: {validation_report.warning_count}")
    print(f"Info count: {validation_report.info_count}")
    for check in validation_report.checks:
        status = "PASS" if check["passed"] else "FAIL"
        print(f"  [{status}] {check['check_name']}: {check['message']}")
    print()

    print("=" * 60)
    print("STEP 7: EXPORT DATASET")
    print("=" * 60)

    output_dir = "output/e2e-test-db"
    export_result = dataset_exporter.export(
        build=build_result.build,
        output_dir=output_dir,
        records=build_result.accepted,
        rejected_decisions=build_result.rejected,
        validation=validation_report,
        specification=specification,
    )
    print(f"Export result: build_id={export_result.build_id}")
    print(f"Output directory: {export_result.output_dir}")
    print(f"Accepted count: {export_result.accepted_count}")
    print(f"Rejected count: {export_result.rejected_count}")
    print(f"Files: {export_result.files}")
    print()

    print("=" * 60)
    print("STEP 8: VERIFY OUTPUTS")
    print("=" * 60)

    expected_files = [
        "data.jsonl",
        "manifest.json",
        "statistics.json",
        "rejected.jsonl",
        "provenance.jsonl",
        "validation_report.json",
    ]

    all_exist = True
    for filename in expected_files:
        filepath = Path(output_dir) / filename
        exists = filepath.exists()
        non_empty = False
        size = 0
        if exists:
            size = filepath.stat().st_size
            non_empty = size > 0
        status = "OK" if (exists and non_empty) else "FAIL"
        if not (exists and non_empty):
            all_exist = False
        print(f"  [{status}] {filename}: exists={exists}, size={size} bytes")
    print()

    print("=" * 60)
    print("STEP 9: INSPECT RESULTS")
    print("=" * 60)

    stats_path = Path(output_dir) / "statistics.json"
    if stats_path.exists():
        with open(stats_path, "r", encoding="utf-8") as fh:
            stats = json.load(fh)
        print(f"Total records considered: {stats.get('records_considered', 'N/A')}")
        print(f"Accepted count: {stats.get('records_accepted', 'N/A')}")
        print(f"Rejected count: {stats.get('records_rejected', 'N/A')}")
        print(f"Rejection reason counts: {stats.get('reason_counts', {})}")
        print(f"Acceptance rate: {stats.get('acceptance_rate', 'N/A')}")

    val_path = Path(output_dir) / "validation_report.json"
    if val_path.exists():
        with open(val_path, "r", encoding="utf-8") as fh:
            val = json.load(fh)
        print(f"Validation status: {val.get('status', 'N/A')}")
        print(f"Validation overall_status: {val.get('overall_status', 'N/A')}")

    print("File sizes:")
    for filename in expected_files:
        filepath = Path(output_dir) / filename
        if filepath.exists():
            size = filepath.stat().st_size
            print(f"  {filename}: {size} bytes")
    print()

    print("=" * 60)
    print("E2E SCENARIO B COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
