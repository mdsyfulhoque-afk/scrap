from __future__ import annotations

import http.server
import socketserver
import threading
import uuid

import pytest

from data_fetcher.config import load_config
from data_fetcher.database import Database
from data_fetcher.fetcher import Fetcher
from data_fetcher.runner import run_controlled_fetch
from data_fetcher.storage import MinioStorage


class SimpleIntegrationHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/ok":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"integration-test")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        return


@pytest.fixture(scope="module")
def local_server():
    with socketserver.TCPServer(("127.0.0.1", 0), SimpleIntegrationHandler) as httpd:
        port = httpd.server_address[1]
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        yield f"http://127.0.0.1:{port}"
        httpd.shutdown()
        thread.join()


def test_controlled_integration(local_server, monkeypatch):
    monkeypatch.setenv("FETCH_ALLOWED_DOMAINS", "127.0.0.1")
    config = load_config()
    storage = MinioStorage(
        endpoint_url=config.minio_endpoint,
        access_key=config.minio_access_key,
        secret_key=config.minio_secret_key,
        bucket_name=config.minio_bucket,
    )
    storage.ensure_bucket()

    # run controlled fetch using the helper runner
    provenance = run_controlled_fetch(f"{local_server}/ok")

    assert provenance["resource_url"] == f"{local_server}/ok"
    assert provenance["http_status"] == 200
    assert provenance["bucket_name"] == config.minio_bucket
    assert provenance["checksum_sha256"] is not None
    assert provenance["object_key"] is not None

    object_data = storage.get_object(provenance["object_key"])
    assert object_data == b"integration-test"

    # verify the object metadata is present
    metadata = storage.get_object_metadata(provenance["object_key"])
    assert metadata.get("checksum_sha256") == provenance["checksum_sha256"]


def test_repeat_acquisition_uses_same_resource(monkeypatch, local_server):
    monkeypatch.setenv("FETCH_ALLOWED_DOMAINS", "127.0.0.1")
    config = load_config()
    storage = MinioStorage(
        endpoint_url=config.minio_endpoint,
        access_key=config.minio_access_key,
        secret_key=config.minio_secret_key,
        bucket_name=config.minio_bucket,
    )
    storage.ensure_bucket()

    first_provenance = run_controlled_fetch(f"{local_server}/ok")
    second_provenance = run_controlled_fetch(f"{local_server}/ok")

    assert first_provenance["resource_url"] == second_provenance["resource_url"]
    assert first_provenance["resource_id"] == second_provenance["resource_id"]
    assert first_provenance["fetch_id"] != second_provenance["fetch_id"]
    assert first_provenance["object_key"] != second_provenance["object_key"]

    # verify two distinct artifacts exist
    assert storage.object_exists(first_provenance["object_key"])
    assert storage.object_exists(second_provenance["object_key"])
