import asyncio
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.dependencies.auth import get_current_admin, get_current_user
from backend.exceptions import ConflictError, NotFoundError
from backend.models.account import Account
from backend.models.job import Job
from backend.models.user import User
from backend.schemas.account import AccountCreate, AccountResponse, AccountUpdate
from backend.services.audit import log_event
from backend.services.jobs import execute_job

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


@router.get("", response_model=list[AccountResponse])
async def list_accounts(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    result = await db.execute(select(Account).order_by(Account.created_at.desc()))
    return result.scalars().all()


@router.post("", response_model=AccountResponse, status_code=201)
async def create_account(
    body: AccountCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    # Check for duplicate email
    existing = await db.execute(select(Account).where(Account.account_email == body.account_email))
    if existing.scalar_one_or_none() is not None:
        raise ConflictError("An account with this email already exists")

    account = Account(
        account_name=body.account_name,
        account_email=body.account_email,
        organizational_unit=body.organizational_unit,
        sso_user_email=body.sso_user_email,
        status="pending",
        created_by=admin.id,
    )
    db.add(account)

    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise ConflictError("An account with this email already exists")

    job = Job(
        account_id=account.id,
        job_type="provision_account",
        status="pending",
        started_by=admin.id,
    )
    db.add(job)
    await db.flush()

    await log_event(
        db,
        action="account.create",
        user_id=admin.id,
        resource_type="account",
        resource_id=str(account.id),
        detail={"account_name": body.account_name, "account_email": body.account_email},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    await db.refresh(account)

    # Launch provisioning job as background task, retain reference
    task = asyncio.create_task(execute_job(job.id))
    request.app.state.background_tasks.add(task)
    task.add_done_callback(request.app.state.background_tasks.discard)

    return account


@router.get("/{account_id}", response_model=AccountResponse)
async def get_account(
    account_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    result = await db.execute(select(Account).where(Account.id == account_id))
    account = result.scalar_one_or_none()
    if account is None:
        raise NotFoundError("Account not found")
    return account


@router.patch("/{account_id}", response_model=AccountResponse)
async def update_account(
    account_id: UUID,
    body: AccountUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    result = await db.execute(select(Account).where(Account.id == account_id))
    account = result.scalar_one_or_none()
    if account is None:
        raise NotFoundError("Account not found")

    _UPDATABLE = {"account_name", "organizational_unit", "sso_user_email"}
    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field in _UPDATABLE:
            setattr(account, field, value)

    db.add(account)

    await log_event(
        db,
        action="account.update",
        user_id=admin.id,
        resource_type="account",
        resource_id=str(account.id),
        detail=update_data,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    await db.flush()
    await db.refresh(account)
    return account
