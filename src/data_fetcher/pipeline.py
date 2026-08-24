"""
Configurable pipeline engine that composes plugins.
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from data_fetcher.plugin_base import (
    PluginContext,
    FetcherPlugin,
    ExtractorPlugin,
    StoragePlugin,
    NormalizerPlugin,
    DedupePlugin,
    ExporterPlugin,
    FetchError,
    ExtractionError,
    StorageError,
    NormalizationError,
    DedupeError,
    ExportError,
)
from data_fetcher.plugin_manager import PluginManager

logger = logging.getLogger(__name__)


@dataclass
class PipelineConfig:
    """Configuration for a data pipeline."""
    # Plugin selection
    fetcher: str = "requests"
    extractor: str = "heuristic"
    storage: str = "postgres_minio"
    normalizer: str = "standard"
    dedupe: str = "trigram_jaccard"
    exporter: str = "jsonl"

    # Pipeline-level settings
    batch_size: int = 100
    parallel_workers: int = 4
    fail_fast: bool = False
    continue_on_error: bool = True

    # Plugin-specific configuration
    plugin_config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineResult:
    """Result of a pipeline execution."""
    total_urls: int
    successful: int
    failed: int
    export: Optional[Dict[str, Any]] = None
    results: List[Dict[str, Any]] = field(default_factory=list)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    elapsed_seconds: float = 0.0


class DataPipeline:
    """
    Configurable data pipeline that orchestrates plugins.

    The pipeline runs: Fetch → Extract → Store → Normalize → Dedupe → Export
    """

    def __init__(self, config: PipelineConfig, plugin_manager: PluginManager):
        self.config = config
        self.pm = plugin_manager

        self.fetcher_cls: Optional[type] = None
        self.extractor_cls: Optional[type] = None
        self.storage_cls: Optional[type] = None
        self.normalizer_cls: Optional[type] = None
        self.dedupe_cls: Optional[type] = None
        self.exporter_cls: Optional[type] = None

        self._init_plugins()

    def _init_plugins(self) -> None:
        """Initialize plugin classes from configuration."""
        self.fetcher_cls = self.pm.get_plugin(self.config.fetcher)
        self.extractor_cls = self.pm.get_plugin(self.config.extractor)
        self.storage_cls = self.pm.get_plugin(self.config.storage)
        self.normalizer_cls = self.pm.get_plugin(self.config.normalizer)
        self.dedupe_cls = self.pm.get_plugin(self.config.dedupe)
        self.exporter_cls = self.pm.get_plugin(self.config.exporter)

    def _create_context(self) -> PluginContext:
        """Create a plugin context from configuration."""
        from data_fetcher.plugin_base import PluginContext
        return PluginContext(
            config=self.config.plugin_config,
            db_session=None,
            storage_client=None,
            logger=logger,
        )

    def _instantiate_plugin(self, plugin_cls):
        """Instantiate a plugin and initialize it."""
        instance = plugin_cls()
        return instance

    def run(self, urls: List[str], context: Optional[PluginContext] = None) -> PipelineResult:
        """
        Execute the pipeline on a list of URLs.

        Args:
            urls: List of URLs to process
            context: Optional plugin context (created if not provided)

        Returns:
            PipelineResult: Execution results
        """
        start_time = time.time()
        started_at = datetime.utcnow()

        if context is None:
            context = self._create_context()

        # Instantiate plugins
        fetcher = self._instantiate_plugin(self.fetcher_cls)
        extractor = self._instantiate_plugin(self.extractor_cls)
        storage = self._instantiate_plugin(self.storage_cls)
        normalizer = self._instantiate_plugin(self.normalizer_cls)
        dedupe = self._instantiate_plugin(self.dedupe_cls)
        exporter = self._instantiate_plugin(self.exporter_cls)

        # Initialize plugins
        fetcher.initialize(context)
        extractor.initialize(context)
        storage.initialize(context)
        normalizer.initialize(context)
        dedupe.initialize(context)
        exporter.initialize(context)

        results = []
        successful = 0
        failed = 0

        for url in urls:
            try:
                # 1. Fetch
                logger.info(f"Fetching: {url}")
                fetch_result = fetcher.fetch(url, context)

                # 2. Extract
                logger.info(f"Extracting: {url}")
                extraction_result = extractor.extract(fetch_result.body, context)

                # 3. Store raw artifact
                logger.info(f"Storing: {url}")
                storage_metadata = {
                    "url": url,
                    "normalized_url": fetch_result.normalized_url,
                    "domain": fetch_result.domain,
                    "content_type": fetch_result.content_type,
                    "status_code": fetch_result.status_code,
                }
                storage_result = storage.save(
                    fetch_result.body,
                    {**storage_metadata, **extraction_result.metadata},
                    context
                )

                # 4. Normalize
                logger.info(f"Normalizing: {url}")
                normalization_result = normalizer.normalize(
                    extraction_result.text,
                    context
                )

                # 5. Store normalized document (tracking for dedupe)
                doc_entry = {
                    "url": url,
                    "artifact_id": storage_result.artifact_id,
                    "text": normalization_result.text,
                    "checksum": normalization_result.checksum,
                    "word_count": normalization_result.word_count,
                    "language": normalization_result.language,
                    "quality_signals": normalization_result.quality_signals,
                    "extraction": {
                        "title": extraction_result.title,
                        "links": extraction_result.links,
                        "headings": extraction_result.headings,
                    },
                    "status": "success",
                }
                results.append(doc_entry)
                successful += 1

            except (FetchError, ExtractionError, StorageError,
                    NormalizationError) as e:
                logger.error(f"Error processing {url}: {e}")
                if self.config.fail_fast:
                    raise
                results.append({
                    "url": url,
                    "status": "failed",
                    "error": str(e),
                })
                failed += 1

        # 6. Deduplicate (batch)
        if results and successful > 0:
            try:
                logger.info("Running deduplication...")
                dedupe_result = dedupe.deduplicate(results, context)

                # Update results with dedupe info
                unique_set = set(dedupe_result.unique_documents)
                for result in results:
                    if result["status"] == "success":
                        result["is_duplicate"] = result.get("artifact_id") not in unique_set

                # Build dataset from unique documents
                dataset = [
                    r for r in results
                    if r["status"] == "success" and not r.get("is_duplicate", False)
                ]

                # 7. Export
                logger.info("Exporting dataset...")
                export_config = self.config.plugin_config.get("exporter", {})
                export_result = exporter.export(dataset, export_config, context)

                export_info = {
                    "output_path": export_result.output_path,
                    "format": export_result.format,
                    "record_count": export_result.record_count,
                    "size_bytes": export_result.size_bytes,
                    "manifest": export_result.manifest,
                }

            except (DedupeError, ExportError) as e:
                logger.error(f"Error in dedupe/export: {e}")
                export_info = {"error": str(e)}
        else:
            export_info = {"record_count": 0, "note": "No successful documents"}

        elapsed = time.time() - start_time

        return PipelineResult(
            total_urls=len(urls),
            successful=successful,
            failed=failed,
            export=export_info,
            results=results,
            started_at=started_at,
            completed_at=datetime.utcnow(),
            elapsed_seconds=elapsed,
        )
