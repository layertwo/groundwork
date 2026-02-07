"""Tests for audit log schemas."""

from datetime import datetime, timezone
from uuid import uuid4

from backend.schemas.audit import AuditLogQuery, AuditLogResponse


class TestAuditLogResponse:
    def test_from_dict(self):
        data = {
            "id": 1,
            "user_id": uuid4(),
            "action": "auth.login",
            "resource_type": "session",
            "resource_id": "abc-123",
            "detail": {"key": "value"},
            "ip_address": "127.0.0.1",
            "user_agent": "test-agent",
            "created_at": datetime.now(timezone.utc),
        }
        resp = AuditLogResponse(**data)
        assert resp.id == 1
        assert resp.action == "auth.login"
        assert resp.detail == {"key": "value"}

    def test_optional_fields_none(self):
        resp = AuditLogResponse(
            id=2,
            user_id=None,
            action="system.startup",
            resource_type=None,
            resource_id=None,
            detail=None,
            ip_address=None,
            user_agent=None,
            created_at=datetime.now(timezone.utc),
        )
        assert resp.user_id is None
        assert resp.resource_type is None


class TestAuditLogQuery:
    def test_defaults(self):
        query = AuditLogQuery()
        assert query.page == 1
        assert query.page_size == 50
        assert query.resource_type is None
        assert query.action is None

    def test_with_filters(self):
        uid = uuid4()
        query = AuditLogQuery(
            resource_type="account",
            resource_id="abc",
            user_id=uid,
            action="account.create",
            page=2,
            page_size=25,
        )
        assert query.resource_type == "account"
        assert query.user_id == uid
        assert query.page == 2
