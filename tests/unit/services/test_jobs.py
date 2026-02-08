"""Tests for job executor service."""

from unittest.mock import AsyncMock, patch

from backend.models.account import Account
from backend.models.job import Job
from backend.models.user import User
from backend.services.jobs import (
    run_bootstrap_account,
    run_provision_account,
    run_sync_accounts,
)


async def _create_user(db_session, *, is_admin: bool = True):
    user = User(
        sub=f"job-svc-{id(db_session)}",
        email=f"job-svc-{id(db_session)}@example.com",
        display_name="Job Runner",
        groups=["admins"],
        is_admin=is_admin,
    )
    db_session.add(user)
    await db_session.flush()
    return user


class TestProvisionJobSuccess:
    async def test_full_provisioning_pipeline(self, db_session):
        """Test successful account provisioning: create → poll → move → bootstrap → active."""
        user = await _create_user(db_session)

        account = Account(
            account_name="Provision Test",
            account_email=f"prov-{id(db_session)}@example.com",
            organizational_unit="ou-1234",
            sso_user_email="sso@example.com",
            status="pending",
            created_by=user.id,
        )
        db_session.add(account)
        await db_session.flush()

        job = Job(
            account_id=account.id,
            job_type="provision_account",
            status="pending",
            started_by=user.id,
        )
        db_session.add(job)
        await db_session.flush()

        with (
            patch(
                "backend.services.jobs.aws.create_account",
                new_callable=AsyncMock,
                return_value="car-abc123",
            ),
            patch(
                "backend.services.jobs.aws.poll_account_creation",
                new_callable=AsyncMock,
                return_value={
                    "status": "SUCCEEDED",
                    "aws_account_id": "123456789012",
                },
            ),
            patch(
                "backend.services.jobs.aws.move_account_to_ou",
                new_callable=AsyncMock,
            ),
            patch(
                "backend.services.jobs.aws.bootstrap_account",
                new_callable=AsyncMock,
                return_value={
                    "oidc_provider_arn": "arn:aws:iam::123456789012:oidc-provider/ex",
                    "admin_role_arn": "arn:aws:iam::123456789012:role/GWAdmin",
                },
            ) as mock_bootstrap,
            patch("backend.services.jobs.asyncio.sleep", new_callable=AsyncMock),
        ):
            await run_provision_account(job, db_session)

        await db_session.refresh(account)
        await db_session.refresh(job)

        assert account.status == "active"
        assert account.aws_account_id == "123456789012"
        assert account.oidc_provider_arn is not None
        assert job.status == "completed"
        assert job.completed_at is not None
        assert job.result["aws_account_id"] == "123456789012"
        mock_bootstrap.assert_called_once_with("123456789012", ou_id="ou-1234")


class TestProvisionJobFailure:
    async def test_creation_failure_marks_job_and_account_failed(self, db_session):
        """Test that AWS creation failure marks both job and account as failed."""
        user = await _create_user(db_session)

        account = Account(
            account_name="Fail Test",
            account_email=f"fail-{id(db_session)}@example.com",
            organizational_unit="ou-1234",
            sso_user_email="sso@example.com",
            status="pending",
            created_by=user.id,
        )
        db_session.add(account)
        await db_session.flush()

        job = Job(
            account_id=account.id,
            job_type="provision_account",
            status="pending",
            started_by=user.id,
        )
        db_session.add(job)
        await db_session.flush()

        with (
            patch(
                "backend.services.jobs.aws.create_account",
                new_callable=AsyncMock,
                return_value="car-fail123",
            ),
            patch(
                "backend.services.jobs.aws.poll_account_creation",
                new_callable=AsyncMock,
                return_value={
                    "status": "FAILED",
                    "error": "EMAIL_ALREADY_EXISTS",
                },
            ),
            patch("backend.services.jobs.asyncio.sleep", new_callable=AsyncMock),
        ):
            await run_provision_account(job, db_session)

        await db_session.refresh(account)
        await db_session.refresh(job)

        assert account.status == "failed"
        assert "EMAIL_ALREADY_EXISTS" in account.error_message
        assert job.status == "failed"
        assert job.completed_at is not None

    async def test_bootstrap_failure_marks_failed(self, db_session):
        """Test that bootstrap failure marks both job and account as failed."""
        user = await _create_user(db_session)

        account = Account(
            account_name="Bootstrap Fail",
            account_email=f"bfail-{id(db_session)}@example.com",
            organizational_unit="ou-1234",
            sso_user_email="sso@example.com",
            status="pending",
            created_by=user.id,
        )
        db_session.add(account)
        await db_session.flush()

        job = Job(
            account_id=account.id,
            job_type="provision_account",
            status="pending",
            started_by=user.id,
        )
        db_session.add(job)
        await db_session.flush()

        with (
            patch(
                "backend.services.jobs.aws.create_account",
                new_callable=AsyncMock,
                return_value="car-bs123",
            ),
            patch(
                "backend.services.jobs.aws.poll_account_creation",
                new_callable=AsyncMock,
                return_value={
                    "status": "SUCCEEDED",
                    "aws_account_id": "111222333444",
                },
            ),
            patch(
                "backend.services.jobs.aws.move_account_to_ou",
                new_callable=AsyncMock,
            ),
            patch(
                "backend.services.jobs.aws.bootstrap_account",
                new_callable=AsyncMock,
                side_effect=RuntimeError("IAM CreateRole failed"),
            ),
            patch("backend.services.jobs.asyncio.sleep", new_callable=AsyncMock),
        ):
            await run_provision_account(job, db_session)

        await db_session.refresh(account)
        await db_session.refresh(job)

        assert account.status == "failed"
        assert "Operation failed" in account.error_message
        assert job.status == "failed"


class TestBootstrapJobSuccess:
    async def test_bootstrap_sets_account_active_with_oidc_arn(self, db_session):
        """Successful bootstrap marks account active and sets oidc_provider_arn."""
        user = await _create_user(db_session)

        account = Account(
            account_name="Bootstrap Test",
            account_email=f"bs-{id(db_session)}@example.com",
            organizational_unit="ou-1234",
            sso_user_email="sso@example.com",
            aws_account_id="222222222222",
            status="active",
            created_by=user.id,
        )
        db_session.add(account)
        await db_session.flush()

        job = Job(
            account_id=account.id,
            job_type="bootstrap_account",
            status="pending",
            started_by=user.id,
        )
        db_session.add(job)
        await db_session.flush()

        with (
            patch(
                "backend.services.jobs.aws.bootstrap_account",
                new_callable=AsyncMock,
                return_value={
                    "oidc_provider_arn": (
                        "arn:aws:iam::222222222222:oidc-provider/idp.example.com"
                    ),
                    "admin_role_arn": "arn:aws:iam::222222222222:role/GroundworkAdmin",
                },
            ),
        ):
            await run_bootstrap_account(job, db_session)

        await db_session.refresh(account)
        await db_session.refresh(job)

        assert account.status == "active"
        assert (
            account.oidc_provider_arn == "arn:aws:iam::222222222222:oidc-provider/idp.example.com"
        )
        assert job.status == "completed"
        assert job.completed_at is not None


class TestBootstrapJobFailure:
    async def test_bootstrap_failure_marks_job_and_account_failed(self, db_session):
        """Bootstrap failure marks both job and account as failed."""
        user = await _create_user(db_session)

        account = Account(
            account_name="Bootstrap Fail",
            account_email=f"bsfail-{id(db_session)}@example.com",
            organizational_unit="ou-1234",
            sso_user_email="sso@example.com",
            aws_account_id="222222222222",
            status="active",
            created_by=user.id,
        )
        db_session.add(account)
        await db_session.flush()

        job = Job(
            account_id=account.id,
            job_type="bootstrap_account",
            status="pending",
            started_by=user.id,
        )
        db_session.add(job)
        await db_session.flush()

        with patch(
            "backend.services.jobs.aws.bootstrap_account",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Bootstrap stack deployment failed for account 222222222222"),
        ):
            await run_bootstrap_account(job, db_session)

        await db_session.refresh(account)
        await db_session.refresh(job)

        assert account.status == "failed"
        assert job.status == "failed"
        assert job.completed_at is not None


class TestSyncAccountsNewAccounts:
    async def test_imports_new_active_account_and_spawns_bootstrap(self, db_session):
        """Discovers a new ACTIVE account, creates Account + bootstrap_account Job."""
        user = await _create_user(db_session)

        job = Job(
            job_type="sync_accounts",
            status="pending",
            started_by=user.id,
        )
        db_session.add(job)
        await db_session.flush()

        with (
            patch(
                "backend.services.jobs.aws.ensure_bootstrap_stackset",
                new_callable=AsyncMock,
            ),
            patch(
                "backend.services.jobs.aws.list_org_accounts",
                new_callable=AsyncMock,
                return_value=[
                    {
                        "aws_account_id": "222222222222",
                        "name": "Workload",
                        "email": "work@example.com",
                        "status": "ACTIVE",
                    },
                ],
            ),
            patch(
                "backend.services.jobs.aws.get_account_ou",
                new_callable=AsyncMock,
                return_value="ou-abc1-12345678",
            ),
            patch("backend.services.jobs.asyncio.create_task"),
        ):
            await run_sync_accounts(job, db_session)

        await db_session.refresh(job)
        assert job.status == "completed"
        assert job.result["accounts_found"] == 1
        assert job.result["imported"] == 1
        assert job.result["bootstrap_triggered"] == 1

        # Verify account was created
        from sqlalchemy import select as sa_select

        result = await db_session.execute(
            sa_select(Account).where(Account.aws_account_id == "222222222222")
        )
        account = result.scalar_one()
        assert account.account_name == "Workload"
        assert account.account_email == "work@example.com"
        assert account.organizational_unit == "ou-abc1-12345678"
        assert account.aws_status == "ACTIVE"
        assert account.sso_user_email == "work@example.com"

        # Verify a bootstrap job was created
        result = await db_session.execute(
            sa_select(Job).where(
                Job.account_id == account.id,
                Job.job_type == "bootstrap_account",
            )
        )
        bootstrap_job = result.scalar_one()
        assert bootstrap_job.started_by == user.id

    async def test_imports_suspended_account_without_bootstrap(self, db_session):
        """Discovers a SUSPENDED account, imports it but skips bootstrap."""
        user = await _create_user(db_session)

        job = Job(
            job_type="sync_accounts",
            status="pending",
            started_by=user.id,
        )
        db_session.add(job)
        await db_session.flush()

        with (
            patch(
                "backend.services.jobs.aws.ensure_bootstrap_stackset",
                new_callable=AsyncMock,
            ),
            patch(
                "backend.services.jobs.aws.list_org_accounts",
                new_callable=AsyncMock,
                return_value=[
                    {
                        "aws_account_id": "333333333333",
                        "name": "Suspended Account",
                        "email": "sus@example.com",
                        "status": "SUSPENDED",
                    },
                ],
            ),
            patch(
                "backend.services.jobs.aws.get_account_ou",
                new_callable=AsyncMock,
                return_value="ou-abc1-12345678",
            ),
            patch("backend.services.jobs.asyncio.create_task"),
        ):
            await run_sync_accounts(job, db_session)

        await db_session.refresh(job)
        assert job.result["imported"] == 1
        assert job.result["skipped_suspended"] == 1
        assert job.result["bootstrap_triggered"] == 0

        # Account exists but no bootstrap job
        from sqlalchemy import select as sa_select

        result = await db_session.execute(
            sa_select(Account).where(Account.aws_account_id == "333333333333")
        )
        account = result.scalar_one()
        assert account.aws_status == "SUSPENDED"

        result = await db_session.execute(
            sa_select(Job).where(
                Job.account_id == account.id,
                Job.job_type == "bootstrap_account",
            )
        )
        assert result.scalar_one_or_none() is None


class TestSyncAccountsExistingAccounts:
    async def test_updates_changed_account_name(self, db_session):
        """Updates account_name when it has changed in AWS."""
        user = await _create_user(db_session)

        existing = Account(
            account_name="Old Name",
            account_email="work@example.com",
            organizational_unit="ou-abc1-12345678",
            sso_user_email="work@example.com",
            aws_account_id="222222222222",
            status="active",
            aws_status="ACTIVE",
            oidc_provider_arn="arn:aws:iam::222222222222:oidc-provider/idp.example.com",
            created_by=user.id,
        )
        db_session.add(existing)
        await db_session.flush()

        job = Job(
            job_type="sync_accounts",
            status="pending",
            started_by=user.id,
        )
        db_session.add(job)
        await db_session.flush()

        with (
            patch(
                "backend.services.jobs.aws.ensure_bootstrap_stackset",
                new_callable=AsyncMock,
            ),
            patch(
                "backend.services.jobs.aws.list_org_accounts",
                new_callable=AsyncMock,
                return_value=[
                    {
                        "aws_account_id": "222222222222",
                        "name": "New Name",
                        "email": "work@example.com",
                        "status": "ACTIVE",
                    },
                ],
            ),
            patch(
                "backend.services.jobs.aws.get_account_ou",
                new_callable=AsyncMock,
                return_value="ou-abc1-12345678",
            ),
            patch("backend.services.jobs.asyncio.create_task"),
        ):
            await run_sync_accounts(job, db_session)

        await db_session.refresh(existing)
        assert existing.account_name == "New Name"
        await db_session.refresh(job)
        assert job.result["updated"] == 1
        assert job.result["bootstrap_triggered"] == 0

    async def test_triggers_bootstrap_for_unbootstrapped_account(self, db_session):
        """Existing ACTIVE account with no oidc_provider_arn gets bootstrap job."""
        user = await _create_user(db_session)

        existing = Account(
            account_name="Unbootstrapped",
            account_email="un@example.com",
            organizational_unit="ou-abc1-12345678",
            sso_user_email="un@example.com",
            aws_account_id="222222222222",
            status="failed",
            aws_status="ACTIVE",
            created_by=user.id,
        )
        db_session.add(existing)
        await db_session.flush()

        job = Job(
            job_type="sync_accounts",
            status="pending",
            started_by=user.id,
        )
        db_session.add(job)
        await db_session.flush()

        with (
            patch(
                "backend.services.jobs.aws.ensure_bootstrap_stackset",
                new_callable=AsyncMock,
            ),
            patch(
                "backend.services.jobs.aws.list_org_accounts",
                new_callable=AsyncMock,
                return_value=[
                    {
                        "aws_account_id": "222222222222",
                        "name": "Unbootstrapped",
                        "email": "un@example.com",
                        "status": "ACTIVE",
                    },
                ],
            ),
            patch(
                "backend.services.jobs.aws.get_account_ou",
                new_callable=AsyncMock,
                return_value="ou-abc1-12345678",
            ),
            patch("backend.services.jobs.asyncio.create_task"),
        ):
            await run_sync_accounts(job, db_session)

        await db_session.refresh(job)
        assert job.result["bootstrap_triggered"] == 1

        from sqlalchemy import select as sa_select

        result = await db_session.execute(
            sa_select(Job).where(
                Job.account_id == existing.id,
                Job.job_type == "bootstrap_account",
            )
        )
        assert result.scalar_one() is not None
