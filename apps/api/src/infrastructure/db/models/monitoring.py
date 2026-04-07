from datetime import datetime

from sqlalchemy import DateTime, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.db.models.base import Base, TimestampMixin


class AlertRecordModel(TimestampMixin, Base):
    __tablename__ = "alert_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    alert_key: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    scope_type: Mapped[str] = mapped_column(String(64), nullable=False)
    scope_key: Mapped[str] = mapped_column(String(160), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    message: Mapped[str] = mapped_column(String(512), nullable=False)
    detail: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    first_triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WorkerHeartbeatModel(TimestampMixin, Base):
    __tablename__ = "worker_heartbeats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    worker_id: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    worker_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_job_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
