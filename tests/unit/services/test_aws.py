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


class TestBootstrapAccountStackSet:
    async def test_bootstrap_polls_until_deployed(self):
        """bootstrap_account() polls get_stack_instance_status until deployed."""
        call_count = 0

        async def mock_get_status(account_id):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return {"deployed": False, "status": "OUTDATED", "detailed_status": "RUNNING"}
            return {"deployed": True, "status": "CURRENT", "detailed_status": "SUCCEEDED"}

        with (
            patch.object(aws, "ensure_bootstrap_stackset", new_callable=AsyncMock),
            patch.object(aws, "get_stack_instance_status", side_effect=mock_get_status),
            patch("backend.services.aws.asyncio.sleep", new_callable=AsyncMock),
            patch.object(settings, "oidc_issuer_url", "https://idp.example.com"),
            patch.object(settings, "admin_role_name", "GroundworkAdmin-DO-NOT-DELETE"),
        ):
            result = await aws.bootstrap_account("123456789012")

        assert result["oidc_provider_arn"] == (
            "arn:aws:iam::123456789012:oidc-provider/idp.example.com"
        )
        assert result["admin_role_arn"] == (
            "arn:aws:iam::123456789012:role/GroundworkAdmin-DO-NOT-DELETE"
        )
        assert call_count == 3

    async def test_bootstrap_triggers_deploy_when_not_found(self):
        """If stack instance is NOT_FOUND, triggers manual deploy then polls."""
        first_call = True

        async def mock_get_status(account_id):
            nonlocal first_call
            if first_call:
                first_call = False
                return {"deployed": False, "status": "NOT_FOUND", "detailed_status": "NOT_FOUND"}
            return {"deployed": True, "status": "CURRENT", "detailed_status": "SUCCEEDED"}

        with (
            patch.object(aws, "ensure_bootstrap_stackset", new_callable=AsyncMock),
            patch.object(aws, "get_stack_instance_status", side_effect=mock_get_status),
            patch.object(aws, "deploy_to_account", new_callable=AsyncMock) as mock_deploy,
            patch("backend.services.aws.asyncio.sleep", new_callable=AsyncMock),
            patch.object(settings, "oidc_issuer_url", "https://idp.example.com"),
            patch.object(settings, "admin_role_name", "GroundworkAdmin-DO-NOT-DELETE"),
        ):
            mock_deploy.return_value = "op-123"
            result = await aws.bootstrap_account("123456789012", ou_id="ou-abc1")

        mock_deploy.assert_called_once_with("123456789012", "ou-abc1")
        assert result["oidc_provider_arn"] is not None

    async def test_bootstrap_times_out(self):
        """Raises RuntimeError if stack never deploys within timeout."""

        async def mock_get_status(account_id):
            return {"deployed": False, "status": "OUTDATED", "detailed_status": "RUNNING"}

        with (
            patch.object(aws, "ensure_bootstrap_stackset", new_callable=AsyncMock),
            patch.object(aws, "get_stack_instance_status", side_effect=mock_get_status),
            patch("backend.services.aws.asyncio.sleep", new_callable=AsyncMock),
            patch.object(settings, "oidc_issuer_url", "https://idp.example.com"),
            patch.object(settings, "admin_role_name", "GroundworkAdmin-DO-NOT-DELETE"),
        ):
            with pytest.raises(RuntimeError, match="timed out"):
                await aws.bootstrap_account("123456789012")

    async def test_bootstrap_fails_on_stack_failure(self):
        """Raises RuntimeError if stack instance reports FAILED."""

        async def mock_get_status(account_id):
            return {"deployed": False, "status": "INOPERABLE", "detailed_status": "FAILED"}

        with (
            patch.object(aws, "ensure_bootstrap_stackset", new_callable=AsyncMock),
            patch.object(aws, "get_stack_instance_status", side_effect=mock_get_status),
            patch("backend.services.aws.asyncio.sleep", new_callable=AsyncMock),
            patch.object(settings, "oidc_issuer_url", "https://idp.example.com"),
            patch.object(settings, "admin_role_name", "GroundworkAdmin-DO-NOT-DELETE"),
        ):
            with pytest.raises(RuntimeError, match="failed"):
                await aws.bootstrap_account("123456789012")


class TestGetGroundworkSession:
    async def test_assumes_role_in_groundwork_account(self):
        _, sts_stubber = await create_stubbed_client("sts")
        sts_stubber.add_response(
            "assume_role",
            {
                "Credentials": {
                    "AccessKeyId": "AKIAIOSFODNN7EXAMPLE",
                    "SecretAccessKey": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
                    "SessionToken": "FwoGZXIvYXdzEBYaDHqa0AP1tokenEXAMPLE",
                    "Expiration": datetime(2025, 1, 1),
                },
                "AssumedRoleUser": {
                    "AssumedRoleId": "AROAEXAMPLE:GroundworkStackSet",
                    "Arn": "arn:aws:sts::222233334444:assumed-role/GroundworkStackSetRole/GroundworkStackSet",
                },
            },
            expected_params={
                "RoleArn": "arn:aws:iam::222233334444:role/GroundworkStackSetRole",
                "RoleSessionName": "GroundworkStackSet",
            },
        )
        sts_stubber.activate()

        with (
            patch.object(aws, "get_session", return_value=_stubbed_session({"sts": sts_stubber})),
            patch.object(settings, "aws_groundwork_account_id", "222233334444"),
            patch.object(settings, "aws_groundwork_role_name", "GroundworkStackSetRole"),
            patch("backend.services.aws.aioboto3") as mock_aioboto3,
        ):
            session = await aws.get_groundwork_session()

        assert session is not None
        mock_aioboto3.Session.assert_called_once()
        call_kwargs = mock_aioboto3.Session.call_args[1]
        assert call_kwargs["aws_access_key_id"] == "AKIAIOSFODNN7EXAMPLE"
        sts_stubber.assert_no_pending_responses()


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


class TestEnsureBootstrapStackset:
    async def test_creates_stackset_when_not_exists(self):
        """When the StackSet doesn't exist, create it and deploy to org root."""
        _, cfn_stubber = await create_stubbed_client("cloudformation")

        # describe_stack_set raises StackSetNotFoundException
        cfn_stubber.add_client_error(
            "describe_stack_set",
            service_error_code="StackSetNotFoundException",
            service_message="StackSet not found",
        )
        cfn_stubber.add_response("create_stack_set", {"StackSetId": "ss-123"})
        cfn_stubber.add_response("create_stack_instances", {"OperationId": "op-abc"})
        cfn_stubber.activate()

        mock_gw_session = _stubbed_session({"cloudformation": cfn_stubber})

        with (
            patch.object(aws, "get_groundwork_session", new_callable=AsyncMock) as mock_gw,
            patch.object(aws, "get_oidc_thumbprint", new_callable=AsyncMock) as mock_thumb,
            patch.object(settings, "oidc_issuer_url", "https://idp.example.com"),
            patch.object(settings, "oidc_client_id", "gw-client"),
            patch.object(settings, "aws_groundwork_account_id", "222233334444"),
            patch.object(settings, "admin_role_name", "GroundworkAdmin-DO-NOT-DELETE"),
            patch.object(settings, "aws_region", "us-east-1"),
            patch.object(settings, "aws_org_root_id", "r-abc1"),
        ):
            mock_gw.return_value = mock_gw_session
            mock_thumb.return_value = "a" * 40

            await aws.ensure_bootstrap_stackset()

        cfn_stubber.assert_no_pending_responses()

    async def test_noop_when_stackset_exists(self):
        """When the StackSet already exists, do nothing."""
        _, cfn_stubber = await create_stubbed_client("cloudformation")
        cfn_stubber.add_response(
            "describe_stack_set",
            {
                "StackSet": {
                    "StackSetName": "groundwork-bootstrap",
                    "StackSetId": "ss-123",
                    "Status": "ACTIVE",
                }
            },
        )
        cfn_stubber.activate()

        mock_gw_session = _stubbed_session({"cloudformation": cfn_stubber})

        with (patch.object(aws, "get_groundwork_session", new_callable=AsyncMock) as mock_gw,):
            mock_gw.return_value = mock_gw_session
            await aws.ensure_bootstrap_stackset()

        cfn_stubber.assert_no_pending_responses()


class TestGetStackInstanceStatus:
    async def test_returns_succeeded_when_current(self):
        _, cfn_stubber = await create_stubbed_client("cloudformation")
        cfn_stubber.add_response(
            "describe_stack_instance",
            {
                "StackInstance": {
                    "StackSetId": "ss-123",
                    "Account": "123456789012",
                    "Region": "us-east-1",
                    "Status": "CURRENT",
                    "StackInstanceStatus": {"DetailedStatus": "SUCCEEDED"},
                }
            },
        )
        cfn_stubber.activate()
        mock_gw_session = _stubbed_session({"cloudformation": cfn_stubber})

        with (
            patch.object(aws, "get_groundwork_session", new_callable=AsyncMock) as mock_gw,
            patch.object(settings, "aws_region", "us-east-1"),
        ):
            mock_gw.return_value = mock_gw_session
            result = await aws.get_stack_instance_status("123456789012")

        assert result["status"] == "CURRENT"
        assert result["detailed_status"] == "SUCCEEDED"
        assert result["deployed"] is True

    async def test_returns_not_found_when_instance_missing(self):
        _, cfn_stubber = await create_stubbed_client("cloudformation")
        cfn_stubber.add_client_error(
            "describe_stack_instance",
            service_error_code="StackInstanceNotFoundException",
            service_message="Instance not found",
        )
        cfn_stubber.activate()
        mock_gw_session = _stubbed_session({"cloudformation": cfn_stubber})

        with (
            patch.object(aws, "get_groundwork_session", new_callable=AsyncMock) as mock_gw,
            patch.object(settings, "aws_region", "us-east-1"),
        ):
            mock_gw.return_value = mock_gw_session
            result = await aws.get_stack_instance_status("123456789012")

        assert result["deployed"] is False
        assert result["status"] == "NOT_FOUND"

    async def test_returns_pending_when_running(self):
        _, cfn_stubber = await create_stubbed_client("cloudformation")
        cfn_stubber.add_response(
            "describe_stack_instance",
            {
                "StackInstance": {
                    "StackSetId": "ss-123",
                    "Account": "123456789012",
                    "Region": "us-east-1",
                    "Status": "OUTDATED",
                    "StackInstanceStatus": {"DetailedStatus": "RUNNING"},
                }
            },
        )
        cfn_stubber.activate()
        mock_gw_session = _stubbed_session({"cloudformation": cfn_stubber})

        with (
            patch.object(aws, "get_groundwork_session", new_callable=AsyncMock) as mock_gw,
            patch.object(settings, "aws_region", "us-east-1"),
        ):
            mock_gw.return_value = mock_gw_session
            result = await aws.get_stack_instance_status("123456789012")

        assert result["deployed"] is False
        assert result["detailed_status"] == "RUNNING"


class TestDeployToAccount:
    async def test_creates_stack_instance_for_account(self):
        _, cfn_stubber = await create_stubbed_client("cloudformation")
        cfn_stubber.add_response(
            "create_stack_instances",
            {"OperationId": "op-manual-123"},
        )
        cfn_stubber.activate()
        mock_gw_session = _stubbed_session({"cloudformation": cfn_stubber})

        with (
            patch.object(aws, "get_groundwork_session", new_callable=AsyncMock) as mock_gw,
            patch.object(settings, "aws_region", "us-east-1"),
        ):
            mock_gw.return_value = mock_gw_session
            op_id = await aws.deploy_to_account("123456789012", "ou-abc1-12345678")

        assert op_id == "op-manual-123"
        cfn_stubber.assert_no_pending_responses()


class TestAssumeGroundworkAdminViaGW:
    async def test_chains_through_groundwork_account(self):
        """assume_groundwork_admin uses get_groundwork_session as base."""
        _, sts_stubber = await create_stubbed_client("sts")
        sts_stubber.add_response(
            "assume_role",
            {
                "Credentials": {
                    "AccessKeyId": "AKIATARGETEXAMPLE1",
                    "SecretAccessKey": "secretTARGETkey1234567890example",
                    "SessionToken": "tokenTARGET1234567890",
                    "Expiration": datetime(2025, 1, 1),
                },
                "AssumedRoleUser": {
                    "AssumedRoleId": "AROATARGET:GroundworkRoleMgmt",
                    "Arn": "arn:aws:sts::123456789012:assumed-role/GroundworkAdmin/GroundworkRoleMgmt",
                },
            },
            expected_params={
                "RoleArn": "arn:aws:iam::123456789012:role/GroundworkAdmin-DO-NOT-DELETE",
                "RoleSessionName": "GroundworkRoleMgmt",
            },
        )
        sts_stubber.activate()

        gw_session = _stubbed_session({"sts": sts_stubber})

        with (
            patch.object(aws, "get_groundwork_session", new_callable=AsyncMock) as mock_gw,
            patch("backend.services.aws.aioboto3") as mock_aioboto3,
            patch.object(settings, "admin_role_name", "GroundworkAdmin-DO-NOT-DELETE"),
        ):
            mock_gw.return_value = gw_session
            await aws.assume_groundwork_admin("123456789012")

        mock_gw.assert_called_once()
        mock_aioboto3.Session.assert_called_once()
        call_kwargs = mock_aioboto3.Session.call_args[1]
        assert call_kwargs["aws_access_key_id"] == "AKIATARGETEXAMPLE1"
        sts_stubber.assert_no_pending_responses()
