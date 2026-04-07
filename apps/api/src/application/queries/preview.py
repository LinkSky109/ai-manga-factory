from sqlalchemy.orm import Session

from src.infrastructure.db.repositories.artifact_repository import ArtifactRepository


class PreviewQueryService:
    def __init__(self, session: Session) -> None:
        self.artifacts = ArtifactRepository(session)

    def list_project_previews(self, project_id: int) -> list[dict]:
        items = []
        for artifact in self.artifacts.list_project_artifacts(project_id):
            archive_targets = [archive.archive_type for archive in artifact.archives]
            archive_status = "pending"
            if artifact.archives and all(archive.status == "archived" for archive in artifact.archives):
                archive_status = "archived"
            elif artifact.archives:
                archive_status = "partial"
            items.append(
                {
                    "id": f"artifact-{artifact.id}",
                    "artifact_id": artifact.id,
                    "job_id": artifact.job_run_id,
                    "chapter_id": artifact.chapter_id,
                    "stage_key": artifact.step_key,
                    "title": artifact.title,
                    "media_kind": artifact.media_kind,
                    "status": artifact.status,
                    "provider_key": artifact.provider_key,
                    "mime_type": artifact.mime_type,
                    "archive_status": archive_status,
                    "archive_targets": archive_targets,
                    "playback_url": f"/api/v1/previews/artifacts/{artifact.id}",
                    "playback_hint": str(artifact.artifact_metadata.get("playback_hint", "预览资源已生成。")),
                    "updated_at": artifact.updated_at,
                }
            )
        items.sort(key=lambda item: item["updated_at"], reverse=True)
        return items[:12]
