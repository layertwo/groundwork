import json
import re
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

_ARN_PATTERN = re.compile(r"^arn:aws:iam::\w*:policy/[\w+=,.@\-/]+$")
_ROLE_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_+=,.@-]+$")

MAX_MANAGED_POLICIES = 20
MAX_INLINE_POLICY_BYTES = 10240
MAX_LIST_ENTRIES = 50
MAX_ENTRY_LENGTH = 256


def _validate_role_name(v: str) -> str:
    if not _ROLE_NAME_PATTERN.match(v):
        raise ValueError("Role name may only contain alphanumeric characters and _+=,.@-")
    return v


def _validate_arns(v: list[str]) -> list[str]:
    if len(v) > MAX_MANAGED_POLICIES:
        raise ValueError(f"Maximum {MAX_MANAGED_POLICIES} managed policy ARNs allowed")
    for arn in v:
        if not _ARN_PATTERN.match(arn):
            raise ValueError(f"Invalid IAM policy ARN: {arn}")
    return v


def _validate_string_list(v: list[str]) -> list[str]:
    if len(v) > MAX_LIST_ENTRIES:
        raise ValueError(f"Maximum {MAX_LIST_ENTRIES} entries allowed")
    for item in v:
        if not item or len(item) > MAX_ENTRY_LENGTH:
            raise ValueError(f"Each entry must be 1-{MAX_ENTRY_LENGTH} characters")
    return v


def _validate_inline_policy(v: dict | None) -> dict | None:
    if v is None:
        return v
    serialized = json.dumps(v)
    if len(serialized) > MAX_INLINE_POLICY_BYTES:
        raise ValueError(
            f"Inline policy exceeds AWS maximum size of {MAX_INLINE_POLICY_BYTES} bytes"
        )
    if "Statement" not in v:
        raise ValueError("Inline policy must contain a 'Statement' key")
    return v


class RoleCreate(BaseModel):
    role_name: str = Field(min_length=1, max_length=128)
    template_id: Optional[UUID] = None
    managed_policy_arns: list[str] = []
    inline_policy: Optional[dict[str, Any]] = None
    allowed_groups: list[str] = []
    allowed_users: list[str] = []
    api_session_duration: int = Field(default=900, ge=900, le=43200)
    console_session_duration: int = Field(default=3600, ge=900, le=43200)
    description: Optional[str] = Field(default=None, max_length=1000)

    @field_validator("role_name", mode="before")
    @classmethod
    def check_role_name(cls, v: str) -> str:
        return _validate_role_name(v)

    @field_validator("managed_policy_arns", mode="before")
    @classmethod
    def validate_arns(cls, v: list[str]) -> list[str]:
        return _validate_arns(v)

    @field_validator("allowed_groups", "allowed_users", mode="before")
    @classmethod
    def validate_string_lists(cls, v: list[str]) -> list[str]:
        return _validate_string_list(v)

    @field_validator("inline_policy", mode="before")
    @classmethod
    def validate_inline_policy(cls, v: dict | None) -> dict | None:
        return _validate_inline_policy(v)


class RoleUpdate(BaseModel):
    managed_policy_arns: Optional[list[str]] = None
    inline_policy: Optional[dict[str, Any]] = None
    allowed_groups: Optional[list[str]] = None
    allowed_users: Optional[list[str]] = None
    api_session_duration: Optional[int] = Field(default=None, ge=900, le=43200)
    console_session_duration: Optional[int] = Field(default=None, ge=900, le=43200)
    description: Optional[str] = Field(default=None, max_length=1000)

    @field_validator("managed_policy_arns", mode="before")
    @classmethod
    def validate_arns(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        return _validate_arns(v)

    @field_validator("allowed_groups", "allowed_users", mode="before")
    @classmethod
    def validate_string_lists(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        return _validate_string_list(v)

    @field_validator("inline_policy", mode="before")
    @classmethod
    def validate_inline_policy(cls, v: dict | None) -> dict | None:
        return _validate_inline_policy(v)


class RoleResponse(BaseModel):
    id: UUID
    account_id: UUID
    role_name: str
    role_arn: str
    status: str
    error_message: Optional[str]
    allowed_groups: list[str]
    managed_policy_arns: list[str]
    inline_policy: Optional[dict[str, Any]]
    allowed_users: list[str]
    api_session_duration: int
    console_session_duration: int
    description: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AssumeRoleRequest(BaseModel):
    role_id: UUID


class AssumeRoleResponse(BaseModel):
    access_key_id: str
    secret_access_key: str
    session_token: str
    expiration: datetime
