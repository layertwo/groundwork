"""Unit tests for health endpoint."""

from backend.database import get_db
from backend.main import app


class _UnreachableSession:
    async def execute(self, *args, **kwargs):
        raise RuntimeError("database down")


async def _broken_db():
    yield _UnreachableSession()


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

    async def test_health_returns_503_when_database_unreachable(self, client):
        previous = app.dependency_overrides[get_db]
        app.dependency_overrides[get_db] = _broken_db
        try:
            response = await client.get("/api/health")
        finally:
            app.dependency_overrides[get_db] = previous

        assert response.status_code == 503
        assert response.json() == {
            "status": "error",
            "version": "0.1.0",
            "database": "error",
        }
