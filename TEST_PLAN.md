# Data_Fetcher_Ubuntu_Phase2 — Human Test Plan

**Date:** 2026-08-19  
**Tester:** Human operator  
**Project path:** /run/media/farhan/New Volume/Projects/Data_Fetcher_Ubuntu_Phase2  
**Dependencies:** Docker Compose (PostgreSQL + MinIO), Python 3.14+, .venv  

---

## Pre-flight

```bash
# 1. Start infrastructure
cd "/run/media/farhan/New Volume/Projects/Data_Fetcher_Ubuntu_Phase2"
docker compose up -d

# 2. Activate venv
source .venv_new/bin/activate

# 3. Install package in editable mode
pip install -e .
```

**Expected:** `Successfully installed data_fetcher-0.2.0`

---

## Test 1 — pytest without PYTHONPATH (Bug 4)

```bash
cd "/run/media/farhan/New Volume/Projects/Data_Fetcher_Ubuntu_Phase2"
python -m pytest tests/ -q
```

**Expected output:** `183 passed in X.XXs`  
**Pass criteria:** No `ModuleNotFoundError: No module named 'data_fetcher'`

---

## Test 2 — Editable install from clean path (Bug 5)

```bash
cd /
pip install -e "/run/media/farhan/New Volume/Projects/Data_Fetcher_Ubuntu_Phase2"
```

**Expected output:** `Successfully installed data_fetcher-0.2.0`  
**Pass criteria:** Install succeeds without path-encoding errors

---

## Test 3 — --help CLI behaviour (Bug 3)

```bash
cd "/run/media/farhan/New Volume/Projects/Data_Fetcher_Ubuntu_Phase2"
python -m data_fetcher.demo --help
```

**Expected output:** argparse usage text showing `url`, `phase2`, `fetch` options and `-h, --help`  
**Pass criteria:** Does NOT attempt to fetch a URL named `--help`; exits 0

---

## Test 4 — SSL toggle (Bug 1)

### 4a. Default (SSL enabled)

```bash
cd "/run/media/farhan/New Volume/Projects/Data_Fetcher_Ubuntu_Phase2"
python -c "
from data_fetcher.fetcher import Fetcher
f = Fetcher(
    connect_timeout_seconds=5,
    read_timeout_seconds=5,
    max_size_bytes=1024,
    max_retries=0,
    backoff_seconds=1,
    max_redirects=1,
    allowed_domains=['example.com'],
    allowed_content_types=['text/html'],
)
print('verify_ssl =', f.verify_ssl)
"
```

**Expected:** `verify_ssl = True`

### 4b. Disabled via env var

```bash
cd "/run/media/farhan/New Volume/Projects/Data_Fetcher_Ubuntu_Phase2"
DATA_FETCHER_SSL_VERIFY=false python -c "
from data_fetcher.fetcher import Fetcher
f = Fetcher(
    connect_timeout_seconds=5,
    read_timeout_seconds=5,
    max_size_bytes=1024,
    max_retries=0,
    backoff_seconds=1,
    max_redirects=1,
    allowed_domains=['example.com'],
    allowed_content_types=['text/html'],
)
print('verify_ssl =', f.verify_ssl)
"
```

**Expected:** `verify_ssl = False`

### 4c. Disabled via constructor

```bash
cd "/run/media/farhan/New Volume/Projects/Data_Fetcher_Ubuntu_Phase2"
python -c "
from data_fetcher.fetcher import Fetcher
f = Fetcher(
    connect_timeout_seconds=5,
    read_timeout_seconds=5,
    max_size_bytes=1024,
    max_retries=0,
    backoff_seconds=1,
    max_redirects=1,
    allowed_domains=['example.com'],
    allowed_content_types=['text/html'],
    verify_ssl=False,
)
print('verify_ssl =', f.verify_ssl)
"
```

**Expected:** `verify_ssl = False`

**Pass criteria:** All three variants produce the expected boolean value

---

## Test 5 — Language persistence (Bug 2)

### 5a. Run quality on a document

```bash
cd "/run/media/farhan/New Volume/Projects/Data_Fetcher_Ubuntu_Phase2"
python -m data_fetcher.demo phase2 quality cc40272b-76dc-46b8-9a60-b4eb68d45c0f
```

**Expected output:** Includes `Detected language: English` and `Confidence: high`

### 5b. Verify language is in database

```bash
cd "/run/media/farhan/New Volume/Projects/Data_Fetcher_Ubuntu_Phase2"
python -c "
import psycopg, os
dsn = f'postgresql://{os.environ.get(\"POSTGRES_USER\", \"datafetcher\")}:{os.environ.get(\"POSTGRES_PASSWORD\", \"DataFetcher-Postgres-2026!\")}@{os.environ.get(\"POSTGRES_HOST\", \"localhost\")}:{os.environ.get(\"POSTGRES_PORT\", \"5432\")}/{os.environ.get(\"POSTGRES_DATABASE\", \"data_catalog\")}'
with psycopg.connect(dsn, autocommit=False) as conn:
    with conn.cursor(row_factory=psycopg.rows.class_row(dict)) as cur:
        cur.execute('''SELECT nd.id, nd.quality_signals->'language' as lang FROM normalized_documents nd ORDER BY nd.created_at DESC LIMIT 1''')
        r = cur.fetchone()
        print('language =', r['lang'])
        assert r['lang'] is not None, 'language is None!'
        assert r['lang']['code'] == 'English', 'language code mismatch!'
        print('PASS: language persisted')
"
```

**Expected output:** `language = {'code': 'English', ...}` and `PASS: language persisted`  
**Pass criteria:** `quality_signals->'language'` is not NULL and contains `code`, `confidence`, `method`, `detected_at`

---

## Test 6 — End-to-end DSE acceptance without curl -k (Bug 1 workaround elimination)

### 6a. Ingest DSE pages using project's own fetcher

```bash
cd "/run/media/farhan/New Volume/Projects/Data_Fetcher_Ubuntu_Phase2"
DATA_FETCHER_SSL_VERIFY=false python scripts/dse_acceptance_ingest.py
```

**Expected:** 3 artifacts created with SHA-256 checksums printed

### 6b. Run Phase 2 pipeline

```bash
cd "/run/media/farhan/New Volume/Projects/Data_Fetcher_Ubuntu_Phase2"
python scripts/dse_acceptance_phase2.py
```

**Expected:** 
- 3 artifacts verified
- 3 characterizations created
- 3 canonical documents created
- 3 normalized documents created
- 0 duplicate groups (correct — distinct content)
- Exit code 0

### 6c. Verify dataset JSONL contains language field

```bash
cd "/run/media/farhan/New Volume/Projects/Data_Fetcher_Ubuntu_Phase2"
python scripts/dse_acceptance_dataset.py
grep '"language"' scripts/dse_output/dataset.jsonl | head -3
```

**Expected:** Each record contains a `language` key with value like `"unknown"` or detected language  
**Pass criteria:** No record is missing the `language` field

---

## Test 7 — Acceptance SQL fix (Bug 6)

The `scripts/dse_acceptance_phase2.py` queries should not reference `a.resource_url`.

```bash
cd "/run/media/farhan/New Volume/Projects/Data_Fetcher_Ubuntu_Phase2"
grep -n "a.resource_url" scripts/dse_acceptance_phase2.py
```

**Expected:** No output (empty grep result)  
**Pass criteria:** Zero references to `a.resource_url` in the script

---

## Summary Checklist

| Test | Status |
|------|--------|
| pytest 183/183 without PYTHONPATH | ☐ |
| Editable install from clean path | ☐ |
| `--help` shows argparse help | ☐ |
| SSL toggle: default True | ☐ |
| SSL toggle: env var false | ☐ |
| SSL toggle: constructor false | ☐ |
| Language persisted in DB | ☐ |
| DSE ingestion with SSL disabled | ☐ |
| DSE Phase 2 pipeline completes | ☐ |
| Dataset JSONL has language field | ☐ |
| No `a.resource_url` references | ☐ |

**Overall pass criteria:** All 11 checks pass.
