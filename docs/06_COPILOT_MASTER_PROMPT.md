# Data_Fetcher_Ubuntu — Master Copilot Handover Prompt

You are taking over an EXISTING project named `Data_Fetcher_Ubuntu`.

This is NOT a greenfield project.

Your job is to inspect and preserve the existing implementation, then continue Phase 1B carefully.

## Mission

Build the acquisition/preservation foundation for a future SLM/LLM training-data pipeline.

Long-term:

```text
Source
→ Discovery
→ Acquisition
→ Raw Preservation
→ Catalog/Provenance
→ Preprocessing
→ Dataset Generation
→ Training Corpus
→ SLM/LLM
```

Current work stops before Phase 2 preprocessing.

## Existing infrastructure

MinIO:

```text
container: data-fetcher-minio
API: 9000
Console: 9001
volume: data_fetcher_ubuntu_minio_data
```

PostgreSQL:

```text
container: data-fetcher-postgres
image: postgres:18
database: data_catalog
user: datafetcher
port: 5432
volume: data_fetcher_ubuntu_postgres_data
```

PostgreSQL 18.4 has been verified.

## Existing database

Historical schema:

```text
database/init/001_initial_schema.sql
```

Already applied successfully.

Existing tables:

```text
crawl_jobs
resources
discovered_links
fetches
artifacts
```

Do NOT rewrite the initial schema.

Future schema changes use:

```text
database/migrations/
```

## Copilot instructions

The permanent project rules are already located at:

```text
.github/copilot-instructions.md
```

It is approximately 14K / 676 lines and is already installed.

DO NOT recreate, replace, shorten, or overwrite it.

Read it before making changes.

## Immediate task

Do these in order:

1. Inspect repository.
2. Inspect Docker Compose.
3. Verify Docker services.
4. Verify MinIO authentication.
5. Verify/create the `raw` bucket.
6. Verify PostgreSQL.
7. Inspect all five tables.
8. Assess whether a migration is actually needed.
9. Establish/complete storage and database abstractions.
10. Implement a controlled fetcher.
11. Implement one controlled test acquisition.
12. Verify raw object + database provenance.

## Raw storage principle

Raw data is authoritative preservation data.

Never silently transform or destroy raw payloads.

Never delete duplicate acquisitions merely because content hashes match.

Maintain separate:

- resource identity;
- URL identity;
- content identity;
- acquisition identity.

## Fetcher requirements

Must support:

- allowed sources/domains;
- timeout;
- retry;
- backoff;
- response-size limit;
- content-type handling;
- safe redirects;
- URL normalization;
- SHA-256;
- elapsed time;
- structured error categories;
- structured logging.

Never bypass:

- authentication;
- access controls;
- robots restrictions;
- CAPTCHAs;
- paywalls;
- technical protections.

## Error categories

At minimum:

- network/DNS;
- timeout;
- TLS;
- HTTP;
- redirect;
- content-type;
- response-size;
- parsing/discovery;
- storage;
- database;
- unknown.

A failed acquisition must never be recorded as successful.

## Security

Never hardcode or print:

- passwords;
- API keys;
- access tokens;
- cookies;
- authorization headers.

Use environment variables/configuration.

Do not commit secrets.

## Docker safety

Before changing `docker-compose.yml`:

1. inspect;
2. run `docker compose config`;
3. make smallest change;
4. run `docker compose up -d`;
5. verify health.

Never run:

```text
docker compose down -v
```

unless explicitly authorized.

Never delete persistent volumes casually.

## Database safety

Never modify:

```text
database/init/001_initial_schema.sql
```

to make new code work.

Use migrations for genuine schema changes.

Do not drop/truncate existing data.

## Phase boundary

Do NOT implement:

- OCR;
- normalization;
- language identification;
- quality filtering;
- PII filtering;
- advanced deduplication;
- segmentation;
- dataset construction;
- tokenization;
- training formats.

Those belong to Phase 2.

## Operating mode

Work incrementally.

For every major step:

1. inspect;
2. explain what was found;
3. make the smallest coherent change;
4. test;
5. verify;
6. report exact results.

If repository state contradicts the documentation:

STOP and inspect the actual repository.

Do not guess.

## First implementation target

The first real integration test should prove:

```text
controlled source
→ fetcher
→ SHA-256
→ MinIO raw object
→ PostgreSQL catalog
→ provenance query
```

Do not begin broad crawling.

## Definition of done

Phase 1B database/storage completion requires:

- MinIO authenticated;
- `raw` bucket verified;
- PostgreSQL healthy;
- five existing tables intact;
- required migrations safely applied, if any;
- storage abstraction working;
- database abstraction working;
- controlled fetch working;
- raw payload preserved;
- hash recorded;
- provenance recorded;
- failures classified;
- tests passing;
- no secrets committed.
