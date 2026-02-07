from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel


class RoleResponse(BaseModel):
    id: UUID
    account_id: UUID
    role_name: str
    role_arn: str
    allowed_groups: list[str]
    managed_policy_arns: list[str]
    inline_policy: Optional[dict[str, Any]]
    allowed_users: list[str]
    api_session_duration: int
    console_session_duration: int
    description: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AssumeRoleRequest(BaseModel):
    role_id: UUID


class AssumeRoleResponse(BaseModel):
    access_key_id: str
    secret_access_key: str
    session_token: str
    expiration: datetime
