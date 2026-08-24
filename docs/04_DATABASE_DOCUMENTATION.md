# Data_Fetcher_Ubuntu — Database Documentation

## 1. Database

PostgreSQL is used as the structured catalog and provenance layer.

Current database:

```text
data_catalog
```

Current user:

```text
datafetcher
```

Current PostgreSQL major version:

```text
18
```

Verified server version during setup:

```text
PostgreSQL 18.4
```

## 2. Initial Schema

Historical schema file:

```text
database/init/001_initial_schema.sql
```

Observed:

```text
216 lines
5.3K
```

The schema was successfully applied.

Do not rewrite this file for future changes.

## 3. Existing Tables

### crawl_jobs

Represents crawler/fetching executions.

Conceptually records the acquisition job boundary.

### resources

Represents discovered resources.

Verified columns include:

- `id`
- `url`
- `normalized_url`
- `domain`
- `resource_type`
- `discovered_from`
- `first_seen_at`
- `last_seen_at`
- `metadata`

The table has:

- UUID primary key;
- unique URL constraint;
- indexes for discovery source, domain, and resource type;
- self-referencing discovery relationship.

### discovered_links

Represents discovered relationships/links between resources.

### fetches

Represents acquisition/fetch events.

This table is central to recording the fact that an individual acquisition occurred.

### artifacts

Represents stored/acquired artifacts and their relationship to the catalog.

## 4. Migration Policy

Future schema changes belong in:

```text
database/migrations/
```

Example:

```text
002_add_*.sql
003_add_*.sql
```

Never modify the historical initial schema simply to make current code work.

## 5. Integrity Requirements

Maintain relationships among:

```text
crawl job
    ↓
resource
    ↓
fetch
    ↓
artifact/raw object
```

Foreign keys must remain valid.

Do not introduce duplicate or parallel tables that represent the same concept without a clear architectural reason.

## 6. Required Provenance

The database should ultimately allow the system to answer:

- What resource was acquired?
- From which URL?
- During which crawl job?
- When?
- With what method?
- What was the HTTP response?
- What content type was returned?
- How large was the payload?
- What content hash was generated?
- Where was the raw object stored?
- Did acquisition succeed?
- If it failed, why?
- How long did it take?
- How many retries occurred?

## 7. Hashing

Content identity must be represented separately from URL identity.

Recommended content hash:

```text
SHA-256
```

Hashing is used for:

- integrity verification;
- content identity;
- later deduplication;
- dataset lineage.

A matching content hash must not automatically cause raw acquisition deletion.

## 8. Database Verification Commands

Useful verification commands:

```bash
docker exec -it data-fetcher-postgres \
psql -U datafetcher -d data_catalog -c "\dt"
```

Inspect a table:

```bash
docker exec -it data-fetcher-postgres \
psql -U datafetcher -d data_catalog -c "\d resources"
```

Verify version:

```bash
docker exec -it data-fetcher-postgres \
psql -U datafetcher -d data_catalog -c "SELECT version();"
```

## 9. Migration Testing

Before applying a migration:

1. inspect current schema;
2. inspect the migration;
3. check dependencies;
4. apply locally;
5. inspect resulting schema;
6. run relevant integration tests.

Avoid destructive migrations.

## 10. Database Safety

Never use destructive commands merely to reset development state when persistent project data matters.

In particular, do not casually:

```text
DROP DATABASE
DROP TABLE
TRUNCATE
```

and never delete Docker persistent volumes without explicit authorization.
