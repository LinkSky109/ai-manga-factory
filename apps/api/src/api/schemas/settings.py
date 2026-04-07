from pydantic import BaseModel, ConfigDict, Field

from src.api.schemas.storage import StorageTargetResponse


class BootstrapAccountResponse(BaseModel):
    email: str
    display_name: str
    role: str
    status: str


class SettingsAuthOverviewResponse(BaseModel):
    enabled: bool
    bootstrap_accounts: list[BootstrapAccountResponse] = Field(default_factory=list)


class SettingsRuntimeOverviewResponse(BaseModel):
    environment: str
    default_routing_mode: str
    archive_targets: list[str] = Field(default_factory=list)
    object_storage_mode: str
    quark_pan_mode: str
    aliyundrive_mode: str


class ProviderConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    provider_key: str
    provider_type: str
    routing_mode: str
    is_enabled: bool
    priority: int
    budget_threshold: float
    config: dict = Field(default_factory=dict)


class ProviderConfigUpdateRequest(BaseModel):
    routing_mode: str | None = Field(default=None, min_length=1, max_length=32)
    is_enabled: bool | None = None
    priority: int | None = Field(default=None, ge=0, le=1000)
    budget_threshold: float | None = Field(default=None, ge=0, le=100000)


class SettingsOverviewResponse(BaseModel):
    auth: SettingsAuthOverviewResponse
    runtime: SettingsRuntimeOverviewResponse
    storage_targets: list[StorageTargetResponse] = Field(default_factory=list)
    providers: list[ProviderConfigResponse] = Field(default_factory=list)
