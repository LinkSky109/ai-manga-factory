from sqlalchemy import ForeignKey, Integer, JSON, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.db.models.base import Base, TimestampMixin


class ProviderConfigModel(TimestampMixin, Base):
    __tablename__ = "provider_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider_key: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    provider_type: Mapped[str] = mapped_column(String(32), nullable=False)
    routing_mode: Mapped[str] = mapped_column(String(32), default="smart", nullable=False)
    is_enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    budget_threshold: Mapped[float] = mapped_column(Numeric(12, 2), default=80, nullable=False)
    config: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class ProviderUsageLogModel(TimestampMixin, Base):
    __tablename__ = "provider_usage_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider_key: Mapped[str] = mapped_column(String(120), nullable=False)
    provider_type: Mapped[str] = mapped_column(String(32), nullable=False)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    job_run_id: Mapped[int | None] = mapped_column(ForeignKey("job_runs.id", ondelete="SET NULL"), nullable=True)
    metric_name: Mapped[str] = mapped_column(String(32), nullable=False)
    usage_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    usage_unit: Mapped[str] = mapped_column(String(32), nullable=False)
