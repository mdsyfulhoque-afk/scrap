"""P2.5 Acceptance Runner

Runs the full P2.3->P2.4->P2.5 pipeline on the acceptance corpus and verifies results.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure src is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from data_fetcher.config import load_config
from data_fetcher.database import Database
from psycopg.rows import class_row

logger = logging.getLogger(__name__)


def run_cmd(cmd: list[str], cwd: Path) -> int:
    """Run a command and return exit code."""
    env = {
        **os.environ,
        "PYTHONPATH": str(cwd / "src"),
    }
    result = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        env=env,
    )
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    return result.returncode


def get_acceptance_artifacts(db: Database) -> list[dict]:
    """Get all acceptance corpus artifacts."""
    with db.connect() as conn:
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
                "WHERE a.metadata->>'acceptance_corpus' = 'true' "
                "ORDER BY a.created_at"
            )
            return [dict(row) for row in cur.fetchall()]


def run_extraction(artifact_id: str, cwd: Path) -> bool:
    """Run P2.3 extraction on an artifact."""
    artifact_id = str(artifact_id)
    cmd = [sys.executable, "-m", "data_fetcher.demo", "phase2", "extract", artifact_id]
    print(f"\n{'='*60}")
    print(f"EXTRACTING: {artifact_id}")
    print(f"{'='*60}")
    rc = run_cmd(cmd, cwd)
    return rc == 0


def run_quality(artifact_id: str, cwd: Path) -> bool:
    """Run P2.4 quality on an artifact."""
    artifact_id = str(artifact_id)
    cmd = [sys.executable, "-m", "data_fetcher.demo", "phase2", "quality", artifact_id]
    print(f"\n{'='*60}")
    print(f"QUALITY: {artifact_id}")
    print(f"{'='*60}")
    rc = run_cmd(cmd, cwd)
    return rc == 0


def run_deduplication(cwd: Path, threshold: float = 0.85) -> bool:
    """Run P2.5 deduplication."""
    cmd = [sys.executable, "-m", "data_fetcher.demo", "phase2", "deduplicate", "--threshold", str(threshold)]
    print(f"\n{'='*60}")
    print(f"RUNNING DEDUPLICATION (threshold={threshold})")
    print(f"{'='*60}")
    rc = run_cmd(cmd, cwd)
    return rc == 0


def verify_results(db: Database) -> dict:
    """Verify deduplication results."""
    with db.connect() as conn:
        with conn.cursor(row_factory=class_row(dict)) as cur:
            # Count groups by method
            cur.execute("SELECT duplicate_method, COUNT(*) as count FROM duplicate_groups GROUP BY duplicate_method")
            groups_by_method = {row["duplicate_method"]: row["count"] for row in cur.fetchall()}
            
            # Count total groups
            cur.execute("SELECT COUNT(*) as total FROM duplicate_groups")
            total_groups = cur.fetchone()["total"]
            
            # Count total memberships
            cur.execute("SELECT COUNT(*) as total FROM duplicate_memberships")
            total_memberships = cur.fetchone()["total"]
            
            # Count representatives
            cur.execute("SELECT COUNT(*) as total FROM duplicate_memberships WHERE is_representative = true")
            total_representatives = cur.fetchone()["total"]
            
            # Get group details
            cur.execute("""
                SELECT g.id, g.duplicate_method, g.group_size, g.representative_normalized_document_id,
                       g.similarity_stats, COUNT(m.id) as member_count
                FROM duplicate_groups g
                LEFT JOIN duplicate_memberships m ON g.id = m.group_id
                GROUP BY g.id, g.duplicate_method, g.group_size, g.representative_normalized_document_id, g.similarity_stats
                ORDER BY g.duplicate_method, g.created_at
            """)
            groups = [dict(row) for row in cur.fetchall()]
            
            # Get membership details
            cur.execute("""
                SELECT m.group_id, m.normalized_document_id, m.is_representative, m.selection_basis,
                       m.similarity_score, g.duplicate_method
                FROM duplicate_memberships m
                JOIN duplicate_groups g ON m.group_id = g.id
                ORDER BY g.duplicate_method, m.group_id, m.created_at
            """)
            memberships = [dict(row) for row in cur.fetchall()]
            
            return {
                "groups_by_method": groups_by_method,
                "total_groups": total_groups,
                "total_memberships": total_memberships,
                "total_representatives": total_representatives,
                "groups": groups,
                "memberships": memberships,
            }


def main() -> int:
    cwd = Path(__file__).resolve().parent.parent
    config = load_config()
    db = Database(config.postgres_dsn)
    
    print("=" * 60)
    print("P2.5 ACCEPTANCE RUNNER")
    print("=" * 60)
    print()
    
    # Get acceptance artifacts
    artifacts = get_acceptance_artifacts(db)
    if not artifacts:
        print("ERROR: No acceptance corpus artifacts found. Run corpus builder first.", file=sys.stderr)
        return 1
    
    print(f"Found {len(artifacts)} acceptance corpus artifacts")
    
    # Run extraction on all artifacts
    print("\n" + "=" * 60)
    print("PHASE 2.3: EXTRACTION")
    print("=" * 60)
    extraction_success = 0
    for art in artifacts:
        if run_extraction(art["id"], cwd):
            extraction_success += 1
    print(f"\nExtraction complete: {extraction_success}/{len(artifacts)} succeeded")
    
    # Run quality on all artifacts
    print("\n" + "=" * 60)
    print("PHASE 2.4: QUALITY + NORMALIZATION")
    print("=" * 60)
    quality_success = 0
    for art in artifacts:
        if run_quality(art["id"], cwd):
            quality_success += 1
    print(f"\nQuality complete: {quality_success}/{len(artifacts)} succeeded")
    
    # Run deduplication
    print("\n" + "=" * 60)
    print("PHASE 2.5: DEDUPLICATION")
    print("=" * 60)
    if not run_deduplication(cwd, threshold=0.85):
        print("ERROR: Deduplication failed", file=sys.stderr)
        return 1
    
    # Verify results
    print("\n" + "=" * 60)
    print("VERIFICATION RESULTS")
    print("=" * 60)
    
    results = verify_results(db)
    
    print(f"\nTotal groups: {results['total_groups']}")
    print(f"Total memberships: {results['total_memberships']}")
    print(f"Total representatives: {results['total_representatives']}")
    print(f"\nGroups by method:")
    for method, count in results["groups_by_method"].items():
        print(f"  {method}: {count}")
    
    print(f"\nGroup details:")
    for g in results["groups"]:
        print(f"  {g['duplicate_method']}: size={g['group_size']}, members={g['member_count']}, rep={g['representative_normalized_document_id']}")
        if g.get("similarity_stats"):
            print(f"    stats: {g['similarity_stats']}")
    
    print(f"\nMembership details:")
    for m in results["memberships"]:
        rep_marker = " [REP]" if m["is_representative"] else ""
        sim = f" sim={m['similarity_score']:.2f}" if m["similarity_score"] is not None else ""
        print(f"  {m['group_id'][:8]}... | {m['normalized_document_id'][:8]}...{rep_marker}{sim} | basis={m.get('selection_basis')}")
    
    # Verify expected results
    print("\n" + "=" * 60)
    print("EXPECTED vs ACTUAL")
    print("=" * 60)
    
    raw_exact_count = results["groups_by_method"].get("raw_exact", 0)
    norm_exact_count = results["groups_by_method"].get("normalized_exact", 0)
    near_dup_count = results["groups_by_method"].get("near_duplicate", 0)
    
    print(f"Raw exact groups: expected >= 3, got {raw_exact_count}")
    print(f"  (2 from Category A + 3 from Category F = 5 total, but some may overlap)")
    print(f"Normalized exact groups: expected >= 1, got {norm_exact_count}")
    print(f"Near duplicate groups: expected >= 2, got {near_dup_count}")
    print(f"  (Category C: 3 docs, Category E: 3 docs)")
    
    # Save results to file
    results_file = cwd / "scripts" / "p2_5_acceptance_results.json"
    with open(results_file, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved to: {results_file}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
