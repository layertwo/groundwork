from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import ARRAY, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from backend.models.account import Account


class Role(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "roles"
    __table_args__ = (
        UniqueConstraint("account_id", "role_name", name="uq_roles_account_role"),
        Index("ix_roles_allowed_groups", "allowed_groups", postgresql_using="gin"),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    role_name: Mapped[str] = mapped_column(String(128), nullable=False)
    role_arn: Mapped[str] = mapped_column(String(2048), nullable=False)
    allowed_groups: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, server_default="{}"
    )
    managed_policy_arns: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, server_default="{}"
    )
    inline_policy: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    allowed_users: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, server_default="{}"
    )
    api_session_duration: Mapped[int] = mapped_column(
        Integer, nullable=False, default=900, server_default="900"
    )
    console_session_duration: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3600, server_default="3600"
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    account: Mapped["Account"] = relationship("Account", back_populates="roles")
