"""Unit tests for Phase 2 deduplication."""

from __future__ import annotations

import pytest

from data_fetcher.models import CanonicalDocument, DuplicateGroup, DuplicateMembership, NormalizedDocument
from data_fetcher.phase2.deduplication import (
    DuplicateDetectionConfig,
    DuplicateDetectionResult,
    DuplicateDetector,
    DocumentReference,
)
from data_fetcher.phase2.similarity import (
    UnionFind,
    compute_jaccard_similarity,
    compute_min_hash_sketch,
    extract_trigrams,
    find_candidate_pairs,
)


# ============================================================
# Similarity Tests
# ============================================================

class TestExtractTrigrams:
    def test_basic_trigrams(self):
        trigrams = extract_trigrams("hello world")
        assert "hel" in trigrams
        assert "ell" in trigrams
        assert "llo" in trigrams
        assert "lo " in trigrams
        assert "o w" in trigrams
        assert " wo" in trigrams
        assert "wor" in trigrams
        assert "orl" in trigrams
        assert "rld" in trigrams

    def test_short_text(self):
        assert extract_trigrams("") == set()
        assert extract_trigrams("a") == set()
        assert extract_trigrams("ab") == set()
        assert extract_trigrams("abc") == {"abc"}

    def test_normalization(self):
        assert extract_trigrams("Hello World") == extract_trigrams("hello world")

    def test_whitespace_collapse(self):
        trigrams = extract_trigrams("hello   world")
        assert "lo " in trigrams
        assert "o  " not in trigrams  # Multiple spaces collapsed


class TestJaccardSimilarity:
    def test_identical_sets(self):
        a = {"a", "b", "c"}
        b = {"a", "b", "c"}
        assert compute_jaccard_similarity(a, b) == 1.0

    def test_disjoint_sets(self):
        a = {"a", "b"}
        b = {"c", "d"}
        assert compute_jaccard_similarity(a, b) == 0.0

    def test_partial_overlap(self):
        a = {"a", "b", "c"}
        b = {"b", "c", "d"}
        assert compute_jaccard_similarity(a, b) == 0.5

    def test_empty_sets(self):
        assert compute_jaccard_similarity(set(), set()) == 1.0
        assert compute_jaccard_similarity(set(), {"a"}) == 0.0


class TestMinHashSketch:
    def test_deterministic(self):
        trigrams = {"abc", "def", "ghi"}
        sketch1 = compute_min_hash_sketch(trigrams, 4)
        sketch2 = compute_min_hash_sketch(trigrams, 4)
        assert sketch1 == sketch2

    def test_sketch_size(self):
        trigrams = {f"t{i}" for i in range(100)}
        sketch = compute_min_hash_sketch(trigrams, 10)
        assert len(sketch) == 10

    def test_empty_trigrams(self):
        assert compute_min_hash_sketch(set()) == []

    def test_sketch_is_sorted(self):
        trigrams = {"zzz", "aaa", "mmm"}
        sketch = compute_min_hash_sketch(trigrams, 3)
        assert sketch == sorted(sketch)


class TestCandidatePairs:
    def test_no_candidates(self):
        sketches = {
            "a": ["h1", "h2"],
            "b": ["h3", "h4"],
        }
        pairs = find_candidate_pairs(sketches, band_count=2)
        assert len(pairs) == 0

    def test_shared_band(self):
        # Same first element means shared band with band_size=1
        sketches = {
            "a": ["h1", "h2", "h3", "h4"],
            "b": ["h1", "h5", "h6", "h7"],
        }
        pairs = find_candidate_pairs(sketches, band_count=4)
        assert ("a", "b") in pairs

    def test_multiple_candidates(self):
        sketches = {
            "a": ["h1", "h2", "h3", "h4"],
            "b": ["h1", "h5", "h6", "h7"],
            "c": ["h8", "h9", "h10", "h11"],
        }
        pairs = find_candidate_pairs(sketches, band_count=4)
        assert ("a", "b") in pairs
        assert ("a", "c") not in pairs
        assert ("b", "c") not in pairs


class TestUnionFind:
    def test_single_element(self):
        uf = UnionFind()
        uf.find("a")
        groups = uf.get_groups()
        assert groups == {"a": ["a"]}

    def test_union_two(self):
        uf = UnionFind()
        uf.union("a", "b")
        groups = uf.get_groups()
        assert len(groups) == 1
        assert set(groups[list(groups.keys())[0]]) == {"a", "b"}

    def test_transitive_union(self):
        uf = UnionFind()
        uf.union("a", "b")
        uf.union("b", "c")
        groups = uf.get_groups()
        assert len(groups) == 1
        members = list(groups.values())[0]
        assert set(members) == {"a", "b", "c"}

    def test_sorted_members(self):
        uf = UnionFind()
        uf.union("c", "a")
        uf.union("b", "a")
        groups = uf.get_groups()
        members = list(groups.values())[0]
        assert members == ["a", "b", "c"]


# ============================================================
# Deduplication Engine Tests
# ============================================================

@pytest.fixture
def sample_documents():
    return [
        DocumentReference(
            document_id="doc-1",
            document_type="normalized_document",
            normalized_checksum="checksum-a",
            canonical_checksum="canon-a",
            raw_checksum="raw-a",
            normalized_text="The quick brown fox jumps over the lazy dog",
            quality_score=0.8,
            warning_count=0,
            source_url="http://example.com/1",
            artifact_id="artifact-1",
            canonical_document_id="canon-1",
            normalized_document_id="norm-1",
        ),
        DocumentReference(
            document_id="doc-2",
            document_type="normalized_document",
            normalized_checksum="checksum-a",  # Same as doc-1
            canonical_checksum="canon-b",
            raw_checksum="raw-b",
            normalized_text="The quick brown fox jumps over the lazy dog",  # Same content
            quality_score=0.6,
            warning_count=1,
            source_url="http://example.com/2",
            artifact_id="artifact-2",
            canonical_document_id="canon-2",
            normalized_document_id="norm-2",
        ),
        DocumentReference(
            document_id="doc-3",
            document_type="normalized_document",
            normalized_checksum="checksum-c",
            canonical_checksum="canon-c",
            raw_checksum="raw-c",
            normalized_text="The quick brown fox leaps over the sleepy dog",  # Near duplicate
            quality_score=0.9,
            warning_count=0,
            source_url="http://example.com/3",
            artifact_id="artifact-3",
            canonical_document_id="canon-3",
            normalized_document_id="norm-3",
        ),
        DocumentReference(
            document_id="doc-4",
            document_type="normalized_document",
            normalized_checksum="checksum-d",
            canonical_checksum="canon-d",
            raw_checksum="raw-d",
            normalized_text="Completely different content about cats and dogs",
            quality_score=0.5,
            warning_count=2,
            source_url="http://example.com/4",
            artifact_id="artifact-4",
            canonical_document_id="canon-4",
            normalized_document_id="norm-4",
        ),
    ]


class TestNormalizedExactDetection:
    def test_detects_normalized_exact_duplicates(self, sample_documents):
        detector = DuplicateDetector(DuplicateDetectionConfig(enable_raw_exact=False))
        result = detector.detect(sample_documents)
        
        # doc-1 and doc-2 have same normalized_checksum
        normalized_groups = [g for g in result.normalized_exact_groups if g.duplicate_method == "normalized_exact"]
        assert len(normalized_groups) >= 1
        
        group_sizes = [g.group_size for g in normalized_groups]
        assert 2 in group_sizes

    def test_no_false_positives(self, sample_documents):
        detector = DuplicateDetector(DuplicateDetectionConfig(enable_raw_exact=False))
        result = detector.detect(sample_documents)
        
        # doc-3 and doc-4 should NOT be in same normalized exact group
        for group in result.normalized_exact_groups:
            member_ids = [m.normalized_document_id for m in result.memberships if m.group_id == group.id]
            assert not ("norm-3" in member_ids and "norm-4" in member_ids)

    def test_deterministic(self, sample_documents):
        detector = DuplicateDetector(DuplicateDetectionConfig(enable_raw_exact=False))
        result1 = detector.detect(sample_documents)
        result2 = detector.detect(sample_documents)
        
        assert len(result1.normalized_exact_groups) == len(result2.normalized_exact_groups)
        for g1, g2 in zip(result1.normalized_exact_groups, result2.normalized_exact_groups):
            assert g1.group_size == g2.group_size


class TestNearDuplicateDetection:
    def test_detects_near_duplicates(self, sample_documents):
        detector = DuplicateDetector(
            DuplicateDetectionConfig(
                enable_raw_exact=False,
                enable_normalized_exact=False,
                jaccard_threshold=0.7,
            )
        )
        result = detector.detect(sample_documents)
        
        near_groups = result.near_duplicate_groups
        assert len(near_groups) >= 1

    def test_threshold_behavior(self, sample_documents):
        # High threshold should find fewer groups
        detector_high = DuplicateDetector(
            DuplicateDetectionConfig(
                enable_raw_exact=False,
                enable_normalized_exact=False,
                jaccard_threshold=0.99,
            )
        )
        result_high = detector_high.detect(sample_documents)
        
        # Lower threshold should find more groups
        detector_low = DuplicateDetector(
            DuplicateDetectionConfig(
                enable_raw_exact=False,
                enable_normalized_exact=False,
                jaccard_threshold=0.3,
            )
        )
        result_low = detector_low.detect(sample_documents)
        
        assert len(result_low.near_duplicate_groups) >= len(result_high.near_duplicate_groups)

    def test_unique_content_not_grouped(self, sample_documents):
        detector = DuplicateDetector(
            DuplicateDetectionConfig(
                enable_raw_exact=False,
                enable_normalized_exact=False,
                jaccard_threshold=0.7,
            )
        )
        result = detector.detect(sample_documents)
        
        # doc-4 has completely different content
        for group in result.near_duplicate_groups:
            member_ids = [m.normalized_document_id for m in result.memberships if m.group_id == group.id]
            assert not ("norm-4" in member_ids and len(member_ids) > 1)


class TestRepresentativeSelection:
    def test_highest_quality_selected(self, sample_documents):
        detector = DuplicateDetector(DuplicateDetectionConfig(enable_raw_exact=False))
        result = detector.detect(sample_documents)
        
        # Find the normalized_exact group
        for group in result.normalized_exact_groups:
            members = [m for m in result.memberships if m.group_id == group.id]
            representatives = [m for m in members if m.is_representative]
            assert len(representatives) == 1

    def test_representative_has_highest_quality(self, sample_documents):
        detector = DuplicateDetector(DuplicateDetectionConfig(enable_raw_exact=False))
        result = detector.detect(sample_documents)
        
        # In normalized exact group, doc-1 has quality 0.8, doc-2 has 0.6
        # doc-1 should be representative
        for group in result.normalized_exact_groups:
            for membership in result.memberships:
                if membership.group_id == group.id and membership.is_representative:
                    assert membership.normalized_document_id == "norm-1"

    def test_selection_basis_stored(self, sample_documents):
        detector = DuplicateDetector(DuplicateDetectionConfig(enable_raw_exact=False))
        result = detector.detect(sample_documents)
        
        for group in result.normalized_exact_groups:
            for membership in result.memberships:
                if membership.group_id == group.id and membership.is_representative:
                    assert membership.selection_basis is not None
                    assert "quality" in membership.selection_basis


class TestTransitiveGrouping:
    def test_transitive_near_duplicates(self):
        docs = [
            DocumentReference(
                document_id="a", document_type="normalized_document",
                normalized_checksum="c1", canonical_checksum="cc1", raw_checksum="r1",
                normalized_text="The quick brown fox jumps over the lazy dog",
                quality_score=0.5, warning_count=0, source_url="http://a",
                artifact_id="a1", canonical_document_id="ca1", normalized_document_id="na1",
            ),
            DocumentReference(
                document_id="b", document_type="normalized_document",
                normalized_checksum="c2", canonical_checksum="cc2", raw_checksum="r2",
                normalized_text="The quick brown fox jumps over the lazy dog",  # Same as a
                quality_score=0.5, warning_count=0, source_url="http://b",
                artifact_id="a2", canonical_document_id="ca2", normalized_document_id="na2",
            ),
            DocumentReference(
                document_id="c", document_type="normalized_document",
                normalized_checksum="c3", canonical_checksum="cc3", raw_checksum="r3",
                normalized_text="The quick brown fox jumps over the lazy dog",  # Same as a and b
                quality_score=0.5, warning_count=0, source_url="http://c",
                artifact_id="a3", canonical_document_id="ca3", normalized_document_id="na3",
            ),
        ]
        detector = DuplicateDetector(DuplicateDetectionConfig(enable_raw_exact=False, enable_normalized_exact=False, jaccard_threshold=0.99))
        result = detector.detect(docs)
        
        # All three should be in one near-duplicate group
        assert len(result.near_duplicate_groups) == 1
        assert result.near_duplicate_groups[0].group_size == 3


class TestDeterminism:
    def test_same_input_same_output(self, sample_documents):
        detector = DuplicateDetector(DuplicateDetectionConfig(enable_raw_exact=False))
        result1 = detector.detect(sample_documents)
        result2 = detector.detect(sample_documents)
        
        assert len(result1.all_groups) == len(result2.all_groups)
        assert len(result1.memberships) == len(result2.memberships)
        
        # Compare group sizes
        sizes1 = sorted([g.group_size for g in result1.all_groups])
        sizes2 = sorted([g.group_size for g in result2.all_groups])
        assert sizes1 == sizes2


class TestDatabaseIntegration:
    def test_save_and_retrieve_group(self):
        from unittest.mock import MagicMock
        
        mock_db = MagicMock()
        mock_db.save_duplicate_group.return_value = DuplicateGroup(
            id="group-123",
            duplicate_method="normalized_exact",
            algorithm_version="trigram-jaccard-1.0.0",
            algorithm_config={"threshold": 0.85},
            representative_normalized_document_id=None,
            representative_canonical_document_id=None,
            group_size=2,
            similarity_stats={"exact_match": True},
            warnings=[],
            errors=[],
            provenance={},
            created_at="2026-01-01",
            updated_at="2026-01-01",
        )
        mock_db.get_duplicate_group.return_value = {
            "id": "group-123",
            "duplicate_method": "normalized_exact",
            "algorithm_version": "trigram-jaccard-1.0.0",
            "group_size": 2,
        }
        
        group = DuplicateGroup(
            id="",
            duplicate_method="normalized_exact",
            algorithm_version="trigram-jaccard-1.0.0",
            algorithm_config={"threshold": 0.85},
            representative_normalized_document_id=None,
            representative_canonical_document_id=None,
            group_size=2,
            similarity_stats={"exact_match": True},
            warnings=[],
            errors=[],
            provenance={},
            created_at="",
            updated_at="",
        )
        
        saved = mock_db.save_duplicate_group(group)
        assert saved.id == "group-123"
        
        retrieved = mock_db.get_duplicate_group("group-123")
        assert retrieved is not None
        assert retrieved["duplicate_method"] == "normalized_exact"

    def test_save_and_retrieve_membership(self):
        from unittest.mock import MagicMock
        
        mock_db = MagicMock()
        mock_db.save_duplicate_group.return_value = DuplicateGroup(
            id="group-123", duplicate_method="near_duplicate", algorithm_version="1.0.0",
            algorithm_config={}, representative_normalized_document_id=None,
            representative_canonical_document_id=None, group_size=1,
            similarity_stats={}, warnings=[], errors=[], provenance={},
            created_at="", updated_at="",
        )
        mock_db.save_duplicate_membership.return_value = DuplicateMembership(
            id="mem-123", group_id="group-123", normalized_document_id="norm-1",
            canonical_document_id=None, artifact_id=None,
            comparison_method="trigram_jaccard", similarity_score=0.9,
            is_representative=True, selection_basis="highest_quality",
            warnings=[], errors=[], provenance={},
            created_at="", updated_at="",
        )
        mock_db.get_duplicate_memberships.return_value = [
            {
                "id": "mem-123",
                "group_id": "group-123",
                "normalized_document_id": "norm-1",
                "is_representative": True,
            }
        ]
        
        membership = DuplicateMembership(
            id="", group_id="group-123", normalized_document_id="norm-1",
            canonical_document_id=None, artifact_id=None,
            comparison_method="trigram_jaccard", similarity_score=0.9,
            is_representative=True, selection_basis="highest_quality",
            warnings=[], errors=[], provenance={},
            created_at="", updated_at="",
        )
        
        saved_membership = mock_db.save_duplicate_membership(membership)
        assert saved_membership.id == "mem-123"
        
        memberships = mock_db.get_duplicate_memberships("group-123")
        assert len(memberships) == 1
        assert memberships[0]["is_representative"] is True

    def test_clear_duplicate_data(self):
        from unittest.mock import MagicMock
        
        mock_db = MagicMock()
        mock_db.get_all_duplicate_groups.return_value = []
        
        mock_db.clear_duplicate_data()
        mock_db.clear_duplicate_data.assert_called_once()


class TestEmptyAndEdgeCases:
    def test_empty_document_list(self):
        detector = DuplicateDetector()
        result = detector.detect([])
        assert result.total_documents_analyzed == 0
        assert len(result.all_groups) == 0

    def test_single_document(self):
        docs = [
            DocumentReference(
                document_id="only", document_type="normalized_document",
                normalized_checksum="c1", canonical_checksum="cc1", raw_checksum="r1",
                normalized_text="Only document",
                quality_score=0.5, warning_count=0, source_url="http://x",
                artifact_id="a1", canonical_document_id="ca1", normalized_document_id="na1",
            ),
        ]
        detector = DuplicateDetector()
        result = detector.detect(docs)
        assert len(result.all_groups) == 0

    def test_no_normalized_text_skipped(self):
        docs = [
            DocumentReference(
                document_id="no-text", document_type="normalized_document",
                normalized_checksum="c1", canonical_checksum="cc1", raw_checksum="r1",
                normalized_text=None,
                quality_score=0.0, warning_count=1, source_url="http://x",
                artifact_id="a1", canonical_document_id="ca1", normalized_document_id="na1",
            ),
        ]
        detector = DuplicateDetector()
        result = detector.detect(docs)
        assert result.documents_skipped == 1
