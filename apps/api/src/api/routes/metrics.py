from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from src.application.queries.monitoring import MonitoringQueryService
from src.core.dependencies import get_db_session
from src.infrastructure.observability.prometheus_metrics import render_prometheus_metrics

router = APIRouter(tags=["metrics"])


@router.get("/metrics", include_in_schema=False, response_class=PlainTextResponse)
def metrics(session: Session = Depends(get_db_session)) -> PlainTextResponse:
    overview = MonitoringQueryService(session).overview()
    session.commit()
    return PlainTextResponse(
        content=render_prometheus_metrics(overview),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
