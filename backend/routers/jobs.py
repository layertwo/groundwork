from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.dependencies.auth import get_current_user
from backend.exceptions import NotFoundError
from backend.models.job import Job
from backend.models.user import User
from backend.schemas.job import JobResponse

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("", response_model=list[JobResponse])
async def list_jobs(
    account_id: Optional[UUID] = Query(None),
    status: Optional[Literal["pending", "in_progress", "completed", "failed"]] = Query(None),
    job_type: Optional[Literal["provision_account"]] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = select(Job).order_by(Job.created_at.desc())

    # Non-admins only see their own jobs
    if not user.is_admin:
        query = query.where(Job.started_by == user.id)

    if account_id is not None:
        query = query.where(Job.account_id == account_id)
    if status is not None:
        query = query.where(Job.status == status)
    if job_type is not None:
        query = query.where(Job.job_type == job_type)

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise NotFoundError("Job not found")

    # Non-admins can only see their own jobs
    if not user.is_admin and job.started_by != user.id:
        raise NotFoundError("Job not found")

    return job
