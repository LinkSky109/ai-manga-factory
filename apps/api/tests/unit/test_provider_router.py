import unittest

from src.domain.provider.routing import ProviderConfigSnapshot, ProviderRouter


class ProviderRouterTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.router = ProviderRouter(
            providers=[
                ProviderConfigSnapshot(
                    provider_key="vidu-primary",
                    provider_type="video",
                    routing_mode="smart",
                    is_enabled=True,
                    priority=100,
                    budget_threshold=80,
                    config={},
                ),
                ProviderConfigSnapshot(
                    provider_key="vidu-backup",
                    provider_type="video",
                    routing_mode="smart",
                    is_enabled=True,
                    priority=80,
                    budget_threshold=90,
                    config={},
                ),
                ProviderConfigSnapshot(
                    provider_key="voice-clone-main",
                    provider_type="voice",
                    routing_mode="smart",
                    is_enabled=True,
                    priority=100,
                    budget_threshold=85,
                    config={},
                ),
            ]
        )

    def test_prefers_highest_priority_provider_for_smart_routing(self) -> None:
        decision = self.router.resolve(provider_type="video", routing_mode="smart")

        self.assertEqual(decision.provider_key, "vidu-primary")
        self.assertEqual(decision.candidates, ["vidu-primary", "vidu-backup"])

    def test_manual_provider_override_wins_when_enabled(self) -> None:
        decision = self.router.resolve(
            provider_type="video",
            routing_mode="manual",
            manual_provider="vidu-backup",
        )

        self.assertEqual(decision.provider_key, "vidu-backup")
        self.assertEqual(decision.routing_mode, "manual")
        self.assertEqual(decision.candidates, ["vidu-backup"])

    def test_raises_when_no_provider_available(self) -> None:
        with self.assertRaises(LookupError):
            self.router.resolve(provider_type="image", routing_mode="smart")


if __name__ == "__main__":
    unittest.main()
