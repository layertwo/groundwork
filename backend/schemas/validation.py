"""Validation the Smithy contract cannot express.

Kept as plain functions so generated models are never wrapped or aliased:
routes call these before writing the request to the database.
"""

import json
from typing import Any

from pydantic import EmailStr, TypeAdapter, ValidationError

from backend.exceptions import GroundworkError

_MAX_INLINE_POLICY_BYTES = 10240

_EMAIL = TypeAdapter(EmailStr)


def ensure_email(value: str) -> None:
    try:
        _EMAIL.validate_python(value)
    except ValidationError as exc:
        raise GroundworkError(f"Invalid email address: {value}", status_code=422) from exc


def ensure_inline_policy(value: dict[str, Any] | None) -> None:
    if value is None:
        return
    if len(json.dumps(value)) > _MAX_INLINE_POLICY_BYTES:
        raise GroundworkError(
            f"Inline policy exceeds AWS maximum size of {_MAX_INLINE_POLICY_BYTES} bytes",
            status_code=422,
        )
    if "Statement" not in value:
        raise GroundworkError("Inline policy must contain a 'Statement' key", status_code=422)
