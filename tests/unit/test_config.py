from backend.config import Settings


class TestStackSetConfig:
    def test_groundwork_account_id_default(self):
        s = Settings(session_secret="test")
        assert s.aws_groundwork_account_id == ""

    def test_groundwork_role_name_default(self):
        s = Settings(session_secret="test")
        assert s.aws_groundwork_role_name == "GroundworkStackSetRole"

    def test_org_root_id_default(self):
        s = Settings(session_secret="test")
        assert s.aws_org_root_id == ""
