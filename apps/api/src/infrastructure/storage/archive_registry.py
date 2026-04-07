from src.core.config import Settings, get_settings
from src.infrastructure.storage.archive_adapters import (
    AliyunDriveArchiveAdapter,
    LocalArchiveAdapter,
    ObjectStorageArchiveAdapter,
    QuarkPanArchiveAdapter,
)


def build_archive_adapters(settings: Settings | None = None) -> list:
    resolved_settings = settings or get_settings()
    registry = {
        "local-archive": lambda: LocalArchiveAdapter(resolved_settings),
        "object-storage": lambda: ObjectStorageArchiveAdapter(resolved_settings),
        "quark-pan": lambda: QuarkPanArchiveAdapter(resolved_settings),
        "aliyundrive": lambda: AliyunDriveArchiveAdapter(resolved_settings),
    }

    adapters = []
    for target in resolved_settings.archive_targets:
        factory = registry.get(target)
        if factory is None:
            raise ValueError(f"Unsupported archive target '{target}'.")
        adapters.append(factory())
    return adapters
