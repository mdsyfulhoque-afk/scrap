-- ============================================================
-- Data Fetcher Ubuntu
-- Phase 2 - Feasibility Reports
-- P2.7 Feasibility Analysis
-- ============================================================

CREATE TABLE IF NOT EXISTS feasibility_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    specification_id UUID NOT NULL REFERENCES dataset_specifications(id) ON DELETE CASCADE,
    specification_hash TEXT NOT NULL,
    source_snapshot TEXT NOT NULL DEFAULT 'current',
    records_considered INTEGER NOT NULL DEFAULT 0,
    eligible_count INTEGER NOT NULL DEFAULT 0,
    rejection_counts JSONB NOT NULL DEFAULT '{}'::jsonb,
    language_distribution JSONB NOT NULL DEFAULT '{}'::jsonb,
    quality_distribution JSONB NOT NULL DEFAULT '{}'::jsonb,
    dedup_impact JSONB NOT NULL DEFAULT '{}'::jsonb,
    blockers JSONB NOT NULL DEFAULT '[]'::jsonb,
    warnings JSONB NOT NULL DEFAULT '[]'::jsonb,
    feasibility TEXT NOT NULL DEFAULT 'pass',
    estimated_output_size_bytes INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_feasibility_reports_specification_id
    ON feasibility_reports(specification_id);

CREATE INDEX IF NOT EXISTS idx_feasibility_reports_feasibility
    ON feasibility_reports(feasibility);

CREATE INDEX IF NOT EXISTS idx_feasibility_reports_created_at
    ON feasibility_reports(created_at);

COMMENT ON TABLE feasibility_reports
IS 'Phase 2 feasibility reports: dataset build feasibility analysis';
