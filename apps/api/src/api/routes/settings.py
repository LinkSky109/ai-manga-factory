from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.api.schemas.settings import (
    BootstrapAccountResponse,
    ProviderConfigResponse,
    ProviderConfigUpdateRequest,
    SettingsAuthOverviewResponse,
    SettingsOverviewResponse,
    SettingsRuntimeOverviewResponse,
)
from src.api.schemas.storage import StorageTargetResponse
from src.core.config import get_settings
from src.core.dependencies import get_db_session
from src.infrastructure.db.repositories.provider_repository import ProviderRepository
from src.infrastructure.db.repositories.security_repository import SecurityRepository
from src.infrastructure.storage.archive_registry import build_archive_adapters

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/overview", response_model=SettingsOverviewResponse)
def get_settings_overview(session: Session = Depends(get_db_session)) -> SettingsOverviewResponse:
    settings = get_settings()
    security = SecurityRepository(session)
    providers = ProviderRepository(session)
    return SettingsOverviewResponse(
        auth=SettingsAuthOverviewResponse(
            enabled=settings.auth_enabled,
            bootstrap_accounts=[
                BootstrapAccountResponse.model_validate(item)
                for item in security.list_bootstrap_accounts()
            ],
        ),
        runtime=SettingsRuntimeOverviewResponse(
            environment=settings.environment,
            default_routing_mode=settings.routing_mode,
            archive_targets=list(settings.archive_targets),
            object_storage_mode=settings.object_storage_mode,
            quark_pan_mode=settings.quark_pan_mode,
            aliyundrive_mode=settings.aliyundrive_mode,
        ),
        storage_targets=[
            StorageTargetResponse.model_validate(adapter.describe())
            for adapter in build_archive_adapters(settings)
        ],
        providers=[
            ProviderConfigResponse.model_validate(item)
            for item in providers.list_provider_configs()
        ],
    )


@router.patch("/providers/{provider_key}", response_model=ProviderConfigResponse)
def update_provider_config(
    provider_key: str,
    request: ProviderConfigUpdateRequest,
    session: Session = Depends(get_db_session),
) -> ProviderConfigResponse:
    provider = ProviderRepository(session).update_provider_config(
        provider_key,
        is_enabled=request.is_enabled,
        priority=request.priority,
        budget_threshold=request.budget_threshold,
        routing_mode=request.routing_mode,
    )
    if provider is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found.")
    session.commit()
    session.refresh(provider)
    return ProviderConfigResponse.model_validate(provider)
