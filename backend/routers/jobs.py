import asyncio
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.dependencies.auth import get_current_admin, get_current_user
from backend.exceptions import ConflictError, GroundworkError, NotFoundError
from backend.models.job import Job
from backend.models.user import User
from backend.schemas.job import JobCreate, JobResponse
from backend.services.jobs import execute_job

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

ALLOWED_JOB_TYPES = {"sync_accounts"}


@router.post("", response_model=JobResponse, status_code=201)
async def create_job(
    body: JobCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    if body.job_type not in ALLOWED_JOB_TYPES:
        raise GroundworkError("Unsupported job type", status_code=400)

    # Prevent duplicate sync jobs (FOR UPDATE prevents TOCTOU race)
    existing = await db.execute(
        select(Job)
        .where(
            Job.job_type == body.job_type,
            Job.status.in_(["pending", "in_progress"]),
        )
        .with_for_update()
    )
    if existing.scalar_one_or_none() is not None:
        raise ConflictError(f"A {body.job_type} job is already running")

    job = Job(
        job_type=body.job_type,
        status="pending",
        started_by=admin.id,
    )
    db.add(job)
    await db.flush()
    await db.refresh(job)

    task = asyncio.create_task(execute_job(job.id))
    request.app.state.background_tasks.add(task)
    task.add_done_callback(request.app.state.background_tasks.discard)

    return job


@router.get("", response_model=list[JobResponse])
async def list_jobs(
    account_id: Optional[UUID] = Query(None),
    status: Optional[Literal["pending", "in_progress", "completed", "failed"]] = Query(None),
    job_type: Optional[
        Literal[
            "provision_account",
            "sync_accounts",
            "bootstrap_account",
            "create_role",
            "update_role",
            "delete_role",
        ]
    ] = Query(None),
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
