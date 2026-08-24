"""P2.5 realistic deduplication acceptance tests."""

import time
import pytest

from data_fetcher.phase2.deduplication import DuplicateDetector, DuplicateDetectionConfig, DocumentReference
from tests.test_phase2.fixtures.p25_corpus import generate_corpus, get_ground_truth


@pytest.fixture(scope="module")
def corpus():
    return generate_corpus()


@pytest.fixture(scope="module")
def ground_truth():
    return get_ground_truth()


def _run_deduplication(corpus, threshold):
    """Run deduplication on corpus at given threshold and return results."""
    docs = []
    for doc in corpus:
        docs.append(DocumentReference(
            document_id=doc["id"],
            document_type="artifact",
            normalized_checksum=None,
            canonical_checksum=None,
            raw_checksum=None,
            normalized_text=doc["text"],
            quality_score=doc["quality_score"],
            warning_count=0,
            source_url=doc["source_url"],
            artifact_id=doc["id"],
            canonical_document_id=None,
            normalized_document_id=None,
        ))

    config = DuplicateDetectionConfig(jaccard_threshold=threshold)
    detector = DuplicateDetector(config)
    result = detector.detect(docs)
    return result


def _calculate_metrics(result, ground_truth, corpus):
    """Calculate precision, recall, F1 against ground truth."""
    # Build predicted groups from memberships
    predicted_groups = {}
    for membership in result.memberships:
        gid = membership.group_id
        doc_id = membership.normalized_document_id or membership.canonical_document_id or membership.artifact_id
        if doc_id:
            predicted_groups.setdefault(gid, set()).add(doc_id)

    # Build predicted unique set
    all_doc_ids = {doc["id"] for doc in corpus}
    grouped_doc_ids = set()
    for members in predicted_groups.values():
        grouped_doc_ids.update(members)
    predicted_unique = all_doc_ids - grouped_doc_ids

    # Calculate TP, FP, FN at pair level
    expected_pairs = set()
    for group in ground_truth["expected_groups"]:
        members = group["document_ids"]
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                expected_pairs.add((min(members[i], members[j]), max(members[i], members[j])))

    predicted_pairs = set()
    for members in predicted_groups.values():
        members_list = sorted(members)
        for i in range(len(members_list)):
            for j in range(i + 1, len(members_list)):
                predicted_pairs.add((min(members_list[i], members_list[j]), max(members_list[i], members_list[j])))

    tp = len(expected_pairs & predicted_pairs)
    fp = len(predicted_pairs - expected_pairs)
    fn = len(expected_pairs - predicted_pairs)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "predicted_group_count": len(predicted_groups),
        "expected_group_count": len(ground_truth["expected_groups"]),
        "predicted_unique_count": len(predicted_unique),
        "expected_unique_count": len(ground_truth["expected_unique"]),
    }


class TestP25RealisticAcceptance:
    """P2.5 realistic deduplication acceptance tests."""

    def test_corpus_generation(self, corpus, ground_truth):
        """Verify corpus has exactly 100 documents."""
        assert len(corpus) == 100
        assert len(ground_truth["expected_groups"]) > 0
        assert len(ground_truth["expected_unique"]) > 0

    @pytest.mark.parametrize("threshold", [0.80, 0.85, 0.90, 0.95])
    def test_dedup_metrics_at_threshold(self, corpus, ground_truth, threshold):
        """Run deduplication at multiple thresholds and measure metrics."""
        start = time.time()
        result = _run_deduplication(corpus, threshold)
        elapsed = time.time() - start

        metrics = _calculate_metrics(result, ground_truth, corpus)

        print(f"\nThreshold {threshold}:")
        print(f"  Precision: {metrics['precision']:.3f}")
        print(f"  Recall: {metrics['recall']:.3f}")
        print(f"  F1: {metrics['f1']:.3f}")
        print(f"  TP={metrics['tp']}, FP={metrics['fp']}, FN={metrics['fn']}")
        print(f"  Groups: predicted={metrics['predicted_group_count']}, expected={metrics['expected_group_count']}")
        print(f"  Unique: predicted={metrics['predicted_unique_count']}, expected={metrics['expected_unique_count']}")
        print(f"  Runtime: {elapsed:.3f}s")

        # At 0.85, we expect reasonable precision/recall
        if threshold == 0.85:
            assert metrics["precision"] >= 0.60, f"Precision too low at 0.85: {metrics['precision']}"
            assert metrics["recall"] >= 0.60, f"Recall too low at 0.85: {metrics['recall']}"

    def test_transitive_clustering(self, corpus, ground_truth):
        """Test A~B, B~C, A not ~ C transitive behavior."""
        result = _run_deduplication(corpus, 0.85)

        trans_docs = ground_truth["transitive_chain_docs"]
        # Find which group each transitive doc is in
        doc_to_group = {}
        for membership in result.memberships:
            doc_id = membership.normalized_document_id or membership.canonical_document_id or membership.artifact_id
            if doc_id:
                doc_to_group[doc_id] = membership.group_id

        # trans_a and trans_b should be in same group
        assert doc_to_group.get("trans_a") == doc_to_group.get("trans_b"), "trans_a and trans_b should be grouped"
        # trans_c should be alone or in different group
        assert doc_to_group.get("trans_c") != doc_to_group.get("trans_a"), "trans_c should NOT be grouped with trans_a"

        print(f"\nTransitive test: trans_a={doc_to_group.get('trans_a')}, trans_b={doc_to_group.get('trans_b')}, trans_c={doc_to_group.get('trans_c')}")

    def test_deterministic_rerun(self, corpus):
        """Verify deduplication produces identical results on rerun."""
        result1 = _run_deduplication(corpus, 0.85)
        result2 = _run_deduplication(corpus, 0.85)

        groups1 = sorted([g.id for g in result1.all_groups])
        groups2 = sorted([g.id for g in result2.all_groups])
        assert groups1 == groups2, "Deduplication must be deterministic"

        members1 = sorted([sorted([m.normalized_document_id or m.canonical_document_id or m.artifact_id for m in result1.memberships if (m.normalized_document_id or m.canonical_document_id or m.artifact_id) in [doc["id"] for doc in corpus]]) for g in result1.all_groups])
        members2 = sorted([sorted([m.normalized_document_id or m.canonical_document_id or m.artifact_id for m in result2.memberships if (m.normalized_document_id or m.canonical_document_id or m.artifact_id) in [doc["id"] for doc in corpus]]) for g in result2.all_groups])
        assert members1 == members2, "Duplicate members must be deterministic"
