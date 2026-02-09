"""Tests for the system user service."""

import uuid
from unittest.mock import AsyncMock, MagicMock

from backend.services.system_user import SYSTEM_USER_ID, get_or_create_system_user


def _mock_session(existing_user=None):
    """Return a mock async session that returns the given user on query."""
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = existing_user
    session.execute.return_value = result
    return session


class TestGetOrCreateSystemUser:
    async def test_creates_user_when_absent(self):
        session = _mock_session(existing_user=None)

        user = await get_or_create_system_user(session)

        assert user.id == SYSTEM_USER_ID
        assert user.sub == "system@groundwork.internal"
        assert user.is_admin is True
        session.add.assert_called_once_with(user)
        session.flush.assert_called_once()

    async def test_returns_existing_user(self):
        existing = MagicMock()
        existing.id = SYSTEM_USER_ID
        session = _mock_session(existing_user=existing)

        user = await get_or_create_system_user(session)

        assert user is existing
        session.add.assert_not_called()
        session.flush.assert_not_called()

    async def test_system_user_id_is_deterministic(self):
        expected = uuid.uuid5(uuid.NAMESPACE_DNS, "system.groundwork.internal")
        assert SYSTEM_USER_ID == expected
