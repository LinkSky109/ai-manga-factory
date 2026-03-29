from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.config import PROVIDER_USAGE_DIR, ROOT_DIR
from shared.quark_pan_sync import collect_business_output_entries

try:
    from aligo import Aligo
    from aligo.core import set_config_folder
except ImportError:  # pragma: no cover - optional dependency
    Aligo = None  # type: ignore[assignment]
    set_config_folder = None  # type: ignore[assignment]


LEDGER_FILE = PROVIDER_USAGE_DIR / "aliyundrive_sync_ledger.json"
REPORT_FILE = PROVIDER_USAGE_DIR / "aliyundrive_last_sync.json"
DEFAULT_CONFIG_DIR = ROOT_DIR / "secrets" / "aliyundrive"


def build_aliyun_sync_config(raw: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = dict(raw or {})
    return {
        "config_dir": str(Path(str(raw.get("config_dir") or DEFAULT_CONFIG_DIR)).expanduser()),
        "name": str(raw.get("name") or "ai-manga-factory"),
        "root_folder": str(raw.get("root_folder") or "AI-Manga-Factory"),
        "business_folder": str(raw.get("business_folder") or "业务产物"),
        "pack_reports_folder": str(raw.get("pack_reports_folder") or "适配包汇总"),
        "check_name_mode": str(raw.get("check_name_mode") or "overwrite"),
        "upload_pack_reports": bool(raw.get("upload_pack_reports", True)),
        "only_completed_jobs": bool(raw.get("only_completed_jobs", True)),
    }


def sync_business_outputs_to_aliyundrive(
    *,
    config: dict[str, Any] | None = None,
    dry_run: bool = False,
    job_ids: set[int] | None = None,
) -> dict[str, Any]:
    resolved = build_aliyun_sync_config(config)
    entries = collect_business_output_entries(config=resolved, job_ids=job_ids)
    ledger = _load_json(LEDGER_FILE)
    ledger_entries = dict(ledger.get("entries", {}))
    pending = [entry for entry in entries if ledger_entries.get(str(entry.local_path)) != _ledger_value(entry)]

    report: dict[str, Any] = {
        "provider": "aliyundrive",
        "dry_run": dry_run,
        "root_folder": resolved["root_folder"],
        "business_folder": resolved["business_folder"],
        "pack_reports_folder": resolved["pack_reports_folder"],
        "planned": len(entries),
        "pending": len(pending),
        "uploaded": [],
        "skipped": [],
    }

    if dry_run:
        report["planned_paths"] = ["/".join(entry.remote_parts) for entry in pending]
        REPORT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return report

    ali = _create_client(resolved)
    for entry in entries:
        if ledger_entries.get(str(entry.local_path)) == _ledger_value(entry):
            report["skipped"].append(_entry_record(entry))
            continue

        remote_parent = "/" + "/".join(entry.remote_parts[:-1])
        parent = ali.get_folder_by_path(remote_parent, create_folder=True, check_name_mode="refuse")
        uploaded = ali.upload_file(
            str(entry.local_path),
            parent_file_id=parent.file_id,
            name=entry.remote_parts[-1],
            check_name_mode=resolved["check_name_mode"],
        )
        ledger_entries[str(entry.local_path)] = _ledger_value(entry)
        record = _entry_record(entry)
        record["file_id"] = getattr(uploaded, "file_id", None)
        report["uploaded"].append(record)

    payload = {"entries": ledger_entries, "updated_at": _now_iso()}
    LEDGER_FILE.parent.mkdir(parents=True, exist_ok=True)
    LEDGER_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    report["updated_at"] = payload["updated_at"]
    REPORT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def _create_client(config: dict[str, Any]) -> Any:
    if Aligo is None or set_config_folder is None:  # pragma: no cover - optional dependency
        raise RuntimeError("缺少 aligo 依赖，请先安装 requirements-storage.txt")
    config_dir = Path(str(config["config_dir"])).expanduser()
    config_dir.mkdir(parents=True, exist_ok=True)
    set_config_folder(str(config_dir))
    return Aligo(name=str(config["name"]), re_login=True)


def _entry_record(entry: Any) -> dict[str, Any]:
    return {
        "local_path": str(entry.local_path),
        "remote_path": "/".join(entry.remote_parts),
        "signature": entry.signature,
    }


def _ledger_value(entry: Any) -> str:
    return f"{entry.signature}|{'/'.join(entry.remote_parts)}"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}


def _now_iso() -> str:
    from datetime import datetime

    return datetime.now().astimezone().isoformat()
