from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class RoleTemplateCreate(BaseModel):
    name: str
    description: Optional[str] = None
    managed_policy_arns: list[str] = []


class RoleTemplateUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    managed_policy_arns: Optional[list[str]] = None


class RoleTemplateResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str]
    managed_policy_arns: list[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
