"""Tests for startup bootstrap verification (verify_account_bootstraps)."""

import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from backend.services.jobs import verify_account_bootstraps
from backend.services.system_user import SYSTEM_USER_ID


def _make_account(aws_account_id="123456789012", status="active", account_id=None):
    account = MagicMock()
    account.id = account_id or uuid.uuid4()
    account.aws_account_id = aws_account_id
    account.status = status
    return account


def _make_system_user():
    user = MagicMock()
    user.id = SYSTEM_USER_ID
    return user


def _mock_session_factory(accounts, pending_account_ids=None):
    """Return a factory yielding a mock session.

    First execute call returns accounts, second returns pending job account_ids.
    """
    system_user = _make_system_user()
    call_count = 0

    @asynccontextmanager
    async def _factory():
        session = AsyncMock()
        session.add = MagicMock()

        async def execute_side_effect(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()

            if call_count == 1:
                # get_or_create_system_user query
                result.scalar_one_or_none.return_value = system_user
            elif call_count == 2:
                # Active accounts query
                scalars = MagicMock()
                scalars.all.return_value = accounts
                result.scalars.return_value = scalars
            elif call_count == 3:
                # Pending bootstrap jobs query
                rows = [(aid,) for aid in (pending_account_ids or [])]
                result.all.return_value = rows

            return result

        session.execute.side_effect = execute_side_effect
        yield session

    return _factory


class TestVerifyAccountBootstraps:
    async def test_no_accounts_returns_zero(self):
        background_tasks = set()

        with (
            patch(
                "backend.services.jobs.async_session_factory",
                _mock_session_factory(accounts=[]),
            ),
            patch(
                "backend.services.jobs.execute_job",
                new_callable=AsyncMock,
            ) as mock_execute,
        ):
            count = await verify_account_bootstraps(background_tasks)

        assert count == 0
        mock_execute.assert_not_called()

    async def test_healthy_accounts_return_zero(self):
        account = _make_account()
        background_tasks = set()

        with (
            patch(
                "backend.services.jobs.async_session_factory",
                _mock_session_factory(accounts=[account]),
            ),
            patch(
                "backend.services.jobs.aws.assume_groundwork_admin",
                new_callable=AsyncMock,
            ),
            patch(
                "backend.services.jobs.execute_job",
                new_callable=AsyncMock,
            ) as mock_execute,
        ):
            count = await verify_account_bootstraps(background_tasks)

        assert count == 0
        mock_execute.assert_not_called()

    async def test_failed_account_creates_delayed_job(self):
        account = _make_account()
        background_tasks = set()

        with (
            patch(
                "backend.services.jobs.async_session_factory",
                _mock_session_factory(accounts=[account]),
            ),
            patch(
                "backend.services.jobs.aws.assume_groundwork_admin",
                new_callable=AsyncMock,
                side_effect=Exception("role not found"),
            ),
            patch(
                "backend.services.jobs.execute_job",
                new_callable=AsyncMock,
            ) as mock_execute,
        ):
            count = await verify_account_bootstraps(background_tasks)

        assert count == 1
        mock_execute.assert_called_once()

    async def test_duplicate_prevention_skips_pending(self):
        account = _make_account()
        background_tasks = set()

        with (
            patch(
                "backend.services.jobs.async_session_factory",
                _mock_session_factory(
                    accounts=[account],
                    pending_account_ids=[account.id],
                ),
            ),
            patch(
                "backend.services.jobs.aws.assume_groundwork_admin",
                new_callable=AsyncMock,
                side_effect=Exception("role not found"),
            ),
            patch(
                "backend.services.jobs.execute_job",
                new_callable=AsyncMock,
            ) as mock_execute,
        ):
            count = await verify_account_bootstraps(background_tasks)

        assert count == 0
        mock_execute.assert_not_called()

    async def test_system_user_is_used_for_jobs(self):
        account = _make_account()
        background_tasks = set()
        added_objects = []
        system_user = _make_system_user()
        call_count = 0

        @asynccontextmanager
        async def capturing_factory():
            session = AsyncMock()

            def capture_add(obj):
                added_objects.append(obj)

            session.add = MagicMock(side_effect=capture_add)

            async def execute_side_effect(stmt):
                nonlocal call_count
                call_count += 1
                result = MagicMock()

                if call_count == 1:
                    result.scalar_one_or_none.return_value = system_user
                elif call_count == 2:
                    scalars = MagicMock()
                    scalars.all.return_value = [account]
                    result.scalars.return_value = scalars
                elif call_count == 3:
                    result.all.return_value = []

                return result

            session.execute.side_effect = execute_side_effect
            yield session

        with (
            patch(
                "backend.services.jobs.async_session_factory",
                capturing_factory,
            ),
            patch(
                "backend.services.jobs.aws.assume_groundwork_admin",
                new_callable=AsyncMock,
                side_effect=Exception("role not found"),
            ),
            patch(
                "backend.services.jobs.execute_job",
                new_callable=AsyncMock,
            ),
        ):
            await verify_account_bootstraps(background_tasks)

        jobs = [o for o in added_objects if hasattr(o, "job_type")]
        assert len(jobs) == 1
        assert jobs[0].started_by == SYSTEM_USER_ID
        assert jobs[0].scheduled_after is not None
        # Verify delay is approximately 5 minutes
        delay = jobs[0].scheduled_after - datetime.now(timezone.utc)
        assert timedelta(minutes=4) < delay < timedelta(minutes=6)
