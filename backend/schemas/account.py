from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr


class AccountCreate(BaseModel):
    account_name: str
    account_email: EmailStr
    organizational_unit: str
    sso_user_email: EmailStr


class AccountUpdate(BaseModel):
    account_name: Optional[str] = None
    organizational_unit: Optional[str] = None
    sso_user_email: Optional[EmailStr] = None


class AccountResponse(BaseModel):
    id: UUID
    aws_account_id: Optional[str]
    account_name: str
    account_email: str
    organizational_unit: str
    status: str
    sso_user_email: str
    provisioned_product_id: Optional[str]
    oidc_provider_arn: Optional[str]
    created_by: UUID
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
