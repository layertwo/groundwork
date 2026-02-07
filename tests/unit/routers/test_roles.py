"""Unit tests for roles router stubs."""

import pytest


class TestRoleRoutes:
    async def test_list_roles_returns_501(self, client):
        """Test list roles stub returns 501 Not Implemented."""
        response = await client.get("/api/roles")

        assert response.status_code == 501
        assert response.json() == {"detail": "Not implemented"}

    async def test_assume_role_returns_501(self, client):
        """Test assume role stub returns 501 Not Implemented."""
        response = await client.post("/api/roles/assume")

        assert response.status_code == 501
        assert response.json() == {"detail": "Not implemented"}
