from pydantic import BaseModel, Field


class StorageTargetResponse(BaseModel):
    archive_type: str
    mode: str
    location: str
    remote_base_url: str | None = None
    is_ready: bool
    readiness_reason: str


class StorageTargetListResponse(BaseModel):
    items: list[StorageTargetResponse] = Field(default_factory=list)


class ArtifactArchiveBatchSyncResponse(BaseModel):
    project_id: int
    synced_artifacts: int
    restored_targets: int
