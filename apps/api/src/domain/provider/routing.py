from dataclasses import dataclass


@dataclass(slots=True)
class ProviderConfigSnapshot:
    provider_key: str
    provider_type: str
    routing_mode: str
    is_enabled: bool
    priority: int
    budget_threshold: float
    config: dict | None = None


@dataclass(slots=True)
class ProviderDecision:
    provider_key: str
    provider_type: str
    routing_mode: str
    candidates: list[str]


class ProviderRouter:
    def __init__(self, providers: list[ProviderConfigSnapshot]) -> None:
        self.providers = providers

    def resolve(self, provider_type: str, routing_mode: str, manual_provider: str | None = None) -> ProviderDecision:
        enabled = [provider for provider in self.providers if provider.provider_type == provider_type and provider.is_enabled]
        if manual_provider:
            for provider in enabled:
                if provider.provider_key == manual_provider:
                    return ProviderDecision(
                        provider_key=provider.provider_key,
                        provider_type=provider.provider_type,
                        routing_mode="manual",
                        candidates=[provider.provider_key],
                    )
            raise LookupError(f"Provider '{manual_provider}' is not available for type '{provider_type}'.")

        if not enabled:
            raise LookupError(f"No enabled provider for type '{provider_type}'.")

        ordered = sorted(enabled, key=lambda item: item.priority, reverse=True)
        selected = ordered[0]
        return ProviderDecision(
            provider_key=selected.provider_key,
            provider_type=selected.provider_type,
            routing_mode=routing_mode,
            candidates=[provider.provider_key for provider in ordered],
        )
