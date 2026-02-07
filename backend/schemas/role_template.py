import re
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

_ARN_PATTERN = re.compile(r"^arn:aws:iam::\w*:policy/[\w+=,.@\-/]+$")


class RoleTemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: Optional[str] = Field(default=None, max_length=1000)
    managed_policy_arns: list[str] = []

    @field_validator("managed_policy_arns", mode="before")
    @classmethod
    def validate_arns(cls, v: list[str]) -> list[str]:
        for arn in v:
            if not _ARN_PATTERN.match(arn):
                raise ValueError(f"Invalid IAM policy ARN: {arn}")
        return v


class RoleTemplateUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    description: Optional[str] = Field(default=None, max_length=1000)
    managed_policy_arns: Optional[list[str]] = None

    @field_validator("managed_policy_arns", mode="before")
    @classmethod
    def validate_arns(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        for arn in v:
            if not _ARN_PATTERN.match(arn):
                raise ValueError(f"Invalid IAM policy ARN: {arn}")
        return v


class RoleTemplateResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str]
    managed_policy_arns: list[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
