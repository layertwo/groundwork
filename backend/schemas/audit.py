from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel


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

    model_config = {"from_attributes": True}


class AuditLogQuery(BaseModel):
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    user_id: Optional[UUID] = None
    action: Optional[str] = None
    page: int = 1
    page_size: int = 50
