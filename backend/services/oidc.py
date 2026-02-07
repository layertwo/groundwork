import logging
from typing import Any

from authlib.integrations.httpx_client import AsyncOAuth2Client
from authlib.jose import JsonWebKey, jwt

from backend.config import settings

logger = logging.getLogger(__name__)

_jwks_cache: dict[str, Any] | None = None


def _get_client() -> AsyncOAuth2Client:
    return AsyncOAuth2Client(
        client_id=settings.oidc_client_id,
        client_secret=settings.oidc_client_secret,
        redirect_uri=settings.oidc_redirect_uri,
        scope="openid profile email groups",
    )


async def _discover(client: AsyncOAuth2Client) -> dict[str, Any]:
    url = f"{settings.oidc_issuer_url.rstrip('/')}/.well-known/openid-configuration"
    resp = await client.get(url)
    resp.raise_for_status()
    return resp.json()


async def create_authorization_url(state: str, nonce: str) -> str:
    client = _get_client()
    discovery = await _discover(client)
    authorization_endpoint = discovery["authorization_endpoint"]
    url, _ = client.create_authorization_url(
        authorization_endpoint, state=state, nonce=nonce
    )
    await client.aclose()
    return url


async def exchange_code(code: str) -> dict[str, Any]:
    client = _get_client()
    discovery = await _discover(client)
    token_endpoint = discovery["token_endpoint"]
    token = await client.fetch_token(
        token_endpoint,
        code=code,
        grant_type="authorization_code",
    )
    await client.aclose()
    return token


async def _fetch_jwks() -> dict[str, Any]:
    global _jwks_cache
    if _jwks_cache is not None:
        return _jwks_cache
    client = _get_client()
    discovery = await _discover(client)
    jwks_uri = discovery["jwks_uri"]
    resp = await client.get(jwks_uri)
    resp.raise_for_status()
    _jwks_cache = resp.json()
    await client.aclose()
    return _jwks_cache


async def validate_id_token(id_token: str, nonce: str) -> dict[str, Any]:
    jwks_data = await _fetch_jwks()
    key_set = JsonWebKey.import_key_set(jwks_data)
    claims = jwt.decode(
        id_token,
        key_set,
        claims_options={
            "iss": {"essential": True, "value": settings.oidc_issuer_url},
            "aud": {"essential": True, "value": settings.oidc_client_id},
            "nonce": {"essential": True, "value": nonce},
        },
    )
    claims.validate()
    return dict(claims)


async def refresh_tokens(refresh_token: str) -> dict[str, Any]:
    client = _get_client()
    discovery = await _discover(client)
    token_endpoint = discovery["token_endpoint"]
    token = await client.fetch_token(
        token_endpoint,
        grant_type="refresh_token",
        refresh_token=refresh_token,
    )
    await client.aclose()
    return token
