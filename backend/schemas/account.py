from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class AccountCreate(BaseModel):
    account_name: str = Field(min_length=1, max_length=50)
    account_email: EmailStr
    organizational_unit: str = Field(min_length=1, max_length=128, pattern=r"^(ou-|r-)[a-z0-9-]+$")
    sso_user_email: EmailStr


class AccountUpdate(BaseModel):
    account_name: Optional[str] = Field(None, min_length=1, max_length=50)
    organizational_unit: Optional[str] = Field(
        None, min_length=1, max_length=128, pattern=r"^(ou-|r-)[a-z0-9-]+$"
    )
    sso_user_email: Optional[EmailStr] = None


class AccountResponse(BaseModel):
    id: UUID
    aws_account_id: Optional[str]
    account_name: str
    account_email: str
    organizational_unit: str
    status: str
    aws_status: Optional[str]
    sso_user_email: str
    provisioned_product_id: Optional[str]
    oidc_provider_arn: Optional[str]
    created_by: UUID
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
