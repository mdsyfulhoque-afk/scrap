"""Pluggy hook registry for the Data Fetcher plugin system.

This module re-declares the hook *specifications* (imported from
:mod:`data_fetcher.plugin_base`) and exposes :func:`create_hook_manager`, which
returns a configured :class:`pluggy.PluginManager` ready to have plugins
registered against it.
"""

from __future__ import annotations

import sys

import pluggy

from data_fetcher.plugin_base import (
    PLUGIN_PROJECT_NAME,
    data_fetcher_deduplicate,
    data_fetcher_export,
    data_fetcher_extract,
    data_fetcher_fetch,
    data_fetcher_normalize,
    data_fetcher_store,
)


def create_hook_manager() -> pluggy.PluginManager:
    """Return a pluggy manager with every hook specification registered.

    The specifications are the ``data_fetcher_*`` functions defined in
    :mod:`data_fetcher.plugin_base`; they are re-exported here so the manager
    can register them from a single module object.
    """
    manager = pluggy.PluginManager(PLUGIN_PROJECT_NAME)
    manager.add_hookspecs(sys.modules[__name__])
    return manager
