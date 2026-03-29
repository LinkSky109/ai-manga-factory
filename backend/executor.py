from backend.config import ARTIFACTS_DIR
from backend.schemas import ArtifactPreview
from backend.storage import PlatformStore
from modules.base import ExecutionContext
from modules.registry import CapabilityRegistry
from shared.result_depository import record_job_result


class JobExecutor:
    def __init__(self, store: PlatformStore, registry: CapabilityRegistry):
        self.store = store
        self.registry = registry
        ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    def reconcile_orphaned_jobs(self) -> int:
        orphaned_jobs = [job for job in self.store.list_jobs() if job.status == "running"]
        for job in orphaned_jobs:
            self.store.update_job(
                job_id=job.id,
                status="failed",
                workflow=self._workflow_marked_failed(
                    job.workflow,
                    details="任务执行进程已中断，服务重启后自动标记为失败，请按需重跑。",
                ),
                artifacts=job.artifacts,
                summary="任务执行进程已中断，服务重启后自动标记为失败，请按需重跑。",
                error="orphaned_running_job_after_restart",
            )
            self._persist_result_summary(job.id)
        return len(orphaned_jobs)

    def execute(self, job_id: int) -> None:
        job = self.store.get_job(job_id)
        module = self.registry.get(job.capability_id)
        job_dir = ARTIFACTS_DIR / f"job_{job.id}"
        job_dir.mkdir(parents=True, exist_ok=True)

        running_workflow = []
        first_pending = True
        for step in job.workflow:
            if first_pending:
                running_workflow.append(step.model_copy(update={"status": "running"}))
                first_pending = False
            else:
                running_workflow.append(step.model_copy(update={"status": "pending"}))

        self.store.update_job(
            job_id=job.id,
            status="running",
            workflow=running_workflow,
            artifacts=job.artifacts,
            summary=job.summary,
            error=None,
        )

        try:
            result = module.execute_job(
                payload=job.input,
                context=ExecutionContext(
                    job_id=job.id,
                    project_id=job.project_id,
                    job_dir=job_dir,
                    report_progress=self._build_progress_reporter(job_id=job.id),
                ),
            )
            completed_workflow = [
                step.model_copy(update={"status": "completed", "details": None})
                for step in result.workflow
            ]
            self.store.update_job(
                job_id=job.id,
                status="completed",
                workflow=completed_workflow,
                artifacts=result.artifacts,
                summary=result.summary,
                error=None,
            )
            self._persist_result_summary(job.id)
        except Exception as exc:
            failed_workflow = []
            failed_marked = False
            for step in job.workflow:
                if not failed_marked:
                    failed_workflow.append(
                        step.model_copy(update={"status": "failed", "details": str(exc)})
                    )
                    failed_marked = True
                else:
                    failed_workflow.append(step.model_copy(update={"status": "pending"}))

            self.store.update_job(
                job_id=job.id,
                status="failed",
                workflow=failed_workflow,
                artifacts=job.artifacts,
                summary=job.summary,
                error=str(exc),
            )
            self._persist_result_summary(job.id)

    def _persist_result_summary(self, job_id: int) -> None:
        final_job = self.store.get_job(job_id)
        project = self.store.get_project(final_job.project_id)
        try:
            extra_artifacts = record_job_result(final_job, project.name)
        except Exception:
            return

        merged_artifacts = self._merge_artifacts(final_job.artifacts, extra_artifacts)
        self.store.update_job(
            job_id=final_job.id,
            status=final_job.status,
            workflow=final_job.workflow,
            artifacts=merged_artifacts,
            summary=final_job.summary,
            error=final_job.error,
        )

    def _merge_artifacts(
        self,
        artifacts: list[ArtifactPreview],
        extra_artifacts: list[ArtifactPreview],
    ) -> list[ArtifactPreview]:
        merged: list[ArtifactPreview] = []
        seen: set[tuple[str, str | None]] = set()
        for artifact in [*artifacts, *extra_artifacts]:
            key = (artifact.label, artifact.path_hint)
            if key in seen:
                continue
            seen.add(key)
            merged.append(artifact)
        return merged

    def _build_progress_reporter(self, *, job_id: int):
        def report(step_key: str, details: str) -> None:
            current_job = self.store.get_job(job_id)
            workflow = self._workflow_with_progress(current_job.workflow, step_key=step_key, details=details)
            self.store.update_job(
                job_id=current_job.id,
                status="running",
                workflow=workflow,
                artifacts=current_job.artifacts,
                summary=details or current_job.summary,
                error=None,
            )

        return report

    def _workflow_with_progress(
        self,
        workflow: list,
        *,
        step_key: str,
        details: str,
    ) -> list:
        updated = []
        active_found = False
        for step in workflow:
            if active_found:
                updated.append(step.model_copy(update={"status": "pending", "details": None}))
                continue

            if step.key == step_key:
                updated.append(step.model_copy(update={"status": "running", "details": details}))
                active_found = True
            else:
                updated.append(step.model_copy(update={"status": "completed", "details": step.details}))

        return updated

    def _workflow_marked_failed(self, workflow: list, *, details: str) -> list:
        updated = []
        failed_marked = False
        for step in workflow:
            if step.status == "completed":
                updated.append(step.model_copy(update={"status": "completed"}))
                continue
            if not failed_marked:
                updated.append(step.model_copy(update={"status": "failed", "details": details}))
                failed_marked = True
                continue
            updated.append(step.model_copy(update={"status": "pending", "details": None}))

        if failed_marked:
            return updated

        if not workflow:
            return updated

        first, *rest = workflow
        return [
            first.model_copy(update={"status": "failed", "details": details}),
            *[step.model_copy(update={"status": "pending", "details": None}) for step in rest],
        ]
