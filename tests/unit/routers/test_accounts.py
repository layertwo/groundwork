"""Unit tests for accounts router stubs."""

import pytest


class TestAccountRoutes:
    async def test_list_accounts_returns_501(self, client):
        """Test list accounts stub returns 501 Not Implemented."""
        response = await client.get("/api/accounts")

        assert response.status_code == 501
        assert response.json() == {"detail": "Not implemented"}

    async def test_create_account_returns_501(self, client):
        """Test create account stub returns 501 Not Implemented."""
        response = await client.post("/api/accounts")

        assert response.status_code == 501
        assert response.json() == {"detail": "Not implemented"}

    async def test_get_account_returns_501(self, client):
        """Test get account stub returns 501 Not Implemented."""
        response = await client.get("/api/accounts/some-id")

        assert response.status_code == 501
        assert response.json() == {"detail": "Not implemented"}

    async def test_update_account_returns_501(self, client):
        """Test update account stub returns 501 Not Implemented."""
        response = await client.patch("/api/accounts/some-id")

        assert response.status_code == 501
        assert response.json() == {"detail": "Not implemented"}
