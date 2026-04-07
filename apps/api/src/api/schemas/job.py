from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class JobCreateRequest(BaseModel):
    project_id: int
    workflow_id: int
    chapter_id: int | None = None
    execution_mode: str = Field(default="sync", pattern="^(sync|async)$")
    routing_mode: str | None = Field(default=None, max_length=32)
    input: dict = Field(default_factory=dict)


class JobResumeRequest(BaseModel):
    override_input: dict = Field(default_factory=dict)


class JobStepResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sequence_no: int
    step_key: str
    step_name: str
    provider_type: str
    provider_key: str | None
    status: str
    usage_amount: float | None
    usage_unit: str | None
    output_snapshot: dict | None = None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class JobCheckpointResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    step_key: str
    payload: dict
    resume_cursor: str | None
    created_at: datetime
    updated_at: datetime


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    chapter_id: int | None
    workflow_id: int | None
    execution_mode: str
    routing_mode: str
    status: str
    current_step_key: str | None
    summary: str | None
    error_message: str | None
    request_payload: dict
    queued_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None
    locked_at: datetime | None
    last_heartbeat_at: datetime | None
    worker_id: str | None
    attempt_count: int
    steps: list[JobStepResponse] = Field(default_factory=list)
    checkpoints: list[JobCheckpointResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ProjectPreviewItemResponse(BaseModel):
    id: str
    artifact_id: int
    job_id: int
    chapter_id: int | None
    stage_key: str
    title: str
    media_kind: str
    status: str
    provider_key: str | None
    mime_type: str | None = None
    archive_status: str | None = None
    archive_targets: list[str] = Field(default_factory=list)
    playback_url: str | None
    playback_hint: str
    updated_at: datetime


class ProjectPreviewListResponse(BaseModel):
    items: list[ProjectPreviewItemResponse] = Field(default_factory=list)
