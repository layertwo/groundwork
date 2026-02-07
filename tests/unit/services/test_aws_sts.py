"""Tests for AWS STS assume-role-with-web-identity and console URL functions."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, unquote, urlparse

from backend.services import aws
from tests.fixtures.aws import _stubbed_session, create_stubbed_client

ROLE_ARN = "arn:aws:iam::123456789012:role/TestRole"
FAKE_ID_TOKEN = "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ1c2VyLTEifQ.sig"

FAKE_STS_CREDENTIALS = {
    "AccessKeyId": "AKIAIOSFODNN7EXAMPLE",
    "SecretAccessKey": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
    "SessionToken": "FwoGZXIvYXdzEBYaDHqa0AP1",
    "Expiration": datetime(2026, 1, 1, tzinfo=timezone.utc),
}


class TestAssumeRoleWithWebIdentity:
    async def test_returns_sts_credentials(self):
        _, sts_stubber = await create_stubbed_client("sts")
        sts_stubber.add_response(
            "assume_role_with_web_identity",
            {
                "Credentials": FAKE_STS_CREDENTIALS,
                "SubjectFromWebIdentityToken": "user-1",
                "AssumedRoleUser": {
                    "AssumedRoleId": "AROAEXAMPLE:user@example.com",
                    "Arn": f"{ROLE_ARN}/user@example.com",
                },
            },
            expected_params={
                "RoleArn": ROLE_ARN,
                "RoleSessionName": "user@example.com",
                "WebIdentityToken": FAKE_ID_TOKEN,
                "DurationSeconds": 900,
            },
        )
        sts_stubber.activate()

        session = _stubbed_session({"sts": sts_stubber})
        with patch.object(aws, "get_session", return_value=session):
            result = await aws.assume_role_with_web_identity(
                role_arn=ROLE_ARN,
                id_token=FAKE_ID_TOKEN,
                session_duration=900,
                session_name="user@example.com",
            )

        assert result["access_key_id"] == "AKIAIOSFODNN7EXAMPLE"
        assert result["secret_access_key"] == "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
        assert result["session_token"] == "FwoGZXIvYXdzEBYaDHqa0AP1"
        assert result["expiration"] == datetime(2026, 1, 1, tzinfo=timezone.utc)
        sts_stubber.assert_no_pending_responses()


class TestGetConsoleUrl:
    async def test_returns_valid_federation_url(self):
        credentials: aws.STSCredentials = {
            "access_key_id": "AKIAIOSFODNN7EXAMPLE",
            "secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            "session_token": "FwoGZXIvYXdzEBYaDHqa0AP1",
            "expiration": datetime(2026, 1, 1, tzinfo=timezone.utc),
        }

        mock_response = AsyncMock()
        mock_response.raise_for_status = lambda: None
        mock_response.json = AsyncMock(return_value={"SigninToken": "fake-signin-token-123"})

        mock_http_get = AsyncMock(return_value=mock_response)

        # Mock aiohttp.ClientSession as a context manager
        mock_session_instance = AsyncMock()
        mock_session_instance.get = lambda *args, **kwargs: _async_ctx(
            mock_http_get, *args, **kwargs
        )

        with patch("backend.services.aws.aiohttp.ClientSession") as mock_session_cls:
            mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session_instance)
            mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            url = await aws.get_console_url(
                credentials=credentials,
                console_session_duration=3600,
                issuer="https://groundwork.example.com",
            )

        parsed = urlparse(url)
        # Base federation endpoint
        assert parsed.scheme == "https"
        assert parsed.netloc == "signin.aws.amazon.com"
        assert parsed.path == "/federation"

        # Query parameters
        query = parse_qs(parsed.query)
        assert query.get("Action") == ["login"]
        assert query.get("SigninToken") == ["fake-signin-token-123"]

        # Destination should be an AWS console URL
        destination_values = query.get("Destination")
        assert destination_values, "Destination parameter missing from console URL"
        destination_url = unquote(destination_values[0])
        destination_parsed = urlparse(destination_url)
        assert destination_parsed.netloc == "console.aws.amazon.com"

    async def test_console_url_contains_issuer(self):
        credentials: aws.STSCredentials = {
            "access_key_id": "AKID",
            "secret_access_key": "SECRET",
            "session_token": "TOKEN",
            "expiration": datetime(2026, 1, 1, tzinfo=timezone.utc),
        }

        mock_response = AsyncMock()
        mock_response.raise_for_status = lambda: None
        mock_response.json = AsyncMock(return_value={"SigninToken": "tok"})

        mock_http_get = AsyncMock(return_value=mock_response)

        mock_session_instance = AsyncMock()
        mock_session_instance.get = lambda *args, **kwargs: _async_ctx(
            mock_http_get, *args, **kwargs
        )

        with patch("backend.services.aws.aiohttp.ClientSession") as mock_session_cls:
            mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session_instance)
            mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            url = await aws.get_console_url(
                credentials=credentials,
                console_session_duration=3600,
                issuer="https://myapp.example.com",
            )

        # Issuer should be URL-encoded in the final URL
        parsed = urlparse(url)
        query_params = parse_qs(parsed.query)
        assert query_params.get("Issuer") == ["https://myapp.example.com"]

    async def test_federation_request_params(self):
        """Verify the getSigninToken request sends correct params."""
        credentials: aws.STSCredentials = {
            "access_key_id": "AKID",
            "secret_access_key": "SECRET",
            "session_token": "TOKEN",
            "expiration": datetime(2026, 1, 1, tzinfo=timezone.utc),
        }

        captured_params: dict = {}

        mock_response = AsyncMock()
        mock_response.raise_for_status = lambda: None
        mock_response.json = AsyncMock(return_value={"SigninToken": "tok"})

        async def capture_get(url, *, params=None, **kwargs):
            captured_params["url"] = url
            captured_params["params"] = params
            return mock_response

        mock_session_instance = AsyncMock()
        mock_session_instance.get = lambda *args, **kwargs: _async_ctx_fn(
            capture_get, *args, **kwargs
        )

        with patch("backend.services.aws.aiohttp.ClientSession") as mock_session_cls:
            mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session_instance)
            mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            await aws.get_console_url(
                credentials=credentials,
                console_session_duration=7200,
                issuer="https://example.com",
            )

        assert captured_params["url"] == "https://signin.aws.amazon.com/federation"
        assert captured_params["params"]["Action"] == "getSigninToken"
        assert captured_params["params"]["SessionDuration"] == "7200"
        assert '"sessionId": "AKID"' in captured_params["params"]["Session"]
        assert '"sessionKey": "SECRET"' in captured_params["params"]["Session"]
        assert '"sessionToken": "TOKEN"' in captured_params["params"]["Session"]


# ---------------------------------------------------------------------------
# Helpers for mocking aiohttp context managers
# ---------------------------------------------------------------------------


class _async_ctx:
    """Wrap an AsyncMock to behave as an async context manager (for aiohttp response)."""

    def __init__(self, mock, *args, **kwargs):
        self._mock = mock
        self._args = args
        self._kwargs = kwargs

    async def __aenter__(self):
        return await self._mock(*self._args, **self._kwargs)

    async def __aexit__(self, *args):
        pass


class _async_ctx_fn:
    """Wrap an async function to behave as an async context manager."""

    def __init__(self, fn, *args, **kwargs):
        self._fn = fn
        self._args = args
        self._kwargs = kwargs

    async def __aenter__(self):
        return await self._fn(*self._args, **self._kwargs)

    async def __aexit__(self, *args):
        pass
