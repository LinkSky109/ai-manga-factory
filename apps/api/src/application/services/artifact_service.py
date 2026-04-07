from sqlalchemy.orm import Session

from src.infrastructure.db.repositories.artifact_repository import ArtifactRepository
from src.infrastructure.storage.artifact_storage import ArtifactStorageService


class ArtifactService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.artifacts = ArtifactRepository(session)
        self.storage = ArtifactStorageService(self.artifacts)

    def sync_artifact_archives(self, artifact_id: int):
        artifact = self.artifacts.get_artifact(artifact_id)
        if artifact is None:
            raise LookupError("Artifact not found.")

        self.storage.sync_existing_artifact(artifact)
        self.session.commit()
        self.session.expire_all()
        return self.artifacts.get_artifact(artifact_id)

    def enqueue_artifact_sync_runs(self, artifact_id: int, archive_types: list[str]):
        artifact = self.artifacts.get_artifact(artifact_id)
        if artifact is None:
            raise LookupError("Artifact not found.")

        requested_types = self._normalize_archive_types(archive_types)
        enabled_types = self.storage.list_enabled_archive_types()
        unsupported_types = [archive_type for archive_type in requested_types if archive_type not in enabled_types]
        if unsupported_types:
            raise ValueError(f"Archive targets are not enabled: {', '.join(unsupported_types)}.")

        existing_runs = self.artifacts.list_sync_runs_for_artifact(artifact_id)
        queued_types = {
            run.archive_type for run in existing_runs if run.status in {"queued", "running"}
        }
        created_runs = []
        for archive_type in requested_types:
            if archive_type in queued_types:
                continue
            created_runs.append(self.artifacts.enqueue_sync_run(artifact_id=artifact_id, archive_type=archive_type))

        self.session.commit()
        return created_runs

    def list_artifact_sync_runs(self, artifact_id: int):
        artifact = self.artifacts.get_artifact(artifact_id)
        if artifact is None:
            raise LookupError("Artifact not found.")
        return self.artifacts.list_sync_runs_for_artifact(artifact_id)

    def sync_project_artifact_archives(self, project_id: int) -> dict:
        artifacts = self.artifacts.list_project_artifacts(project_id)
        restored_targets = 0
        for artifact in artifacts:
            restored_targets += self.storage.sync_existing_artifact(artifact)
        self.session.commit()
        self.session.expire_all()
        return {
            "project_id": project_id,
            "synced_artifacts": len(artifacts),
            "restored_targets": restored_targets,
        }

    @staticmethod
    def _normalize_archive_types(archive_types: list[str]) -> list[str]:
        normalized: list[str] = []
        for archive_type in archive_types:
            clean_value = archive_type.strip()
            if clean_value and clean_value not in normalized:
                normalized.append(clean_value)
        if not normalized:
            raise ValueError("At least one archive target must be provided.")
        return normalized
