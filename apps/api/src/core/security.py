from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any


ROLE_LEVELS = {
    "viewer": 10,
    "operator": 20,
    "reviewer": 30,
    "admin": 40,
}


@dataclass(slots=True)
class AuthActor:
    user_id: int | None
    email: str | None
    display_name: str | None
    role: str
    token_id: int | None = None


def hash_access_token(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def token_prefix(token: str) -> str:
    compact = token.strip()
    return compact[:8] if len(compact) >= 8 else compact


def role_satisfies(actor_role: str, minimum_role: str) -> bool:
    return ROLE_LEVELS.get(actor_role, 0) >= ROLE_LEVELS.get(minimum_role, 0)


def required_role_for_request(path: str, method: str) -> str | None:
    normalized_method = method.upper()
    if not path.startswith("/api/v1"):
        return None
    if path.startswith("/api/v1/settings") or path.startswith("/api/v1/audit-logs"):
        return "admin"
    if path.startswith("/api/v1/reviews") and normalized_method not in {"GET", "HEAD", "OPTIONS"}:
        return "reviewer"
    if normalized_method in {"GET", "HEAD", "OPTIONS"}:
        return "viewer"
    return "operator"


def derive_audit_action(path: str, method: str) -> tuple[str, str, str | None]:
    segments = [segment for segment in path.split("/") if segment]
    resource_type = segments[2] if len(segments) >= 3 else "unknown"
    resource_id = segments[3] if len(segments) >= 4 else None
    action = f"{method.lower()}:{resource_type}"
    return action, resource_type, resource_id


def sanitize_detail(detail: dict[str, Any]) -> dict[str, Any]:
    scrubbed: dict[str, Any] = {}
    for key, value in detail.items():
        normalized_key = key.lower()
        if any(token in normalized_key for token in {"token", "secret", "password", "key"}):
            scrubbed[key] = "***"
            continue
        scrubbed[key] = value
    return scrubbed
