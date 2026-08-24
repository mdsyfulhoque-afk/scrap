from __future__ import annotations

import os

import boto3
import pytest

from data_fetcher.storage import MinioStorage, StorageError


@pytest.fixture
def minio_storage():
    endpoint = os.getenv("MINIO_ENDPOINT", "http://localhost:9000")
    access_key = os.getenv("MINIO_ACCESS_KEY", "datafetcheradmin")
    secret_key = os.getenv("MINIO_SECRET_KEY", "DataFetcher-MinIO-2026!")
    bucket = os.getenv("MINIO_BUCKET", "raw")
    return MinioStorage(endpoint, access_key, secret_key, bucket)


def test_minio_bucket_exists(minio_storage):
    minio_storage.ensure_bucket()
    assert minio_storage.object_exists("nonexistent-placeholder") is False


def test_minio_upload_and_get(minio_storage):
    key = "tests/test_payload.bin"
    body = b"test-data"
    minio_storage.upload_object(key, body, content_type="application/octet-stream", metadata={"test": "true"})
    assert minio_storage.object_exists(key)
    data = minio_storage.get_object(key)
    assert data == body
    metadata = minio_storage.get_object_metadata(key)
    assert metadata.get("test") == "true"
