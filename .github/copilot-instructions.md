# Data_Fetcher — GitHub Copilot Instructions

## 1. Project Identity

Project name: `Data_Fetcher_Ubuntu`

Purpose:

Build a robust, reproducible data acquisition and storage system that can collect heterogeneous raw data and preserve it in a form suitable for later preprocessing, dataset construction, and training of SLM/LLM systems.

Long-term objective:

`Raw acquisition → preservation → cataloging/provenance → preprocessing → dataset generation → training-ready corpora`

Important: preprocessing and model training are **Phase 2**. Do not prematurely mix them into the acquisition layer.

---

## 2. Current Phase

### Phase 1A — Infrastructure

Status: **COMPLETE / VERIFIED**

The following components have already been installed and verified:

- Ubuntu environment
- Docker / Docker Compose
- MinIO object storage
- PostgreSQL 18.4
- Persistent Docker volumes
- MinIO authentication
- PostgreSQL database `data_catalog`
- Initial PostgreSQL schema

Do not rebuild or replace these components unless explicitly instructed.

### Phase 1B — Data Acquisition Layer

Status: **NEXT**

Phase 1B will establish the controlled acquisition layer:

1. MinIO raw bucket
2. Raw-object storage conventions
3. Fetcher architecture
4. HTTP acquisition
5. Response/body preservation
6. Request/response metadata
7. Content hashing
8. Provenance
9. Crawl/fetch job tracking
10. Resource discovery
11. Safe retry/error handling
12. Deduplication at the acquisition/catalog level
13. Verification and tests

Do not begin Phase 2 preprocessing unless explicitly instructed.

---

## 3. Core Architecture

Use this architecture:

    DATA SOURCES
         |
         v
      FETCHER
       /   \
      /     \
     v       v
  MINIO   POSTGRESQL
  RAW       CATALOG
  DATA
     \       /
      \     /
       \   /
        v
   PHASE 2 LATER
   preprocessing
   dataset generation
   training data

### Separation of responsibilities

MinIO is the primary storage location for large/raw objects.

PostgreSQL is the metadata/catalog/provenance system.

Do NOT store large HTML, PDF, image, audio, video, archive, or other raw payloads directly inside PostgreSQL unless a future design explicitly requires it.

PostgreSQL should store references/metadata such as:

- resource identity
- URL
- normalized URL
- domain
- resource type
- discovery information
- fetch information
- timestamps
- content hashes
- storage/object keys
- status
- metadata
- provenance

---

## 4. Verified PostgreSQL State

Database:

`data_catalog`

User:

`datafetcher`

Verified tables:

- `crawl_jobs`
- `resources`
- `discovered_links`
- `fetches`
- `artifacts`

The existing schema has already been applied successfully.

Do not casually modify, drop, rename, or recreate these tables.

Before changing the schema:

1. inspect the existing schema;
2. explain why a migration is necessary;
3. prefer a migration over editing/replacing the initial schema;
4. preserve backward compatibility where practical;
5. obtain explicit approval before destructive changes.

---

## 5. Verified MinIO State

MinIO container:

`data-fetcher-minio`

API:

`http://localhost:9000`

Console:

`http://localhost:9001`

The MinIO server is healthy and authentication has been verified.

The intended raw bucket is:

`raw`

Before creating or changing buckets, verify the current bucket state.

Use the existing MinIO credentials/configuration through environment variables or secure configuration mechanisms.

Never print secrets into source code, logs, documentation, commits, or error messages.

---

## 6. Raw Data Principle

### RAW DATA MUST BE PRESERVED

The acquisition layer must preserve the closest practical representation of what was actually retrieved.

Never silently:

- clean HTML;
- rewrite text;
- remove boilerplate;
- normalize Unicode;
- translate content;
- summarize content;
- tokenize content;
- filter training examples;
- remove duplicates from the raw store;
- overwrite a previously acquired raw object.

Those operations belong to later processing stages.

If transformation is necessary for acquisition/transport, preserve the original whenever practical and record the transformation in metadata.

---

## 7. Proposed MinIO Raw Layout

Use object prefixes rather than creating unnecessary filesystem-style directories.

Conceptual layout:

    raw/
    ├── web/
    │   └── <domain>/
    │       └── <date>/
    │           └── <resource-id>/
    │               ├── response.bin
    │               ├── metadata.json
    │               └── headers.json
    │
    ├── documents/
    │   └── <domain>/
    │       └── <date>/
    │           └── <resource-id>/
    │               ├── original.pdf
    │               └── metadata.json
    │
    ├── api/
    │   └── <source>/
    │       └── <date>/
    │           └── <resource-id>/
    │               ├── response.json
    │               └── metadata.json
    │
    └── archives/
        └── <source>/
            └── <date>/
                └── <resource-id>/
                    └── original.warc

This is a design convention, not permission to create all of these prefixes immediately.

Create only what Phase 1B actually needs.

---

## 8. Acquisition Metadata

For each fetched resource, design the system to capture as much of the following as is available and appropriate:

### Identity

- resource ID
- URL
- normalized URL
- domain
- source
- parent/discovery resource

### Timing

- discovered timestamp
- fetch-start timestamp
- fetch-completion timestamp
- first-seen timestamp
- last-seen timestamp

### HTTP

- HTTP method
- status code
- response headers
- content type
- content length
- final URL after redirects
- redirect information
- user-agent/version

### Content

- byte size
- cryptographic content hash
- storage/object key
- encoding where known
- detected media/content type

### Execution

- crawl job ID
- fetch status
- retry count
- error category
- error message where safe
- elapsed time

### Provenance

The system must be able to answer:

> Where did this object come from, when was it fetched, how was it fetched, and which acquisition job produced it?

---

## 9. Hashing and Deduplication

Use content hashing for raw payload identity.

Do not assume:

`URL == content identity`

Different URLs may contain identical content.

Likewise:

`same URL != guaranteed same content forever`

Therefore maintain separate concepts for:

- resource identity
- URL identity
- content identity
- acquisition event

Do not delete duplicate raw acquisitions merely because their content hashes match unless an explicit retention policy is later approved.

The raw layer should favor reproducibility over aggressive space optimization.

---

## 10. Fetcher Design Rules

The fetcher must be:

- modular;
- testable;
- retry-aware;
- timeout-aware;
- observable;
- resumable where practical;
- deterministic where practical;
- respectful of server policies;
- safe against uncontrolled crawling.

Do not build an uncontrolled internet crawler.

Implement explicit:

- allowed domains/sources;
- request timeouts;
- concurrency limits;
- retry limits;
- backoff;
- maximum response size;
- content-type handling;
- URL normalization;
- crawl/job boundaries;
- logging.

Never bypass authentication, access controls, robots restrictions, paywalls, CAPTCHAs, or other technical protections.

Only acquire data that the configured source and project policy permit us to retrieve.

---

## 11. Error Handling

Errors must be classified rather than swallowed.

At minimum distinguish:

- DNS/network failure
- connection timeout
- TLS failure
- HTTP error
- redirect failure
- content-type rejection
- response-size limit
- parsing/discovery failure
- storage failure
- database failure
- unknown failure

A failed fetch must not be represented as a successful acquisition.

Do not silently continue after database/storage corruption or schema errors.

---

## 12. Logging

Logs should be useful for debugging and auditing.

Include identifiers such as:

- crawl job ID
- resource ID
- URL
- fetch ID
- status
- duration
- error category

Never log:

- passwords
- API keys
- access tokens
- cookies
- authorization headers
- secret environment variables

Avoid logging complete raw document bodies.

---

## 13. Configuration and Secrets

Never hardcode credentials in Python, shell scripts, tests, or application source.

Prefer:

- `.env`
- Docker Compose environment variables
- environment-specific configuration
- secret managers later when appropriate

If an existing file currently contains credentials, do not expose or duplicate them in new source files.

Do not commit `.env` or secret files.

Ensure `.gitignore` protects local secrets.

---

## 14. Docker Rules

Existing working Docker services are infrastructure.

Do not replace:

- MinIO
- PostgreSQL
- Docker Compose

with another technology unless explicitly instructed.

Before modifying `docker-compose.yml`:

1. inspect the current file;
2. inspect running containers;
3. run `docker compose config`;
4. explain the proposed change;
5. make the smallest safe change;
6. verify with `docker compose up -d`;
7. verify health/status.

Do not casually delete persistent volumes.

Never run destructive commands such as:

`docker compose down -v`

unless explicitly instructed.

---

## 15. Database Migration Rules

The initial schema is:

`database/init/001_initial_schema.sql`

Treat it as the historical initial schema.

For future schema changes, use migration files such as:

`database/migrations/002_*.sql`

Do not rewrite the original migration merely to make new code work.

Before applying a migration:

- inspect the current schema;
- verify the migration is idempotent where appropriate;
- avoid destructive operations;
- test against the local PostgreSQL instance.

---

## 16. Code Quality

Prefer:

- Python 3
- type hints
- clear modules
- small functions
- dependency injection where useful
- structured logging
- explicit configuration
- unit tests
- integration tests
- meaningful error classes
- clear docstrings for public interfaces

Avoid:

- giant single-file applications;
- duplicated database logic;
- hidden global state;
- hardcoded credentials;
- arbitrary magic numbers;
- silent exception handling;
- unnecessary frameworks.

Do not add dependencies unless they provide a clear benefit.

---

## 17. Testing Requirements

Every major Phase 1B component should have tests.

At minimum test:

### Storage

- MinIO connection
- bucket existence
- object upload
- object retrieval
- object metadata

### Database

- connection
- schema availability
- resource insertion
- fetch recording
- artifact recording
- relationship integrity

### Fetcher

- successful HTTP response
- redirect
- timeout
- HTTP failure
- invalid content
- content-size limit
- hash generation
- metadata generation

### Integration

A test acquisition should be able to demonstrate:

`source → fetcher → raw object → PostgreSQL catalog`

without requiring the real internet for every automated test.

Use mocked/local test fixtures wherever practical.

---

## 18. Phase Boundaries

### Phase 1

Concerned with acquisition and preservation.

### Phase 2

Will later handle:

- parsing
- text extraction
- OCR
- normalization
- language identification
- quality filtering
- PII/safety filtering
- deduplication
- document segmentation
- metadata enrichment
- dataset construction
- train/validation/test generation
- tokenization
- training formats

Do NOT implement Phase 2 features just because they appear useful.

---

## 19. Ultimate Model Requirement

The long-term objective is to build the data foundation for training a high-capability SLM/LLM.

Therefore the acquisition system should preserve enough provenance and metadata to later support:

- dataset lineage;
- source attribution;
- reproducibility;
- quality scoring;
- filtering;
- deduplication;
- domain balancing;
- temporal analysis;
- contamination analysis;
- dataset versioning;
- training-corpus reconstruction.

Do not optimize the raw layer solely for today's crawler.

Design it so that future dataset-generation pipelines can consume it reliably.

---

## 20. Architecture Before Code

When asked to implement a new component:

1. Inspect the existing repository.
2. Identify existing components that already solve part of the problem.
3. Reuse existing abstractions where appropriate.
4. State the intended change briefly.
5. Implement the smallest coherent change.
6. Run relevant tests.
7. Verify integration with MinIO/PostgreSQL where applicable.
8. Report exactly what changed and what was verified.

Do not create parallel implementations of functionality that already exists.

---

## 21. Do Not Guess

If repository state contradicts these instructions:

- inspect the actual files;
- inspect Docker state;
- inspect PostgreSQL schema;
- inspect MinIO state;
- report the discrepancy.

Do not silently overwrite working infrastructure.

If a requirement is ambiguous and could affect data integrity, stop and ask for clarification.

---

## 22. Current Next Task

The immediate next task is **Phase 1B initialization**.

Before implementing the crawler/fetcher:

1. verify MinIO authentication;
2. create the `raw` bucket if it does not exist;
3. verify the bucket;
4. verify PostgreSQL connectivity;
5. verify the existing five-table schema;
6. inspect the repository structure;
7. establish the Phase 1B application layout;
8. only then begin the fetcher implementation.

Do not start broad crawling yet.

Start with a controlled test acquisition.

---

## 23. Working Principle

The project follows this rule:

**Acquire first. Preserve first. Catalog everything. Transform later.**

Raw data is valuable because it allows future preprocessing and dataset-generation strategies to change without having to reacquire the source.

Do not destroy information unnecessarily.
Do not silently transform data.
Do not bypass source protections.
Do not make destructive infrastructure changes.
Do not move to Phase 2 prematurely.
