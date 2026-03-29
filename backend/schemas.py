from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


JobStatus = Literal["pending", "planned", "running", "completed", "failed"]


class CapabilityField(BaseModel):
    key: str
    label: str
    required: bool = True
    field_type: str = "string"
    description: str


class CapabilityDescriptor(BaseModel):
    id: str
    name: str
    description: str
    category: str
    outputs: list[str]
    input_fields: list[CapabilityField]


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)


class ProjectResponse(BaseModel):
    id: int
    name: str
    description: str | None = None
    created_at: datetime


class JobCreate(BaseModel):
    capability_id: str
    project_id: int | None = None
    project_name: str | None = Field(default=None, min_length=1, max_length=120)
    input: dict[str, Any] = Field(default_factory=dict)


class WorkflowStep(BaseModel):
    key: str
    title: str
    description: str
    status: Literal["pending", "running", "completed", "failed"] = "pending"
    details: str | None = None


class ArtifactPreview(BaseModel):
    artifact_type: str
    label: str
    path_hint: str | None = None


class ArtifactInventoryItemResponse(BaseModel):
    key: str
    url: str
    label: str
    file_name: str
    kind: str
    source: Literal["job", "pack"]
    source_label: str
    path_hint: str | None = None
    byte_size: int | None = None
    updated_at: str | None = None
    status: str | None = None


class ArtifactInventoryResponse(BaseModel):
    items: list[ArtifactInventoryItemResponse] = Field(default_factory=list)


class ArtifactSyncProviderResponse(BaseModel):
    provider: str
    display_name: str
    status: Literal["uploaded", "synced", "missing"]
    updated_at: str | None = None
    dry_run: bool = False
    remote_path: str | None = None
    remote_dir: str | None = None
    provider_home_url: str | None = None
    file_web_url: str | None = None
    note: str | None = None
    root_folder: str | None = None


class ArtifactSyncStatusResponse(BaseModel):
    artifact_url: str
    local_path: str | None = None
    providers: list[ArtifactSyncProviderResponse] = Field(default_factory=list)


class CloudSyncOverviewProviderResponse(BaseModel):
    provider: str
    display_name: str
    updated_at: str | None = None
    dry_run: bool = False
    root_folder: str | None = None
    business_folder: str | None = None
    pack_reports_folder: str | None = None
    uploaded_count: int = 0
    synced_count: int = 0
    pending_count: int = 0
    provider_home_url: str | None = None
    note: str | None = None


class CloudSyncOverviewResponse(BaseModel):
    runtime_provider: str
    remote_sync_enabled: bool
    remote_sync_provider: str
    providers: list[CloudSyncOverviewProviderResponse] = Field(default_factory=list)


class JobSyncProviderResponse(BaseModel):
    provider: str
    display_name: str
    status: Literal["uploaded", "synced", "missing"]
    updated_at: str | None = None
    matched_files: int = 0
    remote_dirs: list[str] = Field(default_factory=list)
    provider_home_url: str | None = None
    note: str | None = None


class JobSyncStatusResponse(BaseModel):
    job_id: int
    local_roots: list[str] = Field(default_factory=list)
    providers: list[JobSyncProviderResponse] = Field(default_factory=list)


class JobSyncTriggerRequest(BaseModel):
    provider: Literal["quark_pan", "aliyundrive", "all"] = "all"
    dry_run: bool = False


class JobSyncTriggerItemResponse(BaseModel):
    provider: str
    dry_run: bool = False
    planned: int = 0
    pending: int = 0
    uploaded: int = 0
    skipped: int = 0
    updated_at: str | None = None
    note: str | None = None


class JobSyncTriggerResponse(BaseModel):
    job_id: int
    items: list[JobSyncTriggerItemResponse] = Field(default_factory=list)


class BatchSyncStorageRequest(BaseModel):
    job_ids: list[int] = Field(default_factory=list, min_length=1)
    provider: Literal["quark_pan", "aliyundrive", "all"] = "all"
    dry_run: bool = False


class BatchSyncStorageResponse(BaseModel):
    job_ids: list[int] = Field(default_factory=list)
    items: list[JobSyncTriggerItemResponse] = Field(default_factory=list)


class CloudSyncTaskResponse(BaseModel):
    id: str
    scope: Literal["job", "batch"]
    provider: Literal["quark_pan", "aliyundrive", "all"]
    job_ids: list[int] = Field(default_factory=list)
    status: Literal["queued", "running", "completed", "failed"]
    dry_run: bool = False
    created_at: str
    updated_at: str
    note: str | None = None
    items: list[JobSyncTriggerItemResponse] = Field(default_factory=list)
    error: str | None = None


class CloudSyncTaskListResponse(BaseModel):
    items: list[CloudSyncTaskResponse] = Field(default_factory=list)


class JobResponse(BaseModel):
    id: int
    project_id: int
    project_name: str | None = None
    capability_id: str
    status: JobStatus
    input: dict[str, Any]
    workflow: list[WorkflowStep]
    artifacts: list[ArtifactPreview]
    summary: str
    error: str | None = None
    created_at: datetime
    updated_at: datetime


class JobListResponse(BaseModel):
    items: list[JobResponse]


class JobSummaryBucketResponse(BaseModel):
    key: str
    label: str
    count: int


class JobSummaryResponse(BaseModel):
    totals: dict[str, int] = Field(default_factory=dict)
    by_status: list[JobSummaryBucketResponse] = Field(default_factory=list)
    by_capability: list[JobSummaryBucketResponse] = Field(default_factory=list)


class BatchRetryRequest(BaseModel):
    job_ids: list[int] = Field(default_factory=list, min_length=1)


class BatchRetryResponse(BaseModel):
    requested: int
    created: int
    items: list[JobResponse] = Field(default_factory=list)


class BatchJobResponse(BaseModel):
    job_id: int
    chapter_range: str
    chapter_count: int
    status: JobStatus


class AdaptationPackResponse(BaseModel):
    pack_name: str
    source_title: str
    chapter_range: str
    chapter_count: int
    default_project_name: str
    default_scene_count: int


class AdaptationPackLatestResultResponse(BaseModel):
    pack_name: str
    job_id: int
    project_name: str | None = None
    capability_id: str | None = None
    status: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    validation_status: str | None = None
    validation_passed: int | None = None
    validation_total: int | None = None
    source: Literal["pointer", "scan-fallback"]
    artifact_summary_url: str
    artifact_validation_url: str
    artifact_snapshot_url: str
    pack_summary_url: str | None = None
    pack_validation_url: str | None = None
    shared_summary_url: str | None = None
    shared_validation_url: str | None = None


class AdaptationJobRequest(BaseModel):
    project_name: str | None = Field(default=None, min_length=1, max_length=120)
    scene_count: int = Field(default=20, ge=2, le=60)
    target_duration_seconds: float | None = Field(default=None, ge=20, le=180)
    chapter_keyframe_count: int | None = Field(default=4, ge=3, le=6)
    chapter_shot_count: int | None = Field(default=10, ge=8, le=12)
    use_model_storyboard: bool = False
    use_real_images: bool = False
    image_model: str | None = Field(default=None, max_length=120)
    video_model: str | None = Field(default=None, max_length=120)
    chapter_start: int | None = Field(default=None, ge=1)
    chapter_end: int | None = Field(default=None, ge=1)


class AdaptationBatchRequest(BaseModel):
    project_name: str | None = Field(default=None, min_length=1, max_length=120)
    batch_size: int = Field(default=5, ge=1, le=20)
    scene_count: int = Field(default=2, ge=2, le=60)
    target_duration_seconds: float | None = Field(default=None, ge=20, le=180)
    chapter_keyframe_count: int | None = Field(default=4, ge=3, le=6)
    chapter_shot_count: int | None = Field(default=10, ge=8, le=12)
    use_model_storyboard: bool = False
    use_real_images: bool = False
    image_model: str | None = Field(default=None, max_length=120)
    video_model: str | None = Field(default=None, max_length=120)


class AdaptationBatchResponse(BaseModel):
    pack_name: str
    source_title: str
    project_name: str
    total_batches: int
    items: list[BatchJobResponse] = Field(default_factory=list)


class ProviderModelUsageResponse(BaseModel):
    name: str
    label: str
    priority: int
    enabled: bool
    budget_limit: float | None = None
    usage_value: float
    usage_ratio: float
    usage_unit: str
    status: Literal["healthy", "warning", "switch", "exhausted", "disabled"]
    request_count: int
    success_count: int
    failure_count: int
    input_estimated_tokens: int = 0
    output_estimated_tokens: int = 0
    last_used_at: str | None = None
    last_error: str | None = None
    exhausted_until: str | None = None


class ProviderCapabilityUsageResponse(BaseModel):
    capability: Literal["text", "image", "video"]
    usage_unit: str
    warning_ratio: float
    switch_ratio: float
    active_model: str | None = None
    last_routing: dict[str, Any] = Field(default_factory=dict)
    recent_events: list[dict[str, Any]] = Field(default_factory=list)
    models: list[ProviderModelUsageResponse] = Field(default_factory=list)


class ProviderUsageResponse(BaseModel):
    provider: str
    display_name: str
    config_path: str
    ledger_path: str
    period_key: str
    updated_at: str
    measurement_note: str
    capabilities: list[ProviderCapabilityUsageResponse] = Field(default_factory=list)


class StageModelPlanStageResponse(BaseModel):
    stage: str
    entrypoints: list[str] = Field(default_factory=list)
    uses_model: bool
    current_default: str | None = None
    fallbacks: list[str] = Field(default_factory=list)
    cost_effectiveness: str
    coding_plan_pro_fit: str
    notes: str


class StageModelPlanStrategyResponse(BaseModel):
    name: str
    description: str


class StageModelPlanResponse(BaseModel):
    updated_at: str
    project: str
    strategy: StageModelPlanStrategyResponse
    pipeline: list[StageModelPlanStageResponse] = Field(default_factory=list)


class UiPreferencesResponse(BaseModel):
    density_mode: Literal["comfortable", "balanced", "compact"] = "balanced"
    updated_at: str | None = None


class UiPreferencesUpdate(BaseModel):
    density_mode: Literal["comfortable", "balanced", "compact"]
