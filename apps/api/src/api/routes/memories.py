from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from src.api.schemas.memory import SharedMemoryCreateRequest, SharedMemoryResponse
from src.application.services.memory_service import MemoryService
from src.core.dependencies import get_db_session

router = APIRouter(prefix="/memories", tags=["memories"])


@router.get("", response_model=list[SharedMemoryResponse])
def list_memories(
    project_id: int | None = Query(default=None),
    session: Session = Depends(get_db_session),
) -> list[SharedMemoryResponse]:
    service = MemoryService(session)
    return [SharedMemoryResponse.model_validate(item) for item in service.list_memories(project_id=project_id)]


@router.post("", response_model=SharedMemoryResponse, status_code=status.HTTP_201_CREATED)
def create_memory(
    request: SharedMemoryCreateRequest,
    session: Session = Depends(get_db_session),
) -> SharedMemoryResponse:
    service = MemoryService(session)
    memory = service.create_memory(**request.model_dump())
    return SharedMemoryResponse.model_validate(memory)
