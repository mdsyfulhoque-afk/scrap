-- ============================================================
-- Data Fetcher Ubuntu
-- Phase 2 - Duplicate Memberships
-- P2.5 Deduplication and Duplicate Decision Layer
-- ============================================================

CREATE TABLE IF NOT EXISTS duplicate_memberships (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Link to parent group
    group_id UUID NOT NULL
        REFERENCES duplicate_groups(id)
        ON DELETE CASCADE,

    -- Document references (exactly one must be non-null)
    normalized_document_id UUID
        REFERENCES normalized_documents(id)
        ON DELETE CASCADE,
    canonical_document_id UUID
        REFERENCES canonical_documents(id)
        ON DELETE CASCADE,
    artifact_id UUID
        REFERENCES artifacts(id)
        ON DELETE CASCADE,

    -- Comparison metadata
    comparison_method TEXT NOT NULL,
    similarity_score FLOAT,
    is_representative BOOLEAN NOT NULL DEFAULT false,
    selection_basis TEXT,

    -- Warnings and errors
    warnings JSONB NOT NULL DEFAULT '[]'::jsonb,
    errors JSONB NOT NULL DEFAULT '[]'::jsonb,

    -- Provenance
    provenance JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Exactly one document reference must be provided
    CONSTRAINT one_document_reference CHECK (
        (normalized_document_id IS NOT NULL)::int +
        (canonical_document_id IS NOT NULL)::int +
        (artifact_id IS NOT NULL)::int
        = 1
    ),

    -- Prevent duplicate memberships in the same group for the same document
    CONSTRAINT unique_membership_per_group_document UNIQUE (
        group_id,
        normalized_document_id,
        canonical_document_id,
        artifact_id
    )
);

-- ============================================================
-- INDEXES
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_duplicate_memberships_group_id
    ON duplicate_memberships(group_id);

CREATE INDEX IF NOT EXISTS idx_duplicate_memberships_normalized_document_id
    ON duplicate_memberships(normalized_document_id);

CREATE INDEX IF NOT EXISTS idx_duplicate_memberships_canonical_document_id
    ON duplicate_memberships(canonical_document_id);

CREATE INDEX IF NOT EXISTS idx_duplicate_memberships_artifact_id
    ON duplicate_memberships(artifact_id);

CREATE INDEX IF NOT EXISTS idx_duplicate_memberships_is_representative
    ON duplicate_memberships(is_representative);

CREATE INDEX IF NOT EXISTS idx_duplicate_memberships_created_at
    ON duplicate_memberships(created_at);

-- ============================================================
-- COMPLETION MARKER
-- ============================================================

COMMENT ON TABLE duplicate_memberships
IS 'Phase 2 duplicate memberships: links documents to duplicate groups with comparison metadata';
