-- ============================================================
-- Data Fetcher Ubuntu
-- Phase 1 - Raw Data Acquisition Catalog
-- Initial Database Schema
-- ============================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ============================================================
-- CRAWL JOBS
-- Represents one crawler/fetching execution.
-- ============================================================

CREATE TABLE IF NOT EXISTS crawl_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    name TEXT NOT NULL,

    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN (
            'pending',
            'running',
            'completed',
            'failed',
            'cancelled'
        )),

    config JSONB NOT NULL DEFAULT '{}'::jsonb,

    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- ============================================================
-- RESOURCES
-- Represents a discovered URL/resource.
-- ============================================================

CREATE TABLE IF NOT EXISTS resources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    url TEXT NOT NULL UNIQUE,

    normalized_url TEXT,

    domain TEXT,

    resource_type TEXT,

    discovered_from UUID
        REFERENCES resources(id)
        ON DELETE SET NULL,

    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);


-- ============================================================
-- FETCHES
-- Represents an attempt to retrieve a resource.
-- ============================================================

CREATE TABLE IF NOT EXISTS fetches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    resource_id UUID NOT NULL
        REFERENCES resources(id)
        ON DELETE CASCADE,

    crawl_job_id UUID
        REFERENCES crawl_jobs(id)
        ON DELETE SET NULL,

    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN (
            'pending',
            'running',
            'success',
            'failed'
        )),

    http_status INTEGER,

    content_type TEXT,

    content_length BIGINT,

    headers JSONB NOT NULL DEFAULT '{}'::jsonb,

    error_message TEXT,

    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- ============================================================
-- ARTIFACTS
-- Represents the actual fetched data stored in object storage.
-- MinIO is the Phase 1 object-storage backend.
-- ============================================================

CREATE TABLE IF NOT EXISTS artifacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    fetch_id UUID NOT NULL
        REFERENCES fetches(id)
        ON DELETE CASCADE,

    storage_backend TEXT NOT NULL DEFAULT 'minio',

    bucket_name TEXT NOT NULL,

    object_key TEXT NOT NULL,

    content_type TEXT,

    size_bytes BIGINT,

    checksum_sha256 TEXT,

    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (
        storage_backend,
        bucket_name,
        object_key
    )
);


-- ============================================================
-- DISCOVERED LINKS
-- Represents links found inside fetched resources.
-- ============================================================

CREATE TABLE IF NOT EXISTS discovered_links (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    source_resource_id UUID NOT NULL
        REFERENCES resources(id)
        ON DELETE CASCADE,

    target_url TEXT NOT NULL,

    link_text TEXT,

    discovered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

    UNIQUE (
        source_resource_id,
        target_url
    )
);


-- ============================================================
-- INDEXES
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_crawl_jobs_status
    ON crawl_jobs(status);

CREATE INDEX IF NOT EXISTS idx_crawl_jobs_created_at
    ON crawl_jobs(created_at);

CREATE INDEX IF NOT EXISTS idx_resources_domain
    ON resources(domain);

CREATE INDEX IF NOT EXISTS idx_resources_resource_type
    ON resources(resource_type);

CREATE INDEX IF NOT EXISTS idx_resources_discovered_from
    ON resources(discovered_from);

CREATE INDEX IF NOT EXISTS idx_fetches_resource_id
    ON fetches(resource_id);

CREATE INDEX IF NOT EXISTS idx_fetches_crawl_job_id
    ON fetches(crawl_job_id);

CREATE INDEX IF NOT EXISTS idx_fetches_status
    ON fetches(status);

CREATE INDEX IF NOT EXISTS idx_fetches_created_at
    ON fetches(created_at);

CREATE INDEX IF NOT EXISTS idx_artifacts_fetch_id
    ON artifacts(fetch_id);

CREATE INDEX IF NOT EXISTS idx_artifacts_checksum
    ON artifacts(checksum_sha256);

CREATE INDEX IF NOT EXISTS idx_discovered_links_source
    ON discovered_links(source_resource_id);


-- ============================================================
-- COMPLETION MARKER
-- ============================================================

COMMENT ON DATABASE data_catalog
IS 'Data Fetcher Ubuntu - Phase 1 raw acquisition and artifact catalog';
