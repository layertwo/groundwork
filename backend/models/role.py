from typing import Optional
import uuid

from sqlalchemy import ARRAY, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


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
    max_session_duration: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3600, server_default="3600"
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    account: Mapped["Account"] = relationship("Account", back_populates="roles")
