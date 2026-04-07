from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.db.models.base import Base, TimestampMixin


class ProjectModel(TimestampMixin, Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)

    chapters = relationship("ChapterModel", back_populates="project", cascade="all, delete-orphan")
    characters = relationship("CharacterProfileModel", back_populates="project", cascade="all, delete-orphan")
    scenes = relationship("SceneProfileModel", back_populates="project", cascade="all, delete-orphan")
    voices = relationship("VoiceProfileModel", back_populates="project", cascade="all, delete-orphan")
    workflows = relationship("WorkflowDefinitionModel", back_populates="project", cascade="all, delete-orphan")
    jobs = relationship("JobRunModel", back_populates="project", cascade="all, delete-orphan")
    artifacts = relationship("ArtifactModel", back_populates="project", cascade="all, delete-orphan")
    source_materials = relationship("ProjectSourceMaterialModel", back_populates="project", cascade="all, delete-orphan")
    story_summaries = relationship("ProjectStorySummaryModel", back_populates="project", cascade="all, delete-orphan")
    scripts = relationship("ProjectScriptModel", back_populates="project", cascade="all, delete-orphan")


class ChapterModel(TimestampMixin, Base):
    __tablename__ = "chapters"
    __table_args__ = (UniqueConstraint("project_id", "chapter_number", name="uq_chapter_project_number"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    chapter_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="not_started", nullable=False)

    project = relationship("ProjectModel", back_populates="chapters")
    pipeline_states = relationship(
        "ChapterPipelineStateModel",
        back_populates="chapter",
        cascade="all, delete-orphan",
        order_by="ChapterPipelineStateModel.id",
    )
    jobs = relationship("JobRunModel", back_populates="chapter")
    artifacts = relationship("ArtifactModel", back_populates="chapter")


class ChapterPipelineStateModel(TimestampMixin, Base):
    __tablename__ = "chapter_pipeline_states"
    __table_args__ = (UniqueConstraint("chapter_id", "stage_key", name="uq_chapter_stage"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chapter_id: Mapped[int] = mapped_column(ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False)
    stage_key: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="not_started", nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    chapter = relationship("ChapterModel", back_populates="pipeline_states")
