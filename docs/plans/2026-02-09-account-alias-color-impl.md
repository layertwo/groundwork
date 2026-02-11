# Account Alias & Color Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add support for viewing and editing AWS account aliases and account colors through the existing Groundwork API and frontend.

**Architecture:** No local database changes. Alias uses standard IAM APIs via boto3. Color uses the UXC service via raw HTTP with SigV4 signing. An in-memory TTL cache (15 min) serves reads for both list and detail endpoints. The existing PATCH endpoint handles writes with write-through cache updates.

**Tech Stack:** Python/FastAPI backend, aioboto3 for IAM, httpx + botocore SigV4Auth for UXC, React/TypeScript frontend with shadcn/ui.

---

### Task 1: AWS Service Layer — Account Alias Functions

**Files:**
- Modify: `backend/services/aws.py` (append after line 403)
- Test: `tests/unit/services/test_aws.py` (append new test classes)

**Step 1: Write the failing tests**

Add to `tests/unit/services/test_aws.py`:

```python
class TestGetAccountAlias:
    async def test_returns_alias_when_set(self):
        _, iam_stubber = await create_stubbed_client("iam")
        iam_stubber.add_response(
            "list_account_aliases",
            {"AccountAliases": ["my-alias"], "IsTruncated": False},
        )
        iam_stubber.activate()

        with patch.object(
            aws,
            "assume_groundwork_admin",
            new_callable=AsyncMock,
            return_value=_stubbed_session({"iam": iam_stubber}),
        ):
            result = await aws.get_account_alias("123456789012")

        assert result == "my-alias"
        iam_stubber.assert_no_pending_responses()

    async def test_returns_none_when_no_alias(self):
        _, iam_stubber = await create_stubbed_client("iam")
        iam_stubber.add_response(
            "list_account_aliases",
            {"AccountAliases": [], "IsTruncated": False},
        )
        iam_stubber.activate()

        with patch.object(
            aws,
            "assume_groundwork_admin",
            new_callable=AsyncMock,
            return_value=_stubbed_session({"iam": iam_stubber}),
        ):
            result = await aws.get_account_alias("123456789012")

        assert result is None
        iam_stubber.assert_no_pending_responses()


class TestSetAccountAlias:
    async def test_creates_alias(self):
        _, iam_stubber = await create_stubbed_client("iam")
        iam_stubber.add_response(
            "create_account_alias",
            {},
            expected_params={"AccountAlias": "my-alias"},
        )
        iam_stubber.activate()

        with patch.object(
            aws,
            "assume_groundwork_admin",
            new_callable=AsyncMock,
            return_value=_stubbed_session({"iam": iam_stubber}),
        ):
            await aws.set_account_alias("123456789012", "my-alias")

        iam_stubber.assert_no_pending_responses()


class TestDeleteAccountAlias:
    async def test_deletes_alias(self):
        _, iam_stubber = await create_stubbed_client("iam")
        iam_stubber.add_response(
            "delete_account_alias",
            {},
            expected_params={"AccountAlias": "my-alias"},
        )
        iam_stubber.activate()

        with patch.object(
            aws,
            "assume_groundwork_admin",
            new_callable=AsyncMock,
            return_value=_stubbed_session({"iam": iam_stubber}),
        ):
            await aws.delete_account_alias("123456789012", "my-alias")

        iam_stubber.assert_no_pending_responses()
```

**Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=. pytest tests/unit/services/test_aws.py::TestGetAccountAlias -v`
Expected: FAIL — `AttributeError: module 'backend.services.aws' has no attribute 'get_account_alias'`

**Step 3: Write the implementation**

Add to `backend/services/aws.py` after the `delete_iam_role` function (after line 403):

```python
# ---------------------------------------------------------------------------
# Account alias management
# ---------------------------------------------------------------------------


async def get_account_alias(aws_account_id: str) -> str | None:
    """Get the IAM account alias for a member account.

    Returns the alias string, or None if no alias is set.
    """
    target_session = await assume_groundwork_admin(aws_account_id)
    async with target_session.client("iam") as iam:
        resp = await iam.list_account_aliases()
        aliases = resp.get("AccountAliases", [])
        return aliases[0] if aliases else None


async def set_account_alias(aws_account_id: str, alias: str) -> None:
    """Set the IAM account alias for a member account.

    AWS only allows one alias per account; creating a new alias overwrites
    the previous one.
    """
    target_session = await assume_groundwork_admin(aws_account_id)
    async with target_session.client("iam") as iam:
        await iam.create_account_alias(AccountAlias=alias)
    logger.info("Set account alias '%s' for account %s", alias, aws_account_id)


async def delete_account_alias(aws_account_id: str, alias: str) -> None:
    """Delete the IAM account alias for a member account."""
    target_session = await assume_groundwork_admin(aws_account_id)
    async with target_session.client("iam") as iam:
        await iam.delete_account_alias(AccountAlias=alias)
    logger.info("Deleted account alias '%s' from account %s", alias, aws_account_id)
```

**Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=. pytest tests/unit/services/test_aws.py::TestGetAccountAlias tests/unit/services/test_aws.py::TestSetAccountAlias tests/unit/services/test_aws.py::TestDeleteAccountAlias -v`
Expected: 4 tests PASS

**Step 5: Commit**

```bash
git add backend/services/aws.py tests/unit/services/test_aws.py
git commit -m "feat: add IAM account alias functions to AWS service layer"
```

---

### Task 2: AWS Service Layer — Account Color Functions (UXC via SigV4)

**Files:**
- Modify: `backend/services/aws.py` (append after alias functions)
- Test: `tests/unit/services/test_aws.py` (append new test classes)

**Step 1: Write the failing tests**

Add to `tests/unit/services/test_aws.py`:

```python
class TestGetAccountColor:
    async def test_returns_color_when_set(self):
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.content = b'{"color": "red"}'
        mock_response.json.return_value = {"color": "red"}

        with (
            patch.object(
                aws,
                "assume_groundwork_admin",
                new_callable=AsyncMock,
            ) as mock_assume,
            patch("backend.services.aws.httpx.AsyncClient") as mock_httpx_cls,
        ):
            mock_session = MagicMock()
            mock_creds = MagicMock()
            mock_creds.access_key = "AKIAEXAMPLE"
            mock_creds.secret_key = "secret"
            mock_creds.token = "token"
            mock_session.get_credentials.return_value.get_frozen_credentials.return_value = (
                mock_creds
            )
            mock_assume.return_value = mock_session

            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.request.return_value = mock_response
            mock_httpx_cls.return_value = mock_client

            result = await aws.get_account_color("123456789012")

        assert result == "red"
        mock_client.request.assert_called_once()
        call_kwargs = mock_client.request.call_args
        assert call_kwargs[0][0] == "GET"

    async def test_returns_none_when_no_color(self):
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.content = b'{"color": "none"}'
        mock_response.json.return_value = {"color": "none"}

        with (
            patch.object(
                aws,
                "assume_groundwork_admin",
                new_callable=AsyncMock,
            ) as mock_assume,
            patch("backend.services.aws.httpx.AsyncClient") as mock_httpx_cls,
        ):
            mock_session = MagicMock()
            mock_creds = MagicMock()
            mock_creds.access_key = "AKIAEXAMPLE"
            mock_creds.secret_key = "secret"
            mock_creds.token = "token"
            mock_session.get_credentials.return_value.get_frozen_credentials.return_value = (
                mock_creds
            )
            mock_assume.return_value = mock_session

            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.request.return_value = mock_response
            mock_httpx_cls.return_value = mock_client

            result = await aws.get_account_color("123456789012")

        assert result is None


class TestSetAccountColor:
    async def test_sets_color(self):
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.content = b'{"color": "green"}'
        mock_response.json.return_value = {"color": "green"}
        mock_response.raise_for_status = MagicMock()

        with (
            patch.object(
                aws,
                "assume_groundwork_admin",
                new_callable=AsyncMock,
            ) as mock_assume,
            patch("backend.services.aws.httpx.AsyncClient") as mock_httpx_cls,
        ):
            mock_session = MagicMock()
            mock_creds = MagicMock()
            mock_creds.access_key = "AKIAEXAMPLE"
            mock_creds.secret_key = "secret"
            mock_creds.token = "token"
            mock_session.get_credentials.return_value.get_frozen_credentials.return_value = (
                mock_creds
            )
            mock_assume.return_value = mock_session

            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.request.return_value = mock_response
            mock_httpx_cls.return_value = mock_client

            await aws.set_account_color("123456789012", "green")

        mock_client.request.assert_called_once()
        call_kwargs = mock_client.request.call_args
        assert call_kwargs[0][0] == "PUT"


class TestDeleteAccountColor:
    async def test_deletes_color(self):
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.content = b""
        mock_response.raise_for_status = MagicMock()

        with (
            patch.object(
                aws,
                "assume_groundwork_admin",
                new_callable=AsyncMock,
            ) as mock_assume,
            patch("backend.services.aws.httpx.AsyncClient") as mock_httpx_cls,
        ):
            mock_session = MagicMock()
            mock_creds = MagicMock()
            mock_creds.access_key = "AKIAEXAMPLE"
            mock_creds.secret_key = "secret"
            mock_creds.token = "token"
            mock_session.get_credentials.return_value.get_frozen_credentials.return_value = (
                mock_creds
            )
            mock_assume.return_value = mock_session

            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.request.return_value = mock_response
            mock_httpx_cls.return_value = mock_client

            await aws.delete_account_color("123456789012")

        mock_client.request.assert_called_once()
        call_kwargs = mock_client.request.call_args
        assert call_kwargs[0][0] == "DELETE"
```

**Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=. pytest tests/unit/services/test_aws.py::TestGetAccountColor -v`
Expected: FAIL — `AttributeError: module 'backend.services.aws' has no attribute 'get_account_color'`

**Step 3: Write the implementation**

Add new import at top of `backend/services/aws.py` (after the existing imports around line 13):

```python
import httpx
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.credentials import Credentials
```

Add after the account alias functions:

```python
# ---------------------------------------------------------------------------
# Account color management (UXC service — no boto3 support)
# ---------------------------------------------------------------------------

UXC_ENDPOINT = "https://uxc.us-east-1.api.aws/v1/account-color"
UXC_SERVICE = "uxc"
UXC_REGION = "us-east-1"

VALID_ACCOUNT_COLORS = frozenset(
    {"none", "pink", "purple", "darkBlue", "lightBlue", "teal", "green", "yellow", "orange", "red"}
)


async def _uxc_request(
    session, method: str, body: str | None = None
) -> dict | None:
    """Make a SigV4-signed request to the UXC service.

    ``session`` is an aioboto3.Session with credentials for the target account.
    """
    creds = session.get_credentials().get_frozen_credentials()
    botocore_creds = Credentials(
        access_key=creds.access_key,
        secret_key=creds.secret_key,
        token=creds.token,
    )

    headers = {"Content-Type": "application/json"}
    aws_request = AWSRequest(method=method, url=UXC_ENDPOINT, data=body, headers=headers)
    SigV4Auth(botocore_creds, UXC_SERVICE, UXC_REGION).add_auth(aws_request)

    async with httpx.AsyncClient() as client:
        response = await client.request(
            method,
            UXC_ENDPOINT,
            headers=dict(aws_request.headers),
            content=body,
        )
        response.raise_for_status()
        return response.json() if response.content else None


async def get_account_color(aws_account_id: str) -> str | None:
    """Get the console color for a member account.

    Returns the color string (e.g. "red", "green"), or None if no color
    is set (color is "none").
    """
    target_session = await assume_groundwork_admin(aws_account_id)
    result = await _uxc_request(target_session, "GET")
    color = result.get("color") if result else None
    return None if color == "none" else color


async def set_account_color(aws_account_id: str, color: str) -> None:
    """Set the console color for a member account."""
    target_session = await assume_groundwork_admin(aws_account_id)
    body = json.dumps({"color": color})
    await _uxc_request(target_session, "PUT", body)
    logger.info("Set account color '%s' for account %s", color, aws_account_id)


async def delete_account_color(aws_account_id: str) -> None:
    """Delete the console color for a member account."""
    target_session = await assume_groundwork_admin(aws_account_id)
    await _uxc_request(target_session, "DELETE")
    logger.info("Deleted account color from account %s", aws_account_id)
```

**Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=. pytest tests/unit/services/test_aws.py::TestGetAccountColor tests/unit/services/test_aws.py::TestSetAccountColor tests/unit/services/test_aws.py::TestDeleteAccountColor -v`
Expected: 4 tests PASS

**Step 5: Commit**

```bash
git add backend/services/aws.py tests/unit/services/test_aws.py
git commit -m "feat: add UXC account color functions with SigV4 signing"
```

---

### Task 3: Account Metadata Cache

**Files:**
- Create: `backend/services/account_metadata.py`
- Test: `tests/unit/services/test_account_metadata.py`

**Step 1: Write the failing tests**

Create `tests/unit/services/test_account_metadata.py`:

```python
"""Tests for the account metadata cache."""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from backend.services import account_metadata


class TestGetAccountMetadata:
    async def test_fetches_from_aws_on_cache_miss(self):
        account_metadata._cache.clear()

        with (
            patch.object(
                account_metadata,
                "_fetch_metadata",
                new_callable=AsyncMock,
                return_value={"alias": "prod", "color": "red"},
            ) as mock_fetch,
        ):
            result = await account_metadata.get_account_metadata("123456789012")

        assert result["alias"] == "prod"
        assert result["color"] == "red"
        mock_fetch.assert_called_once_with("123456789012")

    async def test_returns_cached_entry_when_fresh(self):
        account_metadata._cache["123456789012"] = {
            "alias": "prod",
            "color": "red",
            "fetched_at": datetime.now(timezone.utc),
        }

        with patch.object(
            account_metadata,
            "_fetch_metadata",
            new_callable=AsyncMock,
        ) as mock_fetch:
            result = await account_metadata.get_account_metadata("123456789012")

        assert result["alias"] == "prod"
        mock_fetch.assert_not_called()
        account_metadata._cache.clear()

    async def test_refetches_when_stale(self):
        account_metadata._cache["123456789012"] = {
            "alias": "old",
            "color": None,
            "fetched_at": datetime.now(timezone.utc) - timedelta(minutes=20),
        }

        with patch.object(
            account_metadata,
            "_fetch_metadata",
            new_callable=AsyncMock,
            return_value={"alias": "new", "color": "green"},
        ) as mock_fetch:
            result = await account_metadata.get_account_metadata("123456789012")

        assert result["alias"] == "new"
        assert result["color"] == "green"
        mock_fetch.assert_called_once()
        account_metadata._cache.clear()


class TestGetAllAccountMetadata:
    async def test_fetches_all_concurrently(self):
        account_metadata._cache.clear()
        ids = ["111111111111", "222222222222"]

        async def fake_fetch(account_id):
            return {"alias": f"alias-{account_id[-1]}", "color": None}

        with patch.object(
            account_metadata,
            "_fetch_metadata",
            side_effect=fake_fetch,
        ):
            result = await account_metadata.get_all_account_metadata(ids)

        assert result["111111111111"]["alias"] == "alias-1"
        assert result["222222222222"]["alias"] == "alias-2"
        account_metadata._cache.clear()


class TestWriteThrough:
    async def test_update_alias_updates_cache(self):
        account_metadata._cache["123456789012"] = {
            "alias": "old",
            "color": "red",
            "fetched_at": datetime.now(timezone.utc),
        }

        account_metadata.update_cached_alias("123456789012", "new")

        assert account_metadata._cache["123456789012"]["alias"] == "new"
        account_metadata._cache.clear()

    async def test_update_color_updates_cache(self):
        account_metadata._cache["123456789012"] = {
            "alias": "prod",
            "color": "red",
            "fetched_at": datetime.now(timezone.utc),
        }

        account_metadata.update_cached_color("123456789012", "green")

        assert account_metadata._cache["123456789012"]["color"] == "green"
        account_metadata._cache.clear()

    async def test_update_creates_entry_if_missing(self):
        account_metadata._cache.clear()

        account_metadata.update_cached_alias("123456789012", "new")

        assert account_metadata._cache["123456789012"]["alias"] == "new"
        assert account_metadata._cache["123456789012"]["color"] is None
        account_metadata._cache.clear()
```

**Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=. pytest tests/unit/services/test_account_metadata.py -v`
Expected: FAIL — `ModuleNotFoundError` or `ImportError`

**Step 3: Write the implementation**

Create `backend/services/account_metadata.py`:

```python
"""In-memory TTL cache for account alias and color metadata.

These values are fetched from AWS (IAM for alias, UXC for color) and
cached to avoid per-request API calls. Cache TTL is 15 minutes.
Write-through updates are applied when changes are made via Groundwork.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

CACHE_TTL = timedelta(minutes=15)

# Keyed by AWS account ID → {"alias": str|None, "color": str|None, "fetched_at": datetime}
_cache: dict[str, dict] = {}


async def _fetch_metadata(aws_account_id: str) -> dict:
    """Fetch alias and color from AWS for a single account."""
    from backend.services.aws import get_account_alias, get_account_color

    alias, color = await asyncio.gather(
        get_account_alias(aws_account_id),
        get_account_color(aws_account_id),
        return_exceptions=True,
    )

    if isinstance(alias, Exception):
        logger.warning("Failed to fetch alias for account %s: %s", aws_account_id, alias)
        alias = None
    if isinstance(color, Exception):
        logger.warning("Failed to fetch color for account %s: %s", aws_account_id, color)
        color = None

    return {"alias": alias, "color": color}


def _is_fresh(entry: dict) -> bool:
    """Check if a cache entry is within the TTL."""
    return datetime.now(timezone.utc) - entry["fetched_at"] < CACHE_TTL


async def get_account_metadata(aws_account_id: str) -> dict:
    """Get alias and color for a single account, using cache when fresh."""
    entry = _cache.get(aws_account_id)
    if entry and _is_fresh(entry):
        return entry

    data = await _fetch_metadata(aws_account_id)
    entry = {**data, "fetched_at": datetime.now(timezone.utc)}
    _cache[aws_account_id] = entry
    return entry


async def get_all_account_metadata(aws_account_ids: list[str]) -> dict[str, dict]:
    """Get alias and color for multiple accounts concurrently.

    Returns a dict keyed by AWS account ID.
    """
    stale_ids = []
    result: dict[str, dict] = {}

    for account_id in aws_account_ids:
        entry = _cache.get(account_id)
        if entry and _is_fresh(entry):
            result[account_id] = entry
        else:
            stale_ids.append(account_id)

    if stale_ids:
        fetched = await asyncio.gather(
            *[_fetch_metadata(aid) for aid in stale_ids],
            return_exceptions=True,
        )
        now = datetime.now(timezone.utc)
        for account_id, data in zip(stale_ids, fetched):
            if isinstance(data, Exception):
                logger.warning(
                    "Failed to fetch metadata for account %s: %s", account_id, data
                )
                data = {"alias": None, "color": None}
            entry = {**data, "fetched_at": now}
            _cache[account_id] = entry
            result[account_id] = entry

    return result


def update_cached_alias(aws_account_id: str, alias: str | None) -> None:
    """Write-through update for alias."""
    entry = _cache.get(aws_account_id)
    if entry:
        entry["alias"] = alias
        entry["fetched_at"] = datetime.now(timezone.utc)
    else:
        _cache[aws_account_id] = {
            "alias": alias,
            "color": None,
            "fetched_at": datetime.now(timezone.utc),
        }


def update_cached_color(aws_account_id: str, color: str | None) -> None:
    """Write-through update for color."""
    entry = _cache.get(aws_account_id)
    if entry:
        entry["color"] = color
        entry["fetched_at"] = datetime.now(timezone.utc)
    else:
        _cache[aws_account_id] = {
            "alias": None,
            "color": color,
            "fetched_at": datetime.now(timezone.utc),
        }
```

**Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=. pytest tests/unit/services/test_account_metadata.py -v`
Expected: All 7 tests PASS

**Step 5: Commit**

```bash
git add backend/services/account_metadata.py tests/unit/services/test_account_metadata.py
git commit -m "feat: add in-memory TTL cache for account alias and color metadata"
```

---

### Task 4: Schema Changes — AccountResponse and AccountUpdate

**Files:**
- Modify: `backend/schemas/account.py`
- Test: `tests/unit/schemas/test_account.py` (create)

**Step 1: Write the failing tests**

Create `tests/unit/schemas/test_account.py`:

```python
"""Tests for account schema validation."""

import pytest
from pydantic import ValidationError

from backend.schemas.account import AccountUpdate


class TestAccountUpdateAliasValidation:
    def test_valid_alias(self):
        body = AccountUpdate(alias="my-prod-account")
        assert body.alias == "my-prod-account"

    def test_alias_min_length(self):
        with pytest.raises(ValidationError):
            AccountUpdate(alias="ab")

    def test_alias_max_length(self):
        with pytest.raises(ValidationError):
            AccountUpdate(alias="a" * 64)

    def test_alias_no_uppercase(self):
        with pytest.raises(ValidationError):
            AccountUpdate(alias="MyAlias")

    def test_alias_no_special_chars(self):
        with pytest.raises(ValidationError):
            AccountUpdate(alias="my_alias!")

    def test_alias_empty_string_allowed(self):
        """Empty string means 'delete the alias'."""
        body = AccountUpdate(alias="")
        assert body.alias == ""


class TestAccountUpdateColorValidation:
    def test_valid_color(self):
        body = AccountUpdate(color="red")
        assert body.color == "red"

    def test_valid_camelcase_color(self):
        body = AccountUpdate(color="darkBlue")
        assert body.color == "darkBlue"

    def test_invalid_color(self):
        with pytest.raises(ValidationError):
            AccountUpdate(color="magenta")

    def test_none_color_clears(self):
        body = AccountUpdate(color="none")
        assert body.color == "none"

    def test_empty_string_clears(self):
        body = AccountUpdate(color="")
        assert body.color == ""
```

**Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=. pytest tests/unit/schemas/test_account.py -v`
Expected: FAIL — fields `alias` and `color` don't exist on `AccountUpdate`

**Step 3: Write the implementation**

Modify `backend/schemas/account.py`. Replace entire file:

```python
from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class AccountCreate(BaseModel):
    account_name: str = Field(min_length=1, max_length=50)
    account_email: EmailStr
    organizational_unit: str = Field(min_length=1, max_length=128, pattern=r"^(ou-|r-)[a-z0-9-]+$")
    sso_user_email: EmailStr


VALID_COLORS = Literal[
    "none", "pink", "purple", "darkBlue", "lightBlue", "teal", "green", "yellow", "orange", "red"
]


class AccountUpdate(BaseModel):
    account_name: Optional[str] = Field(None, min_length=1, max_length=50)
    organizational_unit: Optional[str] = Field(
        None, min_length=1, max_length=128, pattern=r"^(ou-|r-)[a-z0-9-]+$"
    )
    sso_user_email: Optional[EmailStr] = None
    alias: Optional[str] = Field(
        None, min_length=0, max_length=63, pattern=r"^$|^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$"
    )
    color: Optional[str] = Field(None)

    def model_post_init(self, __context) -> None:
        if self.color is not None and self.color != "":
            valid = {
                "none", "pink", "purple", "darkBlue", "lightBlue",
                "teal", "green", "yellow", "orange", "red",
            }
            if self.color not in valid:
                raise ValueError(
                    f"Invalid color '{self.color}'. "
                    f"Must be one of: {', '.join(sorted(valid))}"
                )


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
    alias: Optional[str] = None
    color: Optional[str] = None

    model_config = {"from_attributes": True}
```

**Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=. pytest tests/unit/schemas/test_account.py -v`
Expected: All 10 tests PASS

**Step 5: Commit**

```bash
git add backend/schemas/account.py tests/unit/schemas/test_account.py
git commit -m "feat: add alias and color fields to account schemas"
```

---

### Task 5: Router Changes — PATCH, GET, and LIST Endpoints

**Files:**
- Modify: `backend/routers/accounts.py`
- Modify: `tests/unit/routers/test_accounts.py`

**Step 1: Write the failing tests**

Add to `tests/unit/routers/test_accounts.py`:

```python
class TestUpdateAccountAlias:
    async def test_set_alias(self, client, db_session):
        admin, session_id = await _create_authenticated_user(db_session, is_admin=True)

        account = Account(
            account_name="Alias Test",
            account_email=f"alias-{id(db_session)}@example.com",
            organizational_unit="ou-1234",
            sso_user_email="sso@example.com",
            created_by=admin.id,
            status="active",
            aws_account_id="111111111111",
        )
        db_session.add(account)
        await db_session.flush()

        with (
            patch(
                "backend.routers.accounts.aws.set_account_alias", new_callable=AsyncMock
            ),
            patch(
                "backend.routers.accounts.account_metadata.update_cached_alias"
            ),
        ):
            response = await client.patch(
                f"/api/accounts/{account.id}",
                json={"alias": "my-alias"},
                cookies=_cookies(session_id),
            )

        assert response.status_code == 200

    async def test_set_alias_requires_active_account(self, client, db_session):
        admin, session_id = await _create_authenticated_user(db_session, is_admin=True)

        account = Account(
            account_name="Pending Account",
            account_email=f"pending-{id(db_session)}@example.com",
            organizational_unit="ou-1234",
            sso_user_email="sso@example.com",
            created_by=admin.id,
            status="pending",
        )
        db_session.add(account)
        await db_session.flush()

        response = await client.patch(
            f"/api/accounts/{account.id}",
            json={"alias": "my-alias"},
            cookies=_cookies(session_id),
        )

        assert response.status_code == 400

    async def test_delete_alias_with_empty_string(self, client, db_session):
        admin, session_id = await _create_authenticated_user(db_session, is_admin=True)

        account = Account(
            account_name="Del Alias Test",
            account_email=f"del-alias-{id(db_session)}@example.com",
            organizational_unit="ou-1234",
            sso_user_email="sso@example.com",
            created_by=admin.id,
            status="active",
            aws_account_id="222222222222",
        )
        db_session.add(account)
        await db_session.flush()

        with (
            patch(
                "backend.routers.accounts.account_metadata.get_account_metadata",
                new_callable=AsyncMock,
                return_value={"alias": "old-alias", "color": None, "fetched_at": None},
            ),
            patch(
                "backend.routers.accounts.aws.delete_account_alias", new_callable=AsyncMock
            ),
            patch(
                "backend.routers.accounts.account_metadata.update_cached_alias"
            ),
        ):
            response = await client.patch(
                f"/api/accounts/{account.id}",
                json={"alias": ""},
                cookies=_cookies(session_id),
            )

        assert response.status_code == 200


class TestUpdateAccountColor:
    async def test_set_color(self, client, db_session):
        admin, session_id = await _create_authenticated_user(db_session, is_admin=True)

        account = Account(
            account_name="Color Test",
            account_email=f"color-{id(db_session)}@example.com",
            organizational_unit="ou-1234",
            sso_user_email="sso@example.com",
            created_by=admin.id,
            status="active",
            aws_account_id="333333333333",
        )
        db_session.add(account)
        await db_session.flush()

        with (
            patch(
                "backend.routers.accounts.aws.set_account_color", new_callable=AsyncMock
            ),
            patch(
                "backend.routers.accounts.account_metadata.update_cached_color"
            ),
        ):
            response = await client.patch(
                f"/api/accounts/{account.id}",
                json={"color": "red"},
                cookies=_cookies(session_id),
            )

        assert response.status_code == 200

    async def test_delete_color_with_none(self, client, db_session):
        admin, session_id = await _create_authenticated_user(db_session, is_admin=True)

        account = Account(
            account_name="Del Color Test",
            account_email=f"del-color-{id(db_session)}@example.com",
            organizational_unit="ou-1234",
            sso_user_email="sso@example.com",
            created_by=admin.id,
            status="active",
            aws_account_id="444444444444",
        )
        db_session.add(account)
        await db_session.flush()

        with (
            patch(
                "backend.routers.accounts.aws.delete_account_color", new_callable=AsyncMock
            ),
            patch(
                "backend.routers.accounts.account_metadata.update_cached_color"
            ),
        ):
            response = await client.patch(
                f"/api/accounts/{account.id}",
                json={"color": "none"},
                cookies=_cookies(session_id),
            )

        assert response.status_code == 200


class TestAccountResponseIncludesMetadata:
    async def test_get_account_includes_alias_and_color(self, client, db_session):
        admin, session_id = await _create_authenticated_user(db_session, is_admin=True)

        account = Account(
            account_name="Meta Test",
            account_email=f"meta-{id(db_session)}@example.com",
            organizational_unit="ou-1234",
            sso_user_email="sso@example.com",
            created_by=admin.id,
            status="active",
            aws_account_id="555555555555",
        )
        db_session.add(account)
        await db_session.flush()

        with patch(
            "backend.routers.accounts.account_metadata.get_account_metadata",
            new_callable=AsyncMock,
            return_value={"alias": "prod", "color": "red", "fetched_at": None},
        ):
            response = await client.get(
                f"/api/accounts/{account.id}",
                cookies=_cookies(session_id),
            )

        assert response.status_code == 200
        data = response.json()
        assert data["alias"] == "prod"
        assert data["color"] == "red"

    async def test_list_accounts_includes_alias_and_color(self, client, db_session):
        admin, session_id = await _create_authenticated_user(db_session, is_admin=True)

        account = Account(
            account_name="List Meta Test",
            account_email=f"list-meta-{id(db_session)}@example.com",
            organizational_unit="ou-1234",
            sso_user_email="sso@example.com",
            created_by=admin.id,
            status="active",
            aws_account_id="666666666666",
        )
        db_session.add(account)
        await db_session.flush()

        with patch(
            "backend.routers.accounts.account_metadata.get_all_account_metadata",
            new_callable=AsyncMock,
            return_value={
                "666666666666": {"alias": "staging", "color": "yellow", "fetched_at": None}
            },
        ):
            response = await client.get(
                "/api/accounts",
                cookies=_cookies(session_id),
            )

        assert response.status_code == 200
        data = response.json()
        matched = [a for a in data if a["aws_account_id"] == "666666666666"]
        assert len(matched) == 1
        assert matched[0]["alias"] == "staging"
        assert matched[0]["color"] == "yellow"
```

**Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=. pytest tests/unit/routers/test_accounts.py::TestUpdateAccountAlias -v`
Expected: FAIL — tests fail because the router doesn't handle alias/color yet

**Step 3: Write the implementation**

Modify `backend/routers/accounts.py`. Replace entire file:

```python
"""Account management endpoints."""

import logging
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.dependencies.auth import get_current_admin, get_current_user
from backend.exceptions import ConflictError, GroundworkError, NotFoundError
from backend.models.account import Account
from backend.models.job import Job
from backend.models.user import User
from backend.schemas.account import AccountCreate, AccountResponse, AccountUpdate
from backend.services import aws
from backend.services.audit import log_event
from backend.services import account_metadata
from backend.services.jobs import execute_job

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


@router.get("", response_model=list[AccountResponse])
async def list_accounts(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(Account).order_by(Account.created_at.desc()))
    accounts = list(result.scalars().all())

    # Fetch metadata for all accounts with AWS account IDs
    aws_ids = [a.aws_account_id for a in accounts if a.aws_account_id]
    try:
        metadata = await account_metadata.get_all_account_metadata(aws_ids) if aws_ids else {}
    except Exception:
        logger.warning("Failed to fetch account metadata for list", exc_info=True)
        metadata = {}

    responses = []
    for acct in accounts:
        resp = AccountResponse.model_validate(acct)
        meta = metadata.get(acct.aws_account_id) if acct.aws_account_id else None
        if meta:
            resp.alias = meta.get("alias")
            resp.color = meta.get("color")
        responses.append(resp)

    return responses


@router.post("", response_model=AccountResponse, status_code=201)
async def create_account(
    body: AccountCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    # Check for duplicate email
    existing = await db.execute(
        select(Account).where(Account.account_email == body.account_email)
    )
    if existing.scalar_one_or_none():
        raise ConflictError("An account with this email already exists")

    account = Account(
        account_name=body.account_name,
        account_email=body.account_email,
        organizational_unit=body.organizational_unit,
        sso_user_email=body.sso_user_email,
        created_by=admin.id,
    )
    db.add(account)
    await db.flush()

    job = Job(
        account_id=account.id,
        job_type="provision_account",
        started_by=admin.id,
    )
    db.add(job)
    await db.flush()

    await log_event(
        db,
        action="account.create",
        user_id=admin.id,
        resource_type="account",
        resource_id=str(account.id),
        detail=body.model_dump(),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    await db.refresh(account)
    background_tasks.add_task(execute_job, str(job.id))
    return account


@router.get("/{account_id}", response_model=AccountResponse)
async def get_account(
    account_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(Account).where(Account.id == account_id))
    account = result.scalar_one_or_none()
    if account is None:
        raise NotFoundError("Account not found")

    resp = AccountResponse.model_validate(account)

    if account.aws_account_id:
        try:
            meta = await account_metadata.get_account_metadata(account.aws_account_id)
            resp.alias = meta.get("alias")
            resp.color = meta.get("color")
        except Exception:
            logger.warning(
                "Failed to fetch metadata for account %s", account.aws_account_id, exc_info=True
            )

    return resp


@router.patch("/{account_id}", response_model=AccountResponse)
async def update_account(
    account_id: UUID,
    body: AccountUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    result = await db.execute(select(Account).where(Account.id == account_id))
    account = result.scalar_one_or_none()
    if account is None:
        raise NotFoundError("Account not found")

    update_data = body.model_dump(exclude_unset=True)

    # Handle alias and color updates (require active account with AWS ID)
    alias_update = update_data.pop("alias", None)
    color_update = update_data.pop("color", None)

    if (alias_update is not None or color_update is not None):
        if account.status != "active" or not account.aws_account_id:
            raise GroundworkError(
                "Account must be active to modify alias or color", status_code=400
            )

    # Apply standard DB field updates
    _UPDATABLE = {"account_name", "organizational_unit", "sso_user_email"}
    for field, value in update_data.items():
        if field in _UPDATABLE:
            setattr(account, field, value)

    # Handle alias update via AWS IAM
    if alias_update is not None:
        if alias_update == "":
            # Delete alias — need to know current alias first
            current_meta = await account_metadata.get_account_metadata(account.aws_account_id)
            current_alias = current_meta.get("alias")
            if current_alias:
                await aws.delete_account_alias(account.aws_account_id, current_alias)
            account_metadata.update_cached_alias(account.aws_account_id, None)
        else:
            await aws.set_account_alias(account.aws_account_id, alias_update)
            account_metadata.update_cached_alias(account.aws_account_id, alias_update)

    # Handle color update via AWS UXC
    if color_update is not None:
        if color_update in ("", "none"):
            await aws.delete_account_color(account.aws_account_id)
            account_metadata.update_cached_color(account.aws_account_id, None)
        else:
            await aws.set_account_color(account.aws_account_id, color_update)
            account_metadata.update_cached_color(account.aws_account_id, color_update)

    db.add(account)
    await log_event(
        db,
        action="account.update",
        user_id=admin.id,
        resource_type="account",
        resource_id=str(account.id),
        detail=body.model_dump(exclude_unset=True),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    await db.flush()
    await db.refresh(account)

    # Build response with metadata
    resp = AccountResponse.model_validate(account)
    if account.aws_account_id:
        try:
            meta = await account_metadata.get_account_metadata(account.aws_account_id)
            resp.alias = meta.get("alias")
            resp.color = meta.get("color")
        except Exception:
            logger.warning(
                "Failed to fetch metadata for account %s",
                account.aws_account_id,
                exc_info=True,
            )

    return resp
```

**Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=. pytest tests/unit/routers/test_accounts.py -v`
Expected: All tests PASS (both old and new)

**Step 5: Commit**

```bash
git add backend/routers/accounts.py tests/unit/routers/test_accounts.py
git commit -m "feat: add alias and color support to account CRUD endpoints"
```

---

### Task 6: Frontend — API Types and Color Map Constant

**Files:**
- Modify: `frontend/src/api/accounts.ts`
- Create: `frontend/src/lib/aws-colors.ts`

**Step 1: Update TypeScript types**

Modify `frontend/src/api/accounts.ts`. Add `alias` and `color` to `AccountResponse` and `AccountUpdate`:

In the `AccountResponse` interface, add after `updated_at: string`:
```typescript
  alias: string | null
  color: string | null
```

In the `AccountUpdate` interface, add after `sso_user_email?: string`:
```typescript
  alias?: string
  color?: string
```

**Step 2: Create the color map**

Create `frontend/src/lib/aws-colors.ts`:

```typescript
export const AWS_COLORS: Record<string, string> = {
  pink: '#e0529e',
  purple: '#8b5cf6',
  darkBlue: '#1d4ed8',
  lightBlue: '#38bdf8',
  teal: '#14b8a6',
  green: '#22c55e',
  yellow: '#eab308',
  orange: '#f97316',
  red: '#ef4444',
}

export const AWS_COLOR_NAMES = [
  'pink',
  'purple',
  'darkBlue',
  'lightBlue',
  'teal',
  'green',
  'yellow',
  'orange',
  'red',
] as const

export type AwsColor = (typeof AWS_COLOR_NAMES)[number]

export function awsColorLabel(color: string): string {
  switch (color) {
    case 'darkBlue':
      return 'Dark Blue'
    case 'lightBlue':
      return 'Light Blue'
    default:
      return color.charAt(0).toUpperCase() + color.slice(1)
  }
}
```

**Step 3: Verify frontend builds**

Run: `cd frontend && npx tsc --noEmit`
Expected: No type errors

**Step 4: Commit**

```bash
git add frontend/src/api/accounts.ts frontend/src/lib/aws-colors.ts
git commit -m "feat: add alias/color to frontend types and create color map constant"
```

---

### Task 7: Frontend — Dashboard Color Square and Alias Display

**Files:**
- Modify: `frontend/src/pages/Dashboard.tsx`

**Step 1: Add imports**

At top of `Dashboard.tsx`, add:
```typescript
import { AWS_COLORS } from '@/lib/aws-colors'
```

**Step 2: Update search filter**

In the `grouped` useMemo (around line 114-121), extend the search filter to include alias:
```typescript
filtered = filtered.filter(
  (a) =>
    a.account_name.toLowerCase().includes(q) ||
    a.account_email.toLowerCase().includes(q) ||
    (a.aws_account_id ?? '').includes(q) ||
    a.organizational_unit.toLowerCase().includes(q) ||
    (a.alias ?? '').toLowerCase().includes(q)
)
```

**Step 3: Update the Name table cell**

Replace the Name `<TableCell>` (lines 226-232) with:
```tsx
<TableCell>
  <div className="flex items-center gap-2">
    {account.color && AWS_COLORS[account.color] && (
      <span
        className="inline-block size-3 rounded-sm shrink-0"
        style={{ backgroundColor: AWS_COLORS[account.color] }}
      />
    )}
    <div>
      <Link
        to={`/accounts/${account.id}`}
        className="font-medium hover:underline"
      >
        {account.account_name}
      </Link>
      {account.alias && (
        <div className="text-xs text-muted-foreground">{account.alias}</div>
      )}
    </div>
  </div>
</TableCell>
```

**Step 4: Verify frontend builds**

Run: `cd frontend && npx tsc --noEmit`
Expected: No type errors

**Step 5: Commit**

```bash
git add frontend/src/pages/Dashboard.tsx
git commit -m "feat: show account color square and alias on dashboard"
```

---

### Task 8: Frontend — Account Detail Color Picker and Alias Editor

**Files:**
- Modify: `frontend/src/pages/AccountDetail.tsx`

**Step 1: Add imports and state**

At top of `AccountDetail.tsx`, add imports:
```typescript
import { Pencil, Check, X } from 'lucide-react'
import { useMutation } from '@tanstack/react-query'
import { updateAccount } from '@/api/accounts'
import { Input } from '@/components/ui/input'
import { AWS_COLORS, AWS_COLOR_NAMES, awsColorLabel } from '@/lib/aws-colors'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
```

Note: `DropdownMenu` is already imported — just ensure `useMutation`, `updateAccount`, `Input`, `Pencil`, `Check`, `X`, and the aws-colors imports are present. Do not duplicate existing imports.

**Step 2: Add state and mutation inside the component**

Inside `AccountDetail` function, after the existing state declarations (around line 96), add:
```typescript
// Alias editing state
const [editingAlias, setEditingAlias] = useState(false)
const [aliasValue, setAliasValue] = useState('')

const aliasMutation = useMutation({
  mutationFn: (alias: string) => updateAccount(id!, { alias }),
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ['account', id] })
    queryClient.invalidateQueries({ queryKey: ['accounts'] })
    setEditingAlias(false)
    toast.success('Account alias updated')
  },
  onError: (err) => {
    toast.error(err instanceof ApiError ? err.detail : 'Failed to update alias')
  },
})

const colorMutation = useMutation({
  mutationFn: (color: string) => updateAccount(id!, { color }),
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ['account', id] })
    queryClient.invalidateQueries({ queryKey: ['accounts'] })
    toast.success('Account color updated')
  },
  onError: (err) => {
    toast.error(err instanceof ApiError ? err.detail : 'Failed to update color')
  },
})
```

**Step 3: Add color and alias rows to the account detail card**

In the `<dl>` grid inside CardContent (after the "Last Updated" `<div>`, around line 282), add:
```tsx
<div>
  <dt className="text-muted-foreground">Account Alias</dt>
  <dd>
    {editingAlias ? (
      <div className="flex items-center gap-1">
        <Input
          value={aliasValue}
          onChange={(e) => setAliasValue(e.target.value)}
          placeholder="e.g. my-prod-account"
          className="h-7 w-48 text-sm"
          pattern="[a-z0-9-]*"
        />
        <Button
          variant="ghost"
          size="xs"
          onClick={() => aliasMutation.mutate(aliasValue)}
          disabled={aliasMutation.isPending}
        >
          <Check className="size-3.5" />
        </Button>
        <Button
          variant="ghost"
          size="xs"
          onClick={() => setEditingAlias(false)}
        >
          <X className="size-3.5" />
        </Button>
      </div>
    ) : (
      <span className="flex items-center gap-1.5">
        {account.alias ?? '—'}
        {isAdmin && account.status === 'active' && (
          <Button
            variant="ghost"
            size="xs"
            onClick={() => {
              setAliasValue(account.alias ?? '')
              setEditingAlias(true)
            }}
          >
            <Pencil className="size-3" />
          </Button>
        )}
      </span>
    )}
  </dd>
</div>
<div>
  <dt className="text-muted-foreground">Account Color</dt>
  <dd>
    {isAdmin && account.status === 'active' ? (
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="xs" className="gap-1.5" disabled={colorMutation.isPending}>
            {account.color && AWS_COLORS[account.color] ? (
              <>
                <span
                  className="inline-block size-3 rounded-sm"
                  style={{ backgroundColor: AWS_COLORS[account.color] }}
                />
                {awsColorLabel(account.color)}
              </>
            ) : (
              'None'
            )}
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent>
          <DropdownMenuItem onClick={() => colorMutation.mutate('none')}>
            None
          </DropdownMenuItem>
          {AWS_COLOR_NAMES.map((c) => (
            <DropdownMenuItem key={c} onClick={() => colorMutation.mutate(c)}>
              <span
                className="inline-block size-3 rounded-sm mr-2"
                style={{ backgroundColor: AWS_COLORS[c] }}
              />
              {awsColorLabel(c)}
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
    ) : (
      <span className="flex items-center gap-1.5">
        {account.color && AWS_COLORS[account.color] ? (
          <>
            <span
              className="inline-block size-3 rounded-sm"
              style={{ backgroundColor: AWS_COLORS[account.color] }}
            />
            {awsColorLabel(account.color)}
          </>
        ) : (
          '—'
        )}
      </span>
    )}
  </dd>
</div>
```

**Step 4: Verify frontend builds**

Run: `cd frontend && npx tsc --noEmit`
Expected: No type errors

**Step 5: Commit**

```bash
git add frontend/src/pages/AccountDetail.tsx
git commit -m "feat: add color picker and alias editor to account detail page"
```

---

### Task 9: Bootstrap Template — Add IAM and UXC Permissions

**Files:**
- Modify: `backend/services/aws.py` (the `_build_bootstrap_template` function)
- Modify: `tests/unit/services/test_aws.py` (add test for new permissions)

**Step 1: Write the failing test**

Add to `tests/unit/services/test_aws.py`:

```python
class TestBuildBootstrapTemplatePermissions:
    def test_template_includes_alias_and_color_permissions(self):
        template_json = aws._build_bootstrap_template("111111111111")
        template = json.loads(template_json)
        role_props = template["Resources"]["AdminRole"]["Properties"]

        # The role uses AdministratorAccess which covers all permissions,
        # so no additional policy statement is needed. Verify the managed
        # policy is still present.
        managed_arns = role_props["ManagedPolicyArns"]
        assert "arn:aws:iam::aws:policy/AdministratorAccess" in managed_arns
```

**Step 2: Run the test**

Run: `PYTHONPATH=. pytest tests/unit/services/test_aws.py::TestBuildBootstrapTemplatePermissions -v`
Expected: PASS — The GroundworkAdmin role already has `AdministratorAccess` which includes all IAM and UXC permissions. No template change is needed.

**Important note:** The existing bootstrap template uses `AdministratorAccess` managed policy, which already grants `iam:*` and `uxc:*`. No modification to the template is required. The design doc's "Bootstrap Role Permissions" section documents what permissions are needed, but they're already covered.

**Step 3: Commit**

```bash
git add tests/unit/services/test_aws.py
git commit -m "test: verify bootstrap template covers alias and color permissions"
```

---

### Task 10: Full Test Suite and Lint

**Step 1: Run the full test suite**

Run: `PYTHONPATH=. pytest`
Expected: All tests PASS

**Step 2: Run linting and formatting**

Run: `black backend/ tests/ && isort backend/ tests/`
Run: `flake8 backend/ tests/`
Expected: No errors

**Step 3: Fix any issues found**

If any tests fail or lint errors appear, fix them before proceeding.

**Step 4: Run frontend build check**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

**Step 5: Final commit if any fixes were needed**

```bash
git add -A
git commit -m "chore: lint and formatting fixes for alias/color feature"
```
