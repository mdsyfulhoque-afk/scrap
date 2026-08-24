-- ============================================================
-- Data Fetcher Ubuntu
-- Phase 2 - Quality Signals
-- P2.4 Quality Signals & Normalization
-- ============================================================

-- Add quality_signals JSONB column to canonical_documents
ALTER TABLE canonical_documents
    ADD COLUMN IF NOT EXISTS quality_signals JSONB NOT NULL DEFAULT '{}'::jsonb;

-- Add index for quality signal queries
CREATE INDEX IF NOT EXISTS idx_canonical_documents_quality_signals
    ON canonical_documents USING GIN (quality_signals);

-- ============================================================
-- COMPLETION MARKER
-- ============================================================

COMMENT ON COLUMN canonical_documents.quality_signals
IS 'P2.4 quality signals: deterministic metrics describing canonical document content';
