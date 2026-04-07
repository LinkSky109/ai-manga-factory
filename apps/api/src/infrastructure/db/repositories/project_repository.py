from sqlalchemy import select
from sqlalchemy.orm import Session

from src.domain.project.entities import DEFAULT_CHAPTER_STAGES
from src.infrastructure.db.models import (
    ChapterModel,
    ChapterPipelineStateModel,
    ProjectModel,
    ProjectScriptModel,
    ProjectSourceMaterialModel,
    ProjectStorySummaryModel,
)


class ProjectRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_project(self, name: str, description: str | None) -> ProjectModel:
        project = ProjectModel(name=name, description=description, status="draft")
        self.session.add(project)
        self.session.flush()
        return project

    def list_projects(self) -> list[ProjectModel]:
        return list(self.session.scalars(select(ProjectModel).order_by(ProjectModel.id.desc())))

    def get_project(self, project_id: int) -> ProjectModel | None:
        return self.session.get(ProjectModel, project_id)

    def update_project_status(self, project: ProjectModel, status: str) -> ProjectModel:
        project.status = status
        self.session.flush()
        return project

    def create_chapter(self, project_id: int, chapter_number: int, title: str, summary: str | None) -> ChapterModel:
        chapter = ChapterModel(
            project_id=project_id,
            chapter_number=chapter_number,
            title=title,
            summary=summary,
            status="not_started",
        )
        self.session.add(chapter)
        self.session.flush()
        for stage_key in DEFAULT_CHAPTER_STAGES:
            self.session.add(
                ChapterPipelineStateModel(chapter_id=chapter.id, stage_key=stage_key, status="not_started")
            )
        self.session.flush()
        return chapter

    def get_chapter_by_number(self, project_id: int, chapter_number: int) -> ChapterModel | None:
        return self.session.scalar(
            select(ChapterModel).where(
                ChapterModel.project_id == project_id,
                ChapterModel.chapter_number == chapter_number,
            )
        )

    def create_or_update_chapter(
        self,
        project_id: int,
        chapter_number: int,
        title: str,
        summary: str | None,
    ) -> ChapterModel:
        chapter = self.get_chapter_by_number(project_id=project_id, chapter_number=chapter_number)
        if chapter is not None:
            chapter.title = title
            chapter.summary = summary
            self.session.flush()
            return chapter
        return self.create_chapter(
            project_id=project_id,
            chapter_number=chapter_number,
            title=title,
            summary=summary,
        )

    def list_chapters(self, project_id: int) -> list[ChapterModel]:
        return list(
            self.session.scalars(
                select(ChapterModel).where(ChapterModel.project_id == project_id).order_by(ChapterModel.chapter_number)
            )
        )

    def create_source_material(
        self,
        project_id: int,
        source_title: str,
        source_type: str,
        body: str,
        chapter_count: int,
        source_metadata: dict,
    ) -> ProjectSourceMaterialModel:
        item = ProjectSourceMaterialModel(
            project_id=project_id,
            source_title=source_title,
            source_type=source_type,
            body=body,
            chapter_count=chapter_count,
            source_metadata=source_metadata,
            import_status="imported",
        )
        self.session.add(item)
        self.session.flush()
        return item

    def create_story_summary(
        self,
        project_id: int,
        source_material_id: int | None,
        summary_body: str,
        highlights: list[str],
    ) -> ProjectStorySummaryModel:
        item = ProjectStorySummaryModel(
            project_id=project_id,
            source_material_id=source_material_id,
            summary_body=summary_body,
            highlights=highlights,
            status="completed",
        )
        self.session.add(item)
        self.session.flush()
        return item

    def create_script(
        self,
        project_id: int,
        story_summary_id: int | None,
        title: str,
        script_body: str,
    ) -> ProjectScriptModel:
        item = ProjectScriptModel(
            project_id=project_id,
            story_summary_id=story_summary_id,
            title=title,
            script_body=script_body,
            status="completed",
        )
        self.session.add(item)
        self.session.flush()
        return item

    def get_latest_source_material(self, project_id: int) -> ProjectSourceMaterialModel | None:
        return self.session.scalar(
            select(ProjectSourceMaterialModel)
            .where(ProjectSourceMaterialModel.project_id == project_id)
            .order_by(ProjectSourceMaterialModel.id.desc())
        )

    def get_latest_story_summary(self, project_id: int) -> ProjectStorySummaryModel | None:
        return self.session.scalar(
            select(ProjectStorySummaryModel)
            .where(ProjectStorySummaryModel.project_id == project_id)
            .order_by(ProjectStorySummaryModel.id.desc())
        )

    def get_latest_script(self, project_id: int) -> ProjectScriptModel | None:
        return self.session.scalar(
            select(ProjectScriptModel)
            .where(ProjectScriptModel.project_id == project_id)
            .order_by(ProjectScriptModel.id.desc())
        )
