from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REFERENCE_REGISTRY_PATH = Path(__file__).resolve().parent.parent / "data" / "reference" / "source_ingestion_registry.json"


def load_source_tool_catalog(path: Path | None = None) -> dict[str, Any]:
    registry_path = path or REFERENCE_REGISTRY_PATH
    return json.loads(registry_path.read_text(encoding="utf-8"))


def list_source_tools(path: Path | None = None) -> list[dict[str, Any]]:
    return list(load_source_tool_catalog(path).get("tools", []))


def list_internal_capabilities(path: Path | None = None) -> list[dict[str, Any]]:
    return list(load_source_tool_catalog(path).get("internal_capabilities", []))


def get_recommended_stack(scenario_id: str, path: Path | None = None) -> dict[str, Any] | None:
    catalog = load_source_tool_catalog(path)
    for item in catalog.get("recommended_stacks", []):
        if str(item.get("scenario_id")) == scenario_id:
            return item
    return None
