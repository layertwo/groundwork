"""Unit tests for User and Session models."""

import uuid

import pytest
from sqlalchemy import select

from backend.models import Session, User


class TestUserModel:
    async def test_create_user(self, db_session):
        """Test creating a user persists to the database."""
        user = User(
            sub="auth|123456",
            email="test@example.com",
            display_name="Test User",
            groups=["engineering"],
        )
        db_session.add(user)
        await db_session.commit()

        result = await db_session.execute(select(User).where(User.sub == "auth|123456"))
        saved = result.scalar_one()

        assert saved.email == "test@example.com"
        assert saved.display_name == "Test User"
        assert saved.groups == ["engineering"]
        assert saved.is_admin is False
        assert saved.id is not None

    async def test_user_sub_unique(self, db_session):
        """Test that sub must be unique across users."""
        user1 = User(sub="auth|same", email="a@example.com", display_name="A")
        user2 = User(sub="auth|same", email="b@example.com", display_name="B")
        db_session.add(user1)
        await db_session.commit()

        db_session.add(user2)
        with pytest.raises(Exception):
            await db_session.commit()

    async def test_user_default_groups_empty(self, db_session):
        """Test that groups defaults to empty array."""
        user = User(sub="auth|no-groups", email="c@example.com", display_name="C")
        db_session.add(user)
        await db_session.commit()

        result = await db_session.execute(select(User).where(User.sub == "auth|no-groups"))
        saved = result.scalar_one()
        assert saved.groups == []


class TestSessionModel:
    async def test_create_session_without_user(self, db_session):
        """Test creating a session with null user_id (pre-auth OIDC redirect)."""
        session = Session(state="random-state", nonce="random-nonce")
        db_session.add(session)
        await db_session.commit()

        result = await db_session.execute(select(Session).where(Session.state == "random-state"))
        saved = result.scalar_one()

        assert saved.user_id is None
        assert saved.state == "random-state"
        assert saved.nonce == "random-nonce"
        assert saved.id is not None

    async def test_create_session_with_user(self, db_session):
        """Test creating a session linked to a user."""
        user = User(sub="auth|session-test", email="d@example.com", display_name="D")
        db_session.add(user)
        await db_session.commit()

        session = Session(
            user_id=user.id,
            access_token="tok",
            state="state",
            nonce="nonce",
        )
        db_session.add(session)
        await db_session.commit()

        result = await db_session.execute(select(Session).where(Session.user_id == user.id))
        saved = result.scalar_one()
        assert saved.access_token == "tok"
