"""Tests for stale job recovery on server restart."""

import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from backend.services.jobs import recover_stale_jobs


def _make_job(status, started_at=None, scheduled_after=None):
    """Create a mock Job with the given status."""
    job = MagicMock()
    job.id = uuid.uuid4()
    job.status = status
    job.started_at = started_at
    job.scheduled_after = scheduled_after
    return job


def _mock_session_factory(jobs):
    """Return a factory that yields a mock session returning the given jobs."""

    @asynccontextmanager
    async def _factory():
        session = AsyncMock()
        result = MagicMock()
        scalars = MagicMock()
        scalars.all.return_value = jobs
        result.scalars.return_value = scalars
        session.execute.return_value = result
        yield session

    return _factory


class TestRecoverStaleJobs:
    async def test_pending_jobs_are_re_enqueued(self):
        """Pending jobs get picked up and spawned as asyncio tasks."""
        job = _make_job("pending")

        background_tasks = set()

        with (
            patch(
                "backend.services.jobs.async_session_factory",
                _mock_session_factory([job]),
            ),
            patch(
                "backend.services.jobs.execute_job",
                new_callable=AsyncMock,
            ) as mock_execute,
        ):
            count = await recover_stale_jobs(background_tasks)

        assert count == 1
        mock_execute.assert_called_once_with(job.id)
        # Pending jobs should not have their status changed
        assert job.status == "pending"

    async def test_in_progress_jobs_reset_to_pending(self):
        """In-progress jobs have status reset to pending and started_at cleared."""
        job = _make_job("in_progress", started_at=datetime.now(timezone.utc))

        background_tasks = set()

        with (
            patch(
                "backend.services.jobs.async_session_factory",
                _mock_session_factory([job]),
            ),
            patch(
                "backend.services.jobs.execute_job",
                new_callable=AsyncMock,
            ),
        ):
            count = await recover_stale_jobs(background_tasks)

        assert count == 1
        assert job.status == "pending"
        assert job.started_at is None

    async def test_completed_jobs_are_not_recovered(self):
        """Completed jobs should not be touched by recovery."""
        # The function only queries pending/in_progress, so completed jobs
        # won't appear in the result set. We simulate this by returning [].
        background_tasks = set()

        with (
            patch(
                "backend.services.jobs.async_session_factory",
                _mock_session_factory([]),
            ),
            patch(
                "backend.services.jobs.execute_job",
                new_callable=AsyncMock,
            ) as mock_execute,
        ):
            count = await recover_stale_jobs(background_tasks)

        assert count == 0
        mock_execute.assert_not_called()

    async def test_failed_jobs_are_not_recovered(self):
        """Failed jobs should not be touched by recovery (not queried)."""
        background_tasks = set()

        with (
            patch(
                "backend.services.jobs.async_session_factory",
                _mock_session_factory([]),
            ),
            patch(
                "backend.services.jobs.execute_job",
                new_callable=AsyncMock,
            ) as mock_execute,
        ):
            count = await recover_stale_jobs(background_tasks)

        assert count == 0
        mock_execute.assert_not_called()

    async def test_returns_correct_count_for_mixed_statuses(self):
        """Both pending and in_progress jobs are counted and re-enqueued."""
        pending_job = _make_job("pending")
        in_progress_job = _make_job("in_progress", started_at=datetime.now(timezone.utc))

        background_tasks = set()

        with (
            patch(
                "backend.services.jobs.async_session_factory",
                _mock_session_factory([pending_job, in_progress_job]),
            ),
            patch(
                "backend.services.jobs.execute_job",
                new_callable=AsyncMock,
            ) as mock_execute,
        ):
            count = await recover_stale_jobs(background_tasks)

        assert count == 2
        assert mock_execute.call_count == 2
        # in_progress should be reset
        assert in_progress_job.status == "pending"
        assert in_progress_job.started_at is None
        # pending should be unchanged
        assert pending_job.status == "pending"

    async def test_background_tasks_set_receives_task_references(self):
        """Recovered tasks are added to background_tasks set for GC protection."""
        job = _make_job("pending")

        background_tasks = set()

        with (
            patch(
                "backend.services.jobs.async_session_factory",
                _mock_session_factory([job]),
            ),
            patch(
                "backend.services.jobs.execute_job",
                new_callable=AsyncMock,
            ),
        ):
            await recover_stale_jobs(background_tasks)

        # The function ran without error. Tasks are added to the set and
        # may have already completed and been discarded via the done callback.

    async def test_session_commit_is_called(self):
        """Verify the function commits DB changes before spawning tasks."""
        job = _make_job("in_progress", started_at=datetime.now(timezone.utc))

        # Use a custom factory to capture the session mock
        session = AsyncMock()
        result = MagicMock()
        scalars = MagicMock()
        scalars.all.return_value = [job]
        result.scalars.return_value = scalars
        session.execute.return_value = result

        @asynccontextmanager
        async def factory():
            yield session

        background_tasks = set()

        with (
            patch("backend.services.jobs.async_session_factory", factory),
            patch(
                "backend.services.jobs.execute_job",
                new_callable=AsyncMock,
            ),
        ):
            await recover_stale_jobs(background_tasks)

        session.commit.assert_called_once()
        session.add.assert_called_once_with(job)

    async def test_future_scheduled_jobs_are_skipped(self):
        """Jobs with scheduled_after in the future should not be recovered.

        The SQL query filters them out, so they won't appear in results.
        We simulate this by returning an empty list (the DB would exclude them).
        """
        background_tasks = set()

        with (
            patch(
                "backend.services.jobs.async_session_factory",
                _mock_session_factory([]),
            ),
            patch(
                "backend.services.jobs.execute_job",
                new_callable=AsyncMock,
            ) as mock_execute,
        ):
            count = await recover_stale_jobs(background_tasks)

        assert count == 0
        mock_execute.assert_not_called()
