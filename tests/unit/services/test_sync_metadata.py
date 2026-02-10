"""Tests for account metadata sync."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from backend.models.account import Account
from backend.models.role import Role
from backend.models.user import User
from backend.services.jobs import sync_account_metadata


async def _create_user(db_session):
    user = User(
        sub=f"sync-meta-{id(db_session)}",
        email=f"sync-meta-{id(db_session)}@example.com",
        display_name="Sync Test",
        groups=["admins"],
        is_admin=True,
    )
    db_session.add(user)
    await db_session.flush()
    return user


class TestSyncAccountMetadata:
    async def test_updates_alias_and_color(self, db_session):
        user = await _create_user(db_session)
        account = Account(
            account_name="Sync Test",
            account_email=f"sync-{id(db_session)}@example.com",
            organizational_unit="ou-1234",
            sso_user_email="sso@example.com",
            created_by=user.id,
            status="active",
            aws_account_id="111111111111",
        )
        db_session.add(account)
        await db_session.flush()

        with (
            patch(
                "backend.services.jobs.aws.get_account_alias",
                new_callable=AsyncMock,
                return_value="prod",
            ),
            patch(
                "backend.services.jobs.aws.get_account_color",
                new_callable=AsyncMock,
                return_value="red",
            ),
        ):
            await sync_account_metadata(account, db_session)

        await db_session.refresh(account)
        assert account.alias == "prod"
        assert account.color == "red"

    async def test_detects_deleted_role(self, db_session):
        user = await _create_user(db_session)
        account = Account(
            account_name="Drift Test",
            account_email=f"drift-{id(db_session)}@example.com",
            organizational_unit="ou-1234",
            sso_user_email="sso@example.com",
            created_by=user.id,
            status="active",
            aws_account_id="222222222222",
        )
        db_session.add(account)
        await db_session.flush()

        role = Role(
            account_id=account.id,
            role_name="DeletedRole",
            role_arn="arn:aws:iam::222222222222:role/DeletedRole",
            status="active",
            managed_policy_arns=["arn:aws:iam::aws:policy/ReadOnlyAccess"],
        )
        db_session.add(role)
        await db_session.flush()

        with (
            patch(
                "backend.services.jobs.aws.get_account_alias",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "backend.services.jobs.aws.get_account_color",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "backend.services.jobs.aws.get_iam_role_metadata",
                new_callable=AsyncMock,
                return_value={
                    "exists": False,
                    "max_session_duration": None,
                    "attached_policy_arns": [],
                    "last_used": None,
                },
            ),
        ):
            await sync_account_metadata(account, db_session)

        await db_session.refresh(role)
        assert role.status == "drifted"

    async def test_detects_policy_drift(self, db_session):
        user = await _create_user(db_session)
        account = Account(
            account_name="Policy Drift",
            account_email=f"policy-drift-{id(db_session)}@example.com",
            organizational_unit="ou-1234",
            sso_user_email="sso@example.com",
            created_by=user.id,
            status="active",
            aws_account_id="333333333333",
        )
        db_session.add(account)
        await db_session.flush()

        role = Role(
            account_id=account.id,
            role_name="DriftedRole",
            role_arn="arn:aws:iam::333333333333:role/DriftedRole",
            status="active",
            managed_policy_arns=["arn:aws:iam::aws:policy/ReadOnlyAccess"],
            api_session_duration=900,
            console_session_duration=3600,
        )
        db_session.add(role)
        await db_session.flush()

        with (
            patch(
                "backend.services.jobs.aws.get_account_alias",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "backend.services.jobs.aws.get_account_color",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "backend.services.jobs.aws.get_iam_role_metadata",
                new_callable=AsyncMock,
                return_value={
                    "exists": True,
                    "max_session_duration": 3600,
                    "attached_policy_arns": ["arn:aws:iam::aws:policy/AdministratorAccess"],
                    "last_used": datetime(2025, 6, 15, tzinfo=timezone.utc),
                },
            ),
        ):
            await sync_account_metadata(account, db_session)

        await db_session.refresh(role)
        assert role.status == "drifted"

    async def test_no_drift_when_matching(self, db_session):
        user = await _create_user(db_session)
        account = Account(
            account_name="No Drift",
            account_email=f"no-drift-{id(db_session)}@example.com",
            organizational_unit="ou-1234",
            sso_user_email="sso@example.com",
            created_by=user.id,
            status="active",
            aws_account_id="444444444444",
        )
        db_session.add(account)
        await db_session.flush()

        role = Role(
            account_id=account.id,
            role_name="GoodRole",
            role_arn="arn:aws:iam::444444444444:role/GoodRole",
            status="active",
            managed_policy_arns=["arn:aws:iam::aws:policy/ReadOnlyAccess"],
            api_session_duration=900,
            console_session_duration=3600,
        )
        db_session.add(role)
        await db_session.flush()

        with (
            patch(
                "backend.services.jobs.aws.get_account_alias",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "backend.services.jobs.aws.get_account_color",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "backend.services.jobs.aws.get_iam_role_metadata",
                new_callable=AsyncMock,
                return_value={
                    "exists": True,
                    "max_session_duration": 3600,
                    "attached_policy_arns": ["arn:aws:iam::aws:policy/ReadOnlyAccess"],
                    "last_used": None,
                },
            ),
        ):
            await sync_account_metadata(account, db_session)

        await db_session.refresh(role)
        assert role.status == "active"
