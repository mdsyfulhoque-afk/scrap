from __future__ import annotations

import argparse
import http.server
import socketserver
import threading
from typing import Final

HOST: Final[str] = "127.0.0.1"
PORT: Final[int] = 8765


class SimpleHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/ok":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"live-test")
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return


def build_test_url(path: str = "/ok") -> str:
    return f"http://{HOST}:{PORT}{path}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Start a tiny local test server for live fetch testing")
    parser.add_argument("--host", default=HOST)
    parser.add_argument("--port", type=int, default=PORT)
    args = parser.parse_args()

    with socketserver.TCPServer((args.host, args.port), SimpleHandler) as httpd:
        print(f"Serving live test endpoint at http://{args.host}:{args.port}/ok")
        httpd.serve_forever()


if __name__ == "__main__":
    raise SystemExit(main())
