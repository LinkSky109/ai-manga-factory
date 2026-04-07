from fastapi import APIRouter, Depends

from src.api.schemas.auth import AuthMeResponse
from src.core.config import get_settings
from src.core.dependencies import get_request_actor

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=AuthMeResponse)
def get_auth_me(actor = Depends(get_request_actor)) -> AuthMeResponse:
    settings = get_settings()
    if actor is None:
        return AuthMeResponse(auth_enabled=settings.auth_enabled)
    return AuthMeResponse(
        auth_enabled=settings.auth_enabled,
        email=actor.email,
        display_name=actor.display_name,
        role=actor.role,
    )
