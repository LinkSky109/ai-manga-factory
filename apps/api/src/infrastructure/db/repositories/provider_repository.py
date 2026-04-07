from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.core.config import get_settings
from src.domain.provider.routing import ProviderConfigSnapshot
from src.infrastructure.db.models import ProviderConfigModel, ProviderUsageLogModel


BASE_PROVIDER_CONFIGS = [
    {
        "provider_key": "kling-image",
        "provider_type": "image",
        "routing_mode": "smart",
        "priority": 100,
        "budget_threshold": 80,
        "config": {"vendor": "kling"},
    },
    {
        "provider_key": "vidu-primary",
        "provider_type": "video",
        "routing_mode": "smart",
        "priority": 100,
        "budget_threshold": 80,
        "config": {"vendor": "vidu"},
    },
    {
        "provider_key": "voice-clone-main",
        "provider_type": "voice",
        "routing_mode": "smart",
        "priority": 100,
        "budget_threshold": 85,
        "config": {"vendor": "voice-clone"},
    },
    {
        "provider_key": "llm-story",
        "provider_type": "llm",
        "routing_mode": "smart",
        "priority": 100,
        "budget_threshold": 85,
        "config": {"vendor": "local-sim"},
    },
]


def default_provider_configs() -> list[dict]:
    settings = get_settings()
    providers = list(BASE_PROVIDER_CONFIGS)
    if settings.ark_api_key:
        providers.extend(
            [
                {
                    "provider_key": "ark-image",
                    "provider_type": "image",
                    "routing_mode": "smart",
                    "priority": 150,
                    "budget_threshold": 80,
                    "config": {"vendor": "ark", "model": settings.ark_image_model},
                },
                {
                    "provider_key": "ark-video",
                    "provider_type": "video",
                    "routing_mode": "smart",
                    "priority": 150,
                    "budget_threshold": 80,
                    "config": {"vendor": "ark", "model": settings.ark_video_model},
                },
                {
                    "provider_key": "ark-story",
                    "provider_type": "llm",
                    "routing_mode": "smart",
                    "priority": 150,
                    "budget_threshold": 85,
                    "config": {"vendor": "ark", "model": settings.ark_text_model},
                },
            ]
        )
    return providers


class ProviderRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def seed_defaults(self) -> None:
        existing = {
            row[0]
            for row in self.session.execute(select(ProviderConfigModel.provider_key)).all()
        }
        for provider in default_provider_configs():
            if provider["provider_key"] in existing:
                continue
            self.session.add(
                ProviderConfigModel(
                    provider_key=provider["provider_key"],
                    provider_type=provider["provider_type"],
                    routing_mode=provider["routing_mode"],
                    priority=provider["priority"],
                    budget_threshold=provider["budget_threshold"],
                    config=provider.get("config", {}),
                )
            )
        self.session.flush()

    def list_provider_snapshots(self) -> list[ProviderConfigSnapshot]:
        rows = self.session.scalars(select(ProviderConfigModel).order_by(ProviderConfigModel.priority.desc())).all()
        return [
            ProviderConfigSnapshot(
                provider_key=row.provider_key,
                provider_type=row.provider_type,
                routing_mode=row.routing_mode,
                is_enabled=row.is_enabled,
                priority=row.priority,
                budget_threshold=float(row.budget_threshold),
                config=row.config,
            )
            for row in rows
        ]

    def list_provider_configs(self) -> list[ProviderConfigModel]:
        return list(
            self.session.scalars(
                select(ProviderConfigModel).order_by(ProviderConfigModel.provider_type, ProviderConfigModel.priority.desc())
            )
        )

    def get_provider_config(self, provider_key: str) -> ProviderConfigModel | None:
        return self.session.scalars(
            select(ProviderConfigModel).where(ProviderConfigModel.provider_key == provider_key)
        ).first()

    def update_provider_config(
        self,
        provider_key: str,
        *,
        is_enabled: bool | None = None,
        priority: int | None = None,
        budget_threshold: float | None = None,
        routing_mode: str | None = None,
    ) -> ProviderConfigModel | None:
        provider = self.get_provider_config(provider_key)
        if provider is None:
            return None
        if is_enabled is not None:
            provider.is_enabled = is_enabled
        if priority is not None:
            provider.priority = priority
        if budget_threshold is not None:
            provider.budget_threshold = budget_threshold
        if routing_mode is not None:
            provider.routing_mode = routing_mode
        self.session.flush()
        return provider

    def log_usage(
        self,
        provider_key: str,
        provider_type: str,
        project_id: int | None,
        job_run_id: int | None,
        metric_name: str,
        usage_amount: float,
        usage_unit: str,
    ) -> None:
        self.session.add(
            ProviderUsageLogModel(
                provider_key=provider_key,
                provider_type=provider_type,
                project_id=project_id,
                job_run_id=job_run_id,
                metric_name=metric_name,
                usage_amount=usage_amount,
                usage_unit=usage_unit,
            )
        )
        self.session.flush()

    def summarize_usage(self, project_id: int | None = None) -> list[dict]:
        query = (
            select(
                ProviderConfigModel.provider_key,
                ProviderConfigModel.provider_type,
                ProviderConfigModel.routing_mode,
                ProviderConfigModel.budget_threshold,
                func.coalesce(func.sum(ProviderUsageLogModel.usage_amount), 0),
                func.max(ProviderUsageLogModel.usage_unit),
            )
            .select_from(ProviderConfigModel)
            .join(
                ProviderUsageLogModel,
                ProviderUsageLogModel.provider_key == ProviderConfigModel.provider_key,
                isouter=True,
            )
        )
        if project_id is not None:
            query = query.where(
                (ProviderUsageLogModel.project_id == project_id) | (ProviderUsageLogModel.project_id.is_(None))
            )
        query = query.group_by(
            ProviderConfigModel.provider_key,
            ProviderConfigModel.provider_type,
            ProviderConfigModel.routing_mode,
            ProviderConfigModel.budget_threshold,
        ).order_by(ProviderConfigModel.provider_type, ProviderConfigModel.provider_key)
        items = []
        for provider_key, provider_type, routing_mode, threshold, consumed, unit in self.session.execute(query):
            items.append(
                {
                    "provider_key": provider_key,
                    "provider_type": provider_type,
                    "routing_mode": routing_mode,
                    "budget_threshold": float(threshold),
                    "consumed": float(consumed),
                    "usage_unit": unit or "credits",
                    "alert_status": "warning" if float(consumed) >= float(threshold) else "healthy",
                }
            )
        return items
