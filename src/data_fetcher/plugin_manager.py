"""High-level plugin manager: discovers, registers and runs plugins.

The :class:`PluginManager` wraps a :class:`pluggy.PluginManager`. On
construction it discovers plugins in two ways:

1. Through the ``data_fetcher`` entry-point group declared in ``pyproject.toml``
   (the primary mechanism once the package is installed).
2. As a fallback, by importing the built-in plugin modules directly so that
   discovery still works from a source checkout that has not been installed.

Use :meth:`list_plugins` to inspect what was discovered, :meth:`get_plugin` to
retrieve a single plugin, and :meth:`run` to invoke a hook across all plugins
that implement it.
"""

from __future__ import annotations

import importlib
import logging
from typing import Any

import pluggy

try:  # Python >= 3.10
    from importlib.metadata import entry_points
except ImportError:  # pragma: no cover - Python < 3.10
    from importlib_metadata import entry_points  # type: ignore

from data_fetcher import hooks as hook_module
from data_fetcher.plugin_base import (
    PLUGIN_ENTRY_POINT_GROUP,
    DataFetcherPlugin,
    PluginInfo,
)

logger = logging.getLogger(__name__)

#: Built-in plugin modules imported directly when entry-points are unavailable.
BUILTIN_PLUGINS: list[str] = [
    "data_fetcher.plugins.fetchers.requests_fetcher",
    "data_fetcher.plugins.extractors.heuristic_extractor",
    "data_fetcher.plugins.storages.postgres_minio_storage",
    "data_fetcher.plugins.normalizers.standard_normalizer",
    "data_fetcher.plugins.dedupes.trigram_jaccard",
    "data_fetcher.plugins.exporters.jsonl_exporter",
]


def _plugin_classes(module: Any) -> list[type[DataFetcherPlugin]]:
    """Return every concrete ``DataFetcherPlugin`` subclass defined in ``module``."""
    classes: list[type[DataFetcherPlugin]] = []
    for obj in vars(module).values():
        if (
            isinstance(obj, type)
            and issubclass(obj, DataFetcherPlugin)
            and obj is not DataFetcherPlugin
        ):
            classes.append(obj)
    return classes


class PluginManager:
    """Discovers and orchestrates Data Fetcher plugins."""

    def __init__(self, autodiscover: bool = True) -> None:
        self._pm = pluggy.PluginManager("data_fetcher")
        self._pm.add_hookspecs(hook_module)
        self._plugins: dict[str, DataFetcherPlugin] = {}
        if autodiscover:
            self.discover()

    # -- discovery ---------------------------------------------------------

    def discover(self) -> list[PluginInfo]:
        """Load entry-point plugins, then fall back to built-in modules."""
        discovered: list[PluginInfo] = []
        seen_modules: set[str] = set()

        # 1. Entry points (installed package).
        try:
            eps = entry_points(group=PLUGIN_ENTRY_POINT_GROUP)
        except TypeError:  # pragma: no cover - older importlib.metadata
            eps = entry_points().get(PLUGIN_ENTRY_POINT_GROUP, [])  # type: ignore

        for ep in eps:
            if ep.name in self._plugins:
                continue
            try:
                plugin_cls = ep.load()
                plugin = plugin_cls() if isinstance(plugin_cls, type) else plugin_cls
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Failed to load entry-point plugin %s: %s", ep.name, exc)
                continue
            self.register(plugin, name=ep.name, source="entry_point")

        # 2. Built-in modules (source checkout).
        for module_path in BUILTIN_PLUGINS:
            if module_path in seen_modules or self._module_loaded(module_path):
                continue
            try:
                module = importlib.import_module(module_path)
            except Exception as exc:
                logger.warning("Failed to import built-in plugin %s: %s", module_path, exc)
                continue
            seen_modules.add(module_path)
            for plugin_cls in _plugin_classes(module):
                if plugin_cls.name in self._plugins:
                    continue
                try:
                    self.register(plugin_cls(), name=plugin_cls.name, source="builtin")
                except Exception as exc:  # pragma: no cover - defensive
                    logger.warning("Failed to register %s: %s", plugin_cls.__name__, exc)

        return self.list_plugins()

    def _module_loaded(self, module_path: str) -> bool:
        return module_path in __import__("sys").modules

    # -- registration ------------------------------------------------------

    def register(
        self,
        plugin: DataFetcherPlugin,
        name: str | None = None,
        source: str = "builtin",
    ) -> None:
        """Register ``plugin`` under ``name`` (defaults to its class name)."""
        key = name or getattr(plugin, "name", None) or plugin.__class__.__name__
        plugin._source = source  # type: ignore[attr-defined]
        self._plugins[key] = plugin
        try:
            self._pm.register(plugin, name=key)
        except ValueError:
            # Already registered (e.g. during re-discovery); ignore.
            pass

    # -- inspection --------------------------------------------------------

    def list_plugins(self) -> list[PluginInfo]:
        """Return metadata for every discovered plugin."""
        return [p.info() for p in self._plugins.values()]

    def get_plugin(self, name: str) -> DataFetcherPlugin | None:
        """Return the plugin registered under ``name`` (or ``None``)."""
        return self._plugins.get(name)

    def get_plugins_for_stage(self, stage: str) -> list[DataFetcherPlugin]:
        """Return every plugin that implements ``stage``."""
        return [p for p in self._plugins.values() if p.stage == stage]

    @property
    def hook(self) -> Any:
        """Expose the underlying pluggy hook caller."""
        return self._pm.hook

    # -- execution ---------------------------------------------------------

    def run(self, hook_name: str, **kwargs: Any) -> list[Any]:
        """Invoke ``hook_name`` across all plugins that implement it."""
        hook = getattr(self._pm.hook, hook_name)
        return list(hook(**kwargs))
