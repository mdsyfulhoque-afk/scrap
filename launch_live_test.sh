#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
. .venv/bin/activate
python -m data_fetcher.live_test_server
