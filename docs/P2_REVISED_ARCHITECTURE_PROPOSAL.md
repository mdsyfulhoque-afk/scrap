# Phase 2 Revised Architecture Proposal

**Date:** 2026-08-17  
**Baseline:** P2.1 VERIFIED (commit cd46ea1)  
**Status:** PROPOSAL FOR REVIEW

---

## Executive Summary

The current P2.2 design focuses narrowly on extraction (raw artifact → canonical text). However, the actual Phase 2 objective is to build a complete **dataset construction application** that transforms Phase 1 data into model-ready datasets through a human-testable workflow.

**Critical Gap:** The current design stops at extraction, but the acceptance criterion requires a complete end-to-end workflow:
- Data inventory
- Format/type discovery  
- Canonical representation
- Quality analysis
- Normalization
- Deduplication
- Filtering/selection
- Dataset construction
- Dataset validation
- Export

**Proposal:** Revise Phase 2 architecture to focus on the complete dataset construction workflow rather than just extraction components.

---

## Current State Analysis

### P2.1 Baseline (VERIFIED)
- ✅ Raw artifact materialization from PostgreSQL/MinIO
- ✅ Checksum verification
- ✅ Processing job lifecycle
- ✅ Provenance preservation
- ✅ Live infrastructure verification

### Current P2.2 Design (INSUFFICIENT)
**What it covers:**
- ✅ Multi-format extraction (HTML, JSON, XML, CSV, Markdown, plain text)
- ✅ Canonical text representation
- ✅ Error classification
- ✅ Provenance preservation
- ✅ Reproducibility mechanisms

**What it misses:**
- ❌ Data inventory and type discovery
- ❌ Document type classification (article, documentation, API response, etc.)
- ❌ Quality signal computation
- ❌ Normalization beyond extraction
- ❌ Deduplication architecture
- ❌ Dataset specification language
- ❌ Dataset builder
- ❌ Dataset validation
- ❌ Human-testable CLI/UI
- ❌ End-to-end demo workflow

---

## Revised Phase 2 Objective

**PRIMARY ACCEPTANCE CRITERION:**
> I provide a database containing collected artifacts. I define dataset requirements. The software inventories the source, identifies data/document types, detects formats, extracts data, creates canonical records, calculates quality signals, removes/reports duplicates, applies dataset requirements, constructs the dataset, validates the dataset, exports it, and shows me what happened.

**User Workflow:**
```
DATABASE (existing Phase 1 artifacts)
    ↓
"UNDERSTAND WHAT IS HERE" (inventory + discovery)
    ↓
"CHOOSE WHAT I WANT" (dataset specification)
    ↓
"BUILD DATASET" (pipeline execution)
    ↓
"VERIFY DATASET" (validation)
    ↓
"EXPORT DATASET" (export)
```

---

## Revised Architecture: Complete Dataset Construction Pipeline

### 1. Data Inventory & Discovery (NEW P2.2)

**Objective:** Understand what data exists in the source database

**Input:** PostgreSQL artifacts table (71+ artifacts in current database)

**Output:** Data inventory report with format/type statistics

**Capabilities:**
- Scan all artifacts in database
- Detect MIME types, file extensions, encodings
- Identify content types (HTML, JSON, XML, CSV, etc.)
- Estimate document types (article, documentation, API, etc.)
- Compute basic statistics (size distribution, format distribution)
- Identify potential issues (unsupported formats, encoding problems)

**Data Model:**
```python
@dataclass
class DataInventory:
    total_artifacts: int
    format_distribution: dict[str, int]  # {"html": 50, "json": 15, ...}
    size_distribution: dict[str, int]   # {"<1KB": 10, "1-10KB": 40, ...}
    domain_distribution: dict[str, int]
    encoding_distribution: dict[str, int]
    unsupported_formats: list[str]
    potential_issues: list[str]
    inventory_timestamp: str
```

**CLI Command:**
```bash
data-fetcher phase2 inventory
```

### 2. Format & Type Discovery (NEW P2.2)

**Objective:** Detailed analysis of each artifact's characteristics

**Input:** Individual artifact from database

**Output:** Artifact characterization record

**Capabilities:**
- MIME type detection (from content-type + content analysis)
- File extension inference (from URL)
- Encoding detection (chardet)
- Document type classification (heuristic-based)
- Structural type detection (nested, flat, tabular, etc.)
- Schema inference (for structured data)
- Metadata availability assessment

**Data Model:**
```python
@dataclass
class ArtifactCharacterization:
    artifact_id: str
    source_url: str
    mime_type: str
    file_extension: str
    encoding: str
    document_type: str  # "html_article", "json_api", "csv_data", etc.
    structural_type: str  # "nested", "flat", "tabular", "unstructured"
    has_metadata: bool
    schema_inference: dict | None
    confidence_score: float
    characterization_method: str
    timestamp: str
```

### 3. Canonical Representation (REVISED P2.3)

**Objective:** Convert diverse formats into stable internal representation

**Input:** Characterized artifact + raw bytes

**Output:** Canonical document record

**Capabilities:**
- Format-aware extraction (HTML, JSON, XML, CSV, Markdown, plain text)
- Structural preservation (don't flatten structured data)
- Metadata extraction (title, author, dates, etc.)
- Canonical text generation (UTF-8 NFC)
- Structured data preservation (for JSON/XML/CSV)
- Error classification and handling

**Data Model:**
```python
@dataclass
class CanonicalDocument:
    document_id: str
    source_artifact_id: str
    source_url: str
    source_domain: str
    document_type: str
    format: str
    language: str | None
    title: str | None
    text: str
    structured_data: dict | None
    sections: list[dict] | None
    metadata: dict
    timestamps: dict
    checksum: str
    extraction_version: str
    extraction_method: str
    extraction_confidence: float
    quality_signals: dict  # Basic signals from extraction
    provenance: dict
    created_at: str
```

**Key Change:** Preserve structured data rather than converting everything to plain text.

### 4. Quality Signal Computation (NEW P2.4)

**Objective:** Compute measurable quality metrics for filtering

**Input:** Canonical document

**Output:** Quality signal record

**Capabilities:**
- Character count, word count, token estimate
- Language detection (fastText or heuristic)
- Alphabetic ratio, whitespace ratio, repetition ratio
- URL density, line density
- Malformed content detection
- Empty content detection
- Boilerplate ratio (for HTML)
- Metadata completeness score
- Extraction confidence integration

**Data Model:**
```python
@dataclass
class QualitySignals:
    document_id: str
    character_count: int
    word_count: int
    estimated_tokens: int
    language: str | None
    language_confidence: float | None
    alphabetic_ratio: float
    whitespace_ratio: float
    repetition_ratio: float
    url_density: float
    line_density: float
    is_malformed: bool
    is_empty: bool
    boilerplate_ratio: float | None
    metadata_completeness: float
    extraction_confidence: float
    overall_quality_score: float
    signal_version: str
    computed_at: str
```

**Design Principle:** Deterministic, no ML required initially.

### 5. Normalization (REVISED P2.5)

**Objective:** Normalize text for consistent processing

**Input:** Canonical document + quality signals

**Output:** Normalized document

**Capabilities:**
- Unicode normalization (NFC)
- Whitespace normalization
- Case normalization (optional, configurable)
- Special character handling
- Text cleaning (beyond boilerplate removal)

**Data Model:**
```python
@dataclass
class NormalizedDocument:
    document_id: str
    original_document_id: str
    normalized_text: str
    normalization_rules_applied: list[str]
    normalization_version: str
    normalized_at: str
```

### 6. Deduplication (NEW P2.6)

**Objective:** Remove duplicate and near-duplicate documents

**Input:** Set of normalized documents

**Output:** Deduplication decisions

**Capabilities:**
- Exact deduplication (SHA-256 hashing)
- Near-duplicate architecture (MinHash/LSH for future)
- Duplicate grouping and reporting
- First-occurrence preservation
- Configurable deduplication strategy

**Data Model:**
```python
@dataclass
class DeduplicationResult:
    document_id: str
    duplicate_status: str  # "unique", "exact_duplicate", "near_duplicate"
    duplicate_group_id: str | None
    first_occurrence_id: str | None
    similarity_score: float | None
    deduplication_method: str
    deduplication_version: str
    decided_at: str
```

**Architecture:** Design for fuzzy deduplication but implement exact first.

### 7. Dataset Specification (NEW P2.7)

**Objective:** Define dataset requirements in structured format

**Input:** Human requirements (language, document types, quality thresholds, etc.)

**Output:** Dataset specification record

**Capabilities:**
- Language filtering
- Document type filtering
- Length constraints (min/max)
- Quality threshold filtering
- Deduplication configuration
- Output format specification
- Metadata preservation requirements

**Data Model:**
```python
@dataclass
class DatasetSpecification:
    dataset_id: str
    name: str
    description: str
    language: str | None
    document_types: list[str] | None
    min_length: int | None
    max_length: int | None
    min_quality_score: float | None
    deduplication_enabled: bool
    near_deduplication_enabled: bool
    output_format: str  # "jsonl", "json", "csv"
    preserve_metadata: bool
    preserve_provenance: bool
    created_at: str
    created_by: str
```

**CLI Interface:**
```bash
data-fetcher phase2 create-spec --name "tech-docs" --language en --document-types documentation,code --min-quality 0.7
```

### 8. Dataset Builder (NEW P2.8)

**Objective:** Construct dataset from canonical documents per specification

**Input:** Dataset specification + canonical documents + quality signals + deduplication results

**Output:** Dataset with accepted/rejected documents

**Capabilities:**
- Apply dataset specification filters
- Track acceptance/rejection decisions
- Generate dataset statistics
- Create dataset manifest
- Preserve provenance

**Data Model:**
```python
@dataclass
class DatasetRecord:
    dataset_id: str
    document_id: str
    status: str  # "accepted", "rejected", "excluded", "duplicate", "invalid", "unsupported"
    rejection_reason: str | None
    included_at: str
```

```python
@dataclass
class Dataset:
    dataset_id: str
    specification: DatasetSpecification
    documents: list[DatasetRecord]
    statistics: dict
    manifest: dict
    created_at: str
    created_by: str
```

### 9. Dataset Validation (NEW P2.9)

**Objective:** Validate dataset before export

**Input:** Constructed dataset

**Output:** Validation report

**Capabilities:**
- Schema validation
- Document count verification
- Empty record detection
- Duplicate ID detection
- Duplicate content detection
- Encoding validation
- Required field validation
- Provenance validation
- Source linkage validation
- Checksum linkage validation
- Configuration validation
- Output readability validation

**Data Model:**
```python
@dataclass
class ValidationReport:
    dataset_id: str
    validation_timestamp: str
    schema_valid: bool
    document_count: int
    accepted_count: int
    rejected_count: int
    duplicate_count: int
    invalid_count: int
    unsupported_count: int
    languages: list[str]
    document_types: list[str]
    average_length: int
    min_length: int
    max_length: int
    output_size_bytes: int
    provenance_valid: bool
    source_linkage_valid: bool
    checksum_linkage_valid: bool
    configuration_valid: bool
    output_readable: bool
    overall_status: str  # "valid", "invalid", "warnings"
    issues: list[str]
    warnings: list[str]
```

### 10. Dataset Export (NEW P2.10)

**Objective:** Export validated dataset in model-ready format

**Input:** Validated dataset

**Output:** Exported dataset files

**Capabilities:**
- JSONL export (primary)
- JSON export (alternative)
- CSV export (where appropriate)
- Manifest generation
- Statistics export
- Rejection export
- Provenance export

**Output Structure:**
```
dataset/
    manifest.json
    dataset.jsonl
    statistics.json
    rejected.jsonl
    provenance.jsonl
```

**JSONL Format:**
```json
{
  "id": "doc-123",
  "text": "canonical text here",
  "source": "http://example.com",
  "metadata": {
    "document_type": "documentation",
    "language": "en",
    "quality_score": 0.85,
    "title": "Example Title"
  }
}
```

### 11. Human-Testable CLI (NEW P2.11)

**Objective:** Provide command-line interface for entire workflow

**Commands:**
```bash
# Inventory and discovery
data-fetcher phase2 inventory
data-fetcher phase2 inspect <artifact-id>

# Extraction and processing
data-fetcher phase2 extract <artifact-id>
data-fetcher phase2 extract-batch <spec>

# Quality analysis
data-fetcher phase2 analyze <document-id>
data-fetcher phase2 analyze-batch

# Dataset construction
data-fetcher phase2 create-spec <options>
data-fetcher phase2 build-dataset <spec-id>
data-fetcher phase2 validate <dataset-id>

# Export
data-fetcher phase2 export <dataset-id>
data-fetcher phase2 export <dataset-id> --format jsonl

# Demo
data-fetcher phase2 demo
```

### 12. Demo Mode (NEW P2.12)

**Objective:** Demonstrate complete pipeline with small deterministic dataset

**Capabilities:**
- Pre-configured demo dataset
- Multiple formats
- Different webpage structures
- Structured JSON
- Plain text
- Duplicate records
- Low-quality records
- Different languages (if practical)
- Accepted/rejected records

**Demo Workflow:**
```bash
data-fetcher phase2 demo
# Runs complete pipeline:
# 1. Inventory demo data
# 2. Extract and characterize
# 3. Compute quality signals
# 4. Deduplicate
# 5. Build dataset with demo spec
# 6. Validate dataset
# 7. Export dataset
# 8. Show results
```

---

## Revised Milestone Structure

### P2.0: Research & Architecture
**Status:** VERIFIED
**Evidence:** Original research document created

### P2.1: Materialization
**Status:** VERIFIED
**Evidence:** Live infrastructure verification, commit cd46ea1

### P2.2: Data Inventory & Format Discovery
**Status:** PLANNED
**Objective:** Understand what data exists, characterize artifacts
**Deliverables:**
- Data inventory module
- Format/type discovery module
- CLI commands (inventory, inspect)
- Database schema (artifact_characterization table)
- Tests with real artifacts

### P2.3: Canonical Representation & Extraction
**Status:** PLANNED (revised from current P2.2)
**Objective:** Convert diverse formats to stable internal representation
**Deliverables:**
- Extraction module (format-aware)
- Canonical document model
- Database schema (canonical_documents table)
- Multi-format support (HTML, JSON, XML, CSV, Markdown, plain text)
- Structured data preservation
- Tests

### P2.4: Quality Signals & Normalization
**Status:** PLANNED
**Objective:** Compute quality metrics and normalize text
**Deliverables:**
- Quality signal computation module
- Normalization module
- Database schema (quality_signals table)
- Deterministic quality metrics
- Tests

### P2.5: Deduplication
**Status:** PLANNED
**Objective:** Remove duplicate and near-duplicate documents
**Deliverables:**
- Exact deduplication implementation
- Near-duplicate architecture (MinHash/LSH design)
- Database schema (deduplication_results table)
- Tests

### P2.6: Dataset Specification
**Status:** PLANNED
**Objective:** Define dataset requirements in structured format
**Deliverables:**
- Dataset specification model
- CLI interface for spec creation
- Database schema (dataset_specifications table)
- Tests

### P2.7: Dataset Builder
**Status:** PLANNED
**Objective:** Construct dataset from canonical documents per specification
**Deliverables:**
- Dataset builder module
- Dataset record model
- Database schema (datasets, dataset_records tables)
- Acceptance/rejection tracking
- Tests

### P2.8: Dataset Validation & Manifest
**Status:** PLANNED
**Objective:** Validate dataset before export
**Deliverables:**
- Validation module
- Validation report model
- Manifest generation
- Comprehensive validation checks
- Tests

### P2.9: Dataset Export
**Status:** PLANNED
**Objective:** Export validated dataset in model-ready format
**Deliverables:**
- Export module (JSONL primary)
- Output structure (manifest, dataset, statistics, rejected, provenance)
- Tests

### P2.10: Human-Testable CLI
**Status:** PLANNED
**Objective:** Provide complete CLI interface for workflow
**Deliverables:**
- CLI command implementation
- Command help and documentation
- Integration of all pipeline stages
- Tests

### P2.11: End-to-End Demonstration
**Status:** PLANNED
**Objective:** Demonstrate complete pipeline with demo dataset
**Deliverables:**
- Demo dataset creation
- Demo workflow implementation
- Demo documentation
- Live verification

### P2.12: Documentation & Reproducibility
**Status:** PLANNED
**Objective:** Complete documentation and ensure reproducibility
**Deliverables:**
- User documentation
- Developer documentation
- Reproducibility verification
- Final progress update

---

## Database Schema Revision

### New Tables Required

**1. artifact_characterization** (P2.2)
```sql
CREATE TABLE artifact_characterization (
    id UUID PRIMARY KEY,
    artifact_id UUID NOT NULL REFERENCES artifacts(id),
    mime_type TEXT,
    file_extension TEXT,
    encoding TEXT,
    document_type TEXT,
    structural_type TEXT,
    has_metadata BOOLEAN,
    schema_inference JSONB,
    confidence_score FLOAT,
    characterization_method TEXT,
    timestamp TIMESTAMPTZ DEFAULT NOW()
);
```

**2. canonical_documents** (P2.3)
```sql
CREATE TABLE canonical_documents (
    id UUID PRIMARY KEY,
    source_artifact_id UUID NOT NULL REFERENCES artifacts(id),
    source_url TEXT,
    source_domain TEXT,
    document_type TEXT,
    format TEXT,
    language TEXT,
    title TEXT,
    text TEXT,
    structured_data JSONB,
    sections JSONB,
    metadata JSONB,
    timestamps JSONB,
    checksum TEXT,
    extraction_version TEXT,
    extraction_method TEXT,
    extraction_confidence FLOAT,
    quality_signals JSONB,
    provenance JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

**3. quality_signals** (P2.4)
```sql
CREATE TABLE quality_signals (
    id UUID PRIMARY KEY,
    document_id UUID NOT NULL REFERENCES canonical_documents(id),
    character_count INT,
    word_count INT,
    estimated_tokens INT,
    language TEXT,
    language_confidence FLOAT,
    alphabetic_ratio FLOAT,
    whitespace_ratio FLOAT,
    repetition_ratio FLOAT,
    url_density FLOAT,
    line_density FLOAT,
    is_malformed BOOLEAN,
    is_empty BOOLEAN,
    boilerplate_ratio FLOAT,
    metadata_completeness FLOAT,
    extraction_confidence FLOAT,
    overall_quality_score FLOAT,
    signal_version TEXT,
    computed_at TIMESTAMPTZ DEFAULT NOW()
);
```

**4. deduplication_results** (P2.5)
```sql
CREATE TABLE deduplication_results (
    id UUID PRIMARY KEY,
    document_id UUID NOT NULL REFERENCES canonical_documents(id),
    duplicate_status TEXT,
    duplicate_group_id UUID,
    first_occurrence_id UUID REFERENCES canonical_documents(id),
    similarity_score FLOAT,
    deduplication_method TEXT,
    deduplication_version TEXT,
    decided_at TIMESTAMPTZ DEFAULT NOW()
);
```

**5. dataset_specifications** (P2.6)
```sql
CREATE TABLE dataset_specifications (
    id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    language TEXT,
    document_types TEXT[],
    min_length INT,
    max_length INT,
    min_quality_score FLOAT,
    deduplication_enabled BOOLEAN DEFAULT true,
    near_deduplication_enabled BOOLEAN DEFAULT false,
    output_format TEXT DEFAULT 'jsonl',
    preserve_metadata BOOLEAN DEFAULT true,
    preserve_provenance BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by TEXT
);
```

**6. datasets** (P2.7)
```sql
CREATE TABLE datasets (
    id UUID PRIMARY KEY,
    specification_id UUID NOT NULL REFERENCES dataset_specifications(id),
    statistics JSONB,
    manifest JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by TEXT
);
```

**7. dataset_records** (P2.7)
```sql
CREATE TABLE dataset_records (
    id UUID PRIMARY KEY,
    dataset_id UUID NOT NULL REFERENCES datasets(id),
    document_id UUID NOT NULL REFERENCES canonical_documents(id),
    status TEXT,
    rejection_reason TEXT,
    included_at TIMESTAMPTZ DEFAULT NOW()
);
```

**Update existing extraction_results table design** to align with canonical_documents approach.

---

## Key Architectural Decisions

### 1. Preserve Structured Data
**Decision:** Do not convert structured data (JSON/XML/CSV) to plain text only.
**Rationale:** Different dataset requirements may need structured vs. unstructured data.
**Implementation:** Store both canonical text and structured data separately.

### 2. Separate Discovery from Extraction
**Decision:** Data inventory/format discovery (P2.2) precedes extraction (P2.3).
**Rationale:** Users need to understand what data exists before processing.
**Implementation:** Characterization step before extraction.

### 3. Quality Signals Before Filtering
**Decision:** Compute quality signals (P2.4) before dataset filtering (P2.7).
**Rationale:** Filtering decisions should be based on measured attributes.
**Implementation:** Store quality signals for auditability.

### 4. Dataset Specification Language
**Decision:** Use structured configuration (not natural language parsing).
**Rationale:** Deterministic, reproducible, no LLM dependency.
**Implementation:** JSON/YAML configuration with CLI builder.

### 5. Exact Deduplication First
**Decision:** Implement exact deduplication (P2.5), design near-duplicate architecture.
**Rationale:** Exact deduplication is essential and computationally feasible.
**Implementation:** SHA-256 hashing with grouping, MinHash/LSH design for future.

### 6. Human-Testable CLI Priority
**Decision:** CLI interface (P2.11) is critical, not optional.
**Rationale:** User must be able to run the entire workflow manually.
**Implementation:** Comprehensive CLI with demo mode.

### 7. Demo Dataset
**Decision:** Create deterministic demo dataset (P2.12) for end-to-end testing.
**Rationale:** Demonstrate complete pipeline without external data dependencies.
**Implementation:** Pre-configured demo with multiple formats and edge cases.

### 8. Resource-Constrained Design
**Decision:** Design for local machine (16GB RAM, no GPU) first.
**Rationale:** Development machine constraints, scale later.
**Implementation:** Streaming/chunked processing, bounded memory.

---

## Implementation Order

### Immediate Next Steps

1. **Update P2_Progress.md** with revised milestone structure
2. **Revise P2.2 research document** to focus on data inventory + format discovery
3. **Create new P2.3 research document** for canonical representation (extracted from current P2.2)
4. **Create research documents** for P2.4-P2.12 as needed
5. **Begin P2.2 implementation** (data inventory + format discovery)

### Implementation Priority

**High Priority (Core Workflow):**
- P2.2: Data inventory + format discovery
- P2.3: Canonical representation + extraction
- P2.4: Quality signals + normalization
- P2.7: Dataset specification + builder
- P2.11: Human-testable CLI

**Medium Priority (Quality & Validation):**
- P2.5: Deduplication
- P2.8: Dataset validation + manifest
- P2.9: Dataset export

**Lower Priority (Enhancement):**
- P2.6: Dataset specification enhancements
- P2.10: Advanced export formats
- P2.12: Demo mode (can be developed in parallel)

---

## Success Criteria

### Phase 2 Success Criteria

**Acceptance Test:**
1. User provides database with collected artifacts
2. User defines dataset requirements via CLI
3. Software inventories source data
4. Software identifies data/document types
5. Software detects formats
6. Software extracts data
7. Software creates canonical records
8. Software calculates quality signals
9. Software removes/reports duplicates
10. Software applies dataset requirements
11. Software constructs dataset
12. Software validates dataset
13. Software exports dataset
14. Software shows user what happened

**Manual Test Requirement:**
- User can run entire workflow manually via CLI
- Demo dataset demonstrates complete pipeline
- All stages produce inspectable outputs
- Reproducible results (same input → same output)

---

## Resource Constraints Compliance

**Hardware Constraints:**
- CPU: Intel Core i3-1315U (modest)
- RAM: 16 GB (limited)
- Storage: 512 GB NVMe (sufficient)
- GPU: None (no CUDA)

**Design Compliance:**
- CPU-first processing (no GPU dependency)
- Bounded memory processing (<4GB per process)
- Streaming/chunked for large datasets
- No distributed infrastructure initially
- No heavy ML dependencies initially

**Dependency Constraints:**
- Minimal external dependencies
- Prefer standard library
- Justify each new dependency
- No Kafka, Kubernetes, Spark, Ray initially

---

## Next Actions

1. **Review and approve** this revised architecture proposal
2. **Update P2_Progress.md** with revised milestone structure
3. **Retire current P2.2 research document** (split into P2.2 + P2.3)
4. **Create new research documents** for revised milestones
5. **Begin P2.2 implementation** (data inventory + format discovery)

**STOP and report proposed architecture before making substantial code changes.**

---

**Proposal Status:** READY FOR REVIEW
