from datetime import datetime
from typing import Annotated, Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class AuditUserResponse(BaseModel):
    id: UUID
    display_name: str

    model_config = {"from_attributes": True}


class AuditLogResponse(BaseModel):
    id: int
    user_id: Optional[UUID]
    action: str
    resource_type: Optional[str]
    resource_id: Optional[str]
    detail: Optional[dict[str, Any]]
    ip_address: Optional[str]
    user_agent: Optional[str]
    created_at: datetime
    user: Optional[AuditUserResponse] = None

    model_config = {"from_attributes": True}


class AuditLogQuery(BaseModel):
    resource_type: Annotated[Optional[str], Field(max_length=64)] = None
    resource_id: Annotated[Optional[str], Field(max_length=255)] = None
    user_id: Optional[UUID] = None
    action: Annotated[Optional[str], Field(max_length=128)] = None
    page: Annotated[int, Field(ge=1, le=1_000_000)] = 1
    page_size: Annotated[int, Field(ge=1, le=200)] = 50
