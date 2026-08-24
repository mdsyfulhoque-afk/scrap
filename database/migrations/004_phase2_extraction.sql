-- ============================================================
-- Data Fetcher Ubuntu
-- Phase 2 - Canonical Extraction
-- P2.3 Canonical Representation & Extraction
-- ============================================================

CREATE TABLE IF NOT EXISTS canonical_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Link to source artifact (one canonical document per artifact)
    artifact_id UUID NOT NULL
        REFERENCES artifacts(id)
        ON DELETE CASCADE,
    
    -- Link to processing job
    processing_job_id UUID
        REFERENCES processing_jobs(id)
        ON DELETE SET NULL,

    -- Source information
    source_url TEXT NOT NULL,
    source_mime_type TEXT,
    detected_format TEXT,

    -- Extraction status
    extraction_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (extraction_status IN (
            'pending',
            'running',
            'completed',
            'failed',
            'unsupported',
            'partial'
        )),

    -- Canonical outputs
    canonical_text TEXT,
    structured_data JSONB,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    structure JSONB,

    -- Extraction metadata
    extraction_method TEXT NOT NULL,
    extraction_version TEXT NOT NULL DEFAULT '1.0.0',
    warnings JSONB NOT NULL DEFAULT '[]'::jsonb,
    errors JSONB NOT NULL DEFAULT '[]'::jsonb,

    -- Checksums for reproducibility
    original_checksum TEXT NOT NULL,
    canonical_checksum TEXT,

    -- Provenance
    provenance JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Unique constraint: one canonical document per artifact
    CONSTRAINT unique_canonical_document_per_artifact UNIQUE (artifact_id)
);

-- ============================================================
-- INDEXES
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_canonical_documents_artifact_id
    ON canonical_documents(artifact_id);

CREATE INDEX IF NOT EXISTS idx_canonical_documents_detected_format
    ON canonical_documents(detected_format);

CREATE INDEX IF NOT EXISTS idx_canonical_documents_extraction_status
    ON canonical_documents(extraction_status);

CREATE INDEX IF NOT EXISTS idx_canonical_documents_extraction_method
    ON canonical_documents(extraction_method);

CREATE INDEX IF NOT EXISTS idx_canonical_documents_created_at
    ON canonical_documents(created_at);

-- ============================================================
-- COMPLETION MARKER
-- ============================================================

COMMENT ON TABLE canonical_documents
IS 'Phase 2 canonical extraction results: deterministic, versioned, format-preserving representations of artifacts';
