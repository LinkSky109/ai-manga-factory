from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SharedMemoryCreateRequest(BaseModel):
    project_id: int | None = None
    scope_type: str = Field(min_length=1, max_length=32)
    scope_key: str = Field(min_length=1, max_length=120)
    memory_type: str = Field(min_length=1, max_length=32)
    content: dict = Field(default_factory=dict)


class SharedMemoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int | None
    scope_type: str
    scope_key: str
    memory_type: str
    content: dict
    created_at: datetime
    updated_at: datetime
