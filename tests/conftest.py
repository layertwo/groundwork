"""
Pytest configuration and shared fixtures for Groundwork tests.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from backend.database import get_db
from backend.main import app
from tests.fixtures.database import *  # noqa: F403,F401
from tests.fixtures.oidc import *  # noqa: F403,F401


@pytest.fixture(autouse=True)
def setup_environment(monkeypatch):
    """Ensure test environment variables are set."""
    monkeypatch.setenv("GW_DEBUG", "true")
    monkeypatch.setenv("GW_SESSION_SECRET", "test-secret")


@pytest.fixture
async def client(db_session) -> AsyncClient:
    """Async HTTP client that shares the test DB session with the app."""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"X-Requested-With": "test"},
    ) as ac:
        yield ac
    app.dependency_overrides.pop(get_db, None)
