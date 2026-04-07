from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.config import get_settings
from src.core.security import AuthActor, hash_access_token, token_prefix
from src.infrastructure.db.models import AccessTokenModel, UserAccountModel


BOOTSTRAP_SPECS = (
    ("admin", "AUTH_BOOTSTRAP_ADMIN_TOKEN", "admin@ai-manga.local", "Factory Admin"),
    ("operator", "AUTH_BOOTSTRAP_OPERATOR_TOKEN", "operator@ai-manga.local", "Factory Operator"),
    ("reviewer", "AUTH_BOOTSTRAP_REVIEWER_TOKEN", "reviewer@ai-manga.local", "Factory Reviewer"),
    ("viewer", "AUTH_BOOTSTRAP_VIEWER_TOKEN", "viewer@ai-manga.local", "Factory Viewer"),
)


class SecurityRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def seed_bootstrap_users(self) -> None:
        settings = get_settings()
        for role, env_key, default_email, default_name in BOOTSTRAP_SPECS:
            token = settings.security_tokens.get(role)
            if not token:
                continue
            email = settings.security_emails.get(role) or default_email
            display_name = settings.security_names.get(role) or default_name
            user = self._find_user_by_email(email)
            if user is None:
                user = UserAccountModel(email=email, display_name=display_name, role=role, status="active")
                self.session.add(user)
                self.session.flush()
            else:
                user.display_name = display_name
                user.role = role
                user.status = "active"
                self.session.flush()
            self._upsert_access_token(user_id=user.id, raw_token=token, description=f"bootstrap-{role}")
        self.session.flush()

    def authenticate_token(self, raw_token: str) -> AuthActor | None:
        hashed = hash_access_token(raw_token)
        token = self.session.scalars(
            select(AccessTokenModel).where(
                AccessTokenModel.token_hash == hashed,
                AccessTokenModel.is_revoked.is_(False),
            )
        ).first()
        if token is None:
            return None
        if token.expires_at is not None and token.expires_at <= self._utcnow():
            return None
        user = self.session.get(UserAccountModel, token.user_id)
        if user is None or user.status != "active":
            return None
        token.last_used_at = self._utcnow()
        self.session.flush()
        return AuthActor(
            user_id=user.id,
            email=user.email,
            display_name=user.display_name,
            role=user.role,
            token_id=token.id,
        )

    def list_bootstrap_accounts(self) -> list[dict]:
        users = list(self.session.scalars(select(UserAccountModel).order_by(UserAccountModel.role, UserAccountModel.email)))
        return [
            {
                "email": user.email,
                "display_name": user.display_name,
                "role": user.role,
                "status": user.status,
            }
            for user in users
        ]

    def _find_user_by_email(self, email: str) -> UserAccountModel | None:
        return self.session.scalars(select(UserAccountModel).where(UserAccountModel.email == email)).first()

    def _upsert_access_token(self, *, user_id: int, raw_token: str, description: str) -> AccessTokenModel:
        hashed = hash_access_token(raw_token)
        token = self.session.scalars(select(AccessTokenModel).where(AccessTokenModel.token_hash == hashed)).first()
        if token is None:
            token = AccessTokenModel(
                user_id=user_id,
                token_prefix=token_prefix(raw_token),
                token_hash=hashed,
                description=description,
                is_revoked=False,
            )
            self.session.add(token)
            self.session.flush()
            return token

        token.user_id = user_id
        token.token_prefix = token_prefix(raw_token)
        token.description = description
        token.is_revoked = False
        self.session.flush()
        return token

    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(timezone.utc)
