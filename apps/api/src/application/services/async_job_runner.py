from collections.abc import Callable
from sqlalchemy.orm import Session, sessionmaker

from src.application.services.job_runtime_service import JobRuntimeService
from src.infrastructure.db.repositories.job_repository import JobRepository


class AsyncJobRunner:
    def __init__(
        self,
        session_factory: sessionmaker,
        worker_id: str,
        session_initializer: Callable[[Session], None] | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.worker_id = worker_id
        self.session_initializer = session_initializer

    def consume_next(self) -> int | None:
        session = self.session_factory()
        job = None
        try:
            if self.session_initializer is not None:
                self.session_initializer(session)

            jobs = JobRepository(session)
            runtime = JobRuntimeService(session)
            job = jobs.claim_next_queued_job(worker_id=self.worker_id)
            if job is None:
                session.commit()
                return None

            latest_checkpoint = jobs.get_latest_checkpoint(job.id)
            resume_from_step_key = latest_checkpoint.step_key if latest_checkpoint else job.current_step_key
            runtime.execute_job(
                job=job,
                payload=dict(job.request_payload),
                resume_from_step_key=resume_from_step_key,
            )
            session.commit()
            return job.id
        except Exception as exc:
            session.rollback()
            recovery_session = self.session_factory()
            try:
                if self.session_initializer is not None:
                    self.session_initializer(recovery_session)
                recovery_jobs = JobRepository(recovery_session)
                failed_job = recovery_jobs.get_job(job.id) if job is not None else None
                if failed_job is not None:
                    recovery_jobs.update_job_state(
                        job=failed_job,
                        status="failed",
                        summary="Async worker crashed during execution.",
                        current_step_key=failed_job.current_step_key,
                        error_message=str(exc),
                    )
                    recovery_session.commit()
                else:
                    recovery_session.rollback()
            finally:
                recovery_session.close()
            raise
        finally:
            session.close()
