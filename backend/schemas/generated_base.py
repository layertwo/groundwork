"""Base class for Smithy-generated pydantic models.

Wired in via ``--base-class`` in ``scripts/codegen.sh``. Keeps the generated
file free of project config while making every model accept both wire
(camelCase alias) and Python (snake_case) field names on input, and serialize
SQLAlchemy objects directly.

Two normalizations the Smithy contract cannot express:

* ids are modelled as ``String`` (Smithy has no UUID shape), so UUID values
  from the ORM are stringified;
* timestamps are ``AwareDatetime`` but the database columns are TIMESTAMP
  WITHOUT TIME ZONE, so naive values are read as UTC.
"""

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator


class GeneratedBaseModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    @field_validator("*", mode="before")
    @classmethod
    def _normalize_scalars(cls, value: Any) -> Any:
        if isinstance(value, datetime) and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        if isinstance(value, UUID):
            return str(value)
        return value
