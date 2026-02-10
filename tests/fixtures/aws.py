"""AWS test fixtures — Stubber helpers and service-level mocks."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import aiobotocore.session
import pytest
from aiobotocore.stub import AioStubber

FAKE_ACCOUNT_ID = "123456789012"
FAKE_REQUEST_ID = "car-abc123def456"
FAKE_ADMIN_ROLE_ARN = "arn:aws:iam::123456789012:role/GroundworkAdmin-DO-NOT-DELETE"


def _stubbed_session(stubs: dict):
    """Build a mock aioboto3 session whose .client() yields pre-stubbed clients.

    ``stubs`` maps service names (e.g. "organizations") to AioStubber instances.
    """

    @asynccontextmanager
    async def _client(service_name, **kwargs):
        yield stubs[service_name].client

    mock_session = MagicMock()
    mock_session.client = _client
    return mock_session


async def create_stubbed_client(service: str):
    """Create an aiobotocore client with dummy credentials and return it with an AioStubber."""
    session = aiobotocore.session.get_session()
    ctx = session.create_client(
        service,
        region_name="us-east-1",
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
        aws_session_token="testing",
    )
    client = await ctx.__aenter__()
    stubber = AioStubber(client)
    stubber._ctx = ctx
    return client, stubber


# ---------------------------------------------------------------------------
# Router-level fixtures (mock the service functions, not the AWS clients)
# ---------------------------------------------------------------------------


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
