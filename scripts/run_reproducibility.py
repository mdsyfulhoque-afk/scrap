"""Task 4: Verify reproducibility of the Data_Fetcher_Ubuntu e2e-test build.

Run 1 outputs already exist at output/e2e-test (produced by a previous run of
the e2e scenario). This script re-runs the e2e build pipeline (feasibility ->
build -> validate -> export) against the SAME e2e-test specification into a
separate directory (output/e2e-test-run2), then compares rejected.jsonl and
manifest.json between run 1 and run 2, reporting any differences.

Note: fresh runs assign new UUIDs and timestamps, so the comparison ignores
those non-deterministic fields and focuses on the reproducible decision content
and governance metadata.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = "/run/media/farhan/New Volume/Projects/Data_Fetcher_Ubuntu_Phase2"
RUN1_DIR = Path(ROOT) / "output" / "e2e-test"
RUN2_DIR = Path(ROOT) / "output" / "e2e-test-run2"

os.chdir(ROOT)
sys.path.insert(0, "src")

from data_fetcher.config import load_config
from data_fetcher.database import Database
from data_fetcher.phase2.specification import DatasetSpecificationManager
from data_fetcher.phase2.feasibility import FeasibilityEngine
from data_fetcher.phase2.dataset_builder import DatasetBuilder
from data_fetcher.phase2.validation import DatasetValidator
from data_fetcher.phase2.export import DatasetExporter
from data_fetcher.phase2.manifest import ManifestBuilder

# Fields that are expected to change between runs (UUIDs / timestamps).
VOLATILE_MANIFEST_KEYS = {
    "dataset_build_id",
    "created_at",
    "build",            # nested: id, started_at, finished_at
}


def build_again() -> None:
    config = load_config()
    db = Database(config.postgres_dsn)
    spec_manager = DatasetSpecificationManager(db)
    feasibility_engine = FeasibilityEngine(db, spec_manager)
    dataset_builder = DatasetBuilder(db, spec_manager)
    dataset_validator = DatasetValidator(db)
    dataset_exporter = DatasetExporter(db, spec_manager)
    ManifestBuilder()

    spec = db.get_dataset_specification_by_name_version("e2e-test", 1)
    if spec is None:
        raise SystemExit("FAIL: e2e-test specification not found; cannot rebuild.")

    print(f"Reusing specification: id={spec.id} name={spec.name} v{spec.version}")

    report = feasibility_engine.analyze(spec)
    print(f"Feasibility: {report.feasibility} | "
          f"considered={report.records_considered} eligible={report.eligible_count}")

    build_result = dataset_builder.build(spec)
    print(f"Build: id={build_result.build.id} status={build_result.build.status} "
          f"accepted={len(build_result.accepted)} rejected={len(build_result.rejected)}")

    validation_report = dataset_validator.validate(build_result.build, build_result.accepted)
    print(f"Validation: status={validation_report.status} "
          f"overall={validation_report.overall_status}")

    export_result = dataset_exporter.export(
        build=build_result.build,
        output_dir=str(RUN2_DIR),
        records=build_result.accepted,
        rejected_decisions=build_result.rejected,
        validation=validation_report,
        specification=spec,
    )
    print(f"Export -> {export_result.output_dir} "
          f"(accepted={export_result.accepted_count}, rejected={export_result.rejected_count})")


def _read_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _normalize_rejected(rows: list[dict]) -> list[dict]:
    volatile = {"id", "build_id", "created_at"}
    return [{k: v for k, v in r.items() if k not in volatile} for r in rows]


def _compare_manifests(m1: dict, m2: dict):
    """Return (diffs, reconciled_pass) where diffs lists only meaningful diffs."""
    diffs = []

    def recurse(a, b, path):
        for key in a:
            p = f"{path}.{key}" if path else key
            if key in VOLATILE_MANIFEST_KEYS:
                continue
            if key == "id":  # generated primary-key UUIDs are non-deterministic
                continue
            if key not in b:
                diffs.append(f"  missing in run2: {p}")
                continue
            if isinstance(a[key], dict) and isinstance(b[key], dict):
                recurse(a[key], b[key], p)
            elif a[key] != b[key]:
                diffs.append(f"  {p}: run1={a[key]!r} run2={b[key]!r}")

    recurse(m1, m2, "")
    # also flag keys present in run2 but not run1 (outside volatile)
    for key in m2:
        if key in VOLATILE_MANIFEST_KEYS:
            continue
        if key not in m1:
            diffs.append(f"  missing in run1: {key}")
    return diffs


def main() -> int:
    print("=" * 70)
    print("TASK 4: REPRODUCIBILITY")
    print("=" * 70)

    if not RUN1_DIR.exists():
        print(f"FAIL: run 1 directory missing: {RUN1_DIR}")
        return 1

    print("STEP 1: Run scenario A build again (into output/e2e-test-run2)")
    print("-" * 70)
    build_again()
    print()

    print("STEP 2: Compare rejected.jsonl (run 1 vs run 2)")
    print("-" * 70)
    r1 = _read_jsonl(RUN1_DIR / "rejected.jsonl")
    r2 = _read_jsonl(RUN2_DIR / "rejected.jsonl")
    n1, n2 = _normalize_rejected(r1), _normalize_rejected(r2)
    print(f"  run1 records: {len(r1)} | run2 records: {len(r2)}")
    rejected_match = (n1 == n2)
    if rejected_match:
        print("  [PASS] normalized rejected decision content is identical "
              "(decision, reason_codes, actual_values, thresholds, "
              "representative_record_id, source_url)")
    else:
        print("  [FAIL] rejected decision content differs:")
        for i, (a, b) in enumerate(zip(n1, n2)):
            if a != b:
                print(f"    record {i}: run1={a}\n                 run2={b}")

    print("\nSTEP 3: Compare manifest.json (run 1 vs run 2)")
    print("-" * 70)
    m1 = json.loads((RUN1_DIR / "manifest.json").read_text())
    m2 = json.loads((RUN2_DIR / "manifest.json").read_text())
    diffs = _compare_manifests(m1, m2)
    # Report volatile (expected) differences for transparency
    print(f"  dataset_build_id: run1={m1.get('dataset_build_id')} "
          f"run2={m2.get('dataset_build_id')} (expected to differ)")
    print(f"  created_at:       run1={m1.get('created_at')} "
          f"run2={m2.get('created_at')} (expected to differ)")
    if diffs:
        print("  [FAIL] meaningful manifest differences found:")
        for d in diffs:
            print(d)
    else:
        print("  [PASS] all meaningful manifest fields are identical between runs")

    print("\nSTEP 4: Differences report")
    print("-" * 70)
    overall_pass = rejected_match and not diffs
    print(f"  rejected.jsonl reproducible: {'YES' if rejected_match else 'NO'}")
    print(f"  manifest.json reproducible:  {'YES' if not diffs else 'NO'}")
    print(f"  Volatile (expected) diffs:    dataset_build_id, created_at, "
          f"build.id/started_at/finished_at")
    print(f"\n  SUMMARY: {'REPRODUCIBLE - PASS' if overall_pass else 'NOT REPRODUCIBLE - FAIL'}")

    print("\n" + "=" * 70)
    print(f"TASK 4 RESULT: {'PASS' if overall_pass else 'FAIL'}")
    print("=" * 70)
    return 0 if overall_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
