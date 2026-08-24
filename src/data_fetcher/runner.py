from __future__ import annotations

import datetime
import logging
import os
import uuid

from data_fetcher.config import load_config
from data_fetcher.database import Database
from data_fetcher.fetcher import FetchError, Fetcher
from data_fetcher.storage import MinioStorage

logger = logging.getLogger(__name__)


def run_controlled_fetch(url: str, crawl_job_id: str | None = None) -> dict[str, str]:
    config = load_config()
    fetcher = Fetcher(
        connect_timeout_seconds=config.fetch_connect_timeout_seconds,
        read_timeout_seconds=config.fetch_read_timeout_seconds,
        max_size_bytes=config.fetch_max_size_bytes,
        max_retries=config.fetch_max_retries,
        backoff_seconds=config.fetch_backoff_seconds,
        max_redirects=config.fetch_max_redirects,
        allowed_domains=config.fetch_allowed_domains,
        allowed_content_types=config.fetch_allowed_content_types,
    )
    storage = MinioStorage(
        endpoint_url=config.minio_endpoint,
        access_key=config.minio_access_key,
        secret_key=config.minio_secret_key,
        bucket_name=config.minio_bucket,
    )
    storage.ensure_bucket()
    db = Database(config.postgres_dsn)
    if crawl_job_id is None:
        crawl_job = db.create_crawl_job(
            name=f"controlled-fetch-{uuid.uuid4()}",
            status="running",
            config={
                "allowed_domains": config.fetch_allowed_domains,
                "max_size_bytes": config.fetch_max_size_bytes,
                "max_retries": config.fetch_max_retries,
                "max_redirects": config.fetch_max_redirects,
            },
        )
        crawl_job_id = crawl_job.id
    normalized_url, domain = fetcher.normalize_and_validate_url(url)
    resource = db.ensure_resource(
        url=url,
        normalized_url=normalized_url,
        domain=domain,
        resource_type=None,
        metadata={
            "fetcher_version": os.getenv("FETCHER_VERSION", "0.1.0"),
        },
    )
    started_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    fetch = db.create_fetch(
        resource_id=resource.id,
        crawl_job_id=crawl_job_id,
        status="running",
        http_status=None,
        content_type=None,
        content_length=None,
        headers={},
        error_message=None,
        started_at=started_at,
        completed_at=None,
    )
    try:
        result = fetcher.fetch(url)
        object_key = f"web/{result.domain}/{datetime.datetime.now().strftime('%Y%m%d')}/{fetch.id}/payload.bin"
        storage.upload_object(
            object_key=object_key,
            body=result.body,
            content_type=result.content_type,
            metadata={"checksum_sha256": result.checksum_sha256},
        )
        db.create_artifact(
            fetch_id=fetch.id,
            storage_backend="minio",
            bucket_name=config.minio_bucket,
            object_key=object_key,
            content_type=result.content_type,
            size_bytes=result.content_length,
            checksum_sha256=result.checksum_sha256,
            metadata={
                "redirect_chain": result.redirect_chain,
                "fetched_at": started_at,
            },
        )
        db.complete_fetch(
            fetch.id,
            "success",
            result.status_code,
            result.content_type,
            result.content_length,
            result.headers,
            None,
        )
        db.update_crawl_job_status(crawl_job_id, "completed")
        provenance = db.get_provenance(fetch.id)
        logger.info("fetch completed", extra={"fetch_id": fetch.id, "resource_id": resource.id})
        return provenance or {}
    except FetchError as exc:
        if 'fetch' in locals():
            db.update_fetch_status(fetch.id, "failed", exc.category + ": " + str(exc))
        db.update_crawl_job_status(crawl_job_id, "failed")
        logger.error(
            "fetch failed",
            extra={"url": url, "crawl_job_id": crawl_job_id, "error_category": exc.category},
        )
        raise
    except Exception as exc:
        if 'fetch' in locals():
            db.update_fetch_status(fetch.id, "failed", str(exc))
        db.update_crawl_job_status(crawl_job_id, "failed")
        logger.error(
            "fetch failed",
            extra={"url": url, "crawl_job_id": crawl_job_id, "error_message": str(exc)},
        )
        raise
