from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    actor_user_id: int | None
    actor_email: str | None
    actor_role: str | None
    action: str
    resource_type: str
    resource_id: str | None
    request_method: str
    request_path: str
    response_status: int
    outcome: str
    detail: dict
    created_at: datetime
    updated_at: datetime


class AuditLogListResponse(BaseModel):
    items: list[AuditLogResponse] = Field(default_factory=list)
