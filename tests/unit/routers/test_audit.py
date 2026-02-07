"""Unit tests for audit router stubs."""

import pytest


class TestAuditRoutes:
    async def test_list_audit_logs_returns_501(self, client):
        """Test list audit logs stub returns 501 Not Implemented."""
        response = await client.get("/api/audit")

        assert response.status_code == 501
        assert response.json() == {"detail": "Not implemented"}
