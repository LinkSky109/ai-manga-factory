from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROJECT_DATA_DIR = PROJECT_ROOT / "data"
SECRETS_DIR = PROJECT_ROOT / "secrets"
DEFAULT_CONFIG_PATH = SECRETS_DIR / "runtime_storage_config.json"
DEFAULT_ONEDRIVE_SUBDIR = Path("CodexRuntime") / "ai-manga-factory"
DEFAULT_LOCAL_SUBDIR = Path("data_runtime")


@dataclass(slots=True)
class RuntimeStoragePlan:
    runtime_root: Path
    config_path: Path
    source: str
    runtime_provider: str
    remote_sync_enabled: bool
    remote_sync_provider: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime_root": str(self.runtime_root),
            "config_path": str(self.config_path),
            "source": self.source,
            "runtime_provider": self.runtime_provider,
            "remote_sync_enabled": self.remote_sync_enabled,
            "remote_sync_provider": self.remote_sync_provider,
        }


def _config_path() -> Path:
    raw = os.getenv("AI_MANGA_FACTORY_RUNTIME_STORAGE_CONFIG", "").strip()
    if raw:
        return Path(raw).expanduser()
    return DEFAULT_CONFIG_PATH


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _normalize_path(raw: str | None) -> Path | None:
    value = str(raw or "").strip()
    if not value:
        return None
    return Path(os.path.expandvars(value)).expanduser()


def _candidate_onedrive_root() -> Path | None:
    env_candidates = [
        os.getenv("OneDriveCommercial", "").strip(),
        os.getenv("OneDriveConsumer", "").strip(),
        os.getenv("OneDrive", "").strip(),
    ]
    for item in env_candidates:
        candidate = _normalize_path(item)
        if candidate and candidate.exists():
            return candidate

    home = Path.home()
    for candidate in (home / "OneDrive", Path(os.environ.get("USERPROFILE", str(home))) / "OneDrive"):
        if candidate.exists():
            return candidate
    return None


def default_runtime_root() -> Path:
    env_path = _normalize_path(os.getenv("AI_MANGA_FACTORY_RUNTIME_DIR"))
    if env_path:
        return env_path

    onedrive_root = _candidate_onedrive_root()
    if onedrive_root:
        return onedrive_root / DEFAULT_ONEDRIVE_SUBDIR

    return PROJECT_ROOT / DEFAULT_LOCAL_SUBDIR


def load_runtime_storage_config(path: Path | None = None) -> dict[str, Any]:
    config_path = path or _config_path()
    config = _load_json(config_path)
    if not config:
        return {
            "runtime_root": str(default_runtime_root()),
            "runtime_provider": {
                "type": "sync_folder",
                "name": "onedrive" if _candidate_onedrive_root() else "local_disk",
                "root_path": str(default_runtime_root()),
            },
            "remote_sync": {
                "enabled": False,
                "provider": "aliyun_oss",
                "aliyun_oss": {
                    "endpoint": "",
                    "bucket": "",
                    "prefix": "ai-manga-factory/runtime",
                    "access_key_id_env": "AI_MANGA_FACTORY_OSS_ACCESS_KEY_ID",
                    "access_key_secret_env": "AI_MANGA_FACTORY_OSS_ACCESS_KEY_SECRET",
                },
                "baidu_pan": {
                    "status": "planned",
                    "note": "当前未接入稳定官方 API，建议先使用本地同步目录模式。",
                },
                "quark_pan": {
                    "config_dir": str(SECRETS_DIR / "quark_pan"),
                    "cookie_file": str(SECRETS_DIR / "quark_pan_cookie.txt"),
                    "root_folder": "AI-Manga-Factory",
                    "business_folder": "业务产物",
                    "pack_reports_folder": "适配包汇总",
                    "replace_existing": True,
                    "upload_pack_reports": True,
                    "only_completed_jobs": True,
                },
                "aliyundrive": {
                    "config_dir": str(SECRETS_DIR / "aliyundrive"),
                    "name": "ai-manga-factory",
                    "root_folder": "AI-Manga-Factory",
                    "business_folder": "业务产物",
                    "pack_reports_folder": "适配包汇总",
                    "check_name_mode": "overwrite",
                    "upload_pack_reports": True,
                    "only_completed_jobs": True,
                },
            },
        }
    return config


def get_runtime_storage_plan(path: Path | None = None) -> RuntimeStoragePlan:
    config_path = path or _config_path()
    config = load_runtime_storage_config(config_path)

    env_root = _normalize_path(os.getenv("AI_MANGA_FACTORY_RUNTIME_DIR"))
    config_root = _normalize_path(config.get("runtime_root"))
    runtime_root = env_root or config_root or default_runtime_root()
    runtime_provider = str(config.get("runtime_provider", {}).get("name", "local_disk")).strip() or "local_disk"
    remote_sync = config.get("remote_sync", {})
    remote_sync_provider = str(remote_sync.get("provider", "disabled")).strip() or "disabled"
    remote_sync_enabled = bool(remote_sync.get("enabled", False))

    source = "env:AI_MANGA_FACTORY_RUNTIME_DIR" if env_root else ("config" if config_root else "auto-default")
    runtime_root.mkdir(parents=True, exist_ok=True)

    return RuntimeStoragePlan(
        runtime_root=runtime_root,
        config_path=config_path,
        source=source,
        runtime_provider=runtime_provider,
        remote_sync_enabled=remote_sync_enabled,
        remote_sync_provider=remote_sync_provider,
    )


def ensure_runtime_subdirs(root: Path, names: list[str]) -> None:
    for name in names:
        (root / name).mkdir(parents=True, exist_ok=True)
