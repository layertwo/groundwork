"""Tests for job executor service."""

from unittest.mock import AsyncMock, patch

from backend.models.account import Account
from backend.models.job import Job
from backend.models.user import User
from backend.services.jobs import run_provision_account


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
