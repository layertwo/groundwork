"""Tests for AWS IAM role management functions."""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from backend.config import settings
from backend.services import aws
from tests.fixtures.aws import _stubbed_session, create_stubbed_client

OIDC_PROVIDER_ARN = "arn:aws:iam::123456789012:oidc-provider/idp.example.com"
OIDC_CLIENT_ID = "groundwork-client"
AWS_ACCOUNT_ID = "123456789012"
ROLE_NAME = "TestRole"


class TestBuildTrustPolicy:
    def test_groups_only(self):
        """Group access gates on aud only — AWS STS does not support :groups."""
        with patch.object(settings, "oidc_client_id", OIDC_CLIENT_ID):
            policy_str = aws._build_trust_policy(
                oidc_provider_arn=OIDC_PROVIDER_ARN,
                allowed_groups=["devs", "admins"],
                allowed_users=[],
            )

        policy = json.loads(policy_str)
        assert policy["Version"] == "2012-10-17"
        assert len(policy["Statement"]) == 1
        stmt = policy["Statement"][0]
        assert stmt["Sid"] == "AllowGroupAccess"
        assert stmt["Principal"]["Federated"] == OIDC_PROVIDER_ARN
        assert stmt["Action"] == "sts:AssumeRoleWithWebIdentity"
        assert stmt["Condition"]["StringEquals"]["idp.example.com:aud"] == OIDC_CLIENT_ID
        # No :groups condition — AWS STS ignores it for custom OIDC providers.
        # Group membership is enforced by Groundwork at the application layer.
        assert "ForAnyValue:StringEquals" not in stmt["Condition"]

    def test_users_only(self):
        with patch.object(settings, "oidc_client_id", OIDC_CLIENT_ID):
            policy_str = aws._build_trust_policy(
                oidc_provider_arn=OIDC_PROVIDER_ARN,
                allowed_groups=[],
                allowed_users=["user-1", "user-2"],
            )

        policy = json.loads(policy_str)
        assert len(policy["Statement"]) == 1
        stmt = policy["Statement"][0]
        assert stmt["Sid"] == "AllowUserAccess"
        assert stmt["Condition"]["StringEquals"]["idp.example.com:sub"] == ["user-1", "user-2"]

    def test_groups_and_users(self):
        with patch.object(settings, "oidc_client_id", OIDC_CLIENT_ID):
            policy_str = aws._build_trust_policy(
                oidc_provider_arn=OIDC_PROVIDER_ARN,
                allowed_groups=["devs"],
                allowed_users=["user-1"],
            )

        policy = json.loads(policy_str)
        assert len(policy["Statement"]) == 2
        sids = [s["Sid"] for s in policy["Statement"]]
        assert "AllowGroupAccess" in sids
        assert "AllowUserAccess" in sids

    def test_empty_groups_and_users(self):
        with patch.object(settings, "oidc_client_id", OIDC_CLIENT_ID):
            policy_str = aws._build_trust_policy(
                oidc_provider_arn=OIDC_PROVIDER_ARN,
                allowed_groups=[],
                allowed_users=[],
            )

        policy = json.loads(policy_str)
        assert len(policy["Statement"]) == 0


class TestAssumeGroundworkAdmin:
    async def test_returns_session_with_assumed_credentials(self):
        _, sts_stubber = await create_stubbed_client("sts")
        sts_stubber.add_response(
            "assume_role",
            {
                "Credentials": {
                    "AccessKeyId": "AKIAIOSFODNN7EXAMPLE",
                    "SecretAccessKey": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
                    "SessionToken": "FwoGZXIvYXdzEBYaDHqa0AP1",
                    "Expiration": datetime(2025, 1, 1),
                },
                "AssumedRoleUser": {
                    "AssumedRoleId": "AROAIOSFODNN7EXAMPLE:GroundworkRoleMgmt",
                    "Arn": (
                        f"arn:aws:sts::{AWS_ACCOUNT_ID}:assumed-role"
                        "/GroundworkAdmin-DO-NOT-DELETE/GroundworkRoleMgmt"
                    ),
                },
            },
            expected_params={
                "RoleArn": (f"arn:aws:iam::{AWS_ACCOUNT_ID}:role/GroundworkAdmin-DO-NOT-DELETE"),
                "RoleSessionName": "GroundworkRoleMgmt",
            },
        )
        sts_stubber.activate()

        gw_session = _stubbed_session({"sts": sts_stubber})

        with (
            patch.object(aws, "get_session", return_value=gw_session),
            patch("backend.services.aws.aioboto3") as mock_aioboto3,
        ):
            mock_target_session = MagicMock()
            mock_aioboto3.Session.return_value = mock_target_session

            result = await aws.assume_groundwork_admin(AWS_ACCOUNT_ID)
        assert result is mock_target_session
        mock_aioboto3.Session.assert_called_once_with(
            aws_access_key_id="AKIAIOSFODNN7EXAMPLE",
            aws_secret_access_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            aws_session_token="FwoGZXIvYXdzEBYaDHqa0AP1",
            region_name=settings.aws_region,
        )
        sts_stubber.assert_no_pending_responses()


class TestCreateIamRole:
    async def test_creates_role_with_policies(self):
        _, iam_stubber = await create_stubbed_client("iam")
        iam_stubber.add_response(
            "create_role",
            {
                "Role": {
                    "Path": "/",
                    "RoleName": ROLE_NAME,
                    "RoleId": "AROAIOSFODNN7EXAMPLE",
                    "Arn": f"arn:aws:iam::{AWS_ACCOUNT_ID}:role/{ROLE_NAME}",
                    "CreateDate": datetime(2025, 1, 1),
                    "AssumeRolePolicyDocument": "{}",
                }
            },
        )
        iam_stubber.add_response("attach_role_policy", {})
        iam_stubber.add_response("put_role_policy", {})
        iam_stubber.activate()

        target_session = _stubbed_session({"iam": iam_stubber})

        with (
            patch.object(aws, "assume_groundwork_admin", new_callable=AsyncMock) as mock_assume,
            patch.object(settings, "oidc_client_id", OIDC_CLIENT_ID),
        ):
            mock_assume.return_value = target_session

            role_arn = await aws.create_iam_role(
                aws_account_id=AWS_ACCOUNT_ID,
                role_name=ROLE_NAME,
                oidc_provider_arn=OIDC_PROVIDER_ARN,
                allowed_groups=["devs"],
                allowed_users=[],
                managed_policy_arns=["arn:aws:iam::aws:policy/ReadOnlyAccess"],
                inline_policy={"Version": "2012-10-17", "Statement": []},
                max_duration=3600,
            )

        assert role_arn == f"arn:aws:iam::{AWS_ACCOUNT_ID}:role/{ROLE_NAME}"
        mock_assume.assert_called_once_with(AWS_ACCOUNT_ID)
        iam_stubber.assert_no_pending_responses()


class TestDeleteIamRole:
    async def test_detaches_policies_and_deletes(self):
        _, iam_stubber = await create_stubbed_client("iam")
        # list_attached_role_policies
        iam_stubber.add_response(
            "list_attached_role_policies",
            {
                "AttachedPolicies": [
                    {
                        "PolicyName": "ReadOnlyAccess",
                        "PolicyArn": "arn:aws:iam::aws:policy/ReadOnlyAccess",
                    }
                ],
                "IsTruncated": False,
            },
        )
        # detach_role_policy
        iam_stubber.add_response("detach_role_policy", {})
        # list_role_policies (inline)
        iam_stubber.add_response(
            "list_role_policies",
            {"PolicyNames": ["GroundworkInlinePolicy"], "IsTruncated": False},
        )
        # delete_role_policy
        iam_stubber.add_response("delete_role_policy", {})
        # delete_role
        iam_stubber.add_response("delete_role", {})
        iam_stubber.activate()

        target_session = _stubbed_session({"iam": iam_stubber})

        with patch.object(aws, "assume_groundwork_admin", new_callable=AsyncMock) as mock_assume:
            mock_assume.return_value = target_session

            await aws.delete_iam_role(AWS_ACCOUNT_ID, ROLE_NAME)

        mock_assume.assert_called_once_with(AWS_ACCOUNT_ID)
        iam_stubber.assert_no_pending_responses()
