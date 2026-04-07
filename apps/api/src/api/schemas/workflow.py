from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from src.domain.workflow.specs import WorkflowEdgeSpec, WorkflowNodeSpec


class WorkflowCreateRequest(BaseModel):
    project_id: int
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    routing_mode: str = Field(default="smart", max_length=32)
    nodes: list[WorkflowNodeSpec] = Field(default_factory=list)
    edges: list[WorkflowEdgeSpec] = Field(default_factory=list)


class WorkflowUpdateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    routing_mode: str = Field(default="smart", max_length=32)
    nodes: list[WorkflowNodeSpec] = Field(default_factory=list)
    edges: list[WorkflowEdgeSpec] = Field(default_factory=list)


class WorkflowResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    name: str
    description: str | None
    routing_mode: str
    spec: dict
    created_at: datetime
    updated_at: datetime
