import asyncio
import re
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from backend.config import settings
from backend.database import get_db
from backend.dependencies.auth import (
    get_current_admin,
    get_current_session,
    get_current_user,
    get_fresh_id_token,
)
from backend.exceptions import ConflictError, ForbiddenError, GroundworkError, NotFoundError
from backend.models.account import Account
from backend.models.job import Job
from backend.models.role import Role
from backend.models.role_template import RoleTemplate
from backend.models.user import Session, User
from backend.schemas.role import (
    AssumeRoleRequest,
    AssumeRoleResponse,
    ConsoleUrlResponse,
    RoleCreate,
    RoleResponse,
    RoleUpdate,
)
from backend.schemas.role_template import (
    RoleTemplateCreate,
    RoleTemplateResponse,
    RoleTemplateUpdate,
)
from backend.services import aws
from backend.services.audit import log_event
from backend.services.jobs import execute_job

router = APIRouter(tags=["roles"])

_SESSION_NAME_RE = re.compile(r"[^\w+=,.@\-]")
_SESSION_NAME_MAX_LEN = 64


def _sanitize_session_name(email: str) -> str:
    """Sanitize an email for use as STS RoleSessionName.

    AWS requires RoleSessionName to match [\\w+=,.@\\-]* and be <= 64 chars.
    """
    return _SESSION_NAME_RE.sub("_", email)[:_SESSION_NAME_MAX_LEN]


# ---------------------------------------------------------------------------
# Role CRUD (account-scoped)
# ---------------------------------------------------------------------------


@router.post(
    "/api/accounts/{account_id}/roles",
    response_model=RoleResponse,
    status_code=201,
)
async def create_role(
    account_id: UUID,
    body: RoleCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    # Verify account exists and is active
    result = await db.execute(select(Account).where(Account.id == account_id))
    account = result.scalar_one_or_none()
    if account is None:
        raise NotFoundError("Account not found")
    if account.status != "active":
        raise GroundworkError("Account is not active", status_code=400)

    # Check for duplicate role name on this account
    existing = await db.execute(
        select(Role).where(Role.account_id == account_id, Role.role_name == body.role_name)
    )
    if existing.scalar_one_or_none() is not None:
        raise ConflictError("A role with this name already exists on this account")

    # At least one of allowed_groups or allowed_users must be specified
    if not body.allowed_groups and not body.allowed_users:
        raise GroundworkError(
            "At least one of allowed_groups or allowed_users is required",
            status_code=400,
        )

    # If template_id provided, use its managed_policy_arns
    managed_policy_arns = body.managed_policy_arns
    if body.template_id is not None:
        tmpl_result = await db.execute(
            select(RoleTemplate).where(RoleTemplate.id == body.template_id)
        )
        template = tmpl_result.scalar_one_or_none()
        if template is None:
            raise NotFoundError("Template not found")
        managed_policy_arns = template.managed_policy_arns

    role = Role(
        account_id=account_id,
        role_name=body.role_name,
        role_arn="",  # placeholder until IAM creation completes
        managed_policy_arns=managed_policy_arns,
        inline_policy=body.inline_policy,
        allowed_groups=body.allowed_groups,
        allowed_users=body.allowed_users,
        api_session_duration=body.api_session_duration,
        console_session_duration=body.console_session_duration,
        description=body.description,
    )
    db.add(role)
    await db.flush()

    job = Job(
        account_id=account_id,
        job_type="create_role",
        status="pending",
        started_by=admin.id,
        result={"role_id": str(role.id)},
    )
    db.add(job)
    await db.flush()

    await log_event(
        db,
        action="role.create",
        user_id=admin.id,
        resource_type="role",
        resource_id=str(role.id),
        detail={"role_name": body.role_name, "account_id": str(account_id)},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    await db.refresh(role)

    # Launch job as background task
    task = asyncio.create_task(execute_job(job.id))
    request.app.state.background_tasks.add(task)
    task.add_done_callback(request.app.state.background_tasks.discard)

    return role


@router.patch(
    "/api/accounts/{account_id}/roles/{role_id}",
    response_model=RoleResponse,
)
async def update_role(
    account_id: UUID,
    role_id: UUID,
    body: RoleUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    result = await db.execute(select(Role).where(Role.id == role_id, Role.account_id == account_id))
    role = result.scalar_one_or_none()
    if role is None:
        raise NotFoundError("Role not found")

    if role.status in ("pending", "deleting"):
        raise GroundworkError("Role cannot be modified in its current state", status_code=400)

    update_data = body.model_dump(exclude_unset=True)
    if not update_data:
        return role

    # Fields that require IAM changes
    iam_fields = {
        "allowed_groups",
        "allowed_users",
        "managed_policy_arns",
        "inline_policy",
        "api_session_duration",
        "console_session_duration",
    }
    iam_changes = {k: v for k, v in update_data.items() if k in iam_fields}

    if role.status == "updating" and iam_changes:
        raise ConflictError("Role IAM update already in progress")

    # Apply all DB field updates
    for field, value in update_data.items():
        setattr(role, field, value)
    db.add(role)

    # If IAM-affecting fields changed, create a job
    if iam_changes:
        # For trust policy updates, include current values for fields not in changes
        if "allowed_groups" in iam_changes or "allowed_users" in iam_changes:
            iam_changes.setdefault("allowed_groups", role.allowed_groups)
            iam_changes.setdefault("allowed_users", role.allowed_users)
        if "api_session_duration" in iam_changes or "console_session_duration" in iam_changes:
            iam_changes.setdefault("api_session_duration", role.api_session_duration)
            iam_changes.setdefault("console_session_duration", role.console_session_duration)

        if role.status == "failed":
            # Re-create from scratch
            role.status = "pending"
            role.error_message = None
            role.role_arn = ""
            job = Job(
                account_id=account_id,
                job_type="create_role",
                status="pending",
                started_by=admin.id,
                result={"role_id": str(role.id)},
            )
        else:
            # Active → updating
            role.status = "updating"
            job = Job(
                account_id=account_id,
                job_type="update_role",
                status="pending",
                started_by=admin.id,
                result={"role_id": str(role.id), "changes": iam_changes},
            )

        db.add(job)
        await db.flush()

        task = asyncio.create_task(execute_job(job.id))
        request.app.state.background_tasks.add(task)
        task.add_done_callback(request.app.state.background_tasks.discard)

    await log_event(
        db,
        action="role.update",
        user_id=admin.id,
        resource_type="role",
        resource_id=str(role.id),
        detail=update_data,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    await db.flush()
    await db.refresh(role)
    return role


@router.delete("/api/accounts/{account_id}/roles/{role_id}", status_code=202)
async def delete_role(
    account_id: UUID,
    role_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    result = await db.execute(select(Role).where(Role.id == role_id, Role.account_id == account_id))
    role = result.scalar_one_or_none()
    if role is None:
        raise NotFoundError("Role not found")

    if role.status == "updating":
        raise ConflictError("Cannot delete role while an IAM update is in progress")
    if role.status == "deleting":
        return Response(status_code=202)

    role.status = "deleting"
    db.add(role)

    # Load account for aws_account_id
    acct_result = await db.execute(select(Account).where(Account.id == account_id))
    account = acct_result.scalar_one()

    job = Job(
        account_id=account_id,
        job_type="delete_role",
        status="pending",
        started_by=admin.id,
        result={
            "role_id": str(role.id),
            "role_name": role.role_name,
            "aws_account_id": account.aws_account_id,
        },
    )
    db.add(job)
    await db.flush()

    await log_event(
        db,
        action="role.delete",
        user_id=admin.id,
        resource_type="role",
        resource_id=str(role.id),
        detail={"role_name": role.role_name, "account_id": str(account_id)},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    task = asyncio.create_task(execute_job(job.id))
    request.app.state.background_tasks.add(task)
    task.add_done_callback(request.app.state.background_tasks.discard)

    return Response(status_code=202)


# ---------------------------------------------------------------------------
# Role listing (cross-account, filtered by user access)
# ---------------------------------------------------------------------------


@router.get("/api/roles", response_model=list[RoleResponse])
async def list_roles(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(Role).options(joinedload(Role.account)))
    roles = result.scalars().unique().all()

    # Filter to roles the user can access:
    # user's groups intersect allowed_groups OR user's sub in allowed_users
    user_groups = set(user.groups or [])
    visible = []
    for role in roles:
        role_groups = set(role.allowed_groups or [])
        role_users = role.allowed_users or []
        if user.is_admin or user_groups & role_groups or user.sub in role_users:
            visible.append(role)

    return visible


async def _load_role_for_assumption(
    role_id: UUID,
    user: User,
    db: AsyncSession,
) -> Role:
    """Load a role by ID and verify the user has access to assume it."""
    result = await db.execute(
        select(Role).options(joinedload(Role.account)).where(Role.id == role_id)
    )
    role = result.scalar_one_or_none()
    if role is None:
        raise NotFoundError("Role not found")

    if role.status != "active":
        raise GroundworkError("Role is not available for assumption", status_code=400)

    # Access check: user's groups intersect allowed_groups OR sub in allowed_users
    user_groups = set(user.groups or [])
    role_groups = set(role.allowed_groups or [])
    if not (user_groups & role_groups) and user.sub not in (role.allowed_users or []):
        raise ForbiddenError("You do not have access to assume this role")

    # Account must be active
    if role.account.status != "active":
        raise GroundworkError("Account is not active", status_code=400)

    return role


@router.post("/api/roles/assume", response_model=AssumeRoleResponse)
async def assume_role(
    body: AssumeRoleRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    session: Session = Depends(get_current_session),
):
    user = session.user
    role = await _load_role_for_assumption(body.role_id, user, db)

    id_token = await get_fresh_id_token(session, db)

    credentials = await aws.assume_role_with_web_identity(
        role_arn=role.role_arn,
        id_token=id_token,
        session_duration=role.api_session_duration,
        session_name=_sanitize_session_name(user.email),
    )

    await log_event(
        db,
        action="role.assume",
        user_id=user.id,
        resource_type="role",
        resource_id=str(role.id),
        detail={
            "role_name": role.role_name,
            "account_id": str(role.account_id),
            "role_arn": role.role_arn,
        },
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return AssumeRoleResponse(
        access_key_id=credentials["access_key_id"],
        secret_access_key=credentials["secret_access_key"],
        session_token=credentials["session_token"],
        expiration=credentials["expiration"],
    )


@router.post("/api/roles/console", response_model=ConsoleUrlResponse)
async def console_access(
    body: AssumeRoleRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    session: Session = Depends(get_current_session),
):
    user = session.user
    role = await _load_role_for_assumption(body.role_id, user, db)

    id_token = await get_fresh_id_token(session, db)

    credentials = await aws.assume_role_with_web_identity(
        role_arn=role.role_arn,
        id_token=id_token,
        session_duration=role.console_session_duration,
        session_name=_sanitize_session_name(user.email),
    )

    console_url = await aws.get_console_url(
        credentials=credentials,
        console_session_duration=role.console_session_duration,
        issuer=settings.app_url,
    )

    await log_event(
        db,
        action="role.console",
        user_id=user.id,
        resource_type="role",
        resource_id=str(role.id),
        detail={
            "role_name": role.role_name,
            "account_id": str(role.account_id),
            "role_arn": role.role_arn,
        },
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return ConsoleUrlResponse(
        console_url=console_url,
        expiration=credentials["expiration"],
    )


# ---------------------------------------------------------------------------
# Role templates
# ---------------------------------------------------------------------------


@router.get("/api/roles/templates", response_model=list[RoleTemplateResponse])
async def list_templates(
    db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)
):
    result = await db.execute(select(RoleTemplate).order_by(RoleTemplate.name))
    return result.scalars().all()


@router.post("/api/roles/templates", response_model=RoleTemplateResponse, status_code=201)
async def create_template(
    body: RoleTemplateCreate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    existing = await db.execute(select(RoleTemplate).where(RoleTemplate.name == body.name))
    if existing.scalar_one_or_none() is not None:
        raise ConflictError(f"Template '{body.name}' already exists")

    template = RoleTemplate(
        name=body.name,
        description=body.description,
        managed_policy_arns=body.managed_policy_arns,
    )
    db.add(template)
    await db.flush()
    await db.refresh(template)
    return template


@router.patch("/api/roles/templates/{template_id}", response_model=RoleTemplateResponse)
async def update_template(
    template_id: UUID,
    body: RoleTemplateUpdate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    result = await db.execute(select(RoleTemplate).where(RoleTemplate.id == template_id))
    template = result.scalar_one_or_none()
    if template is None:
        raise NotFoundError("Template not found")

    _UPDATABLE = {"name", "description", "managed_policy_arns"}
    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field in _UPDATABLE:
            setattr(template, field, value)

    db.add(template)
    await db.flush()
    await db.refresh(template)
    return template


@router.delete("/api/roles/templates/{template_id}", status_code=204)
async def delete_template(
    template_id: UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    result = await db.execute(select(RoleTemplate).where(RoleTemplate.id == template_id))
    template = result.scalar_one_or_none()
    if template is None:
        raise NotFoundError("Template not found")

    await db.delete(template)
