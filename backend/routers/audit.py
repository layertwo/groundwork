from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.database import get_db
from backend.dependencies.auth import get_current_admin
from backend.models.audit import AuditLog
from backend.models.user import User
from backend.schemas.generated.models import ListAuditEntriesResponseContent

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("", response_model=ListAuditEntriesResponseContent)
async def list_audit_logs(
    response: Response,
    resource_type: Optional[str] = Query(None, alias="resourceType", max_length=64),
    resource_id: Optional[str] = Query(None, alias="resourceId", max_length=255),
    user_id: Optional[UUID] = Query(None, alias="userId"),
    action: Optional[str] = Query(None, max_length=128),
    page: int = Query(1, ge=1, le=1_000_000),
    page_size: int = Query(50, ge=1, le=200, alias="pageSize"),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    # Entries carry actor identity, IPs and user agents — keep them out of caches.
    response.headers["Cache-Control"] = "no-store"

    filters = []
    if resource_type is not None:
        filters.append(AuditLog.resource_type == resource_type)
    if resource_id is not None:
        filters.append(AuditLog.resource_id == resource_id)
    if user_id is not None:
        filters.append(AuditLog.user_id == user_id)
    if action is not None:
        # autoescape keeps % and _ literal and avoids a trailing-backslash LIKE error
        filters.append(AuditLog.action.contains(action, autoescape=True))

    total = await db.scalar(select(func.count()).select_from(AuditLog).where(*filters))
    result = await db.execute(
        select(AuditLog)
        .options(selectinload(AuditLog.user))
        .where(*filters)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    return {
        "items": list(result.scalars().all()),
        "total": total or 0,
        "page": page,
        "page_size": page_size,
    }
