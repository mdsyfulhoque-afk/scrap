-- ============================================================
-- Data Fetcher Ubuntu
-- Phase 2 - Dataset Builds
-- P2.6 Dataset Builder
-- ============================================================

CREATE TABLE IF NOT EXISTS dataset_builds (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    specification_id UUID NOT NULL
        REFERENCES dataset_specifications(id)
        ON DELETE CASCADE,

    specification_hash TEXT NOT NULL,

    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN (
            'draft'::text,
            'planned'::text,
            'building'::text,
            'validating'::text,
            'review_required'::text,
            'accepted'::text,
            'released'::text,
            'superseded'::text,
            'failed'::text
        )),

    records_considered INTEGER NOT NULL DEFAULT 0,
    records_accepted INTEGER NOT NULL DEFAULT 0,
    records_rejected INTEGER NOT NULL DEFAULT 0,

    error_message TEXT,

    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- INDEXES
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_dataset_builds_specification_id
    ON dataset_builds(specification_id);

CREATE INDEX IF NOT EXISTS idx_dataset_builds_status
    ON dataset_builds(status);

CREATE INDEX IF NOT EXISTS idx_dataset_builds_specification_hash
    ON dataset_builds(specification_hash);

CREATE INDEX IF NOT EXISTS idx_dataset_builds_started_at
    ON dataset_builds(started_at);

-- ============================================================
-- COMPLETION MARKER
-- ============================================================

COMMENT ON TABLE dataset_builds
IS 'Phase 2 dataset builds: auditable build records for governed dataset construction';
