import pytest
from pydantic import ValidationError

from backend.config import Settings


class TestManagementRoleConfig:
    def test_management_role_arn_default(self, monkeypatch):
        monkeypatch.delenv("GW_AWS_MANAGEMENT_ROLE_ARN", raising=False)
        s = Settings(session_secret="test", _env_file=None)
        assert s.aws_management_role_arn == ""


class TestStackSetConfig:
    def test_groundwork_account_id_default(self, monkeypatch):
        monkeypatch.delenv("GW_AWS_GROUNDWORK_ACCOUNT_ID", raising=False)
        s = Settings(session_secret="test", _env_file=None)
        assert s.aws_groundwork_account_id == ""

    def test_org_root_id_default(self, monkeypatch):
        monkeypatch.delenv("GW_AWS_ORG_ROOT_ID", raising=False)
        s = Settings(session_secret="test", _env_file=None)
        assert s.aws_org_root_id == ""

    def test_groundwork_account_id_rejects_invalid(self):
        with pytest.raises(ValidationError):
            Settings(session_secret="test", aws_groundwork_account_id="not-an-id")

    def test_org_root_id_rejects_invalid(self):
        with pytest.raises(ValidationError):
            Settings(session_secret="test", aws_org_root_id="invalid")
