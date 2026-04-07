from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.db.models.base import Base, TimestampMixin


class JobRunModel(TimestampMixin, Base):
    __tablename__ = "job_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    chapter_id: Mapped[int | None] = mapped_column(ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True)
    workflow_id: Mapped[int | None] = mapped_column(
        ForeignKey("workflow_definitions.id", ondelete="SET NULL"),
        nullable=True,
    )
    execution_mode: Mapped[str] = mapped_column(String(16), default="sync", nullable=False)
    routing_mode: Mapped[str] = mapped_column(String(32), default="smart", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="queued", nullable=False)
    current_step_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    worker_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    project = relationship("ProjectModel", back_populates="jobs")
    chapter = relationship("ChapterModel", back_populates="jobs")
    workflow = relationship("WorkflowDefinitionModel", back_populates="jobs")
    steps = relationship("JobRunStepModel", back_populates="job_run", cascade="all, delete-orphan")
    checkpoints = relationship("JobCheckpointModel", back_populates="job_run", cascade="all, delete-orphan")
    artifacts = relationship("ArtifactModel", back_populates="job_run", cascade="all, delete-orphan")


class JobRunStepModel(TimestampMixin, Base):
    __tablename__ = "job_run_steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_run_id: Mapped[int] = mapped_column(ForeignKey("job_runs.id", ondelete="CASCADE"), nullable=False)
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    step_key: Mapped[str] = mapped_column(String(64), nullable=False)
    step_name: Mapped[str] = mapped_column(String(120), nullable=False)
    provider_type: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    usage_amount: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    usage_unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    output_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    job_run = relationship("JobRunModel", back_populates="steps")


class JobCheckpointModel(TimestampMixin, Base):
    __tablename__ = "job_checkpoints"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_run_id: Mapped[int] = mapped_column(ForeignKey("job_runs.id", ondelete="CASCADE"), nullable=False)
    step_key: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    resume_cursor: Mapped[str | None] = mapped_column(String(64), nullable=True)

    job_run = relationship("JobRunModel", back_populates="checkpoints")
