import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.database import get_db
from backend.dependencies.auth import (
    SESSION_COOKIE,
    get_current_user,
    sign_session_id,
    unsign_session_id,
)
from backend.exceptions import UnauthorizedError
from backend.models.user import Session, User
from backend.schemas.auth import AuthStatus, UserInfo
from backend.services import audit, oidc
from backend.services.crypto import encrypt_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

MAX_STATE_AGE = timedelta(minutes=10)

_COOKIE_OPTS = {
    "key": SESSION_COOKIE,
    "httponly": True,
    "secure": not settings.debug,
    "samesite": "lax",
}


@router.get("/login")
async def login(db: AsyncSession = Depends(get_db)) -> RedirectResponse:
    state = secrets.token_hex(32)
    nonce = secrets.token_hex(32)

    session = Session(state=state, nonce=nonce)
    db.add(session)
    await db.flush()

    authorization_url = await oidc.create_authorization_url(state=state, nonce=nonce)
    return RedirectResponse(url=authorization_url, status_code=302)


@router.get("/callback")
async def callback(
    code: str, state: str, request: Request, db: AsyncSession = Depends(get_db)
) -> RedirectResponse:
    result = await db.execute(select(Session).where(Session.state == state))
    pre_auth_session = result.scalar_one_or_none()

    if pre_auth_session is None:
        await audit.log_event(
            db,
            action="auth.callback_failed",
            detail={"reason": "invalid_state"},
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        raise UnauthorizedError("Invalid state parameter")

    age = datetime.now(timezone.utc) - pre_auth_session.created_at.replace(
        tzinfo=timezone.utc
    )
    if age > MAX_STATE_AGE:
        await db.delete(pre_auth_session)
        await audit.log_event(
            db,
            action="auth.callback_failed",
            detail={"reason": "state_expired"},
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        raise UnauthorizedError("State expired")

    tokens = await oidc.exchange_code(code)
    id_token_str = tokens["id_token"]
    claims = await oidc.validate_id_token(id_token_str, nonce=pre_auth_session.nonce)

    sub = claims["sub"]
    email = claims.get("email", "")
    display_name = claims.get("name") or claims.get("preferred_username", "")
    groups = claims.get("groups", [])

    result = await db.execute(select(User).where(User.sub == sub))
    user = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)
    if user is None:
        user = User(
            sub=sub,
            email=email,
            display_name=display_name,
            groups=groups,
            last_login_at=now,
        )
        db.add(user)
        await db.flush()
    else:
        user.email = email
        user.display_name = display_name
        user.groups = groups
        user.last_login_at = now
        db.add(user)

    # M2: Create a new session (prevents session fixation)
    await db.delete(pre_auth_session)

    expires_at = now + timedelta(seconds=tokens.get("expires_in", 3600))
    raw_access = tokens.get("access_token")
    raw_refresh = tokens.get("refresh_token")
    auth_session = Session(
        user_id=user.id,
        access_token=encrypt_token(raw_access) if raw_access else None,
        refresh_token=encrypt_token(raw_refresh) if raw_refresh else None,
        id_token=encrypt_token(id_token_str),
        expires_at=expires_at,
    )
    db.add(auth_session)
    await db.flush()

    await audit.log_event(
        db,
        action="auth.login",
        user_id=user.id,
        resource_type="session",
        resource_id=str(auth_session.id),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    response = RedirectResponse(url=settings.app_url, status_code=302)
    response.set_cookie(value=sign_session_id(str(auth_session.id)), **_COOKIE_OPTS)
    return response


@router.post("/logout")
async def logout(
    request: Request, db: AsyncSession = Depends(get_db)
) -> JSONResponse:
    cookie = request.cookies.get(SESSION_COOKIE)
    if cookie:
        session_id = unsign_session_id(cookie)
        if session_id:
            result = await db.execute(
                select(Session).where(Session.id == session_id)
            )
            session = result.scalar_one_or_none()
            if session:
                user_id = session.user_id
                await db.delete(session)
                await audit.log_event(
                    db,
                    action="auth.logout",
                    user_id=user_id,
                    resource_type="session",
                    resource_id=session_id,
                    ip_address=request.client.host if request.client else None,
                    user_agent=request.headers.get("user-agent"),
                )

    response = JSONResponse(content={"detail": "logged out"})
    response.delete_cookie(**_COOKIE_OPTS)
    return response


@router.get("/me")
async def me(user: User = Depends(get_current_user)) -> UserInfo:
    return UserInfo.model_validate(user)


@router.get("/status")
async def status(request: Request, db: AsyncSession = Depends(get_db)) -> AuthStatus:
    cookie = request.cookies.get(SESSION_COOKIE)
    if not cookie:
        return AuthStatus(authenticated=False)

    session_id = unsign_session_id(cookie)
    if session_id is None:
        return AuthStatus(authenticated=False)

    try:
        result = await db.execute(select(Session).where(Session.id == session_id))
        session = result.scalar_one_or_none()
        if session is None or session.user_id is None:
            return AuthStatus(authenticated=False)

        now = datetime.now(timezone.utc)
        if session.expires_at is not None and session.expires_at < now:
            return AuthStatus(authenticated=False)

        result = await db.execute(select(User).where(User.id == session.user_id))
        user = result.scalar_one_or_none()
        if user is None:
            return AuthStatus(authenticated=False)

        return AuthStatus(
            authenticated=True,
            user=UserInfo.model_validate(user),
        )
    except Exception:
        logger.exception("Unexpected error in /api/auth/status")
        return AuthStatus(authenticated=False)
