"""Tests for AWS service layer using aiobotocore AioStubber."""

import json
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from backend.config import settings
from backend.services import aws
from tests.fixtures.aws import _stubbed_session, create_stubbed_client

OIDC_ISSUER = "https://idp.example.com"
OIDC_CLIENT_ID = "groundwork-client"
MGMT_ACCOUNT_ID = "999888777666"


class TestCreateAccount:
    async def test_create_account_returns_request_id(self):
        _, stubber = await create_stubbed_client("organizations")
        stubber.add_response(
            "create_account",
            {"CreateAccountStatus": {"Id": "car-abc123", "State": "IN_PROGRESS"}},
            expected_params={"Email": "test@example.com", "AccountName": "TestAccount"},
        )
        stubber.activate()

        with patch.object(
            aws, "get_session", return_value=_stubbed_session({"organizations": stubber})
        ):
            result = await aws.create_account("TestAccount", "test@example.com")

        assert result == "car-abc123"
        stubber.assert_no_pending_responses()


class TestPollAccountCreation:
    async def test_poll_succeeded(self):
        _, stubber = await create_stubbed_client("organizations")
        stubber.add_response(
            "describe_create_account_status",
            {
                "CreateAccountStatus": {
                    "Id": "car-abc123",
                    "State": "SUCCEEDED",
                    "AccountId": "123456789012",
                }
            },
            expected_params={"CreateAccountRequestId": "car-abc123"},
        )
        stubber.activate()

        with patch.object(
            aws, "get_session", return_value=_stubbed_session({"organizations": stubber})
        ):
            result = await aws.poll_account_creation("car-abc123")

        assert result["status"] == "SUCCEEDED"
        assert result["aws_account_id"] == "123456789012"
        stubber.assert_no_pending_responses()

    async def test_poll_in_progress(self):
        _, stubber = await create_stubbed_client("organizations")
        stubber.add_response(
            "describe_create_account_status",
            {"CreateAccountStatus": {"Id": "car-abc123", "State": "IN_PROGRESS"}},
            expected_params={"CreateAccountRequestId": "car-abc123"},
        )
        stubber.activate()

        with patch.object(
            aws, "get_session", return_value=_stubbed_session({"organizations": stubber})
        ):
            result = await aws.poll_account_creation("car-abc123")

        assert result["status"] == "IN_PROGRESS"
        stubber.assert_no_pending_responses()

    async def test_poll_failed(self):
        _, stubber = await create_stubbed_client("organizations")
        stubber.add_response(
            "describe_create_account_status",
            {
                "CreateAccountStatus": {
                    "Id": "car-abc123",
                    "State": "FAILED",
                    "FailureReason": "EMAIL_ALREADY_EXISTS",
                }
            },
            expected_params={"CreateAccountRequestId": "car-abc123"},
        )
        stubber.activate()

        with patch.object(
            aws, "get_session", return_value=_stubbed_session({"organizations": stubber})
        ):
            result = await aws.poll_account_creation("car-abc123")

        assert result["status"] == "FAILED"
        assert result["error"] == "EMAIL_ALREADY_EXISTS"
        stubber.assert_no_pending_responses()


class TestMoveAccountToOu:
    async def test_move_account_to_ou(self):
        _, stubber = await create_stubbed_client("organizations")
        stubber.add_response(
            "list_roots",
            {
                "Roots": [
                    {
                        "Id": "r-abc1",
                        "Name": "Root",
                        "Arn": "arn:aws:organizations::123:root/o-abc/r-abc1",
                        "PolicyTypes": [],
                    }
                ]
            },
        )
        stubber.add_response(
            "move_account",
            {},
            expected_params={
                "AccountId": "123456789012",
                "SourceParentId": "r-abc1",
                "DestinationParentId": "ou-abc1-12345678",
            },
        )
        stubber.activate()

        with patch.object(
            aws, "get_session", return_value=_stubbed_session({"organizations": stubber})
        ):
            await aws.move_account_to_ou("123456789012", "ou-abc1-12345678")

        stubber.assert_no_pending_responses()

    async def test_move_account_no_roots_raises(self):
        _, stubber = await create_stubbed_client("organizations")
        stubber.add_response("list_roots", {"Roots": []})
        stubber.activate()

        with patch.object(
            aws, "get_session", return_value=_stubbed_session({"organizations": stubber})
        ):
            with pytest.raises(RuntimeError, match="No organization root found"):
                await aws.move_account_to_ou("123456789012", "ou-abc1-12345678")


class TestBootstrapAccount:
    async def test_bootstrap_creates_oidc_and_role(self):
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
                    "AssumedRoleId": "AROAIOSFODNN7EXAMPLE:GroundworkBootstrap",
                    "Arn": (
                        "arn:aws:sts::123456789012:assumed-role"
                        "/OrganizationAccountAccessRole/GroundworkBootstrap"
                    ),
                },
            },
            expected_params={
                "RoleArn": ("arn:aws:iam::123456789012:role/OrganizationAccountAccessRole"),
                "RoleSessionName": "GroundworkBootstrap",
            },
        )
        sts_stubber.activate()

        _, iam_stubber = await create_stubbed_client("iam")
        iam_stubber.add_response(
            "create_open_id_connect_provider",
            {"OpenIDConnectProviderArn": ("arn:aws:iam::123456789012:oidc-provider/example.com")},
        )
        iam_stubber.add_response(
            "create_role",
            {
                "Role": {
                    "Path": "/",
                    "RoleName": "GroundworkAdmin-DO-NOT-DELETE",
                    "RoleId": "AROAIOSFODNN7EXAMPLE",
                    "Arn": ("arn:aws:iam::123456789012:role/GroundworkAdmin-DO-NOT-DELETE"),
                    "CreateDate": datetime(2025, 1, 1),
                    "AssumeRolePolicyDocument": "{}",
                }
            },
        )
        iam_stubber.add_response("attach_role_policy", {})
        iam_stubber.activate()

        mgmt_session = _stubbed_session({"sts": sts_stubber})
        target_session = _stubbed_session({"iam": iam_stubber})

        with (
            patch.object(aws, "get_session", return_value=mgmt_session),
            patch.object(aws, "get_oidc_thumbprint", new_callable=AsyncMock) as mock_thumb,
            patch("backend.services.aws.aioboto3") as mock_aioboto3,
            patch.object(settings, "oidc_issuer_url", OIDC_ISSUER),
            patch.object(settings, "oidc_client_id", OIDC_CLIENT_ID),
            patch.object(settings, "aws_management_account_id", MGMT_ACCOUNT_ID),
        ):
            mock_thumb.return_value = "abcdef1234567890abcdef1234567890abcdef12"
            mock_aioboto3.Session.return_value = target_session

            result = await aws.bootstrap_account("123456789012")

        assert result["oidc_provider_arn"] == "arn:aws:iam::123456789012:oidc-provider/example.com"
        assert (
            result["admin_role_arn"]
            == "arn:aws:iam::123456789012:role/GroundworkAdmin-DO-NOT-DELETE"
        )
        sts_stubber.assert_no_pending_responses()
        iam_stubber.assert_no_pending_responses()


class TestBuildBootstrapTemplate:
    def test_template_has_required_resources(self):
        body = aws._build_bootstrap_template(
            oidc_issuer_url="https://idp.example.com",
            oidc_client_id="gw-client",
            oidc_thumbprint="a" * 40,
            groundwork_account_id="222233334444",
            admin_role_name="GroundworkAdmin-DO-NOT-DELETE",
        )
        parsed = json.loads(body)
        assert parsed["AWSTemplateFormatVersion"] == "2010-09-09"
        assert "OidcProvider" in parsed["Resources"]
        assert "AdminRole" in parsed["Resources"]

    def test_oidc_provider_config(self):
        body = aws._build_bootstrap_template(
            oidc_issuer_url="https://idp.example.com",
            oidc_client_id="gw-client",
            oidc_thumbprint="a" * 40,
            groundwork_account_id="222233334444",
            admin_role_name="GroundworkAdmin-DO-NOT-DELETE",
        )
        parsed = json.loads(body)
        oidc = parsed["Resources"]["OidcProvider"]["Properties"]
        assert oidc["Url"] == "https://idp.example.com"
        assert oidc["ClientIdList"] == ["gw-client"]
        assert oidc["ThumbprintList"] == ["a" * 40]

    def test_admin_role_trusts_groundwork_account(self):
        body = aws._build_bootstrap_template(
            oidc_issuer_url="https://idp.example.com",
            oidc_client_id="gw-client",
            oidc_thumbprint="a" * 40,
            groundwork_account_id="222233334444",
            admin_role_name="GroundworkAdmin-DO-NOT-DELETE",
        )
        parsed = json.loads(body)
        role = parsed["Resources"]["AdminRole"]["Properties"]
        assert role["RoleName"] == "GroundworkAdmin-DO-NOT-DELETE"
        assert role["MaxSessionDuration"] == 3600
        trust = role["AssumeRolePolicyDocument"]
        assert trust["Statement"][0]["Principal"]["AWS"] == "arn:aws:iam::222233334444:root"
        assert trust["Statement"][0]["Action"] == "sts:AssumeRole"
        assert "arn:aws:iam::aws:policy/AdministratorAccess" in role["ManagedPolicyArns"]

    def test_template_has_outputs(self):
        body = aws._build_bootstrap_template(
            oidc_issuer_url="https://idp.example.com",
            oidc_client_id="gw-client",
            oidc_thumbprint="a" * 40,
            groundwork_account_id="222233334444",
            admin_role_name="GroundworkAdmin-DO-NOT-DELETE",
        )
        parsed = json.loads(body)
        assert "OidcProviderArn" in parsed["Outputs"]
        assert "AdminRoleArn" in parsed["Outputs"]
