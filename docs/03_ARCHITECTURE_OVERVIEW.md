# Data_Fetcher_Ubuntu — Architecture Overview

## 1. High-Level Architecture

```text
                    ┌─────────────────────┐
                    │ Permitted Sources   │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │ Discovery / Jobs    │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │ Controlled Fetcher  │
                    └──────┬────────┬─────┘
                           │        │
                     payload        metadata
                           │        │
                           ▼        ▼
                 ┌────────────┐  ┌──────────────┐
                 │   MinIO    │  │ PostgreSQL   │
                 │ Raw Store  │  │ Catalog      │
                 └────────────┘  └──────────────┘
                           │        │
                           └───┬────┘
                               ▼
                       Provenance / Lineage
                               │
                               ▼
                    Phase 2 Preprocessing
                               │
                               ▼
                    Dataset Generation
                               │
                               ▼
                         SLM / LLM
```

## 2. Infrastructure Layer

### Docker Compose

Provides reproducible local infrastructure.

Services currently include:

- MinIO;
- PostgreSQL.

Persistent volumes are used for both.

### MinIO

Responsible for raw object preservation.

### PostgreSQL

Responsible for structured metadata, relationships, acquisition events, and provenance.

## 3. Logical Data Flow

### Discovery

A crawl/acquisition job identifies a resource.

### Resource Cataloging

The resource receives a stable resource identity.

### Fetch

The fetcher retrieves the permitted payload under configured controls.

### Hash

The payload receives a content hash, preferably SHA-256.

### Raw Preservation

The exact acquired payload is stored in MinIO.

### Catalog

PostgreSQL records the acquisition event and links it to the resource/job/artifact.

### Provenance

The system preserves enough information to reconstruct the acquisition lineage.

## 4. Identity Separation

```text
Resource
   │
   ├── URL identity
   │
   ├── Content identity
   │
   └── Acquisition events
             │
             ├── time
             ├── method
             ├── status
             ├── hash
             └── storage location
```

Never assume:

```text
URL == Content
```

and never assume:

```text
same URL == same content forever
```

## 5. Storage vs Catalog

MinIO stores payloads.

PostgreSQL describes those payloads and their provenance.

This separation allows future dataset-generation systems to use PostgreSQL for selection/lineage while retrieving exact source payloads from MinIO.

## 6. Phase 1 vs Phase 2

### Phase 1

```text
Acquire
Preserve
Catalog
Provenance
```

### Phase 2

```text
Extract
Normalize
Filter
Deduplicate
Segment
Enrich
Generate datasets
Tokenize
```

The architecture must keep these concerns separate.

## 7. Failure Model

A successful acquisition should result in both:

- a preserved raw object;
- a corresponding catalog/provenance record.

A failed acquisition must not appear as successful.

Failures should be classified and observable.

Potential failure classes include:

```text
network
timeout
TLS
HTTP
redirect
content-type
size-limit
parsing
storage
database
unknown
```

## 8. Safety Boundaries

The fetcher must use:

- domain/source allowlists;
- timeouts;
- concurrency limits;
- retry limits;
- backoff;
- response-size limits;
- content-type controls;
- crawl boundaries.

The system must not bypass access controls or other technical protections.
