from sqlalchemy import ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.db.models.base import Base, TimestampMixin


class PromptTemplateModel(TimestampMixin, Base):
    __tablename__ = "prompt_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    workflow_key: Mapped[str] = mapped_column(String(120), nullable=False)
    template_version: Mapped[str] = mapped_column(String(32), nullable=False)
    template_body: Mapped[str] = mapped_column(Text, nullable=False)


class PromptFeedbackModel(TimestampMixin, Base):
    __tablename__ = "prompt_feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    prompt_template_id: Mapped[int] = mapped_column(ForeignKey("prompt_templates.id", ondelete="CASCADE"), nullable=False)
    job_run_id: Mapped[int | None] = mapped_column(ForeignKey("job_runs.id", ondelete="SET NULL"), nullable=True)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    correction_summary: Mapped[str] = mapped_column(Text, nullable=False)
    corrected_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)


class SharedMemoryModel(TimestampMixin, Base):
    __tablename__ = "shared_memories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_key: Mapped[str] = mapped_column(String(120), nullable=False)
    memory_type: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class ReviewTaskModel(TimestampMixin, Base):
    __tablename__ = "review_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    chapter_id: Mapped[int | None] = mapped_column(ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True)
    review_stage: Mapped[str] = mapped_column(String(32), nullable=False)
    review_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    assigned_agents: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    checklist: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    findings_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
