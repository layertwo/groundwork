"""Account management endpoints."""

import asyncio
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.dependencies.auth import get_current_admin, get_current_user
from backend.exceptions import ConflictError, GroundworkError, NotFoundError
from backend.models.account import Account
from backend.models.job import Job
from backend.models.user import User
from backend.schemas.account import AccountCreate, AccountResponse, AccountUpdate
from backend.services import account_metadata, aws
from backend.services.audit import log_event
from backend.services.jobs import execute_job

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


@router.get("", response_model=list[AccountResponse])
async def list_accounts(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(Account).order_by(Account.created_at.desc()))
    accounts = list(result.scalars().all())

    # Fetch metadata for all accounts with AWS account IDs
    aws_ids = [a.aws_account_id for a in accounts if a.aws_account_id]
    try:
        metadata = await account_metadata.get_all_account_metadata(aws_ids) if aws_ids else {}
    except Exception:
        logger.warning("Failed to fetch account metadata for list", exc_info=True)
        metadata = {}

    responses = []
    for acct in accounts:
        resp = AccountResponse.model_validate(acct)
        meta = metadata.get(acct.aws_account_id) if acct.aws_account_id else None
        if meta:
            resp.alias = meta.get("alias")
            resp.color = meta.get("color")
        responses.append(resp)

    return responses


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
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(Account).where(Account.id == account_id))
    account = result.scalar_one_or_none()
    if account is None:
        raise NotFoundError("Account not found")

    resp = AccountResponse.model_validate(account)

    if account.aws_account_id:
        try:
            meta = await account_metadata.get_account_metadata(account.aws_account_id)
            resp.alias = meta.get("alias")
            resp.color = meta.get("color")
        except Exception:
            logger.warning(
                "Failed to fetch metadata for account %s",
                account.aws_account_id,
                exc_info=True,
            )

    return resp


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

    update_data = body.model_dump(exclude_unset=True)

    # Handle alias and color updates (require active account with AWS ID)
    alias_update = update_data.pop("alias", None)
    color_update = update_data.pop("color", None)

    if alias_update is not None or color_update is not None:
        if account.status != "active" or not account.aws_account_id:
            raise GroundworkError(
                "Account must be active to modify alias or color", status_code=400
            )

    # Apply standard DB field updates
    _UPDATABLE = {"account_name", "organizational_unit", "sso_user_email"}
    for field, value in update_data.items():
        if field in _UPDATABLE:
            setattr(account, field, value)

    # Handle alias update via AWS IAM
    if alias_update is not None:
        if alias_update == "":
            # Delete alias — need to know current alias first
            current_meta = await account_metadata.get_account_metadata(account.aws_account_id)
            current_alias = current_meta.get("alias")
            if current_alias:
                await aws.delete_account_alias(account.aws_account_id, current_alias)
            account_metadata.update_cached_alias(account.aws_account_id, None)
        else:
            await aws.set_account_alias(account.aws_account_id, alias_update)
            account_metadata.update_cached_alias(account.aws_account_id, alias_update)

    # Handle color update via AWS UXC
    if color_update is not None:
        if color_update in ("", "none"):
            await aws.delete_account_color(account.aws_account_id)
            account_metadata.update_cached_color(account.aws_account_id, None)
        else:
            await aws.set_account_color(account.aws_account_id, color_update)
            account_metadata.update_cached_color(account.aws_account_id, color_update)

    db.add(account)

    await log_event(
        db,
        action="account.update",
        user_id=admin.id,
        resource_type="account",
        resource_id=str(account.id),
        detail=body.model_dump(exclude_unset=True),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    await db.flush()
    await db.refresh(account)

    # Build response with metadata
    resp = AccountResponse.model_validate(account)
    if account.aws_account_id:
        try:
            meta = await account_metadata.get_account_metadata(account.aws_account_id)
            resp.alias = meta.get("alias")
            resp.color = meta.get("color")
        except Exception:
            logger.warning(
                "Failed to fetch metadata for account %s",
                account.aws_account_id,
                exc_info=True,
            )

    return resp
