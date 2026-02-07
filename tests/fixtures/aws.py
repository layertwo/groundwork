"""Mock AWS fixtures for testing."""

from unittest.mock import AsyncMock, patch

import pytest

FAKE_ACCOUNT_ID = "123456789012"
FAKE_REQUEST_ID = "car-abc123def456"
FAKE_OIDC_ARN = "arn:aws:iam::123456789012:oidc-provider/example.com"
FAKE_ADMIN_ROLE_ARN = "arn:aws:iam::123456789012:role/GroundworkAdmin-DO-NOT-DELETE"


@pytest.fixture
def mock_aws_create_account():
    with patch("backend.services.aws.create_account", new_callable=AsyncMock) as m:
        m.return_value = FAKE_REQUEST_ID
        yield m


@pytest.fixture
def mock_aws_poll_account_creation():
    with patch("backend.services.aws.poll_account_creation", new_callable=AsyncMock) as m:
        m.return_value = {
            "status": "SUCCEEDED",
            "aws_account_id": FAKE_ACCOUNT_ID,
        }
        yield m


@pytest.fixture
def mock_aws_move_account_to_ou():
    with patch("backend.services.aws.move_account_to_ou", new_callable=AsyncMock) as m:
        yield m


@pytest.fixture
def mock_aws_bootstrap_account():
    with patch("backend.services.aws.bootstrap_account", new_callable=AsyncMock) as m:
        m.return_value = {
            "oidc_provider_arn": FAKE_OIDC_ARN,
            "admin_role_arn": FAKE_ADMIN_ROLE_ARN,
        }
        yield m


@pytest.fixture
def mock_aws_full(
    mock_aws_create_account,
    mock_aws_poll_account_creation,
    mock_aws_move_account_to_ou,
    mock_aws_bootstrap_account,
):
    """Convenience fixture that mocks all AWS service functions."""
    return {
        "create_account": mock_aws_create_account,
        "poll_account_creation": mock_aws_poll_account_creation,
        "move_account_to_ou": mock_aws_move_account_to_ou,
        "bootstrap_account": mock_aws_bootstrap_account,
    }
