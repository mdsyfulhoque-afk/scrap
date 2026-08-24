-- ============================================================
-- Data Fetcher Ubuntu
-- Phase 2 - Validation Reports
-- P2.8 Validation
-- ============================================================

CREATE TABLE IF NOT EXISTS validation_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    build_id UUID NOT NULL
        REFERENCES dataset_builds(id)
        ON DELETE CASCADE,

    status TEXT NOT NULL DEFAULT 'pass'
        CHECK (status IN (
            'pass'::text,
            'warn'::text,
            'fail'::text
        )),

    overall_status TEXT NOT NULL DEFAULT 'unknown',

    checks JSONB NOT NULL DEFAULT '[]'::jsonb,

    error_count INTEGER NOT NULL DEFAULT 0,
    warning_count INTEGER NOT NULL DEFAULT 0,
    info_count INTEGER NOT NULL DEFAULT 0,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- INDEXES
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_validation_reports_build_id
    ON validation_reports(build_id);

CREATE INDEX IF NOT EXISTS idx_validation_reports_status
    ON validation_reports(status);

CREATE INDEX IF NOT EXISTS idx_validation_reports_created_at
    ON validation_reports(created_at);

-- ============================================================
-- COMPLETION MARKER
-- ============================================================

COMMENT ON TABLE validation_reports
IS 'Phase 2 validation reports: pre-export dataset validation results';
