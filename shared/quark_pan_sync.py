from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.config import ADAPTATIONS_DIR, ARTIFACTS_DIR, PROVIDER_USAGE_DIR, ROOT_DIR

try:
    from quark_client import QuarkClient
except ImportError:  # pragma: no cover - optional dependency
    QuarkClient = None  # type: ignore[assignment]


LEDGER_FILE = PROVIDER_USAGE_DIR / "quark_pan_sync_ledger.json"
REPORT_FILE = PROVIDER_USAGE_DIR / "quark_pan_last_sync.json"
DEFAULT_QUARK_CONFIG_DIR = ROOT_DIR / "secrets" / "quark_pan"
DEFAULT_COOKIE_FILE = ROOT_DIR / "secrets" / "quark_pan_cookie.txt"
INVALID_REMOTE_NAME = re.compile(r'[\\/:*?"<>|]+')

JOB_ROOT_FILES = (
    "result_summary.md",
    "validation_report.md",
    "result_snapshot.json",
    "research.md",
    "screenplay.md",
    "art_direction.md",
    "prompts.json",
    "manifest.json",
    "chapters_index.json",
    "qa_overview.md",
)

JOB_GLOBS = (
    "delivery/final_cut.mp4",
    "characters/lead_character.png",
    "storyboard/scene_*.png",
    "chapters/chapter_*/delivery/chapter_final_cut.mp4",
    "chapters/chapter_*/storyboard/storyboard.json",
    "chapters/chapter_*/storyboard/storyboard.csv",
    "chapters/chapter_*/storyboard/storyboard.xlsx",
    "chapters/chapter_*/audio/audio_plan.json",
    "chapters/chapter_*/audio/narration_script.txt",
    "chapters/chapter_*/audio/voice_script.txt",
    "chapters/chapter_*/audio/voiceover.mp3",
    "chapters/chapter_*/audio/ambience.wav",
    "chapters/chapter_*/qa/qa_report.md",
    "chapters/chapter_*/qa/qa_snapshot.json",
)

PACK_REPORT_FILES = (
    "latest_result.md",
    "latest_validation.md",
    "latest_result_pointer.json",
)


@dataclass(slots=True)
class UploadEntry:
    local_path: Path
    remote_parts: tuple[str, ...]
    signature: str


def build_quark_sync_config(raw: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = dict(raw or {})
    return {
        "config_dir": str(Path(str(raw.get("config_dir") or DEFAULT_QUARK_CONFIG_DIR)).expanduser()),
        "cookie_file": str(Path(str(raw.get("cookie_file") or DEFAULT_COOKIE_FILE)).expanduser()),
        "root_folder": str(raw.get("root_folder") or "AI-Manga-Factory"),
        "business_folder": str(raw.get("business_folder") or "业务产物"),
        "pack_reports_folder": str(raw.get("pack_reports_folder") or "适配包汇总"),
        "replace_existing": bool(raw.get("replace_existing", True)),
        "upload_pack_reports": bool(raw.get("upload_pack_reports", True)),
        "only_completed_jobs": bool(raw.get("only_completed_jobs", True)),
    }


def sync_business_outputs_to_quark(
    *,
    config: dict[str, Any] | None = None,
    dry_run: bool = False,
    job_ids: set[int] | None = None,
) -> dict[str, Any]:
    resolved = build_quark_sync_config(config)
    entries = collect_business_output_entries(config=resolved, job_ids=job_ids)
    ledger = _load_json(LEDGER_FILE)
    ledger_entries = dict(ledger.get("entries", {}))
    pending = [entry for entry in entries if ledger_entries.get(str(entry.local_path)) != _ledger_value(entry)]

    report: dict[str, Any] = {
        "provider": "quark_pan",
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

    client = _create_client(resolved)
    folder_cache: dict[tuple[str, ...], str] = {tuple(): "0"}

    for entry in entries:
        if ledger_entries.get(str(entry.local_path)) == _ledger_value(entry):
            report["skipped"].append(_entry_record(entry))
            continue

        parent_parts = entry.remote_parts[:-1]
        folder_id = _ensure_remote_folder(client, folder_cache, parent_parts)
        existing = _find_child_by_name(client, folder_id, entry.remote_parts[-1], want_folder=False)
        if existing and resolved["replace_existing"]:
            client.delete_files([str(existing.get("fid"))])
            existing = None
        if existing:
            ledger_entries[str(entry.local_path)] = _ledger_value(entry)
            report["skipped"].append(_entry_record(entry))
            continue

        print(f"[quark] upload {entry.local_path} -> {'/'.join(entry.remote_parts)}")
        upload_result = client.upload.upload_file(
            str(entry.local_path),
            parent_folder_id=folder_id,
            progress_callback=lambda progress, message, path=entry.local_path.name: print(
                f"\r[quark] {path} {progress:>3}% {message}",
                end="",
                flush=True,
            ),
        )
        print()
        ledger_entries[str(entry.local_path)] = _ledger_value(entry)
        record = _entry_record(entry)
        record["upload_result"] = upload_result.get("finish_result", {})
        report["uploaded"].append(record)

    payload = {
        "entries": ledger_entries,
        "updated_at": _now_iso(),
    }
    LEDGER_FILE.parent.mkdir(parents=True, exist_ok=True)
    LEDGER_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    report["updated_at"] = payload["updated_at"]
    REPORT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def collect_business_output_entries(*, config: dict[str, Any], job_ids: set[int] | None = None) -> list[UploadEntry]:
    entries: list[UploadEntry] = []
    only_completed = bool(config.get("only_completed_jobs", True))

    for job_dir in sorted(ARTIFACTS_DIR.glob("job_*")):
        if not job_dir.is_dir():
            continue
        try:
            job_id = int(job_dir.name.split("_", 1)[1])
        except (IndexError, ValueError):
            continue
        if job_ids and job_id not in job_ids:
            continue

        snapshot_path = job_dir / "result_snapshot.json"
        if not snapshot_path.exists():
            continue
        snapshot = _load_json(snapshot_path)
        if only_completed and snapshot.get("status") != "completed":
            continue

        project_name = _safe_remote_name(str(snapshot.get("project_name") or "default-project"))
        capability_id = _safe_remote_name(str(snapshot.get("capability_id") or "unknown"))
        pack_name = _safe_remote_name(str(snapshot.get("adaptation_pack") or "general"))
        job_root = (
            _safe_remote_name(str(config["root_folder"])),
            _safe_remote_name(str(config["business_folder"])),
            project_name,
            capability_id,
            pack_name,
            f"job_{job_id:04d}",
        )

        for relative in JOB_ROOT_FILES:
            path = job_dir / relative
            if path.exists() and path.is_file():
                entries.append(_build_entry(path=path, job_dir=job_dir, remote_root=job_root))
        for pattern in JOB_GLOBS:
            for path in sorted(job_dir.glob(pattern)):
                if path.exists() and path.is_file():
                    entries.append(_build_entry(path=path, job_dir=job_dir, remote_root=job_root))

        if config.get("upload_pack_reports", True):
            raw_pack_name = str(snapshot.get("adaptation_pack") or "").strip()
            if raw_pack_name:
                pack_dir = ADAPTATIONS_DIR / raw_pack_name / "reports"
                pack_root = (
                    _safe_remote_name(str(config["root_folder"])),
                    _safe_remote_name(str(config["pack_reports_folder"])),
                    _safe_remote_name(raw_pack_name),
                    "reports",
                )
                for relative in PACK_REPORT_FILES:
                    path = pack_dir / relative
                    if path.exists() and path.is_file():
                        entries.append(_build_entry(path=path, job_dir=pack_dir, remote_root=pack_root))

    unique: dict[tuple[str, tuple[str, ...]], UploadEntry] = {}
    for entry in entries:
        unique[(str(entry.local_path), entry.remote_parts)] = entry
    return list(unique.values())


def _create_client(config: dict[str, Any]) -> Any:
    if QuarkClient is None:  # pragma: no cover - optional dependency
        raise RuntimeError("缺少 quarkpan 依赖，请先安装 requirements-storage.txt")

    config_dir = Path(str(config["config_dir"])).expanduser()
    cookie_file = Path(str(config["cookie_file"])).expanduser()
    config_dir.mkdir(parents=True, exist_ok=True)
    cookie_file.parent.mkdir(parents=True, exist_ok=True)
    os.environ["QUARK_CONFIG_DIR"] = str(config_dir)

    cookie = os.getenv("AI_MANGA_FACTORY_QUARK_COOKIE", "").strip()
    if not cookie and cookie_file.exists():
        cookie = cookie_file.read_text(encoding="utf-8").strip()

    try:
        client = QuarkClient(cookies=cookie or None, auto_login=not bool(cookie))
        storage = client.get_storage_info()
    except Exception:
        if not cookie:
            raise
        try:
            cookie_file.unlink(missing_ok=True)
        except OSError:
            pass
        client = QuarkClient(cookies=None, auto_login=True)
        storage = client.get_storage_info()

    cookie_value = getattr(client.api_client, "cookies", "") or ""
    if not cookie_value:
        raise RuntimeError(f"夸克网盘登录成功，但未拿到 Cookie。storage={storage}")
    cookie_file.write_text(cookie_value, encoding="utf-8")
    return client


def _ensure_remote_folder(client: Any, cache: dict[tuple[str, ...], str], parts: tuple[str, ...]) -> str:
    if parts in cache:
        return cache[parts]

    parent_id = "0"
    current: list[str] = []
    for part in parts:
        current.append(part)
        key = tuple(current)
        if key in cache:
            parent_id = cache[key]
            continue
        existing = _find_child_by_name(client, parent_id, part, want_folder=True)
        if existing:
            parent_id = str(existing.get("fid"))
            cache[key] = parent_id
            continue
        result = client.create_folder(part, parent_id)
        folder_id = _extract_fid(result)
        if not folder_id:
            created = _find_child_by_name(client, parent_id, part, want_folder=True)
            folder_id = str(created.get("fid")) if created else ""
        if not folder_id:
            raise RuntimeError(f"无法创建远程文件夹: {'/'.join(parts)}")
        parent_id = folder_id
        cache[key] = parent_id
    return parent_id


def _find_child_by_name(client: Any, parent_id: str, name: str, *, want_folder: bool) -> dict[str, Any] | None:
    page = 1
    while True:
        response = client.list_files(parent_id, page=page, size=200)
        items = _extract_items(response)
        if not items:
            return None
        for item in items:
            file_name = str(item.get("file_name") or item.get("name") or "")
            file_type = item.get("file_type")
            is_folder = str(file_type) == "0" or bool(item.get("dir", False))
            if file_name == name and is_folder == want_folder:
                return item
        if len(items) < 200:
            return None
        page += 1


def _extract_items(response: dict[str, Any]) -> list[dict[str, Any]]:
    data = response.get("data")
    if isinstance(data, dict):
        for key in ("list", "data"):
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    return []


def _extract_fid(response: dict[str, Any]) -> str:
    data = response.get("data")
    if isinstance(data, dict):
        for key in ("fid", "file_id"):
            value = data.get(key)
            if value:
                return str(value)
        for nested_key in ("list", "data"):
            nested = data.get(nested_key)
            if isinstance(nested, list) and nested and isinstance(nested[0], dict):
                value = nested[0].get("fid") or nested[0].get("file_id")
                if value:
                    return str(value)
    return ""


def _build_entry(*, path: Path, job_dir: Path, remote_root: tuple[str, ...]) -> UploadEntry:
    relative = path.relative_to(job_dir).parts
    signature = f"{path.stat().st_size}:{path.stat().st_mtime_ns}"
    return UploadEntry(
        local_path=path,
        remote_parts=remote_root + tuple(_safe_remote_name(part) for part in relative),
        signature=signature,
    )


def _entry_record(entry: UploadEntry) -> dict[str, Any]:
    return {
        "local_path": str(entry.local_path),
        "remote_path": "/".join(entry.remote_parts),
        "signature": entry.signature,
    }


def _ledger_value(entry: UploadEntry) -> str:
    return f"{entry.signature}|{'/'.join(entry.remote_parts)}"


def _safe_remote_name(value: str) -> str:
    cleaned = INVALID_REMOTE_NAME.sub("-", value).strip().strip(".")
    return cleaned or "unnamed"


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
