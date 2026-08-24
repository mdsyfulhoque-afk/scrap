"""Task 1: Verify record-level explainability for the Data_Fetcher_Ubuntu e2e-test build.

Connects to the database, locates the e2e-test dataset build, and prints the
full decision details for a rejected and an accepted record. Also verifies that
every record produced by the build carries an explicit accept/reject decision.
"""

from __future__ import annotations

import json
import os
import sys

os.chdir("/run/media/farhan/New Volume/Projects/Data_Fetcher_Ubuntu_Phase2")
sys.path.insert(0, "src")

import psycopg
from data_fetcher.config import load_config
from data_fetcher.database import Database


def main() -> int:
    config = load_config()
    db = Database(config.postgres_dsn)

    print("=" * 70)
    print("TASK 1: RECORD-LEVEL EXPLAINABILITY")
    print("=" * 70)
    print(f"Database DSN: {config.postgres_dsn}\n")

    # --- Locate the e2e-test build (most recent build for spec name 'e2e-test')
    with db.connect() as conn:
        with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
            cur.execute(
                """
                SELECT b.id AS build_id, b.status, b.records_considered,
                       b.records_accepted, b.records_rejected, s.name AS spec_name
                FROM dataset_builds b
                JOIN dataset_specifications s ON b.specification_id = s.id
                WHERE s.name = 'e2e-test'
                ORDER BY b.created_at DESC
                LIMIT 1
                """
            )
            build = cur.fetchone()
            if build is None:
                print("FAIL: could not locate an e2e-test build in the database.")
                return 1
            build = dict(build)
            print(f"Found e2e-test build: {build['build_id']} (status={build['status']})")
            print(
                f"  records_considered={build['records_considered']} "
                f"records_accepted={build['records_accepted']} "
                f"records_rejected={build['records_rejected']}\n"
            )

    build_id = str(build["build_id"])

    # --- Pull all decision records for the build
    decision_records = db.get_decision_records(build_id)
    if not decision_records:
        print("FAIL: no decision records found for the e2e-test build.")
        return 1

    rejected = [d for d in decision_records if d.decision == "rejected"]
    accepted = [d for d in decision_records if d.decision == "accepted"]

    print(f"Decision records in build: {len(decision_records)} "
          f"(accepted={len(accepted)}, rejected={len(rejected)})")

    # --- Print a rejected decision record
    overall_pass = True
    print("\n" + "-" * 70)
    print("REJECTED DECISION RECORD")
    print("-" * 70)
    if not rejected:
        print("FAIL: no rejected decision record found.")
        overall_pass = False
    else:
        d = rejected[0]
        details = {
            "record_id": str(d.record_id) if d.record_id else None,
            "decision": d.decision,
            "reason_codes": d.reason_codes,
            "actual_values": d.actual_values,
            "thresholds": d.thresholds,
            "representative_record_id": (
                str(d.representative_record_id) if d.representative_record_id else None
            ),
            "source_url": d.source_url,
        }
        print(json.dumps(details, indent=2, default=str))
        for key in ("record_id", "decision", "reason_codes", "actual_values",
                    "thresholds", "source_url"):
            if not getattr(d, key):
                print(f"  WARN: rejected record missing populated field '{key}'")
                overall_pass = False

    # --- Print an accepted decision record
    print("\n" + "-" * 70)
    print("ACCEPTED DECISION RECORD")
    print("-" * 70)
    if not accepted:
        print("FAIL: no accepted decision record found.")
        overall_pass = False
    else:
        d = accepted[0]
        details = {
            "record_id": str(d.record_id) if d.record_id else None,
            "decision": d.decision,
            "reason_codes": d.reason_codes,
            "actual_values": d.actual_values,
            "thresholds": d.thresholds,
            "representative_record_id": (
                str(d.representative_record_id) if d.representative_record_id else None
            ),
            "source_url": d.source_url,
        }
        print(json.dumps(details, indent=2, default=str))
        for key in ("record_id", "decision", "reason_codes", "actual_values",
                    "thresholds", "source_url"):
            if not getattr(d, key):
                print(f"  WARN: accepted record missing populated field '{key}'")
                overall_pass = False

    # --- Verify every record has a decision
    print("\n" + "-" * 70)
    print("EVERY-RECORD-HAS-A-DECISION CHECK")
    print("-" * 70)

    dataset_records = db.get_dataset_records(build_id)
    print(f"dataset_records (accepted rows): {len(dataset_records)}")
    print(f"decision_records total:          {len(decision_records)}")
    print(f"build.records_considered:        {build['records_considered']}")

    valid_decisions = all(
        d.decision in ("accepted", "rejected") for d in decision_records
    )
    every_decision_present = all(d.decision for d in decision_records)

    count_consistent = len(decision_records) == build["records_considered"]

    # A decision record's record_id links to the source/normalized record id
    # (dataset_records.source_record_id / normalized_record_id).
    accepted_record_ids = {str(d.record_id) for d in decision_records
                            if d.decision == "accepted"}
    accepted_rows_covered = all(
        str(r.source_record_id) in accepted_record_ids for r in dataset_records
    )

    print(f"  [{'PASS' if every_decision_present else 'FAIL'}] "
          f"all decision records have a non-null decision")
    print(f"  [{'PASS' if valid_decisions else 'FAIL'}] "
          f"all decision values are valid (accepted|rejected)")
    print(f"  [{'PASS' if count_consistent else 'FAIL'}] "
          f"decision count ({len(decision_records)}) == records_considered "
          f"({build['records_considered']})")
    print(f"  [{'PASS' if accepted_rows_covered else 'FAIL'}] "
          f"every accepted dataset_record has a matching accepted decision")

    explainability_pass = (
        every_decision_present
        and valid_decisions
        and count_consistent
        and accepted_rows_covered
    )
    overall_pass = overall_pass and explainability_pass

    print("\n" + "=" * 70)
    print(f"TASK 1 RESULT: {'PASS' if overall_pass else 'FAIL'}")
    print("=" * 70)
    return 0 if overall_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
