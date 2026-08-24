# Overall Overview — Phase 1 Progress (0% → now)

## Date

2026-08-10

## Purpose

This document provides a concise, actionable overview of what has been implemented from project inception (0%) to the current state. It focuses on Phase 1: raw data acquisition and preservation (Phase 1A infrastructure + Phase 1B controlled acquisition).

## High-level summary

- Project goal: Build a robust acquisition layer that preserves raw data, records provenance, and stores payloads in object storage (MinIO) with metadata in PostgreSQL.
- Phase completed so far: core infrastructure verified, controlled fetcher implemented and integrated with MinIO + PostgreSQL, test coverage for key failure paths and repeat acquisitions.

## Completion estimate

- Estimated completion of Phase 1B so far: ~65% (see `progressv6.md`).

## What was done (from 0% → now)

1. Infrastructure and schema (Phase 1A)
   - Docker Compose services provisioned for MinIO and PostgreSQL.
   - Verified MinIO is reachable and healthy (ports `9000` and `9001`).
   - Verified PostgreSQL service and `data_catalog` database with initial schema applied from `database/init/001_initial_schema.sql`.
   - Confirmed the existence of the five catalogue tables: `resources`, `fetches`, `artifacts`, `crawl_jobs`, `discovered_links`.

2. Configuration and environment
   - Implemented environment-driven configuration in `src/data_fetcher/config.py` with `.env` file support and sensible fallbacks.
   - Ensured required secrets are validated at runtime (`MINIO_SECRET_KEY`, `POSTGRES_PASSWORD`).

3. Storage abstraction
   - Implemented `src/data_fetcher/storage.py` (`MinioStorage`) with:
     - `ensure_bucket()` to verify or create the `raw` bucket.
     - `upload_object()`, `get_object()`, `get_object_metadata()`, and `object_exists()` helpers.
   - Storage uses S3-compatible `boto3` client with endpoint configuration.

4. Database access layer
   - Implemented `src/data_fetcher/database.py` with:
     - Connection management and transactional helpers.
     - `ensure_resource()`, `create_fetch()`, `create_artifact()` and `get_provenance()` functions.
     - Added `complete_fetch()` and improved fetch status handling.
     - `get_provenance()` now returns `resource_id` along with artifact and fetch information.

5. Controlled fetcher
   - Implemented `src/data_fetcher/fetcher.py` (`Fetcher`) supporting:
     - URL normalization and domain allow-list validation.
     - Timeouts, retries, backoff, and redirect checks.
     - Response-size limit and chunked streaming to avoid large in-memory reads.
     - Content-type classification and allowlist enforcement.
     - SHA-256 hashing of the raw payload.
     - Granular error classification via `FetchError` (categories: `HTTP`, `timeout`, `TLS`, `redirect`, `content-type`, `response-size`, `network/DNS`, etc.).

6. Runner / orchestrator
   - Implemented `src/data_fetcher/runner.py` with `run_controlled_fetch()`:
     - Creates or re-uses `resource` rows via `ensure_resource()`.
     - Creates a `fetch` row before network operations so that failures are recorded.
     - Uploads raw payload to MinIO and records artifacts.
     - Marks fetch records complete via `complete_fetch()` and updates crawl job status.

7. Tests and verification
   - Added and run unit tests and integration tests under `tests/`:
     - `tests/test_fetcher.py` includes success cases and deterministic failure-path tests (content-type rejection, size limit, timeout/retry behavior).
     - `tests/test_integration.py` ensures controlled integration end-to-end and repeat acquisition behavior (same resource_id, different fetch_id/artifact).
     - `tests/test_storage.py` and `tests/test_database.py` verify storage and DB helpers.
   - Created a local virtual environment and ran the test suite; result: `8 passed`.

8. Progress tracking and documentation
   - Updated `progress.md` to reflect current status.
   - Added `progressv6.md` summarizing the v6 snapshot.
   - Added this `docs/07_OVERALL_OVERVIEW.md` for a concise end-to-end summary.

## Key design decisions and guarantees

- Raw payloads are preserved unchanged and stored in MinIO; only metadata and references are stored in PostgreSQL.
- Content identity is tracked via SHA-256 checksums; identical content from repeated acquisitions results in separate artifact records (no automatic dedupe in the raw store).
- Database schema is preserved; new behavior implemented via application logic and non-destructive modifications.
- Fetch attempts are recorded even on failure to ensure provenance and observability.

## Next recommended actions

1. Expand failure-path tests to include:
   - redirect chain rejection
   - TLS failures
   - explicit network/DNS errors (mock/stub)
2. Add retention/dedupe policy discussion and optional dedupe step (Phase 2 decision).
3. Add a small `bin/demo_fetch.py` script that runs a controlled fetch and prints provenance.
4. Create CI workflow to run tests in a reproducible environment with mocked MinIO/Postgres or a docker-compose job.

## Reference files

- `database/init/001_initial_schema.sql`
- `src/data_fetcher/config.py`
- `src/data_fetcher/storage.py`
- `src/data_fetcher/database.py`
- `src/data_fetcher/fetcher.py`
- `src/data_fetcher/runner.py`
- `tests/test_fetcher.py`
- `tests/test_integration.py`
- `progress.md`, `progressv6.md`

---

If you want, I can:
- Commit these changes and open a single patch/PR.
- Add the demo script and CI config.
- Expand test coverage for the other failure classes now.

Which of these would you like next?# Overall Overview — 0% → Now

Date: 2026-08-10

This document summarizes what has been implemented in the repository from project initiation (0%) through the current state (Phase 1B continuation). It is intended as a concise handoff-ready overview for maintainers and reviewers.

## High-level status

- Current phase: Phase 1B — Controlled acquisition, raw preservation, and provenance cataloging.
- Estimated completion: 65% (end-to-end acquisition + storage + provenance validated; more tests and failure classes remain).

## What was present at 0% (baseline)

- Project skeleton: README, pyproject.toml, docker-compose.yml, docs/, src/, tests/.
- Infrastructure definitions for MinIO and PostgreSQL in `docker-compose.yml`.
- Initial PostgreSQL schema in `database/init/001_initial_schema.sql` describing the five key tables: `crawl_jobs`, `resources`, `fetches`, `artifacts`, and `discovered_links`.

## What has been implemented (0% → now)

1. Environment & configuration
   - Added a robust `load_config()` in `src/data_fetcher/config.py` supporting `.env` overrides and tolerant fallbacks for MinIO and PostgreSQL credentials.
   - Config parameters for fetch timeouts, size limits, allowed domains, and allowed content types.

2. Storage integration
   - Implemented `MinioStorage` in `src/data_fetcher/storage.py` with:
     - `ensure_bucket()` to verify or create the `raw` bucket.
     - `upload_object()`, `get_object()`, `object_exists()` and `get_object_metadata()` wrappers.
   - Verified MinIO authentication and bucket existence during integration tests.

3. Database / Catalog
   - Implemented `Database` abstraction in `src/data_fetcher/database.py` to:
     - Create crawl jobs, resources, fetches, and artifacts.
     - Query acquisition provenance via `get_provenance()` (now returns `resource_id`).
     - Added `complete_fetch()` helper to atomically mark fetch completion metadata.
   - Tests verify insertion and provenance lookups.

4. Fetcher
   - Implemented `Fetcher` in `src/data_fetcher/fetcher.py` with:
     - URL normalization and domain allowlisting.
     - Connect/read timeouts, retries and backoff, max redirects.
     - Response-size enforcement and streaming read.
     - Content-type classification and allowlist validation.
     - SHA-256 hashing of raw payload.
     - Rich error classification via `FetchError` (timeout, redirect, content-type, network, TLS, HTTP, response-size).

5. Orchestration / Runner
   - Implemented `run_controlled_fetch()` in `src/data_fetcher/runner.py` to:
     - Pre-create a `fetch` record (status `running`) linked to a `resource` and `crawl_job`.
     - Execute the fetch, upload raw payload to MinIO, create an `artifact` record, and mark the fetch `success`/`failed` using `complete_fetch()` / `update_fetch_status()`.
     - Preserve metadata such as checksum, redirect chain, headers, and timing.

6. Tests and verification
   - Unit tests for fetcher under deterministic local HTTP fixtures (`tests/test_fetcher.py`): success, 404 handling, domain allowlist, content-type rejection, response-size limit, and timeout/retry exhaustion.
   - Integration tests (`tests/test_integration.py`) using a local HTTP server and live MinIO/Postgres to validate:
     - end-to-end fetch → MinIO → PostgreSQL provenance recording
     - repeat acquisitions: same `resource` reused, distinct `fetch` and `artifact` records created
   - All local tests pass: `8 passed` (after adding and running the virtualenv and dependencies).

7. Documentation / Progress files
   - Updated `progress.md` with current Phase 1B status and created `progressv6.md` capturing the recent changes.
   - Added this `docs/07_OVERALL_OVERVIEW.md` for a consolidated handoff view.

## Files created or modified (not exhaustive)

- Created: `docs/07_OVERALL_OVERVIEW.md`, `progressv6.md`
- Modified: `progress.md`
- Key source files changed:
  - `src/data_fetcher/config.py`
  - `src/data_fetcher/storage.py`
  - `src/data_fetcher/database.py`
  - `src/data_fetcher/fetcher.py`
  - `src/data_fetcher/runner.py`
  - `src/data_fetcher/models.py`
- Tests added/updated:
  - `tests/test_fetcher.py` (failure paths added)
  - `tests/test_integration.py` (repeat acquisition test)

## What remains (next priorities)

- Broaden failure-path SQA: redirects to disallowed hosts, TLS failures, DNS/network errors, retry exhaustion behavior, and storage failures.
- Add redirect-chain integration tests and larger payload handling tests (streaming / enforced limits).
- Harden duplicate-content policy and retention (debate deduplication vs. full preservation).
- Build a small CLI/demo script to run a controlled job and print provenance for quick manual verification.
- Prepare migration path and non-destructive schema changes if Phase 1B requires metadata extensions.

## How to reproduce the current test run locally

1. Create a Python virtualenv and install dependencies (example):

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip setuptools wheel
.venv/bin/python -m pip install -r <(python3 - <<'PY'
import tomllib
p = open('pyproject.toml','rb').read()
project = tomllib.loads(p)
print('\n'.join(project['project']['dependencies']))
PY)
```

2. Run the tests:

```bash
.venv/bin/python -m pytest -q
```

(Adjust environment variables for MinIO/Postgres when running integration tests.)

## Contact / Next action

If you'd like, I can:
- Commit these changes to a branch and open a patch/PR.
- Add the CLI demo runner and a small README describing usage.
- Expand tests for the remaining failure classes now.

---

Path: docs/07_OVERALL_OVERVIEW.md
