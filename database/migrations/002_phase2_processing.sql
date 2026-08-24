-- ============================================================
-- Data Fetcher Ubuntu
-- Phase 2 - Processing Jobs
-- Minimal Migration for P2.1 Materialization
-- ============================================================
-- This migration adds the minimal schema required for P.1 Raw Materialization.
-- Additional Phase 2 tables will be added in subsequent migrations as needed.

-- ============================================================
-- PROCESSING JOBS
-- Tracks Phase 2 processing jobs for materialization and transformation
-- ============================================================

CREATE TABLE IF NOT EXISTS processing_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    name TEXT NOT NULL,
    
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN (
            'pending',
            'running',
            'completed',
            'failed',
            'cancelled'
        )),
    
    config JSONB NOT NULL DEFAULT '{}'::jsonb,
    
    -- Link to source Phase 1 artifact
    source_artifact_id UUID,
    
    -- Processing metadata
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    
    -- Error information
    error_message TEXT,
    error_category TEXT,
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- INDEXES
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_processing_jobs_status
    ON processing_jobs(status);

CREATE INDEX IF NOT EXISTS idx_processing_jobs_source_artifact
    ON processing_jobs(source_artifact_id);

CREATE INDEX IF NOT EXISTS idx_processing_jobs_created_at
    ON processing_jobs(created_at);

-- ============================================================
-- COMPLETION MARKER
-- ============================================================

COMMENT ON TABLE processing_jobs
IS 'Phase 2 processing job tracking for materialization and transformation pipeline';
