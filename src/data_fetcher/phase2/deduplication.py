"""Phase 2: Duplicate detection and duplicate decision layer."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any

from data_fetcher.models import (
    CanonicalDocument,
    DuplicateComparison,
    DuplicateGroup,
    DuplicateMembership,
    NormalizedDocument,
)
from data_fetcher.phase2.similarity import (
    SimilarityConfig,
    SimilarityResult,
    compute_jaccard_similarity,
    compute_min_hash_sketch,
    extract_trigrams,
    find_candidate_pairs,
    UnionFind,
)

logger = logging.getLogger(__name__)


class DuplicateDetectionError(Exception):
    """Duplicate detection-specific errors."""
    def __init__(self, category: str, message: str):
        self.category = category
        super().__init__(message)


@dataclass
class DuplicateDetectionConfig:
    """Configuration for duplicate detection."""
    algorithm_version: str = "trigram-jaccard-1.0.0"
    jaccard_threshold: float = 0.85
    shingle_size: int = 3
    min_hash_sketch_size: int = 128
    band_count: int = 16
    enable_raw_exact: bool = True
    enable_normalized_exact: bool = True
    enable_near_duplicate: bool = True


@dataclass
class DocumentReference:
    """Reference to a document for duplicate comparison."""
    document_id: str
    document_type: str  # "normalized_document", "canonical_document", "artifact"
    normalized_checksum: str | None
    canonical_checksum: str | None
    raw_checksum: str | None
    normalized_text: str | None
    quality_score: float
    warning_count: int
    source_url: str
    artifact_id: str
    canonical_document_id: str | None
    normalized_document_id: str | None


@dataclass
class DuplicateDetectionResult:
    """Result of duplicate detection run."""
    algorithm_version: str
    algorithm_config: dict[str, Any]
    total_documents_analyzed: int
    raw_exact_groups: list[DuplicateGroup]
    normalized_exact_groups: list[DuplicateGroup]
    near_duplicate_groups: list[DuplicateGroup]
    all_groups: list[DuplicateGroup]
    memberships: list[DuplicateMembership]
    comparisons: list[DuplicateComparison]
    warnings: list[str]
    errors: list[str]
    documents_skipped: int
    created_at: str


class DuplicateDetector:
    """Detect duplicates and form duplicate groups."""

    def __init__(self, config: DuplicateDetectionConfig | None = None) -> None:
        self.config = config or DuplicateDetectionConfig()
        self.similarity_config = SimilarityConfig(
            shingle_size=self.config.shingle_size,
            min_hash_sketch_size=self.config.min_hash_sketch_size,
            band_count=self.config.band_count,
            jaccard_threshold=self.config.jaccard_threshold,
            algorithm_version=self.config.algorithm_version,
        )

    def detect(
        self,
        documents: list[DocumentReference],
    ) -> DuplicateDetectionResult:
        """
        Run duplicate detection on a list of documents.
        
        Args:
            documents: List of document references
            
        Returns:
            DuplicateDetectionResult with groups, memberships, and comparisons
        """
        warnings: list[str] = []
        errors: list[str] = []
        comparisons: list[DuplicateComparison] = []
        
        # Filter documents with normalized text for near-duplicate detection
        analyzable = [d for d in documents if d.normalized_text]
        documents_skipped = len(documents) - len(analyzable)
        
        if documents_skipped > 0:
            warnings.append(f"{documents_skipped} documents skipped (no normalized text)")
        
        # Step 1: Raw exact duplicates
        raw_exact_groups: list[DuplicateGroup] = []
        raw_exact_memberships: list[DuplicateMembership] = []
        if self.config.enable_raw_exact:
            raw_exact_groups, raw_exact_memberships = self._detect_raw_exact(documents)
        
        # Step 2: Normalized exact duplicates
        normalized_exact_groups: list[DuplicateGroup] = []
        normalized_exact_memberships: list[DuplicateMembership] = []
        if self.config.enable_normalized_exact:
            normalized_exact_groups, normalized_exact_memberships = self._detect_normalized_exact(analyzable)
        
        # Step 3: Near duplicates (only on documents not already in exact groups)
        exact_member_doc_ids = set()
        for membership in raw_exact_memberships + normalized_exact_memberships:
            if membership.normalized_document_id:
                exact_member_doc_ids.add(membership.normalized_document_id)
            if membership.canonical_document_id:
                exact_member_doc_ids.add(membership.canonical_document_id)
            if membership.artifact_id:
                exact_member_doc_ids.add(membership.artifact_id)
        
        near_duplicate_groups: list[DuplicateGroup] = []
        near_duplicate_memberships: list[DuplicateMembership] = []
        if self.config.enable_near_duplicate:
            near_duplicate_groups, near_duplicate_memberships, near_comparisons = self._detect_near_duplicates(
                analyzable, exact_member_doc_ids
            )
            comparisons.extend(near_comparisons)
        
        # Combine all groups and memberships
        all_groups = raw_exact_groups + normalized_exact_groups + near_duplicate_groups
        all_memberships = raw_exact_memberships + normalized_exact_memberships + near_duplicate_memberships
        
        # Temporary IDs were assigned at group/membership creation time above
        
        # Add representatives to groups
        self._assign_representatives(all_groups, all_memberships, documents)
        
        return DuplicateDetectionResult(
            algorithm_version=self.config.algorithm_version,
            algorithm_config=self._get_algorithm_config(),
            total_documents_analyzed=len(documents),
            raw_exact_groups=raw_exact_groups,
            normalized_exact_groups=normalized_exact_groups,
            near_duplicate_groups=near_duplicate_groups,
            all_groups=all_groups,
            memberships=all_memberships,
            comparisons=comparisons,
            warnings=warnings,
            errors=errors,
            documents_skipped=documents_skipped,
            created_at="",
        )

    def _detect_raw_exact(
        self, documents: list[DocumentReference]
    ) -> tuple[list[DuplicateGroup], list[DuplicateMembership]]:
        """Detect raw exact duplicates by checksum."""
        groups: list[DuplicateGroup] = []
        memberships: list[DuplicateMembership] = []
        
        # Group by raw checksum
        checksum_groups: dict[str, list[DocumentReference]] = {}
        for doc in documents:
            if doc.raw_checksum:
                checksum_groups.setdefault(doc.raw_checksum, []).append(doc)
        
        # Create groups for checksums with more than one document
        for checksum, docs in checksum_groups.items():
            if len(docs) < 2:
                continue
            
            # Sort docs by ID for deterministic group formation
            docs.sort(key=lambda d: d.document_id)
            
            temp_group_id = f"temp-raw-{len(groups)}"
            group = DuplicateGroup(
                id=temp_group_id,
                duplicate_method="raw_exact",
                algorithm_version=self.config.algorithm_version,
                algorithm_config=self._get_algorithm_config(),
                representative_normalized_document_id=None,
                representative_canonical_document_id=None,
                group_size=len(docs),
                similarity_stats={"raw_checksum": checksum, "exact_match": True},
                warnings=[],
                errors=[],
                provenance={"checksum_type": "raw_sha256"},
                created_at="",
                updated_at="",
            )
            groups.append(group)
            
            for doc in docs:
                membership = DuplicateMembership(
                    id=f"temp-raw-m-{len(memberships)}",
                    group_id=temp_group_id,
                    normalized_document_id=doc.normalized_document_id,
                    canonical_document_id=doc.canonical_document_id,
                    artifact_id=doc.artifact_id,
                    comparison_method="raw_exact",
                    similarity_score=1.0,
                    is_representative=False,
                    selection_basis=None,
                    warnings=[],
                    errors=[],
                    provenance={"raw_checksum": checksum},
                    created_at="",
                    updated_at="",
                )
                memberships.append(membership)
        
        return groups, memberships

    def _detect_normalized_exact(
        self, documents: list[DocumentReference]
    ) -> tuple[list[DuplicateGroup], list[DuplicateMembership]]:
        """Detect normalized exact duplicates by normalized_checksum."""
        groups: list[DuplicateGroup] = []
        memberships: list[DuplicateMembership] = []
        
        # Group by normalized checksum
        checksum_groups: dict[str, list[DocumentReference]] = {}
        for doc in documents:
            if doc.normalized_checksum:
                checksum_groups.setdefault(doc.normalized_checksum, []).append(doc)
        
        # Create groups for checksums with more than one document
        for checksum, docs in checksum_groups.items():
            if len(docs) < 2:
                continue
            
            # Sort docs by ID for deterministic group formation
            docs.sort(key=lambda d: d.document_id)
            
            temp_group_id = f"temp-norm-{len(groups)}"
            group = DuplicateGroup(
                id=temp_group_id,
                duplicate_method="normalized_exact",
                algorithm_version=self.config.algorithm_version,
                algorithm_config=self._get_algorithm_config(),
                representative_normalized_document_id=None,
                representative_canonical_document_id=None,
                group_size=len(docs),
                similarity_stats={"normalized_checksum": checksum, "exact_match": True},
                warnings=[],
                errors=[],
                provenance={"checksum_type": "normalized_sha256"},
                created_at="",
                updated_at="",
            )
            groups.append(group)
            
            for doc in docs:
                membership = DuplicateMembership(
                    id=f"temp-norm-m-{len(memberships)}",
                    group_id=temp_group_id,
                    normalized_document_id=doc.normalized_document_id,
                    canonical_document_id=doc.canonical_document_id,
                    artifact_id=doc.artifact_id,
                    comparison_method="normalized_exact",
                    similarity_score=1.0,
                    is_representative=False,
                    selection_basis=None,
                    warnings=[],
                    errors=[],
                    provenance={"normalized_checksum": checksum},
                    created_at="",
                    updated_at="",
                )
                memberships.append(membership)
        
        return groups, memberships

    def _detect_near_duplicates(
        self,
        documents: list[DocumentReference],
        exclude_doc_ids: set[str],
    ) -> tuple[list[DuplicateGroup], list[DuplicateMembership], list[DuplicateComparison]]:
        """Detect near duplicates using trigram Jaccard similarity."""
        groups: list[DuplicateGroup] = []
        memberships: list[DuplicateMembership] = []
        comparisons: list[DuplicateComparison] = []
        
        # Filter out already-grouped documents
        candidates = [d for d in documents if d.document_id not in exclude_doc_ids]
        
        if len(candidates) < 2:
            return groups, memberships, comparisons
        
        # Extract trigrams and compute min-hash sketches
        doc_trigrams: dict[str, set[str]] = {}
        doc_sketches: dict[str, list[str]] = {}
        
        for doc in candidates:
            if doc.normalized_text:
                trigrams = extract_trigrams(doc.normalized_text)
                sketch = compute_min_hash_sketch(trigrams, self.config.min_hash_sketch_size)
                doc_trigrams[doc.document_id] = trigrams
                doc_sketches[doc.document_id] = sketch
        
        # Find candidate pairs using banding
        candidate_pairs = find_candidate_pairs(doc_sketches, self.config.band_count)
        
        if not candidate_pairs:
            return groups, memberships, comparisons
        
        # Compute exact Jaccard similarity for candidates
        similar_pairs: list[tuple[str, str, float]] = []
        for doc_a_id, doc_b_id in candidate_pairs:
            trigrams_a = doc_trigrams.get(doc_a_id, set())
            trigrams_b = doc_trigrams.get(doc_b_id, set())
            similarity = compute_jaccard_similarity(trigrams_a, trigrams_b)
            
            doc_a = next(d for d in candidates if d.document_id == doc_a_id)
            doc_b = next(d for d in candidates if d.document_id == doc_b_id)
            
            is_duplicate = similarity >= self.config.jaccard_threshold
            duplicate_type = "near_duplicate" if is_duplicate else None
            
            comparison = DuplicateComparison(
                document_a_id=doc_a_id,
                document_b_id=doc_b_id,
                document_a_type=doc_a.document_type,
                document_b_type=doc_b.document_type,
                comparison_method="trigram_jaccard",
                similarity_score=similarity,
                is_duplicate=is_duplicate,
                duplicate_type=duplicate_type,
                jaccard_similarity=similarity,
                min_hash_sketch_a=doc_sketches.get(doc_a_id),
                min_hash_sketch_b=doc_sketches.get(doc_b_id),
                shared_bands=sum(
                    1 for band_index in range(self.config.band_count)
                    if self._bands_share_element(
                        doc_sketches.get(doc_a_id, []),
                        doc_sketches.get(doc_b_id, []),
                        self.config.min_hash_sketch_size // self.config.band_count,
                        band_index,
                    )
                ),
                warnings=[],
                errors=[],
            )
            comparisons.append(comparison)
            
            if is_duplicate:
                similar_pairs.append((doc_a_id, doc_b_id, similarity))
        
        if not similar_pairs:
            return groups, memberships, comparisons
        
        # Form groups using union-find for transitive closure
        uf = UnionFind()
        for doc in candidates:
            uf.find(doc.document_id)  # Initialize all documents
        
        for doc_a_id, doc_b_id, _ in similar_pairs:
            uf.union(doc_a_id, doc_b_id)
        
        # Create groups from union-find components
        uf_groups = uf.get_groups()
        
        # Sort groups by root ID for determinism
        sorted_roots = sorted(uf_groups.keys())
        
        for root in sorted_roots:
            members = uf_groups[root]
            if len(members) < 2:
                continue
            
            # Compute average similarity for the group
            group_similarities = [
                sim for (a, b, sim) in similar_pairs
                if a in members and b in members
            ]
            avg_similarity = sum(group_similarities) / len(group_similarities) if group_similarities else 0.0
            max_similarity = max(group_similarities) if group_similarities else 0.0
            min_similarity = min(group_similarities) if group_similarities else 0.0
            
            temp_group_id = f"temp-near-{len(groups)}"
            group = DuplicateGroup(
                id=temp_group_id,
                duplicate_method="near_duplicate",
                algorithm_version=self.config.algorithm_version,
                algorithm_config=self._get_algorithm_config(),
                representative_normalized_document_id=None,
                representative_canonical_document_id=None,
                group_size=len(members),
                similarity_stats={
                    "jaccard_threshold": self.config.jaccard_threshold,
                    "avg_similarity": round(avg_similarity, 4),
                    "max_similarity": round(max_similarity, 4),
                    "min_similarity": round(min_similarity, 4),
                    "pair_count": len(group_similarities),
                },
                warnings=[],
                errors=[],
                provenance={"algorithm": "trigram_jaccard_banding"},
                created_at="",
                updated_at="",
            )
            groups.append(group)
            
            for doc_id in members:
                doc = next(d for d in candidates if d.document_id == doc_id)
                membership = DuplicateMembership(
                    id=f"temp-near-m-{len(memberships)}",
                    group_id=temp_group_id,
                    normalized_document_id=doc.normalized_document_id,
                    canonical_document_id=doc.canonical_document_id,
                    artifact_id=doc.artifact_id,
                    comparison_method="trigram_jaccard",
                    similarity_score=None,
                    is_representative=False,
                    selection_basis=None,
                    warnings=[],
                    errors=[],
                    provenance={"jaccard_threshold": self.config.jaccard_threshold},
                    created_at="",
                    updated_at="",
                )
                memberships.append(membership)
        
        return groups, memberships, comparisons

    def _bands_share_element(
        self, sketch_a: list[str], sketch_b: list[str], band_size: int, band_index: int
    ) -> bool:
        """Check if two sketches share any element in a specific band."""
        start = band_index * band_size
        end = start + band_size
        
        band_a = set(sketch_a[start:end]) if start < len(sketch_a) else set()
        band_b = set(sketch_b[start:end]) if start < len(sketch_b) else set()
        
        return bool(band_a & band_b)

    def _assign_representatives(
        self,
        groups: list[DuplicateGroup],
        memberships: list[DuplicateMembership],
        all_documents: list[DocumentReference],
    ) -> None:
        """Assign representatives to groups using deterministic priority rules."""
        doc_map = {d.document_id: d for d in all_documents}
        doc_map_by_normalized_id = {d.normalized_document_id: d for d in all_documents if d.normalized_document_id}
        doc_map_by_canonical_id = {d.canonical_document_id: d for d in all_documents if d.canonical_document_id}
        doc_map_by_artifact_id = {d.artifact_id: d for d in all_documents}
        
        def get_doc(doc_id: str) -> DocumentReference | None:
            return (
                doc_map.get(doc_id) or
                doc_map_by_normalized_id.get(doc_id) or
                doc_map_by_canonical_id.get(doc_id) or
                doc_map_by_artifact_id.get(doc_id)
            )
        
        for group in groups:
            group_memberships = [m for m in memberships if m.group_id == group.id]
            if not group_memberships:
                continue
            
            # Get document IDs for this group
            member_doc_ids: list[str] = []
            for membership in group_memberships:
                if membership.normalized_document_id:
                    member_doc_ids.append(membership.normalized_document_id)
                elif membership.canonical_document_id:
                    member_doc_ids.append(membership.canonical_document_id)
                elif membership.artifact_id:
                    member_doc_ids.append(membership.artifact_id)
            
            # Sort by deterministic priority
            def sort_key(doc_id: str) -> tuple[int, int, int, str]:
                doc = get_doc(doc_id)
                if not doc:
                    return (0, 0, 0, doc_id)
                
                # Priority 1: has normalized text (1 = yes, 0 = no)
                has_normalized = 1 if doc.normalized_text else 0
                
                # Priority 2: quality score (higher is better, negate for ascending sort)
                quality = -doc.quality_score
                
                # Priority 3: warning count (lower is better, negate for ascending sort)
                warnings = doc.warning_count
                
                # Priority 4: stable ID tie-breaker
                stable_id = doc_id
                
                return (has_normalized, quality, warnings, stable_id)
            
            member_doc_ids.sort(key=sort_key)
            representative_id = member_doc_ids[0]
            representative_doc = get_doc(representative_id)
            
            # Update group
            if representative_doc and representative_doc.normalized_document_id:
                group.representative_normalized_document_id = representative_doc.normalized_document_id
            elif representative_doc and representative_doc.canonical_document_id:
                group.representative_canonical_document_id = representative_doc.canonical_document_id
            
            # Update memberships
            for membership in group_memberships:
                if (
                    (membership.normalized_document_id and membership.normalized_document_id == representative_id) or
                    (membership.canonical_document_id and membership.canonical_document_id == representative_id) or
                    (membership.artifact_id and membership.artifact_id == representative_id)
                ):
                    membership.is_representative = True
                    membership.selection_basis = self._get_selection_basis(representative_doc)

    def _get_selection_basis(self, doc: DocumentReference | None) -> str:
        """Generate human-readable selection basis for a representative."""
        if not doc:
            return "stable_id_tiebreaker"
        
        reasons = []
        if doc.normalized_text:
            reasons.append("has_normalized_text")
        if doc.quality_score > 0:
            reasons.append(f"quality_score_{doc.quality_score:.2f}")
        if doc.warning_count == 0:
            reasons.append("no_warnings")
        
        if reasons:
            return "_".join(reasons) + "_stable_id"
        return "stable_id_tiebreaker"

    def _get_algorithm_config(self) -> dict[str, Any]:
        """Get algorithm configuration as a dictionary."""
        return {
            "algorithm_version": self.config.algorithm_version,
            "jaccard_threshold": self.config.jaccard_threshold,
            "shingle_size": self.config.shingle_size,
            "min_hash_sketch_size": self.config.min_hash_sketch_size,
            "band_count": self.config.band_count,
            "enable_raw_exact": self.config.enable_raw_exact,
            "enable_normalized_exact": self.config.enable_normalized_exact,
            "enable_near_duplicate": self.config.enable_near_duplicate,
        }
