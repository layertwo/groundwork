"""Unit tests for jobs router stubs."""

import pytest


class TestJobRoutes:
    async def test_list_jobs_returns_501(self, client):
        """Test list jobs stub returns 501 Not Implemented."""
        response = await client.get("/api/jobs")

        assert response.status_code == 501
        assert response.json() == {"detail": "Not implemented"}

    async def test_get_job_returns_501(self, client):
        """Test get job stub returns 501 Not Implemented."""
        response = await client.get("/api/jobs/some-id")

        assert response.status_code == 501
        assert response.json() == {"detail": "Not implemented"}
