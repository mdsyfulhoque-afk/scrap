-- ============================================================
-- Data Fetcher Ubuntu
-- Phase 2 - Extraction Versioning Fix
-- P2.3 Audit Remediation
-- ============================================================
-- This migration fixes the canonical_documents unique constraint
-- to support multiple extraction versions per artifact.

-- Drop the old unique constraint (one canonical document per artifact)
ALTER TABLE canonical_documents
    DROP CONSTRAINT IF EXISTS unique_canonical_document_per_artifact;

-- Add new unique constraint supporting versioning
ALTER TABLE canonical_documents
    ADD CONSTRAINT unique_canonical_document_per_artifact_version
    UNIQUE (artifact_id, extraction_version);

-- ============================================================
-- COMPLETION MARKER
-- ============================================================

COMMENT ON TABLE canonical_documents
IS 'Phase 2 canonical extraction results: deterministic, versioned, format-preserving representations of artifacts';
