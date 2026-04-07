from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.db.models.base import Base, TimestampMixin


class ArtifactModel(TimestampMixin, Base):
    __tablename__ = "artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    chapter_id: Mapped[int | None] = mapped_column(ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True)
    job_run_id: Mapped[int] = mapped_column(ForeignKey("job_runs.id", ondelete="CASCADE"), nullable=False)
    step_key: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    media_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="ready", nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False)
    artifact_path: Mapped[str] = mapped_column(Text, nullable=False)
    preview_path: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    artifact_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    project = relationship("ProjectModel", back_populates="artifacts")
    chapter = relationship("ChapterModel", back_populates="artifacts")
    job_run = relationship("JobRunModel", back_populates="artifacts")
    archives = relationship("ArtifactArchiveModel", back_populates="artifact", cascade="all, delete-orphan")
    sync_runs = relationship("ArtifactSyncRunModel", back_populates="artifact", cascade="all, delete-orphan")


class ArtifactArchiveModel(TimestampMixin, Base):
    __tablename__ = "artifact_archives"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    artifact_id: Mapped[int] = mapped_column(ForeignKey("artifacts.id", ondelete="CASCADE"), nullable=False)
    archive_type: Mapped[str] = mapped_column(String(32), default="local-archive", nullable=False)
    archive_path: Mapped[str] = mapped_column(Text, nullable=False)
    index_key: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="archived", nullable=False)
    remote_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)

    artifact = relationship("ArtifactModel", back_populates="archives")


class ArtifactSyncRunModel(TimestampMixin, Base):
    __tablename__ = "artifact_sync_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    artifact_id: Mapped[int] = mapped_column(ForeignKey("artifacts.id", ondelete="CASCADE"), nullable=False)
    archive_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="queued", nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    worker_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    artifact = relationship("ArtifactModel", back_populates="sync_runs")
