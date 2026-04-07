from sqlalchemy import ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.db.models.base import Base, TimestampMixin


class ProjectSourceMaterialModel(TimestampMixin, Base):
    __tablename__ = "project_source_materials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    source_title: Mapped[str] = mapped_column(String(160), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, default="novel_text")
    body: Mapped[str] = mapped_column(Text, nullable=False)
    import_status: Mapped[str] = mapped_column(String(32), nullable=False, default="imported")
    chapter_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_metadata: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    project = relationship("ProjectModel", back_populates="source_materials")
    summaries = relationship("ProjectStorySummaryModel", back_populates="source_material", cascade="all, delete-orphan")


class ProjectStorySummaryModel(TimestampMixin, Base):
    __tablename__ = "project_story_summaries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    source_material_id: Mapped[int | None] = mapped_column(
        ForeignKey("project_source_materials.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    summary_body: Mapped[str] = mapped_column(Text, nullable=False)
    highlights: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    project = relationship("ProjectModel", back_populates="story_summaries")
    source_material = relationship("ProjectSourceMaterialModel", back_populates="summaries")
    scripts = relationship("ProjectScriptModel", back_populates="story_summary", cascade="all, delete-orphan")


class ProjectScriptModel(TimestampMixin, Base):
    __tablename__ = "project_scripts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    story_summary_id: Mapped[int | None] = mapped_column(
        ForeignKey("project_story_summaries.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    script_body: Mapped[str] = mapped_column(Text, nullable=False)

    project = relationship("ProjectModel", back_populates="scripts")
    story_summary = relationship("ProjectStorySummaryModel", back_populates="scripts")
