from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PromptFeedbackCreateRequest(BaseModel):
    project_id: int | None = None
    job_id: int | None = None
    workflow_key: str = Field(min_length=1, max_length=120)
    template_version: str = Field(min_length=1, max_length=32)
    template_body: str = Field(min_length=1)
    score: int = Field(ge=1, le=5)
    correction_summary: str = Field(min_length=1)
    corrected_prompt: str | None = None


class PromptFeedbackResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    prompt_template_id: int
    job_run_id: int | None
    score: int
    correction_summary: str
    corrected_prompt: str | None
    created_at: datetime
    updated_at: datetime


class PromptTemplateSummaryResponse(BaseModel):
    id: int
    project_id: int | None
    workflow_key: str
    template_version: str
    template_body: str
    feedback_count: int
    latest_score: int | None
    created_at: datetime
    updated_at: datetime
