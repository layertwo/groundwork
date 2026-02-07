"""Tests for auth router endpoints."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from backend.dependencies.auth import SESSION_COOKIE, sign_session_id
from backend.models.user import Session, User
from tests.fixtures.oidc import MOCK_ISSUER, make_token_response


def _utcnow_naive() -> datetime:
    """Return current UTC time as a tz-naive datetime (for TIMESTAMP WITHOUT TIME ZONE)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _signed_cookie(session_id: str) -> dict:
    return {SESSION_COOKIE: sign_session_id(session_id)}


class TestLogin:
    async def test_login_redirects_to_oidc_provider(self, client, mock_oidc_discovery):
        response = await client.get("/api/auth/login", follow_redirects=False)

        assert response.status_code == 302
        location = response.headers["location"]
        assert MOCK_ISSUER in location
        assert "state=" in location
        assert "nonce=" in location


class TestCallback:
    async def test_callback_creates_user_and_session(
        self, client, db_session, mock_oidc_exchange, mock_oidc_validate
    ):
        session = Session(state="test-state", nonce="test-nonce", created_at=_utcnow_naive())
        db_session.add(session)
        await db_session.flush()

        nonce = "test-nonce"
        tokens = make_token_response(nonce=nonce)
        mock_oidc_exchange.return_value = tokens
        mock_oidc_validate.return_value = {
            "sub": "new-user-sub",
            "email": "new@example.com",
            "name": "New User",
            "groups": ["engineers"],
            "nonce": nonce,
        }

        response = await client.get(
            "/api/auth/callback",
            params={"code": "auth-code", "state": "test-state"},
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert SESSION_COOKIE in response.cookies

    async def test_callback_updates_existing_user(
        self, client, db_session, mock_oidc_exchange, mock_oidc_validate
    ):
        user = User(
            sub="existing-sub",
            email="old@example.com",
            display_name="Old Name",
            groups=["old-group"],
        )
        db_session.add(user)
        await db_session.flush()

        session = Session(
            state="test-state-2", nonce="test-nonce-2", created_at=_utcnow_naive()
        )
        db_session.add(session)
        await db_session.flush()

        nonce = "test-nonce-2"
        tokens = make_token_response(
            nonce=nonce,
            sub="existing-sub",
            email="updated@example.com",
            name="Updated Name",
            groups=["new-group"],
        )
        mock_oidc_exchange.return_value = tokens
        mock_oidc_validate.return_value = {
            "sub": "existing-sub",
            "email": "updated@example.com",
            "name": "Updated Name",
            "groups": ["new-group"],
            "nonce": nonce,
        }

        response = await client.get(
            "/api/auth/callback",
            params={"code": "auth-code", "state": "test-state-2"},
            follow_redirects=False,
        )

        assert response.status_code == 302

        result = await db_session.execute(
            select(User).where(User.sub == "existing-sub")
        )
        updated_user = result.scalar_one()
        assert updated_user.email == "updated@example.com"
        assert updated_user.display_name == "Updated Name"
        assert updated_user.groups == ["new-group"]

    async def test_callback_invalid_state_returns_401(self, client):
        response = await client.get(
            "/api/auth/callback",
            params={"code": "auth-code", "state": "invalid-state"},
            follow_redirects=False,
        )

        assert response.status_code == 401


class TestMe:
    async def test_me_returns_user_info(self, client, db_session):
        user = User(
            sub="me-sub",
            email="me@example.com",
            display_name="Me User",
            groups=["devs"],
            is_admin=False,
        )
        db_session.add(user)
        await db_session.flush()

        session = Session(
            user_id=user.id,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            created_at=_utcnow_naive(),
        )
        db_session.add(session)
        await db_session.flush()

        response = await client.get(
            "/api/auth/me",
            cookies=_signed_cookie(str(session.id)),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["sub"] == "me-sub"
        assert data["email"] == "me@example.com"
        assert data["display_name"] == "Me User"
        assert data["groups"] == ["devs"]
        assert data["is_admin"] is False

    async def test_me_unauthenticated_returns_401(self, client):
        response = await client.get("/api/auth/me")
        assert response.status_code == 401

    async def test_me_tampered_cookie_returns_401(self, client):
        response = await client.get(
            "/api/auth/me",
            cookies={SESSION_COOKIE: "tampered-value"},
        )
        assert response.status_code == 401

    async def test_me_expired_session_returns_401(self, client, db_session):
        user = User(
            sub="expired-sub",
            email="expired@example.com",
            display_name="Expired User",
            groups=[],
        )
        db_session.add(user)
        await db_session.flush()

        session = Session(
            user_id=user.id,
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
            created_at=_utcnow_naive(),
        )
        db_session.add(session)
        await db_session.flush()

        response = await client.get(
            "/api/auth/me",
            cookies=_signed_cookie(str(session.id)),
        )

        assert response.status_code == 401


class TestStatus:
    async def test_status_authenticated_returns_user(self, client, db_session):
        user = User(
            sub="status-sub",
            email="status@example.com",
            display_name="Status User",
            groups=["team"],
            is_admin=True,
        )
        db_session.add(user)
        await db_session.flush()

        session = Session(
            user_id=user.id,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            created_at=_utcnow_naive(),
        )
        db_session.add(session)
        await db_session.flush()

        response = await client.get(
            "/api/auth/status",
            cookies=_signed_cookie(str(session.id)),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["authenticated"] is True
        assert data["user"]["email"] == "status@example.com"

    async def test_status_unauthenticated_returns_false(self, client):
        response = await client.get("/api/auth/status")

        assert response.status_code == 200
        data = response.json()
        assert data["authenticated"] is False
        assert data["user"] is None

    async def test_status_tampered_cookie_returns_false(self, client):
        response = await client.get(
            "/api/auth/status",
            cookies={SESSION_COOKIE: "bad-signature"},
        )

        assert response.status_code == 200
        assert response.json()["authenticated"] is False

    async def test_status_expired_session_returns_false(self, client, db_session):
        user = User(
            sub="status-expired-sub",
            email="se@example.com",
            display_name="SE User",
            groups=[],
        )
        db_session.add(user)
        await db_session.flush()

        session = Session(
            user_id=user.id,
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
            created_at=_utcnow_naive(),
        )
        db_session.add(session)
        await db_session.flush()

        response = await client.get(
            "/api/auth/status",
            cookies=_signed_cookie(str(session.id)),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["authenticated"] is False


class TestLogout:
    async def test_logout_clears_session(self, client, db_session):
        user = User(
            sub="logout-sub",
            email="logout@example.com",
            display_name="Logout User",
            groups=[],
        )
        db_session.add(user)
        await db_session.flush()

        session = Session(
            user_id=user.id,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            created_at=_utcnow_naive(),
        )
        db_session.add(session)
        await db_session.flush()

        response = await client.post(
            "/api/auth/logout",
            cookies=_signed_cookie(str(session.id)),
        )

        assert response.status_code == 200
        assert response.json() == {"detail": "logged out"}

    async def test_logout_without_session_succeeds(self, client):
        response = await client.post("/api/auth/logout")

        assert response.status_code == 200
        assert response.json() == {"detail": "logged out"}
