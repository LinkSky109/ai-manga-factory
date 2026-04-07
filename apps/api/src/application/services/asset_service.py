from sqlalchemy.orm import Session

from src.infrastructure.db.repositories.asset_repository import AssetRepository


class AssetService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.assets = AssetRepository(session)

    def create_character(self, **payload):
        character = self.assets.create_character(**payload)
        self.session.commit()
        self.session.refresh(character)
        return character

    def create_voice(self, **payload):
        voice = self.assets.create_voice(**payload)
        self.session.commit()
        self.session.refresh(voice)
        return voice

    def create_scene(self, **payload):
        scene = self.assets.create_scene(**payload)
        self.session.commit()
        self.session.refresh(scene)
        return scene

    def list_characters(self, project_id: int | None = None):
        return self.assets.list_characters(project_id=project_id)

    def list_voices(self, project_id: int | None = None):
        return self.assets.list_voices(project_id=project_id)

    def list_scenes(self, project_id: int | None = None):
        return self.assets.list_scenes(project_id=project_id)
