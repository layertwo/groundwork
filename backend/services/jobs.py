"""Job executor — background task runner for multi-step provisioning jobs."""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import async_session_factory
from backend.models.account import Account
from backend.models.job import Job
from backend.models.role import Role
from backend.services import aws
from backend.services.audit import log_event
from backend.services.system_user import get_or_create_system_user

logger = logging.getLogger(__name__)


async def recover_stale_jobs(background_tasks: set) -> int:
    """Re-enqueue pending/in_progress jobs that were orphaned by a server restart.

    - Resets ``in_progress`` jobs back to ``pending`` (clears ``started_at``).
    - Spawns an ``asyncio.Task`` for each recovered job via ``execute_job()``.
    - Returns the number of recovered jobs for logging.
    """
    async with async_session_factory() as db:
        now = datetime.now(timezone.utc)
        result = await db.execute(
            select(Job).where(
                Job.status.in_(["pending", "in_progress"]),
                or_(Job.scheduled_after.is_(None), Job.scheduled_after <= now),
            )
        )
        stale_jobs = result.scalars().all()

        for job in stale_jobs:
            if job.status == "in_progress":
                job.status = "pending"
                job.started_at = None
                db.add(job)

        await db.commit()

    # Spawn tasks outside the DB session so rows are visible to new sessions
    for job in stale_jobs:
        task = asyncio.create_task(execute_job(job.id))
        background_tasks.add(task)
        task.add_done_callback(background_tasks.discard)

    return len(stale_jobs)


POLL_INTERVAL_SECONDS = 30
POLL_TIMEOUT_SECONDS = 30 * 60  # 30 minutes


MAX_SCHEDULED_DELAY_SECONDS = 30 * 60  # 30 minutes


async def execute_job(job_id: uuid.UUID) -> None:
    """Load a job and dispatch to the appropriate handler.

    Runs in its own DB session (not the request session).
    If the job has a ``scheduled_after`` value in the future, sleeps outside
    any DB session to avoid holding a connection pool slot.
    """
    # Check for scheduled delay in a short-lived session
    async with async_session_factory() as db:
        result = await db.execute(select(Job.scheduled_after).where(Job.id == job_id))
        row = result.one_or_none()
        if row is None:
            logger.error("Job %s not found", job_id)
            return
        scheduled_after = row[0]

    if scheduled_after is not None:
        delay = (scheduled_after - datetime.now(timezone.utc)).total_seconds()
        delay = min(delay, MAX_SCHEDULED_DELAY_SECONDS)
        if delay > 0:
            logger.info(
                "Job %s scheduled for %s, sleeping %.0fs",
                job_id,
                scheduled_after,
                delay,
            )
            await asyncio.sleep(delay)

    # Execute the job in a fresh session
    async with async_session_factory() as db:
        try:
            result = await db.execute(select(Job).where(Job.id == job_id))
            job = result.scalar_one_or_none()
            if job is None:
                logger.error("Job %s not found", job_id)
                return

            handlers = {
                "provision_account": run_provision_account,
                "bootstrap_account": run_bootstrap_account,
                "sync_accounts": run_sync_accounts,
                "create_role": run_create_role,
                "update_role": run_update_role,
                "delete_role": run_delete_role,
            }
            handler = handlers.get(job.job_type)
            if handler is None:
                logger.error("Unknown job type: %s", job.job_type)
                job.status = "failed"
                job.error_message = f"Unknown job type: {job.job_type}"
                db.add(job)
                await db.commit()
                return

            await handler(job, db)
        except Exception:
            logger.exception("Unhandled error in job %s", job_id)
            try:
                job.status = "failed"
                job.error_message = "Internal error"
                job.completed_at = datetime.now(timezone.utc)
                db.add(job)
                await db.commit()
            except Exception:
                logger.exception("Failed to mark job %s as failed", job_id)


async def run_provision_account(job: Job, db: AsyncSession) -> None:
    """Run the full account provisioning pipeline.

    Steps:
    1. Create account via Organizations
    2. Poll until creation completes
    3. Move account to target OU
    4. Bootstrap account (admin role via StackSet)
    5. Mark account active
    """
    now = datetime.now(timezone.utc)
    job.status = "in_progress"
    job.started_at = now
    db.add(job)
    await db.commit()

    # Load the associated account
    result = await db.execute(select(Account).where(Account.id == job.account_id))
    account = result.scalar_one_or_none()
    if account is None:
        job.status = "failed"
        job.error_message = "Associated account not found"
        job.completed_at = datetime.now(timezone.utc)
        db.add(job)
        await db.commit()
        return

    try:
        # Step 1: Create account
        account.status = "provisioning"
        db.add(account)
        await db.commit()

        request_id = await aws.create_account(
            account_name=account.account_name,
            account_email=account.account_email,
        )
        job.result = {"create_account_request_id": request_id}
        db.add(job)
        await db.commit()

        # Step 2: Poll for completion
        elapsed = 0
        while elapsed < POLL_TIMEOUT_SECONDS:
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
            elapsed += POLL_INTERVAL_SECONDS

            status = await aws.poll_account_creation(request_id)

            if status["status"] == "SUCCEEDED":
                account.aws_account_id = status["aws_account_id"]
                db.add(account)
                await db.commit()
                break
            elif status["status"] == "FAILED":
                raise RuntimeError(f"Account creation failed: {status.get('error', 'unknown')}")
        else:
            raise RuntimeError("Account creation timed out")

        # Step 3: Move to target OU
        await aws.move_account_to_ou(account.aws_account_id, account.organizational_unit)

        # Step 4: Bootstrap
        bootstrap_result = await aws.bootstrap_account(
            account.aws_account_id, ou_id=account.organizational_unit
        )

        # Step 5: Mark complete
        account.status = "active"
        db.add(account)

        job.status = "completed"
        job.completed_at = datetime.now(timezone.utc)
        job.result = {
            **(job.result or {}),
            "aws_account_id": account.aws_account_id,
            **bootstrap_result,
        }
        db.add(job)

        await log_event(
            db,
            action="account.provision.completed",
            user_id=job.started_by,
            resource_type="account",
            resource_id=str(account.id),
            detail={"aws_account_id": account.aws_account_id},
        )
        await db.commit()

    except Exception as exc:
        logger.exception("Provisioning failed for account %s", account.id)
        safe_msg = _sanitize_error(exc)
        account.status = "failed"
        account.error_message = safe_msg
        db.add(account)

        job.status = "failed"
        job.error_message = safe_msg
        job.completed_at = datetime.now(timezone.utc)
        db.add(job)

        await log_event(
            db,
            action="account.provision.failed",
            user_id=job.started_by,
            resource_type="account",
            resource_id=str(account.id),
            detail={"error": safe_msg},
        )
        await db.commit()


async def run_bootstrap_account(job: Job, db: AsyncSession) -> None:
    """Bootstrap a single account via StackSet deployment.

    Deploys the admin role, then marks the account active.
    """
    now = datetime.now(timezone.utc)
    job.status = "in_progress"
    job.started_at = now
    db.add(job)
    await db.commit()

    result = await db.execute(select(Account).where(Account.id == job.account_id))
    account = result.scalar_one_or_none()
    if account is None:
        job.status = "failed"
        job.error_message = "Associated account not found"
        job.completed_at = datetime.now(timezone.utc)
        db.add(job)
        await db.commit()
        return

    try:
        bootstrap_result = await aws.bootstrap_account(
            account.aws_account_id, ou_id=account.organizational_unit
        )
        account.status = "active"
        db.add(account)

        job.status = "completed"
        job.completed_at = datetime.now(timezone.utc)
        job.result = bootstrap_result
        db.add(job)

        await log_event(
            db,
            action="account.bootstrap.completed",
            user_id=job.started_by,
            resource_type="account",
            resource_id=str(account.id),
            detail={"aws_account_id": account.aws_account_id},
        )
        await db.commit()

    except Exception as exc:
        logger.exception("Bootstrap failed for account %s", account.id)
        safe_msg = _sanitize_error(exc)
        account.status = "failed"
        account.error_message = safe_msg
        db.add(account)

        job.status = "failed"
        job.error_message = safe_msg
        job.completed_at = datetime.now(timezone.utc)
        db.add(job)

        await log_event(
            db,
            action="account.bootstrap.failed",
            user_id=job.started_by,
            resource_type="account",
            resource_id=str(account.id),
            detail={"error": safe_msg},
        )
        await db.commit()


async def run_sync_accounts(job: Job, db: AsyncSession) -> None:
    """Discover org accounts, import/reconcile, and bootstrap active ones.

    1. Ensure bootstrap StackSet exists.
    2. List all org accounts (paginated).
    3. For each account: import new, reconcile existing, skip/mark suspended.
    4. Spawn bootstrap_account jobs for accounts needing deployment.
    """
    now = datetime.now(timezone.utc)
    job.status = "in_progress"
    job.started_at = now
    db.add(job)
    await db.commit()

    try:
        # Step 1: Ensure StackSet exists
        await aws.ensure_bootstrap_stackset()

        # Step 2: Discover accounts
        org_accounts = await aws.list_org_accounts()

        # Build lookup of existing accounts by aws_account_id
        result = await db.execute(select(Account).where(Account.aws_account_id.isnot(None)))
        existing_map: dict[str, Account] = {a.aws_account_id: a for a in result.scalars().all()}

        counts = {
            "accounts_found": len(org_accounts),
            "imported": 0,
            "updated": 0,
            "bootstrap_triggered": 0,
            "skipped_suspended": 0,
        }
        bootstrap_job_ids: list[uuid.UUID] = []

        for org_acct in org_accounts:
            aws_id = org_acct["aws_account_id"]
            aws_status = org_acct["status"]
            ou_id = await aws.get_account_ou(aws_id)

            if aws_id not in existing_map:
                # New account -- import
                account = Account(
                    aws_account_id=aws_id,
                    account_name=org_acct["name"],
                    account_email=org_acct["email"],
                    organizational_unit=ou_id,
                    sso_user_email=org_acct["email"],
                    status="active",
                    aws_status=aws_status,
                    created_by=job.started_by,
                )
                db.add(account)
                await db.flush()
                counts["imported"] += 1

                if aws_status != "ACTIVE":
                    counts["skipped_suspended"] += 1
                else:
                    bootstrap_job = Job(
                        account_id=account.id,
                        job_type="bootstrap_account",
                        status="pending",
                        started_by=job.started_by,
                    )
                    db.add(bootstrap_job)
                    await db.flush()
                    bootstrap_job_ids.append(bootstrap_job.id)
                    counts["bootstrap_triggered"] += 1
            else:
                # Existing account -- reconcile
                account = existing_map[aws_id]
                changed = False

                if account.account_name != org_acct["name"]:
                    account.account_name = org_acct["name"]
                    changed = True
                if account.account_email != org_acct["email"]:
                    account.account_email = org_acct["email"]
                    changed = True
                if account.organizational_unit != ou_id:
                    account.organizational_unit = ou_id
                    changed = True
                if account.aws_status != aws_status:
                    account.aws_status = aws_status
                    changed = True

                if changed:
                    db.add(account)
                    counts["updated"] += 1

                # Trigger bootstrap if needed
                needs_bootstrap = aws_status == "ACTIVE" and account.status == "failed"
                if needs_bootstrap:
                    bootstrap_job = Job(
                        account_id=account.id,
                        job_type="bootstrap_account",
                        status="pending",
                        started_by=job.started_by,
                    )
                    db.add(bootstrap_job)
                    await db.flush()
                    bootstrap_job_ids.append(bootstrap_job.id)
                    counts["bootstrap_triggered"] += 1

                if aws_status != "ACTIVE":
                    counts["skipped_suspended"] += 1

        job.status = "completed"
        job.completed_at = datetime.now(timezone.utc)
        job.result = counts
        db.add(job)

        await log_event(
            db,
            action="accounts.sync.completed",
            user_id=job.started_by,
            resource_type="account",
            detail=counts,
        )
        await db.commit()

        # Fire bootstrap tasks after commit so child jobs can find their rows
        for bj_id in bootstrap_job_ids:
            asyncio.create_task(execute_job(bj_id))

    except Exception as exc:
        logger.exception("Sync accounts failed")
        safe_msg = _sanitize_error(exc)
        job.status = "failed"
        job.error_message = safe_msg
        job.completed_at = datetime.now(timezone.utc)
        db.add(job)

        await log_event(
            db,
            action="accounts.sync.failed",
            user_id=job.started_by,
            resource_type="account",
            detail={"error": safe_msg},
        )
        await db.commit()


async def run_create_role(job: Job, db: AsyncSession) -> None:
    """Create an IAM role in the target account."""
    now = datetime.now(timezone.utc)
    job.status = "in_progress"
    job.started_at = now
    db.add(job)
    await db.commit()

    role_id = job.result["role_id"]
    result = await db.execute(select(Role).where(Role.id == role_id))
    role = result.scalar_one_or_none()
    if role is None:
        job.status = "failed"
        job.error_message = "Associated role not found"
        job.completed_at = datetime.now(timezone.utc)
        db.add(job)
        await db.commit()
        return

    result = await db.execute(select(Account).where(Account.id == role.account_id))
    account = result.scalar_one()

    try:
        role_arn = await aws.create_iam_role(
            aws_account_id=account.aws_account_id,
            role_name=role.role_name,
            role_id=str(role.id),
            account_id=str(role.account_id),
            managed_policy_arns=role.managed_policy_arns,
            inline_policy=role.inline_policy,
            max_duration=max(role.api_session_duration, role.console_session_duration),
        )
        role.role_arn = role_arn
        role.status = "active"
        role.error_message = None
        db.add(role)

        job.status = "completed"
        job.completed_at = datetime.now(timezone.utc)
        job.result = {**(job.result or {}), "role_arn": role_arn}
        db.add(job)

        await log_event(
            db,
            action="role.create.completed",
            user_id=job.started_by,
            resource_type="role",
            resource_id=str(role.id),
            detail={"role_arn": role_arn, "account_id": str(account.id)},
        )
        await db.commit()

    except Exception as exc:
        logger.exception("Role creation failed for role %s", role_id)
        safe_msg = _sanitize_error(exc)

        role.status = "failed"
        role.error_message = safe_msg
        db.add(role)

        job.status = "failed"
        job.error_message = safe_msg
        job.completed_at = datetime.now(timezone.utc)
        db.add(job)

        await log_event(
            db,
            action="role.create.failed",
            user_id=job.started_by,
            resource_type="role",
            resource_id=str(role.id),
            detail={"error": safe_msg},
        )
        await db.commit()


async def run_update_role(job: Job, db: AsyncSession) -> None:
    """Update an IAM role in the target account."""
    now = datetime.now(timezone.utc)
    job.status = "in_progress"
    job.started_at = now
    db.add(job)
    await db.commit()

    role_id = job.result["role_id"]
    changes = job.result.get("changes", {})

    result = await db.execute(select(Role).where(Role.id == role_id))
    role = result.scalar_one_or_none()
    if role is None:
        job.status = "failed"
        job.error_message = "Associated role not found"
        job.completed_at = datetime.now(timezone.utc)
        db.add(job)
        await db.commit()
        return

    result = await db.execute(select(Account).where(Account.id == role.account_id))
    account = result.scalar_one()

    try:
        await aws.update_iam_role(
            aws_account_id=account.aws_account_id,
            role_name=role.role_name,
            changes=changes,
        )

        role.status = "active"
        role.error_message = None
        db.add(role)

        job.status = "completed"
        job.completed_at = datetime.now(timezone.utc)
        db.add(job)

        await log_event(
            db,
            action="role.update.completed",
            user_id=job.started_by,
            resource_type="role",
            resource_id=str(role.id),
            detail={"changes": list(changes.keys())},
        )
        await db.commit()

    except Exception as exc:
        logger.exception("Role update failed for role %s", role_id)
        safe_msg = _sanitize_error(exc)

        role.status = "failed"
        role.error_message = safe_msg
        db.add(role)

        job.status = "failed"
        job.error_message = safe_msg
        job.completed_at = datetime.now(timezone.utc)
        db.add(job)

        await log_event(
            db,
            action="role.update.failed",
            user_id=job.started_by,
            resource_type="role",
            resource_id=str(role.id),
            detail={"error": safe_msg},
        )
        await db.commit()


async def run_delete_role(job: Job, db: AsyncSession) -> None:
    """Delete an IAM role from the target account and remove the DB row."""
    now = datetime.now(timezone.utc)
    job.status = "in_progress"
    job.started_at = now
    db.add(job)
    await db.commit()

    role_id = job.result["role_id"]
    role_name = job.result["role_name"]
    aws_account_id = job.result["aws_account_id"]

    try:
        await aws.delete_iam_role(aws_account_id, role_name)

        # Delete the Role row from the database
        result = await db.execute(select(Role).where(Role.id == role_id))
        role = result.scalar_one_or_none()
        if role is not None:
            await db.delete(role)

        job.status = "completed"
        job.completed_at = datetime.now(timezone.utc)
        db.add(job)

        await log_event(
            db,
            action="role.delete.completed",
            user_id=job.started_by,
            resource_type="role",
            resource_id=str(role_id),
            detail={"role_name": role_name, "aws_account_id": aws_account_id},
        )
        await db.commit()

    except Exception as exc:
        logger.exception("Role deletion failed for role %s", role_id)
        safe_msg = _sanitize_error(exc)

        # Reload role to set failure status (role may not be in scope)
        result = await db.execute(select(Role).where(Role.id == role_id))
        failed_role = result.scalar_one_or_none()
        if failed_role is not None:
            failed_role.status = "failed"
            failed_role.error_message = safe_msg
            db.add(failed_role)

        job.status = "failed"
        job.error_message = safe_msg
        job.completed_at = datetime.now(timezone.utc)
        db.add(job)

        await log_event(
            db,
            action="role.delete.failed",
            user_id=job.started_by,
            resource_type="role",
            resource_id=str(role_id),
            detail={"error": safe_msg},
        )
        await db.commit()


BOOTSTRAP_REPAIR_DELAY = timedelta(minutes=5)


async def verify_account_bootstraps(background_tasks: set) -> int:
    """Check each active account's bootstrap and schedule repairs for failures.

    For every active account with an ``aws_account_id``, attempts
    ``assume_groundwork_admin()``.  If the call fails, creates a delayed
    ``bootstrap_account`` job (scheduled 5 minutes in the future) so the
    StackSet deployment has time to propagate.

    Returns the number of repair jobs created.
    """
    async with async_session_factory() as db:
        system_user = await get_or_create_system_user(db)

        # Active accounts with an AWS account ID
        result = await db.execute(
            select(Account).where(
                Account.aws_account_id.isnot(None),
                Account.status == "active",
            )
        )
        accounts = result.scalars().all()

        if not accounts:
            return 0

        # Accounts that already have a pending bootstrap_account job
        result = await db.execute(
            select(Job.account_id).where(
                Job.job_type == "bootstrap_account",
                Job.status == "pending",
            )
        )
        already_pending = {row[0] for row in result.all()}

        repair_jobs: list[Job] = []
        now = datetime.now(timezone.utc)

        for account in accounts:
            if account.id in already_pending:
                continue

            try:
                await aws.assume_groundwork_admin(account.aws_account_id)
            except Exception:
                logger.warning(
                    "Bootstrap check failed for account %s (%s), scheduling repair",
                    account.id,
                    account.aws_account_id,
                )
                job = Job(
                    account_id=account.id,
                    job_type="bootstrap_account",
                    status="pending",
                    started_by=system_user.id,
                    scheduled_after=now + BOOTSTRAP_REPAIR_DELAY,
                )
                db.add(job)
                repair_jobs.append(job)

        await db.commit()

    # Spawn tasks after commit so rows are visible to new sessions
    for job in repair_jobs:
        task = asyncio.create_task(execute_job(job.id))
        background_tasks.add(task)
        task.add_done_callback(background_tasks.discard)

    return len(repair_jobs)


def _sanitize_error(exc: Exception) -> str:
    """Return a user-safe error message from an exception."""
    msg = str(exc)
    # Account provisioning errors
    if "Account creation failed:" in msg:
        return msg
    if "Account creation timed out" in msg:
        return msg
    if "Bootstrap stack deployment failed" in msg:
        return "Bootstrap stack deployment failed"
    if "Bootstrap stack deployment timed out" in msg:
        return "Bootstrap stack deployment timed out"
    # AWS IAM errors safe to surface
    safe_codes = ["EntityAlreadyExists", "MalformedPolicyDocument", "NoSuchEntity"]
    for code in safe_codes:
        if code in msg:
            return msg
    return "Operation failed — see server logs for details"
