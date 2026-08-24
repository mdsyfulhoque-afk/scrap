-- ============================================================
-- Data Fetcher Ubuntu
-- Phase 2 - Normalization Layer
-- P2.4 Quality Signals & Normalization
-- ============================================================

CREATE TABLE IF NOT EXISTS normalized_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Link to source canonical document
    canonical_document_id UUID NOT NULL
        REFERENCES canonical_documents(id)
        ON DELETE CASCADE,

    -- Link to source artifact
    artifact_id UUID NOT NULL
        REFERENCES artifacts(id)
        ON DELETE CASCADE,

    -- Link to processing job
    processing_job_id UUID
        REFERENCES processing_jobs(id)
        ON DELETE SET NULL,

    -- Source information
    source_url TEXT NOT NULL,
    detected_format TEXT,

    -- Normalization versioning
    normalization_version TEXT NOT NULL DEFAULT '1.0.0',
    normalization_operations JSONB NOT NULL DEFAULT '[]'::jsonb,

    -- Canonical outputs
    normalized_text TEXT,
    original_checksum TEXT NOT NULL,
    normalized_checksum TEXT,
    content_changed BOOLEAN NOT NULL DEFAULT false,

    -- Quality signals
    quality_signals JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- Warnings and errors
    warnings JSONB NOT NULL DEFAULT '[]'::jsonb,
    errors JSONB NOT NULL DEFAULT '[]'::jsonb,

    -- Provenance
    provenance JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Unique constraint: one normalized document per canonical document per version
    CONSTRAINT unique_normalized_document_per_canonical_version UNIQUE (canonical_document_id, normalization_version)
);

-- ============================================================
-- INDEXES
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_normalized_documents_canonical_document_id
    ON normalized_documents(canonical_document_id);

CREATE INDEX IF NOT EXISTS idx_normalized_documents_artifact_id
    ON normalized_documents(artifact_id);

CREATE INDEX IF NOT EXISTS idx_normalized_documents_detected_format
    ON normalized_documents(detected_format);

CREATE INDEX IF NOT EXISTS idx_normalized_documents_normalization_version
    ON normalized_documents(normalization_version);

CREATE INDEX IF NOT EXISTS idx_normalized_documents_created_at
    ON normalized_documents(created_at);

-- ============================================================
-- COMPLETION MARKER
-- ============================================================

COMMENT ON TABLE normalized_documents
IS 'Phase 2 normalized documents: deterministic, versioned, non-destructive normalization of canonical documents';
