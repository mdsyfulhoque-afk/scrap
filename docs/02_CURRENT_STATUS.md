# Data_Fetcher_Ubuntu — Current Status

## Status Date

2026-08-11

## Overall Status

Phase 1 infrastructure is verified and the initial Phase 1B acquisition/storage integration milestone is now complete.

The project is ready for continued Phase 1B refinement, but the current core acquisition flow is working end to end against the local MinIO and PostgreSQL services.

## Completed

### 1. Project directory

Working directory:

```text
/run/media/farhan/New Volume/Projects/Data_Fetcher_Ubuntu
```

### 2. Docker Compose

Docker Compose is operational.

The project contains MinIO and PostgreSQL services.

`docker compose config` was successfully executed.

### 3. MinIO

Container:

```text
data-fetcher-minio
```

Status was verified as healthy.

Ports:

```text
9000
9001
```

The MinIO persistent volume exists:

```text
data_fetcher_ubuntu_minio_data
```

MinIO health endpoint returned:

```text
HTTP/1.1 200 OK
```

MinIO administrative status reported one online drive.

### 4. MinIO authentication

An initial `mc` attempt failed because the internal `mc` client did not have the correct alias credentials.

This was corrected using an explicit alias configuration:

```bash
docker exec data-fetcher-minio \
mc alias set local http://127.0.0.1:9000 <MINIO_USER> '<MINIO_PASSWORD>'
```

After this, authentication worked and:

```bash
mc admin info local
```

successfully returned MinIO server information.

### 5. MinIO raw bucket

The `raw` bucket is now verified and usable through the application configuration.

The application can create or use the bucket as needed through the MinIO storage abstraction.

### 6. PostgreSQL

Container:

```text
data-fetcher-postgres
```

Image:

```text
postgres:18
```

Actual PostgreSQL version verified:

```text
PostgreSQL 18.4
```

Database:

```text
data_catalog
```

User:

```text
datafetcher
```

### 7. PostgreSQL health

PostgreSQL was verified as healthy.

The `data_catalog` database was confirmed to exist.

### 8. PostgreSQL persistent storage

Volume exists:

```text
data_fetcher_ubuntu_postgres_data
```

### 9. Initial database schema

File:

```text
database/init/001_initial_schema.sql
```

The file was created and verified.

Observed file size:

```text
5.3K
```

Observed line count:

```text
216
```

The schema was successfully applied.

### 10. Existing tables

PostgreSQL reported five public tables:

```text
artifacts
crawl_jobs
discovered_links
fetches
resources
```

### 11. Resources table

The existing `resources` table was inspected.

It includes:

- UUID primary key;
- URL;
- normalized URL;
- domain;
- resource type;
- discovery relationship;
- first/last seen timestamps;
- JSONB metadata.

Indexes and foreign-key relationships were also verified.

### 12. GitHub Copilot instructions

The project now contains:

```text
.github/copilot-instructions.md
```

Verified:

```text
14K
676 lines
```

The file is readable and correctly located.

It should be treated as the permanent project rulebook.

Do not recreate or overwrite it.

## Not Yet Completed

### MinIO

- `raw` bucket creation/verification.

### Database

- Phase 1B database/storage assessment.
- Any additional migration only if the existing schema proves insufficient.
- Acquisition transaction/provenance implementation.

### Application

- Storage abstraction: completed and verified.
- PostgreSQL application abstraction: completed and verified.
- Controlled fetcher: completed and verified.
- Acquisition orchestration: completed and verified.
- Hashing integration: completed and verified.
- Error classification: completed and verified.
- Structured logging: present in the runner path.
- Tests: completed and passing.

### Integration

The controlled flow is now implemented and verified:

```text
source
→ fetcher
→ raw object
→ PostgreSQL catalog
```

## Critical Current State

Do not:

- recreate MinIO;
- recreate PostgreSQL;
- delete persistent volumes;
- rewrite `001_initial_schema.sql`;
- start broad crawling;
- implement Phase 2 preprocessing.

The next task is to continue refining Phase 1B behaviors if needed, while keeping the current end-to-end acquisition flow intact.
