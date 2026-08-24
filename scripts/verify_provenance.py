"""Task 2: Verify provenance traceability for the Data_Fetcher_Ubuntu e2e-test build.

Reads output/e2e-test/provenance.jsonl and traces the lineage of the first 3
records: dataset_record_id, source_record_id, normalized_record_id,
canonical_record_id, raw_artifact_id, source_url. Verifies that all lineage
fields that should carry data are populated (no empty strings / nulls where
data is expected).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = "/run/media/farhan/New Volume/Projects/Data_Fetcher_Ubuntu_Phase2"
PROVENANCE_PATH = Path(ROOT) / "output" / "e2e-test" / "provenance.jsonl"

# Map the required lineage field names to the keys used in provenance.jsonl.
# "dataset_record_id" is stored as "record_id" in the export.
FIELD_MAP = {
    "dataset_record_id": "record_id",
    "source_record_id": "source_record_id",
    "normalized_record_id": "normalized_record_id",
    "canonical_record_id": "canonical_record_id",
    "raw_artifact_id": "raw_artifact_id",
    "source_url": "source_url",
}

# Fields that must always be populated for a complete lineage chain.
REQUIRED_FIELDS = list(FIELD_MAP.keys())


def main() -> int:
    print("=" * 70)
    print("TASK 2: PROVENANCE TRACEABILITY")
    print("=" * 70)
    print(f"Provenance file: {PROVENANCE_PATH}\n")

    if not PROVENANCE_PATH.exists():
        print(f"FAIL: provenance file not found at {PROVENANCE_PATH}")
        return 1

    records = []
    with PROVENANCE_PATH.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))

    if not records:
        print("FAIL: provenance file is empty.")
        return 1

    print(f"Total provenance records: {len(records)}\n")

    overall_pass = True
    first_three = records[:3]

    print("-" * 70)
    print("LINEAGE TRACE (first 3 records)")
    print("-" * 70)
    for idx, rec in enumerate(first_three, start=1):
        print(f"\nRecord {idx}:")
        for label, key in FIELD_MAP.items():
            value = rec.get(key)
            print(f"  {label:22s} = {value}")

    # --- Verify all lineage fields are populated
    print("\n" + "-" * 70)
    print("LINEAGE COMPLETENESS CHECK")
    print("-" * 70)

    all_populated = True
    for i, rec in enumerate(records, start=1):
        for label, key in FIELD_MAP.items():
            value = rec.get(key)
            is_empty = value is None or (isinstance(value, str) and value.strip() == "")
            status = "OK" if not is_empty else "EMPTY"
            if is_empty:
                all_populated = False
                overall_pass = False
                print(f"  [FAIL] record {i}: {label} is empty/null")
            else:
                print(f"  [PASS] record {i}: {label} populated")

    print(f"\n  Every required lineage field populated across all "
          f"{len(records)} records: {'YES' if all_populated else 'NO'}")

    print("\n" + "=" * 70)
    print(f"TASK 2 RESULT: {'PASS' if overall_pass else 'FAIL'}")
    print("=" * 70)
    return 0 if overall_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
