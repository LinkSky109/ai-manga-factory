from __future__ import annotations

import importlib.util
import os
import re
from pathlib import Path
from typing import Any, Protocol

from src.core.config import Settings


INVALID_REMOTE_NAME = re.compile(r'[\\/:*?"<>|]+')


class RemoteArchiveUploader(Protocol):
    def upload(self, remote_path: str, source_file: Path, content_type: str | None = None) -> None:
        ...


def has_quark_pan_dependency() -> bool:
    return importlib.util.find_spec("quark_client") is not None


def has_aliyundrive_dependency() -> bool:
    return importlib.util.find_spec("aligo") is not None


def resolve_quark_pan_cookie(settings: Settings) -> str | None:
    for value in (
        os.getenv("AI_MANGA_FACTORY_QUARK_COOKIE"),
        os.getenv("QUARK_PAN_COOKIE"),
        os.getenv("QUARK_PAN_TOKEN"),
    ):
        if value and value.strip():
            return value.strip()

    if settings.quark_pan_cookie_file.exists():
        cookie = settings.quark_pan_cookie_file.read_text(encoding="utf-8").strip()
        if cookie:
            return cookie
    return None


def has_saved_aliyundrive_session(settings: Settings) -> bool:
    return settings.aliyundrive_config_dir.exists() and any(settings.aliyundrive_config_dir.iterdir())


def validate_quark_pan_api_config(settings: Settings) -> tuple[bool, str]:
    if not has_quark_pan_dependency():
        return False, "Missing quark-client dependency."
    if not resolve_quark_pan_cookie(settings):
        return False, "Quark Pan cookie is missing. Run auth script or provide QUARK_PAN_COOKIE_FILE."
    return True, "Quark Pan API credentials are configured."


def validate_aliyundrive_api_config(settings: Settings) -> tuple[bool, str]:
    if not has_aliyundrive_dependency():
        return False, "Missing aligo dependency."
    if not has_saved_aliyundrive_session(settings):
        return False, "AliyunDrive config directory is empty. Run auth script to generate login state."
    return True, "AliyunDrive API credentials are configured."


def build_quark_pan_remote_uploader(
    settings: Settings,
    *,
    interactive_login: bool = False,
) -> RemoteArchiveUploader:
    return QuarkPanRemoteUploader(settings, interactive_login=interactive_login)


def build_aliyundrive_remote_uploader(
    settings: Settings,
    *,
    interactive_login: bool = False,
) -> RemoteArchiveUploader:
    return AliyunDriveRemoteUploader(settings, interactive_login=interactive_login)


class QuarkPanRemoteUploader:
    def __init__(self, settings: Settings, *, interactive_login: bool = False) -> None:
        if not has_quark_pan_dependency():
            raise RuntimeError("Missing quark-client dependency.")

        from quark_client import QuarkClient  # type: ignore

        self.settings = settings
        self.folder_cache: dict[tuple[str, ...], str] = {tuple(): "0"}
        os.environ["QUARK_CONFIG_DIR"] = str(settings.quark_pan_config_dir)

        cookie = resolve_quark_pan_cookie(settings)
        if not cookie and not interactive_login:
            raise RuntimeError("Quark Pan cookie is missing.")

        self.client = QuarkClient(cookies=cookie or None, auto_login=interactive_login and not bool(cookie))
        self.client.get_storage_info()

        cookie_value = getattr(getattr(self.client, "api_client", None), "cookies", "") or ""
        if cookie_value:
            settings.quark_pan_cookie_file.write_text(str(cookie_value), encoding="utf-8")

    def upload(self, remote_path: str, source_file: Path, content_type: str | None = None) -> None:
        del content_type
        parts = tuple(_safe_remote_name(part) for part in remote_path.split("/") if part)
        if not parts:
            raise RuntimeError("Remote path is empty.")

        folder_id = self._ensure_remote_folder(parts[:-1])
        file_name = parts[-1]
        existing = self._find_child_by_name(folder_id, file_name, want_folder=False)
        if existing and self.settings.quark_pan_replace_existing:
            self.client.delete_files([str(existing.get("fid"))])
            existing = None
        if existing is not None:
            return

        self.client.upload.upload_file(str(source_file), parent_folder_id=folder_id)

    def _ensure_remote_folder(self, parts: tuple[str, ...]) -> str:
        if parts in self.folder_cache:
            return self.folder_cache[parts]

        parent_id = "0"
        current: list[str] = []
        for part in parts:
            current.append(part)
            key = tuple(current)
            if key in self.folder_cache:
                parent_id = self.folder_cache[key]
                continue
            existing = self._find_child_by_name(parent_id, part, want_folder=True)
            if existing:
                parent_id = str(existing.get("fid"))
                self.folder_cache[key] = parent_id
                continue
            result = self.client.create_folder(part, parent_id)
            folder_id = _extract_fid(result)
            if not folder_id:
                created = self._find_child_by_name(parent_id, part, want_folder=True)
                folder_id = str(created.get("fid")) if created else ""
            if not folder_id:
                raise RuntimeError(f"Unable to create remote folder: {'/'.join(parts)}")
            parent_id = folder_id
            self.folder_cache[key] = parent_id
        return parent_id

    def _find_child_by_name(self, parent_id: str, name: str, *, want_folder: bool) -> dict[str, Any] | None:
        page = 1
        while True:
            response = self.client.list_files(parent_id, page=page, size=200)
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


class AliyunDriveRemoteUploader:
    def __init__(self, settings: Settings, *, interactive_login: bool = False) -> None:
        if not has_aliyundrive_dependency():
            raise RuntimeError("Missing aligo dependency.")
        if not has_saved_aliyundrive_session(settings) and not interactive_login:
            raise RuntimeError("AliyunDrive config directory is empty.")

        from aligo import Aligo  # type: ignore
        from aligo.core import set_config_folder  # type: ignore

        self.settings = settings
        set_config_folder(str(settings.aliyundrive_config_dir))
        self.client = Aligo(name=settings.aliyundrive_name, re_login=interactive_login)
        self.client.get_drive()

    def upload(self, remote_path: str, source_file: Path, content_type: str | None = None) -> None:
        del content_type
        parts = tuple(_safe_remote_name(part) for part in remote_path.split("/") if part)
        if not parts:
            raise RuntimeError("Remote path is empty.")

        remote_parent = "/" + "/".join(parts[:-1]) if len(parts) > 1 else "/"
        parent = self.client.get_folder_by_path(remote_parent, create_folder=True, check_name_mode="refuse")
        self.client.upload_file(
            str(source_file),
            parent_file_id=parent.file_id,
            name=parts[-1],
            check_name_mode=self.settings.aliyundrive_check_name_mode,
        )


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


def _safe_remote_name(value: str) -> str:
    cleaned = INVALID_REMOTE_NAME.sub("-", value).strip().strip(".")
    return cleaned or "unnamed"
