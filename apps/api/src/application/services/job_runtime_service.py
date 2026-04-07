from sqlalchemy.orm import Session
from dataclasses import asdict

from src.domain.execution.engine import ExecutionEngine
from src.domain.provider.routing import ProviderRouter
from src.domain.workflow.specs import WorkflowDefinitionSpec
from src.infrastructure.db.models import JobRunModel
from src.infrastructure.db.repositories.artifact_repository import ArtifactRepository
from src.infrastructure.db.repositories.job_repository import JobRepository
from src.infrastructure.db.repositories.provider_repository import ProviderRepository
from src.infrastructure.db.repositories.workflow_repository import WorkflowRepository
from src.infrastructure.storage.artifact_storage import ArtifactStorageService


class JobRuntimeService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.jobs = JobRepository(session)
        self.artifacts = ArtifactRepository(session)
        self.providers = ProviderRepository(session)
        self.workflows = WorkflowRepository(session)
        self.storage = ArtifactStorageService(self.artifacts)

    def execute_job(
        self,
        job: JobRunModel,
        payload: dict,
        resume_from_step_key: str | None,
    ) -> None:
        if job.workflow_id is None:
            raise LookupError("Workflow reference missing.")

        workflow = self.workflows.get_workflow(job.workflow_id)
        if workflow is None:
            raise LookupError("Workflow not found.")

        provider_snapshots = self.providers.list_provider_snapshots()
        router = ProviderRouter(provider_snapshots)
        engine = ExecutionEngine(provider_router=router)
        spec = WorkflowDefinitionSpec.model_validate(workflow.spec)
        result = engine.run(
            nodes=spec.nodes,
            routing_mode=job.routing_mode,
            payload=payload,
            resume_from_step_key=resume_from_step_key,
        )

        if resume_from_step_key:
            retained_steps = [step for step in job.steps if step.step_key != resume_from_step_key]
            job.steps[:] = retained_steps

        sequence_start = len(job.steps)
        for index, step in enumerate(result.steps, start=sequence_start + 1):
            output_snapshot = {
                "provider_candidates": list(getattr(step, "provider_candidates", []) or [step.provider_key]),
                "resolved_provider_key": step.provider_key,
            }
            if step.status == "completed":
                try:
                    storage_snapshot = self.storage.materialize_step_artifact(job=job, step=step, payload=payload) or {}
                    output_snapshot = {
                        **output_snapshot,
                        **storage_snapshot,
                    }
                except Exception as exc:
                    step.status = "failed"
                    step.usage_amount = 0
                    step.error_message = str(exc)
                    result.status = "failed"
                    result.summary = f"Job failed at step '{step.title}'."
                    result.current_step_key = step.key
                    result.checkpoints = list(result.checkpoints or []) + [
                        {"step_key": step.key, "payload": asdict(step)}
                    ]
                    output_snapshot = {
                        **output_snapshot,
                        "provider_attempts": [
                            {
                                "provider_key": step.provider_key,
                                "status": "failed",
                                "error_message": str(exc),
                            }
                        ],
                    }

            self.jobs.add_step(
                job_run_id=job.id,
                sequence_no=index,
                step_key=step.key,
                step_name=step.title,
                provider_type=step.provider_type,
                provider_key=step.provider_key,
                status=step.status,
                usage_amount=step.usage_amount,
                usage_unit=step.usage_unit,
                output_snapshot=output_snapshot,
                error_message=step.error_message,
            )
            if step.status == "completed":
                self.providers.log_usage(
                    provider_key=step.provider_key,
                    provider_type=step.provider_type,
                    project_id=job.project_id,
                    job_run_id=job.id,
                    metric_name="generation",
                    usage_amount=step.usage_amount,
                    usage_unit=step.usage_unit,
                )
            if job.chapter_id:
                self.jobs.update_chapter_stage(
                    chapter_id=job.chapter_id,
                    stage_key=step.key,
                    status="completed" if step.status == "completed" else "failed",
                    detail=step.error_message,
                )
            if step.status == "failed":
                break

        if result.checkpoints:
            for checkpoint in result.checkpoints:
                self.jobs.create_checkpoint(
                    job_run_id=job.id,
                    step_key=checkpoint["step_key"],
                    payload=checkpoint["payload"],
                    resume_cursor=checkpoint["step_key"],
                )

        self.jobs.update_job_state(
            job=job,
            status=result.status,
            summary=result.summary,
            current_step_key=result.current_step_key,
            error_message=result.steps[-1].error_message if result.status == "failed" else None,
        )
