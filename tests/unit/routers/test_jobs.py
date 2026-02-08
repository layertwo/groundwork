"""Tests for jobs router."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from backend.dependencies.auth import SESSION_COOKIE, sign_session_id
from backend.models.account import Account
from backend.models.job import Job
from backend.models.user import Session, User


async def _create_authenticated_user(db_session, *, is_admin: bool = False):
    """Helper to create a user with a valid session, returns (user, signed_cookie)."""
    user = User(
        sub=f"job-test-{is_admin}-{id(db_session)}",
        email=f"job-{'admin' if is_admin else 'user'}-{id(db_session)}@example.com",
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


class TestListJobs:
    async def test_list_jobs_admin_sees_all(self, client, db_session):
        admin, session_id = await _create_authenticated_user(db_session, is_admin=True)
        user, _ = await _create_authenticated_user(db_session, is_admin=False)

        account = Account(
            account_name="Job List Test",
            account_email=f"jl-{id(db_session)}@example.com",
            organizational_unit="ou-1234",
            sso_user_email="sso@example.com",
            created_by=admin.id,
        )
        db_session.add(account)
        await db_session.flush()

        # Create jobs from both users
        for u in [admin, user]:
            db_session.add(
                Job(
                    account_id=account.id,
                    job_type="provision_account",
                    started_by=u.id,
                )
            )
        await db_session.flush()

        response = await client.get("/api/jobs", cookies=_cookies(session_id))

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 2

    async def test_list_jobs_non_admin_sees_own(self, client, db_session):
        admin, _ = await _create_authenticated_user(db_session, is_admin=True)
        user, user_session = await _create_authenticated_user(db_session, is_admin=False)

        account = Account(
            account_name="Job Filter Test",
            account_email=f"jf-{id(db_session)}@example.com",
            organizational_unit="ou-1234",
            sso_user_email="sso@example.com",
            created_by=admin.id,
        )
        db_session.add(account)
        await db_session.flush()

        db_session.add(
            Job(
                account_id=account.id,
                job_type="provision_account",
                started_by=admin.id,
            )
        )
        db_session.add(
            Job(
                account_id=account.id,
                job_type="provision_account",
                started_by=user.id,
            )
        )
        await db_session.flush()

        response = await client.get("/api/jobs", cookies=_cookies(user_session))

        assert response.status_code == 200
        data = response.json()
        # Non-admin should only see their own job
        for job in data:
            assert job["started_by"] == str(user.id)

    async def test_list_jobs_filter_by_status(self, client, db_session):
        admin, session_id = await _create_authenticated_user(db_session, is_admin=True)

        account = Account(
            account_name="Status Filter",
            account_email=f"sf-{id(db_session)}@example.com",
            organizational_unit="ou-1234",
            sso_user_email="sso@example.com",
            created_by=admin.id,
        )
        db_session.add(account)
        await db_session.flush()

        db_session.add(
            Job(
                account_id=account.id,
                job_type="provision_account",
                status="completed",
                started_by=admin.id,
            )
        )
        db_session.add(
            Job(
                account_id=account.id,
                job_type="provision_account",
                status="pending",
                started_by=admin.id,
            )
        )
        await db_session.flush()

        response = await client.get(
            "/api/jobs",
            params={"status": "completed"},
            cookies=_cookies(session_id),
        )

        assert response.status_code == 200
        data = response.json()
        for job in data:
            assert job["status"] == "completed"

    async def test_list_jobs_unauthenticated_returns_401(self, client):
        response = await client.get("/api/jobs")
        assert response.status_code == 401


class TestGetJob:
    async def test_get_job(self, client, db_session):
        admin, session_id = await _create_authenticated_user(db_session, is_admin=True)

        account = Account(
            account_name="Get Job Test",
            account_email=f"gj-{id(db_session)}@example.com",
            organizational_unit="ou-1234",
            sso_user_email="sso@example.com",
            created_by=admin.id,
        )
        db_session.add(account)
        await db_session.flush()

        job = Job(
            account_id=account.id,
            job_type="provision_account",
            started_by=admin.id,
        )
        db_session.add(job)
        await db_session.flush()

        response = await client.get(f"/api/jobs/{job.id}", cookies=_cookies(session_id))

        assert response.status_code == 200
        data = response.json()
        assert data["job_type"] == "provision_account"
        assert data["account_id"] == str(account.id)

    async def test_get_job_non_admin_cannot_see_others_job(self, client, db_session):
        admin, _ = await _create_authenticated_user(db_session, is_admin=True)
        _, user_session = await _create_authenticated_user(db_session, is_admin=False)

        account = Account(
            account_name="Auth Test",
            account_email=f"auth-{id(db_session)}@example.com",
            organizational_unit="ou-1234",
            sso_user_email="sso@example.com",
            created_by=admin.id,
        )
        db_session.add(account)
        await db_session.flush()

        job = Job(
            account_id=account.id,
            job_type="provision_account",
            started_by=admin.id,
        )
        db_session.add(job)
        await db_session.flush()

        response = await client.get(f"/api/jobs/{job.id}", cookies=_cookies(user_session))

        assert response.status_code == 404

    async def test_get_job_not_found(self, client, db_session):
        _, session_id = await _create_authenticated_user(db_session, is_admin=True)
        fake_id = "00000000-0000-0000-0000-000000000000"

        response = await client.get(f"/api/jobs/{fake_id}", cookies=_cookies(session_id))

        assert response.status_code == 404


class TestCreateJob:
    async def test_create_sync_accounts_job(self, client, db_session):
        admin, session_id = await _create_authenticated_user(db_session, is_admin=True)

        with patch("backend.routers.jobs.execute_job", new_callable=AsyncMock):
            response = await client.post(
                "/api/jobs",
                json={"job_type": "sync_accounts"},
                cookies=_cookies(session_id),
            )

        assert response.status_code == 201
        data = response.json()
        assert data["job_type"] == "sync_accounts"
        assert data["status"] == "pending"
        assert data["account_id"] is None
        assert data["started_by"] == str(admin.id)

    async def test_create_job_unsupported_type_returns_400(self, client, db_session):
        _, session_id = await _create_authenticated_user(db_session, is_admin=True)

        response = await client.post(
            "/api/jobs",
            json={"job_type": "nonexistent_type"},
            cookies=_cookies(session_id),
        )

        assert response.status_code == 400

    async def test_create_job_non_admin_returns_403(self, client, db_session):
        _, user_session = await _create_authenticated_user(db_session, is_admin=False)

        response = await client.post(
            "/api/jobs",
            json={"job_type": "sync_accounts"},
            cookies=_cookies(user_session),
        )

        assert response.status_code == 403

    async def test_create_job_rejects_duplicate_pending_sync(self, client, db_session):
        admin, session_id = await _create_authenticated_user(db_session, is_admin=True)

        # Create an in-progress sync job
        db_session.add(
            Job(
                job_type="sync_accounts",
                status="in_progress",
                started_by=admin.id,
            )
        )
        await db_session.flush()

        response = await client.post(
            "/api/jobs",
            json={"job_type": "sync_accounts"},
            cookies=_cookies(session_id),
        )

        assert response.status_code == 409

    async def test_create_job_unauthenticated_returns_401(self, client):
        response = await client.post(
            "/api/jobs",
            json={"job_type": "sync_accounts"},
        )

        assert response.status_code == 401
