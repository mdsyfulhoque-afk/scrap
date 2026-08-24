from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


def _load_env_file(path: str = ".env") -> dict[str, str]:
    env_path = Path(path)
    if not env_path.exists():
        return {}
    values: dict[str, str] = {}
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


_ENV_FILE_VALUES = _load_env_file()


def _load_compose_defaults() -> dict[str, str]:
    compose_path = Path(__file__).resolve().parents[2] / "docker-compose.yml"
    if not compose_path.exists():
        return {}

    values: dict[str, str] = {}
    text = compose_path.read_text()
    patterns = {
        "MINIO_ROOT_USER": r"(?m)^\s*MINIO_ROOT_USER:\s*(.+?)\s*$",
        "MINIO_ROOT_PASSWORD": r"(?m)^\s*MINIO_ROOT_PASSWORD:\s*(.+?)\s*$",
        "POSTGRES_USER": r"(?m)^\s*POSTGRES_USER:\s*(.+?)\s*$",
        "POSTGRES_PASSWORD": r"(?m)^\s*POSTGRES_PASSWORD:\s*(.+?)\s*$",
        "POSTGRES_DB": r"(?m)^\s*POSTGRES_DB:\s*(.+?)\s*$",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, text)
        if match:
            values[key] = match.group(1).strip().strip('"').strip("'")
    return values


_COMPOSE_FILE_VALUES = _load_compose_defaults()


def _env_str(name: str, default: str | None = None) -> str | None:
    if name in _ENV_FILE_VALUES:
        return _ENV_FILE_VALUES[name]
    value = os.getenv(name)
    if value is not None:
        return value
    if name == "MINIO_SECRET_KEY":
        return _COMPOSE_FILE_VALUES.get("MINIO_ROOT_PASSWORD", default)
    if name == "MINIO_ACCESS_KEY":
        return _COMPOSE_FILE_VALUES.get("MINIO_ROOT_USER", default)
    if name == "POSTGRES_PASSWORD":
        return _COMPOSE_FILE_VALUES.get("POSTGRES_PASSWORD", default)
    if name == "POSTGRES_USER":
        return _COMPOSE_FILE_VALUES.get("POSTGRES_USER", default)
    if name == "POSTGRES_DATABASE":
        return _COMPOSE_FILE_VALUES.get("POSTGRES_DB", default)
    return _COMPOSE_FILE_VALUES.get(name, default)


def _env_int(name: str, default: int) -> int:
    value = _env_str(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"Invalid integer value for {name}") from exc


def _env_list(name: str, default: str) -> list[str]:
    raw = _env_str(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass
class FetcherConfig:
    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    minio_bucket: str
    postgres_host: str
    postgres_port: int
    postgres_database: str
    postgres_user: str
    postgres_password: str
    fetch_connect_timeout_seconds: int
    fetch_read_timeout_seconds: int
    fetch_max_size_bytes: int
    fetch_max_retries: int
    fetch_backoff_seconds: int
    fetch_max_redirects: int
    fetch_allowed_domains: list[str]
    fetch_allowed_content_types: list[str]

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_database}"
        )


def load_config(prefix: str = "") -> FetcherConfig:
    minio_endpoint = _env_str("MINIO_ENDPOINT", "http://localhost:9000")
    minio_access_key = _env_str(
        "MINIO_ACCESS_KEY",
        _env_str("MINIO_ROOT_USER", "datafetcheradmin"),
    )
    minio_secret_key = _env_str(
        "MINIO_SECRET_KEY",
        _env_str("MINIO_ROOT_PASSWORD", None),
    )
    if not minio_secret_key:
        raise EnvironmentError("Missing required environment variable: MINIO_SECRET_KEY")

    postgres_password = _env_str("POSTGRES_PASSWORD", None)
    if not postgres_password:
        raise EnvironmentError("Missing required environment variable: POSTGRES_PASSWORD")

    fetch_connect_timeout_seconds = _env_int(
        "FETCH_CONNECT_TIMEOUT_SECONDS",
        _env_int("FETCH_TIMEOUT_SECONDS", 5),
    )
    fetch_read_timeout_seconds = _env_int(
        "FETCH_READ_TIMEOUT_SECONDS",
        _env_int("FETCH_TIMEOUT_SECONDS", 25),
    )

    return FetcherConfig(
        minio_endpoint=minio_endpoint,
        minio_access_key=minio_access_key,
        minio_secret_key=minio_secret_key,
        minio_bucket=_env_str("MINIO_BUCKET", "raw") or "raw",
        postgres_host=_env_str("POSTGRES_HOST", "localhost") or "localhost",
        postgres_port=_env_int("POSTGRES_PORT", 5432),
        postgres_database=_env_str("POSTGRES_DATABASE", "data_catalog") or "data_catalog",
        postgres_user=_env_str("POSTGRES_USER", "datafetcher") or "datafetcher",
        postgres_password=postgres_password,
        fetch_connect_timeout_seconds=fetch_connect_timeout_seconds,
        fetch_read_timeout_seconds=fetch_read_timeout_seconds,
        fetch_max_size_bytes=_env_int("FETCH_MAX_SIZE_BYTES", 10 * 1024 * 1024),
        fetch_max_retries=_env_int("FETCH_MAX_RETRIES", 2),
        fetch_backoff_seconds=_env_int("FETCH_BACKOFF_SECONDS", 1),
        fetch_max_redirects=_env_int("FETCH_MAX_REDIRECTS", 5),
        fetch_allowed_domains=_env_list("FETCH_ALLOWED_DOMAINS", "localhost,127.0.0.1"),
        fetch_allowed_content_types=_env_list("FETCH_ALLOWED_CONTENT_TYPES", "*/*"),
    )


def normalize_domain(domain: str) -> str:
    return domain.lower().strip()


def allowed_domain(domain: str, allowed_domains: Iterable[str]) -> bool:
    normalized = normalize_domain(domain)
    return any(normalized == normalize_domain(candidate) for candidate in allowed_domains)
