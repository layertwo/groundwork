"""Tests for role template schema validation edge cases."""

import pytest
from pydantic import ValidationError

from backend.schemas.role_template import RoleTemplateUpdate


class TestRoleTemplateUpdate:
    def test_validate_arns_none_passes(self):
        update = RoleTemplateUpdate(managed_policy_arns=None)
        assert update.managed_policy_arns is None

    def test_validate_arns_invalid_raises(self):
        with pytest.raises(ValidationError, match="Invalid IAM policy ARN"):
            RoleTemplateUpdate(managed_policy_arns=["not-an-arn"])

    def test_validate_arns_valid(self):
        arns = ["arn:aws:iam::123456789012:policy/MyPolicy"]
        update = RoleTemplateUpdate(managed_policy_arns=arns)
        assert update.managed_policy_arns == arns
