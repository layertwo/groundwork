import pytest
from pydantic import ValidationError

from backend.config import Settings


class TestStackSetConfig:
    def test_groundwork_account_id_default(self):
        s = Settings(session_secret="test")
        assert s.aws_groundwork_account_id == ""

    def test_org_root_id_default(self):
        s = Settings(session_secret="test")
        assert s.aws_org_root_id == ""

    def test_groundwork_account_id_rejects_invalid(self):
        with pytest.raises(ValidationError):
            Settings(session_secret="test", aws_groundwork_account_id="not-an-id")

    def test_org_root_id_rejects_invalid(self):
        with pytest.raises(ValidationError):
            Settings(session_secret="test", aws_org_root_id="invalid")
