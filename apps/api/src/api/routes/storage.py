from fastapi import APIRouter

from src.api.schemas.storage import StorageTargetListResponse, StorageTargetResponse
from src.infrastructure.storage.archive_registry import build_archive_adapters

router = APIRouter(prefix="/storage", tags=["storage"])


@router.get("/targets", response_model=StorageTargetListResponse)
def list_storage_targets() -> StorageTargetListResponse:
    items = [StorageTargetResponse.model_validate(adapter.describe()) for adapter in build_archive_adapters()]
    return StorageTargetListResponse(items=items)
