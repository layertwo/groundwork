from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel


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

    model_config = {"from_attributes": True}
