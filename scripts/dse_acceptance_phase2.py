"""DSE Acceptance Phase 2 Runner

Runs P2.2 inventory, P2.3 extraction, P2.4 quality, and P2.5 deduplication
on the DSE acceptance artifacts.
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path

# Ensure src is on path for direct imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from psycopg.rows import class_row
from data_fetcher.config import load_config
from data_fetcher.database import Database

logger = logging.getLogger(__name__)

DSE_ARTIFACT_IDS = [
    "cc40272b-76dc-46b8-9a60-b4eb68d45c0f",  # DSE Homepage
    "e72660d9-097a-4970-8b7d-f714be86cc70",  # Latest Share Price
    "ac32ae3f-6933-4817-9038-22d60f236d29",  # Top Ten Gainer
]


def run_cli(cmd: list[str], cwd: Path) -> int:
    """Run a CLI command and return exit code."""
    env = {
        **subprocess.os.environ,
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


def verify_artifact_exists(db: Database, artifact_id: str) -> bool:
    """Verify an artifact exists in the database."""
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM artifacts WHERE id = %s", (artifact_id,))
            return cur.fetchone() is not None


def verify_characterization(db: Database, artifact_id: str) -> bool:
    """Verify a characterization record exists for an artifact."""
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM artifact_characterization WHERE artifact_id = %s",
                (artifact_id,),
            )
            return cur.fetchone() is not None


def verify_canonical_document(db: Database, artifact_id: str) -> bool:
    """Verify a canonical document exists for an artifact."""
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM canonical_documents WHERE artifact_id = %s",
                (artifact_id,),
            )
            return cur.fetchone() is not None


def verify_normalized_document(db: Database, artifact_id: str) -> bool:
    """Verify a normalized document exists for an artifact."""
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT nd.id FROM normalized_documents nd "
                "JOIN canonical_documents cd ON nd.canonical_document_id = cd.id "
                "WHERE cd.artifact_id = %s",
                (artifact_id,),
            )
            return cur.fetchone() is not None


def main() -> int:
    cwd = Path(__file__).resolve().parent.parent
    config = load_config()
    db = Database(config.postgres_dsn)

    print("=" * 60)
    print("DSE ACCEPTANCE PHASE 2 PIPELINE")
    print("=" * 60)
    print()

    # Verify artifacts exist
    print("VERIFYING ARTIFACTS")
    print("-" * 40)
    for artifact_id in DSE_ARTIFACT_IDS:
        exists = verify_artifact_exists(db, artifact_id)
        print(f"  {artifact_id[:8]}... exists={exists}")
    print()

    # Phase 2.2: Inventory
    print("=" * 60)
    print("PHASE 2.2: INVENTORY / FORMAT DISCOVERY")
    print("=" * 60)
    
    # Run inspect on each artifact to create characterization records
    for artifact_id in DSE_ARTIFACT_IDS:
        cmd = [sys.executable, "-m", "data_fetcher.demo", "phase2", "inspect", artifact_id]
        print(f"\nInspecting {artifact_id[:8]}...")
        rc = run_cli(cmd, cwd)
        print(f"  Exit code: {rc}")
    
    # Verify characterizations
    print("\nVerifying characterizations:")
    for artifact_id in DSE_ARTIFACT_IDS:
        exists = verify_characterization(db, artifact_id)
        print(f"  {artifact_id[:8]}... characterized={exists}")
    print()

    # Phase 2.3: Extraction
    print("=" * 60)
    print("PHASE 2.3: EXTRACTION")
    print("=" * 60)
    
    for artifact_id in DSE_ARTIFACT_IDS:
        cmd = [sys.executable, "-m", "data_fetcher.demo", "phase2", "extract", artifact_id]
        print(f"\nExtracting {artifact_id[:8]}...")
        rc = run_cli(cmd, cwd)
        print(f"  Exit code: {rc}")
    
    # Verify canonical documents
    print("\nVerifying canonical documents:")
    for artifact_id in DSE_ARTIFACT_IDS:
        exists = verify_canonical_document(db, artifact_id)
        print(f"  {artifact_id[:8]}... canonical={exists}")
    print()

    # Phase 2.4: Quality / Normalization
    print("=" * 60)
    print("PHASE 2.4: QUALITY / NORMALIZATION")
    print("=" * 60)
    
    for artifact_id in DSE_ARTIFACT_IDS:
        cmd = [sys.executable, "-m", "data_fetcher.demo", "phase2", "quality", artifact_id]
        print(f"\nAnalyzing quality {artifact_id[:8]}...")
        rc = run_cli(cmd, cwd)
        print(f"  Exit code: {rc}")
    
    # Verify normalized documents
    print("\nVerifying normalized documents:")
    for artifact_id in DSE_ARTIFACT_IDS:
        exists = verify_normalized_document(db, artifact_id)
        print(f"  {artifact_id[:8]}... normalized={exists}")
    print()

    # Phase 2.5: Deduplication
    print("=" * 60)
    print("PHASE 2.5: DEDUPLICATION")
    print("=" * 60)
    
    cmd = [sys.executable, "-m", "data_fetcher.demo", "phase2", "deduplicate"]
    print("\nRunning deduplication on all DSE documents...")
    rc = run_cli(cmd, cwd)
    print(f"  Exit code: {rc}")
    print()

    # Query results
    print("=" * 60)
    print("RESULTS SUMMARY")
    print("=" * 60)
    
    with db.connect() as conn:
        with conn.cursor(row_factory=class_row(dict)) as cur:
            # Count groups by method
            cur.execute("SELECT duplicate_method, COUNT(*) as count FROM duplicate_groups GROUP BY duplicate_method")
            groups_by_method = {row["duplicate_method"]: row["count"] for row in cur.fetchall()}
            
            # Count total groups and memberships
            cur.execute("SELECT COUNT(*) as total FROM duplicate_groups")
            total_groups = cur.fetchone()["total"]
            
            cur.execute("SELECT COUNT(*) as total FROM duplicate_memberships")
            total_memberships = cur.fetchone()["total"]
            
            cur.execute("SELECT COUNT(*) as total FROM duplicate_memberships WHERE is_representative = true")
            total_representatives = cur.fetchone()["total"]
    
    print(f"Duplicate groups: {total_groups}")
    print(f"Duplicate memberships: {total_memberships}")
    print(f"Representatives: {total_representatives}")
    print(f"Groups by method: {groups_by_method}")
    
    # Save results
    results = {
        "total_groups": total_groups,
        "total_memberships": total_memberships,
        "total_representatives": total_representatives,
        "groups_by_method": groups_by_method,
    }
    
    results_path = cwd / "scripts" / "dse_acceptance_phase2_results.json"
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to: {results_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
