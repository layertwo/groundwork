from typing import Optional

from sqlalchemy import ARRAY, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class RoleTemplate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "role_templates"

    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    managed_policy_arns: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, server_default="{}"
    )
