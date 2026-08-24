-- ============================================================
-- Data Fetcher Ubuntu
-- Phase 2 - Dataset Specifications
-- P2.6 Dataset Specification
-- ============================================================

CREATE TABLE IF NOT EXISTS dataset_specifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    specification_hash TEXT NOT NULL,
    canonical_specification JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Unique constraint on (name, version)
    CONSTRAINT unique_specification_name_version UNIQUE (name, version)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_dataset_specifications_name
    ON dataset_specifications(name);

CREATE INDEX IF NOT EXISTS idx_dataset_specifications_status
    ON dataset_specifications(status);

CREATE INDEX IF NOT EXISTS idx_dataset_specifications_hash
    ON dataset_specifications(specification_hash);

-- Completion marker
COMMENT ON TABLE dataset_specifications
IS 'Phase 2 dataset specifications: versioned dataset requirements';
