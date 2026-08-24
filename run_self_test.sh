#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

if [ ! -x "$ROOT_DIR/.venv/bin/python" ]; then
  echo "Virtual environment not found. Creating it..."
  python3 -m venv .venv
fi

. "$ROOT_DIR/.venv/bin/activate"
python -m pip install -e . >/dev/null 2>&1 || true

python -m pytest -q >/tmp/data_fetcher_pytest.log 2>&1 || {
  cat /tmp/data_fetcher_pytest.log
  exit 1
}

python -m data_fetcher.live_test_server > /tmp/data_fetcher_live_test.log 2>&1 &
SERVER_PID=$!
trap 'kill "$SERVER_PID" 2>/dev/null || true' EXIT

sleep 1
python -m data_fetcher.demo http://127.0.0.1:8765/ok
