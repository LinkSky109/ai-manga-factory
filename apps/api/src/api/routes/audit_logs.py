from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.api.schemas.audit import AuditLogListResponse, AuditLogResponse
from src.core.dependencies import get_db_session
from src.infrastructure.db.repositories.audit_repository import AuditRepository

router = APIRouter(prefix="/audit-logs", tags=["audit-logs"])


@router.get("", response_model=AuditLogListResponse)
def list_audit_logs(
    limit: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_db_session),
) -> AuditLogListResponse:
    items = [AuditLogResponse.model_validate(item) for item in AuditRepository(session).list_logs(limit=limit)]
    return AuditLogListResponse(items=items)
