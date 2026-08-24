"""Phase 2: Similarity metrics for duplicate detection."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


class SimilarityError(Exception):
    """Similarity-specific errors."""
    def __init__(self, category: str, message: str):
        self.category = category
        super().__init__(message)


@dataclass
class SimilarityConfig:
    """Configuration for similarity calculation."""
    shingle_size: int = 3  # character trigrams
    min_hash_sketch_size: int = 128
    band_count: int = 16
    jaccard_threshold: float = 0.85
    algorithm_version: str = "trigram-jaccard-1.0.0"


@dataclass
class SimilarityResult:
    """Result of comparing two documents."""
    document_a_id: str
    document_b_id: str
    document_a_type: str
    document_b_type: str
    comparison_method: str
    similarity_score: float | None
    is_duplicate: bool
    duplicate_type: str | None
    jaccard_similarity: float | None
    min_hash_sketch_a: list[str] | None
    min_hash_sketch_b: list[str] | None
    shared_bands: int | None
    warnings: list[str]
    errors: list[str]


def extract_trigrams(text: str) -> set[str]:
    """
    Extract character trigrams from text.
    
    Args:
        text: Input text
        
    Returns:
        Set of character trigrams
    """
    if not text or len(text) < 3:
        return set()
    
    # Normalize: lowercase, collapse whitespace to single space
    normalized = text.lower()
    normalized = " ".join(normalized.split())
    
    trigrams: set[str] = set()
    for i in range(len(normalized) - 2):
        trigram = normalized[i:i + 3]
        trigrams.add(trigram)
    
    return trigrams


def compute_min_hash_sketch(trigrams: set[str], sketch_size: int = 128) -> list[str]:
    """
    Compute a deterministic min-hash sketch using SHA-256.
    
    For each of sketch_size hash functions, find the minimum hash value
    across all trigrams. This provides a Jaccard similarity approximation.
    
    Args:
        trigrams: Set of character trigrams
        sketch_size: Number of hash values to keep
        
    Returns:
        Sorted list of min-hash values for determinism
    """
    if not trigrams:
        return []
    
    trigrams_list = list(trigrams)
    hashes: list[str] = []
    
    for i in range(sketch_size):
        min_hash = None
        for trigram in trigrams_list:
            # Deterministic hash: SHA-256 with seed prefix for each hash function
            hash_value = hashlib.sha256(f"{i}:{trigram}".encode("utf-8")).hexdigest()
            if min_hash is None or hash_value < min_hash:
                min_hash = hash_value
        hashes.append(min_hash)
    
    hashes.sort()
    return hashes


def compute_jaccard_similarity(set_a: set[str], set_b: set[str]) -> float:
    """
    Compute Jaccard similarity between two sets.
    
    Jaccard = |A ∩ B| / |A ∪ B|
    
    Args:
        set_a: First set
        set_b: Second set
        
    Returns:
        Jaccard similarity float between 0.0 and 1.0
    """
    if not set_a and not set_b:
        return 1.0
    
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    
    if union == 0:
        return 0.0
    
    return intersection / union


def compute_band_hash(sketch: list[str], band_size: int, band_index: int) -> str | None:
    """
    Compute a hash for a specific band of a min-hash sketch.
    
    Args:
        sketch: Min-hash sketch
        band_size: Number of elements per band
        band_index: Which band to hash (0-indexed)
        
    Returns:
        SHA-256 hex digest of the band, or None if band is out of range
    """
    start = band_index * band_size
    end = start + band_size
    
    if start >= len(sketch):
        return None
    
    band_elements = sketch[start:end]
    band_content = "".join(band_elements)
    return hashlib.sha256(band_content.encode("utf-8")).hexdigest()


def find_candidate_pairs(
    sketches: dict[str, list[str]],
    band_count: int = 16,
) -> set[tuple[str, str]]:
    """
    Find candidate pairs using banding on min-hash sketches.
    
    Documents sharing any band are candidates for detailed comparison.
    
    Args:
        sketches: Mapping from document ID to min-hash sketch
        band_count: Number of bands to use
        
    Returns:
        Set of candidate document ID pairs (sorted tuples)
    """
    band_size = max(1, len(next(iter(sketches.values()))) // band_count) if sketches else 1
    
    band_buckets: dict[str, list[str]] = {}
    
    for doc_id, sketch in sketches.items():
        for band_index in range(band_count):
            band_hash = compute_band_hash(sketch, band_size, band_index)
            if band_hash is None:
                break
            
            if band_hash not in band_buckets:
                band_buckets[band_hash] = []
            band_buckets[band_hash].append(doc_id)
    
    # Generate candidate pairs from shared bands
    candidate_pairs: set[tuple[str, str]] = set()
    for doc_ids in band_buckets.values():
        if len(doc_ids) > 1:
            # Generate all pairs within this bucket
            for i in range(len(doc_ids)):
                for j in range(i + 1, len(doc_ids)):
                    pair = (doc_ids[i], doc_ids[j]) if doc_ids[i] < doc_ids[j] else (doc_ids[j], doc_ids[i])
                    candidate_pairs.add(pair)
    
    return candidate_pairs


class UnionFind:
    """Union-Find data structure for transitive grouping."""
    
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}
        self.rank: dict[str, int] = {}
    
    def find(self, x: str) -> str:
        """Find the root of x with path compression."""
        if x not in self.parent:
            self.parent[x] = x
            self.rank[x] = 0
            return x
        
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])
        return self.parent[x]
    
    def union(self, x: str, y: str) -> None:
        """Union the sets containing x and y."""
        root_x = self.find(x)
        root_y = self.find(y)
        
        if root_x == root_y:
            return
        
        # Union by rank
        if self.rank[root_x] < self.rank[root_y]:
            self.parent[root_x] = root_y
        elif self.rank[root_x] > self.rank[root_y]:
            self.parent[root_y] = root_x
        else:
            self.parent[root_y] = root_x
            self.rank[root_x] += 1
    
    def get_groups(self) -> dict[str, list[str]]:
        """Get all groups as mapping from root to members."""
        groups: dict[str, list[str]] = {}
        for x in self.parent:
            root = self.find(x)
            if root not in groups:
                groups[root] = []
            groups[root].append(x)
        
        # Sort members for determinism
        for members in groups.values():
            members.sort()
        
        return groups
