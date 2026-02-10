"""Tests for job executor service."""

from unittest.mock import AsyncMock, patch

from backend.models.account import Account
from backend.models.job import Job
from backend.models.role import Role
from backend.models.user import User
from backend.services.jobs import (
    run_bootstrap_account,
    run_create_role,
    run_provision_account,
    run_sync_accounts,
    run_update_role,
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


class TestCreateRoleSuccess:
    async def test_create_role_calls_aws_with_new_signature(self, db_session):
        """run_create_role passes role_id and account_id instead of OIDC params."""
        user = await _create_user(db_session)

        account = Account(
            account_name="Role Account",
            account_email=f"role-{id(db_session)}@example.com",
            organizational_unit="ou-1234",
            sso_user_email="sso@example.com",
            aws_account_id="111111111111",
            status="active",
            oidc_provider_arn="arn:aws:iam::111111111111:oidc-provider/idp.example.com",
            created_by=user.id,
        )
        db_session.add(account)
        await db_session.flush()

        role = Role(
            account_id=account.id,
            role_name="TestRole",
            role_arn="",
            allowed_groups=["devs"],
            allowed_users=["user1@example.com"],
            managed_policy_arns=["arn:aws:iam::aws:policy/ReadOnlyAccess"],
            inline_policy=None,
            api_session_duration=900,
            console_session_duration=3600,
            status="pending",
        )
        db_session.add(role)
        await db_session.flush()

        job = Job(
            account_id=account.id,
            job_type="create_role",
            status="pending",
            started_by=user.id,
            result={"role_id": str(role.id)},
        )
        db_session.add(job)
        await db_session.flush()

        mock_arn = "arn:aws:iam::111111111111:role/TestRole"
        with patch(
            "backend.services.jobs.aws.create_iam_role",
            new_callable=AsyncMock,
            return_value=mock_arn,
        ) as mock_create:
            await run_create_role(job, db_session)

        mock_create.assert_called_once_with(
            aws_account_id="111111111111",
            role_name="TestRole",
            role_id=str(role.id),
            account_id=str(role.account_id),
            managed_policy_arns=["arn:aws:iam::aws:policy/ReadOnlyAccess"],
            inline_policy=None,
            max_duration=3600,
        )

        await db_session.refresh(role)
        await db_session.refresh(job)
        assert role.status == "active"
        assert role.role_arn == mock_arn
        assert job.status == "completed"
        assert job.completed_at is not None

    async def test_create_role_missing_role_fails(self, db_session):
        """run_create_role fails gracefully when the role record is missing."""
        user = await _create_user(db_session)

        import uuid

        job = Job(
            job_type="create_role",
            status="pending",
            started_by=user.id,
            result={"role_id": str(uuid.uuid4())},
        )
        db_session.add(job)
        await db_session.flush()

        await run_create_role(job, db_session)

        await db_session.refresh(job)
        assert job.status == "failed"
        assert job.error_message == "Associated role not found"


class TestCreateRoleFailure:
    async def test_aws_error_marks_role_and_job_failed(self, db_session):
        """AWS error during create_iam_role marks both role and job as failed."""
        user = await _create_user(db_session)

        account = Account(
            account_name="Role Fail Account",
            account_email=f"rfail-{id(db_session)}@example.com",
            organizational_unit="ou-1234",
            sso_user_email="sso@example.com",
            aws_account_id="222222222222",
            status="active",
            oidc_provider_arn="arn:aws:iam::222222222222:oidc-provider/idp.example.com",
            created_by=user.id,
        )
        db_session.add(account)
        await db_session.flush()

        role = Role(
            account_id=account.id,
            role_name="FailRole",
            role_arn="",
            allowed_groups=[],
            allowed_users=[],
            managed_policy_arns=[],
            inline_policy=None,
            api_session_duration=900,
            console_session_duration=3600,
            status="pending",
        )
        db_session.add(role)
        await db_session.flush()

        job = Job(
            account_id=account.id,
            job_type="create_role",
            status="pending",
            started_by=user.id,
            result={"role_id": str(role.id)},
        )
        db_session.add(job)
        await db_session.flush()

        with patch(
            "backend.services.jobs.aws.create_iam_role",
            new_callable=AsyncMock,
            side_effect=RuntimeError("IAM CreateRole failed"),
        ):
            await run_create_role(job, db_session)

        await db_session.refresh(role)
        await db_session.refresh(job)
        assert role.status == "failed"
        assert job.status == "failed"
        assert job.completed_at is not None


class TestUpdateRoleSuccess:
    async def test_update_role_calls_aws_without_oidc_provider_arn(self, db_session):
        """run_update_role no longer passes oidc_provider_arn to aws.update_iam_role."""
        user = await _create_user(db_session)

        account = Account(
            account_name="Update Role Account",
            account_email=f"upd-{id(db_session)}@example.com",
            organizational_unit="ou-1234",
            sso_user_email="sso@example.com",
            aws_account_id="333333333333",
            status="active",
            oidc_provider_arn="arn:aws:iam::333333333333:oidc-provider/idp.example.com",
            created_by=user.id,
        )
        db_session.add(account)
        await db_session.flush()

        role = Role(
            account_id=account.id,
            role_name="UpdateRole",
            role_arn="arn:aws:iam::333333333333:role/UpdateRole",
            allowed_groups=["devs"],
            allowed_users=[],
            managed_policy_arns=["arn:aws:iam::aws:policy/ReadOnlyAccess"],
            inline_policy=None,
            api_session_duration=900,
            console_session_duration=3600,
            status="active",
        )
        db_session.add(role)
        await db_session.flush()

        changes = {"managed_policy_arns": ["arn:aws:iam::aws:policy/PowerUserAccess"]}

        job = Job(
            account_id=account.id,
            job_type="update_role",
            status="pending",
            started_by=user.id,
            result={"role_id": str(role.id), "changes": changes},
        )
        db_session.add(job)
        await db_session.flush()

        with patch(
            "backend.services.jobs.aws.update_iam_role",
            new_callable=AsyncMock,
        ) as mock_update:
            await run_update_role(job, db_session)

        mock_update.assert_called_once_with(
            aws_account_id="333333333333",
            role_name="UpdateRole",
            changes=changes,
        )

        await db_session.refresh(role)
        await db_session.refresh(job)
        assert role.status == "active"
        assert job.status == "completed"
        assert job.completed_at is not None

    async def test_update_role_missing_role_fails(self, db_session):
        """run_update_role fails gracefully when the role record is missing."""
        user = await _create_user(db_session)

        import uuid

        job = Job(
            job_type="update_role",
            status="pending",
            started_by=user.id,
            result={"role_id": str(uuid.uuid4()), "changes": {}},
        )
        db_session.add(job)
        await db_session.flush()

        await run_update_role(job, db_session)

        await db_session.refresh(job)
        assert job.status == "failed"
        assert job.error_message == "Associated role not found"


class TestUpdateRoleFailure:
    async def test_aws_error_marks_role_and_job_failed(self, db_session):
        """AWS error during update_iam_role marks both role and job as failed."""
        user = await _create_user(db_session)

        account = Account(
            account_name="Update Fail Account",
            account_email=f"ufail-{id(db_session)}@example.com",
            organizational_unit="ou-1234",
            sso_user_email="sso@example.com",
            aws_account_id="444444444444",
            status="active",
            oidc_provider_arn="arn:aws:iam::444444444444:oidc-provider/idp.example.com",
            created_by=user.id,
        )
        db_session.add(account)
        await db_session.flush()

        role = Role(
            account_id=account.id,
            role_name="FailUpdateRole",
            role_arn="arn:aws:iam::444444444444:role/FailUpdateRole",
            allowed_groups=[],
            allowed_users=[],
            managed_policy_arns=[],
            inline_policy=None,
            api_session_duration=900,
            console_session_duration=3600,
            status="active",
        )
        db_session.add(role)
        await db_session.flush()

        job = Job(
            account_id=account.id,
            job_type="update_role",
            status="pending",
            started_by=user.id,
            result={"role_id": str(role.id), "changes": {"max_duration": 7200}},
        )
        db_session.add(job)
        await db_session.flush()

        with patch(
            "backend.services.jobs.aws.update_iam_role",
            new_callable=AsyncMock,
            side_effect=RuntimeError("IAM UpdateRole failed"),
        ):
            await run_update_role(job, db_session)

        await db_session.refresh(role)
        await db_session.refresh(job)
        assert role.status == "failed"
        assert job.status == "failed"
        assert job.completed_at is not None
