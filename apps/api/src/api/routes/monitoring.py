from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.api.schemas.monitoring import (
    MonitoringAlertResponse,
    MonitoringOverviewResponse,
    MonitoringSummaryResponse,
    ProviderUsageItemResponse,
    ProviderUsageListResponse,
    WorkerHeartbeatResponse,
)
from src.application.queries.monitoring import MonitoringQueryService
from src.core.dependencies import get_db_session

router = APIRouter(prefix="/monitoring", tags=["monitoring"])


@router.get("/providers", response_model=ProviderUsageListResponse)
def provider_monitoring(session: Session = Depends(get_db_session)) -> ProviderUsageListResponse:
    service = MonitoringQueryService(session)
    items = [ProviderUsageItemResponse.model_validate(item) for item in service.provider_usage()]
    session.commit()
    return ProviderUsageListResponse(items=items)


@router.get("/overview", response_model=MonitoringOverviewResponse)
def monitoring_overview(session: Session = Depends(get_db_session)) -> MonitoringOverviewResponse:
    service = MonitoringQueryService(session)
    overview = service.overview()
    session.commit()
    return MonitoringOverviewResponse(
        items=[ProviderUsageItemResponse.model_validate(item) for item in overview["items"]],
        alerts=[MonitoringAlertResponse.model_validate(item, from_attributes=True) for item in overview["alerts"]],
        workers=[WorkerHeartbeatResponse.model_validate(item) for item in overview["workers"]],
        summary=MonitoringSummaryResponse.model_validate(overview["summary"]),
    )
