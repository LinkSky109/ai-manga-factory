from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.config import REQUIREMENTS_DIR


INCIDENT_LOG_PATH = REQUIREMENTS_DIR / "incident_log.jsonl"
REQUIREMENT_BACKLOG_PATH = REQUIREMENTS_DIR / "requirement_backlog.json"


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RequirementMiner:
    MAX_EXAMPLES = 5

    def __init__(
        self,
        *,
        backlog_path: Path = REQUIREMENT_BACKLOG_PATH,
        incident_log_path: Path = INCIDENT_LOG_PATH,
    ) -> None:
        self.backlog_path = backlog_path
        self.incident_log_path = incident_log_path
        self._ensure_files_exist()

    def record_incident(
        self,
        *,
        title: str,
        summary: str,
        area: str,
        suggested_change: str,
        severity: str = "medium",
        dedupe_key: str | None = None,
        context: dict[str, Any] | None = None,
        related_files: list[str] | None = None,
        status: str = "pending",
    ) -> dict[str, Any]:
        context = context or {}
        related_files = related_files or []
        item_key = dedupe_key or title.strip()

        backlog = self._load_json(
            self.backlog_path,
            {"updated_at": _iso_now(), "items": []},
        )
        items = backlog.setdefault("items", [])
        now = _iso_now()
        existing = next((item for item in items if item.get("dedupe_key") == item_key), None)

        incident = {
            "timestamp": now,
            "title": title.strip(),
            "summary": summary.strip(),
            "area": area.strip(),
            "severity": severity.strip(),
            "dedupe_key": item_key,
            "context": context,
            "related_files": related_files,
        }
        self._append_incident_log(incident)

        if existing is None:
            existing = {
                "id": f"req-{len(items) + 1:04d}",
                "title": title.strip(),
                "summary": summary.strip(),
                "area": area.strip(),
                "severity": severity.strip(),
                "status": status.strip(),
                "suggested_change": suggested_change.strip(),
                "dedupe_key": item_key,
                "occurrence_count": 0,
                "first_seen_at": now,
                "last_seen_at": now,
                "examples": [],
                "related_files": [],
            }
            items.append(existing)

        existing["occurrence_count"] = int(existing.get("occurrence_count", 0)) + 1
        existing["last_seen_at"] = now
        if not existing.get("summary"):
            existing["summary"] = summary.strip()
        if not existing.get("suggested_change"):
            existing["suggested_change"] = suggested_change.strip()

        file_set = {str(item) for item in existing.get("related_files", [])}
        for file_path in related_files:
            file_value = str(file_path).strip()
            if file_value and file_value not in file_set:
                existing.setdefault("related_files", []).append(file_value)
                file_set.add(file_value)

        examples = existing.setdefault("examples", [])
        examples.append(
            {
                "timestamp": now,
                "summary": summary.strip(),
                "context": context,
            }
        )
        if len(examples) > self.MAX_EXAMPLES:
            del examples[:-self.MAX_EXAMPLES]

        backlog["updated_at"] = now
        self._write_json(self.backlog_path, backlog)
        return existing

    def _ensure_files_exist(self) -> None:
        REQUIREMENTS_DIR.mkdir(parents=True, exist_ok=True)
        if not self.backlog_path.exists():
            self._write_json(
                self.backlog_path,
                {"updated_at": _iso_now(), "items": []},
            )
        if not self.incident_log_path.exists():
            self.incident_log_path.write_text("", encoding="utf-8")

    def _append_incident_log(self, incident: dict[str, Any]) -> None:
        self.incident_log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.incident_log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(incident, ensure_ascii=False) + "\n")

    def _load_json(self, path: Path, fallback: dict[str, Any]) -> dict[str, Any]:
        if not path.exists():
            return json.loads(json.dumps(fallback))
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return json.loads(json.dumps(fallback))

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
