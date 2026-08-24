-- ============================================================
-- Data Fetcher Ubuntu
-- Phase 2 - Source Rights Governance
-- Adds rights metadata to artifacts
-- ============================================================

ALTER TABLE artifacts
    ADD COLUMN IF NOT EXISTS license TEXT,
    ADD COLUMN IF NOT EXISTS commercial_use_permitted BOOLEAN,
    ADD COLUMN IF NOT EXISTS redistribution_permitted BOOLEAN,
    ADD COLUMN IF NOT EXISTS attribution_required BOOLEAN,
    ADD COLUMN IF NOT EXISTS rights_basis TEXT,
    ADD COLUMN IF NOT EXISTS review_status TEXT NOT NULL DEFAULT 'requires_review',
    ADD COLUMN IF NOT EXISTS reviewed_by TEXT,
    ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS rights_notes TEXT;

-- Index for rights review queries
CREATE INDEX IF NOT EXISTS idx_artifacts_review_status
    ON artifacts(review_status);

-- Completion marker
COMMENT ON TABLE artifacts
IS 'Phase 1 artifacts with rights governance metadata';
