"""Exporter plugin serializing processed records to newline-delimited JSON."""

from __future__ import annotations

import json
from typing import Any

from data_fetcher.plugin_base import DataFetcherPlugin, hookimpl


class JsonlExporterPlugin(DataFetcherPlugin):
    """Exporter that writes newline-delimited JSON (JSONL)."""

    name = "jsonl_exporter"
    stage = "exporter"
    version = "1.0.0"
    description = "Exports processed records to newline-delimited JSON (JSONL)."

    def capabilities(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "format": "jsonl",
            "streaming": False,
        }

    @staticmethod
    def _serialize(record: Any) -> dict[str, Any]:
        if hasattr(record, "as_dict"):
            return record.as_dict()
        if hasattr(record, "__dict__"):
            return {k: v for k, v in vars(record).items() if not k.startswith("_")}
        return record

    @hookimpl
    def data_fetcher_export(self, records: list[Any], config: dict[str, Any] | None = None) -> Any:
        config = config or {}
        path = config.get("path", "export.jsonl")
        count = 0
        with open(path, "w", encoding="utf-8") as fh:
            for record in records:
                fh.write(json.dumps(self._serialize(record), default=str, ensure_ascii=False))
                fh.write("\n")
                count += 1
        return {"path": path, "count": count}
