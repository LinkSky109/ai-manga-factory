from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import selectinload
from sqlalchemy.orm import Session

from src.infrastructure.db.models import ArtifactArchiveModel, ArtifactModel, ArtifactSyncRunModel


class ArtifactRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert_artifact(
        self,
        project_id: int,
        chapter_id: int | None,
        job_run_id: int,
        step_key: str,
        title: str,
        media_kind: str,
        provider_key: str | None,
        mime_type: str,
        artifact_path: str,
        preview_path: str,
        size_bytes: int,
        artifact_metadata: dict,
    ) -> ArtifactModel:
        artifact = self.session.scalars(
            select(ArtifactModel).where(
                ArtifactModel.job_run_id == job_run_id,
                ArtifactModel.step_key == step_key,
            )
        ).first()
        if artifact is None:
            artifact = ArtifactModel(
                project_id=project_id,
                chapter_id=chapter_id,
                job_run_id=job_run_id,
                step_key=step_key,
                title=title,
                media_kind=media_kind,
                provider_key=provider_key,
                mime_type=mime_type,
                artifact_path=artifact_path,
                preview_path=preview_path,
                size_bytes=size_bytes,
                artifact_metadata=artifact_metadata,
                status="ready",
            )
            self.session.add(artifact)
        else:
            artifact.title = title
            artifact.media_kind = media_kind
            artifact.provider_key = provider_key
            artifact.mime_type = mime_type
            artifact.artifact_path = artifact_path
            artifact.preview_path = preview_path
            artifact.size_bytes = size_bytes
            artifact.artifact_metadata = artifact_metadata
            artifact.status = "ready"
        self.session.flush()
        return artifact

    def upsert_archive(
        self,
        artifact_id: int,
        archive_type: str,
        archive_path: str,
        index_key: str,
        remote_url: str | None = None,
        checksum_sha256: str | None = None,
        status: str = "archived",
    ) -> ArtifactArchiveModel:
        archive = self.session.scalars(
            select(ArtifactArchiveModel).where(
                ArtifactArchiveModel.artifact_id == artifact_id,
                ArtifactArchiveModel.archive_type == archive_type,
            )
        ).first()
        if archive is None:
            archive = ArtifactArchiveModel(
                artifact_id=artifact_id,
                archive_type=archive_type,
                archive_path=archive_path,
                index_key=index_key,
                status=status,
                remote_url=remote_url,
                checksum_sha256=checksum_sha256,
            )
            self.session.add(archive)
        else:
            archive.archive_path = archive_path
            archive.index_key = index_key
            archive.status = status
            archive.remote_url = remote_url
            archive.checksum_sha256 = checksum_sha256
        self.session.flush()
        return archive

    def list_project_artifacts(self, project_id: int) -> list[ArtifactModel]:
        return list(
            self.session.scalars(
                select(ArtifactModel)
                .where(ArtifactModel.project_id == project_id)
                .options(selectinload(ArtifactModel.archives))
                .order_by(ArtifactModel.updated_at.desc(), ArtifactModel.id.desc())
            )
        )

    def get_artifact(self, artifact_id: int) -> ArtifactModel | None:
        return self.session.scalars(
            select(ArtifactModel)
            .where(ArtifactModel.id == artifact_id)
            .options(selectinload(ArtifactModel.archives), selectinload(ArtifactModel.sync_runs))
        ).first()

    def enqueue_sync_run(self, artifact_id: int, archive_type: str) -> ArtifactSyncRunModel:
        sync_run = ArtifactSyncRunModel(
            artifact_id=artifact_id,
            archive_type=archive_type,
            status="queued",
            summary="Archive sync task queued.",
        )
        self.session.add(sync_run)
        self.session.flush()
        return sync_run

    def list_sync_runs_for_artifact(self, artifact_id: int) -> list[ArtifactSyncRunModel]:
        return list(
            self.session.scalars(
                select(ArtifactSyncRunModel)
                .where(ArtifactSyncRunModel.artifact_id == artifact_id)
                .order_by(ArtifactSyncRunModel.id.desc())
            )
        )

    def get_sync_run(self, sync_run_id: int) -> ArtifactSyncRunModel | None:
        return self.session.get(ArtifactSyncRunModel, sync_run_id)

    def claim_next_sync_run(self, worker_id: str) -> ArtifactSyncRunModel | None:
        candidate_ids = self.session.scalars(
            select(ArtifactSyncRunModel.id)
            .where(ArtifactSyncRunModel.status == "queued")
            .order_by(ArtifactSyncRunModel.id.asc())
            .limit(5)
        ).all()

        for candidate_id in candidate_ids:
            claimed_at = self._utcnow()
            result = self.session.execute(
                update(ArtifactSyncRunModel)
                .where(
                    ArtifactSyncRunModel.id == candidate_id,
                    ArtifactSyncRunModel.status == "queued",
                )
                .values(
                    status="running",
                    worker_id=worker_id,
                    started_at=claimed_at,
                    summary="Archive sync task claimed by worker.",
                    error_message=None,
                    attempt_count=ArtifactSyncRunModel.attempt_count + 1,
                )
            )
            if result.rowcount:
                self.session.flush()
                return self.session.get(ArtifactSyncRunModel, candidate_id)
        return None

    def update_sync_run_state(
        self,
        sync_run: ArtifactSyncRunModel,
        status: str,
        summary: str,
        error_message: str | None = None,
    ) -> ArtifactSyncRunModel:
        sync_run.status = status
        sync_run.summary = summary
        sync_run.error_message = error_message
        if status == "running" and sync_run.started_at is None:
            sync_run.started_at = self._utcnow()
        if status == "queued":
            sync_run.worker_id = None
            sync_run.started_at = None
            sync_run.finished_at = None
        if status in {"completed", "failed"}:
            sync_run.finished_at = self._utcnow()
        self.session.flush()
        return sync_run

    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(timezone.utc)
