from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.core.config import get_settings
from src.infrastructure.db.models import AlertRecordModel, JobRunModel, WorkerHeartbeatModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class MonitoringRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def record_worker_heartbeat(
        self,
        *,
        worker_id: str,
        worker_type: str,
        status: str,
        seen_at: datetime | None = None,
        last_job_id: int | None = None,
        detail: dict | None = None,
    ) -> WorkerHeartbeatModel:
        heartbeat = self.session.scalars(
            select(WorkerHeartbeatModel).where(WorkerHeartbeatModel.worker_id == worker_id)
        ).first()
        resolved_seen_at = _ensure_aware(seen_at or _utcnow())
        if heartbeat is None:
            heartbeat = WorkerHeartbeatModel(
                worker_id=worker_id,
                worker_type=worker_type,
                status=status,
                last_seen_at=resolved_seen_at,
                last_job_id=last_job_id,
                detail=detail or {},
            )
            self.session.add(heartbeat)
        else:
            heartbeat.worker_type = worker_type
            heartbeat.status = status
            heartbeat.last_seen_at = resolved_seen_at
            heartbeat.last_job_id = last_job_id
            heartbeat.detail = detail or {}
        self.session.flush()
        return heartbeat

    def worker_snapshots(self) -> list[dict]:
        stale_after_seconds = max(get_settings().worker_stale_after_seconds, 1)
        now = _utcnow()
        rows = self.session.scalars(select(WorkerHeartbeatModel).order_by(WorkerHeartbeatModel.worker_id)).all()
        snapshots: list[dict] = []
        for row in rows:
            last_seen_at = _ensure_aware(row.last_seen_at)
            seconds_since_seen = max((now - last_seen_at).total_seconds(), 0.0)
            if row.status == "stopped":
                health_status = "stopped"
            elif seconds_since_seen > stale_after_seconds:
                health_status = "stale"
            else:
                health_status = "healthy"
            snapshots.append(
                {
                    "worker_id": row.worker_id,
                    "worker_type": row.worker_type,
                    "status": row.status,
                    "health_status": health_status,
                    "last_seen_at": last_seen_at,
                    "seconds_since_seen": round(seconds_since_seen, 2),
                    "last_job_id": row.last_job_id,
                    "detail": row.detail,
                }
            )
        return snapshots

    def sync_provider_budget_alerts(self, provider_items: list[dict]) -> list[AlertRecordModel]:
        now = _utcnow()
        active_alert_keys: set[str] = set()
        for item in provider_items:
            threshold = float(item["budget_threshold"])
            consumed = float(item["consumed"])
            provider_key = item["provider_key"]
            alert_key = f"provider-budget:{provider_key}"
            if threshold <= 0 or consumed < threshold:
                self._resolve_alert(alert_key=alert_key, resolved_at=now)
                continue

            active_alert_keys.add(alert_key)
            severity = "critical" if consumed >= threshold * 1.2 else "warning"
            ratio = round(consumed / threshold, 3) if threshold else 0.0
            self._upsert_alert(
                alert_key=alert_key,
                scope_type="provider_budget",
                scope_key=provider_key,
                severity=severity,
                title=f"{provider_key} budget threshold exceeded",
                message=(
                    f"{provider_key} has consumed {consumed:.0f} {item['usage_unit']} "
                    f"against threshold {threshold:.0f} {item['usage_unit']}."
                ),
                detail={
                    "provider_key": provider_key,
                    "provider_type": item["provider_type"],
                    "consumed": consumed,
                    "budget_threshold": threshold,
                    "usage_unit": item["usage_unit"],
                    "ratio": ratio,
                    "routing_mode": item["routing_mode"],
                },
                triggered_at=now,
            )

        existing_active = self.session.scalars(
            select(AlertRecordModel).where(
                AlertRecordModel.scope_type == "provider_budget",
                AlertRecordModel.status == "active",
            )
        ).all()
        for alert in existing_active:
            if alert.alert_key not in active_alert_keys:
                alert.status = "resolved"
                alert.resolved_at = now
        self.session.flush()
        return self.list_alerts(active_only=True)

    def list_alerts(self, *, active_only: bool = False) -> list[AlertRecordModel]:
        query = select(AlertRecordModel).order_by(AlertRecordModel.last_triggered_at.desc(), AlertRecordModel.id.desc())
        if active_only:
            query = query.where(AlertRecordModel.status == "active")
        return list(self.session.scalars(query))

    def job_summary(self) -> dict[str, int]:
        rows = self.session.execute(
            select(JobRunModel.status, func.count(JobRunModel.id)).group_by(JobRunModel.status)
        ).all()
        counts = {status: int(count) for status, count in rows}
        return {
            "queued_jobs": counts.get("queued", 0),
            "running_jobs": counts.get("running", 0),
            "failed_jobs": counts.get("failed", 0),
            "resumable_jobs": counts.get("resumable", 0),
            "completed_jobs": counts.get("completed", 0),
        }

    def _upsert_alert(
        self,
        *,
        alert_key: str,
        scope_type: str,
        scope_key: str,
        severity: str,
        title: str,
        message: str,
        detail: dict,
        triggered_at: datetime,
    ) -> AlertRecordModel:
        alert = self.session.scalars(select(AlertRecordModel).where(AlertRecordModel.alert_key == alert_key)).first()
        if alert is None:
            alert = AlertRecordModel(
                alert_key=alert_key,
                scope_type=scope_type,
                scope_key=scope_key,
                severity=severity,
                status="active",
                title=title,
                message=message,
                detail=detail,
                first_triggered_at=triggered_at,
                last_triggered_at=triggered_at,
                resolved_at=None,
            )
            self.session.add(alert)
        else:
            alert.scope_type = scope_type
            alert.scope_key = scope_key
            alert.severity = severity
            alert.status = "active"
            alert.title = title
            alert.message = message
            alert.detail = detail
            alert.last_triggered_at = triggered_at
            alert.resolved_at = None
        self.session.flush()
        return alert

    def _resolve_alert(self, *, alert_key: str, resolved_at: datetime) -> None:
        alert = self.session.scalars(select(AlertRecordModel).where(AlertRecordModel.alert_key == alert_key)).first()
        if alert is None:
            return
        alert.status = "resolved"
        alert.resolved_at = resolved_at
        self.session.flush()
