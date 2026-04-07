from dataclasses import asdict, dataclass

from src.domain.provider.routing import ProviderDecision, ProviderRouter
from src.domain.workflow.specs import WorkflowNodeSpec


@dataclass(slots=True)
class ExecutionStepOutcome:
    key: str
    title: str
    provider_type: str
    provider_key: str
    provider_candidates: list[str]
    status: str
    usage_amount: float
    usage_unit: str
    error_message: str | None = None


@dataclass(slots=True)
class ExecutionRunResult:
    status: str
    summary: str
    steps: list[ExecutionStepOutcome]
    current_step_key: str | None = None
    checkpoints: list[dict] | None = None


class ExecutionEngine:
    def __init__(self, provider_router: ProviderRouter) -> None:
        self.provider_router = provider_router

    def run(
        self,
        nodes: list[WorkflowNodeSpec],
        routing_mode: str,
        payload: dict,
        resume_from_step_key: str | None = None,
    ) -> ExecutionRunResult:
        active_nodes = nodes
        if resume_from_step_key:
            start_index = next(
                (index for index, node in enumerate(nodes) if node.key == resume_from_step_key),
                None,
            )
            if start_index is None:
                raise ValueError(f"Unknown resume step '{resume_from_step_key}'.")
            active_nodes = nodes[start_index:]

        steps: list[ExecutionStepOutcome] = []
        failure_key = payload.get("simulate_failure_at_step")

        for node in active_nodes:
            provider_decision = self.provider_router.resolve(
                provider_type=node.provider_type,
                routing_mode=routing_mode,
                manual_provider=payload.get("manual_provider"),
            )

            if node.key == failure_key:
                failed_step = ExecutionStepOutcome(
                    key=node.key,
                    title=node.title,
                    provider_type=node.provider_type,
                    provider_key=provider_decision.provider_key,
                    provider_candidates=list(provider_decision.candidates),
                    status="failed",
                    usage_amount=0,
                    usage_unit=self._usage_unit(node.provider_type),
                    error_message=f"Execution interrupted at step '{node.key}'.",
                )
                steps.append(failed_step)
                return ExecutionRunResult(
                    status="failed",
                    summary=f"Job failed at step '{node.title}'.",
                    steps=steps,
                    current_step_key=node.key,
                    checkpoints=[{"step_key": node.key, "payload": asdict(failed_step)}],
                )

            steps.append(
                ExecutionStepOutcome(
                    key=node.key,
                    title=node.title,
                    provider_type=node.provider_type,
                    provider_key=provider_decision.provider_key,
                    provider_candidates=list(provider_decision.candidates),
                    status="completed",
                    usage_amount=self._usage_amount(node.provider_type),
                    usage_unit=self._usage_unit(node.provider_type),
                )
            )

        return ExecutionRunResult(
            status="completed",
            summary="Job completed successfully.",
            steps=steps,
            current_step_key=None,
            checkpoints=[],
        )

    @staticmethod
    def _usage_amount(provider_type: str) -> float:
        usage_map = {
            "llm": 1200,
            "image": 40,
            "video": 85,
            "voice": 35,
            "finalize": 1,
        }
        return float(usage_map.get(provider_type, 10))

    @staticmethod
    def _usage_unit(provider_type: str) -> str:
        if provider_type == "llm":
            return "tokens"
        if provider_type in {"video", "voice", "image"}:
            return "credits"
        return "runs"
