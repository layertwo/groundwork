"""Tests for role schemas."""

from datetime import datetime, timezone
from uuid import uuid4

from backend.schemas.federate import AssumeRoleResponse
from backend.schemas.generated.models import RoleResponse


class TestRoleResponse:
    def test_from_dict(self):
        now = datetime.now(timezone.utc)
        resp = RoleResponse.model_validate(
            {
                "id": str(uuid4()),
                "account_id": str(uuid4()),
                "role_name": "AdminRole",
                "role_arn": "arn:aws:iam::123456789012:role/AdminRole",
                "status": "active",
                "error_message": None,
                "allowed_groups": ["admins"],
                "managed_policy_arns": ["arn:aws:iam::aws:policy/ReadOnlyAccess"],
                "inline_policy": {"Version": "2012-10-17", "Statement": []},
                "allowed_users": ["user@example.com"],
                "api_session_duration": 3600,
                "console_session_duration": 7200,
                "description": "Admin role",
                "created_at": now,
                "updated_at": now,
            }
        )
        dumped = resp.model_dump()
        assert dumped["role_name"] == "AdminRole"
        assert dumped["allowed_groups"] == ["admins"]
        assert dumped["api_session_duration"] == 3600

    def test_optional_fields(self):
        now = datetime.now(timezone.utc)
        resp = RoleResponse.model_validate(
            {
                "id": str(uuid4()),
                "account_id": str(uuid4()),
                "role_name": "BasicRole",
                "role_arn": "arn:aws:iam::123456789012:role/BasicRole",
                "status": "pending",
                "error_message": None,
                "allowed_groups": [],
                "managed_policy_arns": [],
                "inline_policy": None,
                "allowed_users": [],
                "api_session_duration": 900,
                "console_session_duration": 900,
                "description": None,
                "created_at": now,
                "updated_at": now,
            }
        )
        assert resp.inline_policy is None
        assert resp.description is None


class TestAssumeRoleResponse:
    def test_create(self):
        resp = AssumeRoleResponse(
            access_key_id="AKIAIOSFODNN7EXAMPLE",
            secret_access_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            session_token="FwoGZXIvYXdzEBY...",
            expiration=datetime.now(timezone.utc),
        )
        assert resp.access_key_id == "AKIAIOSFODNN7EXAMPLE"
        assert resp.session_token.startswith("FwoG")
