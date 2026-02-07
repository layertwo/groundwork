"""Mock OIDC provider fixtures for testing auth flows."""

import time
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from authlib.jose import JsonWebKey, jwt

# Generate a stable RSA key pair for test token signing
_RSA_KEY = JsonWebKey.generate_key("RSA", 2048, is_private=True)
_RSA_KEY_DICT = _RSA_KEY.as_dict(is_private=True)
_RSA_PUBLIC_KEY_DICT = _RSA_KEY.as_dict(is_private=False)
_RSA_PUBLIC_KEY_DICT["kid"] = "test-key-1"
_RSA_PUBLIC_KEY_DICT["use"] = "sig"
_RSA_PUBLIC_KEY_DICT["alg"] = "RS256"

MOCK_ISSUER = "https://id.example.com"
MOCK_CLIENT_ID = "test-client-id"

MOCK_DISCOVERY = {
    "issuer": MOCK_ISSUER,
    "authorization_endpoint": f"{MOCK_ISSUER}/authorize",
    "token_endpoint": f"{MOCK_ISSUER}/token",
    "userinfo_endpoint": f"{MOCK_ISSUER}/userinfo",
    "jwks_uri": f"{MOCK_ISSUER}/.well-known/jwks.json",
    "response_types_supported": ["code"],
    "grant_types_supported": ["authorization_code", "refresh_token"],
    "scopes_supported": ["openid", "profile", "email", "groups"],
}

MOCK_JWKS = {"keys": [_RSA_PUBLIC_KEY_DICT]}


def make_id_token(
    sub: str = "test-user-sub",
    email: str = "test@example.com",
    name: str = "Test User",
    groups: list[str] | None = None,
    nonce: str = "test-nonce",
    expires_in: int = 3600,
) -> str:
    now = int(time.time())
    header = {"alg": "RS256", "kid": "test-key-1"}
    payload = {
        "iss": MOCK_ISSUER,
        "aud": MOCK_CLIENT_ID,
        "sub": sub,
        "email": email,
        "name": name,
        "groups": groups or ["users"],
        "nonce": nonce,
        "iat": now,
        "exp": now + expires_in,
    }
    token = jwt.encode(header, payload, _RSA_KEY)
    return token.decode("utf-8") if isinstance(token, bytes) else token


def make_token_response(
    nonce: str = "test-nonce",
    sub: str = "test-user-sub",
    email: str = "test@example.com",
    name: str = "Test User",
    groups: list[str] | None = None,
    expires_in: int = 3600,
) -> dict:
    return {
        "access_token": f"mock-access-token-{uuid.uuid4().hex[:8]}",
        "refresh_token": f"mock-refresh-token-{uuid.uuid4().hex[:8]}",
        "id_token": make_id_token(sub=sub, email=email, name=name, groups=groups, nonce=nonce),
        "token_type": "Bearer",
        "expires_in": expires_in,
    }


@pytest.fixture
def mock_oidc_discovery():
    """Patch OIDC discovery to return mock configuration."""
    with patch("backend.services.oidc._discover", new_callable=AsyncMock) as mock:
        mock.return_value = MOCK_DISCOVERY
        yield mock


@pytest.fixture
def mock_oidc_exchange():
    """Patch OIDC code exchange to return mock tokens."""
    with patch("backend.services.oidc.exchange_code", new_callable=AsyncMock) as mock:
        yield mock


@pytest.fixture
def mock_oidc_validate():
    """Patch OIDC token validation to return mock claims."""
    with patch("backend.services.oidc.validate_id_token", new_callable=AsyncMock) as mock:
        yield mock


@pytest.fixture
def mock_oidc_refresh():
    """Patch OIDC token refresh to return new mock tokens."""
    with patch("backend.services.oidc.refresh_tokens", new_callable=AsyncMock) as mock:
        yield mock


@pytest.fixture
def mock_oidc_full(mock_oidc_discovery, mock_oidc_exchange, mock_oidc_validate):
    """Full OIDC mock: discovery + exchange + validate."""
    return {
        "discovery": mock_oidc_discovery,
        "exchange": mock_oidc_exchange,
        "validate": mock_oidc_validate,
    }
