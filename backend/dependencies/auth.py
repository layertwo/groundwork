import asyncio
import base64
import json
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

# Per-session lock to prevent concurrent token refresh races (MEDIUM-1)
_refresh_locks: dict[str, asyncio.Lock] = {}


def sign_session_id(session_id: str) -> str:
    return _signer.dumps(session_id)


def unsign_session_id(signed: str) -> str | None:
    try:
        return _signer.loads(signed)
    except BadSignature:
        return None


async def _load_validated_session(request: Request, db: AsyncSession) -> Session:
    """Load and validate a session from the request cookie.

    Shared logic for get_current_user and get_current_session to avoid
    divergence in security checks (MEDIUM-4).
    """
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

    # Absolute session lifetime — no refresh can extend beyond this
    if now - session.created_at > ABSOLUTE_SESSION_LIFETIME:
        raise UnauthorizedError("Session expired")

    return session


async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    session = await _load_validated_session(request, db)

    now = datetime.now(timezone.utc)
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


TOKEN_REFRESH_MARGIN = timedelta(seconds=60)


def _decode_jwt_exp(token: str) -> datetime | None:
    """Extract the exp claim from a JWT without signature validation.

    Returns None only if the token has no exp claim. Logs a warning and
    returns a past datetime for malformed tokens so they trigger a refresh
    rather than being passed to STS as-is (MEDIUM-3).
    """
    try:
        parts = token.split(".")
        if len(parts) != 3:
            logger.warning("Malformed JWT: expected 3 parts, got %d", len(parts))
            return datetime.min.replace(tzinfo=timezone.utc)
        payload_b64 = parts[1]
        # Add padding if needed
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        exp = payload.get("exp")
        if exp is not None:
            return datetime.fromtimestamp(exp, tz=timezone.utc)
    except Exception:
        logger.warning("Failed to decode JWT exp claim", exc_info=True)
        return datetime.min.replace(tzinfo=timezone.utc)
    return None


def _get_refresh_lock(session_id: str) -> asyncio.Lock:
    """Get or create a per-session asyncio lock for token refresh (MEDIUM-1)."""
    if session_id not in _refresh_locks:
        _refresh_locks[session_id] = asyncio.Lock()
    return _refresh_locks[session_id]


async def get_fresh_id_token(session: Session, db: AsyncSession) -> str:
    """Return a plaintext id_token from the session, refreshing if near expiry.

    Uses a per-session lock to prevent concurrent refresh races (MEDIUM-1).
    Raises UnauthorizedError if no id_token is available.
    """
    if not session.id_token:
        raise UnauthorizedError("No id_token in session")

    lock = _get_refresh_lock(str(session.id))
    async with lock:
        # Re-read the token under lock in case another request already refreshed it
        plain_id_token = decrypt_token(session.id_token)
        if plain_id_token is None:
            raise UnauthorizedError("Could not decrypt id_token")

        now = datetime.now(timezone.utc)
        exp = _decode_jwt_exp(plain_id_token)

        if exp is not None and exp - now < TOKEN_REFRESH_MARGIN:
            if not session.refresh_token:
                raise UnauthorizedError("id_token expired and no refresh token available")

            plain_refresh = decrypt_token(session.refresh_token)
            if plain_refresh is None:
                raise UnauthorizedError("Could not decrypt refresh token")

            tokens = await oidc.refresh_tokens(plain_refresh)
            raw_id = tokens.get("id_token")
            if not raw_id:
                raise UnauthorizedError("Token refresh did not return an id_token")

            raw_access = tokens.get("access_token")
            raw_refresh = tokens.get("refresh_token")
            session.access_token = encrypt_token(raw_access) if raw_access else None
            session.refresh_token = (
                encrypt_token(raw_refresh) if raw_refresh else session.refresh_token
            )
            session.id_token = encrypt_token(raw_id)
            if "expires_in" in tokens:
                session.expires_at = now + timedelta(seconds=tokens["expires_in"])
            db.add(session)
            plain_id_token = raw_id

    return plain_id_token


async def get_current_session(request: Request, db: AsyncSession = Depends(get_db)) -> Session:
    """Return the current Session object (with user loaded).

    Used by endpoints that need direct access to session tokens (e.g. role assumption).
    Uses the shared _load_validated_session to ensure consistent security checks (MEDIUM-4).
    """
    return await _load_validated_session(request, db)
