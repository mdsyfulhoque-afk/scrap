"""DSE Acceptance Dataset Builder (P2.6-P2.8)

Lightweight dataset spec, builder, and exporter.
Uses psycopg directly to avoid import path issues in acceptance scripts.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import psycopg
from psycopg.rows import class_row

logger = logging.getLogger(__name__)

POSTGRES_DSN = (
    f"postgresql://{os.environ.get('POSTGRES_USER', 'datafetcher')}:"
    f"{os.environ.get('POSTGRES_PASSWORD', 'DataFetcher-Postgres-2026!')}@"
    f"{os.environ.get('POSTGRES_HOST', 'localhost')}:"
    f"{os.environ.get('POSTGRES_PORT', '5432')}/"
    f"{os.environ.get('POSTGRES_DATABASE', 'data_catalog')}"
)


@dataclass
class DatasetSpec:
    name: str
    description: str
    languages: list[str]
    formats: list[str]
    min_words: int = 0
    max_words: int = 100000
    required_fields: list[str] = field(default_factory=lambda: ["source_url", "normalized_text"])
    deduplicate: bool = True
    output_format: str = "jsonl"
    output_fields: list[str] = field(default_factory=lambda: [
        "source_url",
        "title",
        "normalized_text",
        "normalized_checksum",
        "word_count",
        "language",
        "artifact_id",
        "canonical_document_id",
        "normalized_document_id",
    ])


@dataclass
class CandidateRecord:
    artifact_id: str
    canonical_document_id: str
    normalized_document_id: str
    source_url: str
    title: str
    normalized_text: str
    normalized_checksum: str
    word_count: int
    language: str
    quality_signals: dict
    raw_checksum: str
    canonical_checksum: str


@dataclass
class AcceptanceDecision:
    accepted: bool
    reason: str
    record: CandidateRecord | None = None


def load_spec() -> DatasetSpec:
    return DatasetSpec(
        name="dse_market_data",
        description="Dhaka Stock Exchange market data pages (acceptance run 2026-08-19)",
        languages=["en"],
        formats=["html"],
        min_words=100,
        max_words=50000,
        required_fields=["source_url", "title", "normalized_text"],
        deduplicate=True,
        output_format="jsonl",
    )


def fetch_candidates() -> list[CandidateRecord]:
    candidates = []
    with psycopg.connect(POSTGRES_DSN, autocommit=False) as conn:
        with conn.cursor(row_factory=class_row(dict)) as cur:
            cur.execute("""
                SELECT 
                    a.id as artifact_id,
                    cd.id as canonical_document_id,
                    nd.id as normalized_document_id,
                    r.url as source_url,
                    cd.canonical_checksum,
                    a.checksum_sha256 as raw_checksum,
                    nd.normalized_checksum,
                    nd.normalized_text,
                    nd.quality_signals,
                    cd.provenance->>'title' as title
                FROM normalized_documents nd
                JOIN canonical_documents cd ON nd.canonical_document_id = cd.id
                JOIN artifacts a ON cd.artifact_id = a.id
                JOIN fetches f ON a.fetch_id = f.id
                JOIN resources r ON f.resource_id = r.id
                WHERE nd.normalized_text IS NOT NULL
                  AND LENGTH(nd.normalized_text) > 0
                ORDER BY nd.created_at
            """)
            for row in cur.fetchall():
                qs = row.get("quality_signals") or {}
                tm = qs.get("text_metrics", {})
                wc = tm.get("word_count", 0)
                lang = qs.get("language", {}).get("language", "unknown")
                title = row.get("title") or ""
                candidates.append(CandidateRecord(
                    artifact_id=row["artifact_id"],
                    canonical_document_id=row["canonical_document_id"],
                    normalized_document_id=row["normalized_document_id"],
                    source_url=row["source_url"],
                    title=title,
                    normalized_text=row["normalized_text"],
                    normalized_checksum=row["normalized_checksum"],
                    word_count=wc,
                    language=lang,
                    quality_signals=qs,
                    raw_checksum=row["raw_checksum"],
                    canonical_checksum=row["canonical_checksum"],
                ))
    return candidates


def evaluate_candidate(candidate: CandidateRecord, spec: DatasetSpec) -> AcceptanceDecision:
    reasons = []
    if not candidate.source_url:
        reasons.append("missing source_url")
    if not candidate.normalized_text or not candidate.normalized_text.strip():
        reasons.append("empty normalized_text")
    if spec.languages and candidate.language not in spec.languages:
        reasons.append(f"language '{candidate.language}' not in {spec.languages}")
    if candidate.word_count < spec.min_words:
        reasons.append(f"word_count {candidate.word_count} < min_words {spec.min_words}")
    if candidate.word_count > spec.max_words:
        reasons.append(f"word_count {candidate.word_count} > max_words {spec.max_words}")
    if reasons:
        return AcceptanceDecision(accepted=False, reason="; ".join(reasons), record=candidate)
    return AcceptanceDecision(accepted=True, reason="accepted", record=candidate)


def build_dataset(candidates: list[CandidateRecord], spec: DatasetSpec) -> tuple[list[dict], list[AcceptanceDecision]]:
    accepted = []
    decisions = []
    seen_checksums = set()
    for candidate in candidates:
        decision = evaluate_candidate(candidate, spec)
        decisions.append(decision)
        if not decision.accepted:
            continue
        if spec.deduplicate and candidate.normalized_checksum in seen_checksums:
            decision.reason = f"duplicate normalized_checksum {candidate.normalized_checksum[:16]}..."
            decision.accepted = False
            continue
        seen_checksums.add(candidate.normalized_checksum)
        record = {}
        for field in spec.output_fields:
            if hasattr(candidate, field):
                record[field] = getattr(candidate, field)
            else:
                record[field] = None
        record["_provenance"] = {
            "artifact_id": candidate.artifact_id,
            "canonical_document_id": candidate.canonical_document_id,
            "normalized_document_id": candidate.normalized_document_id,
            "raw_checksum": candidate.raw_checksum,
            "canonical_checksum": candidate.canonical_checksum,
            "normalized_checksum": candidate.normalized_checksum,
        }
        accepted.append(record)
    return accepted, decisions


def export_jsonl(records: list[dict], path: Path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def export_manifest(records: list[dict], decisions: list[AcceptanceDecision], spec: DatasetSpec, path: Path) -> None:
    accepted_count = sum(1 for d in decisions if d.accepted)
    rejected_count = len(decisions) - accepted_count
    rejection_reasons = {}
    for d in decisions:
        if not d.accepted:
            key = d.reason.split(";")[0].strip()
            rejection_reasons[key] = rejection_reasons.get(key, 0) + 1
    manifest = {
        "dataset_name": spec.name,
        "description": spec.description,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "spec": {
            "languages": spec.languages,
            "formats": spec.formats,
            "min_words": spec.min_words,
            "max_words": spec.max_words,
            "deduplicate": spec.deduplicate,
        },
        "statistics": {
            "total_candidates": len(decisions),
            "accepted": accepted_count,
            "rejected": rejected_count,
            "rejection_reasons": rejection_reasons,
        },
        "output": {
            "format": spec.output_format,
            "record_count": len(records),
            "fields": spec.output_fields,
        },
        "source_urls": list({r.get("source_url") for r in records if r.get("source_url")}),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False, default=str)


def export_statistics(records: list[dict], decisions: list[AcceptanceDecision], path: Path) -> None:
    accepted_records = [d.record for d in decisions if d.accepted and d.record]
    word_counts = [r.word_count for r in accepted_records] if accepted_records else []
    languages = [r.language for r in accepted_records] if accepted_records else []
    stats = {
        "total_records": len(records),
        "accepted_records": len(accepted_records),
        "rejected_records": len(decisions) - len(accepted_records),
        "word_count": {
            "min": min(word_counts) if word_counts else 0,
            "max": max(word_counts) if word_counts else 0,
            "mean": round(sum(word_counts) / len(word_counts), 2) if word_counts else 0,
        },
        "language_distribution": {lang: languages.count(lang) for lang in set(languages)} if languages else {},
        "source_domains": list({
            r.source_url.split("/")[2] if len(r.source_url.split("/")) > 2 else r.source_url
            for r in accepted_records
        }) if accepted_records else [],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False, default=str)


def main() -> int:
    root = Path(__file__).resolve().parent.parent

    print("=" * 60)
    print("DSE ACCEPTANCE DATASET BUILDER (P2.6-P2.8)")
    print("=" * 60)
    print()

    spec = load_spec()
    print(f"Dataset spec: {spec.name}")
    print(f"Description: {spec.description}")
    print(f"Languages: {spec.languages}")
    print(f"Formats: {spec.formats}")
    print(f"Min words: {spec.min_words}")
    print(f"Deduplicate: {spec.deduplicate}")
    print()

    print("Fetching candidates from database...")
    candidates = fetch_candidates()
    print(f"Total candidates: {len(candidates)}")
    print()

    print("Building dataset...")
    records, decisions = build_dataset(candidates, spec)

    accepted = [d for d in decisions if d.accepted]
    rejected = [d for d in decisions if not d.accepted]

    print(f"Accepted: {len(accepted)}")
    print(f"Rejected: {len(rejected)}")
    print()

    for d in decisions:
        status = "ACCEPT" if d.accepted else "REJECT"
        url = d.record.source_url if d.record else "unknown"
        print(f"  [{status}] {url[:50]}... - {d.reason}")
    print()

    output_dir = root / "scripts" / "dse_output"
    output_dir.mkdir(exist_ok=True)

    dataset_path = output_dir / "dataset.jsonl"
    manifest_path = output_dir / "manifest.json"
    statistics_path = output_dir / "statistics.json"

    print("Exporting...")
    export_jsonl(records, dataset_path)
    export_manifest(records, decisions, spec, manifest_path)
    export_statistics(records, decisions, statistics_path)

    print(f"Dataset: {dataset_path} ({len(records)} records)")
    print(f"Manifest: {manifest_path}")
    print(f"Statistics: {statistics_path}")
    print()

    if records:
        print("Sample record:")
        sample = records[0]
        for key in spec.output_fields:
            if key in sample and sample[key]:
                val = str(sample[key])[:100]
                print(f"  {key}: {val}...")

    return 0


if __name__ == "__main__":
    sys.exit(main())
