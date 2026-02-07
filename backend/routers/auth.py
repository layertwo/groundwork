import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.database import get_db
from backend.dependencies.auth import SESSION_COOKIE, get_current_user
from backend.exceptions import UnauthorizedError
from backend.models.user import Session, User
from backend.schemas.auth import AuthStatus, UserInfo
from backend.services import audit, oidc

router = APIRouter(prefix="/api/auth", tags=["auth"])

MAX_STATE_AGE = timedelta(minutes=10)


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
    session = result.scalar_one_or_none()

    if session is None:
        raise UnauthorizedError("Invalid state parameter")

    age = datetime.now(timezone.utc) - session.created_at.replace(tzinfo=timezone.utc)
    if age > MAX_STATE_AGE:
        await db.delete(session)
        raise UnauthorizedError("State expired")

    tokens = await oidc.exchange_code(code)
    id_token_str = tokens["id_token"]
    claims = await oidc.validate_id_token(id_token_str, nonce=session.nonce)

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

    expires_at = now + timedelta(seconds=tokens.get("expires_in", 3600))
    session.user_id = user.id
    session.access_token = tokens.get("access_token")
    session.refresh_token = tokens.get("refresh_token")
    session.id_token = id_token_str
    session.expires_at = expires_at
    session.state = None
    session.nonce = None
    db.add(session)

    await audit.log_event(
        db,
        action="auth.login",
        user_id=user.id,
        resource_type="session",
        resource_id=str(session.id),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    response = RedirectResponse(url=settings.app_url, status_code=302)
    response.set_cookie(
        key=SESSION_COOKIE,
        value=str(session.id),
        httponly=True,
        secure=not settings.debug,
        samesite="lax",
    )
    return response


@router.post("/logout")
async def logout(
    request: Request, db: AsyncSession = Depends(get_db)
) -> JSONResponse:
    session_id = request.cookies.get(SESSION_COOKIE)
    if session_id:
        result = await db.execute(select(Session).where(Session.id == session_id))
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
    response.delete_cookie(key=SESSION_COOKIE)
    return response


@router.get("/me")
async def me(user: User = Depends(get_current_user)) -> UserInfo:
    return UserInfo.model_validate(user)


@router.get("/status")
async def status(request: Request, db: AsyncSession = Depends(get_db)) -> AuthStatus:
    session_id = request.cookies.get(SESSION_COOKIE)
    if not session_id:
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
        return AuthStatus(authenticated=False)
