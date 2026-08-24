# Data_Fetcher_Ubuntu — Phase 1B Continuation

## Current Continuation Point

The project has completed the initial infrastructure and schema setup.

The next work is Phase 1B.

## Immediate Sequence

### Step 1 — Verify repository

Inspect:

```bash
pwd
find . -maxdepth 3 -type f | sort
```

Do not modify files during initial inspection.

### Step 2 — Verify Docker

Run:

```bash
docker compose ps
docker compose config
```

Expected infrastructure:

- MinIO running/healthy;
- PostgreSQL running/healthy.

### Step 3 — Verify MinIO authentication

The `mc` client inside the MinIO container requires an explicit alias.

Use the existing configured credentials without printing secrets into source files.

Then:

```bash
docker exec data-fetcher-minio mc ls local
```

### Step 4 — Create/verify raw bucket

If `raw` does not exist:

```bash
docker exec data-fetcher-minio \
mc mb --ignore-existing local/raw
```

Then:

```bash
docker exec data-fetcher-minio \
mc ls local
```

Expected:

```text
raw
```

Do not delete any other bucket.

### Step 5 — Verify PostgreSQL

```bash
docker exec -it data-fetcher-postgres \
psql -U datafetcher -d data_catalog \
-c "SELECT version();"
```

Then:

```bash
docker exec -it data-fetcher-postgres \
psql -U datafetcher -d data_catalog \
-c "\dt"
```

Expected five existing tables:

```text
artifacts
crawl_jobs
discovered_links
fetches
resources
```

### Step 6 — Inspect the complete schema

Inspect:

```text
crawl_jobs
resources
discovered_links
fetches
artifacts
```

Determine whether the current schema already supports the Phase 1B requirements.

Only create a migration if required.

### Step 7 — Inspect application repository

Identify:

- existing Python files;
- configuration;
- requirements/dependencies;
- tests;
- storage code;
- database code;
- logging;
- entry points.

Reuse existing architecture where present.

### Step 8 — Storage abstraction

Implement or complete a MinIO abstraction supporting:

- bucket verification;
- upload;
- retrieval;
- object existence;
- object metadata;
- deterministic object-key generation.

### Step 9 — Database abstraction

Implement or complete PostgreSQL access supporting:

- connection;
- transactions;
- resource recording;
- fetch recording;
- artifact recording;
- provenance queries.

### Step 10 — Controlled fetcher

Implement:

- URL validation;
- source/domain allowlist;
- timeout;
- retry;
- backoff;
- response-size limit;
- content-type checks;
- redirect handling;
- SHA-256 hashing;
- error classification;
- elapsed-time measurement.

### Step 11 — Controlled integration test

Demonstrate:

```text
controlled source
      ↓
fetcher
      ↓
SHA-256
      ↓
MinIO raw object
      ↓
PostgreSQL fetch/artifact record
      ↓
provenance query
```

Do not begin broad crawling.

## Definition of Done

Phase 1B storage/database integration is complete when:

- MinIO authentication works;
- `raw` exists;
- PostgreSQL remains healthy;
- the five existing tables remain intact;
- any required migration is applied safely;
- the application connects to MinIO;
- the application connects to PostgreSQL;
- one controlled acquisition succeeds;
- raw payload is preserved;
- SHA-256 is recorded;
- acquisition provenance is queryable;
- failures are classified;
- tests pass;
- no secrets are committed.
