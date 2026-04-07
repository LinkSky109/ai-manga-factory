from sqlalchemy.orm import Session

from src.infrastructure.db.repositories.monitoring_repository import MonitoringRepository
from src.infrastructure.db.repositories.provider_repository import ProviderRepository


class MonitoringQueryService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.providers = ProviderRepository(session)
        self.monitoring = MonitoringRepository(session)

    def provider_usage(self) -> list[dict]:
        items = self.providers.summarize_usage()
        self.monitoring.sync_provider_budget_alerts(items)
        return items

    def overview(self) -> dict:
        items = self.provider_usage()
        alerts = self.monitoring.list_alerts(active_only=True)
        workers = self.monitoring.worker_snapshots()
        job_summary = self.monitoring.job_summary()
        return {
            "items": items,
            "alerts": alerts,
            "workers": workers,
            "summary": {
                "active_alerts": len(alerts),
                "healthy_workers": sum(1 for worker in workers if worker["health_status"] == "healthy"),
                "stale_workers": sum(1 for worker in workers if worker["health_status"] == "stale"),
                **job_summary,
            },
        }
