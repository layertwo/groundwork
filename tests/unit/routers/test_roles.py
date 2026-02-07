"""Tests for roles router including role CRUD and role template CRUD."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from sqlalchemy import select

from backend.dependencies.auth import SESSION_COOKIE, sign_session_id
from backend.models.account import Account
from backend.models.job import Job
from backend.models.role import Role
from backend.models.role_template import RoleTemplate
from backend.models.user import Session, User


async def _create_authenticated_user(db_session, *, is_admin: bool = False, groups=None, sub=None):
    """Helper to create a user with a valid session, returns (user, session_id)."""
    user = User(
        sub=sub or f"test-sub-{is_admin}-{id(db_session)}",
        email=f"role-{'admin' if is_admin else 'user'}-{id(db_session)}@example.com",
        display_name="Admin" if is_admin else "User",
        groups=groups if groups is not None else (["admins"] if is_admin else ["users"]),
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


async def _create_active_account(db_session, admin_user):
    """Helper to create an active account with an OIDC provider ARN."""
    account = Account(
        account_name="Test Account",
        account_email=f"acct-{id(db_session)}@example.com",
        organizational_unit="ou-1234",
        sso_user_email="sso@example.com",
        created_by=admin_user.id,
        status="active",
        aws_account_id="123456789012",
        oidc_provider_arn="arn:aws:iam::123456789012:oidc-provider/idp.example.com",
    )
    db_session.add(account)
    await db_session.flush()
    return account


# ---------------------------------------------------------------------------
# Role CRUD tests
# ---------------------------------------------------------------------------


class TestCreateRole:
    async def test_create_role_custom(self, client, db_session):
        admin, session_id = await _create_authenticated_user(db_session, is_admin=True)
        account = await _create_active_account(db_session, admin)

        with patch("backend.routers.roles.execute_job", new_callable=AsyncMock):
            response = await client.post(
                f"/api/accounts/{account.id}/roles",
                json={
                    "role_name": "CustomRole",
                    "managed_policy_arns": ["arn:aws:iam::aws:policy/ReadOnlyAccess"],
                    "inline_policy": {"Version": "2012-10-17", "Statement": []},
                    "allowed_groups": ["devs"],
                    "allowed_users": ["user-1"],
                    "description": "A custom role",
                },
                cookies=_cookies(session_id),
            )

        assert response.status_code == 201
        data = response.json()
        assert data["role_name"] == "CustomRole"
        assert data["allowed_groups"] == ["devs"]
        assert data["allowed_users"] == ["user-1"]
        assert data["managed_policy_arns"] == ["arn:aws:iam::aws:policy/ReadOnlyAccess"]
        assert data["inline_policy"] is not None
        assert data["description"] == "A custom role"
        assert data["role_arn"] == ""  # placeholder before job completes

    async def test_create_role_from_template(self, client, db_session):
        admin, session_id = await _create_authenticated_user(db_session, is_admin=True)
        account = await _create_active_account(db_session, admin)

        # Get the pre-seeded "ReadOnly" template
        result = await db_session.execute(
            select(RoleTemplate).where(RoleTemplate.name == "ReadOnly")
        )
        template = result.scalar_one()

        with patch("backend.routers.roles.execute_job", new_callable=AsyncMock):
            response = await client.post(
                f"/api/accounts/{account.id}/roles",
                json={
                    "role_name": "FromTemplate",
                    "template_id": str(template.id),
                    "allowed_groups": ["devs"],
                },
                cookies=_cookies(session_id),
            )

        assert response.status_code == 201
        data = response.json()
        assert data["role_name"] == "FromTemplate"
        # managed_policy_arns should come from the template
        assert data["managed_policy_arns"] == template.managed_policy_arns

    async def test_create_role_non_admin_returns_403(self, client, db_session):
        admin, _ = await _create_authenticated_user(db_session, is_admin=True)
        account = await _create_active_account(db_session, admin)
        _, user_session = await _create_authenticated_user(
            db_session, is_admin=False, sub="non-admin-sub"
        )

        response = await client.post(
            f"/api/accounts/{account.id}/roles",
            json={"role_name": "Blocked", "allowed_groups": ["devs"]},
            cookies=_cookies(user_session),
        )

        assert response.status_code == 403

    async def test_create_role_duplicate_name_returns_409(self, client, db_session):
        admin, session_id = await _create_authenticated_user(db_session, is_admin=True)
        account = await _create_active_account(db_session, admin)

        # Create first role directly in DB
        role = Role(
            account_id=account.id,
            role_name="DupeRole",
            role_arn="arn:aws:iam::123456789012:role/DupeRole",
            allowed_groups=["devs"],
        )
        db_session.add(role)
        await db_session.flush()

        response = await client.post(
            f"/api/accounts/{account.id}/roles",
            json={"role_name": "DupeRole", "allowed_groups": ["devs"]},
            cookies=_cookies(session_id),
        )

        assert response.status_code == 409

    async def test_create_role_on_inactive_account_returns_400(self, client, db_session):
        admin, session_id = await _create_authenticated_user(db_session, is_admin=True)

        account = Account(
            account_name="Inactive Account",
            account_email=f"inactive-{id(db_session)}@example.com",
            organizational_unit="ou-1234",
            sso_user_email="sso@example.com",
            created_by=admin.id,
            status="pending",
        )
        db_session.add(account)
        await db_session.flush()

        response = await client.post(
            f"/api/accounts/{account.id}/roles",
            json={"role_name": "NoGo", "allowed_groups": ["devs"]},
            cookies=_cookies(session_id),
        )

        assert response.status_code == 400

    async def test_create_role_empty_groups_and_users_returns_400(self, client, db_session):
        admin, session_id = await _create_authenticated_user(db_session, is_admin=True)
        account = await _create_active_account(db_session, admin)

        response = await client.post(
            f"/api/accounts/{account.id}/roles",
            json={"role_name": "NoAccess", "allowed_groups": [], "allowed_users": []},
            cookies=_cookies(session_id),
        )

        assert response.status_code == 400

    async def test_create_role_job_created(self, client, db_session):
        admin, session_id = await _create_authenticated_user(db_session, is_admin=True)
        account = await _create_active_account(db_session, admin)

        with patch("backend.routers.roles.execute_job", new_callable=AsyncMock):
            response = await client.post(
                f"/api/accounts/{account.id}/roles",
                json={"role_name": "JobTest", "allowed_groups": ["devs"]},
                cookies=_cookies(session_id),
            )

        assert response.status_code == 201
        role_id = response.json()["id"]

        result = await db_session.execute(select(Job).where(Job.job_type == "create_role"))
        job = result.scalar_one()
        assert job.result["role_id"] == role_id
        assert job.started_by == admin.id


class TestUpdateRole:
    async def test_update_role_description_no_job(self, client, db_session):
        admin, session_id = await _create_authenticated_user(db_session, is_admin=True)
        account = await _create_active_account(db_session, admin)

        role = Role(
            account_id=account.id,
            role_name="DescRole",
            role_arn="arn:aws:iam::123456789012:role/DescRole",
            allowed_groups=["devs"],
        )
        db_session.add(role)
        await db_session.flush()

        response = await client.patch(
            f"/api/accounts/{account.id}/roles/{role.id}",
            json={"description": "Updated description"},
            cookies=_cookies(session_id),
        )

        assert response.status_code == 200
        assert response.json()["description"] == "Updated description"

        # No job should be created for description-only update
        result = await db_session.execute(select(Job).where(Job.job_type == "update_role"))
        assert result.scalar_one_or_none() is None

    async def test_update_role_groups_creates_job(self, client, db_session):
        admin, session_id = await _create_authenticated_user(db_session, is_admin=True)
        account = await _create_active_account(db_session, admin)

        role = Role(
            account_id=account.id,
            role_name="GroupRole",
            role_arn="arn:aws:iam::123456789012:role/GroupRole",
            allowed_groups=["old-group"],
        )
        db_session.add(role)
        await db_session.flush()

        with patch("backend.routers.roles.execute_job", new_callable=AsyncMock):
            response = await client.patch(
                f"/api/accounts/{account.id}/roles/{role.id}",
                json={"allowed_groups": ["new-group"]},
                cookies=_cookies(session_id),
            )

        assert response.status_code == 200
        assert response.json()["allowed_groups"] == ["new-group"]

        result = await db_session.execute(select(Job).where(Job.job_type == "update_role"))
        job = result.scalar_one()
        assert "allowed_groups" in job.result["changes"]

    async def test_update_role_users_creates_job(self, client, db_session):
        admin, session_id = await _create_authenticated_user(db_session, is_admin=True)
        account = await _create_active_account(db_session, admin)

        role = Role(
            account_id=account.id,
            role_name="UserRole",
            role_arn="arn:aws:iam::123456789012:role/UserRole",
            allowed_groups=["devs"],
        )
        db_session.add(role)
        await db_session.flush()

        with patch("backend.routers.roles.execute_job", new_callable=AsyncMock):
            response = await client.patch(
                f"/api/accounts/{account.id}/roles/{role.id}",
                json={"allowed_users": ["user-abc"]},
                cookies=_cookies(session_id),
            )

        assert response.status_code == 200

        result = await db_session.execute(select(Job).where(Job.job_type == "update_role"))
        job = result.scalar_one()
        assert "allowed_users" in job.result["changes"]

    async def test_update_role_policy_creates_job(self, client, db_session):
        admin, session_id = await _create_authenticated_user(db_session, is_admin=True)
        account = await _create_active_account(db_session, admin)

        role = Role(
            account_id=account.id,
            role_name="PolicyRole",
            role_arn="arn:aws:iam::123456789012:role/PolicyRole",
            allowed_groups=["devs"],
        )
        db_session.add(role)
        await db_session.flush()

        with patch("backend.routers.roles.execute_job", new_callable=AsyncMock):
            response = await client.patch(
                f"/api/accounts/{account.id}/roles/{role.id}",
                json={"managed_policy_arns": ["arn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess"]},
                cookies=_cookies(session_id),
            )

        assert response.status_code == 200

        result = await db_session.execute(select(Job).where(Job.job_type == "update_role"))
        job = result.scalar_one()
        assert "managed_policy_arns" in job.result["changes"]


class TestDeleteRole:
    async def test_delete_role_creates_job(self, client, db_session):
        admin, session_id = await _create_authenticated_user(db_session, is_admin=True)
        account = await _create_active_account(db_session, admin)

        role = Role(
            account_id=account.id,
            role_name="DeleteMe",
            role_arn="arn:aws:iam::123456789012:role/DeleteMe",
            allowed_groups=["devs"],
        )
        db_session.add(role)
        await db_session.flush()

        with patch("backend.routers.roles.execute_job", new_callable=AsyncMock):
            response = await client.delete(
                f"/api/accounts/{account.id}/roles/{role.id}",
                cookies=_cookies(session_id),
            )

        assert response.status_code == 202

        result = await db_session.execute(select(Job).where(Job.job_type == "delete_role"))
        job = result.scalar_one()
        assert job.result["role_id"] == str(role.id)
        assert job.result["role_name"] == "DeleteMe"
        assert job.result["aws_account_id"] == "123456789012"


class TestListRoles:
    async def test_list_roles_filtered_by_groups(self, client, db_session):
        admin, _ = await _create_authenticated_user(db_session, is_admin=True)
        account = await _create_active_account(db_session, admin)

        # Role accessible to "devs" group
        role1 = Role(
            account_id=account.id,
            role_name="DevRole",
            role_arn="arn:aws:iam::123456789012:role/DevRole",
            allowed_groups=["devs"],
        )
        # Role accessible to "ops" group only
        role2 = Role(
            account_id=account.id,
            role_name="OpsRole",
            role_arn="arn:aws:iam::123456789012:role/OpsRole",
            allowed_groups=["ops"],
        )
        db_session.add_all([role1, role2])
        await db_session.flush()

        # Create user in "devs" group
        user, user_session = await _create_authenticated_user(
            db_session, is_admin=False, groups=["devs"], sub="devs-user"
        )

        response = await client.get("/api/roles", cookies=_cookies(user_session))

        assert response.status_code == 200
        data = response.json()
        names = [r["role_name"] for r in data]
        assert "DevRole" in names
        assert "OpsRole" not in names

    async def test_list_roles_filtered_by_users(self, client, db_session):
        admin, _ = await _create_authenticated_user(db_session, is_admin=True)
        account = await _create_active_account(db_session, admin)

        role = Role(
            account_id=account.id,
            role_name="UserSpecificRole",
            role_arn="arn:aws:iam::123456789012:role/UserSpecificRole",
            allowed_groups=[],
            allowed_users=["specific-user-sub"],
        )
        db_session.add(role)
        await db_session.flush()

        # User whose sub matches
        user, user_session = await _create_authenticated_user(
            db_session, is_admin=False, groups=[], sub="specific-user-sub"
        )

        response = await client.get("/api/roles", cookies=_cookies(user_session))

        assert response.status_code == 200
        data = response.json()
        names = [r["role_name"] for r in data]
        assert "UserSpecificRole" in names

    async def test_list_roles_admin_sees_all(self, client, db_session):
        admin, session_id = await _create_authenticated_user(
            db_session, is_admin=True, groups=[], sub="admin-list-test"
        )
        account = await _create_active_account(db_session, admin)

        role = Role(
            account_id=account.id,
            role_name="AdminVisible",
            role_arn="arn:aws:iam::123456789012:role/AdminVisible",
            allowed_groups=["secret-group"],
        )
        db_session.add(role)
        await db_session.flush()

        response = await client.get("/api/roles", cookies=_cookies(session_id))

        assert response.status_code == 200
        data = response.json()
        names = [r["role_name"] for r in data]
        assert "AdminVisible" in names


# ---------------------------------------------------------------------------
# Role template tests (carried over from Phase 1)
# ---------------------------------------------------------------------------


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
                "managed_policy_arns": ["arn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess"],
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
