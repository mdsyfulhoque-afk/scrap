-- ============================================================
-- Data Fetcher Ubuntu
-- Phase 2 - Schema Migrations Ledger
-- Tracks applied migrations for safe upgrades
-- ============================================================

CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    checksum TEXT NOT NULL
);

-- Index for migration history queries
CREATE INDEX IF NOT EXISTS idx_schema_migrations_applied_at
    ON schema_migrations(applied_at);

-- Completion marker
COMMENT ON TABLE schema_migrations
IS 'Tracks applied database migrations for safe upgrades';
