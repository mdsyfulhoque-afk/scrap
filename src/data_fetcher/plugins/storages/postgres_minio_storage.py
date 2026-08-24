"""Storage plugin persisting artifacts to MinIO and metadata to PostgreSQL.

Adapts the existing :class:`data_fetcher.storage.MinioStorage` object store and
:class:`data_fetcher.database.Database` metadata store to the
``data_fetcher_store`` hook. Clients are constructed lazily from
:func:`data_fetcher.config.load_config` so importing the plugin has no side
effects (no network or database connection is opened at construction time).
"""

from __future__ import annotations

from typing import Any

from data_fetcher.config import load_config
from data_fetcher.database import Database
from data_fetcher.storage import MinioStorage
from data_fetcher.plugin_base import DataFetcherPlugin, hookimpl


class PostgresMinioStoragePlugin(DataFetcherPlugin):
    """Dual-backend storage: MinIO object store + PostgreSQL catalog."""

    name = "postgres_minio_storage"
    stage = "storage"
    version = "1.0.0"
    description = "Stores raw artifacts in MinIO/S3 and provenance in PostgreSQL."

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config or {}
        self._minio: MinioStorage | None = None
        self._db: Database | None = None

    def _ensure(self) -> None:
        if self._minio is not None and self._db is not None:
            return
        cfg = self._config.get("storage") or load_config()
        self._minio = MinioStorage(
            endpoint_url=cfg.minio_endpoint,
            access_key=cfg.minio_access_key,
            secret_key=cfg.minio_secret_key,
            bucket_name=cfg.minio_bucket,
        )
        self._db = Database(cfg.postgres_dsn)
        self._minio.ensure_bucket()

    def capabilities(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "object_store": "minio/s3",
            "database": "postgresql",
            "preserves_provenance": True,
        }

    @hookimpl
    def data_fetcher_store(self, artifact: Any, config: dict[str, Any] | None = None) -> Any:
        self._ensure()
        body = getattr(artifact, "body", None)
        checksum = getattr(artifact, "checksum_sha256", None) or getattr(artifact, "checksum", None)
        object_key = checksum or getattr(artifact, "object_key", None) or "artifact"
        stored: dict[str, Any] = {"object_key": object_key}

        if isinstance(body, (bytes, bytearray)):
            self._minio.upload_object(
                object_key=object_key,
                body=bytes(body),
                content_type=getattr(artifact, "content_type", None),
            )
            stored["uploaded"] = True
            stored["size_bytes"] = len(body)

        try:
            fetch_id = getattr(artifact, "fetch_id", None) or (config or {}).get("fetch_id")
            if fetch_id and self._db is not None:
                record = self._db.create_artifact(
                    fetch_id=fetch_id,
                    storage_backend="minio",
                    bucket_name=self._minio.bucket_name,
                    object_key=object_key,
                    content_type=getattr(artifact, "content_type", None),
                    size_bytes=len(body) if isinstance(body, (bytes, bytearray)) else 0,
                    checksum_sha256=checksum or "",
                    metadata=getattr(artifact, "metadata", {}) or {},
                )
                stored["artifact_id"] = record.id
        except Exception as exc:  # pragma: no cover - depends on running services
            stored["warning"] = f"metadata persistence skipped: {exc}"
        return stored
