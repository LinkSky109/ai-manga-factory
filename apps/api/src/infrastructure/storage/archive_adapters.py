from dataclasses import dataclass
from pathlib import Path
import shutil
from typing import Protocol

from src.core.config import Settings
from src.infrastructure.db.models import ArtifactModel
from src.infrastructure.storage.remote_storage_clients import (
    build_aliyundrive_remote_uploader,
    build_quark_pan_remote_uploader,
    has_aliyundrive_dependency,
    has_saved_aliyundrive_session,
    has_quark_pan_dependency,
    resolve_quark_pan_cookie,
)


@dataclass(slots=True)
class ArchiveWriteResult:
    archive_type: str
    archive_path: str
    index_key: str
    public_url: str | None


class S3Uploader(Protocol):
    def put_object(self, bucket: str, object_key: str, body: bytes, content_type: str | None) -> None:
        ...


class Boto3S3Uploader:
    def __init__(self, settings: Settings) -> None:
        try:
            import boto3
        except ImportError as exc:
            raise RuntimeError("boto3 is required for OBJECT_STORAGE_MODE=s3.") from exc

        self.client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint,
            aws_access_key_id=settings.s3_access_key_id,
            aws_secret_access_key=settings.s3_secret_access_key,
            region_name=settings.s3_region,
        )

    def put_object(self, bucket: str, object_key: str, body: bytes, content_type: str | None) -> None:
        payload = {
            "Bucket": bucket,
            "Key": object_key,
            "Body": body,
        }
        if content_type:
            payload["ContentType"] = content_type
        self.client.put_object(**payload)


def build_s3_uploader(settings: Settings) -> S3Uploader:
    return Boto3S3Uploader(settings)


def resolve_object_storage_bucket(settings: Settings) -> str:
    return settings.s3_bucket or settings.object_storage_bucket


def validate_s3_upload_config(settings: Settings) -> tuple[bool, str]:
    missing_fields = []
    if not settings.s3_endpoint:
        missing_fields.append("S3_ENDPOINT")
    if not resolve_object_storage_bucket(settings):
        missing_fields.append("S3_BUCKET")
    if not settings.s3_access_key_id:
        missing_fields.append("S3_ACCESS_KEY_ID")
    if not settings.s3_secret_access_key:
        missing_fields.append("S3_SECRET_ACCESS_KEY")

    if missing_fields:
        return False, f"Missing S3 config: {', '.join(missing_fields)}."

    try:
        build_s3_uploader(settings)
    except RuntimeError as exc:
        return False, str(exc)

    return True, "S3 remote upload is configured."


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


class LocalArchiveAdapter:
    archive_type = "local-archive"
    mode = "mirror"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def write(self, artifact: ArtifactModel, source_file: Path) -> ArchiveWriteResult:
        destination = self.settings.archive_root / self.archive_type / artifact.artifact_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_file, destination)
        return ArchiveWriteResult(
            archive_type=self.archive_type,
            archive_path=destination.relative_to(self.settings.archive_root).as_posix(),
            index_key=f"{self.archive_type}:{artifact.id}",
            public_url=None,
        )

    def describe(self) -> dict:
        return {
            "archive_type": self.archive_type,
            "mode": self.mode,
            "location": (self.settings.archive_root / self.archive_type).as_posix(),
            "remote_base_url": None,
            "is_ready": True,
            "readiness_reason": "Local archive mirror directory is available.",
        }


class ObjectStorageArchiveAdapter:
    archive_type = "object-storage"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.mode = settings.object_storage_mode

    def write(self, artifact: ArtifactModel, source_file: Path) -> ArchiveWriteResult:
        bucket = resolve_object_storage_bucket(self.settings)
        object_key = Path(artifact.artifact_path)

        if self.mode == "s3":
            uploader = build_s3_uploader(self.settings)
            uploader.put_object(
                bucket=bucket,
                object_key=object_key.as_posix(),
                body=source_file.read_bytes(),
                content_type=getattr(artifact, "mime_type", None),
            )
        else:
            mirror_path = Path(bucket) / object_key
            destination = self.settings.object_storage_root / mirror_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_file, destination)

        archive_path = f"{bucket}/{object_key.as_posix()}"
        if self.settings.object_storage_public_base_url:
            public_url = f"{self.settings.object_storage_public_base_url.rstrip('/')}/{archive_path}"
        else:
            public_url = f"s3://{archive_path}"

        return ArchiveWriteResult(
            archive_type=self.archive_type,
            archive_path=archive_path,
            index_key=f"{self.archive_type}:{artifact.id}",
            public_url=public_url,
        )

    def describe(self) -> dict:
        if self.mode == "s3":
            is_ready, readiness_reason = validate_s3_upload_config(self.settings)
            bucket = resolve_object_storage_bucket(self.settings)
            return {
                "archive_type": self.archive_type,
                "mode": self.mode,
                "location": self.settings.s3_endpoint or "remote-s3",
                "remote_base_url": self.settings.object_storage_public_base_url or (f"s3://{bucket}" if bucket else None),
                "is_ready": is_ready,
                "readiness_reason": readiness_reason,
            }

        bucket = resolve_object_storage_bucket(self.settings)
        return {
            "archive_type": self.archive_type,
            "mode": self.mode,
            "location": self.settings.object_storage_root.as_posix(),
            "remote_base_url": self.settings.object_storage_public_base_url
            or f"s3://{bucket}",
            "is_ready": bool(bucket),
            "readiness_reason": "Bucket and mirror root are configured."
            if bucket
            else "OBJECT_STORAGE_BUCKET is missing.",
        }


class QuarkPanArchiveAdapter:
    archive_type = "quark-pan"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.mode = settings.quark_pan_mode

    def write(self, artifact: ArtifactModel, source_file: Path) -> ArchiveWriteResult:
        remote_path = f"{self.settings.quark_pan_root_folder}/{artifact.artifact_path}"
        if self.mode == "api":
            uploader = build_quark_pan_remote_uploader(self.settings)
            uploader.upload(remote_path=remote_path, source_file=source_file, content_type=getattr(artifact, "mime_type", None))
            archive_path = artifact.artifact_path
        else:
            destination = self.settings.quark_pan_mirror_root / artifact.artifact_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_file, destination)
            archive_path = destination.relative_to(self.settings.quark_pan_mirror_root).as_posix()
        return ArchiveWriteResult(
            archive_type=self.archive_type,
            archive_path=archive_path,
            index_key=f"{self.archive_type}:{artifact.id}",
            public_url=f"quark://{remote_path}",
        )

    def describe(self) -> dict:
        if self.mode == "api":
            is_ready, readiness_reason = validate_quark_pan_api_config(self.settings)
            return {
                "archive_type": self.archive_type,
                "mode": self.mode,
                "location": self.settings.quark_pan_config_dir.as_posix(),
                "remote_base_url": f"quark://{self.settings.quark_pan_root_folder}",
                "is_ready": is_ready,
                "readiness_reason": readiness_reason,
            }
        return {
            "archive_type": self.archive_type,
            "mode": self.mode,
            "location": self.settings.quark_pan_mirror_root.as_posix(),
            "remote_base_url": f"quark://{self.settings.quark_pan_root_folder}",
            "is_ready": bool(self.settings.quark_pan_root_folder),
            "readiness_reason": "Quark Pan mirror root is configured."
            if self.settings.quark_pan_root_folder
            else "QUARK_PAN_ROOT_FOLDER is missing.",
        }


class AliyunDriveArchiveAdapter:
    archive_type = "aliyundrive"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.mode = settings.aliyundrive_mode

    def write(self, artifact: ArtifactModel, source_file: Path) -> ArchiveWriteResult:
        remote_path = f"{self.settings.aliyundrive_root_folder}/{artifact.artifact_path}"
        if self.mode == "api":
            uploader = build_aliyundrive_remote_uploader(self.settings)
            uploader.upload(remote_path=remote_path, source_file=source_file, content_type=getattr(artifact, "mime_type", None))
            archive_path = artifact.artifact_path
        else:
            destination = self.settings.aliyundrive_mirror_root / artifact.artifact_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_file, destination)
            archive_path = destination.relative_to(self.settings.aliyundrive_mirror_root).as_posix()
        return ArchiveWriteResult(
            archive_type=self.archive_type,
            archive_path=archive_path,
            index_key=f"{self.archive_type}:{artifact.id}",
            public_url=f"aliyundrive://{remote_path}",
        )

    def describe(self) -> dict:
        if self.mode == "api":
            is_ready, readiness_reason = validate_aliyundrive_api_config(self.settings)
            return {
                "archive_type": self.archive_type,
                "mode": self.mode,
                "location": self.settings.aliyundrive_config_dir.as_posix(),
                "remote_base_url": f"aliyundrive://{self.settings.aliyundrive_root_folder}",
                "is_ready": is_ready,
                "readiness_reason": readiness_reason,
            }
        return {
            "archive_type": self.archive_type,
            "mode": self.mode,
            "location": self.settings.aliyundrive_mirror_root.as_posix(),
            "remote_base_url": f"aliyundrive://{self.settings.aliyundrive_root_folder}",
            "is_ready": bool(self.settings.aliyundrive_root_folder),
            "readiness_reason": "AliyunDrive mirror root is configured."
            if self.settings.aliyundrive_root_folder
            else "ALIYUNDRIVE_ROOT_FOLDER is missing.",
        }
