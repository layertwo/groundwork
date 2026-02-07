"""Tests for accounts router."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from backend.dependencies.auth import SESSION_COOKIE, sign_session_id
from backend.models.account import Account
from backend.models.user import Session, User


async def _create_authenticated_user(db_session, *, is_admin: bool = False):
    """Helper to create a user with a valid session, returns (user, signed_cookie)."""
    user = User(
        sub=f"acct-test-{is_admin}-{id(db_session)}",
        email=f"acct-{'admin' if is_admin else 'user'}-{id(db_session)}@example.com",
        display_name="Admin" if is_admin else "User",
        groups=["admins"] if is_admin else ["users"],
        is_admin=is_admin,
    )
    db_session.add(user)
    await db_session.flush()

    session = Session(
        user_id=user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(session)
    await db_session.flush()
    return user, sign_session_id(str(session.id))


def _cookies(signed_id: str) -> dict:
    return {SESSION_COOKIE: signed_id}


class TestCreateAccount:
    async def test_create_account_returns_201(self, client, db_session):
        admin, session_id = await _create_authenticated_user(db_session, is_admin=True)

        with patch("backend.routers.accounts.execute_job", new_callable=AsyncMock):
            response = await client.post(
                "/api/accounts",
                json={
                    "account_name": "Test Account",
                    "account_email": "test@example.com",
                    "organizational_unit": "ou-1234",
                    "sso_user_email": "sso@example.com",
                },
                cookies=_cookies(session_id),
            )

        assert response.status_code == 201
        data = response.json()
        assert data["account_name"] == "Test Account"
        assert data["account_email"] == "test@example.com"
        assert data["status"] == "pending"
        assert data["created_by"] == str(admin.id)

    async def test_create_account_non_admin_returns_403(self, client, db_session):
        _, session_id = await _create_authenticated_user(db_session, is_admin=False)

        response = await client.post(
            "/api/accounts",
            json={
                "account_name": "Test Account",
                "account_email": "test@example.com",
                "organizational_unit": "ou-1234",
                "sso_user_email": "sso@example.com",
            },
            cookies=_cookies(session_id),
        )

        assert response.status_code == 403

    async def test_create_account_unauthenticated_returns_401(self, client):
        response = await client.post(
            "/api/accounts",
            json={
                "account_name": "Test Account",
                "account_email": "test@example.com",
                "organizational_unit": "ou-1234",
                "sso_user_email": "sso@example.com",
            },
        )

        assert response.status_code == 401

    async def test_create_account_duplicate_email_returns_409(self, client, db_session):
        admin, session_id = await _create_authenticated_user(db_session, is_admin=True)

        account = Account(
            account_name="Existing",
            account_email="dupe@example.com",
            organizational_unit="ou-1234",
            sso_user_email="sso@example.com",
            created_by=admin.id,
        )
        db_session.add(account)
        await db_session.flush()

        response = await client.post(
            "/api/accounts",
            json={
                "account_name": "New Account",
                "account_email": "dupe@example.com",
                "organizational_unit": "ou-5678",
                "sso_user_email": "sso@example.com",
            },
            cookies=_cookies(session_id),
        )

        assert response.status_code == 409

    async def test_create_account_creates_job(self, client, db_session):
        admin, session_id = await _create_authenticated_user(db_session, is_admin=True)

        with patch("backend.routers.accounts.execute_job", new_callable=AsyncMock):
            response = await client.post(
                "/api/accounts",
                json={
                    "account_name": "Job Test",
                    "account_email": "job-test@example.com",
                    "organizational_unit": "ou-1234",
                    "sso_user_email": "sso@example.com",
                },
                cookies=_cookies(session_id),
            )

        assert response.status_code == 201

        # Verify job was created
        from sqlalchemy import select

        from backend.models.job import Job

        result = await db_session.execute(
            select(Job).where(Job.account_id == response.json()["id"])
        )
        job = result.scalar_one()
        assert job.job_type == "provision_account"
        assert job.status == "pending"
        assert job.started_by == admin.id


class TestListAccounts:
    async def test_list_accounts(self, client, db_session):
        admin, session_id = await _create_authenticated_user(db_session, is_admin=True)

        for i in range(3):
            db_session.add(
                Account(
                    account_name=f"Account {i}",
                    account_email=f"acct-{i}-{id(db_session)}@example.com",
                    organizational_unit="ou-1234",
                    sso_user_email="sso@example.com",
                    created_by=admin.id,
                )
            )
        await db_session.flush()

        response = await client.get("/api/accounts", cookies=_cookies(session_id))

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 3

    async def test_list_accounts_unauthenticated_returns_401(self, client):
        response = await client.get("/api/accounts")
        assert response.status_code == 401


class TestGetAccount:
    async def test_get_account(self, client, db_session):
        admin, session_id = await _create_authenticated_user(db_session, is_admin=True)

        account = Account(
            account_name="Get Test",
            account_email=f"get-test-{id(db_session)}@example.com",
            organizational_unit="ou-1234",
            sso_user_email="sso@example.com",
            created_by=admin.id,
        )
        db_session.add(account)
        await db_session.flush()

        response = await client.get(f"/api/accounts/{account.id}", cookies=_cookies(session_id))

        assert response.status_code == 200
        assert response.json()["account_name"] == "Get Test"

    async def test_get_account_not_found(self, client, db_session):
        _, session_id = await _create_authenticated_user(db_session, is_admin=True)
        fake_id = "00000000-0000-0000-0000-000000000000"

        response = await client.get(f"/api/accounts/{fake_id}", cookies=_cookies(session_id))

        assert response.status_code == 404


class TestUpdateAccount:
    async def test_update_account(self, client, db_session):
        admin, session_id = await _create_authenticated_user(db_session, is_admin=True)

        account = Account(
            account_name="Old Name",
            account_email=f"update-{id(db_session)}@example.com",
            organizational_unit="ou-1234",
            sso_user_email="sso@example.com",
            created_by=admin.id,
        )
        db_session.add(account)
        await db_session.flush()

        response = await client.patch(
            f"/api/accounts/{account.id}",
            json={"account_name": "New Name"},
            cookies=_cookies(session_id),
        )

        assert response.status_code == 200
        assert response.json()["account_name"] == "New Name"

    async def test_update_account_non_admin_returns_403(self, client, db_session):
        admin, _ = await _create_authenticated_user(db_session, is_admin=True)
        _, user_session = await _create_authenticated_user(db_session, is_admin=False)

        account = Account(
            account_name="Protected",
            account_email=f"prot-{id(db_session)}@example.com",
            organizational_unit="ou-1234",
            sso_user_email="sso@example.com",
            created_by=admin.id,
        )
        db_session.add(account)
        await db_session.flush()

        response = await client.patch(
            f"/api/accounts/{account.id}",
            json={"account_name": "Hacked"},
            cookies=_cookies(user_session),
        )

        assert response.status_code == 403
