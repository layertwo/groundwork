from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from backend.models.job import Job
    from backend.models.role import Role
    from backend.models.user import User


class Account(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "accounts"

    aws_account_id: Mapped[Optional[str]] = mapped_column(String(12), unique=True, nullable=True)
    account_name: Mapped[str] = mapped_column(String(128), nullable=False)
    account_email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    organizational_unit: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending", server_default="pending"
    )
    sso_user_email: Mapped[str] = mapped_column(String(320), nullable=False)
    provisioned_product_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    oidc_provider_arn: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    creator: Mapped["User"] = relationship("User")
    roles: Mapped[list["Role"]] = relationship(
        "Role", back_populates="account", cascade="all, delete-orphan"
    )
    jobs: Mapped[list["Job"]] = relationship("Job", back_populates="account")
