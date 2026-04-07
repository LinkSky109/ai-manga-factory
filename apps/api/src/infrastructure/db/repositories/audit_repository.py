from sqlalchemy import select
from sqlalchemy.orm import Session

from src.infrastructure.db.models import AuditLogModel


class AuditRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_audit_log(
        self,
        *,
        actor_user_id: int | None,
        actor_email: str | None,
        actor_role: str | None,
        action: str,
        resource_type: str,
        resource_id: str | None,
        request_method: str,
        request_path: str,
        response_status: int,
        outcome: str,
        detail: dict,
    ) -> AuditLogModel:
        audit_log = AuditLogModel(
            actor_user_id=actor_user_id,
            actor_email=actor_email,
            actor_role=actor_role,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            request_method=request_method,
            request_path=request_path,
            response_status=response_status,
            outcome=outcome,
            detail=detail,
        )
        self.session.add(audit_log)
        self.session.flush()
        return audit_log

    def list_logs(self, *, limit: int = 50) -> list[AuditLogModel]:
        return list(
            self.session.scalars(
                select(AuditLogModel).order_by(AuditLogModel.id.desc()).limit(limit)
            )
        )
