-- ============================================================
-- Data Fetcher Ubuntu
-- Phase 2 - Artifact Characterization
-- P2.2 Data Inventory, Data Profiling & Format Discovery
-- ============================================================

CREATE TABLE IF NOT EXISTS artifact_characterization (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Link to source artifact
    artifact_id UUID NOT NULL
        REFERENCES artifacts(id)
        ON DELETE CASCADE,

    -- Characterization versioning
    characterization_version TEXT NOT NULL DEFAULT '1.0.0',
    characterization_config JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- Detected format properties
    detected_format TEXT,
    format_confidence TEXT
        CHECK (format_confidence IN ('high', 'medium', 'low', 'unknown')),
    format_evidence JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- MIME / extension
    mime_type TEXT,
    file_extension TEXT,
    encoding TEXT,

    -- Structural / document type
    structural_type TEXT,
    document_type_candidates JSONB NOT NULL DEFAULT '[]'::jsonb,

    -- Schema information
    schema_summary JSONB,

    -- Content statistics
    content_statistics JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- Metadata availability
    metadata_availability JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- Extraction suitability
    extraction_suitability TEXT
        CHECK (extraction_suitability IN ('suitable', 'partial', 'unsuitable', 'unknown')),

    -- Warnings and errors
    warnings JSONB NOT NULL DEFAULT '[]'::jsonb,
    errors JSONB NOT NULL DEFAULT '[]'::jsonb,

    -- Deterministic flag
    is_deterministic BOOLEAN NOT NULL DEFAULT true,

    -- Timestamps
    characterized_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Unique constraint: one characterization per artifact per version
    CONSTRAINT unique_artifact_characterization UNIQUE (artifact_id, characterization_version)
);

-- ============================================================
-- INDEXES
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_artifact_characterization_artifact_id
    ON artifact_characterization(artifact_id);

CREATE INDEX IF NOT EXISTS idx_artifact_characterization_detected_format
    ON artifact_characterization(detected_format);

CREATE INDEX IF NOT EXISTS idx_artifact_characterization_structural_type
    ON artifact_characterization(structural_type);

CREATE INDEX IF NOT EXISTS idx_artifact_characterization_characterized_at
    ON artifact_characterization(characterized_at);

CREATE INDEX IF NOT EXISTS idx_artifact_characterization_extraction_suitability
    ON artifact_characterization(extraction_suitability);

-- ============================================================
-- COMPLETION MARKER
-- ============================================================

COMMENT ON TABLE artifact_characterization
IS 'Phase 2 artifact characterization: format, structure, content discovery, and statistics';
