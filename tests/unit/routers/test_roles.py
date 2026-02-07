"""Tests for roles router including role template CRUD."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from backend.dependencies.auth import SESSION_COOKIE, sign_session_id
from backend.models.role_template import RoleTemplate
from backend.models.user import Session, User


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def _create_authenticated_user(db_session, *, is_admin: bool = False):
    """Helper to create a user with a valid session, returns (user, session_id)."""
    user = User(
        sub=f"test-sub-{is_admin}-{id(db_session)}",
        email="admin@example.com" if is_admin else "user@example.com",
        display_name="Admin" if is_admin else "User",
        groups=["admins"] if is_admin else ["users"],
        is_admin=is_admin,
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
    return user, sign_session_id(str(session.id))


class TestRoleRouteStubs:
    async def test_list_roles_returns_501(self, client):
        response = await client.get("/api/roles")
        assert response.status_code == 501

    async def test_assume_role_returns_501(self, client):
        response = await client.post("/api/roles/assume")
        assert response.status_code == 501


class TestRoleTemplatesList:
    async def test_list_templates_returns_seeded_data(self, client, db_session):
        _, session_id = await _create_authenticated_user(db_session, is_admin=False)

        response = await client.get(
            "/api/roles/templates",
            cookies={SESSION_COOKIE: session_id},
        )

        assert response.status_code == 200
        data = response.json()
        names = [t["name"] for t in data]
        assert "Admin" in names
        assert "ReadOnly" in names
        assert "PowerUser" in names

    async def test_list_templates_unauthenticated_returns_401(self, client):
        response = await client.get("/api/roles/templates")
        assert response.status_code == 401


class TestRoleTemplatesCreate:
    async def test_create_template_as_admin(self, client, db_session):
        _, session_id = await _create_authenticated_user(db_session, is_admin=True)

        response = await client.post(
            "/api/roles/templates",
            json={
                "name": "CustomTemplate",
                "description": "A custom template",
                "managed_policy_arns": [
                    "arn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess"
                ],
            },
            cookies={SESSION_COOKIE: session_id},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "CustomTemplate"
        assert data["description"] == "A custom template"
        assert "AmazonS3ReadOnlyAccess" in data["managed_policy_arns"][0]

    async def test_create_template_non_admin_returns_403(self, client, db_session):
        _, session_id = await _create_authenticated_user(db_session, is_admin=False)

        response = await client.post(
            "/api/roles/templates",
            json={"name": "Blocked", "managed_policy_arns": []},
            cookies={SESSION_COOKIE: session_id},
        )

        assert response.status_code == 403

    async def test_create_template_unauthenticated_returns_401(self, client):
        response = await client.post(
            "/api/roles/templates",
            json={"name": "NoAuth", "managed_policy_arns": []},
        )

        assert response.status_code == 401

    async def test_create_template_invalid_arn_returns_422(self, client, db_session):
        _, session_id = await _create_authenticated_user(db_session, is_admin=True)

        response = await client.post(
            "/api/roles/templates",
            json={"name": "BadArn", "managed_policy_arns": ["not-a-valid-arn"]},
            cookies={SESSION_COOKIE: session_id},
        )

        assert response.status_code == 422

    async def test_create_duplicate_template_returns_409(self, client, db_session):
        _, session_id = await _create_authenticated_user(db_session, is_admin=True)

        response = await client.post(
            "/api/roles/templates",
            json={"name": "Admin", "managed_policy_arns": []},
            cookies={SESSION_COOKIE: session_id},
        )

        assert response.status_code == 409


class TestRoleTemplatesUpdate:
    async def test_update_template_as_admin(self, client, db_session):
        _, session_id = await _create_authenticated_user(db_session, is_admin=True)

        result = await db_session.execute(
            select(RoleTemplate).where(RoleTemplate.name == "ReadOnly")
        )
        template = result.scalar_one()

        response = await client.patch(
            f"/api/roles/templates/{template.id}",
            json={"description": "Updated description"},
            cookies={SESSION_COOKIE: session_id},
        )

        assert response.status_code == 200
        assert response.json()["description"] == "Updated description"

    async def test_update_nonexistent_template_returns_404(self, client, db_session):
        _, session_id = await _create_authenticated_user(db_session, is_admin=True)
        fake_id = "00000000-0000-0000-0000-000000000000"

        response = await client.patch(
            f"/api/roles/templates/{fake_id}",
            json={"description": "nope"},
            cookies={SESSION_COOKIE: session_id},
        )

        assert response.status_code == 404


class TestRoleTemplatesDelete:
    async def test_delete_template_as_admin(self, client, db_session):
        _, session_id = await _create_authenticated_user(db_session, is_admin=True)

        template = RoleTemplate(
            name="ToDelete",
            description="Will be deleted",
            managed_policy_arns=[],
        )
        db_session.add(template)
        await db_session.flush()

        response = await client.delete(
            f"/api/roles/templates/{template.id}",
            cookies={SESSION_COOKIE: session_id},
        )

        assert response.status_code == 204

    async def test_delete_nonexistent_template_returns_404(self, client, db_session):
        _, session_id = await _create_authenticated_user(db_session, is_admin=True)
        fake_id = "00000000-0000-0000-0000-000000000000"

        response = await client.delete(
            f"/api/roles/templates/{fake_id}",
            cookies={SESSION_COOKIE: session_id},
        )

        assert response.status_code == 404
