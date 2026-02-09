from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class JobCreate(BaseModel):
    job_type: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")


class JobResponse(BaseModel):
    id: UUID
    account_id: Optional[UUID]
    job_type: str
    status: str
    started_by: UUID
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    result: Optional[dict[str, Any]]
    error_message: Optional[str]
    created_at: datetime
    scheduled_after: Optional[datetime]

    model_config = {"from_attributes": True}
