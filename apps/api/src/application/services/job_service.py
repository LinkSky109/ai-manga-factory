from sqlalchemy.orm import Session

from src.application.services.job_runtime_service import JobRuntimeService
from src.infrastructure.db.repositories.job_repository import JobRepository
from src.infrastructure.db.repositories.workflow_repository import WorkflowRepository


class JobService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.jobs = JobRepository(session)
        self.workflows = WorkflowRepository(session)
        self.runtime = JobRuntimeService(session)

    def create_job(
        self,
        project_id: int,
        chapter_id: int | None,
        workflow_id: int,
        execution_mode: str,
        input_payload: dict,
        routing_mode: str | None = None,
    ):
        workflow = self.workflows.get_workflow(workflow_id)
        if workflow is None:
            raise LookupError("Workflow not found.")

        effective_routing_mode = routing_mode or workflow.routing_mode
        job = self.jobs.create_job(
            project_id=project_id,
            chapter_id=chapter_id,
            workflow_id=workflow_id,
            execution_mode=execution_mode,
            routing_mode=effective_routing_mode,
            request_payload=input_payload,
        )

        if execution_mode == "async":
            self.jobs.update_job_state(
                job=job,
                status="queued",
                summary="Job queued for worker execution.",
                current_step_key=None,
                error_message=None,
            )
            self.session.commit()
            self.session.refresh(job)
            return job

        self.runtime.execute_job(job=job, payload=input_payload, resume_from_step_key=None)
        self.session.commit()
        self.session.refresh(job)
        return job

    def resume_job(self, job_id: int, override_input: dict | None = None):
        job = self.jobs.get_job(job_id)
        if job is None:
            raise LookupError("Job not found.")
        if job.workflow_id is None:
            raise LookupError("Workflow reference missing.")

        workflow = self.workflows.get_workflow(job.workflow_id)
        if workflow is None:
            raise LookupError("Workflow not found.")

        latest_checkpoint = self.jobs.get_latest_checkpoint(job_id)
        resume_from_step_key = latest_checkpoint.step_key if latest_checkpoint else job.current_step_key
        resume_payload = dict(job.request_payload)
        resume_payload.pop("simulate_failure_at_step", None)
        if override_input:
            resume_payload.update(override_input)
        job.request_payload = resume_payload

        if job.execution_mode == "async":
            self.jobs.update_job_state(
                job=job,
                status="queued",
                summary="Job re-queued for resume.",
                current_step_key=resume_from_step_key,
                error_message=None,
            )
            self.session.commit()
            self.session.refresh(job)
            return job

        self.runtime.execute_job(
            job=job,
            payload=resume_payload,
            resume_from_step_key=resume_from_step_key,
        )
        self.session.commit()
        self.session.refresh(job)
        return job

    def get_job(self, job_id: int):
        return self.jobs.get_job(job_id)

    def list_jobs_by_project(self, project_id: int):
        return self.jobs.list_jobs_by_project(project_id)
