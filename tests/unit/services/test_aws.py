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


class TestGetManagementSession:
    async def test_assumes_role_with_configured_arn(self):
        _, sts_stubber = await create_stubbed_client("sts")
        sts_stubber.add_response(
            "assume_role",
            {
                "Credentials": {
                    "AccessKeyId": "AKIAMGMTEXAMPLE1234",
                    "SecretAccessKey": "secretMGMTkey1234567890example",
                    "SessionToken": "tokenMGMT1234567890session",
                    "Expiration": datetime(2025, 1, 1),
                },
                "AssumedRoleUser": {
                    "AssumedRoleId": "AROAMGMT:GroundworkOrganizations",
                    "Arn": "arn:aws:sts::111122223333:assumed-role/GroundworkManagementRole/GroundworkOrganizations",
                },
            },
            expected_params={
                "RoleArn": "arn:aws:iam::111122223333:role/GroundworkManagementRole",
                "RoleSessionName": "GroundworkOrganizations",
            },
        )
        sts_stubber.activate()

        with (
            patch.object(aws, "get_session", return_value=_stubbed_session({"sts": sts_stubber})),
            patch.object(
                settings,
                "aws_management_role_arn",
                "arn:aws:iam::111122223333:role/GroundworkManagementRole",
            ),
            patch("backend.services.aws.aioboto3") as mock_aioboto3,
        ):
            session = await aws.get_management_session()

        assert session is not None
        mock_aioboto3.Session.assert_called_once()
        call_kwargs = mock_aioboto3.Session.call_args[1]
        assert call_kwargs["aws_access_key_id"] == "AKIAMGMTEXAMPLE1234"
        sts_stubber.assert_no_pending_responses()


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
            aws,
            "get_management_session",
            new_callable=AsyncMock,
            return_value=_stubbed_session({"organizations": stubber}),
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
            aws,
            "get_management_session",
            new_callable=AsyncMock,
            return_value=_stubbed_session({"organizations": stubber}),
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
            aws,
            "get_management_session",
            new_callable=AsyncMock,
            return_value=_stubbed_session({"organizations": stubber}),
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
            aws,
            "get_management_session",
            new_callable=AsyncMock,
            return_value=_stubbed_session({"organizations": stubber}),
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
            aws,
            "get_management_session",
            new_callable=AsyncMock,
            return_value=_stubbed_session({"organizations": stubber}),
        ):
            await aws.move_account_to_ou("123456789012", "ou-abc1-12345678")

        stubber.assert_no_pending_responses()

    async def test_move_account_no_roots_raises(self):
        _, stubber = await create_stubbed_client("organizations")
        stubber.add_response("list_roots", {"Roots": []})
        stubber.activate()

        with patch.object(
            aws,
            "get_management_session",
            new_callable=AsyncMock,
            return_value=_stubbed_session({"organizations": stubber}),
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
        template_body = aws._build_bootstrap_template(
            oidc_issuer_url="https://idp.example.com",
            oidc_client_id="gw-client",
            oidc_thumbprint="a" * 40,
            groundwork_account_id="222233334444",
            admin_role_name="GroundworkAdmin-DO-NOT-DELETE",
        )

        _, cfn_stubber = await create_stubbed_client("cloudformation")

        # describe_stack_set raises StackSetNotFoundException
        cfn_stubber.add_client_error(
            "describe_stack_set",
            service_error_code="StackSetNotFoundException",
            service_message="StackSet not found",
            expected_params={
                "StackSetName": "groundwork-bootstrap",
                "CallAs": "DELEGATED_ADMIN",
            },
        )
        cfn_stubber.add_response(
            "create_stack_set",
            {"StackSetId": "ss-123"},
            expected_params={
                "StackSetName": "groundwork-bootstrap",
                "Description": "Groundwork bootstrap - OIDC provider and admin role",
                "TemplateBody": template_body,
                "PermissionModel": "SERVICE_MANAGED",
                "AutoDeployment": {"Enabled": True, "RetainStacksOnAccountRemoval": False},
                "Capabilities": ["CAPABILITY_NAMED_IAM"],
                "CallAs": "DELEGATED_ADMIN",
            },
        )
        cfn_stubber.add_response(
            "create_stack_instances",
            {"OperationId": "op-abc"},
            expected_params={
                "StackSetName": "groundwork-bootstrap",
                "DeploymentTargets": {"OrganizationalUnitIds": ["r-abc1"]},
                "Regions": ["us-east-1"],
                "CallAs": "DELEGATED_ADMIN",
            },
        )
        cfn_stubber.activate()

        mock_gw_session = _stubbed_session({"cloudformation": cfn_stubber})

        with (
            patch.object(aws, "get_session", return_value=mock_gw_session),
            patch.object(aws, "get_oidc_thumbprint", new_callable=AsyncMock) as mock_thumb,
            patch.object(settings, "oidc_issuer_url", "https://idp.example.com"),
            patch.object(settings, "oidc_client_id", "gw-client"),
            patch.object(settings, "aws_groundwork_account_id", "222233334444"),
            patch.object(settings, "admin_role_name", "GroundworkAdmin-DO-NOT-DELETE"),
            patch.object(settings, "aws_region", "us-east-1"),
            patch.object(settings, "aws_org_root_id", "r-abc1"),
        ):
            mock_thumb.return_value = "a" * 40

            await aws.ensure_bootstrap_stackset()

        cfn_stubber.assert_no_pending_responses()

    async def test_updates_stackset_when_exists(self):
        """When the StackSet already exists, update it with the latest template."""
        template_body = aws._build_bootstrap_template(
            oidc_issuer_url="https://idp.example.com",
            oidc_client_id="gw-client",
            oidc_thumbprint="a" * 40,
            groundwork_account_id="222233334444",
            admin_role_name="GroundworkAdmin-DO-NOT-DELETE",
        )

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
            expected_params={
                "StackSetName": "groundwork-bootstrap",
                "CallAs": "DELEGATED_ADMIN",
            },
        )
        cfn_stubber.add_response(
            "update_stack_set",
            {"OperationId": "op-update-1"},
            expected_params={
                "StackSetName": "groundwork-bootstrap",
                "Description": "Groundwork bootstrap - OIDC provider and admin role",
                "TemplateBody": template_body,
                "Capabilities": ["CAPABILITY_NAMED_IAM"],
                "CallAs": "DELEGATED_ADMIN",
            },
        )
        cfn_stubber.activate()

        mock_gw_session = _stubbed_session({"cloudformation": cfn_stubber})

        with (
            patch.object(aws, "get_session", return_value=mock_gw_session),
            patch.object(aws, "get_oidc_thumbprint", new_callable=AsyncMock) as mock_thumb,
            patch.object(settings, "oidc_issuer_url", "https://idp.example.com"),
            patch.object(settings, "oidc_client_id", "gw-client"),
            patch.object(settings, "aws_groundwork_account_id", "222233334444"),
            patch.object(settings, "admin_role_name", "GroundworkAdmin-DO-NOT-DELETE"),
        ):
            mock_thumb.return_value = "a" * 40

            await aws.ensure_bootstrap_stackset()

        cfn_stubber.assert_no_pending_responses()

    async def test_update_skipped_when_operation_in_progress(self):
        """When another StackSet operation is running, skip the update gracefully."""
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
            expected_params={
                "StackSetName": "groundwork-bootstrap",
                "CallAs": "DELEGATED_ADMIN",
            },
        )
        cfn_stubber.add_client_error(
            "update_stack_set",
            service_error_code="OperationInProgressException",
            service_message="Another Operation on StackSet is in progress",
        )
        cfn_stubber.activate()

        mock_gw_session = _stubbed_session({"cloudformation": cfn_stubber})

        with (
            patch.object(aws, "get_session", return_value=mock_gw_session),
            patch.object(aws, "get_oidc_thumbprint", new_callable=AsyncMock) as mock_thumb,
            patch.object(settings, "oidc_issuer_url", "https://idp.example.com"),
            patch.object(settings, "oidc_client_id", "gw-client"),
            patch.object(settings, "aws_groundwork_account_id", "222233334444"),
            patch.object(settings, "admin_role_name", "GroundworkAdmin-DO-NOT-DELETE"),
        ):
            mock_thumb.return_value = "a" * 40

            # Should not raise
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
            patch.object(aws, "get_session", return_value=mock_gw_session),
            patch.object(settings, "aws_region", "us-east-1"),
        ):
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
            patch.object(aws, "get_session", return_value=mock_gw_session),
            patch.object(settings, "aws_region", "us-east-1"),
        ):
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
            patch.object(aws, "get_session", return_value=mock_gw_session),
            patch.object(settings, "aws_region", "us-east-1"),
        ):
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
            patch.object(aws, "get_session", return_value=mock_gw_session),
            patch.object(settings, "aws_region", "us-east-1"),
        ):
            op_id = await aws.deploy_to_account("123456789012", "ou-abc1-12345678")

        assert op_id == "op-manual-123"
        cfn_stubber.assert_no_pending_responses()


class TestAssumeGroundworkAdminViaGW:
    async def test_chains_through_groundwork_account(self):
        """assume_groundwork_admin uses get_session as base."""
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
            patch.object(aws, "get_session", return_value=gw_session),
            patch("backend.services.aws.aioboto3") as mock_aioboto3,
            patch.object(settings, "admin_role_name", "GroundworkAdmin-DO-NOT-DELETE"),
        ):
            await aws.assume_groundwork_admin("123456789012")

        mock_aioboto3.Session.assert_called_once()
        call_kwargs = mock_aioboto3.Session.call_args[1]
        assert call_kwargs["aws_access_key_id"] == "AKIATARGETEXAMPLE1"
        sts_stubber.assert_no_pending_responses()


class TestListOrgAccounts:
    async def test_returns_all_accounts_except_management(self):
        """list_org_accounts filters out the management account."""
        _, stubber = await create_stubbed_client("organizations")
        stubber.add_response(
            "list_accounts",
            {
                "Accounts": [
                    {
                        "Id": "111111111111",
                        "Name": "Management",
                        "Email": "mgmt@example.com",
                        "Status": "ACTIVE",
                        "JoinedMethod": "INVITED",
                        "JoinedTimestamp": datetime(2024, 1, 1),
                        "Arn": "arn:aws:organizations::111111111111:account/o-abc/111111111111",
                    },
                    {
                        "Id": "222222222222",
                        "Name": "Workload",
                        "Email": "work@example.com",
                        "Status": "ACTIVE",
                        "JoinedMethod": "CREATED",
                        "JoinedTimestamp": datetime(2024, 6, 1),
                        "Arn": "arn:aws:organizations::111111111111:account/o-abc/222222222222",
                    },
                    {
                        "Id": "333333333333",
                        "Name": "Suspended",
                        "Email": "sus@example.com",
                        "Status": "SUSPENDED",
                        "JoinedMethod": "CREATED",
                        "JoinedTimestamp": datetime(2024, 3, 1),
                        "Arn": "arn:aws:organizations::111111111111:account/o-abc/333333333333",
                    },
                ],
            },
        )
        _, sts_stubber = await create_stubbed_client("sts")
        sts_stubber.add_response(
            "get_caller_identity",
            {
                "UserId": "AROA:GroundworkOrganizations",
                "Account": "111111111111",
                "Arn": "arn:aws:sts::111111111111:assumed-role/GroundworkManagementRole/GroundworkOrganizations",
            },
        )
        stubber.activate()
        sts_stubber.activate()

        mgmt_session = _stubbed_session({"organizations": stubber, "sts": sts_stubber})

        with patch.object(
            aws,
            "get_management_session",
            new_callable=AsyncMock,
            return_value=mgmt_session,
        ):
            accounts = await aws.list_org_accounts()

        assert len(accounts) == 2
        ids = [a["aws_account_id"] for a in accounts]
        assert "111111111111" not in ids
        assert "222222222222" in ids
        assert "333333333333" in ids

    async def test_paginates_accounts(self):
        """list_org_accounts handles pagination."""
        _, stubber = await create_stubbed_client("organizations")
        stubber.add_response(
            "list_accounts",
            {
                "Accounts": [
                    {
                        "Id": "222222222222",
                        "Name": "Page1",
                        "Email": "p1@example.com",
                        "Status": "ACTIVE",
                        "JoinedMethod": "CREATED",
                        "JoinedTimestamp": datetime(2024, 1, 1),
                        "Arn": "arn:aws:organizations::111:account/o-abc/222222222222",
                    },
                ],
                "NextToken": "token123",
            },
        )
        stubber.add_response(
            "list_accounts",
            {
                "Accounts": [
                    {
                        "Id": "333333333333",
                        "Name": "Page2",
                        "Email": "p2@example.com",
                        "Status": "ACTIVE",
                        "JoinedMethod": "CREATED",
                        "JoinedTimestamp": datetime(2024, 2, 1),
                        "Arn": "arn:aws:organizations::111:account/o-abc/333333333333",
                    },
                ],
            },
        )
        _, sts_stubber = await create_stubbed_client("sts")
        sts_stubber.add_response(
            "get_caller_identity",
            {
                "UserId": "AROA:session",
                "Account": "111111111111",
                "Arn": "arn:aws:sts::111111111111:assumed-role/role/session",
            },
        )
        stubber.activate()
        sts_stubber.activate()

        mgmt_session = _stubbed_session({"organizations": stubber, "sts": sts_stubber})

        with patch.object(
            aws,
            "get_management_session",
            new_callable=AsyncMock,
            return_value=mgmt_session,
        ):
            accounts = await aws.list_org_accounts()

        assert len(accounts) == 2
        assert accounts[0]["aws_account_id"] == "222222222222"
        assert accounts[1]["aws_account_id"] == "333333333333"


class TestGetAccountOu:
    async def test_returns_ou_id(self):
        _, stubber = await create_stubbed_client("organizations")
        stubber.add_response(
            "list_parents",
            {
                "Parents": [
                    {"Id": "ou-abc1-12345678", "Type": "ORGANIZATIONAL_UNIT"},
                ]
            },
            expected_params={"ChildId": "222222222222"},
        )
        stubber.activate()

        mgmt_session = _stubbed_session({"organizations": stubber})

        with patch.object(
            aws,
            "get_management_session",
            new_callable=AsyncMock,
            return_value=mgmt_session,
        ):
            ou_id = await aws.get_account_ou("222222222222")

        assert ou_id == "ou-abc1-12345678"
        stubber.assert_no_pending_responses()

    async def test_returns_root_id_when_at_root(self):
        _, stubber = await create_stubbed_client("organizations")
        stubber.add_response(
            "list_parents",
            {
                "Parents": [
                    {"Id": "r-abc1", "Type": "ROOT"},
                ]
            },
            expected_params={"ChildId": "222222222222"},
        )
        stubber.activate()

        mgmt_session = _stubbed_session({"organizations": stubber})

        with patch.object(
            aws,
            "get_management_session",
            new_callable=AsyncMock,
            return_value=mgmt_session,
        ):
            ou_id = await aws.get_account_ou("222222222222")

        assert ou_id == "r-abc1"
