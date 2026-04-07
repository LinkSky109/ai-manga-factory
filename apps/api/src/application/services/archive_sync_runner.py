from collections.abc import Callable

from sqlalchemy.orm import Session, sessionmaker

from src.core.config import get_settings
from src.infrastructure.db.repositories.artifact_repository import ArtifactRepository
from src.infrastructure.storage.artifact_storage import ArtifactStorageService


class ArchiveSyncRunner:
    def __init__(
        self,
        session_factory: sessionmaker,
        worker_id: str,
        session_initializer: Callable[[Session], None] | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.worker_id = worker_id
        self.session_initializer = session_initializer
        self.settings = get_settings()

    def consume_next(self) -> int | None:
        session = self.session_factory()
        sync_run_id: int | None = None
        try:
            if self.session_initializer is not None:
                self.session_initializer(session)

            artifacts = ArtifactRepository(session)
            storage = ArtifactStorageService(artifacts)
            sync_run = artifacts.claim_next_sync_run(worker_id=self.worker_id)
            if sync_run is None:
                session.commit()
                return None

            sync_run_id = sync_run.id
            session.commit()
            artifact = artifacts.get_artifact(sync_run.artifact_id)
            if artifact is None:
                raise LookupError("Artifact not found for queued archive sync run.")

            restored_targets = storage.sync_existing_artifact_targets(
                artifact=artifact,
                archive_types=[sync_run.archive_type],
            )
            artifacts.update_sync_run_state(
                sync_run=sync_run,
                status="completed",
                summary=f"Archive sync finished for {restored_targets} target(s).",
            )
            session.commit()
            return sync_run_id
        except Exception as exc:
            session.rollback()
            if sync_run_id is not None:
                self._recover_sync_run(sync_run_id=sync_run_id, error_message=str(exc))
                return sync_run_id
            raise
        finally:
            session.close()

    def _recover_sync_run(self, sync_run_id: int, error_message: str) -> None:
        recovery_session = self.session_factory()
        try:
            if self.session_initializer is not None:
                self.session_initializer(recovery_session)
            artifacts = ArtifactRepository(recovery_session)
            sync_run = artifacts.get_sync_run(sync_run_id)
            if sync_run is None:
                recovery_session.rollback()
                return
            if sync_run.attempt_count < self.settings.archive_sync_max_attempts:
                artifacts.update_sync_run_state(
                    sync_run=sync_run,
                    status="queued",
                    summary=(
                        "Archive sync failed and was re-queued "
                        f"({sync_run.attempt_count}/{self.settings.archive_sync_max_attempts})."
                    ),
                    error_message=error_message,
                )
            else:
                artifacts.update_sync_run_state(
                    sync_run=sync_run,
                    status="failed",
                    summary=(
                        "Archive sync failed after reaching the retry limit "
                        f"({sync_run.attempt_count}/{self.settings.archive_sync_max_attempts})."
                    ),
                    error_message=error_message,
                )
            recovery_session.commit()
        finally:
            recovery_session.close()
