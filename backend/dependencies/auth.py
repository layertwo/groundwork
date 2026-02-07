import logging
from datetime import datetime, timedelta, timezone

from fastapi import Depends, Request
from itsdangerous import BadSignature, URLSafeSerializer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from backend.config import settings
from backend.database import get_db
from backend.exceptions import ForbiddenError, UnauthorizedError
from backend.models.user import Session, User
from backend.services import oidc
from backend.services.crypto import decrypt_token, encrypt_token

logger = logging.getLogger(__name__)

SESSION_COOKIE = "gw_session"
REFRESH_THRESHOLD = timedelta(minutes=5)
ABSOLUTE_SESSION_LIFETIME = timedelta(hours=24)

_signer = URLSafeSerializer(settings.session_secret, salt="gw-session")


def sign_session_id(session_id: str) -> str:
    return _signer.dumps(session_id)


def unsign_session_id(signed: str) -> str | None:
    try:
        return _signer.loads(signed)
    except BadSignature:
        return None


async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    cookie = request.cookies.get(SESSION_COOKIE)
    if not cookie:
        raise UnauthorizedError()

    session_id = unsign_session_id(cookie)
    if session_id is None:
        raise UnauthorizedError()

    result = await db.execute(
        select(Session).options(joinedload(Session.user)).where(Session.id == session_id)
    )
    session = result.scalar_one_or_none()

    if session is None or session.user is None:
        raise UnauthorizedError()

    now = datetime.now(timezone.utc)
    if session.expires_at is not None and session.expires_at < now:
        raise UnauthorizedError("Session expired")

    # H2: Absolute session lifetime — no refresh can extend beyond this
    if now - session.created_at > ABSOLUTE_SESSION_LIFETIME:
        raise UnauthorizedError("Session expired")

    if (
        session.expires_at is not None
        and session.refresh_token
        and session.expires_at - now < REFRESH_THRESHOLD
    ):
        plain_refresh = decrypt_token(session.refresh_token)
        if plain_refresh is None:
            logger.warning("Could not decrypt refresh token for session %s", session.id)
        else:
            try:
                tokens = await oidc.refresh_tokens(plain_refresh)
                raw_access = tokens.get("access_token")
                raw_refresh = tokens.get("refresh_token")
                raw_id = tokens.get("id_token")
                session.access_token = encrypt_token(raw_access) if raw_access else None
                session.refresh_token = (
                    encrypt_token(raw_refresh) if raw_refresh else session.refresh_token
                )
                session.id_token = encrypt_token(raw_id) if raw_id else session.id_token
                if "expires_in" in tokens:
                    session.expires_at = now + timedelta(seconds=tokens["expires_in"])
                db.add(session)
            except Exception:
                logger.warning("Token refresh failed for session %s", session.id)
                session.refresh_token = None
                db.add(session)

    return session.user


async def get_current_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise ForbiddenError()
    return user
