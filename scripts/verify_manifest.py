"""Task 3: Verify manifest completeness for the Data_Fetcher_Ubuntu e2e-test build.

Reads output/e2e-test/manifest.json and verifies that all required governance
and provenance fields are present and populated.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = "/run/media/farhan/New Volume/Projects/Data_Fetcher_Ubuntu_Phase2"
MANIFEST_PATH = Path(ROOT) / "output" / "e2e-test" / "manifest.json"

# Top-level required keys. "pipeline_version" OR "application_version" suffices.
REQUIRED_KEYS = [
    "dataset_name",
    "dataset_version",
    "dataset_build_id",
    "dataset_spec_hash",
    "source_snapshot",
    "created_at",
    "records_considered",
    "records_accepted",
    "records_rejected",
    "validation_status",
    "export_format",
]
VERSION_ALIASES = ["pipeline_version", "application_version"]


def main() -> int:
    print("=" * 70)
    print("TASK 3: MANIFEST COMPLETENESS")
    print("=" * 70)
    print(f"Manifest file: {MANIFEST_PATH}\n")

    if not MANIFEST_PATH.exists():
        print(f"FAIL: manifest file not found at {MANIFEST_PATH}")
        return 1

    with MANIFEST_PATH.open("r", encoding="utf-8") as fh:
        manifest = json.load(fh)

    print(f"Top-level keys present: {sorted(manifest.keys())}\n")

    overall_pass = True

    print("-" * 70)
    print("REQUIRED FIELD CHECK")
    print("-" * 70)
    for key in REQUIRED_KEYS:
        present = key in manifest
        value = manifest.get(key)
        populated = present and value is not None and value != ""
        status = "PASS" if populated else "FAIL"
        if not populated:
            overall_pass = False
        print(f"  [{status}] {key:22s} = {value!r}")

    # version alias: pipeline_version OR application_version
    version_present = any(
        (alias in manifest and manifest.get(alias) not in (None, ""))
        for alias in VERSION_ALIASES
    )
    found_alias = next(
        (a for a in VERSION_ALIASES if a in manifest and manifest.get(a) not in (None, "")),
        None,
    )
    print(f"  [{'PASS' if version_present else 'FAIL'}] "
          f"({'/'.join(VERSION_ALIASES)}): using '{found_alias}' = "
          f"{manifest.get(found_alias)!r}")
    if not version_present:
        overall_pass = False

    # Reconciliation: accepted + rejected should equal considered
    considered = manifest.get("records_considered")
    accepted = manifest.get("records_accepted")
    rejected = manifest.get("records_rejected")
    reconciled = (
        isinstance(considered, int) and isinstance(accepted, int)
        and isinstance(rejected, int) and (accepted + rejected == considered)
    )
    print(f"  [{'PASS' if reconciled else 'FAIL'}] "
          f"records_accepted ({accepted}) + records_rejected ({rejected}) "
          f"== records_considered ({considered})")
    if not reconciled:
        overall_pass = False

    print("\n" + "=" * 70)
    print(f"TASK 3 RESULT: {'PASS' if overall_pass else 'FAIL'}")
    print("=" * 70)
    return 0 if overall_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
