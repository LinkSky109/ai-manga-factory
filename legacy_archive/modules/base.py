from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from backend.schemas import ArtifactPreview, CapabilityDescriptor, WorkflowStep


@dataclass
class PlannedJob:
    workflow: list[WorkflowStep]
    artifacts: list[ArtifactPreview]
    summary: str


@dataclass
class ExecutionContext:
    job_id: int
    project_id: int
    job_dir: Path
    report_progress: Callable[[str, str], None] = field(default=lambda *_: None, repr=False)


@dataclass
class ExecutionResult:
    workflow: list[WorkflowStep]
    artifacts: list[ArtifactPreview]
    summary: str


class CapabilityModule:
    descriptor: CapabilityDescriptor

    def plan_job(self, payload: dict) -> PlannedJob:
        raise NotImplementedError

    def execute_job(self, payload: dict, context: ExecutionContext) -> ExecutionResult:
        plan = self.plan_job(payload)
        return ExecutionResult(
            workflow=plan.workflow,
            artifacts=plan.artifacts,
            summary=plan.summary,
        )
