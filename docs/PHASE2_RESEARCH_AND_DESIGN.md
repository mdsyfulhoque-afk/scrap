# Phase 2 Research and Design Document

## Executive Summary

This document presents research into how major AI organizations transform large-scale collected data into high-quality training datasets, and proposes a CPU-first architecture for Phase 2 of the Data_Fetcher_Ubuntu project. The research identifies common transformation stages across industry practices and recommends a staged implementation approach appropriate for resource-constrained local development.

**Key Finding:** Industry data processing pipelines consistently follow a multi-stage transformation pattern: extraction → quality filtering → deduplication → contamination prevention → dataset construction. Our implementation should follow this pattern but scaled for local hardware constraints.

**Recommendation:** Implement a modular, CPU-first pipeline with deterministic processing, staged outputs, and comprehensive provenance tracking. Defer GPU-intensive operations (semantic deduplication, ML-based quality scoring) until hardware permits.

---

## Phase 1 → Phase 2 Boundary

**Phase 1 Scope (VERIFIED):**
- Controlled data acquisition from web sources
- Raw payload preservation in MinIO (bucket: `raw`)
- PostgreSQL provenance catalog (resources, fetches, artifacts, crawl_jobs)
- SHA-256 content hashing
- URL normalization and domain allowlisting
- Content-type validation
- Structured error classification

**Phase 2 Scope:**
- Materialization of raw artifacts from Phase 1 storage
- Text extraction and format conversion
- Canonical document representation
- Quality assessment and filtering
- Language identification
- Safety/PII processing
- Deduplication (exact and near-duplicate)
- Document segmentation
- Metadata enrichment
- Dataset record construction
- Train/validation/test splitting with contamination prevention
- Dataset versioning and manifests
- Training-ready export

**Boundary Interface:**
- Input: PostgreSQL artifact records + MinIO raw objects
- Output: Versioned datasets with manifests
- Interface: Query-based materialization of artifacts for processing

---

## Research Methodology

**Sources Investigated:**
- OpenAI fine-tuning documentation and best practices
- Google DeepMind data processing frameworks (DMVR, MD4)
- Meta AI data pipelines (CCNet, LLaMA data preparation)
- HuggingFace DataTrove library and FineWeb dataset pipeline
- Common Crawl processing research (CCNet paper)
- NVIDIA Nemotron-CC data curation recipe
- Academic research on deduplication (MinHash, LSH)
- Dataset splitting and contamination prevention research

**Distinction Levels:**
- **PUBLICLY DOCUMENTED PRACTICE:** Explicitly described in official documentation or peer-reviewed papers
- **REASONABLE INDUSTRY INFERENCE:** Widely adopted practices across multiple organizations
- **OUR DESIGN DECISION:** Adaptations for our specific constraints and requirements

---

## Publicly Documented Industry Practices

### OpenAI

**DOCUMENTED PRACTICE:**
- Format validation with structured error categorization
- JSONL format for training data
- Minimum 10 examples, 50-100 recommended for fine-tuning
- Quality over quantity emphasis
- Chat completion format with role-based messages
- Data type validation, message structure validation, role validation

**INFERENCE:**
- Multi-stage quality filtering before model consumption
- Emphasis on representative, realistic examples
- Format standardization as preprocessing requirement

### Google DeepMind

**DOCUMENTED PRACTICE:**
- DMVR framework: Parse → Sample → Decode → Preprocess → Postprocess phases
- TFRecord/ArrayRecord format for efficient storage
- Modular data processing graphs with customizable builders
- Separate phases for different modalities
- Shard-based data distribution for multi-host training

**INFERENCE:**
- Phase-based abstraction for pipeline organization
- Efficient binary formats for large-scale storage
- Deterministic preprocessing with caching

### Meta AI (CCNet/LLaMA)

**DOCUMENTED PRACTICE:**
- CCNet pipeline: deduplication → language identification → filtering → perplexity scoring
- Paragraph-level deduplication (70% of text removed)
- Language identification with confidence thresholds
- Perplexity-based quality scoring (head/middle/tail buckets)
- WARC/WET/WAT format handling from Common Crawl
- Two-stage deduplication: within-shard then cross-shard

**INFERENCE:**
- Deduplication as first major processing stage
- Language identification before quality filtering
- Statistical language models for quality assessment
- Bucket-based quality classification

### HuggingFace (DataTrove/FineWeb)

**DOCUMENTED PRACTICE:**
- DataTrove pipeline: WarcReader → URLFilter → Trafilatura → LanguageFilter → GopherRepetitionFilter → GopherQualityFilter → C4QualityFilter → FineWebQualityFilter
- Multi-stage quality filtering with exclusion writers
- MinHash deduplication with LSH for near-duplicates
- Sentence-level deduplication as alternative approach
- PII removal with PIIFormatter
- JsonlWriter for intermediate and final outputs

**INFERENCE:**
- Progressive filtering with rejection tracking
- Multiple quality heuristics applied sequentially
- Near-duplicate detection at scale using MinHash+LSH
- Privacy/safety as explicit pipeline stage

### NVIDIA (Nemotron-CC)

**DOCUMENTED PRACTICE:**
- Four-step pipeline: Extract & Clean → Deduplicate → Quality Classify → Synthetic Data Generation
- Step 1: Download, extract, language ID, Unicode cleanup (CPU-only)
- Step 2a: GPU-accelerated exact deduplication
- Step 2b: MinHash + LSH fuzzy deduplication (GPU identify, CPU remove)
- Step 2c: Substring deduplication using suffix arrays (CPU-only)
- Step 3: Ensemble quality scoring into 20 buckets (GPU classify, CPU ensemble)
- Step 4: LLM-based synthetic data generation

**INFERENCE:**
- Hybrid CPU/GPU approach for large-scale processing
- Multiple deduplication strategies (exact, fuzzy, substring)
- Ensemble quality classification
- CPU can handle significant preprocessing workload

### Common Crawl Processing Research

**DOCUMENTED PRACTICE:**
- WARC/WET/WAT format handling
- 5GB shard organization for processing
- Paragraph-level normalization for deduplication (lowercase, number replacement, punctuation removal)
- Two-stage deduplication: within-shard hashing, then cross-shard comparison
- Language identification with confidence thresholds
- Quality filtering based on heuristics

**INFERENCE:**
- Shard-based processing for scalability
- Normalization critical for effective deduplication
- Multi-stage deduplication required for web-scale data

---

## Common Intermediate Processing Stages

Based on research across organizations, the following stages appear consistently:

### UNIVERSAL STAGES (Present in all surveyed systems)

1. **Raw Data Ingestion/Materialization**
   - Reading from storage (WARC files, object storage, databases)
   - Format validation
   - Metadata extraction

2. **Text Extraction**
   - HTML parsing (Trafilatura, BeautifulSoup)
   - Format conversion (WARC → text, JSON → structured)
   - Boilerplate removal

3. **Language Identification**
   - FastText language identification
   - Confidence thresholds
   - Language whitelisting/blacklisting

4. **Quality Filtering**
   - Multiple heuristics (line punctuation ratio, short line ratio, character duplication)
   - Repetition detection
   - Statistical quality measures

5. **Exact Deduplication**
   - SHA-256 hashing
   - Content-based deduplication
   - Usually first deduplication stage

6. **Dataset Splitting**
   - Train/validation/test separation
   - Contamination prevention
   - Deterministic splitting with seeds

### COMMON STAGES (Present in most systems)

7. **Near-Duplicate Detection**
   - MinHash + LSH
   - Sentence-level deduplication
   - Fuzzy matching

8. **URL/Source Filtering**
   - Domain allowlisting/blocklisting
   - URL pattern filtering
   - Source quality assessment

9. **Normalization**
   - Unicode normalization
   - Whitespace normalization
   - Case normalization (for deduplication)

10. **Metadata Enrichment**
    - Source attribution
    - Processing timestamps
    - Quality scores
    - Language metadata

### OPTIONAL/ADVANCED STAGES (System-dependent)

11. **PII/Safety Processing**
    - PII detection and redaction
    - Content safety filtering
    - Toxicity detection

12. **Semantic Quality Scoring**
    - ML-based quality classification
    - Perplexity scoring
    - Ensemble methods

13. **Synthetic Data Generation**
    - LLM-based data augmentation
    - Knowledge extraction
    - QA generation

14. **Advanced Deduplication**
    - Substring deduplication (suffix arrays)
    - Entity-level deduplication
    - Cross-dataset deduplication

---

## Differences Between Organizations

### Scale Approach
- **Google/Meta:** Petabyte-scale distributed processing with custom infrastructure
- **HuggingFace:** Cloud-based processing with Slurm clusters
- **NVIDIA:** Hybrid CPU/GPU approach with specialized hardware
- **OpenAI:** API-focused with emphasis on format validation

### Deduplication Strategy
- **Meta:** Paragraph-level with statistical normalization
- **HuggingFace:** MinHash + LSH with sentence-level alternative
- **NVIDIA:** Three-stage (exact, fuzzy, substring)
- **Common Crawl:** Two-stage (within-shard, cross-shard)

### Quality Assessment
- **Meta:** Perplexity-based bucketing
- **HuggingFace:** Multiple heuristic filters (Gopher, C4, FineWeb)
- **NVIDIA:** Ensemble classification into 20 buckets
- **OpenAI:** Manual curation emphasis

### Storage Format
- **Google:** TFRecord/ArrayRecord
- **HuggingFace:** JSONL with compression
- **Meta:** Custom shard organization
- **NVIDIA:** Intermediate files with final optimized format

---

## Broadly Applicable Practices

The following practices appear across multiple organizations and are recommended for adoption:

### REQUIRED FOR OUR PROJECT

1. **Staged Pipeline Architecture**
   - Clear separation between processing stages
   - Intermediate outputs for debugging and resumption
   - Rejection tracking with reasons

2. **Exact Deduplication**
   - SHA-256-based content deduplication
   - First deduplication stage
   - CPU-friendly and deterministic

3. **Quality Heuristics**
   - Multiple simple filters (line punctuation, short lines, repetition)
   - Configurable thresholds
   - Rejection logging

4. **Language Identification**
   - FastText-based language detection
   - Confidence thresholds
   - Language filtering

5. **Contamination Prevention**
   - Deduplication before train/test split
   - Deterministic splitting with seeds
   - No overlap between splits

6. **Provenance Tracking**
   - Source URL, fetch ID, artifact ID
   - Processing timestamps
   - Configuration versioning

7. **Dataset Versioning**
   - Manifest files with checksums
   - Configuration tracking
   - Reproducible builds

### RECOMMENDED FOR OUR PROJECT

8. **Near-Duplicate Detection**
   - MinHash + LSH for CPU-friendly near-duplicate detection
   - Can be deferred if hardware constraints prevent it

9. **Text Extraction**
   - HTML parsing with boilerplate removal
   - Support for multiple formats (HTML, JSON, plain text)

10. **Normalization**
    - Unicode normalization
    - Whitespace normalization
    - Consistent encoding

### DEFERRED (Hardware/Scale Constraints)

11. **ML-Based Quality Scoring**
    - Requires GPU or significant CPU resources
    - Perplexity scoring, ensemble classification

12. **Advanced Deduplication**
    - Substring deduplication (memory-intensive)
    - Entity-level deduplication

13. **PII/Safety Processing**
    - Requires ML models or complex rules
    - Can be added as safety layer later

14. **Synthetic Data Generation**
    - Requires LLM inference
    - Post-processing stage

---

## Proprietary/Uncertain Practices

The following practices are mentioned but lack detailed public documentation:

### PROPRIETARY INTERNAL PIPELINES
- OpenAI's full pretraining data pipeline
- Google's internal data infrastructure details
- Meta's complete LLaMA training data construction
- Specific hyperparameters for deduplication (exact MinHash settings)

### UNCERTAIN/INFERENCE-BASED
- Exact quality threshold values (organization-specific)
- Optimal deduplication parameters for different domains
- Specific contamination prevention strategies beyond basic deduplication
- Detailed sharding strategies for distributed processing

---

## Recommended Architecture for Our Project

### Design Principles

1. **CPU-First Processing**
   - No GPU dependencies
   - Streaming/chunked processing
   - Bounded memory usage (target: <4GB per process)

2. **Modular Pipeline**
   - Clear stage boundaries
   - Replaceable components
   - Independent testing

3. **Deterministic Processing**
   - Fixed random seeds
   - Reproducible outputs
   - Versioned configurations

4. **Provenance Preservation**
   - Every output traceable to source
   - Processing metadata recorded
   - Configuration versioning

5. **Staged Outputs**
   - Intermediate representations saved
   - Resumable processing
   - Debugging capability

6. **Resource Constraints**
   - 16GB RAM limit respected
   - Chunked processing for large datasets
   - Incremental processing support

### Proposed Pipeline Stages

```
Phase 1: MinIO (raw) + PostgreSQL (catalog)
    ↓
[P2.1] Raw Materialization
    - Query artifacts from PostgreSQL
    - Download raw objects from MinIO
    - Create processing job record
    ↓
[P2.2] Extraction & Canonical Representation
    - HTML parsing (Trafilatura or similar)
    - Format conversion (JSON, plain text)
    - Boilerplate removal
    - Canonical text representation
    ↓
[P2.3] Normalization
    - Unicode normalization (NFC)
    - Whitespace normalization
    - Encoding consistency (UTF-8)
    ↓
[P2.4] Language Identification
    - FastText language detection
    - Confidence scoring
    - Language filtering based on policy
    ↓
[P2.5] Quality Assessment
    - Line punctuation ratio filter
    - Short line ratio filter
    - Character duplication filter
    - Repetition detection
    - Minimum/maximum length filters
    ↓
[P2.6] Exact Deduplication
    - SHA-256 hashing of normalized text
    - Duplicate detection within batch
    - Duplicate detection across history
    - Retain first occurrence, mark duplicates
    ↓
[P2.7] Near-Duplicate Detection (OPTIONAL/DEFERRED)
    - MinHash signature computation
    - LSH for candidate pair generation
    - Jaccard similarity thresholding
    - Mark near-duplicates
    ↓
[P2.8] Document Segmentation
    - Structural segmentation (paragraphs, sections)
    - Sentence splitting
    - Metadata enrichment (segment counts, lengths)
    ↓
[P2.9] Metadata Enrichment
    - Quality scores aggregation
    - Processing timestamps
    - Source attribution
    - Language metadata
    - Deduplication status
    ↓
[P2.10] Dataset Record Construction
    - Create dataset records from processed documents
    - Apply dataset-specific filters
    - Record rejection reasons
    ↓
[P2.11] Dataset Splitting
    - Deterministic train/validation/test split
    - Contamination prevention (no duplicates across splits)
    - Seed-based reproducibility
    ↓
[P2.12] Dataset Validation
    - Schema validation
    - Format validation
    - Contamination checks
    - Quality metrics
    ↓
[P2.13] Dataset Manifest/Versioning
    - Generate manifest with checksums
    - Record configuration version
    - Record processing version
    - Record source artifact IDs
    ↓
[P2.14] Dataset Export/Sharding
    - Export to JSONL or Parquet
    - Shard generation for large datasets
    - Compression
    ↓
Training-ready dataset
```

### Stage Details

#### P2.1: Raw Materialization
- **Input:** PostgreSQL artifact records, MinIO raw objects
- **Output:** Processing job, materialized raw data
- **Storage:** Temporary local storage or streaming
- **Metadata:** Job ID, artifact IDs, processing configuration
- **Failure Behavior:** Retry with exponential backoff, record failure in job record

#### P2.2: Extraction & Canonical Representation
- **Input:** Raw bytes (HTML, JSON, plain text)
- **Output:** Extracted text, metadata
- **Storage:** Intermediate representation (JSON/JSONL)
- **Metadata:** Extraction method, content type, extraction success/failure
- **Failure Behavior:** Classify extraction errors, skip unextractable content

#### P2.3: Normalization
- **Input:** Extracted text
- **Output:** Normalized text
- **Storage:** In-memory or intermediate file
- **Metadata:** Normalization rules applied
- **Failure Behavior:** Log encoding issues, skip malformed content

#### P2.4: Language Identification
- **Input:** Normalized text
- **Output:** Language code, confidence score
- **Storage:** Metadata field
- **Metadata:** Language detection method, confidence
- **Failure Behavior:** Default to "unknown" if detection fails

#### P2.5: Quality Assessment
- **Input:** Normalized text, language metadata
- **Output:** Quality scores, pass/fail decision
- **Storage:** Metadata fields
- **Metadata:** Individual filter results, aggregate score
- **Failure Behavior:** Log but continue processing

#### P2.6: Exact Deduplication
- **Input:** Normalized text, SHA-256 hash
- **Output:** Deduplication status (unique/duplicate)
- **Storage:** Deduplication index (hash → document ID)
- **Metadata:** Duplicate group ID, first occurrence ID
- **Failure Behavior:** Skip deduplication if index unavailable

#### P2.7: Near-Duplicate Detection (DEFERRED)
- **Input:** Normalized text
- **Output:** Near-duplicate status, similarity score
- **Storage:** MinHash signatures, LSH index
- **Metadata:** Jaccard similarity, LSH bands
- **Failure Behavior:** Skip if computational resources insufficient

#### P2.8: Document Segmentation
- **Input:** Quality-filtered text
- **Output:** Segmented document (paragraphs/sentences)
- **Storage:** Structured representation
- **Metadata:** Segment counts, average lengths
- **Failure Behavior:** Fallback to sentence-level splitting

#### P2.9: Metadata Enrichment
- **Input:** All previous stage outputs
- **Output:** Enriched metadata record
- **Storage:** Metadata field
- **Metadata:** Aggregate scores, processing timestamps
- **Failure Behavior:** Log missing metadata, continue processing

#### P2.10: Dataset Record Construction
- **Input:** Processed documents, metadata
- **Output:** Dataset records
- **Storage:** Database or intermediate files
- **Metadata:** Dataset ID, inclusion criteria
- **Failure Behavior:** Skip documents missing required fields

#### P2.11: Dataset Splitting
- **Input:** Dataset records
- **Output:** Train/validation/test splits
- **Storage:** Separate files or database records
- **Metadata:** Split seed, split ratios
- **Failure Behavior:** Use default split if custom split fails

#### P2.12: Dataset Validation
- **Input:** Split datasets
- **Output:** Validation report
- **Storage:** Validation report file
- **Metadata:** Validation metrics, issues found
- **Failure Behavior:** Log validation failures, block dataset if critical

#### P2.13: Dataset Manifest/Versioning
- **Input:** Validated datasets
- **Output:** Manifest file
- **Storage:** JSON/YAML manifest
- **Metadata:** Version ID, checksums, configuration
- **Failure Behavior:** Block dataset generation if manifest creation fails

#### P2.14: Dataset Export/Sharding
- **Input:** Manifested datasets
- **Output:** Training-ready files
- **Storage:** JSONL/Parquet files with compression
- **Metadata:** File checksums, shard metadata
- **Failure Behavior:** Retry export, log partial failures

---

## Hardware/Resource Implications

### CPU-First Design
- **Processing Approach:** Single-threaded or limited multiprocessing
- **Memory Target:** <4GB per process
- **Batch Size:** Configurable (100-1000 documents per batch)
- **Streaming:** Process documents incrementally
- **Disk Usage:** Intermediate files with cleanup after completion

### Storage Requirements
- **Raw Data:** Read from MinIO (no local copy required)
- **Intermediate Data:** Temporary local storage (cleanup after processing)
- **Final Datasets:** Persistent storage (MinIO or local filesystem)
- **Indexes:** Deduplication index (may require significant disk space)

### Processing Time Estimates
- **Extraction:** ~10-100ms per document (HTML complexity dependent)
- **Quality Filtering:** ~1-10ms per document
- **Exact Deduplication:** ~1ms per document (hashing) + index lookup
- **Near-Duplicate Detection:** ~10-100ms per document (MinHash computation)
- **Total:** ~20-200ms per document (excluding near-duplicate detection)

### Scalability Considerations
- **Local Development:** Process 1K-10K documents per session
- **Incremental Processing:** Process in batches, resume from checkpoints
- **Future Scaling:** Architecture supports distributed processing (horizontal scaling)

---

## Storage Architecture

### Current Phase 1 Storage
- **MinIO:** `raw` bucket for raw objects
- **PostgreSQL:** Catalog tables (resources, fetches, artifacts, crawl_jobs)

### Proposed Phase 2 Storage Extensions

#### MinIO Buckets (Deferred until needed)
- **extracted:** Extracted text and intermediate representations
- **processed:** Quality-filtered and deduplicated documents
- **datasets:** Final training-ready datasets

**Rationale:** Defer bucket creation until actual implementation need demonstrated. May use local filesystem for intermediate storage initially.

#### Storage Namespace Design
```
raw/                    # Phase 1 (existing)
  web/{domain}/{date}/{fetch_id}/payload.bin

extracted/              # Phase 2 (proposed)
  {processing_job_id}/
    {artifact_id}/
      extracted.json
      metadata.json

processed/              # Phase 2 (proposed)
  {processing_job_id}/
    {document_id}/
      processed.json
      metadata.json

datasets/               # Phase 2 (proposed)
  {dataset_version}/
    train/
      shard_00000.jsonl.gz
      shard_00001.jsonl.gz
    validation/
      shard_00000.jsonl.gz
    test/
      shard_00000.jsonl.gz
    manifest.json
```

#### Local Filesystem Alternative
- Use local filesystem for intermediate processing
- Upload final datasets to MinIO
- Reduces MinIO API calls during processing
- Faster local I/O for intensive operations

---

## Database/Catalog Architecture

### Current Phase 1 Schema
- **resources:** URL tracking
- **fetches:** Acquisition attempts
- **artifacts:** Raw object storage references
- **crawl_jobs:** Acquisition job tracking
- **discovered_links:** Link discovery

### Proposed Phase 2 Database Extensions (MIGRATIONS)

#### Processing Jobs Table
```sql
CREATE TABLE processing_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    config JSONB NOT NULL DEFAULT '{}'::jsonb,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

**Purpose:** Track Phase 2 processing jobs, enable resumption and monitoring.

#### Derived Documents Table
```sql
CREATE TABLE derived_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    artifact_id UUID NOT NULL REFERENCES artifacts(id) ON DELETE CASCADE,
    processing_job_id UUID NOT NULL REFERENCES processing_jobs(id) ON DELETE CASCADE,
    extraction_method TEXT,
    extracted_text TEXT,
    normalized_text TEXT,
    language_code TEXT,
    language_confidence FLOAT,
    quality_score JSONB,
    deduplication_status TEXT,
    deduplication_group_id UUID,
    is_duplicate BOOLEAN DEFAULT FALSE,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

**Purpose:** Store processed documents with metadata, enable provenance tracking.

#### Quality Assessments Table
```sql
CREATE TABLE quality_assessments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    derived_document_id UUID NOT NULL REFERENCES derived_documents(id) ON DELETE CASCADE,
    assessment_type TEXT NOT NULL,
    result JSONB NOT NULL,
    passed BOOLEAN NOT NULL,
    reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

**Purpose:** Detailed quality assessment results for debugging and analysis.

#### Dataset Records Table
```sql
CREATE TABLE dataset_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    derived_document_id UUID NOT NULL REFERENCES derived_documents(id) ON DELETE CASCADE,
    dataset_version_id UUID NOT NULL REFERENCES dataset_versions(id) ON DELETE CASCADE,
    split TEXT NOT NULL CHECK (split IN ('train', 'validation', 'test')),
    inclusion_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

**Purpose:** Track which documents are included in which dataset versions.

#### Dataset Versions Table
```sql
CREATE TABLE dataset_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    version_name TEXT NOT NULL UNIQUE,
    config JSONB NOT NULL,
    processing_job_id UUID REFERENCES processing_jobs(id),
    train_count INTEGER NOT NULL DEFAULT 0,
    validation_count INTEGER NOT NULL DEFAULT 0,
    test_count INTEGER NOT NULL DEFAULT 0,
    manifest JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

**Purpose:** Versioned dataset tracking with manifests and configuration.

#### Manifests Table
```sql
CREATE TABLE manifests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_version_id UUID NOT NULL REFERENCES dataset_versions(id) ON DELETE CASCADE,
    manifest_type TEXT NOT NULL,
    content JSONB NOT NULL,
    checksum TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

**Purpose:** Store dataset manifests for reproducibility and validation.

**Migration Strategy:**
- Create `database/migrations/002_phase2_processing.sql`
- Apply migration only when Phase 2 implementation begins
- Ensure backward compatibility with Phase 1

---

## Processing Job Architecture

### Job Model
- **Job Identification:** UUID-based job IDs
- **Job States:** pending, running, completed, failed, cancelled
- **Job Configuration:** JSONB config with processing parameters
- **Checkpoints:** Periodic state saves for resumption
- **Logging:** Structured logs with job context

### Job Execution
- **Local Execution:** Single-process or limited multiprocessing
- **Batch Processing:** Process documents in configurable batches
- **Resumption:** Resume from last checkpoint on failure
- **Failure Handling:** Retry with exponential backoff, max retry limits

### Job Tracking
- **Progress Reporting:** Percentage complete, documents processed
- **Resource Monitoring:** Memory usage, disk usage
- **Error Reporting:** Classified errors with counts
- **Completion Reporting:** Final statistics, output locations

---

## Provenance Model

### Lineage Tracking
Every processed document must track:
- **Source:** resource_id, fetch_id, artifact_id
- **Processing:** processing_job_id, derived_document_id
- **Timestamps:** acquisition time, processing time
- **Configuration:** processing config version
- **Decisions:** quality decisions, deduplication decisions

### Provenance Query
Support queries for:
- "Which dataset version contains this document?"
- "What processing produced this dataset?"
- "Which source artifacts contributed to this dataset?"
- "Show the complete processing history for this document"

### Reproducibility
- **Configuration Versioning:** Hash of processing configuration
- **Code Versioning:** Git commit hash (if applicable)
- **Seed Determinism:** Fixed random seeds for all stochastic operations
- **Manifest Validation:** Checksums of all outputs

---

## Data Lineage Model

### Forward Lineage (Source → Dataset)
```
resource → fetch → artifact → derived_document → dataset_record → dataset_version
```

### Reverse Lineage (Dataset → Source)
```
dataset_version → dataset_record → derived_document → artifact → fetch → resource
```

### Lineage Storage
- **Database:** Foreign key relationships
- **Metadata:** JSONB fields for additional lineage info
- **Manifests:** Complete lineage in dataset manifest

---

## Quality Pipeline

### Quality Filters (Initial Implementation)

#### Line Punctuation Ratio Filter
- **Metric:** Ratio of lines ending with terminal punctuation
- **Threshold:** > 0.12 (configurable)
- **Rationale:** Well-formed text has proper sentence structure

#### Short Line Ratio Filter
- **Metric:** Ratio of lines shorter than threshold (default: 30 chars)
- **Threshold:** < 0.67 (configurable)
- **Rationale:** Excessive short lines indicate poor quality

#### Character Duplication Filter
- **Metric:** Ratio of duplicate characters
- **Threshold:** < 0.01 (configurable)
- **Rationale:** High character duplication indicates repetitive/spam content

#### New Line Ratio Filter
- **Metric:** Ratio of newlines to total characters
- **Threshold:** < 0.3 (configurable)
- **Rationale:** Excessive line breaks indicate formatting issues

#### Length Filters
- **Minimum Length:** > 50 characters (configurable)
- **Maximum Length:** < 1,000,000 characters (configurable)
- **Rationale:** Exclude too short or too long documents

#### Repetition Filter
- **Metric:** N-gram repetition detection
- **Threshold:** Configurable repetition ratio
- **Rationale:** Detect repetitive/spam content

### Quality Scoring
- **Aggregate Score:** Weighted combination of filter results
- **Bucket Classification:** high/medium/low quality based on score
- **Policy Decision:** Include/exclude based on quality bucket

---

## Safety/PII Pipeline

### Initial Approach (Deferred)
- **PII Detection:** Rule-based pattern matching (email, phone, SSN patterns)
- **PII Redaction:** Replace detected PII with placeholders
- **Safety Filtering:** Keyword-based content safety filters
- **Policy:** Configurable safety policies

### Future Enhancement
- **ML-Based PII Detection:** Named entity recognition for PII
- **Contextual Safety:** ML-based toxicity detection
- **Custom Policies:** Domain-specific safety rules

---

## Deduplication Strategy

### Exact Deduplication (REQUIRED)
- **Method:** SHA-256 hashing of normalized text
- **Scope:** Within processing job + historical deduplication index
- **Policy:** Keep first occurrence, mark subsequent as duplicates
- **Storage:** Deduplication index (hash → document_id)
- **Implementation:** PostgreSQL table or external key-value store

### Near-Duplicate Detection (DEFERRED)
- **Method:** MinHash + LSH
- **Shingle Size:** 5-9 characters (configurable)
- **Signature Size:** 128-256 hashes (configurable)
- **LSH Bands:** Configurable number of bands and rows
- **Threshold:** Jaccard similarity > 0.8 (configurable)
- **Policy:** Mark near-duplicates, keep highest quality

### Implementation Considerations
- **Memory:** MinHash signatures require significant memory for large datasets
- **Computation:** MinHash computation is CPU-intensive
- **Storage:** LSH index requires disk storage
- **Scalability:** Near-duplicate detection is O(n) with LSH vs O(n²) without

---

## Dataset Construction Strategy

### Dataset Definition
- **Versioned:** Each dataset has a unique version ID
- **Configured:** Processing configuration recorded
- **Filtered:** Documents selected based on quality and other criteria
- **Split:** Train/validation/test separation
- **Manifested:** Complete manifest with checksums

### Construction Process
1. **Select Documents:** Query derived_documents based on criteria
2. **Apply Filters:** Dataset-specific filters (language, quality, source)
3. **Deduplicate:** Ensure no duplicates within dataset
4. **Split:** Deterministic train/validation/test split
5. **Validate:** Schema validation, contamination checks
6. **Manifest:** Generate manifest with all metadata
7. **Export:** Write to final format (JSONL/Parquet)

### Dataset Types
- **Full Dataset:** All processed documents meeting quality criteria
- **Filtered Dataset:** Subset based on specific criteria (language, source, quality)
- **Synthetic Dataset:** Generated from high-quality documents (deferred)

---

## Dataset Versioning Strategy

### Version Identification
- **Version Name:** Semantic versioning (v1.0.0, v1.1.0, etc.)
- **Version ID:** UUID for internal reference
- **Configuration Hash:** Hash of processing configuration
- **Source Hash:** Hash of source artifact IDs

### Version Metadata
- **Processing Configuration:** All parameters and thresholds
- **Code Version:** Git commit hash (if applicable)
- **Source Artifacts:** List of source artifact IDs
- **Record Counts:** Train/validation/test counts
- **Checksums:** File checksums for all outputs
- **Timestamps:** Creation and processing timestamps

### Reproducibility
- **Deterministic:** Same inputs + same config = same outputs
- **Configuration Tracking:** All parameters recorded
- **Seed Control:** Fixed random seeds for all stochastic operations
- **Validation:** Automated validation of reproducibility

---

## Validation/SQA Strategy

### Validation Levels

#### Schema Validation
- **Required Fields:** All required fields present
- **Data Types:** Field types match schema
- **Value Constraints:** Values within allowed ranges

#### Format Validation
- **File Format:** Valid JSONL/Parquet format
- **Encoding:** UTF-8 encoding
- **Compression:** Valid compression format

#### Content Validation
- **Quality Metrics:** Distribution of quality scores
- **Language Distribution:** Language balance
- **Length Distribution:** Document length statistics
- **Contamination Checks:** No duplicates across splits

#### Contamination Validation
- **Cross-Split Deduplication:** No documents in multiple splits
- **Entity-Level Contamination:** No overlapping entities (deferred)
- **Source Contamination:** No source overlap between splits (deferred)

### Testing Strategy

#### Unit Tests
- **Individual Components:** Test each filter and transformer
- **Deterministic Behavior:** Same input = same output
- **Error Handling:** Proper error classification

#### Integration Tests
- **End-to-End Pipeline:** Test complete pipeline with fixture data
- **Database Integration:** Test database operations
- **Storage Integration:** Test MinIO operations

#### Quality Tests
- **Fixture Processing:** Process known-good fixtures
- **Output Validation:** Validate outputs match expectations
- **Provenance Validation:** Verify lineage tracking

#### Regression Tests
- **Known Outputs:** Ensure outputs don't change unexpectedly
- **Performance Tests:** Monitor processing time and resource usage
- **Scale Tests:** Test with larger datasets (when possible)

---

## Failure Recovery Strategy

### Failure Classification
- **Transient Failures:** Network issues, temporary storage issues (retry)
- **Permanent Failures:** Data corruption, invalid data (skip/log)
- **Configuration Errors:** Invalid parameters (fail fast)
- **Resource Errors:** Out of memory, disk full (fail/notify)

### Recovery Mechanisms
- **Checkpoints:** Periodic state saves
- **Retry Logic:** Exponential backoff for transient failures
- **Skip Logic:** Skip unprocessable documents with logging
- **Job Resumption:** Resume from last checkpoint
- **Partial Completion:** Accept partial success with reporting

### Error Reporting
- **Structured Errors:** Error classification with context
- **Error Aggregation:** Summary of errors by category
- **Error Notification:** Critical errors require notification
- **Error Logging:** Detailed error logs for debugging

---

## Reproducibility Strategy

### Deterministic Processing
- **Fixed Seeds:** Random seeds for all stochastic operations
- **Ordered Processing:** Deterministic ordering of documents
- **Versioned Dependencies:** Specific versions of libraries
- **Configuration Tracking:** All parameters recorded

### Reproducibility Validation
- **Hash Verification:** Compare output hashes
- **Manifest Comparison:** Compare manifests between runs
- **Statistical Validation:** Compare statistics between runs
- **Automated Testing:** Regression tests for reproducibility

### Documentation
- **Configuration Files:** All configuration in version control
- **Processing Logs:** Detailed logs of all operations
- **Manifest Files:** Complete metadata in manifests
- **Run Records:** Record of each processing run

---

## Deferred Functionality

### Hardware-Deferred (Requires GPU or More Resources)
- **Near-Duplicate Detection:** MinHash + LSH (can be CPU-only but expensive)
- **ML-Based Quality Scoring:** Perplexity scoring, ensemble classification
- **Advanced Deduplication:** Substring deduplication, entity-level deduplication
- **PII/Safety ML Models:** ML-based PII detection, toxicity detection

### Scale-Deferred (Requires Distributed Processing)
- **Distributed Processing:** Multi-node processing for large datasets
- **Real-Time Processing:** Streaming processing of live data
- **Large-Scale Indexing:** Distributed deduplication indexes

### Feature-Deferred (Lower Priority)
- **Synthetic Data Generation:** LLM-based data augmentation
- **Advanced Segmentation:** Semantic segmentation, topic-based segmentation
- **Custom Quality Models:** Domain-specific quality models
- **Advanced Metadata:** Entity extraction, topic classification

---

## Phase 2 Implementation Roadmap

### P2.0: Research & Architecture (CURRENT)
- [x] Repository audit
- [x] Phase 1 verification
- [x] Industry research
- [x] Architecture design
- [x] This document creation
- [ ] P2_Progress.md update

### P2.1: Raw Materialization Interface
- Implement artifact query from PostgreSQL
- Implement MinIO object retrieval
- Implement processing job creation
- Implement progress tracking
- **Tests:** Materialization with local MinIO/PostgreSQL

### P2.2: Extraction & Canonical Representation
- Implement HTML extraction (Trafilatura or similar)
- Implement JSON extraction
- Implement plain text handling
- Implement canonical text representation
- **Tests:** Extraction with HTML, JSON, plain text fixtures

### P2.3: Normalization
- Implement Unicode normalization
- Implement whitespace normalization
- Implement encoding consistency
- **Tests:** Normalization with various encodings and formats

### P2.4: Language Identification
- Implement FastText language detection
- Implement confidence scoring
- Implement language filtering
- **Tests:** Language identification with multilingual fixtures

### P2.5: Quality Assessment
- Implement line punctuation ratio filter
- Implement short line ratio filter
- Implement character duplication filter
- Implement length filters
- Implement repetition filter
- **Tests:** Quality filters with good/bad quality fixtures

### P2.6: Exact Deduplication
- Implement SHA-256 hashing
- Implement deduplication index
- Implement duplicate detection
- Implement duplicate marking
- **Tests:** Deduplication with duplicate/non-duplicate fixtures

### P2.7: Near-Duplicate Detection (DEFERRED)
- Implement MinHash signature computation
- Implement LSH index
- Implement near-duplicate detection
- **Tests:** Near-duplicate detection with near-duplicate fixtures

### P2.8: Document Segmentation
- Implement paragraph segmentation
- Implement sentence splitting
- Implement metadata enrichment
- **Tests:** Segmentation with various document structures

### P2.9: Metadata Enrichment
- Implement quality score aggregation
- Implement processing timestamp recording
- Implement source attribution
- **Tests:** Metadata enrichment with processed documents

### P2.10: Dataset Record Construction
- Implement dataset record creation
- Implement dataset-specific filtering
- Implement rejection reason recording
- **Tests:** Dataset record construction with processed documents

### P2.11: Dataset Splitting
- Implement deterministic train/validation/test split
- Implement contamination prevention
- Implement seed-based reproducibility
- **Tests:** Splitting with contamination checks

### P2.12: Dataset Validation
- Implement schema validation
- Implement format validation
- Implement contamination validation
- **Tests:** Validation with valid/invalid datasets

### P2.13: Dataset Manifest/Versioning
- Implement manifest generation
- Implement configuration tracking
- Implement checksum computation
- **Tests:** Manifest generation with known datasets

### P2.14: Dataset Export/Sharding
- Implement JSONL export
- Implement Parquet export (optional)
- Implement compression
- Implement sharding
- **Tests:** Export with various dataset sizes

### P2.15: End-to-End Phase 2 SQA
- Implement end-to-end integration test
- Implement reproducibility validation
- Implement performance testing
- **Tests:** Complete pipeline with fixture data

---

## Risks

### Technical Risks
- **Resource Exhaustion:** Memory/disk limits for large datasets
- **Performance:** Processing time may be prohibitive for large datasets
- **Dependencies:** External library compatibility issues
- **Data Quality:** Poor quality source data may break processing

### Architecture Risks
- **Over-Engineering:** Implementing unnecessary complexity
- **Under-Engineering:** Missing critical quality/safety stages
- **Tight Coupling:** Difficulty modifying pipeline later
- **Scalability:** Architecture may not scale to larger datasets

### Project Risks
- **Scope Creep:** Adding too many features
- **Hardware Constraints:** Hardware may limit implementation
- **Time Constraints:** Implementation may take longer than expected
- **Maintenance:** Long-term maintenance burden

### Mitigation Strategies
- **Incremental Implementation:** Implement one stage at a time
- **Modular Design:** Clear separation between stages
- **Comprehensive Testing:** Test each stage independently
- **Documentation:** Document all decisions and configurations
- **Monitoring:** Monitor resource usage and performance
- **Flexibility:** Design for future modifications

---

## Open Questions

### Technical Questions
1. **Exact Deduplication Storage:** Should deduplication index be in PostgreSQL or external key-value store?
2. **Near-Duplicate Feasibility:** Is MinHash + LSH feasible on 16GB RAM for our expected dataset size?
3. **Language Detection:** Should we use FastText or a lighter alternative?
4. **Storage Format:** Should we use JSONL or Parquet for intermediate/final storage?

### Architecture Questions
1. **Project Structure:** Should Phase 2 be in the same repository or separate?
2. **Processing Model:** Should we use batch processing or streaming?
3. **Checkpoint Frequency:** How often should we save checkpoints?
4. **Error Tolerance:** What error rate is acceptable for processing?

### Scope Questions
1. **Initial Dataset Size:** How many documents should we target for initial implementation?
2. **Quality Thresholds:** What quality thresholds should we use initially?
3. **Language Scope:** Should we initially focus on English or multilingual?
4. **Safety Requirements:** What level of safety/PII processing is required initially?

---

## Conclusion

This research demonstrates that large-scale AI data processing follows consistent patterns across organizations: extraction → quality filtering → deduplication → contamination prevention → dataset construction. Our Phase 2 implementation should follow these patterns while adapting to our CPU-first, resource-constrained environment.

The recommended architecture prioritizes:
1. **Modularity:** Clear stage boundaries for independent testing and modification
2. **Determinism:** Reproducible processing with fixed seeds and versioned configurations
3. **Provenance:** Complete lineage tracking from source to dataset
4. **Resource Awareness:** CPU-first design with bounded memory usage
5. **Incremental Implementation:** One stage at a time with comprehensive testing

The deferred functionality (near-duplicate detection, ML-based quality scoring, advanced deduplication) can be added later when hardware permits or requirements justify the complexity.

**Next Step:** Create database migrations for Phase 2 tables and begin implementation of P2.1 (Raw Materialization Interface).
