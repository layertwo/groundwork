"""System user for automated jobs (bootstrap verification, scheduled repairs)."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.user import User

# uuid5(NAMESPACE_DNS, "system.groundwork.internal")
SYSTEM_USER_ID = uuid.UUID("8925bc3e-803b-5205-aefe-2a0f38317f4d")


async def get_or_create_system_user(db: AsyncSession) -> User:
    """Return the system user, creating it on first call."""
    result = await db.execute(select(User).where(User.id == SYSTEM_USER_ID))
    user = result.scalar_one_or_none()
    if user is not None:
        return user

    user = User(
        id=SYSTEM_USER_ID,
        sub="system@groundwork.internal",
        email="system@groundwork.internal",
        display_name="System",
        is_admin=True,
    )
    db.add(user)
    await db.flush()
    return user
