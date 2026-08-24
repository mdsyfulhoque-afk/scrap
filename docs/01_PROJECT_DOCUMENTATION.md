# Data_Fetcher_Ubuntu — Full Project Documentation

## 1. Introduction

`Data_Fetcher_Ubuntu` is a data acquisition and preservation system being developed as the foundation for a future high-capability SLM/LLM training pipeline.

The long-term objective is:

> Acquire first. Preserve first. Catalog everything. Transform later.

The system is deliberately being built in phases so that raw source data remains available for future preprocessing, dataset construction, filtering, deduplication, and training-corpus generation.

## 2. Long-Term Vision

The intended lifecycle is:

```text
Permitted Sources
      ↓
Discovery
      ↓
Acquisition / Fetching
      ↓
Raw Preservation
      ↓
Metadata + Provenance Catalog
      ↓
Validation
      ↓
Phase 2 Preprocessing
      ↓
Dataset Generation
      ↓
Training Corpus
      ↓
SLM / LLM Training
```

Phase 1 focuses on acquisition and preservation.

Phase 2 will later handle parsing, extraction, OCR, normalization, language identification, quality filtering, PII/safety filtering, deduplication, segmentation, enrichment, dataset generation, tokenization, and training formats.

## 3. Why Raw Preservation Comes First

A future preprocessing strategy may change.

For example, a document that is currently treated as plain text may later require:

- better extraction;
- OCR;
- improved language identification;
- different filtering;
- different segmentation;
- different deduplication;
- different dataset weighting.

If the original payload has been preserved, these decisions can be changed without reacquiring the source.

Therefore the raw layer should prioritize reproducibility and provenance over aggressive storage optimization.

## 4. Identity Model

The system deliberately separates:

- resource identity;
- URL identity;
- content identity;
- acquisition-event identity.

A URL is not a content identity.

Different URLs may contain identical content.

The same URL may return different content over time.

Content hashing therefore complements, rather than replaces, acquisition provenance.

## 5. Current Technology Foundation

The currently established infrastructure is:

| Component | Current role |
|---|---|
| Ubuntu | Development/host environment |
| Docker Compose | Local infrastructure orchestration |
| MinIO | S3-compatible raw object storage |
| PostgreSQL 18 | Metadata/catalog/provenance database |
| Python | Intended application/fetcher implementation |
| GitHub Copilot | Assisted continuation/development |

## 6. Current Docker Services

### MinIO

Container:

`data-fetcher-minio`

Ports:

- `9000` — S3/API
- `9001` — MinIO console

Persistent volume:

`data_fetcher_ubuntu_minio_data`

### PostgreSQL

Container:

`data-fetcher-postgres`

Image:

`postgres:18`

Database:

`data_catalog`

User:

`datafetcher`

Port:

`5432`

Persistent volume:

`data_fetcher_ubuntu_postgres_data`

## 7. Database

The historical initial schema is:

`database/init/001_initial_schema.sql`

The schema has been successfully applied to PostgreSQL.

Existing tables:

1. `crawl_jobs`
2. `resources`
3. `discovered_links`
4. `fetches`
5. `artifacts`

Future schema changes should use:

`database/migrations/002_*.sql`

and subsequent migrations.

The initial schema must not be rewritten simply to accommodate new code.

## 8. Provenance Requirement

The system must eventually be able to answer:

> Where did this object come from, when was it fetched, how was it fetched, and which acquisition job produced it?

Acquisition metadata should support concepts including:

- crawl job;
- resource;
- fetch/acquisition event;
- source URL;
- retrieval timestamp;
- HTTP metadata;
- content type;
- response size;
- content hash;
- storage object key;
- retry count;
- error category;
- safe error message;
- elapsed time.

## 9. Storage Model

The intended conceptual raw storage organization is:

```text
raw/
└── <source-domain>/
    └── <resource-id>/
        └── <acquisition-id>/
            ├── payload
            └── metadata.json
```

The actual object-key implementation must follow the repository's final storage abstraction and should not conflict with existing code.

## 10. Fetcher Requirements

The fetcher must be:

- modular;
- testable;
- retry-aware;
- timeout-aware;
- observable;
- resumable where practical;
- deterministic where practical;
- respectful of source/server policies.

Controls must include:

- allowed domains/sources;
- request timeout;
- concurrency limits;
- retry limits;
- backoff;
- maximum response size;
- content-type handling;
- URL normalization;
- crawl/job boundaries;
- logging.

The project must not become an uncontrolled crawler.

The system must never bypass authentication, access controls, robots restrictions, paywalls, CAPTCHAs, or other technical protections.

## 11. Error Handling

At minimum distinguish:

- DNS/network failure;
- connection timeout;
- TLS failure;
- HTTP error;
- redirect failure;
- content-type rejection;
- response-size limit;
- parsing/discovery failure;
- storage failure;
- database failure;
- unknown failure.

A failed fetch must never be represented as a successful acquisition.

## 12. Security

Never hardcode:

- passwords;
- API keys;
- access tokens;
- cookies;
- authorization headers.

Use environment variables, `.env`, Docker Compose configuration, and later an appropriate secret-management system where justified.

Secrets must not be committed to Git.

Logs must not expose credentials or complete raw document bodies.

## 13. SRS / Requirements Status

This documentation preserves the requirements established for the project in the current development handover and Copilot instructions.

An authoritative standalone SRS document was not supplied with this documentation package. Therefore this package does **not** invent an official SRS.

The currently established requirements are:

- build a controlled data acquisition and preservation layer;
- preserve raw payloads;
- catalog resources and acquisition events;
- maintain provenance;
- use MinIO for raw object storage;
- use PostgreSQL for catalog/provenance;
- support hashing and deduplication concepts without destroying duplicate acquisitions;
- use controlled fetching;
- implement retries, timeouts, limits, logging, and error classification;
- maintain clear Phase 1 / Phase 2 boundaries;
- preserve sufficient lineage for future SLM/LLM dataset reconstruction.

If an official SRS exists elsewhere in the project, it should be incorporated into this documentation after inspection rather than replaced by assumptions.

## 14. Phase Boundaries

### Phase 1

Acquisition and preservation.

### Phase 2

Preprocessing and dataset generation, including:

- parsing;
- text extraction;
- OCR;
- normalization;
- language identification;
- quality filtering;
- PII/safety filtering;
- deduplication;
- document segmentation;
- metadata enrichment;
- dataset construction;
- train/validation/test generation;
- tokenization;
- training formats.

Phase 2 must not be implemented prematurely.

## 15. Architecture Principle

Before coding:

1. inspect the repository;
2. inspect existing components;
3. reuse existing abstractions;
4. state the intended change;
5. make the smallest coherent change;
6. test it;
7. verify integration;
8. document the result.

Do not create parallel implementations of existing functionality.

## 16. References

The following are the foundational technologies explicitly used by the project:

- MinIO — S3-compatible object storage
- PostgreSQL — relational database
- Docker Compose — local service orchestration
- GitHub Copilot — development assistance

Official documentation should be consulted during implementation rather than relying on copied snippets:

- MinIO documentation: https://docs.min.io/
- PostgreSQL documentation: https://www.postgresql.org/docs/
- Docker Compose documentation: https://docs.docker.com/compose/
- GitHub Copilot documentation: https://docs.github.com/copilot

These links are technology references, not claims that the project is based on any proprietary Big Tech training implementation.

## 17. Ethical and Operational Boundary

The project is an acquisition and preservation system.

It must only acquire data that the configured source and project policy permit it to retrieve.

The system must not be designed to bypass technical or access controls.

The long-term training objective does not override source permissions, legal requirements, or privacy/security constraints.
