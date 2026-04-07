from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ReviewTaskCreateRequest(BaseModel):
    project_id: int | None = None
    chapter_id: int | None = None
    review_stage: str = Field(min_length=1, max_length=32)
    review_type: str = Field(min_length=1, max_length=32)
    assigned_agents: list[str] = Field(default_factory=list)
    checklist: list[str] = Field(default_factory=list)
    findings_summary: str | None = None
    result_payload: dict = Field(default_factory=dict)
    auto_run: bool = True
    routing_mode: str = Field(default="smart", min_length=1, max_length=32)
    manual_provider: str | None = Field(default=None, min_length=1, max_length=120)


class ReviewTaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int | None
    chapter_id: int | None
    review_stage: str
    review_type: str
    status: str
    assigned_agents: list[str]
    checklist: list[str]
    findings_summary: str | None
    result_payload: dict
    created_at: datetime
    updated_at: datetime
