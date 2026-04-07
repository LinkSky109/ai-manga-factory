from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.db.models.base import Base, TimestampMixin


class CharacterProfileModel(TimestampMixin, Base):
    __tablename__ = "character_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    appearance: Mapped[str] = mapped_column(Text, nullable=False)
    personality: Mapped[str] = mapped_column(Text, nullable=False)
    lora_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    review_status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)

    project = relationship("ProjectModel", back_populates="characters")
    reference_images = relationship(
        "CharacterReferenceImageModel",
        back_populates="character",
        cascade="all, delete-orphan",
    )


class CharacterReferenceImageModel(TimestampMixin, Base):
    __tablename__ = "character_reference_images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    character_id: Mapped[int] = mapped_column(ForeignKey("character_profiles.id", ondelete="CASCADE"), nullable=False)
    view_type: Mapped[str] = mapped_column(String(32), nullable=False)
    asset_path: Mapped[str] = mapped_column(String(255), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    character = relationship("CharacterProfileModel", back_populates="reference_images")


class SceneProfileModel(TimestampMixin, Base):
    __tablename__ = "scene_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    baseline_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    continuity_guardrails: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)

    project = relationship("ProjectModel", back_populates="scenes")


class VoiceProfileModel(TimestampMixin, Base):
    __tablename__ = "voice_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    character_name: Mapped[str] = mapped_column(String(120), nullable=False)
    voice_key: Mapped[str] = mapped_column(String(120), nullable=False)
    provider_key: Mapped[str] = mapped_column(String(120), nullable=False)
    tone_description: Mapped[str] = mapped_column(Text, nullable=False)

    project = relationship("ProjectModel", back_populates="voices")
