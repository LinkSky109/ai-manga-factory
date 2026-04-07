from sqlalchemy import ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.db.models.base import Base, TimestampMixin


class WorkflowDefinitionModel(TimestampMixin, Base):
    __tablename__ = "workflow_definitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    routing_mode: Mapped[str] = mapped_column(String(32), default="smart", nullable=False)
    spec: Mapped[dict] = mapped_column(JSON, nullable=False)

    project = relationship("ProjectModel", back_populates="workflows")
    jobs = relationship("JobRunModel", back_populates="workflow")
