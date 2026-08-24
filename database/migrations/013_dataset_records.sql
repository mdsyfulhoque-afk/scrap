-- ============================================================
-- Data Fetcher Ubuntu
-- Phase 2 - Dataset Records
-- P2.6 Dataset Builder
-- ============================================================

CREATE TABLE IF NOT EXISTS dataset_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    build_id UUID NOT NULL
        REFERENCES dataset_builds(id)
        ON DELETE CASCADE,

    specification_id UUID NOT NULL
        REFERENCES dataset_specifications(id)
        ON DELETE CASCADE,

    source_record_id UUID,
    normalized_record_id UUID,
    canonical_record_id UUID,
    raw_artifact_id UUID,

    source_url TEXT,

    text TEXT,

    language TEXT,

    quality_score FLOAT,

    dedup_group_id UUID,

    selection_reason TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- INDEXES
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_dataset_records_build_id
    ON dataset_records(build_id);

CREATE INDEX IF NOT EXISTS idx_dataset_records_specification_id
    ON dataset_records(specification_id);

CREATE INDEX IF NOT EXISTS idx_dataset_records_normalized_record_id
    ON dataset_records(normalized_record_id);

CREATE INDEX IF NOT EXISTS idx_dataset_records_canonical_record_id
    ON dataset_records(canonical_record_id);

CREATE INDEX IF NOT EXISTS idx_dataset_records_raw_artifact_id
    ON dataset_records(raw_artifact_id);

CREATE INDEX IF NOT EXISTS idx_dataset_records_dedup_group_id
    ON dataset_records(dedup_group_id);

CREATE INDEX IF NOT EXISTS idx_dataset_records_quality_score
    ON dataset_records(quality_score);

CREATE INDEX IF NOT EXISTS idx_dataset_records_created_at
    ON dataset_records(created_at);

-- ============================================================
-- COMPLETION MARKER
-- ============================================================

COMMENT ON TABLE dataset_records
IS 'Phase 2 dataset records: accepted records produced by a dataset build';
