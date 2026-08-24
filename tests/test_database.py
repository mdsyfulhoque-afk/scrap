from __future__ import annotations

import uuid

import pytest

from data_fetcher.config import load_config
from data_fetcher.database import Database


@pytest.fixture
def db():
    cfg = load_config()
    return Database(cfg.postgres_dsn)


def test_database_connection(db):
    assert db is not None


def test_load_config_uses_local_defaults(monkeypatch):
    monkeypatch.delenv("MINIO_SECRET_KEY", raising=False)
    monkeypatch.delenv("MINIO_ROOT_PASSWORD", raising=False)
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)

    cfg = load_config()

    assert cfg.minio_secret_key == "DataFetcher-MinIO-2026!"
    assert cfg.postgres_password == "DataFetcher-Postgres-2026!"
    assert cfg.minio_bucket == "raw"


def test_resource_insert_and_fetch(db):
    resource = db.ensure_resource(
        url="http://example.com/test-resource",
        normalized_url="http://example.com/test-resource",
        domain="example.com",
        resource_type="text/html",
        metadata={"source": "test"},
    )
    assert resource.url == "http://example.com/test-resource"
    assert resource.domain == "example.com"

    fetch = db.create_fetch(
        resource_id=resource.id,
        crawl_job_id=None,
        status="success",
        http_status=200,
        content_type="text/html",
        content_length=10,
        headers={"Content-Type": "text/html"},
        error_message=None,
        started_at=None,
        completed_at=None,
    )
    artifact = db.create_artifact(
        fetch_id=fetch.id,
        storage_backend="minio",
        bucket_name="raw",
        object_key=f"tests/test-artifact-{uuid.uuid4()}.bin",
        content_type="text/html",
        size_bytes=10,
        checksum_sha256="abc123",
        metadata={"test": "true"},
    )
    provenance = db.get_provenance(fetch.id)
    assert provenance is not None
    assert provenance["fetch_id"] == fetch.id
