"""Response returned by the federate CLI flow (not a resource operation)."""

from typing import Any

from pydantic import BaseModel


class AssumeRoleResponse(BaseModel):
    """Temporary STS credentials."""

    access_key_id: str
    secret_access_key: str
    session_token: str
    expiration: Any
