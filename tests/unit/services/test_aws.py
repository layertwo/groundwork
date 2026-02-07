"""Tests for AWS service layer."""

from unittest.mock import AsyncMock, MagicMock, patch

from backend.services import aws


class TestCreateAccount:
    async def test_create_account_returns_request_id(self):
        mock_client = AsyncMock()
        mock_client.create_account.return_value = {
            "CreateAccountStatus": {
                "Id": "car-abc123",
                "State": "IN_PROGRESS",
            }
        }
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.client.return_value = mock_client

        with patch.object(aws, "get_session", return_value=mock_session):
            result = await aws.create_account("TestAccount", "test@example.com")

        assert result == "car-abc123"
        mock_client.create_account.assert_called_once_with(
            Email="test@example.com",
            AccountName="TestAccount",
        )


class TestPollAccountCreation:
    async def test_poll_succeeded(self):
        mock_client = AsyncMock()
        mock_client.describe_create_account_status.return_value = {
            "CreateAccountStatus": {
                "Id": "car-abc123",
                "State": "SUCCEEDED",
                "AccountId": "123456789012",
            }
        }
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.client.return_value = mock_client

        with patch.object(aws, "get_session", return_value=mock_session):
            result = await aws.poll_account_creation("car-abc123")

        assert result["status"] == "SUCCEEDED"
        assert result["aws_account_id"] == "123456789012"

    async def test_poll_in_progress(self):
        mock_client = AsyncMock()
        mock_client.describe_create_account_status.return_value = {
            "CreateAccountStatus": {
                "Id": "car-abc123",
                "State": "IN_PROGRESS",
            }
        }
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.client.return_value = mock_client

        with patch.object(aws, "get_session", return_value=mock_session):
            result = await aws.poll_account_creation("car-abc123")

        assert result["status"] == "IN_PROGRESS"

    async def test_poll_failed(self):
        mock_client = AsyncMock()
        mock_client.describe_create_account_status.return_value = {
            "CreateAccountStatus": {
                "Id": "car-abc123",
                "State": "FAILED",
                "FailureReason": "EMAIL_ALREADY_EXISTS",
            }
        }
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.client.return_value = mock_client

        with patch.object(aws, "get_session", return_value=mock_session):
            result = await aws.poll_account_creation("car-abc123")

        assert result["status"] == "FAILED"
        assert result["error"] == "EMAIL_ALREADY_EXISTS"


class TestBootstrapAccount:
    async def test_bootstrap_creates_oidc_and_role(self):
        mock_sts_client = AsyncMock()
        mock_sts_client.assume_role.return_value = {
            "Credentials": {
                "AccessKeyId": "AKIA_FAKE",
                "SecretAccessKey": "secret",
                "SessionToken": "token",
            }
        }
        mock_sts_client.__aenter__ = AsyncMock(return_value=mock_sts_client)
        mock_sts_client.__aexit__ = AsyncMock(return_value=False)

        mock_iam_client = AsyncMock()
        mock_iam_client.create_open_id_connect_provider.return_value = {
            "OpenIDConnectProviderArn": "arn:aws:iam::123456789012:oidc-provider/example.com"
        }
        mock_iam_client.create_role.return_value = {
            "Role": {"Arn": "arn:aws:iam::123456789012:role/GroundworkAdmin-DO-NOT-DELETE"}
        }
        mock_iam_client.attach_role_policy.return_value = {}
        mock_iam_client.__aenter__ = AsyncMock(return_value=mock_iam_client)
        mock_iam_client.__aexit__ = AsyncMock(return_value=False)

        # First session's client() returns STS, second returns IAM
        mock_session = MagicMock()
        mock_session.client.return_value = mock_sts_client

        mock_target_session = MagicMock()
        mock_target_session.client.return_value = mock_iam_client

        with (
            patch.object(aws, "get_session", return_value=mock_session),
            patch.object(aws, "get_oidc_thumbprint", new_callable=AsyncMock) as mock_thumb,
            patch("backend.services.aws.aioboto3") as mock_aioboto3,
        ):
            mock_thumb.return_value = "abcdef1234567890abcdef1234567890abcdef12"
            mock_aioboto3.Session.return_value = mock_target_session

            result = await aws.bootstrap_account("123456789012")

        assert "oidc_provider_arn" in result
        assert "admin_role_arn" in result
        mock_iam_client.create_open_id_connect_provider.assert_called_once()
        mock_iam_client.create_role.assert_called_once()
        mock_iam_client.attach_role_policy.assert_called_once()
