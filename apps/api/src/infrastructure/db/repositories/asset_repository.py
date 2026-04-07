from sqlalchemy import select
from sqlalchemy.orm import Session

from src.infrastructure.db.models import (
    CharacterProfileModel,
    CharacterReferenceImageModel,
    SceneProfileModel,
    VoiceProfileModel,
)


class AssetRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_character(
        self,
        project_id: int,
        name: str,
        appearance: str,
        personality: str,
        lora_path: str | None,
        reference_images: list[dict],
    ) -> CharacterProfileModel:
        character = CharacterProfileModel(
            project_id=project_id,
            name=name,
            appearance=appearance,
            personality=personality,
            lora_path=lora_path,
        )
        self.session.add(character)
        self.session.flush()
        for image in reference_images:
            self.session.add(
                CharacterReferenceImageModel(
                    character_id=character.id,
                    view_type=image["view_type"],
                    asset_path=image["asset_path"],
                    notes=image.get("notes"),
                )
            )
        self.session.flush()
        self.session.refresh(character)
        return character

    def create_voice(
        self,
        project_id: int,
        character_name: str,
        voice_key: str,
        provider_key: str,
        tone_description: str,
    ) -> VoiceProfileModel:
        voice = VoiceProfileModel(
            project_id=project_id,
            character_name=character_name,
            voice_key=voice_key,
            provider_key=provider_key,
            tone_description=tone_description,
        )
        self.session.add(voice)
        self.session.flush()
        return voice

    def create_scene(
        self,
        project_id: int,
        name: str,
        baseline_prompt: str,
        continuity_guardrails: str | None,
    ) -> SceneProfileModel:
        scene = SceneProfileModel(
            project_id=project_id,
            name=name,
            baseline_prompt=baseline_prompt,
            continuity_guardrails=continuity_guardrails,
        )
        self.session.add(scene)
        self.session.flush()
        return scene

    def list_characters(self, project_id: int | None = None) -> list[CharacterProfileModel]:
        query = select(CharacterProfileModel).order_by(CharacterProfileModel.id.desc())
        if project_id is not None:
            query = query.where(CharacterProfileModel.project_id == project_id)
        return list(self.session.scalars(query))

    def list_voices(self, project_id: int | None = None) -> list[VoiceProfileModel]:
        query = select(VoiceProfileModel).order_by(VoiceProfileModel.id.desc())
        if project_id is not None:
            query = query.where(VoiceProfileModel.project_id == project_id)
        return list(self.session.scalars(query))

    def list_scenes(self, project_id: int | None = None) -> list[SceneProfileModel]:
        query = select(SceneProfileModel).order_by(SceneProfileModel.id.desc())
        if project_id is not None:
            query = query.where(SceneProfileModel.project_id == project_id)
        return list(self.session.scalars(query))

    def count_project_characters(self, project_id: int) -> int:
        return len(list(self.session.scalars(select(CharacterProfileModel.id).where(CharacterProfileModel.project_id == project_id))))

    def count_project_scenes(self, project_id: int) -> int:
        return len(list(self.session.scalars(select(SceneProfileModel.id).where(SceneProfileModel.project_id == project_id))))

    def count_project_voices(self, project_id: int) -> int:
        return len(list(self.session.scalars(select(VoiceProfileModel.id).where(VoiceProfileModel.project_id == project_id))))

    def delete_project_characters(self, project_id: int) -> None:
        characters = self.session.scalars(
            select(CharacterProfileModel).where(CharacterProfileModel.project_id == project_id)
        ).all()
        for character in characters:
            self.session.delete(character)
        self.session.flush()

    def delete_project_scenes(self, project_id: int) -> None:
        scenes = self.session.scalars(select(SceneProfileModel).where(SceneProfileModel.project_id == project_id)).all()
        for scene in scenes:
            self.session.delete(scene)
        self.session.flush()
