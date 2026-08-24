"""Phase 2: Data inventory and profiling."""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from dataclasses import dataclass
from enum import Enum
from typing import Any

from data_fetcher.database import Database, DatabaseError
from data_fetcher.models import ArtifactCharacterization
from data_fetcher.phase2.discovery import DiscoveryConfig, FormatDiscovery, DiscoveryError
from data_fetcher.storage import MinioStorage, StorageError

logger = logging.getLogger(__name__)


class InventoryError(Exception):
    """Inventory-specific errors."""
    def __init__(self, category: str, message: str):
        self.category = category
        super().__init__(message)


class ArtifactAvailability(str, Enum):
    """Availability states for raw artifacts."""
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    CORRUPTED = "corrupted"
    UNSUPPORTED = "unsupported"
    CHARACTERIZATION_FAILED = "characterization_failed"


@dataclass
class InventoryConfig:
    """Configuration for data inventory."""
    characterization_version: str = "1.0.0"
    max_preview_bytes: int = 65536
    characterize_all: bool = True
    save_results: bool = True
    batch_size: int = 50


class DataInventory:
    """Build data inventory and profile artifacts."""

    def __init__(
        self,
        database: Database,
        discovery: FormatDiscovery,
        storage: MinioStorage | None = None,
        config: InventoryConfig | None = None,
    ) -> None:
        self.database = database
        self.discovery = discovery
        self.storage = storage
        self.config = config or InventoryConfig()

    def get_all_artifacts(self) -> list[dict[str, Any]]:
        """Retrieve all artifacts from database with provenance."""
        try:
            return self.database.get_all_artifacts()
        except DatabaseError as exc:
            raise InventoryError("database_error", f"Failed to retrieve artifacts: {exc}") from exc

    def get_artifact(self, artifact_id: str) -> dict[str, Any] | None:
        """Retrieve a single artifact by ID."""
        try:
            return self.database.get_artifact(artifact_id)
        except DatabaseError as exc:
            raise InventoryError("database_error", f"Failed to retrieve artifact: {exc}") from exc

    def _fetch_raw_data(self, artifact: dict[str, Any]) -> tuple[bytes, ArtifactAvailability]:
        """
        Fetch raw data from MinIO for an artifact.
        
        Returns:
            (raw_data, availability_state)
        """
        if not self.storage:
            raise InventoryError("storage_unavailable", "Storage backend not configured")
        try:
            raw_data = self.storage.get_object(artifact["object_key"])
            return raw_data, ArtifactAvailability.AVAILABLE
        except StorageError as exc:
            try:
                exists = self.storage.object_exists(artifact["object_key"])
                if not exists:
                    return b"", ArtifactAvailability.UNAVAILABLE
            except StorageError:
                pass
            raise InventoryError("storage_error", f"Failed to retrieve object: {exc}") from exc

    def characterize_artifact(self, artifact: dict[str, Any]) -> tuple[ArtifactCharacterization | None, ArtifactAvailability]:
        """
        Characterize a single artifact.
        
        Returns:
            (characterization, availability_state)
        """
        try:
            raw_data, availability = self._fetch_raw_data(artifact)
        except InventoryError as exc:
            logger.error("Failed to fetch raw data for artifact %s: %s", artifact["id"], exc)
            if exc.category == "storage_error":
                if self.storage:
                    try:
                        exists = self.storage.object_exists(artifact["object_key"])
                        if not exists:
                            return None, ArtifactAvailability.UNAVAILABLE
                    except StorageError:
                        pass
                return None, ArtifactAvailability.CORRUPTED
            return None, ArtifactAvailability.CHARACTERIZATION_FAILED

        if availability == ArtifactAvailability.UNAVAILABLE:
            return None, ArtifactAvailability.UNAVAILABLE

        try:
            characterization = self.discovery.characterize(
                raw_data=raw_data,
                content_type=artifact.get("content_type"),
                url=artifact.get("resource_url"),
                artifact_id=artifact["id"],
                config={
                    "characterization_version": self.config.characterization_version,
                    "max_preview_bytes": self.config.max_preview_bytes,
                },
            )
            return characterization, ArtifactAvailability.AVAILABLE
        except DiscoveryError as exc:
            logger.error("Discovery failed for artifact %s: %s", artifact["id"], exc)
            return None, ArtifactAvailability.CHARACTERIZATION_FAILED
        except Exception as exc:
            logger.error("Unexpected error during characterization of artifact %s: %s", artifact["id"], exc)
            return None, ArtifactAvailability.CHARACTERIZATION_FAILED

    def save_characterization(self, characterization: ArtifactCharacterization) -> ArtifactCharacterization:
        """Persist characterization to database."""
        try:
            return self.database.save_artifact_characterization(characterization)
        except DatabaseError as exc:
            raise InventoryError("database_error", f"Failed to save characterization: {exc}") from exc

    def build_inventory(self) -> dict[str, Any]:
        """
        Build complete inventory report.
        
        Returns:
            Inventory report dict with global stats and per-artifact details
        """
        artifacts = self.get_all_artifacts()
        characterizations: list[ArtifactCharacterization] = []
        availability_counts: dict[str, int] = {state.value: 0 for state in ArtifactAvailability}
        failed_artifacts: list[dict[str, Any]] = []
        format_conflicts: list[dict[str, Any]] = []

        for artifact in artifacts:
            characterization, availability = self.characterize_artifact(artifact)
            availability_counts[availability.value] += 1
            
            if characterization:
                if self.config.save_results:
                    try:
                        self.save_characterization(characterization)
                    except InventoryError as exc:
                        logger.error("Failed to save characterization for %s: %s", artifact["id"], exc)
                        failed_artifacts.append({
                            "artifact_id": artifact["id"],
                            "error": str(exc),
                            "category": exc.category,
                            "availability": availability.value,
                        })
                        continue
                characterizations.append(characterization)
                
                # Check for MIME/detected format conflict
                declared_mime = artifact.get("content_type")
                detected_format = characterization.detected_format
                if declared_mime and detected_format:
                    declared_norm = declared_mime.lower().split(";")[0].strip()
                    detected_norm = detected_format.lower().replace("_", "").replace("-", "")
                    mime_to_format = {
                        "text/html": "html",
                        "application/xhtml+xml": "html",
                        "text/plain": "plaintext",
                        "text/markdown": "markdown",
                        "application/json": "json",
                        "application/xml": "xml",
                        "text/xml": "xml",
                        "text/csv": "csv",
                        "application/csv": "csv",
                    }
                    expected_format = mime_to_format.get(declared_norm)
                    if expected_format and expected_format.replace("_", "").replace("-", "") != detected_norm:
                        format_conflicts.append({
                            "artifact_id": artifact["id"],
                            "declared_mime": declared_norm,
                            "detected_format": detected_format,
                            "confidence": characterization.format_confidence,
                        })
            else:
                failed_artifacts.append({
                    "artifact_id": artifact["id"],
                    "error": f"Characterization unavailable: {availability.value}",
                    "category": availability.value,
                    "availability": availability.value,
                })

        # Compute global statistics
        stats = self._compute_stats(artifacts, characterizations)

        return {
            "characterization_version": self.config.characterization_version,
            "total_artifacts": len(artifacts),
            "characterized_count": len(characterizations),
            "failed_count": len(failed_artifacts),
            "availability_counts": availability_counts,
            "raw_available": availability_counts.get(ArtifactAvailability.AVAILABLE.value, 0),
            "raw_unavailable": availability_counts.get(ArtifactAvailability.UNAVAILABLE.value, 0),
            "global_statistics": stats,
            "format_distribution": self._format_distribution(characterizations),
            "mime_type_distribution": self._mime_distribution(artifacts),
            "domain_distribution": self._domain_distribution(artifacts),
            "size_distribution": self._size_distribution(artifacts),
            "encoding_distribution": self._encoding_distribution(characterizations),
            "structural_type_distribution": self._structural_type_distribution(characterizations),
            "extraction_suitability_distribution": self._extraction_suitability_distribution(characterizations),
            "format_conflicts": format_conflicts,
            "warnings_summary": self._warnings_summary(characterizations),
            "errors_summary": self._errors_summary(failed_artifacts),
            "characterization_coverage": len(characterizations) / max(len(artifacts), 1),
            "failed_artifacts": failed_artifacts[:20],  # Limit for readability
        }

    def _compute_stats(self, artifacts: list[dict], characterizations: list[ArtifactCharacterization]) -> dict[str, Any]:
        """Compute global statistics."""
        total_bytes = sum(a.get("size_bytes", 0) for a in artifacts)
        total_characters = sum(c.content_statistics.get("character_count", 0) for c in characterizations)
        return {
            "total_bytes": total_bytes,
            "total_characters_estimated": total_characters,
            "average_artifact_bytes": total_bytes / max(len(artifacts), 1),
            "characterized_artifacts": len(characterizations),
        }

    def _format_distribution(self, characterizations: list[ArtifactCharacterization]) -> dict[str, int]:
        return dict(Counter(c.detected_format for c in characterizations if c.detected_format))

    def _mime_distribution(self, artifacts: list[dict]) -> dict[str, int]:
        mime_types = [a.get("content_type", "unknown") for a in artifacts if a.get("content_type")]
        if not mime_types:
            mime_types = ["unknown"] * len(artifacts)
        return dict(Counter(mime_types))

    def _domain_distribution(self, artifacts: list[dict]) -> dict[str, int]:
        return dict(Counter(a.get("domain", "unknown") for a in artifacts))

    def _size_distribution(self, artifacts: list[dict]) -> dict[str, int]:
        buckets: dict[str, int] = {
            "<1KB": 0,
            "1KB-10KB": 0,
            "10KB-100KB": 0,
            "100KB-1MB": 0,
            ">1MB": 0,
        }
        for a in artifacts:
            size = a.get("size_bytes", 0)
            if size < 1024:
                buckets["<1KB"] += 1
            elif size < 10240:
                buckets["1KB-10KB"] += 1
            elif size < 102400:
                buckets["10KB-100KB"] += 1
            elif size < 1048576:
                buckets["100KB-1MB"] += 1
            else:
                buckets[">1MB"] += 1
        return buckets

    def _encoding_distribution(self, characterizations: list[ArtifactCharacterization]) -> dict[str, int]:
        return dict(Counter(c.encoding for c in characterizations if c.encoding))

    def _structural_type_distribution(self, characterizations: list[ArtifactCharacterization]) -> dict[str, int]:
        return dict(Counter(c.structural_type for c in characterizations if c.structural_type))

    def _extraction_suitability_distribution(self, characterizations: list[ArtifactCharacterization]) -> dict[str, int]:
        return dict(Counter(c.extraction_suitability for c in characterizations if c.extraction_suitability))

    def _warnings_summary(self, characterizations: list[ArtifactCharacterization]) -> list[dict[str, Any]]:
        warning_counts: dict[str, int] = defaultdict(int)
        for c in characterizations:
            for w in c.warnings:
                warning_counts[w] += 1
        return [{"warning": k, "count": v} for k, v in sorted(warning_counts.items(), key=lambda x: -x[1])]

    def _errors_summary(self, failed_artifacts: list[dict]) -> list[dict[str, Any]]:
        error_counts: dict[str, int] = defaultdict(int)
        for f in failed_artifacts:
            error_counts[f.get("category", "unknown")] += 1
        return [{"error": k, "count": v} for k, v in sorted(error_counts.items(), key=lambda x: -x[1])]

    def inventory(self) -> dict[str, Any]:
        """
        Main entry point for inventory.
        
        Returns:
            Complete inventory report
        """
        logger.info("Starting data inventory...")
        report = self.build_inventory()
        logger.info(
            "Inventory complete: %d artifacts, %d characterized",
            report["total_artifacts"],
            report["characterized_count"],
        )
        return report
