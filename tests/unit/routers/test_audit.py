"""Tests for the audit log router."""

from datetime import datetime, timedelta, timezone

from backend.dependencies.auth import SESSION_COOKIE, sign_session_id
from backend.models.audit import AuditLog
from backend.models.user import Session, User


async def _create_authenticated_user(db_session, *, is_admin: bool = False):
    """Create a user with a valid session, returns (user, signed_cookie)."""
    user = User(
        sub=f"audit-test-{is_admin}-{id(db_session)}",
        email=f"audit-{'admin' if is_admin else 'user'}-{id(db_session)}@example.com",
        display_name="Audit Admin" if is_admin else "Audit User",
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


async def _add_logs(db_session, user: User):
    # audit_log.created_at is TIMESTAMP WITHOUT TIME ZONE, so asyncpg needs naive UTC
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    db_session.add_all(
        [
            AuditLog(
                user_id=user.id,
                action="account.create",
                resource_type="account",
                resource_id="acct-1",
                created_at=now - timedelta(minutes=2),
            ),
            AuditLog(
                user_id=user.id,
                action="role.create",
                resource_type="role",
                resource_id="role-1",
                created_at=now - timedelta(minutes=1),
            ),
            AuditLog(
                user_id=None,
                action="role.assume",
                resource_type="role",
                resource_id="role-2",
                created_at=now,
            ),
        ]
    )
    await db_session.flush()


class TestListAuditLogs:
    async def test_non_admin_returns_403(self, client, db_session):
        _, session_id = await _create_authenticated_user(db_session)

        response = await client.get("/api/audit", cookies=_cookies(session_id))

        assert response.status_code == 403

    async def test_returns_paginated_logs_newest_first(self, client, db_session):
        admin, session_id = await _create_authenticated_user(db_session, is_admin=True)
        await _add_logs(db_session, admin)

        response = await client.get("/api/audit", cookies=_cookies(session_id))

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3
        assert data["page"] == 1
        assert data["page_size"] == 50
        assert [item["action"] for item in data["items"]] == [
            "role.assume",
            "role.create",
            "account.create",
        ]

    async def test_includes_actor_display_name(self, client, db_session):
        admin, session_id = await _create_authenticated_user(db_session, is_admin=True)
        await _add_logs(db_session, admin)

        response = await client.get("/api/audit", cookies=_cookies(session_id))

        items = {item["action"]: item for item in response.json()["items"]}
        assert items["role.create"]["user"]["display_name"] == "Audit Admin"
        assert items["role.assume"]["user"] is None

    async def test_filters_by_resource_type(self, client, db_session):
        admin, session_id = await _create_authenticated_user(db_session, is_admin=True)
        await _add_logs(db_session, admin)

        response = await client.get(
            "/api/audit", params={"resource_type": "role"}, cookies=_cookies(session_id)
        )

        data = response.json()
        assert data["total"] == 2
        assert {item["action"] for item in data["items"]} == {"role.create", "role.assume"}

    async def test_filters_by_action_substring(self, client, db_session):
        admin, session_id = await _create_authenticated_user(db_session, is_admin=True)
        await _add_logs(db_session, admin)

        response = await client.get(
            "/api/audit", params={"action": "account"}, cookies=_cookies(session_id)
        )

        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["action"] == "account.create"

    async def test_pagination(self, client, db_session):
        admin, session_id = await _create_authenticated_user(db_session, is_admin=True)
        await _add_logs(db_session, admin)

        response = await client.get(
            "/api/audit",
            params={"page": 2, "page_size": 1},
            cookies=_cookies(session_id),
        )

        data = response.json()
        assert data["total"] == 3
        assert data["page"] == 2
        assert [item["action"] for item in data["items"]] == ["role.create"]

    async def test_action_filter_escapes_like_metacharacters(self, client, db_session):
        admin, session_id = await _create_authenticated_user(db_session, is_admin=True)
        await _add_logs(db_session, admin)

        # "%" must not act as a wildcard; a trailing "\" must not break the LIKE pattern
        for value in ("%", "\\"):
            response = await client.get(
                "/api/audit", params={"action": value}, cookies=_cookies(session_id)
            )
            assert response.status_code == 200
            assert response.json()["total"] == 0

    async def test_rejects_page_overflow(self, client, db_session):
        _, session_id = await _create_authenticated_user(db_session, is_admin=True)

        response = await client.get(
            "/api/audit", params={"page": 10**19}, cookies=_cookies(session_id)
        )

        assert response.status_code == 422

    async def test_sets_no_store_cache_header(self, client, db_session):
        _, session_id = await _create_authenticated_user(db_session, is_admin=True)

        response = await client.get("/api/audit", cookies=_cookies(session_id))

        assert response.headers["cache-control"] == "no-store"

    async def test_rejects_invalid_page_size(self, client, db_session):
        _, session_id = await _create_authenticated_user(db_session, is_admin=True)

        response = await client.get(
            "/api/audit", params={"page_size": 0}, cookies=_cookies(session_id)
        )

        assert response.status_code == 422
