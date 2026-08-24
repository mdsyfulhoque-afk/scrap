"""Core plugin infrastructure for the Data Fetcher acquisition pipeline.

This module defines:

* the pluggy project name and hook markers used throughout the plugin system,
* :class:`DataFetcherPlugin`, the base class every plugin must subclass,
* :class:`PluginInfo`, the metadata record returned when listing plugins, and
* the hook *specifications* (``data_fetcher_*``) that plugins may implement.

The existing implementation modules
(``data_fetcher.fetcher``, ``data_fetcher.phase2.extraction``,
``data_fetcher.storage``, ``data_fetcher.phase2.normalization``,
``data_fetcher.phase2.deduplication``) are wrapped by the concrete plugins so
that provenance-preserving behaviour is preserved.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import pluggy

#: pluggy project / hook namespace shared by every data_fetcher hook.
PLUGIN_PROJECT_NAME = "data_fetcher"

#: Entry-point group under which plugins register themselves in pyproject.toml.
PLUGIN_ENTRY_POINT_GROUP = "data_fetcher"

#: Marker used to declare hook *specifications*.
hookspec = pluggy.HookspecMarker(PLUGIN_PROJECT_NAME)

#: Marker used to declare hook *implementations* (on plugin objects).
hookimpl = pluggy.HookimplMarker(PLUGIN_PROJECT_NAME)


@dataclass
class PluginContext:
    """Runtime context passed to plugin methods."""

    config: dict[str, Any] = field(default_factory=dict)
    db_session: Any = None
    storage_client: Any = None
    logger: Any = None


@dataclass
class PluginInfo:
    """Metadata describing a single discovered plugin."""

    name: str
    stage: str
    version: str
    description: str = ""
    source: str = "builtin"

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "stage": self.stage,
            "version": self.version,
            "description": self.description,
            "source": self.source,
        }


class DataFetcherPlugin(ABC):
    """Base class every plugin must subclass.

    Subclasses declare the pipeline ``stage`` they implement (one of
    ``fetcher``, ``extractor``, ``storage``, ``normalizer``, ``dedupe`` or
    ``exporter``), a stable ``name`` and a ``version``. They optionally decorate
    methods with :func:`hookimpl` to provide the behaviour for that stage.
    """

    #: Stable identifier used when listing and selecting plugins.
    name: str = "base"
    #: Pipeline stage implemented by this plugin.
    stage: str = "base"
    #: Semantic version of the plugin implementation.
    version: str = "0.0.0"
    #: Human readable description.
    description: str = ""

    @abstractmethod
    def capabilities(self) -> dict[str, Any]:
        """Return a structured description of what this plugin can do."""
        raise NotImplementedError

    def get_info(self) -> PluginInfo:
        """Return the :class:`PluginInfo` metadata record for this plugin."""
        return PluginInfo(
            name=self.name,
            stage=self.stage,
            version=self.version,
            description=self.description,
            source=getattr(self, "_source", "builtin"),
        )

    def info(self) -> PluginInfo:
        """Return the :class:`PluginInfo` metadata record for this plugin."""
        return self.get_info()


# Stage-specific plugin base classes (type aliases for shared base)
FetcherPlugin = DataFetcherPlugin
ExtractorPlugin = DataFetcherPlugin
StoragePlugin = DataFetcherPlugin
NormalizerPlugin = DataFetcherPlugin
DedupePlugin = DataFetcherPlugin
ExporterPlugin = DataFetcherPlugin


class FetchError(Exception):
    """Fetcher-specific errors."""
    pass


class ExtractionError(Exception):
    """Extraction-specific errors."""
    pass


class StorageError(Exception):
    """Storage-specific errors."""
    pass


class NormalizationError(Exception):
    """Normalization-specific errors."""
    pass


class DedupeError(Exception):
    """Deduplication-specific errors."""
    pass


class ExportError(Exception):
    """Export-specific errors."""
    pass


# ---------------------------------------------------------------------------
# Hook specifications
# ---------------------------------------------------------------------------


@hookspec
def data_fetcher_fetch(url: str, config: dict[str, Any] | None = None) -> Any:
    """Fetch raw content for ``url`` and return a fetch result."""


@hookspec
def data_fetcher_extract(
    raw_data: bytes,
    characterization: Any,
    config: dict[str, Any] | None = None,
) -> Any:
    """Extract a canonical representation from raw bytes."""


@hookspec
def data_fetcher_store(artifact: Any, config: dict[str, Any] | None = None) -> Any:
    """Persist an artifact to the configured object store and metadata store."""


@hookspec
def data_fetcher_normalize(canonical_document: Any, config: dict[str, Any] | None = None) -> Any:
    """Normalize a canonical document deterministically."""


@hookspec
def data_fetcher_deduplicate(documents: list[Any], config: dict[str, Any] | None = None) -> Any:
    """Detect duplicate / near-duplicate documents."""


@hookspec
def data_fetcher_export(records: list[Any], config: dict[str, Any] | None = None) -> Any:
    """Export processed records to an external format."""
