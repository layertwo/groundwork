"""
Pytest configuration and shared fixtures for Groundwork tests.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from backend.config import settings
from backend.main import app
from tests.fixtures.database import *  # noqa: F403,F401


@pytest.fixture(autouse=True)
def setup_environment(monkeypatch):
    """Ensure test environment variables are set."""
    monkeypatch.setenv("GW_DEBUG", "true")
    monkeypatch.setenv("GW_SESSION_SECRET", "test-secret")


@pytest.fixture
async def client() -> AsyncClient:
    """Async HTTP client for testing FastAPI endpoints."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
