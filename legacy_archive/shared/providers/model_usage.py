from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Iterable

from backend.config import DATA_DIR


PROVIDER_USAGE_DIR = DATA_DIR / "provider_usage"
MODEL_BUDGET_CONFIG_PATH = PROVIDER_USAGE_DIR / "model_budget_config.json"
USAGE_LEDGER_PATH = PROVIDER_USAGE_DIR / "usage_ledger.json"
_LOCK_PATH = PROVIDER_USAGE_DIR / ".usage.lock"
_IN_PROCESS_LOCK = RLock()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_now() -> str:
    return _utc_now().isoformat()


def _safe_ratio(numerator: float, denominator: float | None) -> float:
    if not denominator or denominator <= 0:
        return 0.0
    return round(float(numerator) / float(denominator), 4)


def estimate_text_tokens_from_text(value: str) -> int:
    text = str(value or "").strip()
    if not text:
        return 0
    return max(1, len(text))


def estimate_text_tokens_from_messages(messages: list[dict[str, Any]]) -> int:
    total = 0
    for item in messages:
        total += estimate_text_tokens_from_text(item.get("content", ""))
        total += estimate_text_tokens_from_text(item.get("role", ""))
    return total


@contextmanager
def _locked_usage_file():
    PROVIDER_USAGE_DIR.mkdir(parents=True, exist_ok=True)
    _LOCK_PATH.touch(exist_ok=True)
    with _IN_PROCESS_LOCK:
        lock_handle = _LOCK_PATH.open("a+b")
        try:
            if os.name == "nt":
                import msvcrt

                lock_handle.seek(0)
                msvcrt.locking(lock_handle.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl

                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            yield
        finally:
            try:
                if os.name == "nt":
                    import msvcrt

                    lock_handle.seek(0)
                    msvcrt.locking(lock_handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
            finally:
                lock_handle.close()


@dataclass(slots=True)
class RoutingDecision:
    provider: str
    capability: str
    requested_model: str
    preferred_model: str
    candidates: list[str]
    switched: bool
    reason: str
    estimated_cost: float


class ModelUsageManager:
    DEFAULT_WARNING_RATIO = 0.8
    DEFAULT_SWITCH_RATIO = 0.9
    DEFAULT_QUOTA_ERROR_COOLDOWN_MINUTES = 30
    MAX_EVENTS = 80

    def __init__(
        self,
        *,
        config_path: Path = MODEL_BUDGET_CONFIG_PATH,
        ledger_path: Path = USAGE_LEDGER_PATH,
    ) -> None:
        self.config_path = config_path
        self.ledger_path = ledger_path
        self._ensure_files_exist()

    def plan_call(
        self,
        *,
        provider: str,
        capability: str,
        primary: str,
        fallbacks: Iterable[str] = (),
        estimated_cost: float = 0.0,
    ) -> RoutingDecision:
        runtime_models = self._unique([primary, *fallbacks])
        if not runtime_models:
            raise ValueError("No runtime models supplied for routing")

        with _locked_usage_file():
            config = self._load_json(self.config_path, self._default_config())
            ledger = self._load_json(self.ledger_path, self._default_ledger())
            config_changed = self._ensure_runtime_models(
                config=config,
                provider=provider,
                capability=capability,
                runtime_models=runtime_models,
            )
            self._reset_period_if_needed(config=config, ledger=ledger)

            provider_cfg = config["providers"][provider]
            capability_cfg = provider_cfg["capabilities"][capability]
            capability_ledger = self._ensure_capability_ledger(
                ledger=ledger,
                provider=provider,
                capability=capability,
                model_names=[item["name"] for item in capability_cfg["models"]],
            )

            ordered = self._ordered_models(
                capability_cfg=capability_cfg,
                runtime_models=runtime_models,
                primary=primary,
            )
            preferred_model = ordered[0]
            switched = False
            reason = "using requested model"
            switch_reason = ""
            warning_ratio = float(provider_cfg.get("warning_ratio", self.DEFAULT_WARNING_RATIO))
            switch_ratio = float(provider_cfg.get("switch_ratio", self.DEFAULT_SWITCH_RATIO))

            for index, model in enumerate(ordered):
                model_cfg = self._find_model_config(capability_cfg, model)
                if not model_cfg or not model_cfg.get("enabled", True):
                    continue
                model_ledger = capability_ledger["models"][model]
                exhausted_until = self._parse_datetime(model_ledger.get("exhausted_until"))
                if exhausted_until and exhausted_until > _utc_now():
                    continue
                budget_limit = self._as_float(model_cfg.get("budget_limit"))
                current_usage = self._current_usage_value(model_ledger, capability)
                projected_usage = current_usage + max(0.0, float(estimated_cost))
                projected_ratio = _safe_ratio(projected_usage, budget_limit)
                if budget_limit and projected_ratio >= switch_ratio and index < len(ordered) - 1:
                    preferred_model = ordered[index + 1]
                    switched = True
                    switch_reason = (
                        f"{model} projected usage {projected_ratio:.0%} reached switch threshold "
                        f"{switch_ratio:.0%}, switched to {preferred_model}"
                    )
                    continue
                preferred_model = model
                if switch_reason:
                    reason = switch_reason
                    break
                if budget_limit and projected_ratio >= warning_ratio:
                    reason = (
                        f"{model} projected usage {projected_ratio:.0%} reached warning threshold "
                        f"{warning_ratio:.0%}"
                    )
                else:
                    reason = "using healthiest available model"
                break

            candidates = self._unique([preferred_model, *ordered])
            if switched:
                self._append_event(
                    capability_ledger,
                    {
                        "type": "switch",
                        "timestamp": _iso_now(),
                        "from_model": primary,
                        "to_model": preferred_model,
                        "reason": reason,
                    },
                )
            capability_ledger["active_model"] = preferred_model
            capability_ledger["last_routing"] = {
                "requested_model": primary,
                "preferred_model": preferred_model,
                "candidates": candidates,
                "estimated_cost": estimated_cost,
                "reason": reason,
                "switched": switched,
                "timestamp": _iso_now(),
            }
            if config_changed:
                self._write_json(self.config_path, config)
            self._write_json(self.ledger_path, ledger)

        return RoutingDecision(
            provider=provider,
            capability=capability,
            requested_model=primary,
            preferred_model=preferred_model,
            candidates=candidates,
            switched=switched,
            reason=reason,
            estimated_cost=max(0.0, float(estimated_cost)),
        )

    def record_success(
        self,
        *,
        provider: str,
        capability: str,
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_value: float | None = None,
    ) -> None:
        with _locked_usage_file():
            config = self._load_json(self.config_path, self._default_config())
            ledger = self._load_json(self.ledger_path, self._default_ledger())
            self._reset_period_if_needed(config=config, ledger=ledger)
            capability_ledger = self._ensure_capability_ledger(ledger=ledger, provider=provider, capability=capability, model_names=[model])
            model_ledger = capability_ledger["models"][model]
            usage_value = self._resolve_usage_value(capability=capability, input_tokens=input_tokens, output_tokens=output_tokens, cost_value=cost_value)
            model_ledger["usage_value"] = round(float(model_ledger.get("usage_value", 0.0)) + usage_value, 2)
            model_ledger["request_count"] = int(model_ledger.get("request_count", 0)) + 1
            model_ledger["success_count"] = int(model_ledger.get("success_count", 0)) + 1
            model_ledger["input_estimated_tokens"] = int(model_ledger.get("input_estimated_tokens", 0)) + int(input_tokens)
            model_ledger["output_estimated_tokens"] = int(model_ledger.get("output_estimated_tokens", 0)) + int(output_tokens)
            model_ledger["last_used_at"] = _iso_now()
            model_ledger["last_error"] = ""
            capability_ledger["active_model"] = model
            self._write_json(self.ledger_path, ledger)

    def record_failure(
        self,
        *,
        provider: str,
        capability: str,
        model: str,
        error_message: str,
        input_tokens: int = 0,
        cost_value: float | None = None,
        quota_like: bool = False,
    ) -> None:
        with _locked_usage_file():
            config = self._load_json(self.config_path, self._default_config())
            ledger = self._load_json(self.ledger_path, self._default_ledger())
            self._reset_period_if_needed(config=config, ledger=ledger)
            capability_ledger = self._ensure_capability_ledger(ledger=ledger, provider=provider, capability=capability, model_names=[model])
            model_ledger = capability_ledger["models"][model]
            model_ledger["request_count"] = int(model_ledger.get("request_count", 0)) + 1
            model_ledger["failure_count"] = int(model_ledger.get("failure_count", 0)) + 1
            model_ledger["input_estimated_tokens"] = int(model_ledger.get("input_estimated_tokens", 0)) + int(input_tokens)
            if cost_value is not None:
                model_ledger["usage_value"] = round(float(model_ledger.get("usage_value", 0.0)) + max(0.0, float(cost_value)), 2)
            model_ledger["last_used_at"] = _iso_now()
            model_ledger["last_error"] = str(error_message).strip()
            if quota_like:
                provider_cfg = config.get("providers", {}).get(provider, {})
                cooldown_minutes = int(provider_cfg.get("quota_error_cooldown_minutes", self.DEFAULT_QUOTA_ERROR_COOLDOWN_MINUTES))
                exhausted_until = _utc_now() + timedelta(minutes=max(1, cooldown_minutes))
                model_ledger["exhausted_until"] = exhausted_until.isoformat()
                self._append_event(
                    capability_ledger,
                    {
                        "type": "quota_error",
                        "timestamp": _iso_now(),
                        "model": model,
                        "error": model_ledger["last_error"],
                        "exhausted_until": model_ledger["exhausted_until"],
                    },
                )
            self._write_json(self.ledger_path, ledger)

    def get_provider_usage_snapshot(self, provider: str = "ark") -> dict[str, Any]:
        with _locked_usage_file():
            config = self._load_json(self.config_path, self._default_config())
            ledger = self._load_json(self.ledger_path, self._default_ledger())
            self._reset_period_if_needed(config=config, ledger=ledger)
            self._write_json(self.ledger_path, ledger)

        provider_cfg = config.get("providers", {}).get(provider, {})
        provider_ledger = ledger.get("providers", {}).get(provider, {})
        capabilities: list[dict[str, Any]] = []
        for capability, capability_cfg in provider_cfg.get("capabilities", {}).items():
            capability_ledger = provider_ledger.get("capabilities", {}).get(capability, {})
            models: list[dict[str, Any]] = []
            for model_cfg in capability_cfg.get("models", []):
                name = model_cfg["name"]
                model_ledger = capability_ledger.get("models", {}).get(name, self._default_model_ledger())
                budget_limit = self._as_float(model_cfg.get("budget_limit"))
                usage_value = float(model_ledger.get("usage_value", 0.0))
                usage_ratio = _safe_ratio(usage_value, budget_limit)
                exhausted_until = model_ledger.get("exhausted_until")
                status = self._status_label(
                    enabled=bool(model_cfg.get("enabled", True)),
                    usage_ratio=usage_ratio,
                    warning_ratio=float(provider_cfg.get("warning_ratio", self.DEFAULT_WARNING_RATIO)),
                    switch_ratio=float(provider_cfg.get("switch_ratio", self.DEFAULT_SWITCH_RATIO)),
                    exhausted_until=exhausted_until,
                )
                models.append(
                    {
                        "name": name,
                        "label": model_cfg.get("label", name),
                        "priority": int(model_cfg.get("priority", 99)),
                        "enabled": bool(model_cfg.get("enabled", True)),
                        "budget_limit": budget_limit,
                        "usage_value": usage_value,
                        "usage_ratio": usage_ratio,
                        "usage_unit": capability_cfg.get("usage_unit", "request_count"),
                        "status": status,
                        "request_count": int(model_ledger.get("request_count", 0)),
                        "success_count": int(model_ledger.get("success_count", 0)),
                        "failure_count": int(model_ledger.get("failure_count", 0)),
                        "input_estimated_tokens": int(model_ledger.get("input_estimated_tokens", 0)),
                        "output_estimated_tokens": int(model_ledger.get("output_estimated_tokens", 0)),
                        "last_used_at": model_ledger.get("last_used_at"),
                        "last_error": model_ledger.get("last_error") or None,
                        "exhausted_until": exhausted_until,
                    }
                )
            capabilities.append(
                {
                    "capability": capability,
                    "usage_unit": capability_cfg.get("usage_unit", "request_count"),
                    "warning_ratio": float(provider_cfg.get("warning_ratio", self.DEFAULT_WARNING_RATIO)),
                    "switch_ratio": float(provider_cfg.get("switch_ratio", self.DEFAULT_SWITCH_RATIO)),
                    "active_model": capability_ledger.get("active_model"),
                    "last_routing": capability_ledger.get("last_routing", {}),
                    "recent_events": list(capability_ledger.get("events", []))[-10:],
                    "models": models,
                }
            )

        return {
            "provider": provider,
            "display_name": provider_cfg.get("display_name", provider),
            "config_path": str(self.config_path),
            "ledger_path": str(self.ledger_path),
            "period_key": ledger.get("period_key"),
            "updated_at": ledger.get("updated_at"),
            "measurement_note": "文本用量为本地估算 tokens，图片和视频用量按调用次数统计；可在配置文件中调整各模型 budget_limit。",
            "capabilities": capabilities,
        }

    def _ensure_files_exist(self) -> None:
        PROVIDER_USAGE_DIR.mkdir(parents=True, exist_ok=True)
        if not self.config_path.exists():
            self._write_json(self.config_path, self._default_config())
        if not self.ledger_path.exists():
            self._write_json(self.ledger_path, self._default_ledger())

    def _default_config(self) -> dict[str, Any]:
        return {
            "updated_at": _iso_now(),
            "providers": {
                "ark": {
                    "display_name": "火山方舟",
                    "warning_ratio": self.DEFAULT_WARNING_RATIO,
                    "switch_ratio": self.DEFAULT_SWITCH_RATIO,
                    "quota_error_cooldown_minutes": self.DEFAULT_QUOTA_ERROR_COOLDOWN_MINUTES,
                    "capabilities": {
                        "text": {
                            "usage_unit": "estimated_tokens",
                            "models": [
                                {
                                    "name": "Doubao-Seed-1.6",
                                    "label": "Doubao Seed 1.6",
                                    "priority": 1,
                                    "budget_limit": 440000,
                                    "enabled": True,
                                },
                                {
                                    "name": "doubao-seed-1-6-251015",
                                    "label": "Doubao Seed 1.6 251015",
                                    "priority": 2,
                                    "budget_limit": 400000,
                                    "enabled": True,
                                },
                                {
                                    "name": "doubao-seed-1.6",
                                    "label": "Doubao Seed 1.6 Alias",
                                    "priority": 3,
                                    "budget_limit": 440000,
                                    "enabled": True,
                                },
                                {
                                    "name": "doubao-seed-1.6-flash",
                                    "label": "Doubao Seed 1.6 Flash",
                                    "priority": 4,
                                    "budget_limit": 480000,
                                    "enabled": True,
                                },
                                {
                                    "name": "doubao-seed-2-0-lite-260215",
                                    "label": "Doubao Seed 2.0 Lite 260215",
                                    "priority": 5,
                                    "budget_limit": 280000,
                                    "enabled": True,
                                },
                                {
                                    "name": "doubao-seed-2-0-mini-260215",
                                    "label": "Doubao Seed 2.0 Mini 260215",
                                    "priority": 6,
                                    "budget_limit": 360000,
                                    "enabled": True,
                                },
                                {
                                    "name": "doubao-seed-2-0-pro-260215",
                                    "label": "Doubao Seed 2.0 Pro 260215",
                                    "priority": 7,
                                    "budget_limit": 180000,
                                    "enabled": True,
                                },
                            ],
                        },
                        "image": {
                            "usage_unit": "request_count",
                            "models": [
                                {
                                    "name": "Doubao-Seedream-4.5",
                                    "label": "Doubao Seedream 4.5",
                                    "priority": 1,
                                    "budget_limit": 180,
                                    "enabled": True,
                                },
                                {
                                    "name": "doubao-seedream-4-5-251128",
                                    "label": "Seedream 4.5 251128",
                                    "priority": 2,
                                    "budget_limit": 180,
                                    "enabled": True,
                                },
                                {
                                    "name": "doubao-seedream-5-0-260128",
                                    "label": "Seedream 5.0 260128",
                                    "priority": 3,
                                    "budget_limit": 100,
                                    "enabled": True,
                                },
                                {
                                    "name": "doubao-seedream-5-0-lite-260128",
                                    "label": "Seedream 5.0 Lite 260128",
                                    "priority": 4,
                                    "budget_limit": 140,
                                    "enabled": True,
                                },
                                {
                                    "name": "doubao-seedream-4-0-250828",
                                    "label": "Seedream 4.0 250828",
                                    "priority": 5,
                                    "budget_limit": 220,
                                    "enabled": True,
                                },
                            ],
                        },
                        "video": {
                            "usage_unit": "request_count",
                            "models": [
                                {
                                    "name": "Doubao-Seedance-1.5-pro",
                                    "label": "Doubao Seedance 1.5 Pro",
                                    "priority": 1,
                                    "budget_limit": 40,
                                    "enabled": True,
                                },
                                {
                                    "name": "doubao-seedance-1-5-pro-251215",
                                    "label": "Seedance 1.5 Pro 251215",
                                    "priority": 2,
                                    "budget_limit": 40,
                                    "enabled": True,
                                },
                                {
                                    "name": "Doubao-Seedance-1.0-pro",
                                    "label": "Doubao Seedance 1.0 Pro",
                                    "priority": 3,
                                    "budget_limit": 60,
                                    "enabled": True,
                                },
                                {
                                    "name": "doubao-seedance-1-0-pro-250528",
                                    "label": "Seedance 1.0 Pro 250528",
                                    "priority": 4,
                                    "budget_limit": 40,
                                    "enabled": True,
                                },
                            ],
                        },
                    },
                }
            },
        }

    def _default_ledger(self) -> dict[str, Any]:
        now = _utc_now()
        return {
            "updated_at": now.isoformat(),
            "period_key": now.strftime("%Y-%m"),
            "providers": {},
        }

    def _default_model_ledger(self) -> dict[str, Any]:
        return {
            "usage_value": 0.0,
            "request_count": 0,
            "success_count": 0,
            "failure_count": 0,
            "input_estimated_tokens": 0,
            "output_estimated_tokens": 0,
            "last_used_at": "",
            "last_error": "",
            "exhausted_until": "",
        }

    def _load_json(self, path: Path, fallback: dict[str, Any]) -> dict[str, Any]:
        if not path.exists():
            return json.loads(json.dumps(fallback))
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return json.loads(json.dumps(fallback))

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload["updated_at"] = _iso_now()
        fd, temp_name = tempfile.mkstemp(dir=str(path.parent), prefix=path.stem, suffix=".tmp")
        temp_path = Path(temp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
            os.replace(temp_path, path)
        finally:
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)

    def _reset_period_if_needed(self, *, config: dict[str, Any], ledger: dict[str, Any]) -> None:
        current_period = _utc_now().strftime("%Y-%m")
        if ledger.get("period_key") == current_period:
            return
        providers = ledger.setdefault("providers", {})
        for provider_data in providers.values():
            for capability_data in provider_data.setdefault("capabilities", {}).values():
                capability_data["active_model"] = ""
                capability_data["last_routing"] = {}
                for model_data in capability_data.setdefault("models", {}).values():
                    model_data.update(self._default_model_ledger())
        ledger["period_key"] = current_period

    def _ensure_runtime_models(
        self,
        *,
        config: dict[str, Any],
        provider: str,
        capability: str,
        runtime_models: list[str],
    ) -> bool:
        providers = config.setdefault("providers", {})
        provider_cfg = providers.setdefault(
            provider,
            {
                "display_name": provider,
                "warning_ratio": self.DEFAULT_WARNING_RATIO,
                "switch_ratio": self.DEFAULT_SWITCH_RATIO,
                "quota_error_cooldown_minutes": self.DEFAULT_QUOTA_ERROR_COOLDOWN_MINUTES,
                "capabilities": {},
            },
        )
        capabilities = provider_cfg.setdefault("capabilities", {})
        capability_cfg = capabilities.setdefault(capability, {"usage_unit": "request_count", "models": []})
        models = capability_cfg.setdefault("models", [])
        existing = {item["name"] for item in models if item.get("name")}
        next_priority = max([int(item.get("priority", 0)) for item in models] or [0]) + 1
        changed = False
        for model in runtime_models:
            if model in existing:
                continue
            usage_unit = capability_cfg.get("usage_unit", "request_count")
            default_limit = 200000 if usage_unit == "estimated_tokens" else 100
            models.append(
                {
                    "name": model,
                    "label": model,
                    "priority": next_priority,
                    "budget_limit": default_limit,
                    "enabled": True,
                }
            )
            existing.add(model)
            next_priority += 1
            changed = True
        models.sort(key=lambda item: (int(item.get("priority", 99)), str(item.get("name", ""))))
        return changed

    def _ensure_capability_ledger(
        self,
        *,
        ledger: dict[str, Any],
        provider: str,
        capability: str,
        model_names: list[str],
    ) -> dict[str, Any]:
        provider_ledger = ledger.setdefault("providers", {}).setdefault(provider, {"capabilities": {}})
        capability_ledger = provider_ledger.setdefault(
            "capabilities",
            {},
        ).setdefault(
            capability,
            {"active_model": "", "last_routing": {}, "events": [], "models": {}},
        )
        models = capability_ledger.setdefault("models", {})
        for name in model_names:
            models.setdefault(name, self._default_model_ledger())
        capability_ledger.setdefault("events", [])
        capability_ledger.setdefault("last_routing", {})
        return capability_ledger

    def _ordered_models(
        self,
        *,
        capability_cfg: dict[str, Any],
        runtime_models: list[str],
        primary: str,
    ) -> list[str]:
        configured = sorted(
            capability_cfg.get("models", []),
            key=lambda item: (0 if item.get("name") == primary else 1, int(item.get("priority", 99))),
        )
        ordered = [item["name"] for item in configured if item.get("enabled", True)]
        return self._unique([primary, *runtime_models, *ordered])

    def _find_model_config(self, capability_cfg: dict[str, Any], model: str) -> dict[str, Any] | None:
        for item in capability_cfg.get("models", []):
            if item.get("name") == model:
                return item
        return None

    def _append_event(self, capability_ledger: dict[str, Any], event: dict[str, Any]) -> None:
        events = capability_ledger.setdefault("events", [])
        events.append(event)
        if len(events) > self.MAX_EVENTS:
            del events[:-self.MAX_EVENTS]

    def _resolve_usage_value(
        self,
        *,
        capability: str,
        input_tokens: int,
        output_tokens: int,
        cost_value: float | None,
    ) -> float:
        if cost_value is not None:
            return round(max(0.0, float(cost_value)), 2)
        if capability == "text":
            return float(max(0, int(input_tokens) + int(output_tokens)))
        return 1.0

    def _current_usage_value(self, model_ledger: dict[str, Any], capability: str) -> float:
        if capability == "text":
            return float(model_ledger.get("usage_value", 0.0))
        return float(model_ledger.get("usage_value", model_ledger.get("request_count", 0.0)))

    def _status_label(
        self,
        *,
        enabled: bool,
        usage_ratio: float,
        warning_ratio: float,
        switch_ratio: float,
        exhausted_until: str | None,
    ) -> str:
        if not enabled:
            return "disabled"
        exhausted_at = self._parse_datetime(exhausted_until)
        if exhausted_at and exhausted_at > _utc_now():
            return "exhausted"
        if usage_ratio >= switch_ratio:
            return "switch"
        if usage_ratio >= warning_ratio:
            return "warning"
        return "healthy"

    def _parse_datetime(self, value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    def _as_float(self, value: Any) -> float | None:
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _unique(self, values: Iterable[str]) -> list[str]:
        result: list[str] = []
        for value in values:
            text = str(value or "").strip()
            if text and text not in result:
                result.append(text)
        return result
