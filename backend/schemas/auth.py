from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class UserInfo(BaseModel):
    id: UUID
    sub: str
    email: str
    display_name: str
    groups: list[str]
    is_admin: bool

    model_config = {"from_attributes": True}


class LoginResponse(BaseModel):
    redirect_url: str


class AuthStatus(BaseModel):
    authenticated: bool
    user: Optional[UserInfo] = None
