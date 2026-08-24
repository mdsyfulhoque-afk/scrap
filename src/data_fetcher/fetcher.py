from __future__ import annotations

import hashlib
import logging
import os
import time
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urlparse

import requests
from requests.exceptions import (
    ConnectionError,
    HTTPError,
    InvalidSchema,
    InvalidURL,
    RequestException,
    SSLError,
    Timeout,
    TooManyRedirects,
)

from data_fetcher.config import allowed_domain
from data_fetcher.models import FetchResult

logger = logging.getLogger(__name__)


class FetchError(Exception):
    def __init__(self, category: str, message: str):
        self.category = category
        super().__init__(message)


@dataclass
class Fetcher:
    connect_timeout_seconds: int
    read_timeout_seconds: int
    max_size_bytes: int
    max_retries: int
    backoff_seconds: int
    max_redirects: int
    allowed_domains: Iterable[str]
    allowed_content_types: Iterable[str]
    verify_ssl: bool | None = None

    def __post_init__(self) -> None:
        if self.verify_ssl is None:
            env_val = os.getenv("DATA_FETCHER_SSL_VERIFY", "true").lower()
            self.verify_ssl = env_val not in ("false", "0", "no")

    def _normalize_url(self, url: str) -> str:
        parsed = urlparse(url)
        scheme = parsed.scheme or "http"
        if scheme not in ("http", "https"):
            raise FetchError("network/DNS", f"unsupported URL scheme: {scheme}")
        normalized = parsed._replace(scheme=scheme).geturl()
        return normalized

    def _validate_no_private_ip(self, hostname: str) -> None:
        """Block private/internal IP ranges to prevent SSRF."""
        import ipaddress
        try:
            addr = ipaddress.ip_address(hostname)
            if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
                raise FetchError("network/DNS", f"access to private/internal address blocked: {hostname}")
        except ValueError:
            pass

    def _validate_url(self, url: str) -> str:
        parsed = urlparse(url)
        domain = parsed.hostname
        if not domain:
            raise FetchError("network/DNS", "invalid URL domain")
        if not allowed_domain(domain, self.allowed_domains):
            raise FetchError("network/DNS", f"domain '{domain}' is not allowed")
        # Only apply private IP blocking to non-allowed domains.
        # Explicitly allowed domains (e.g. localhost for local testing) bypass this check.
        if domain not in self.allowed_domains:
            self._validate_no_private_ip(domain)
        return domain.lower()

    def _classify_content_type(self, content_type: str | None) -> str:
        if not content_type:
            return "unknown"
        content_type = content_type.split(";")[0].strip().lower()
        if content_type == "text/html":
            return "html"
        if content_type in {"application/json", "text/json"}:
            return "json"
        if content_type in {"application/xml", "text/xml"}:
            return "xml"
        if content_type.startswith("text/"):
            return "text"
        if content_type == "application/pdf":
            return "pdf"
        return "binary"

    def _validate_content_type(self, content_type: str | None) -> bool:
        if not content_type:
            return any(pattern.strip() == "*/*" for pattern in self.allowed_content_types)
        content_type_value = content_type.split(";")[0].strip().lower()
        for pattern in self.allowed_content_types:
            pattern = pattern.strip().lower()
            if pattern == "*/*":
                return True
            if pattern == content_type_value:
                return True
            if pattern.endswith("/*"):
                prefix = pattern[:-2]
                if content_type_value.startswith(prefix + "/"):
                    return True
        return False

    def _hash_body(self, body: bytes) -> str:
        return hashlib.sha256(body).hexdigest()

    def normalize_and_validate_url(self, url: str) -> tuple[str, str]:
        normalized = self._normalize_url(url)
        domain = self._validate_url(normalized)
        return normalized, domain

    def fetch(self, url: str) -> FetchResult:
        normalized_url = self._normalize_url(url)
        domain = self._validate_url(normalized_url)
        attempt = 0
        category = "unknown"
        message = "request failed"
        while attempt <= self.max_retries:
            start = time.monotonic()
            try:
                with requests.Session() as session:
                    session.max_redirects = self.max_redirects
                    if not self.verify_ssl:
                        logger.warning("SSL verification is disabled for %s", normalized_url)
                    response = session.get(
                        normalized_url,
                        timeout=(self.connect_timeout_seconds, self.read_timeout_seconds),
                        allow_redirects=True,
                        stream=True,
                        headers={"User-Agent": "data-fetcher/0.1.0"},
                        verify=self.verify_ssl,
                    )
                    response.raise_for_status()
                    redirect_urls = [resp.url for resp in response.history] + [response.url]
                    for redirect_url in redirect_urls:
                        parsed_redirect = urlparse(redirect_url)
                        if not parsed_redirect.hostname or not allowed_domain(parsed_redirect.hostname, self.allowed_domains):
                            raise FetchError("redirect", "redirect destination is not allowed")
                    content_type = response.headers.get("Content-Type")
                    if not self._validate_content_type(content_type):
                        raise FetchError("content-type", "content type not allowed")
                    body = b""
                    total = 0
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            total += len(chunk)
                            if total > self.max_size_bytes:
                                raise FetchError("response-size", "response exceeds maximum size")
                            body += chunk
                    elapsed = time.monotonic() - start
                    checksum = self._hash_body(body)
                    return FetchResult(
                        url=url,
                        normalized_url=normalized_url,
                        domain=domain,
                        status_code=response.status_code,
                        content_type=response.headers.get("Content-Type"),
                        resource_type=self._classify_content_type(response.headers.get("Content-Type")),
                        content_length=total,
                        headers={k: v for k, v in response.headers.items()},
                        body=body,
                        checksum_sha256=checksum,
                        elapsed_seconds=elapsed,
                        redirect_chain=redirect_urls,
                    )
            except FetchError:
                raise
            except (InvalidURL, InvalidSchema) as exc:
                raise FetchError("network/DNS", "invalid URL") from exc
            except SSLError as exc:
                raise FetchError("TLS", "TLS failure") from exc
            except TooManyRedirects as exc:
                raise FetchError("redirect", "too many redirects") from exc
            except Timeout as exc:
                category = "timeout"
                message = "request timed out"
            except ConnectionError as exc:
                category = "network/DNS"
                message = "network connection failed"
            except HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else None
                raise FetchError("HTTP", f"HTTP error {status}") from exc
            except RequestException as exc:
                category = "unknown"
                message = "request failed"
            if attempt == self.max_retries:
                raise FetchError(category, message)
            attempt += 1
            time.sleep(self.backoff_seconds)
