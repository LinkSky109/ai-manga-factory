from fastapi import APIRouter

from src.api.schemas.health import HealthResponse
from src.core.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def healthcheck() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        environment=settings.environment,
    )
