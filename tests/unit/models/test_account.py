"""Unit tests for Account model."""

import pytest
from sqlalchemy import select

from backend.models import Account, User


class TestAccountModel:
    async def test_create_account(self, db_session):
        """Test creating an account persists to the database."""
        user = User(sub="auth|acct-creator", email="creator@example.com", display_name="Creator")
        db_session.add(user)
        await db_session.commit()

        account = Account(
            account_name="dev-sandbox",
            account_email="dev-sandbox@example.com",
            organizational_unit="Sandbox",
            sso_user_email="admin@example.com",
            created_by=user.id,
        )
        db_session.add(account)
        await db_session.commit()

        result = await db_session.execute(
            select(Account).where(Account.account_name == "dev-sandbox")
        )
        saved = result.scalar_one()

        assert saved.status == "pending"
        assert saved.aws_account_id is None
        assert saved.created_by == user.id

    async def test_account_email_unique(self, db_session):
        """Test that account_email must be unique."""
        user = User(sub="auth|acct-uniq", email="uniq@example.com", display_name="Uniq")
        db_session.add(user)
        await db_session.commit()

        a1 = Account(
            account_name="a1",
            account_email="same@example.com",
            organizational_unit="OU",
            sso_user_email="sso@example.com",
            created_by=user.id,
        )
        a2 = Account(
            account_name="a2",
            account_email="same@example.com",
            organizational_unit="OU",
            sso_user_email="sso2@example.com",
            created_by=user.id,
        )
        db_session.add(a1)
        await db_session.commit()

        db_session.add(a2)
        with pytest.raises(Exception):
            await db_session.commit()
