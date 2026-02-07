import logging
from datetime import datetime, timedelta, timezone

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from backend.database import get_db
from backend.exceptions import ForbiddenError, UnauthorizedError
from backend.models.user import Session, User
from backend.services import oidc

logger = logging.getLogger(__name__)

SESSION_COOKIE = "gw_session"
REFRESH_THRESHOLD = timedelta(minutes=5)


async def get_current_user(
    request: Request, db: AsyncSession = Depends(get_db)
) -> User:
    session_id = request.cookies.get(SESSION_COOKIE)
    if not session_id:
        raise UnauthorizedError()

    result = await db.execute(
        select(Session)
        .options(joinedload(Session.user))
        .where(Session.id == session_id)
    )
    session = result.scalar_one_or_none()

    if session is None or session.user is None:
        raise UnauthorizedError()

    now = datetime.now(timezone.utc)
    if session.expires_at is not None and session.expires_at < now:
        raise UnauthorizedError("Session expired")

    if (
        session.expires_at is not None
        and session.refresh_token
        and session.expires_at - now < REFRESH_THRESHOLD
    ):
        try:
            tokens = await oidc.refresh_tokens(session.refresh_token)
            session.access_token = tokens.get("access_token")
            session.refresh_token = tokens.get("refresh_token", session.refresh_token)
            session.id_token = tokens.get("id_token")
            if "expires_in" in tokens:
                session.expires_at = now + timedelta(seconds=tokens["expires_in"])
            db.add(session)
        except Exception:
            logger.warning("Token refresh failed for session %s", session.id)

    return session.user


async def get_current_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise ForbiddenError()
    return user
