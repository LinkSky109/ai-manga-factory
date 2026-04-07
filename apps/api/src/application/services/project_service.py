from sqlalchemy.orm import Session

from src.application.orchestrators.project_initializer import ProjectInitializationOrchestrator
from src.infrastructure.db.repositories.asset_repository import AssetRepository
from src.infrastructure.db.repositories.project_repository import ProjectRepository
from src.infrastructure.db.repositories.provider_repository import ProviderRepository


class ProjectService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.projects = ProjectRepository(session)
        self.assets = AssetRepository(session)
        self.providers = ProviderRepository(session)
        self.initializer = ProjectInitializationOrchestrator(session)

    def create_project(self, name: str, description: str | None):
        project = self.projects.create_project(name=name, description=description)
        self.session.commit()
        self.session.refresh(project)
        return project

    def list_projects(self):
        return self.projects.list_projects()

    def get_project(self, project_id: int):
        return self.projects.get_project(project_id)

    def create_chapter(self, project_id: int, chapter_number: int, title: str, summary: str | None):
        chapter = self.projects.create_chapter(
            project_id=project_id,
            chapter_number=chapter_number,
            title=title,
            summary=summary,
        )
        self.session.commit()
        self.session.refresh(chapter)
        return chapter

    def list_chapters(self, project_id: int):
        return self.projects.list_chapters(project_id)

    def build_overview(self, project_id: int) -> dict:
        project = self.projects.get_project(project_id)
        if project is None:
            raise LookupError("Project not found.")

        chapters = self.projects.list_chapters(project_id)
        usage = self.providers.summarize_usage(project_id=project_id)
        provider_items = [item for item in usage if item["consumed"] > 0]
        initialization = self.initializer.get_snapshot(project_id)

        return {
            "project_name": project.name,
            "status": project.status,
            "summary": project.description or "项目已进入项目制后端编排模式。",
            "chapter_progress": [
                {"label": "章节总数", "value": str(len(chapters)), "tone": "neutral"},
                {
                    "label": "已完成",
                    "value": str(sum(chapter.status == "completed" for chapter in chapters)),
                    "tone": "success",
                },
                {
                    "label": "进行中",
                    "value": str(sum(chapter.status == "in_progress" for chapter in chapters)),
                    "tone": "warning",
                },
                {
                    "label": "异常章节",
                    "value": str(sum(chapter.status == "failed" for chapter in chapters)),
                    "tone": "danger",
                },
            ],
            "asset_health": [
                {"label": "角色卡", "value": str(self.assets.count_project_characters(project_id)), "tone": "neutral"},
                {"label": "场景资产", "value": str(self.assets.count_project_scenes(project_id)), "tone": "neutral"},
                {"label": "音色资产", "value": str(self.assets.count_project_voices(project_id)), "tone": "neutral"},
            ],
            "provider_usage": [
                {
                    "label": item["provider_key"],
                    "value": f"{item['consumed']:.0f} {item['usage_unit']}",
                    "tone": "warning" if item["alert_status"] == "warning" else "neutral",
                }
                for item in provider_items[:4]
            ],
            "initialization_progress": initialization["stage_cards"],
        }

    def initialize_project(
        self,
        *,
        project_id: int,
        source_title: str,
        source_type: str,
        source_text: str,
        overwrite_assets: bool,
        routing_mode: str,
        manual_provider: str | None,
    ) -> dict:
        return self.initializer.initialize_project(
            project_id=project_id,
            source_title=source_title,
            source_type=source_type,
            source_text=source_text,
            overwrite_assets=overwrite_assets,
            routing_mode=routing_mode,
            manual_provider=manual_provider,
        )

    def get_initialization_snapshot(self, project_id: int) -> dict:
        return self.initializer.get_snapshot(project_id)
