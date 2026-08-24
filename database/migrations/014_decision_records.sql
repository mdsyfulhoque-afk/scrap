-- ============================================================
-- Data Fetcher Ubuntu
-- Phase 2 - Decision Records
-- P2.7 Explainable Decisions
-- ============================================================

CREATE TABLE IF NOT EXISTS decision_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    build_id UUID NOT NULL
        REFERENCES dataset_builds(id)
        ON DELETE CASCADE,

    record_id UUID,

    decision TEXT NOT NULL
        CHECK (decision IN (
            'accepted'::text,
            'rejected'::text
        )),

    reason_codes JSONB NOT NULL DEFAULT '[]'::jsonb,

    actual_values JSONB NOT NULL DEFAULT '{}'::jsonb,

    thresholds JSONB NOT NULL DEFAULT '{}'::jsonb,

    representative_record_id UUID,

    source_url TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- INDEXES
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_decision_records_build_id
    ON decision_records(build_id);

CREATE INDEX IF NOT EXISTS idx_decision_records_record_id
    ON decision_records(record_id);

CREATE INDEX IF NOT EXISTS idx_decision_records_decision
    ON decision_records(decision);

CREATE INDEX IF NOT EXISTS idx_decision_records_reason_codes
    ON decision_records USING GIN (reason_codes);

CREATE INDEX IF NOT EXISTS idx_decision_records_created_at
    ON decision_records(created_at);

-- ============================================================
-- COMPLETION MARKER
-- ============================================================

COMMENT ON TABLE decision_records
IS 'Phase 2 decision records: machine-readable accept/reject decisions with reason codes';
