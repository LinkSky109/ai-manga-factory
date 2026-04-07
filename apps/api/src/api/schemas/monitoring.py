from datetime import datetime

from pydantic import BaseModel, Field


class ProviderUsageItemResponse(BaseModel):
    provider_key: str
    provider_type: str
    routing_mode: str
    budget_threshold: float
    consumed: float
    usage_unit: str
    alert_status: str


class ProviderUsageListResponse(BaseModel):
    items: list[ProviderUsageItemResponse] = Field(default_factory=list)


class MonitoringAlertResponse(BaseModel):
    id: int
    alert_key: str
    scope_type: str
    scope_key: str
    severity: str
    status: str
    title: str
    message: str
    detail: dict = Field(default_factory=dict)
    first_triggered_at: datetime
    last_triggered_at: datetime
    resolved_at: datetime | None
    created_at: datetime
    updated_at: datetime


class WorkerHeartbeatResponse(BaseModel):
    worker_id: str
    worker_type: str
    status: str
    health_status: str
    last_seen_at: datetime
    seconds_since_seen: float
    last_job_id: int | None
    detail: dict = Field(default_factory=dict)


class MonitoringSummaryResponse(BaseModel):
    active_alerts: int = 0
    healthy_workers: int = 0
    stale_workers: int = 0
    queued_jobs: int = 0
    running_jobs: int = 0
    failed_jobs: int = 0
    resumable_jobs: int = 0
    completed_jobs: int = 0


class MonitoringOverviewResponse(BaseModel):
    items: list[ProviderUsageItemResponse] = Field(default_factory=list)
    alerts: list[MonitoringAlertResponse] = Field(default_factory=list)
    workers: list[WorkerHeartbeatResponse] = Field(default_factory=list)
    summary: MonitoringSummaryResponse = Field(default_factory=MonitoringSummaryResponse)
