import json
from pathlib import Path


class ArchiveIndexService:
    def __init__(self, index_path: Path) -> None:
        self.index_path = index_path

    def upsert_record(self, record_id: str, payload: dict) -> None:
        manifest = self._load_manifest()
        manifest[record_id] = payload
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.index_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _load_manifest(self) -> dict[str, dict]:
        if not self.index_path.exists():
            return {}
        try:
            raw = json.loads(self.index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(raw, dict):
            return {}
        return {str(key): value for key, value in raw.items() if isinstance(value, dict)}
