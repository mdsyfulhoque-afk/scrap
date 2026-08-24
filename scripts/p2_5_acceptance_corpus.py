"""P2.5 Acceptance Corpus Builder

Creates a deterministic acceptance corpus for P2.5 deduplication verification.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

# Ensure src is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from data_fetcher.config import load_config
from data_fetcher.database import Database
from data_fetcher.storage import MinioStorage

logger = logging.getLogger(__name__)


def compute_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def create_resource(db: Database, url: str, normalized_url: str, domain: str) -> dict:
    """Create a resource record."""
    return db.ensure_resource(
        url=url,
        normalized_url=normalized_url,
        domain=domain,
        resource_type="web",
        metadata={"acceptance_corpus": True, "created_at": datetime.now(timezone.utc).isoformat()},
    )


def create_fetch(db: Database, resource_id: str | UUID) -> dict:
    """Create a fetch record."""
    started_at = datetime.now(timezone.utc).isoformat()
    return db.create_fetch(
        resource_id=str(resource_id),
        crawl_job_id=None,
        status="success",
        http_status=200,
        content_type="text/html",
        content_length=0,
        headers={},
        error_message=None,
        started_at=started_at,
        completed_at=started_at,
    )


def upload_artifact(storage: MinioStorage, object_key: str, content: str | bytes, content_type: str = "text/html") -> str:
    """Upload content to MinIO and return checksum."""
    if isinstance(content, str):
        body = content.encode("utf-8")
    else:
        body = content
    
    checksum = compute_sha256(body)
    storage.upload_object(
        object_key=object_key,
        body=body,
        content_type=content_type,
        metadata={"checksum_sha256": checksum},
    )
    return checksum


def create_artifact(db: Database, fetch_id: str | UUID, bucket_name: str, object_key: str, content_type: str, size_bytes: int, checksum_sha256: str) -> dict:
    """Create an artifact record."""
    return db.create_artifact(
        fetch_id=str(fetch_id),
        storage_backend="minio",
        bucket_name=bucket_name,
        object_key=object_key,
        content_type=content_type,
        size_bytes=size_bytes,
        checksum_sha256=checksum_sha256,
        metadata={"acceptance_corpus": True},
    )


def build_corpus() -> None:
    """Build the P2.5 acceptance corpus."""
    config = load_config()
    db = Database(config.postgres_dsn)
    storage = MinioStorage(
        endpoint_url=config.minio_endpoint,
        access_key=config.minio_access_key,
        secret_key=config.minio_secret_key,
        bucket_name=config.minio_bucket,
    )
    storage.ensure_bucket()

    bucket = config.minio_bucket
    base_date = datetime.now().strftime("%Y%m%d")
    
    print("=" * 60)
    print("P2.5 ACCEPTANCE CORPUS BUILDER")
    print("=" * 60)
    print()
    
    # ============================================================
    # CATEGORY A: RAW EXACT DUPLICATES
    # Two artifacts with identical raw content
    # ============================================================
    print("CATEGORY A: RAW EXACT DUPLICATES")
    print("-" * 40)
    
    raw_exact_content = b"<html><body><p>The quick brown fox jumps over the lazy dog.</p></body></html>"
    raw_exact_checksum = compute_sha256(raw_exact_content)
    
    # Artifact A1
    resource_a1 = create_resource(db, "http://acceptance.example.com/raw-exact-a", "http://acceptance.example.com/raw-exact-a", "acceptance.example.com")
    fetch_a1 = create_fetch(db, resource_a1.id)
    object_key_a1 = f"acceptance/{base_date}/raw-exact-a-{fetch_a1.id}/payload.bin"
    checksum_a1 = upload_artifact(storage, object_key_a1, raw_exact_content, "text/html")
    artifact_a1 = create_artifact(db, fetch_a1.id, bucket, object_key_a1, "text/html", len(raw_exact_content), checksum_a1)
    
    # Artifact A2 (identical content, different URL)
    resource_a2 = create_resource(db, "http://acceptance.example.com/raw-exact-b", "http://acceptance.example.com/raw-exact-b", "acceptance.example.com")
    fetch_a2 = create_fetch(db, resource_a2.id)
    object_key_a2 = f"acceptance/{base_date}/raw-exact-b-{fetch_a2.id}/payload.bin"
    checksum_a2 = upload_artifact(storage, object_key_a2, raw_exact_content, "text/html")
    artifact_a2 = create_artifact(db, fetch_a2.id, bucket, object_key_a2, "text/html", len(raw_exact_content), checksum_a2)
    
    print(f"Artifact A1: {artifact_a1.id} checksum={checksum_a1[:16]}...")
    print(f"Artifact A2: {artifact_a2.id} checksum={checksum_a2[:16]}...")
    print(f"Raw exact match: {checksum_a1 == checksum_a2}")
    print()
    
    # ============================================================
    # CATEGORY B: NORMALIZED EXACT DUPLICATES
    # Different raw content, same normalized content
    # ============================================================
    print("CATEGORY B: NORMALIZED EXACT DUPLICATES")
    print("-" * 40)
    
    # B1: Unix line endings
    content_b1 = b"<html><body><p>Hello world\nThis is test B1.\n</p></body></html>"
    # B2: Windows line endings
    content_b2 = b"<html><body><p>Hello world\r\nThis is test B1.\r\n</p></body></html>"
    
    checksum_b1 = compute_sha256(content_b1)
    checksum_b2 = compute_sha256(content_b2)
    
    resource_b1 = create_resource(db, "http://acceptance.example.com/norm-exact-a", "http://acceptance.example.com/norm-exact-a", "acceptance.example.com")
    fetch_b1 = create_fetch(db, resource_b1.id)
    object_key_b1 = f"acceptance/{base_date}/norm-exact-a-{fetch_b1.id}/payload.bin"
    upload_artifact(storage, object_key_b1, content_b1, "text/html")
    artifact_b1 = create_artifact(db, fetch_b1.id, bucket, object_key_b1, "text/html", len(content_b1), checksum_b1)
    
    resource_b2 = create_resource(db, "http://acceptance.example.com/norm-exact-b", "http://acceptance.example.com/norm-exact-b", "acceptance.example.com")
    fetch_b2 = create_fetch(db, resource_b2.id)
    object_key_b2 = f"acceptance/{base_date}/norm-exact-b-{fetch_b2.id}/payload.bin"
    upload_artifact(storage, object_key_b2, content_b2, "text/html")
    artifact_b2 = create_artifact(db, fetch_b2.id, bucket, object_key_b2, "text/html", len(content_b2), checksum_b2)
    
    print(f"Artifact B1: {artifact_b1.id} checksum={checksum_b1[:16]}...")
    print(f"Artifact B2: {artifact_b2.id} checksum={checksum_b2[:16]}...")
    print(f"Raw checksums differ: {checksum_b1 != checksum_b2}")
    print()
    
    # ============================================================
    # CATEGORY C: CLEAR NEAR DUPLICATES
    # ============================================================
    print("CATEGORY C: CLEAR NEAR DUPLICATES")
    print("-" * 40)
    
    content_c1 = b"""<html><body><p>The data pipeline architecture consists of several key components. First, the acquisition layer fetches raw content from target websites. Second, the storage layer preserves the original bytes in MinIO object storage. Third, the processing layer transforms raw artifacts into canonical representations through extraction and normalization. Finally, the quality layer evaluates the processed content for downstream dataset construction.</p></body></html>"""
    
    content_c2 = b"""<html><body><p>The data pipeline architecture consists of several key components. First, the acquisition layer fetches raw content from target websites. Second, the storage layer preserves the original bytes in MinIO object storage. Third, the processing layer transforms raw artifacts into canonical representations through extraction and normalization. Finally, the validation layer checks the processed content for downstream dataset construction.</p></body></html>"""
    
    content_c3 = b"""<html><body><p>The data pipeline architecture consists of several key components. First, the acquisition layer fetches raw content from target websites. Second, the storage layer preserves the original bytes in MinIO object storage. Third, the processing layer transforms raw artifacts into canonical representations through extraction and normalization. Finally, the quality layer evaluates the processed content for downstream dataset construction. This pipeline is designed for CPU-first processing on commodity hardware.</p></body></html>"""
    
    checksum_c1 = compute_sha256(content_c1)
    checksum_c2 = compute_sha256(content_c2)
    checksum_c3 = compute_sha256(content_c3)
    
    for idx, (content, checksum, url_suffix) in enumerate([
        (content_c1, checksum_c1, "near-dup-a"),
        (content_c2, checksum_c2, "near-dup-b"),
        (content_c3, checksum_c3, "near-dup-c"),
    ], start=1):
        resource = create_resource(db, f"http://acceptance.example.com/{url_suffix}", f"http://acceptance.example.com/{url_suffix}", "acceptance.example.com")
        fetch = create_fetch(db, resource.id)
        object_key = f"acceptance/{base_date}/{url_suffix}-{fetch.id}/payload.bin"
        upload_artifact(storage, object_key, content, "text/html")
        create_artifact(db, fetch.id, bucket, object_key, "text/html", len(content), checksum)
        print(f"Artifact C{idx}: checksum={checksum[:16]}...")
    
    print(f"All raw checksums differ: {len({checksum_c1, checksum_c2, checksum_c3}) == 3}")
    print()
    
    # ============================================================
    # CATEGORY D: BELOW-THRESHOLD NON-DUPLICATES
    # ============================================================
    print("CATEGORY D: BELOW-THRESHOLD NON-DUPLICATES")
    print("-" * 40)
    
    content_d1 = b"<html><body><p>Machine learning models require large datasets for training. Neural networks learn patterns from examples. Deep learning has revolutionized computer vision and natural language processing.</p></body></html>"
    content_d2 = b"<html><body><p>Traditional Italian cuisine features pasta, pizza, and risotto. Fresh ingredients like tomatoes, basil, and olive oil create authentic flavors. Regional variations exist across Italy from north to south.</p></body></html>"
    
    checksum_d1 = compute_sha256(content_d1)
    checksum_d2 = compute_sha256(content_d2)
    
    for content, checksum, url_suffix in [(content_d1, checksum_d1, "non-dup-a"), (content_d2, checksum_d2, "non-dup-b")]:
        resource = create_resource(db, f"http://acceptance.example.com/{url_suffix}", f"http://acceptance.example.com/{url_suffix}", "acceptance.example.com")
        fetch = create_fetch(db, resource.id)
        object_key = f"acceptance/{base_date}/{url_suffix}-{fetch.id}/payload.bin"
        upload_artifact(storage, object_key, content, "text/html")
        create_artifact(db, fetch.id, bucket, object_key, "text/html", len(content), checksum)
    
    print(f"Artifact D1: checksum={checksum_d1[:16]}...")
    print(f"Artifact D2: checksum={checksum_d2[:16]}...")
    print(f"Raw checksums differ: {checksum_d1 != checksum_d2}")
    print()
    
    # ============================================================
    # CATEGORY E: TRANSITIVE NEAR-DUPLICATE CHAIN
    # ============================================================
    print("CATEGORY E: TRANSITIVE NEAR-DUPLICATE CHAIN")
    print("-" * 40)
    
    content_e1 = b"""<html><body><p>Database systems provide persistent storage for application data. Relational databases use SQL for querying. NoSQL databases offer flexible schemas. NewSQL combines SQL guarantees with NoSQL scalability. Modern applications often use both types depending on requirements.</p></body></html>"""
    
    content_e2 = b"""<html><body><p>Database systems provide persistent storage for application data. Relational databases use SQL for querying. NoSQL databases offer flexible schemas. NewSQL combines SQL guarantees with NoSQL scalability. Contemporary applications often use both types depending on requirements.</p></body></html>"""
    
    content_e3 = b"""<html><body><p>Database systems provide persistent storage for application data. Relational databases use SQL for querying. NoSQL databases offer flexible schemas. NewSQL combines SQL guarantees with NoSQL scalability. Modern software often uses both types depending on business requirements.</p></body></html>"""
    
    checksum_e1 = compute_sha256(content_e1)
    checksum_e2 = compute_sha256(content_e2)
    checksum_e3 = compute_sha256(content_e3)
    
    for content, checksum, url_suffix in [
        (content_e1, checksum_e1, "trans-a"),
        (content_e2, checksum_e2, "trans-b"),
        (content_e3, checksum_e3, "trans-c"),
    ]:
        resource = create_resource(db, f"http://acceptance.example.com/{url_suffix}", f"http://acceptance.example.com/{url_suffix}", "acceptance.example.com")
        fetch = create_fetch(db, resource.id)
        object_key = f"acceptance/{base_date}/{url_suffix}-{fetch.id}/payload.bin"
        upload_artifact(storage, object_key, content, "text/html")
        create_artifact(db, fetch.id, bucket, object_key, "text/html", len(content), checksum)
    
    print(f"Artifact E1: checksum={checksum_e1[:16]}...")
    print(f"Artifact E2: checksum={checksum_e2[:16]}...")
    print(f"Artifact E3: checksum={checksum_e3[:16]}...")
    print(f"All raw checksums differ: {len({checksum_e1, checksum_e2, checksum_e3}) == 3}")
    print()
    
    # ============================================================
    # CATEGORY F: DIFFERENT URL, SAME CONTENT
    # ============================================================
    print("CATEGORY F: DIFFERENT URL, SAME CONTENT")
    print("-" * 40)
    
    content_f = b"<html><body><p>This content appears on multiple domains for testing cross-domain duplicate detection.</p></body></html>"
    checksum_f = compute_sha256(content_f)
    
    for domain_suffix in ["site1.com", "site2.org", "site3.net"]:
        url = f"http://acceptance.example.com/{domain_suffix}/page"
        resource = create_resource(db, url, url, domain_suffix)
        fetch = create_fetch(db, resource.id)
        object_key = f"acceptance/{base_date}/cross-domain-{domain_suffix}-{fetch.id}/payload.bin"
        upload_artifact(storage, object_key, content_f, "text/html")
        create_artifact(db, fetch.id, bucket, object_key, "text/html", len(content_f), checksum_f)
    
    print(f"Created 3 artifacts with identical content across different domains")
    print(f"Shared checksum: {checksum_f[:16]}...")
    print()
    
    # ============================================================
    # SUMMARY
    # ============================================================
    print("=" * 60)
    print("CORPUS CREATION COMPLETE")
    print("=" * 60)
    print()
    print("Next steps:")
    print("1. Run P2.3 extraction: python -m data_fetcher.demo phase2 extract <artifact-id>")
    print("2. Run P2.4 quality: python -m data_fetcher.demo phase2 quality <artifact-id>")
    print("3. Run P2.5 deduplication: python -m data_fetcher.demo phase2 deduplicate")
    print()
    
    print("Created artifacts:")
    artifacts = db.get_all_artifacts()
    for art in artifacts:
        if art.get("resource_url", "").startswith("http://acceptance.example.com"):
            print(f"  {art['id']} | {art['resource_url']} | {art.get('checksum_sha256', '')[:16]}...")


if __name__ == "__main__":
    build_corpus()
