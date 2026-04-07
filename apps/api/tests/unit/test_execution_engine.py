import unittest

from src.domain.execution.engine import ExecutionEngine
from src.domain.provider.routing import ProviderDecision, ProviderRouter
from src.domain.workflow.specs import WorkflowNodeSpec


class StubProviderRouter(ProviderRouter):
    def __init__(self) -> None:
        super().__init__(providers=[])

    def resolve(self, provider_type: str, routing_mode: str, manual_provider: str | None = None) -> ProviderDecision:
        key = manual_provider or f"default-{provider_type}"
        return ProviderDecision(
            provider_key=key,
            provider_type=provider_type,
            routing_mode=routing_mode,
            candidates=[key],
        )


class ExecutionEngineTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = ExecutionEngine(provider_router=StubProviderRouter())
        self.nodes = [
            WorkflowNodeSpec(key="storyboard", title="Storyboard", provider_type="llm"),
            WorkflowNodeSpec(key="video", title="Video", provider_type="video"),
            WorkflowNodeSpec(key="voice", title="Voice", provider_type="voice"),
        ]

    def test_run_completes_all_steps_when_no_failure_requested(self) -> None:
        result = self.engine.run(
            nodes=self.nodes,
            routing_mode="smart",
            payload={},
        )

        self.assertEqual(result.status, "completed")
        self.assertIsNone(result.current_step_key)
        self.assertEqual([step.status for step in result.steps], ["completed", "completed", "completed"])
        self.assertEqual(result.checkpoints, [])

    def test_run_stops_on_failure_and_produces_checkpoint(self) -> None:
        result = self.engine.run(
            nodes=self.nodes,
            routing_mode="smart",
            payload={"simulate_failure_at_step": "video"},
        )

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.current_step_key, "video")
        self.assertEqual([step.status for step in result.steps], ["completed", "failed"])
        self.assertEqual(len(result.checkpoints), 1)
        self.assertEqual(result.checkpoints[0]["step_key"], "video")

    def test_resume_starts_from_first_incomplete_step(self) -> None:
        failed = self.engine.run(
            nodes=self.nodes,
            routing_mode="smart",
            payload={"simulate_failure_at_step": "video"},
        )

        resumed = self.engine.run(
            nodes=self.nodes,
            routing_mode="smart",
            payload={},
            resume_from_step_key=failed.current_step_key,
        )

        self.assertEqual(resumed.status, "completed")
        self.assertEqual([step.key for step in resumed.steps], ["video", "voice"])
        self.assertEqual([step.status for step in resumed.steps], ["completed", "completed"])


if __name__ == "__main__":
    unittest.main()
