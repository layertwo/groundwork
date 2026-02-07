"""Unit tests for health endpoint."""

import pytest


class TestHealthEndpoint:
    async def test_health_returns_ok(self, client):
        """Test health endpoint returns expected response structure."""
        response = await client.get("/api/health")

        assert response.status_code == 200

        body = response.json()
        assert body["status"] == "ok"
        assert body["version"] == "0.1.0"
        assert body["database"] == "ok"

    async def test_health_response_fields(self, client):
        """Test health endpoint includes all required fields."""
        response = await client.get("/api/health")

        body = response.json()
        assert "status" in body
        assert "version" in body
        assert "database" in body
