-- ============================================================
-- Data Fetcher Ubuntu
-- Phase 2 - Duplicate Groups
-- P2.5 Deduplication and Duplicate Decision Layer
-- ============================================================

CREATE TABLE IF NOT EXISTS duplicate_groups (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Duplicate method and algorithm tracking
    duplicate_method TEXT NOT NULL CHECK (duplicate_method = ANY (ARRAY[
        'raw_exact'::text,
        'normalized_exact'::text,
        'near_duplicate'::text
    ])),
    algorithm_version TEXT NOT NULL DEFAULT 'trigram-jaccard-1.0.0',
    algorithm_config JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- Representative selection (nullable: only one of these should be set)
    representative_normalized_document_id UUID
        REFERENCES normalized_documents(id)
        ON DELETE SET NULL,
    representative_canonical_document_id UUID
        REFERENCES canonical_documents(id)
        ON DELETE SET NULL,

    -- Group statistics
    group_size INT NOT NULL DEFAULT 0,
    similarity_stats JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- Warnings and errors
    warnings JSONB NOT NULL DEFAULT '[]'::jsonb,
    errors JSONB NOT NULL DEFAULT '[]'::jsonb,

    -- Provenance
    provenance JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- INDEXES
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_duplicate_groups_duplicate_method
    ON duplicate_groups(duplicate_method);

CREATE INDEX IF NOT EXISTS idx_duplicate_groups_algorithm_version
    ON duplicate_groups(algorithm_version);

CREATE INDEX IF NOT EXISTS idx_duplicate_groups_representative_normalized_document_id
    ON duplicate_groups(representative_normalized_document_id);

CREATE INDEX IF NOT EXISTS idx_duplicate_groups_representative_canonical_document_id
    ON duplicate_groups(representative_canonical_document_id);

CREATE INDEX IF NOT EXISTS idx_duplicate_groups_created_at
    ON duplicate_groups(created_at);

-- ============================================================
-- COMPLETION MARKER
-- ============================================================

COMMENT ON TABLE duplicate_groups
IS 'Phase 2 duplicate groups: auditable duplicate relationship layer for exact and near-duplicate detection';
