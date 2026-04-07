from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from src.api.schemas.asset import CharacterProfileResponse, SceneProfileResponse


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    status: str
    created_at: datetime
    updated_at: datetime


class ChapterCreateRequest(BaseModel):
    chapter_number: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=160)
    summary: str | None = Field(default=None, max_length=1000)


class ChapterResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    chapter_number: int
    title: str
    summary: str | None
    status: str
    created_at: datetime
    updated_at: datetime


class ChapterPipelineStateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    stage_key: str
    status: str
    detail: str | None
    created_at: datetime
    updated_at: datetime


class ChapterDetailResponse(ChapterResponse):
    pipeline_states: list[ChapterPipelineStateResponse] = Field(default_factory=list)


class ProjectOverviewCard(BaseModel):
    label: str
    value: str
    tone: str = "neutral"


class ProjectOverviewResponse(BaseModel):
    project_name: str
    status: str
    summary: str
    chapter_progress: list[ProjectOverviewCard] = Field(default_factory=list)
    asset_health: list[ProjectOverviewCard] = Field(default_factory=list)
    provider_usage: list[ProjectOverviewCard] = Field(default_factory=list)
    initialization_progress: list[ProjectOverviewCard] = Field(default_factory=list)


class ProjectInitializationRequest(BaseModel):
    source_title: str = Field(min_length=1, max_length=160)
    source_type: str = Field(default="novel_text", min_length=1, max_length=32)
    source_text: str = Field(min_length=1, max_length=200000)
    overwrite_assets: bool = False
    routing_mode: str = Field(default="smart", min_length=1, max_length=32)
    manual_provider: str | None = Field(default=None, min_length=1, max_length=120)


class ProjectGenerationAttemptResponse(BaseModel):
    provider_key: str
    status: str
    error_message: str | None = None


class ProjectGenerationTraceResponse(BaseModel):
    generation_mode: str
    routing_mode: str
    manual_provider: str | None = None
    resolved_provider_key: str | None = None
    provider_candidates: list[str] = Field(default_factory=list)
    provider_attempts: list[ProjectGenerationAttemptResponse] = Field(default_factory=list)
    usage_amount: float | int = 0
    usage_unit: str = "tokens"


class ProjectSourceMaterialResponse(BaseModel):
    id: int
    project_id: int
    source_title: str
    source_type: str
    import_status: str
    chapter_count: int
    content_preview: str
    created_at: datetime
    updated_at: datetime


class ProjectStorySummaryResponse(BaseModel):
    id: int
    project_id: int
    status: str
    summary_body: str
    highlights: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ProjectScriptResponse(BaseModel):
    id: int
    project_id: int
    status: str
    title: str
    script_body: str
    created_at: datetime
    updated_at: datetime


class ProjectInitializationResponse(BaseModel):
    project_id: int
    status: str
    stage_cards: list[ProjectOverviewCard] = Field(default_factory=list)
    generation_trace: ProjectGenerationTraceResponse | None = None
    source: ProjectSourceMaterialResponse | None = None
    summary: ProjectStorySummaryResponse | None = None
    script: ProjectScriptResponse | None = None
    chapters: list[ChapterResponse] = Field(default_factory=list)
    character_drafts: list[CharacterProfileResponse] = Field(default_factory=list)
    scene_drafts: list[SceneProfileResponse] = Field(default_factory=list)
