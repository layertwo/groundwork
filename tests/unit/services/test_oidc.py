"""Tests for OIDC service — discovery, JWKS, and authorization URL construction."""

import time
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from backend.services import oidc
from tests.fixtures.oidc import MOCK_DISCOVERY, MOCK_ISSUER, MOCK_JWKS


@pytest.fixture(autouse=True)
def _clear_caches():
    """Reset module-level caches before each test."""
    oidc._discovery_cache = None
    oidc._discovery_fetched_at = 0
    oidc._jwks_cache = None
    oidc._jwks_fetched_at = 0
    yield
    oidc._discovery_cache = None
    oidc._discovery_fetched_at = 0
    oidc._jwks_cache = None
    oidc._jwks_fetched_at = 0


_DUMMY_REQUEST = httpx.Request("GET", "https://example.com")


def _mock_response(json_data: dict, status_code: int = 200) -> httpx.Response:
    return httpx.Response(status_code=status_code, json=json_data, request=_DUMMY_REQUEST)


class TestDiscover:
    async def test_discover_fetches_openid_configuration(self, monkeypatch):
        monkeypatch.setattr("backend.services.oidc.settings.oidc_issuer_url", MOCK_ISSUER)

        mock_get = AsyncMock(return_value=_mock_response(MOCK_DISCOVERY))
        with patch("httpx.AsyncClient.get", mock_get):
            result = await oidc._discover()

        assert result == MOCK_DISCOVERY
        mock_get.assert_called_once_with(f"{MOCK_ISSUER}/.well-known/openid-configuration")

    async def test_discover_uses_plain_httpx_client(self, monkeypatch):
        """Verify discovery does NOT use AsyncOAuth2Client (which adds token headers)."""
        monkeypatch.setattr("backend.services.oidc.settings.oidc_issuer_url", MOCK_ISSUER)

        mock_get = AsyncMock(return_value=_mock_response(MOCK_DISCOVERY))
        with patch("httpx.AsyncClient.get", mock_get):
            await oidc._discover()

        # The key assertion: httpx.AsyncClient.get was called, not OAuth2Client.get
        mock_get.assert_called_once()

    async def test_discover_caches_result(self, monkeypatch):
        monkeypatch.setattr("backend.services.oidc.settings.oidc_issuer_url", MOCK_ISSUER)

        mock_get = AsyncMock(return_value=_mock_response(MOCK_DISCOVERY))
        with patch("httpx.AsyncClient.get", mock_get):
            first = await oidc._discover()
            second = await oidc._discover()

        assert first is second
        mock_get.assert_called_once()

    async def test_discover_cache_expires(self, monkeypatch):
        monkeypatch.setattr("backend.services.oidc.settings.oidc_issuer_url", MOCK_ISSUER)

        mock_get = AsyncMock(return_value=_mock_response(MOCK_DISCOVERY))
        with patch("httpx.AsyncClient.get", mock_get):
            await oidc._discover()

            # Simulate cache expiry
            oidc._discovery_fetched_at = time.monotonic() - oidc._CACHE_TTL - 1
            await oidc._discover()

        assert mock_get.call_count == 2

    async def test_discover_raises_on_http_error(self, monkeypatch):
        monkeypatch.setattr("backend.services.oidc.settings.oidc_issuer_url", MOCK_ISSUER)

        mock_get = AsyncMock(
            return_value=httpx.Response(status_code=404, text="Not Found", request=_DUMMY_REQUEST)
        )
        with patch("httpx.AsyncClient.get", mock_get):
            with pytest.raises(httpx.HTTPStatusError):
                await oidc._discover()


class TestFetchJwks:
    async def test_fetch_jwks_uses_plain_httpx_client(self, monkeypatch):
        """Verify JWKS fetch does NOT use AsyncOAuth2Client."""
        monkeypatch.setattr("backend.services.oidc.settings.oidc_issuer_url", MOCK_ISSUER)

        # Pre-populate discovery cache so only JWKS fetch hits the network
        oidc._discovery_cache = MOCK_DISCOVERY
        oidc._discovery_fetched_at = time.monotonic()

        mock_get = AsyncMock(return_value=_mock_response(MOCK_JWKS))
        with patch("httpx.AsyncClient.get", mock_get):
            result = await oidc._fetch_jwks()

        assert result == MOCK_JWKS
        mock_get.assert_called_once_with(MOCK_DISCOVERY["jwks_uri"])

    async def test_fetch_jwks_caches_result(self, monkeypatch):
        monkeypatch.setattr("backend.services.oidc.settings.oidc_issuer_url", MOCK_ISSUER)

        oidc._discovery_cache = MOCK_DISCOVERY
        oidc._discovery_fetched_at = time.monotonic()

        mock_get = AsyncMock(return_value=_mock_response(MOCK_JWKS))
        with patch("httpx.AsyncClient.get", mock_get):
            first = await oidc._fetch_jwks()
            second = await oidc._fetch_jwks()

        assert first is second
        mock_get.assert_called_once()


class TestCreateAuthorizationUrl:
    async def test_creates_url_with_state_and_nonce(self, monkeypatch):
        monkeypatch.setattr("backend.services.oidc.settings.oidc_issuer_url", MOCK_ISSUER)
        monkeypatch.setattr("backend.services.oidc.settings.oidc_client_id", "test-client")
        monkeypatch.setattr("backend.services.oidc.settings.oidc_client_secret", "test-secret")
        monkeypatch.setattr(
            "backend.services.oidc.settings.oidc_redirect_uri",
            "http://localhost/callback",
        )

        with patch("backend.services.oidc._discover", new_callable=AsyncMock) as mock_disc:
            mock_disc.return_value = MOCK_DISCOVERY
            url = await oidc.create_authorization_url(state="s1", nonce="n1")

        assert MOCK_DISCOVERY["authorization_endpoint"] in url
        assert "state=s1" in url
        assert "nonce=n1" in url

    async def test_calls_discover_without_arguments(self, monkeypatch):
        """Verify _discover() is called with no arguments (no client parameter)."""
        monkeypatch.setattr("backend.services.oidc.settings.oidc_issuer_url", MOCK_ISSUER)
        monkeypatch.setattr("backend.services.oidc.settings.oidc_client_id", "test-client")
        monkeypatch.setattr("backend.services.oidc.settings.oidc_client_secret", "test-secret")
        monkeypatch.setattr(
            "backend.services.oidc.settings.oidc_redirect_uri",
            "http://localhost/callback",
        )

        with patch("backend.services.oidc._discover", new_callable=AsyncMock) as mock_disc:
            mock_disc.return_value = MOCK_DISCOVERY
            await oidc.create_authorization_url(state="s1", nonce="n1")

        mock_disc.assert_called_once_with()


class TestClearJwksCache:
    def test_clear_resets_cache(self):
        oidc._jwks_cache = {"keys": []}
        oidc._jwks_fetched_at = 12345.0

        oidc._clear_jwks_cache()

        assert oidc._jwks_cache is None
        assert oidc._jwks_fetched_at == 0
