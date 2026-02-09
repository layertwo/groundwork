"""Unit tests for AuditLog model."""

from sqlalchemy import select

from backend.models import AuditLog


class TestAuditLogModel:
    async def test_create_audit_log(self, db_session):
        """Test creating an audit log entry."""
        entry = AuditLog(
            action="account.create",
            resource_type="account",
            resource_id="some-uuid",
            detail={"account_name": "dev-sandbox"},
            ip_address="127.0.0.1",
        )
        db_session.add(entry)
        await db_session.commit()

        result = await db_session.execute(
            select(AuditLog).where(AuditLog.action == "account.create")
        )
        saved = result.scalar_one()

        assert saved.id is not None
        assert isinstance(saved.id, int)
        assert saved.user_id is None
        assert saved.detail == {"account_name": "dev-sandbox"}

    async def test_audit_log_autoincrement(self, db_session):
        """Test audit log IDs are monotonically increasing."""
        e1 = AuditLog(action="first.action")
        e2 = AuditLog(action="second.action")
        db_session.add(e1)
        db_session.add(e2)
        await db_session.commit()

        result = await db_session.execute(
            select(AuditLog)
            .where(AuditLog.action.in_(["first.action", "second.action"]))
            .order_by(AuditLog.id)
        )
        entries = result.scalars().all()

        assert len(entries) == 2
        assert entries[0].id < entries[1].id
