from fastapi import APIRouter, Depends, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.database import get_db
from backend.dependencies.auth import get_current_admin
from backend.models.audit import AuditLog
from backend.models.user import User
from backend.schemas.audit import AuditLogQuery, AuditLogResponse
from backend.schemas.common import PaginatedResponse

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("", response_model=PaginatedResponse[AuditLogResponse])
async def list_audit_logs(
    response: Response,
    query: AuditLogQuery = Depends(),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    # Entries carry actor identity, IPs and user agents — keep them out of caches.
    response.headers["Cache-Control"] = "no-store"

    filters = []
    if query.resource_type is not None:
        filters.append(AuditLog.resource_type == query.resource_type)
    if query.resource_id is not None:
        filters.append(AuditLog.resource_id == query.resource_id)
    if query.user_id is not None:
        filters.append(AuditLog.user_id == query.user_id)
    if query.action is not None:
        # autoescape keeps % and _ literal and avoids a trailing-backslash LIKE error
        filters.append(AuditLog.action.contains(query.action, autoescape=True))

    total = await db.scalar(select(func.count()).select_from(AuditLog).where(*filters))
    result = await db.execute(
        select(AuditLog)
        .options(selectinload(AuditLog.user))
        .where(*filters)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .offset((query.page - 1) * query.page_size)
        .limit(query.page_size)
    )
    items = [AuditLogResponse.model_validate(entry) for entry in result.scalars().all()]

    return PaginatedResponse[AuditLogResponse](
        items=items,
        total=total or 0,
        page=query.page,
        page_size=query.page_size,
    )
