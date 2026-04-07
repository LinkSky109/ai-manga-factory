from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.db.models.base import Base, TimestampMixin


class UserAccountModel(TimestampMixin, Base):
    __tablename__ = "user_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="viewer")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")


class AccessTokenModel(TimestampMixin, Base):
    __tablename__ = "access_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False)
    token_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False, default="bootstrap-token")
    is_revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditLogModel(TimestampMixin, Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id", ondelete="SET NULL"), nullable=True)
    actor_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    actor_role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(120), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    request_method: Mapped[str] = mapped_column(String(16), nullable=False)
    request_path: Mapped[str] = mapped_column(String(255), nullable=False)
    response_status: Mapped[int] = mapped_column(Integer, nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    detail: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
