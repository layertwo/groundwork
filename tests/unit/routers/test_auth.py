"""Unit tests for auth router stubs."""

import pytest


class TestAuthRoutes:
    async def test_login_returns_501(self, client):
        """Test login stub returns 501 Not Implemented."""
        response = await client.get("/api/auth/login")

        assert response.status_code == 501
        assert response.json() == {"detail": "Not implemented"}

    async def test_callback_returns_501(self, client):
        """Test callback stub returns 501 Not Implemented."""
        response = await client.get("/api/auth/callback")

        assert response.status_code == 501
        assert response.json() == {"detail": "Not implemented"}

    async def test_logout_returns_501(self, client):
        """Test logout stub returns 501 Not Implemented."""
        response = await client.post("/api/auth/logout")

        assert response.status_code == 501
        assert response.json() == {"detail": "Not implemented"}

    async def test_me_returns_501(self, client):
        """Test me stub returns 501 Not Implemented."""
        response = await client.get("/api/auth/me")

        assert response.status_code == 501
        assert response.json() == {"detail": "Not implemented"}

    async def test_status_returns_501(self, client):
        """Test status stub returns 501 Not Implemented."""
        response = await client.get("/api/auth/status")

        assert response.status_code == 501
        assert response.json() == {"detail": "Not implemented"}
