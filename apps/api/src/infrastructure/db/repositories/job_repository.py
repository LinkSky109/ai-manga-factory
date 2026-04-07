from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from src.infrastructure.db.models import (
    ChapterPipelineStateModel,
    JobCheckpointModel,
    JobRunModel,
    JobRunStepModel,
)


class JobRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_job(
        self,
        project_id: int,
        chapter_id: int | None,
        workflow_id: int | None,
        execution_mode: str,
        routing_mode: str,
        request_payload: dict,
    ) -> JobRunModel:
        job = JobRunModel(
            project_id=project_id,
            chapter_id=chapter_id,
            workflow_id=workflow_id,
            execution_mode=execution_mode,
            routing_mode=routing_mode,
            request_payload=request_payload,
            status="queued" if execution_mode == "async" else "running",
            queued_at=self._utcnow() if execution_mode == "async" else None,
            started_at=self._utcnow() if execution_mode != "async" else None,
        )
        self.session.add(job)
        self.session.flush()
        return job

    def add_step(
        self,
        job_run_id: int,
        sequence_no: int,
        step_key: str,
        step_name: str,
        provider_type: str,
        provider_key: str,
        status: str,
        usage_amount: float,
        usage_unit: str,
        output_snapshot: dict | None = None,
        error_message: str | None = None,
    ) -> JobRunStepModel:
        step = JobRunStepModel(
            job_run_id=job_run_id,
            sequence_no=sequence_no,
            step_key=step_key,
            step_name=step_name,
            provider_type=provider_type,
            provider_key=provider_key,
            status=status,
            usage_amount=usage_amount,
            usage_unit=usage_unit,
            output_snapshot=output_snapshot,
            error_message=error_message,
        )
        self.session.add(step)
        self.session.flush()
        return step

    def create_checkpoint(self, job_run_id: int, step_key: str, payload: dict, resume_cursor: str | None = None) -> None:
        checkpoint = JobCheckpointModel(
            job_run_id=job_run_id,
            step_key=step_key,
            payload=payload,
            resume_cursor=resume_cursor,
        )
        self.session.add(checkpoint)
        self.session.flush()

    def get_job(self, job_id: int) -> JobRunModel | None:
        return self.session.get(JobRunModel, job_id)

    def list_jobs_by_project(self, project_id: int) -> list[JobRunModel]:
        return list(
            self.session.scalars(
                select(JobRunModel).where(JobRunModel.project_id == project_id).order_by(JobRunModel.id.desc())
            )
        )

    def get_latest_checkpoint(self, job_id: int) -> JobCheckpointModel | None:
        return self.session.scalars(
            select(JobCheckpointModel)
            .where(JobCheckpointModel.job_run_id == job_id)
            .order_by(JobCheckpointModel.id.desc())
        ).first()

    def claim_next_queued_job(self, worker_id: str) -> JobRunModel | None:
        candidate_ids = self.session.scalars(
            select(JobRunModel.id)
            .where(
                JobRunModel.execution_mode == "async",
                JobRunModel.status == "queued",
            )
            .order_by(JobRunModel.queued_at.asc(), JobRunModel.id.asc())
            .limit(5)
        ).all()

        for candidate_id in candidate_ids:
            claimed_at = self._utcnow()
            result = self.session.execute(
                update(JobRunModel)
                .where(
                    JobRunModel.id == candidate_id,
                    JobRunModel.status == "queued",
                )
                .values(
                    status="running",
                    started_at=claimed_at,
                    locked_at=claimed_at,
                    last_heartbeat_at=claimed_at,
                    worker_id=worker_id,
                    summary="Job claimed by async worker.",
                    error_message=None,
                    attempt_count=JobRunModel.attempt_count + 1,
                )
            )
            if result.rowcount:
                self.session.flush()
                return self.session.get(JobRunModel, candidate_id)
        return None

    def update_job_state(
        self,
        job: JobRunModel,
        status: str,
        summary: str,
        current_step_key: str | None,
        error_message: str | None,
    ) -> JobRunModel:
        job.status = status
        job.summary = summary
        job.current_step_key = current_step_key
        job.error_message = error_message
        if status == "queued":
            job.queued_at = self._utcnow()
            job.started_at = None
            job.finished_at = None
            job.locked_at = None
            job.last_heartbeat_at = None
            job.worker_id = None
        elif status == "running":
            claimed_at = self._utcnow()
            job.started_at = claimed_at
            job.locked_at = claimed_at
            job.last_heartbeat_at = claimed_at
            job.finished_at = None
        elif status in {"completed", "failed"}:
            finished_at = self._utcnow()
            job.finished_at = finished_at
            job.locked_at = None
            job.last_heartbeat_at = finished_at
        self.session.flush()
        return job

    def update_chapter_stage(self, chapter_id: int, stage_key: str, status: str, detail: str | None = None) -> None:
        stage = self.session.scalars(
            select(ChapterPipelineStateModel).where(
                ChapterPipelineStateModel.chapter_id == chapter_id,
                ChapterPipelineStateModel.stage_key == stage_key,
            )
        ).first()
        if stage is None:
            return
        stage.status = status
        stage.detail = detail
        self.session.flush()

    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(timezone.utc)
