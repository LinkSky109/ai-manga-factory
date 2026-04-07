from functools import lru_cache
from pathlib import Path
import os

from pydantic import BaseModel, Field


REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_DATA_ROOT = REPO_ROOT / "data"
DEFAULT_RUNTIME_ROOT = DEFAULT_DATA_ROOT / "runtime"
DEFAULT_SECRETS_ROOT = REPO_ROOT / "secrets"


def _env_flag(key: str, default: bool) -> bool:
    raw = os.getenv(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class Settings(BaseModel):
    app_name: str = Field(default="AI Manga Factory")
    environment: str = Field(default_factory=lambda: os.getenv("APP_ENV", "development"))
    api_host: str = Field(default_factory=lambda: os.getenv("API_HOST", "0.0.0.0"))
    api_port: int = Field(default_factory=lambda: int(os.getenv("API_PORT", "8000")))
    database_url: str = Field(
        default_factory=lambda: os.getenv(
            "DATABASE_URL",
            f"sqlite+pysqlite:///{(DEFAULT_RUNTIME_ROOT / 'ai_manga_factory.db').as_posix()}",
        )
    )
    artifact_root: Path = Field(
        default_factory=lambda: Path(os.getenv("ARTIFACT_ROOT", str(DEFAULT_RUNTIME_ROOT / "artifacts")))
    )
    archive_root: Path = Field(
        default_factory=lambda: Path(os.getenv("ARCHIVE_ROOT", str(DEFAULT_DATA_ROOT / "archives")))
    )
    archive_targets: tuple[str, ...] = Field(
        default_factory=lambda: tuple(
            item.strip()
            for item in os.getenv("ARCHIVE_TARGETS", "local-archive,object-storage").split(",")
            if item.strip()
        )
    )
    archive_index_path: Path = Field(
        default_factory=lambda: Path(
            os.getenv("ARCHIVE_INDEX_PATH", str(DEFAULT_DATA_ROOT / "archives" / "index" / "artifact-manifest.json"))
        )
    )
    preview_root: Path = Field(
        default_factory=lambda: Path(os.getenv("PREVIEW_ROOT", str(DEFAULT_RUNTIME_ROOT / "previews")))
    )
    object_storage_root: Path = Field(
        default_factory=lambda: Path(
            os.getenv("OBJECT_STORAGE_ROOT", str(DEFAULT_DATA_ROOT / "archives" / "object-storage"))
        )
    )
    object_storage_mode: str = Field(default_factory=lambda: os.getenv("OBJECT_STORAGE_MODE", "mirror"))
    object_storage_bucket: str = Field(default_factory=lambda: os.getenv("OBJECT_STORAGE_BUCKET", "ai-manga-factory"))
    object_storage_public_base_url: str | None = Field(
        default_factory=lambda: os.getenv("OBJECT_STORAGE_PUBLIC_BASE_URL") or None
    )
    s3_endpoint: str | None = Field(default_factory=lambda: os.getenv("S3_ENDPOINT") or None)
    s3_bucket: str | None = Field(default_factory=lambda: os.getenv("S3_BUCKET") or None)
    s3_access_key_id: str | None = Field(default_factory=lambda: os.getenv("S3_ACCESS_KEY_ID") or None)
    s3_secret_access_key: str | None = Field(default_factory=lambda: os.getenv("S3_SECRET_ACCESS_KEY") or None)
    s3_region: str = Field(default_factory=lambda: os.getenv("S3_REGION", "us-east-1"))
    ark_api_key: str | None = Field(default_factory=lambda: os.getenv("ARK_API_KEY") or os.getenv("VOLC_ARK_API_KEY") or None)
    ark_base_url: str | None = Field(default_factory=lambda: os.getenv("ARK_BASE_URL") or None)
    ark_text_model: str = Field(default_factory=lambda: os.getenv("ARK_TEXT_MODEL", "Doubao-Seed-1.6"))
    ark_image_model: str = Field(default_factory=lambda: os.getenv("ARK_IMAGE_MODEL", "Doubao-Seedream-4.5"))
    ark_video_model: str = Field(default_factory=lambda: os.getenv("ARK_VIDEO_MODEL", "Doubao-Seedance-1.5-pro"))
    quark_pan_mirror_root: Path = Field(
        default_factory=lambda: Path(os.getenv("QUARK_PAN_MIRROR_ROOT", str(DEFAULT_DATA_ROOT / "archives" / "quark-pan")))
    )
    quark_pan_mode: str = Field(default_factory=lambda: os.getenv("QUARK_PAN_MODE", "mirror"))
    quark_pan_config_dir: Path = Field(
        default_factory=lambda: Path(os.getenv("QUARK_PAN_CONFIG_DIR", str(DEFAULT_SECRETS_ROOT / "quark_pan")))
    )
    quark_pan_cookie_file: Path = Field(
        default_factory=lambda: Path(os.getenv("QUARK_PAN_COOKIE_FILE", str(DEFAULT_SECRETS_ROOT / "quark_pan_cookie.txt")))
    )
    quark_pan_root_folder: str = Field(default_factory=lambda: os.getenv("QUARK_PAN_ROOT_FOLDER", "AI-Manga-Factory"))
    quark_pan_replace_existing: bool = Field(default_factory=lambda: _env_flag("QUARK_PAN_REPLACE_EXISTING", True))
    aliyundrive_mirror_root: Path = Field(
        default_factory=lambda: Path(
            os.getenv("ALIYUNDRIVE_MIRROR_ROOT", str(DEFAULT_DATA_ROOT / "archives" / "aliyundrive"))
        )
    )
    aliyundrive_mode: str = Field(default_factory=lambda: os.getenv("ALIYUNDRIVE_MODE", "mirror"))
    aliyundrive_config_dir: Path = Field(
        default_factory=lambda: Path(os.getenv("ALIYUNDRIVE_CONFIG_DIR", str(DEFAULT_SECRETS_ROOT / "aliyundrive")))
    )
    aliyundrive_name: str = Field(default_factory=lambda: os.getenv("ALIYUNDRIVE_NAME", "ai-manga-factory"))
    aliyundrive_root_folder: str = Field(
        default_factory=lambda: os.getenv("ALIYUNDRIVE_ROOT_FOLDER", "AI-Manga-Factory")
    )
    aliyundrive_check_name_mode: str = Field(
        default_factory=lambda: os.getenv("ALIYUNDRIVE_CHECK_NAME_MODE", "overwrite")
    )
    archive_sync_max_attempts: int = Field(
        default_factory=lambda: max(1, int(os.getenv("ARCHIVE_SYNC_MAX_ATTEMPTS", "3")))
    )
    routing_mode: str = Field(default_factory=lambda: os.getenv("DEFAULT_ROUTING_MODE", "smart"))
    default_image_provider: str = Field(default_factory=lambda: os.getenv("DEFAULT_IMAGE_PROVIDER", "kling"))
    default_video_provider: str = Field(default_factory=lambda: os.getenv("DEFAULT_VIDEO_PROVIDER", "vidu"))
    default_voice_provider: str = Field(default_factory=lambda: os.getenv("DEFAULT_VOICE_PROVIDER", "voice_clone"))
    auth_enabled: bool = Field(default_factory=lambda: _env_flag("AUTH_ENABLED", any(
        os.getenv(key) for key in (
            "AUTH_BOOTSTRAP_ADMIN_TOKEN",
            "AUTH_BOOTSTRAP_OPERATOR_TOKEN",
            "AUTH_BOOTSTRAP_REVIEWER_TOKEN",
            "AUTH_BOOTSTRAP_VIEWER_TOKEN",
        )
    )))
    security_tokens: dict[str, str | None] = Field(
        default_factory=lambda: {
            "admin": os.getenv("AUTH_BOOTSTRAP_ADMIN_TOKEN") or None,
            "operator": os.getenv("AUTH_BOOTSTRAP_OPERATOR_TOKEN") or None,
            "reviewer": os.getenv("AUTH_BOOTSTRAP_REVIEWER_TOKEN") or None,
            "viewer": os.getenv("AUTH_BOOTSTRAP_VIEWER_TOKEN") or None,
        }
    )
    security_emails: dict[str, str | None] = Field(
        default_factory=lambda: {
            "admin": os.getenv("AUTH_BOOTSTRAP_ADMIN_EMAIL") or None,
            "operator": os.getenv("AUTH_BOOTSTRAP_OPERATOR_EMAIL") or None,
            "reviewer": os.getenv("AUTH_BOOTSTRAP_REVIEWER_EMAIL") or None,
            "viewer": os.getenv("AUTH_BOOTSTRAP_VIEWER_EMAIL") or None,
        }
    )
    security_names: dict[str, str | None] = Field(
        default_factory=lambda: {
            "admin": os.getenv("AUTH_BOOTSTRAP_ADMIN_NAME") or None,
            "operator": os.getenv("AUTH_BOOTSTRAP_OPERATOR_NAME") or None,
            "reviewer": os.getenv("AUTH_BOOTSTRAP_REVIEWER_NAME") or None,
            "viewer": os.getenv("AUTH_BOOTSTRAP_VIEWER_NAME") or None,
        }
    )
    worker_stale_after_seconds: int = Field(
        default_factory=lambda: max(5, int(os.getenv("WORKER_STALE_AFTER_SECONDS", "30")))
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.artifact_root.mkdir(parents=True, exist_ok=True)
    settings.archive_root.mkdir(parents=True, exist_ok=True)
    settings.archive_index_path.parent.mkdir(parents=True, exist_ok=True)
    settings.object_storage_root.mkdir(parents=True, exist_ok=True)
    settings.quark_pan_mirror_root.mkdir(parents=True, exist_ok=True)
    settings.aliyundrive_mirror_root.mkdir(parents=True, exist_ok=True)
    settings.quark_pan_config_dir.mkdir(parents=True, exist_ok=True)
    settings.aliyundrive_config_dir.mkdir(parents=True, exist_ok=True)
    settings.quark_pan_cookie_file.parent.mkdir(parents=True, exist_ok=True)
    settings.preview_root.mkdir(parents=True, exist_ok=True)
    return settings


def reset_settings_cache() -> None:
    get_settings.cache_clear()
