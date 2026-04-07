from sqlalchemy.orm import Session

from src.infrastructure.db.repositories.artifact_repository import ArtifactRepository


class ArtifactQueryService:
    def __init__(self, session: Session) -> None:
        self.artifacts = ArtifactRepository(session)

    def list_project_artifacts(self, project_id: int) -> list[dict]:
        return [self._serialize_artifact(item) for item in self.artifacts.list_project_artifacts(project_id)]

    def get_artifact(self, artifact_id: int) -> dict | None:
        artifact = self.artifacts.get_artifact(artifact_id)
        if artifact is None:
            return None
        return self._serialize_artifact(artifact)

    @staticmethod
    def _serialize_artifact(artifact) -> dict:
        return {
            "id": artifact.id,
            "project_id": artifact.project_id,
            "chapter_id": artifact.chapter_id,
            "job_run_id": artifact.job_run_id,
            "step_key": artifact.step_key,
            "title": artifact.title,
            "media_kind": artifact.media_kind,
            "provider_key": artifact.provider_key,
            "status": artifact.status,
            "mime_type": artifact.mime_type,
            "artifact_path": artifact.artifact_path,
            "preview_path": artifact.preview_path,
            "preview_url": f"/api/v1/previews/artifacts/{artifact.id}",
            "size_bytes": artifact.size_bytes,
            "artifact_metadata": artifact.artifact_metadata,
            "archives": [
                {
                    "id": archive.id,
                    "archive_type": archive.archive_type,
                    "archive_path": archive.archive_path,
                    "index_key": archive.index_key,
                    "status": archive.status,
                    "remote_url": archive.remote_url,
                    "checksum_sha256": archive.checksum_sha256,
                    "created_at": archive.created_at,
                    "updated_at": archive.updated_at,
                }
                for archive in artifact.archives
            ],
            "sync_runs": [
                {
                    "id": sync_run.id,
                    "artifact_id": sync_run.artifact_id,
                    "archive_type": sync_run.archive_type,
                    "status": sync_run.status,
                    "summary": sync_run.summary,
                    "error_message": sync_run.error_message,
                    "worker_id": sync_run.worker_id,
                    "attempt_count": sync_run.attempt_count,
                    "started_at": sync_run.started_at,
                    "finished_at": sync_run.finished_at,
                    "created_at": sync_run.created_at,
                    "updated_at": sync_run.updated_at,
                }
                for sync_run in artifact.sync_runs
            ],
            "created_at": artifact.created_at,
            "updated_at": artifact.updated_at,
        }
