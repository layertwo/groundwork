"""Database fixtures for async SQLAlchemy testing."""

from collections.abc import AsyncGenerator

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.config import settings


@pytest.fixture
def database_url():
    return settings.database_url


@pytest.fixture
async def async_engine(database_url):
    engine = create_async_engine(database_url, pool_pre_ping=True)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(async_engine) -> AsyncGenerator[AsyncSession, None]:
    """Provide a database session wrapped in a transaction that rolls back after each test.

    Tables must already exist (created by alembic migration).
    Each test gets an isolated transaction that is rolled back,
    so tests never see each other's data — safe for parallel execution.
    """
    async with async_engine.connect() as conn:
        txn = await conn.begin()
        session = AsyncSession(bind=conn, expire_on_commit=False)
        yield session
        await session.close()
        await txn.rollback()
