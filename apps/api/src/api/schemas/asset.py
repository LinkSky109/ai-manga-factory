from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CharacterReferenceImageInput(BaseModel):
    view_type: str = Field(min_length=1, max_length=32)
    asset_path: str = Field(min_length=1, max_length=255)
    notes: str | None = Field(default=None, max_length=500)


class CharacterProfileCreateRequest(BaseModel):
    project_id: int
    name: str = Field(min_length=1, max_length=120)
    appearance: str = Field(min_length=1)
    personality: str = Field(min_length=1)
    lora_path: str | None = Field(default=None, max_length=255)
    reference_images: list[CharacterReferenceImageInput] = Field(default_factory=list)


class CharacterReferenceImageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    view_type: str
    asset_path: str
    notes: str | None
    created_at: datetime
    updated_at: datetime


class CharacterProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    name: str
    appearance: str
    personality: str
    lora_path: str | None
    review_status: str
    reference_images: list[CharacterReferenceImageResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class VoiceProfileCreateRequest(BaseModel):
    project_id: int
    character_name: str = Field(min_length=1, max_length=120)
    voice_key: str = Field(min_length=1, max_length=120)
    provider_key: str = Field(min_length=1, max_length=120)
    tone_description: str = Field(min_length=1)


class VoiceProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    character_name: str
    voice_key: str
    provider_key: str
    tone_description: str
    created_at: datetime
    updated_at: datetime


class SceneProfileCreateRequest(BaseModel):
    project_id: int
    name: str = Field(min_length=1, max_length=120)
    baseline_prompt: str = Field(min_length=1)
    continuity_guardrails: str | None = Field(default=None)


class SceneProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    name: str
    baseline_prompt: str
    continuity_guardrails: str | None
    review_status: str
    created_at: datetime
    updated_at: datetime


class ArtifactArchiveResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    archive_type: str
    archive_path: str
    index_key: str
    status: str
    remote_url: str | None
    checksum_sha256: str | None
    created_at: datetime
    updated_at: datetime


class ArtifactSyncRunCreateRequest(BaseModel):
    archive_types: list[str] = Field(min_length=1)


class ArtifactSyncRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    artifact_id: int
    archive_type: str
    status: str
    summary: str | None
    error_message: str | None
    worker_id: str | None
    attempt_count: int
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ArtifactSyncRunListResponse(BaseModel):
    items: list[ArtifactSyncRunResponse] = Field(default_factory=list)


class ArtifactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    chapter_id: int | None
    job_run_id: int
    step_key: str
    title: str
    media_kind: str
    provider_key: str | None
    status: str
    mime_type: str
    artifact_path: str
    preview_path: str
    preview_url: str
    size_bytes: int | None
    artifact_metadata: dict
    archives: list[ArtifactArchiveResponse] = Field(default_factory=list)
    sync_runs: list[ArtifactSyncRunResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
