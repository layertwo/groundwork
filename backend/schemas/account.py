"""Account request/response models.

Wire shapes come from ``smithy/models/accounts.smithy`` and are generated into
``backend/schemas/generated/models.py`` — edit the Smithy model, not that file.
This module only adds what Smithy cannot express (email format) and re-exports
the generated classes under the names the router uses.
"""

from pydantic import EmailStr, TypeAdapter, field_validator

from backend.schemas.generated.models import (
    CreateAccountRequestContent,
    CreateAccountResponseContent,
    GetAccountResponseContent,
    ListAccountsResponseContent,
    UpdateAccountRequestContent,
    UpdateAccountResponseContent,
)

__all__ = [
    "AccountCreate",
    "AccountListResponse",
    "AccountResponse",
    "AccountUpdate",
    "CreateAccountResponse",
    "UpdateAccountResponse",
]

_EMAIL = TypeAdapter(EmailStr)


class AccountCreate(CreateAccountRequestContent):
    """Generated create body, with email fields validated as addresses."""

    @field_validator("account_email", "sso_user_email")
    @classmethod
    def _validate_email(cls, value: str) -> str:
        _EMAIL.validate_python(value)
        return value


AccountUpdate = UpdateAccountRequestContent
AccountResponse = GetAccountResponseContent
AccountListResponse = ListAccountsResponseContent
CreateAccountResponse = CreateAccountResponseContent
UpdateAccountResponse = UpdateAccountResponseContent
