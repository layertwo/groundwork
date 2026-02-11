# Metadata Sync & DB-Backed Alias/Color Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move account alias/color from in-memory cache to database columns, add periodic metadata sync with staggered API calls, and add role drift detection with a fix-drift action.

**Architecture:** Alias and color stored as DB columns on Account model. Periodic sync (piggybacking on existing sync_accounts job) refreshes alias, color, and role drift status from AWS, staggering API calls evenly across the sync interval. The in-memory cache is removed entirely. A new fix-drift endpoint reuses the existing update_role job handler.

**Tech Stack:** Python/FastAPI, async SQLAlchemy, Alembic migrations, aioboto3, httpx + SigV4Auth for UXC, React/TypeScript frontend.

---

### Task 1: Alembic Migration — Add alias and color columns to accounts

**Files:**
- Create: `alembic/versions/<auto>_add_alias_color_to_accounts.py` (via autogenerate)
- Modify: `backend/models/account.py`

**Step 1: Add columns to Account model**

In `backend/models/account.py`, add after the `error_message` field (line 33):

```python
    alias: Mapped[Optional[str]] = mapped_column(String(63), nullable=True)
    color: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
```

Also add `String` to the sqlalchemy import if not already present (it is — line 6).

**Step 2: Generate migration**

Run: `PYTHONPATH=. alembic revision --autogenerate -m "add alias and color columns to accounts"`
Expected: New migration file created

**Step 3: Apply migration**

Run: `PYTHONPATH=. alembic upgrade head`
Expected: Migration applied successfully

**Step 4: Commit**

```bash
git add backend/models/account.py alembic/versions/
git commit -m "feat: add alias and color columns to accounts table"
```

---

### Task 2: Simplify accounts router — remove cache, read from DB

**Files:**
- Modify: `backend/routers/accounts.py`
- Modify: `tests/unit/routers/test_accounts.py`

**Step 1: Write/update tests**

Update existing tests in `tests/unit/routers/test_accounts.py`. The `TestAccountResponseIncludesMetadata` tests need to be rewritten since metadata now comes from the DB, not the cache.

Replace `TestAccountResponseIncludesMetadata` with:

```python
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
            alias="prod",
            color="red",
        )
        db_session.add(account)
        await db_session.flush()

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
            alias="staging",
            color="yellow",
        )
        db_session.add(account)
        await db_session.flush()

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

Update `TestUpdateAccountAlias.test_set_alias` — remove cache mock, add DB assertion:

```python
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

        with patch(
            "backend.routers.accounts.aws.set_account_alias", new_callable=AsyncMock
        ):
            response = await client.patch(
                f"/api/accounts/{account.id}",
                json={"alias": "my-alias"},
                cookies=_cookies(session_id),
            )

        assert response.status_code == 200
        assert response.json()["alias"] == "my-alias"
```

Update `TestUpdateAccountAlias.test_delete_alias_with_empty_string` — now reads current alias from DB:

```python
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
            alias="old-alias",
        )
        db_session.add(account)
        await db_session.flush()

        with patch(
            "backend.routers.accounts.aws.delete_account_alias", new_callable=AsyncMock
        ):
            response = await client.patch(
                f"/api/accounts/{account.id}",
                json={"alias": ""},
                cookies=_cookies(session_id),
            )

        assert response.status_code == 200
        assert response.json()["alias"] is None
```

Update `TestUpdateAccountColor.test_set_color` — remove cache mock:

```python
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

        with patch(
            "backend.routers.accounts.aws.set_account_color", new_callable=AsyncMock
        ):
            response = await client.patch(
                f"/api/accounts/{account.id}",
                json={"color": "red"},
                cookies=_cookies(session_id),
            )

        assert response.status_code == 200
        assert response.json()["color"] == "red"
```

Update `TestUpdateAccountColor.test_delete_color_with_none` — remove cache mock:

```python
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
            color="red",
        )
        db_session.add(account)
        await db_session.flush()

        with patch(
            "backend.routers.accounts.aws.delete_account_color", new_callable=AsyncMock
        ):
            response = await client.patch(
                f"/api/accounts/{account.id}",
                json={"color": "none"},
                cookies=_cookies(session_id),
            )

        assert response.status_code == 200
        assert response.json()["color"] is None
```

**Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=. pytest tests/unit/routers/test_accounts.py -o "addopts=" -v`
Expected: Failures because router still uses cache

**Step 3: Rewrite the router**

Replace `backend/routers/accounts.py` entirely:

```python
"""Account management endpoints."""

import asyncio
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
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
from backend.services.jobs import execute_job

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


@router.get("", response_model=list[AccountResponse])
async def list_accounts(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(Account).order_by(Account.created_at.desc()))
    return list(result.scalars().all())


@router.post("", response_model=AccountResponse, status_code=201)
async def create_account(
    body: AccountCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    # Check for duplicate email
    existing = await db.execute(
        select(Account).where(Account.account_email == body.account_email)
    )
    if existing.scalar_one_or_none() is not None:
        raise ConflictError("An account with this email already exists")

    account = Account(
        account_name=body.account_name,
        account_email=body.account_email,
        organizational_unit=body.organizational_unit,
        sso_user_email=body.sso_user_email,
        status="pending",
        created_by=admin.id,
    )
    db.add(account)

    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise ConflictError("An account with this email already exists")

    job = Job(
        account_id=account.id,
        job_type="provision_account",
        status="pending",
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
        detail={"account_name": body.account_name, "account_email": body.account_email},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    await db.refresh(account)

    # Launch provisioning job as background task, retain reference
    task = asyncio.create_task(execute_job(job.id))
    request.app.state.background_tasks.add(task)
    task.add_done_callback(request.app.state.background_tasks.discard)

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
    return account


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

    if alias_update is not None or color_update is not None:
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
            if account.alias:
                await aws.delete_account_alias(account.aws_account_id, account.alias)
            account.alias = None
        else:
            await aws.set_account_alias(account.aws_account_id, alias_update)
            account.alias = alias_update

    # Handle color update via AWS UXC
    if color_update is not None:
        if color_update in ("", "none"):
            await aws.delete_account_color(account.aws_account_id)
            account.color = None
        else:
            await aws.set_account_color(account.aws_account_id, color_update)
            account.color = color_update

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
    return account
```

**Key changes from current router:**
- Removed `account_metadata` import and all cache calls
- `list_accounts`: returns ORM objects directly (no manual response building)
- `get_account`: returns ORM object directly (no metadata enrichment)
- `update_account`: writes alias/color to `account.alias`/`account.color` DB columns instead of cache. Reads current alias from `account.alias` instead of cache for deletion.
- `create_account`: preserved exactly as-is

**Step 4: Run tests**

Run: `PYTHONPATH=. pytest tests/unit/routers/test_accounts.py -o "addopts=" -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add backend/routers/accounts.py tests/unit/routers/test_accounts.py
git commit -m "refactor: read alias/color from DB instead of in-memory cache"
```

---

### Task 3: Remove in-memory cache module

**Files:**
- Delete: `backend/services/account_metadata.py`
- Delete: `tests/unit/services/test_account_metadata.py`

**Step 1: Delete the files**

```bash
rm backend/services/account_metadata.py tests/unit/services/test_account_metadata.py
```

**Step 2: Verify no remaining references**

Run: `grep -r "account_metadata" backend/ tests/`
Expected: No results

**Step 3: Run tests**

Run: `PYTHONPATH=. pytest tests/unit/ -o "addopts=" -v`
Expected: All tests pass (no imports of deleted module)

**Step 4: Commit**

```bash
git add -A
git commit -m "refactor: remove in-memory account metadata cache"
```

---

### Task 4: Add get_iam_role_metadata to AWS service layer

**Files:**
- Modify: `backend/services/aws.py`
- Modify: `tests/unit/services/test_aws.py`

**Step 1: Write the failing tests**

Add to `tests/unit/services/test_aws.py`:

```python
class TestGetIamRoleMetadata:
    async def test_returns_metadata_for_existing_role(self):
        _, iam_stubber = await create_stubbed_client("iam")
        iam_stubber.add_response(
            "get_role",
            {
                "Role": {
                    "RoleName": "TestRole",
                    "Arn": "arn:aws:iam::123456789012:role/TestRole",
                    "MaxSessionDuration": 3600,
                    "RoleLastUsed": {
                        "LastUsedDate": datetime(2025, 6, 15, 12, 0, 0),
                    },
                    "Path": "/",
                    "RoleId": "AROAEXAMPLE",
                    "CreateDate": datetime(2025, 1, 1),
                    "AssumeRolePolicyDocument": "{}",
                },
            },
            expected_params={"RoleName": "TestRole"},
        )
        iam_stubber.add_response(
            "list_attached_role_policies",
            {
                "AttachedPolicies": [
                    {"PolicyName": "ReadOnly", "PolicyArn": "arn:aws:iam::aws:policy/ReadOnlyAccess"},
                ],
                "IsTruncated": False,
            },
            expected_params={"RoleName": "TestRole"},
        )
        iam_stubber.activate()

        with patch.object(
            aws,
            "assume_groundwork_admin",
            new_callable=AsyncMock,
            return_value=_stubbed_session({"iam": iam_stubber}),
        ):
            result = await aws.get_iam_role_metadata("123456789012", "TestRole")

        assert result["exists"] is True
        assert result["max_session_duration"] == 3600
        assert result["attached_policy_arns"] == ["arn:aws:iam::aws:policy/ReadOnlyAccess"]
        assert result["last_used"] == datetime(2025, 6, 15, 12, 0, 0)
        iam_stubber.assert_no_pending_responses()

    async def test_returns_not_exists_for_missing_role(self):
        _, iam_stubber = await create_stubbed_client("iam")
        iam_stubber.add_client_error(
            "get_role",
            service_error_code="NoSuchEntity",
            service_message="Role not found",
            expected_params={"RoleName": "MissingRole"},
        )
        iam_stubber.activate()

        with patch.object(
            aws,
            "assume_groundwork_admin",
            new_callable=AsyncMock,
            return_value=_stubbed_session({"iam": iam_stubber}),
        ):
            result = await aws.get_iam_role_metadata("123456789012", "MissingRole")

        assert result["exists"] is False
        assert result["max_session_duration"] is None
        assert result["attached_policy_arns"] == []
        assert result["last_used"] is None
```

**Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=. pytest tests/unit/services/test_aws.py::TestGetIamRoleMetadata -o "addopts=" -v`
Expected: FAIL — `AttributeError: module has no attribute 'get_iam_role_metadata'`

**Step 3: Write the implementation**

Add to `backend/services/aws.py` after the account alias functions (before the UXC section):

```python
async def get_iam_role_metadata(aws_account_id: str, role_name: str) -> dict:
    """Get current IAM role metadata from a member account.

    Returns dict with:
    - exists: bool
    - max_session_duration: int | None
    - attached_policy_arns: list[str]
    - last_used: datetime | None
    """
    target_session = await assume_groundwork_admin(aws_account_id)
    async with target_session.client("iam") as iam:
        try:
            role_resp = await iam.get_role(RoleName=role_name)
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "NoSuchEntity":
                return {
                    "exists": False,
                    "max_session_duration": None,
                    "attached_policy_arns": [],
                    "last_used": None,
                }
            raise

        role_data = role_resp["Role"]
        last_used = role_data.get("RoleLastUsed", {}).get("LastUsedDate")

        policies_resp = await iam.list_attached_role_policies(RoleName=role_name)
        policy_arns = [p["PolicyArn"] for p in policies_resp.get("AttachedPolicies", [])]

        return {
            "exists": True,
            "max_session_duration": role_data.get("MaxSessionDuration"),
            "attached_policy_arns": sorted(policy_arns),
            "last_used": last_used,
        }
```

**Step 4: Run tests**

Run: `PYTHONPATH=. pytest tests/unit/services/test_aws.py::TestGetIamRoleMetadata -o "addopts=" -v`
Expected: 2 tests PASS

**Step 5: Commit**

```bash
git add backend/services/aws.py tests/unit/services/test_aws.py
git commit -m "feat: add get_iam_role_metadata for role drift detection"
```

---

### Task 5: Add sync_account_metadata to sync job

**Files:**
- Modify: `backend/services/jobs.py`
- Create: `tests/unit/services/test_sync_metadata.py`

**Step 1: Write the failing tests**

Create `tests/unit/services/test_sync_metadata.py`:

```python
"""Tests for account metadata sync."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from backend.models.account import Account
from backend.models.role import Role
from backend.services.jobs import sync_account_metadata


class TestSyncAccountMetadata:
    async def test_updates_alias_and_color(self, db_session):
        account = Account(
            account_name="Sync Test",
            account_email="sync@example.com",
            organizational_unit="ou-1234",
            sso_user_email="sso@example.com",
            created_by="00000000-0000-0000-0000-000000000001",
            status="active",
            aws_account_id="111111111111",
        )
        db_session.add(account)
        await db_session.flush()

        with (
            patch(
                "backend.services.jobs.aws.get_account_alias",
                new_callable=AsyncMock,
                return_value="prod",
            ),
            patch(
                "backend.services.jobs.aws.get_account_color",
                new_callable=AsyncMock,
                return_value="red",
            ),
        ):
            await sync_account_metadata(account, db_session)

        await db_session.refresh(account)
        assert account.alias == "prod"
        assert account.color == "red"

    async def test_detects_deleted_role(self, db_session):
        account = Account(
            account_name="Drift Test",
            account_email="drift@example.com",
            organizational_unit="ou-1234",
            sso_user_email="sso@example.com",
            created_by="00000000-0000-0000-0000-000000000001",
            status="active",
            aws_account_id="222222222222",
        )
        db_session.add(account)
        await db_session.flush()

        role = Role(
            account_id=account.id,
            role_name="DeletedRole",
            role_arn="arn:aws:iam::222222222222:role/DeletedRole",
            status="active",
            managed_policy_arns=["arn:aws:iam::aws:policy/ReadOnlyAccess"],
        )
        db_session.add(role)
        await db_session.flush()

        with (
            patch(
                "backend.services.jobs.aws.get_account_alias",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "backend.services.jobs.aws.get_account_color",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "backend.services.jobs.aws.get_iam_role_metadata",
                new_callable=AsyncMock,
                return_value={
                    "exists": False,
                    "max_session_duration": None,
                    "attached_policy_arns": [],
                    "last_used": None,
                },
            ),
        ):
            await sync_account_metadata(account, db_session)

        await db_session.refresh(role)
        assert role.status == "drifted"

    async def test_detects_policy_drift(self, db_session):
        account = Account(
            account_name="Policy Drift",
            account_email="policy-drift@example.com",
            organizational_unit="ou-1234",
            sso_user_email="sso@example.com",
            created_by="00000000-0000-0000-0000-000000000001",
            status="active",
            aws_account_id="333333333333",
        )
        db_session.add(account)
        await db_session.flush()

        role = Role(
            account_id=account.id,
            role_name="DriftedRole",
            role_arn="arn:aws:iam::333333333333:role/DriftedRole",
            status="active",
            managed_policy_arns=["arn:aws:iam::aws:policy/ReadOnlyAccess"],
            api_session_duration=900,
            console_session_duration=3600,
        )
        db_session.add(role)
        await db_session.flush()

        with (
            patch(
                "backend.services.jobs.aws.get_account_alias",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "backend.services.jobs.aws.get_account_color",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "backend.services.jobs.aws.get_iam_role_metadata",
                new_callable=AsyncMock,
                return_value={
                    "exists": True,
                    "max_session_duration": 3600,
                    "attached_policy_arns": [
                        "arn:aws:iam::aws:policy/AdministratorAccess"
                    ],
                    "last_used": datetime(2025, 6, 15, tzinfo=timezone.utc),
                },
            ),
        ):
            await sync_account_metadata(account, db_session)

        await db_session.refresh(role)
        assert role.status == "drifted"

    async def test_no_drift_when_matching(self, db_session):
        account = Account(
            account_name="No Drift",
            account_email="no-drift@example.com",
            organizational_unit="ou-1234",
            sso_user_email="sso@example.com",
            created_by="00000000-0000-0000-0000-000000000001",
            status="active",
            aws_account_id="444444444444",
        )
        db_session.add(account)
        await db_session.flush()

        role = Role(
            account_id=account.id,
            role_name="GoodRole",
            role_arn="arn:aws:iam::444444444444:role/GoodRole",
            status="active",
            managed_policy_arns=["arn:aws:iam::aws:policy/ReadOnlyAccess"],
            api_session_duration=900,
            console_session_duration=3600,
        )
        db_session.add(role)
        await db_session.flush()

        with (
            patch(
                "backend.services.jobs.aws.get_account_alias",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "backend.services.jobs.aws.get_account_color",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "backend.services.jobs.aws.get_iam_role_metadata",
                new_callable=AsyncMock,
                return_value={
                    "exists": True,
                    "max_session_duration": 3600,
                    "attached_policy_arns": [
                        "arn:aws:iam::aws:policy/ReadOnlyAccess"
                    ],
                    "last_used": None,
                },
            ),
        ):
            await sync_account_metadata(account, db_session)

        await db_session.refresh(role)
        assert role.status == "active"
```

**Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=. pytest tests/unit/services/test_sync_metadata.py -o "addopts=" -v`
Expected: FAIL — `ImportError: cannot import name 'sync_account_metadata'`

**Step 3: Write the implementation**

Add to `backend/services/jobs.py`, before `run_sync_accounts`:

```python
async def sync_account_metadata(account: Account, db: AsyncSession) -> None:
    """Sync alias, color, and role drift for a single account."""
    # Fetch alias and color concurrently
    alias_result, color_result = await asyncio.gather(
        aws.get_account_alias(account.aws_account_id),
        aws.get_account_color(account.aws_account_id),
        return_exceptions=True,
    )

    if isinstance(alias_result, Exception):
        logger.warning("Failed to fetch alias for %s: %s", account.aws_account_id, alias_result)
    else:
        account.alias = alias_result

    if isinstance(color_result, Exception):
        logger.warning("Failed to fetch color for %s: %s", account.aws_account_id, color_result)
    else:
        account.color = color_result

    db.add(account)

    # Fetch role metadata concurrently
    result = await db.execute(
        select(Role).where(Role.account_id == account.id, Role.status == "active")
    )
    active_roles = list(result.scalars().all())

    if active_roles:
        metadata_results = await asyncio.gather(
            *[
                aws.get_iam_role_metadata(account.aws_account_id, role.role_name)
                for role in active_roles
            ],
            return_exceptions=True,
        )

        for role, meta in zip(active_roles, metadata_results):
            if isinstance(meta, Exception):
                logger.warning(
                    "Failed to fetch metadata for role %s: %s", role.role_name, meta
                )
                continue

            if not meta["exists"]:
                role.status = "drifted"
                role.error_message = "Role not found in AWS"
                db.add(role)
                continue

            # Check for drift
            expected_max_duration = max(role.api_session_duration, role.console_session_duration)
            actual_policies = sorted(meta["attached_policy_arns"])
            expected_policies = sorted(role.managed_policy_arns)

            drifted = False
            drift_reasons = []

            if meta["max_session_duration"] != expected_max_duration:
                drifted = True
                drift_reasons.append("max session duration changed")

            if actual_policies != expected_policies:
                drifted = True
                drift_reasons.append("managed policies changed")

            if drifted:
                role.status = "drifted"
                role.error_message = "Drift detected: " + ", ".join(drift_reasons)
            # else: leave status as "active"

            # Update last_used_at if available
            if meta["last_used"] is not None:
                role.last_used_at = meta["last_used"]

            db.add(role)
```

Also add the `Role` import at the top of `jobs.py` if not already present (it is — line 14).

Then in `run_sync_accounts`, add the metadata sync phase after the main reconciliation loop completes (before setting `job.status = "completed"`). Add after the `for org_acct in org_accounts:` loop ends and before `job.status = "completed"`:

```python
        # Phase 2: Sync metadata (alias, color, role drift) — staggered
        active_accounts = [
            a for a in existing_map.values()
            if a.status == "active" and a.aws_account_id
        ]
        # Also include newly imported active accounts
        # (they were added to DB but not in existing_map)
        result = await db.execute(
            select(Account).where(
                Account.status == "active",
                Account.aws_account_id.isnot(None),
            )
        )
        active_accounts = list(result.scalars().all())

        if active_accounts and settings.sync_interval_minutes > 0:
            delay = (settings.sync_interval_minutes * 60) / len(active_accounts)
            for i, acct in enumerate(active_accounts):
                try:
                    await sync_account_metadata(acct, db)
                    await db.commit()
                except Exception:
                    logger.warning(
                        "Metadata sync failed for account %s",
                        acct.aws_account_id,
                        exc_info=True,
                    )
                    await db.rollback()
                if i < len(active_accounts) - 1:
                    await asyncio.sleep(delay)
```

Import `settings` at the top of `jobs.py`:

```python
from backend.config import settings
```

**Step 4: Run tests**

Run: `PYTHONPATH=. pytest tests/unit/services/test_sync_metadata.py -o "addopts=" -v`
Expected: All 4 tests PASS

**Step 5: Commit**

```bash
git add backend/services/jobs.py tests/unit/services/test_sync_metadata.py
git commit -m "feat: add staggered metadata sync for alias, color, and role drift"
```

---

### Task 6: Add fix-drift endpoint

**Files:**
- Modify: `backend/routers/roles.py`
- Modify: `tests/unit/routers/test_roles.py`
- Modify: `frontend/src/api/roles.ts`

**Step 1: Write the failing test**

Add to `tests/unit/routers/test_roles.py` (using the same auth helper pattern already in the file):

```python
class TestFixDrift:
    async def test_fix_drift_creates_update_job(self, client, db_session):
        admin, session_id = await _create_authenticated_user(db_session, is_admin=True)

        account = Account(
            account_name="Drift Fix",
            account_email=f"drift-fix-{id(db_session)}@example.com",
            organizational_unit="ou-1234",
            sso_user_email="sso@example.com",
            created_by=admin.id,
            status="active",
            aws_account_id="999999999999",
        )
        db_session.add(account)
        await db_session.flush()

        role = Role(
            account_id=account.id,
            role_name="DriftedRole",
            role_arn="arn:aws:iam::999999999999:role/DriftedRole",
            status="drifted",
            error_message="Drift detected: managed policies changed",
            managed_policy_arns=["arn:aws:iam::aws:policy/ReadOnlyAccess"],
        )
        db_session.add(role)
        await db_session.flush()

        response = await client.post(
            f"/api/accounts/{account.id}/roles/{role.id}/fix-drift",
            cookies=_cookies(session_id),
        )

        assert response.status_code == 202

        # Verify role status changed to updating
        await db_session.refresh(role)
        assert role.status == "updating"

        # Verify job was created
        from sqlalchemy import select
        from backend.models.job import Job
        result = await db_session.execute(
            select(Job).where(
                Job.account_id == account.id,
                Job.job_type == "update_role",
            )
        )
        job = result.scalar_one()
        assert job.result["role_id"] == str(role.id)

    async def test_fix_drift_rejects_non_drifted_role(self, client, db_session):
        admin, session_id = await _create_authenticated_user(db_session, is_admin=True)

        account = Account(
            account_name="No Drift",
            account_email=f"no-drift-{id(db_session)}@example.com",
            organizational_unit="ou-1234",
            sso_user_email="sso@example.com",
            created_by=admin.id,
            status="active",
            aws_account_id="888888888888",
        )
        db_session.add(account)
        await db_session.flush()

        role = Role(
            account_id=account.id,
            role_name="ActiveRole",
            role_arn="arn:aws:iam::888888888888:role/ActiveRole",
            status="active",
            managed_policy_arns=[],
        )
        db_session.add(role)
        await db_session.flush()

        response = await client.post(
            f"/api/accounts/{account.id}/roles/{role.id}/fix-drift",
            cookies=_cookies(session_id),
        )

        assert response.status_code == 400
```

**Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=. pytest tests/unit/routers/test_roles.py::TestFixDrift -o "addopts=" -v`
Expected: FAIL — 404 (route doesn't exist)

**Step 3: Write the implementation**

Add to `backend/routers/roles.py`:

```python
@router.post(
    "/api/accounts/{account_id}/roles/{role_id}/fix-drift",
    status_code=202,
)
async def fix_drift(
    account_id: UUID,
    role_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    result = await db.execute(
        select(Role).where(Role.id == role_id, Role.account_id == account_id)
    )
    role = result.scalar_one_or_none()
    if role is None:
        raise NotFoundError("Role not found")

    if role.status != "drifted":
        raise GroundworkError("Role is not in drifted state", status_code=400)

    # Build changes dict with all IAM-affecting fields to re-apply
    changes = {
        "managed_policy_arns": role.managed_policy_arns,
        "api_session_duration": role.api_session_duration,
        "console_session_duration": role.console_session_duration,
    }
    if role.inline_policy is not None:
        changes["inline_policy"] = role.inline_policy

    role.status = "updating"
    role.error_message = None
    db.add(role)

    job = Job(
        account_id=account_id,
        job_type="update_role",
        status="pending",
        started_by=admin.id,
        result={"role_id": str(role.id), "changes": changes},
    )
    db.add(job)
    await db.flush()

    await log_event(
        db,
        action="role.fix_drift",
        user_id=admin.id,
        resource_type="role",
        resource_id=str(role.id),
        detail={"account_id": str(account_id)},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    await db.commit()

    task = asyncio.create_task(execute_job(job.id))
    request.app.state.background_tasks.add(task)
    task.add_done_callback(request.app.state.background_tasks.discard)

    return Response(status_code=202)
```

Ensure needed imports are present at top of `roles.py`: `asyncio`, `Response`, `GroundworkError`.

**Step 4: Add frontend API function**

Add to `frontend/src/api/roles.ts`:

```typescript
export function fixDrift(
  accountId: string,
  roleId: string,
): Promise<void> {
  return apiFetch<void>(`/api/accounts/${accountId}/roles/${roleId}/fix-drift`, {
    method: 'POST',
  })
}
```

**Step 5: Run tests**

Run: `PYTHONPATH=. pytest tests/unit/routers/test_roles.py::TestFixDrift -o "addopts=" -v`
Expected: 2 tests PASS

**Step 6: Commit**

```bash
git add backend/routers/roles.py tests/unit/routers/test_roles.py frontend/src/api/roles.ts
git commit -m "feat: add fix-drift endpoint for drifted roles"
```

---

### Task 7: Frontend — drift badge and Fix Drift button

**Files:**
- Modify: `frontend/src/pages/AccountDetail.tsx`

**Step 1: Update statusVariant**

In the `statusVariant` function, add a case for `'drifted'`:

```typescript
function statusVariant(status: string) {
  switch (status) {
    case 'active':
    case 'completed':
      return 'default' as const
    case 'failed':
    case 'drifted':
      return 'destructive' as const
    default:
      return 'secondary' as const
  }
}
```

**Step 2: Add Fix Drift button**

In the admin action buttons section of the role card (where Edit and Delete are), add a Fix Drift button:

After the Edit button and before the Delete button, add:

```tsx
{role.status === 'drifted' && (
  <Button
    variant="outline"
    size="xs"
    onClick={async () => {
      try {
        await fixDrift(id!, role.id)
        refetchRoles()
        toast.success('Drift fix started')
      } catch (err) {
        toast.error(err instanceof ApiError ? err.detail : 'Failed to fix drift')
      }
    }}
  >
    Fix Drift
  </Button>
)}
```

Add `fixDrift` to the imports from `@/api/roles`.

**Step 3: Verify frontend builds**

Run: `cd /Users/lcmessen/groundwork/frontend && npx tsc --noEmit`
Expected: No type errors

**Step 4: Commit**

```bash
git add frontend/src/pages/AccountDetail.tsx
git commit -m "feat: add drift badge and Fix Drift button to role cards"
```

---

### Task 8: Full test suite and lint

**Step 1: Run the full test suite**

Run: `PYTHONPATH=. pytest tests/unit/ -o "addopts="`
Expected: All tests pass (except pre-existing test_roles failures)

**Step 2: Run formatting and linting**

Run: `black backend/ tests/ && isort backend/ tests/`
Run: `flake8 backend/ tests/`
Expected: No errors

**Step 3: Frontend type check**

Run: `cd /Users/lcmessen/groundwork/frontend && npx tsc --noEmit`
Expected: No errors

**Step 4: Final commit if fixes needed**

```bash
git add -A
git commit -m "chore: lint and formatting fixes"
```
