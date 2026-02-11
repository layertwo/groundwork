# Org Account Sync & Bootstrap Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a background job that discovers existing AWS Organization accounts, imports/reconciles them in Groundwork's DB, and bootstraps each active account via StackSets.

**Architecture:** New `POST /api/jobs` endpoint triggers a `sync_accounts` job. The job calls Organizations `ListAccounts` + `ListParents`, creates/updates Account records, and spawns individual `bootstrap_account` jobs for accounts needing StackSet deployment. A new `aws_status` field on Account tracks the AWS-side lifecycle (ACTIVE/SUSPENDED/PENDING_CLOSURE). The frontend gets a "Sync Accounts" button, default-hidden suspended accounts, and new job type filters.

**Tech Stack:** FastAPI, async SQLAlchemy 2.0, asyncpg, Alembic, aioboto3, React + TypeScript + TanStack Query + shadcn/ui

---

### Task 1: Add `aws_status` column to Account model

**Files:**
- Modify: `backend/models/account.py:20-31`
- Modify: `backend/schemas/account.py:23-38`

**Step 1: Add `aws_status` field to Account model**

In `backend/models/account.py`, add after the `status` field (line 26):

```python
aws_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
```

**Step 2: Add `aws_status` to AccountResponse schema**

In `backend/schemas/account.py`, add `aws_status` field to `AccountResponse` (after `status` on line 30):

```python
aws_status: Optional[str]
```

**Step 3: Add `aws_status` to frontend AccountResponse interface**

In `frontend/src/api/accounts.ts`, add after the `status` field (line 10):

```typescript
aws_status: string | null
```

**Step 4: Generate and apply Alembic migration**

Run:
```bash
PYTHONPATH=. alembic revision --autogenerate -m "add aws_status column to accounts"
```

Review the generated migration, then run:
```bash
PYTHONPATH=. alembic upgrade head
```

**Step 5: Commit**

```bash
git add backend/models/account.py backend/schemas/account.py frontend/src/api/accounts.ts alembic/versions/
git commit -m "feat: add aws_status column to Account model"
```

---

### Task 2: Add `list_org_accounts` and `get_account_ou` to AWS service

**Files:**
- Modify: `backend/services/aws.py` (add after `move_account_to_ou`, around line 119)
- Test: `tests/unit/services/test_aws.py`

**Step 1: Write failing tests for `list_org_accounts`**

In `tests/unit/services/test_aws.py`, add at the end of the file:

```python
class TestListOrgAccounts:
    async def test_returns_all_accounts_except_management(self):
        """list_org_accounts filters out the management account."""
        _, stubber = await create_stubbed_client("organizations")
        stubber.add_response(
            "list_accounts",
            {
                "Accounts": [
                    {
                        "Id": "111111111111",
                        "Name": "Management",
                        "Email": "mgmt@example.com",
                        "Status": "ACTIVE",
                        "JoinedMethod": "INVITED",
                        "JoinedTimestamp": datetime(2024, 1, 1),
                        "Arn": "arn:aws:organizations::111111111111:account/o-abc/111111111111",
                    },
                    {
                        "Id": "222222222222",
                        "Name": "Workload",
                        "Email": "work@example.com",
                        "Status": "ACTIVE",
                        "JoinedMethod": "CREATED",
                        "JoinedTimestamp": datetime(2024, 6, 1),
                        "Arn": "arn:aws:organizations::111111111111:account/o-abc/222222222222",
                    },
                    {
                        "Id": "333333333333",
                        "Name": "Suspended",
                        "Email": "sus@example.com",
                        "Status": "SUSPENDED",
                        "JoinedMethod": "CREATED",
                        "JoinedTimestamp": datetime(2024, 3, 1),
                        "Arn": "arn:aws:organizations::111111111111:account/o-abc/333333333333",
                    },
                ],
            },
        )
        # get_caller_identity to discover management account ID
        _, sts_stubber = await create_stubbed_client("sts")
        sts_stubber.add_response(
            "get_caller_identity",
            {
                "UserId": "AROA:GroundworkOrganizations",
                "Account": "111111111111",
                "Arn": "arn:aws:sts::111111111111:assumed-role/GroundworkManagementRole/GroundworkOrganizations",
            },
        )
        stubber.activate()
        sts_stubber.activate()

        mgmt_session = _stubbed_session(
            {"organizations": stubber, "sts": sts_stubber}
        )

        with patch.object(
            aws,
            "get_management_session",
            new_callable=AsyncMock,
            return_value=mgmt_session,
        ):
            accounts = await aws.list_org_accounts()

        assert len(accounts) == 2
        ids = [a["aws_account_id"] for a in accounts]
        assert "111111111111" not in ids
        assert "222222222222" in ids
        assert "333333333333" in ids

    async def test_paginates_accounts(self):
        """list_org_accounts handles pagination."""
        _, stubber = await create_stubbed_client("organizations")
        stubber.add_response(
            "list_accounts",
            {
                "Accounts": [
                    {
                        "Id": "222222222222",
                        "Name": "Page1",
                        "Email": "p1@example.com",
                        "Status": "ACTIVE",
                        "JoinedMethod": "CREATED",
                        "JoinedTimestamp": datetime(2024, 1, 1),
                        "Arn": "arn:aws:organizations::111:account/o-abc/222222222222",
                    },
                ],
                "NextToken": "token123",
            },
        )
        stubber.add_response(
            "list_accounts",
            {
                "Accounts": [
                    {
                        "Id": "333333333333",
                        "Name": "Page2",
                        "Email": "p2@example.com",
                        "Status": "ACTIVE",
                        "JoinedMethod": "CREATED",
                        "JoinedTimestamp": datetime(2024, 2, 1),
                        "Arn": "arn:aws:organizations::111:account/o-abc/333333333333",
                    },
                ],
            },
        )
        _, sts_stubber = await create_stubbed_client("sts")
        sts_stubber.add_response(
            "get_caller_identity",
            {
                "UserId": "AROA:session",
                "Account": "111111111111",
                "Arn": "arn:aws:sts::111111111111:assumed-role/role/session",
            },
        )
        stubber.activate()
        sts_stubber.activate()

        mgmt_session = _stubbed_session(
            {"organizations": stubber, "sts": sts_stubber}
        )

        with patch.object(
            aws,
            "get_management_session",
            new_callable=AsyncMock,
            return_value=mgmt_session,
        ):
            accounts = await aws.list_org_accounts()

        assert len(accounts) == 2
        assert accounts[0]["aws_account_id"] == "222222222222"
        assert accounts[1]["aws_account_id"] == "333333333333"


class TestGetAccountOu:
    async def test_returns_ou_id(self):
        _, stubber = await create_stubbed_client("organizations")
        stubber.add_response(
            "list_parents",
            {
                "Parents": [
                    {"Id": "ou-abc1-12345678", "Type": "ORGANIZATIONAL_UNIT"},
                ]
            },
            expected_params={"ChildId": "222222222222"},
        )
        stubber.activate()

        mgmt_session = _stubbed_session({"organizations": stubber})

        with patch.object(
            aws,
            "get_management_session",
            new_callable=AsyncMock,
            return_value=mgmt_session,
        ):
            ou_id = await aws.get_account_ou("222222222222")

        assert ou_id == "ou-abc1-12345678"
        stubber.assert_no_pending_responses()

    async def test_returns_root_id_when_at_root(self):
        _, stubber = await create_stubbed_client("organizations")
        stubber.add_response(
            "list_parents",
            {
                "Parents": [
                    {"Id": "r-abc1", "Type": "ROOT"},
                ]
            },
            expected_params={"ChildId": "222222222222"},
        )
        stubber.activate()

        mgmt_session = _stubbed_session({"organizations": stubber})

        with patch.object(
            aws,
            "get_management_session",
            new_callable=AsyncMock,
            return_value=mgmt_session,
        ):
            ou_id = await aws.get_account_ou("222222222222")

        assert ou_id == "r-abc1"
```

**Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=. pytest tests/unit/services/test_aws.py::TestListOrgAccounts -v -o "addopts="`
Expected: FAIL — `list_org_accounts` does not exist

**Step 3: Implement `list_org_accounts` and `get_account_ou`**

In `backend/services/aws.py`, add after the `move_account_to_ou` function (after line 119):

```python
async def list_org_accounts() -> list[dict]:
    """List all accounts in the AWS Organization, excluding the management account.

    Returns a list of dicts with keys: aws_account_id, name, email, status.
    Handles pagination automatically.
    """
    session = await get_management_session()

    # Discover management account ID to filter it out
    async with session.client("sts") as sts:
        identity = await sts.get_caller_identity()
        mgmt_account_id = identity["Account"]

    accounts: list[dict] = []
    async with session.client("organizations") as orgs:
        kwargs: dict = {}
        while True:
            resp = await orgs.list_accounts(**kwargs)
            for acct in resp.get("Accounts", []):
                if acct["Id"] == mgmt_account_id:
                    continue
                accounts.append(
                    {
                        "aws_account_id": acct["Id"],
                        "name": acct["Name"],
                        "email": acct["Email"],
                        "status": acct["Status"],
                    }
                )
            next_token = resp.get("NextToken")
            if not next_token:
                break
            kwargs["NextToken"] = next_token

    logger.info("Discovered %d org accounts (excluding management)", len(accounts))
    return accounts


async def get_account_ou(aws_account_id: str) -> str:
    """Get the parent OU (or root) ID for an account.

    Returns the OU ID string (e.g., 'ou-abc1-12345678' or 'r-abc1').
    """
    session = await get_management_session()
    async with session.client("organizations") as orgs:
        resp = await orgs.list_parents(ChildId=aws_account_id)
        parents = resp.get("Parents", [])
        if not parents:
            raise RuntimeError(f"No parent found for account {aws_account_id}")
        return parents[0]["Id"]
```

**Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=. pytest tests/unit/services/test_aws.py::TestListOrgAccounts tests/unit/services/test_aws.py::TestGetAccountOu -v -o "addopts="`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/services/aws.py tests/unit/services/test_aws.py
git commit -m "feat: add list_org_accounts and get_account_ou to AWS service"
```

---

### Task 3: Add `POST /api/jobs` endpoint

**Files:**
- Modify: `backend/routers/jobs.py:1-59`
- Modify: `backend/schemas/job.py:1-21`
- Test: `tests/unit/routers/test_jobs.py`

**Step 1: Write failing tests for the new endpoint**

In `tests/unit/routers/test_jobs.py`, add a new `JobCreate` schema import and a test class at the end of the file:

```python
class TestCreateJob:
    async def test_create_sync_accounts_job(self, client, db_session):
        admin, session_id = await _create_authenticated_user(db_session, is_admin=True)

        with patch("backend.routers.jobs.execute_job", new_callable=AsyncMock):
            response = await client.post(
                "/api/jobs",
                json={"job_type": "sync_accounts"},
                cookies=_cookies(session_id),
            )

        assert response.status_code == 201
        data = response.json()
        assert data["job_type"] == "sync_accounts"
        assert data["status"] == "pending"
        assert data["account_id"] is None
        assert data["started_by"] == str(admin.id)

    async def test_create_job_unsupported_type_returns_400(self, client, db_session):
        _, session_id = await _create_authenticated_user(db_session, is_admin=True)

        response = await client.post(
            "/api/jobs",
            json={"job_type": "nonexistent_type"},
            cookies=_cookies(session_id),
        )

        assert response.status_code == 400

    async def test_create_job_non_admin_returns_403(self, client, db_session):
        _, user_session = await _create_authenticated_user(db_session, is_admin=False)

        response = await client.post(
            "/api/jobs",
            json={"job_type": "sync_accounts"},
            cookies=_cookies(user_session),
        )

        assert response.status_code == 403

    async def test_create_job_rejects_duplicate_pending_sync(self, client, db_session):
        admin, session_id = await _create_authenticated_user(db_session, is_admin=True)

        # Create an in-progress sync job
        db_session.add(
            Job(
                job_type="sync_accounts",
                status="in_progress",
                started_by=admin.id,
            )
        )
        await db_session.flush()

        response = await client.post(
            "/api/jobs",
            json={"job_type": "sync_accounts"},
            cookies=_cookies(session_id),
        )

        assert response.status_code == 409

    async def test_create_job_unauthenticated_returns_401(self, client):
        response = await client.post(
            "/api/jobs",
            json={"job_type": "sync_accounts"},
        )

        assert response.status_code == 401
```

Add the mock import at the top of the test file:

```python
from unittest.mock import AsyncMock, patch
```

**Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=. pytest tests/unit/routers/test_jobs.py::TestCreateJob -v -o "addopts="`
Expected: FAIL — POST endpoint not defined

**Step 3: Add `JobCreate` schema**

In `backend/schemas/job.py`, add before `JobResponse`:

```python
from pydantic import Field


class JobCreate(BaseModel):
    job_type: str = Field(min_length=1, max_length=64)
```

(Move the existing `BaseModel` import up if needed — it's already imported.)

**Step 4: Implement `POST /api/jobs` endpoint**

In `backend/routers/jobs.py`, update imports and add the endpoint after the existing imports. The full file becomes:

```python
import asyncio
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.dependencies.auth import get_current_admin, get_current_user
from backend.exceptions import ConflictError, NotFoundError
from backend.models.job import Job
from backend.models.user import User
from backend.schemas.job import JobCreate, JobResponse
from backend.services.jobs import execute_job

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

ALLOWED_JOB_TYPES = {"sync_accounts"}


@router.post("", response_model=JobResponse, status_code=201)
async def create_job(
    body: JobCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    if body.job_type not in ALLOWED_JOB_TYPES:
        from backend.exceptions import GroundworkError

        raise GroundworkError(f"Unsupported job type: {body.job_type}", status_code=400)

    # Prevent duplicate sync jobs
    existing = await db.execute(
        select(Job).where(
            Job.job_type == body.job_type,
            Job.status.in_(["pending", "in_progress"]),
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise ConflictError(f"A {body.job_type} job is already running")

    job = Job(
        job_type=body.job_type,
        status="pending",
        started_by=admin.id,
    )
    db.add(job)
    await db.flush()
    await db.refresh(job)

    task = asyncio.create_task(execute_job(job.id))
    request.app.state.background_tasks.add(task)
    task.add_done_callback(request.app.state.background_tasks.discard)

    return job


@router.get("", response_model=list[JobResponse])
async def list_jobs(
    account_id: Optional[UUID] = Query(None),
    status: Optional[Literal["pending", "in_progress", "completed", "failed"]] = Query(None),
    job_type: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = select(Job).order_by(Job.created_at.desc())

    # Non-admins only see their own jobs
    if not user.is_admin:
        query = query.where(Job.started_by == user.id)

    if account_id is not None:
        query = query.where(Job.account_id == account_id)
    if status is not None:
        query = query.where(Job.status == status)
    if job_type is not None:
        query = query.where(Job.job_type == job_type)

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise NotFoundError("Job not found")

    # Non-admins can only see their own jobs
    if not user.is_admin and job.started_by != user.id:
        raise NotFoundError("Job not found")

    return job
```

Note: The `job_type` filter parameter is changed from `Literal["provision_account"]` to `Optional[str]` to support the new job types.

**Step 5: Run tests to verify they pass**

Run: `PYTHONPATH=. pytest tests/unit/routers/test_jobs.py -v -o "addopts="`
Expected: ALL PASS (both existing and new tests)

**Step 6: Commit**

```bash
git add backend/routers/jobs.py backend/schemas/job.py tests/unit/routers/test_jobs.py
git commit -m "feat: add POST /api/jobs endpoint for triggering sync_accounts"
```

---

### Task 4: Implement `run_bootstrap_account` job handler

**Files:**
- Modify: `backend/services/jobs.py:37-42` (handler dispatch) and add new function
- Test: `tests/unit/services/test_jobs.py`

**Step 1: Write failing tests for `run_bootstrap_account`**

In `tests/unit/services/test_jobs.py`, add import for `run_bootstrap_account` alongside the existing `run_provision_account` import. Then add at the end of the file:

```python
from backend.services.jobs import run_bootstrap_account


class TestBootstrapJobSuccess:
    async def test_bootstrap_sets_account_active_with_oidc_arn(self, db_session):
        """Successful bootstrap marks account active and sets oidc_provider_arn."""
        user = await _create_user(db_session)

        account = Account(
            account_name="Bootstrap Test",
            account_email=f"bs-{id(db_session)}@example.com",
            organizational_unit="ou-1234",
            sso_user_email="sso@example.com",
            aws_account_id="222222222222",
            status="active",
            created_by=user.id,
        )
        db_session.add(account)
        await db_session.flush()

        job = Job(
            account_id=account.id,
            job_type="bootstrap_account",
            status="pending",
            started_by=user.id,
        )
        db_session.add(job)
        await db_session.flush()

        with (
            patch(
                "backend.services.jobs.aws.bootstrap_account",
                new_callable=AsyncMock,
                return_value={
                    "oidc_provider_arn": "arn:aws:iam::222222222222:oidc-provider/idp.example.com",
                    "admin_role_arn": "arn:aws:iam::222222222222:role/GroundworkAdmin",
                },
            ),
        ):
            await run_bootstrap_account(job, db_session)

        await db_session.refresh(account)
        await db_session.refresh(job)

        assert account.status == "active"
        assert account.oidc_provider_arn == "arn:aws:iam::222222222222:oidc-provider/idp.example.com"
        assert job.status == "completed"
        assert job.completed_at is not None


class TestBootstrapJobFailure:
    async def test_bootstrap_failure_marks_job_and_account_failed(self, db_session):
        """Bootstrap failure marks both job and account as failed."""
        user = await _create_user(db_session)

        account = Account(
            account_name="Bootstrap Fail",
            account_email=f"bsfail-{id(db_session)}@example.com",
            organizational_unit="ou-1234",
            sso_user_email="sso@example.com",
            aws_account_id="222222222222",
            status="active",
            created_by=user.id,
        )
        db_session.add(account)
        await db_session.flush()

        job = Job(
            account_id=account.id,
            job_type="bootstrap_account",
            status="pending",
            started_by=user.id,
        )
        db_session.add(job)
        await db_session.flush()

        with patch(
            "backend.services.jobs.aws.bootstrap_account",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Bootstrap stack deployment failed for account 222222222222"),
        ):
            await run_bootstrap_account(job, db_session)

        await db_session.refresh(account)
        await db_session.refresh(job)

        assert account.status == "failed"
        assert job.status == "failed"
        assert job.completed_at is not None
```

**Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=. pytest tests/unit/services/test_jobs.py::TestBootstrapJobSuccess -v -o "addopts="`
Expected: FAIL — `run_bootstrap_account` does not exist

**Step 3: Implement `run_bootstrap_account`**

In `backend/services/jobs.py`, add the handler and register it in the dispatch table.

Update the `handlers` dict in `execute_job` (line 37-42) to include:

```python
"bootstrap_account": run_bootstrap_account,
"sync_accounts": run_sync_accounts,
```

Add the `run_bootstrap_account` function after `run_provision_account` (after line 177):

```python
async def run_bootstrap_account(job: Job, db: AsyncSession) -> None:
    """Bootstrap a single account via StackSet deployment.

    Deploys the OIDC provider + admin role, then marks the account active.
    """
    now = datetime.now(timezone.utc)
    job.status = "in_progress"
    job.started_at = now
    db.add(job)
    await db.commit()

    result = await db.execute(select(Account).where(Account.id == job.account_id))
    account = result.scalar_one_or_none()
    if account is None:
        job.status = "failed"
        job.error_message = "Associated account not found"
        job.completed_at = datetime.now(timezone.utc)
        db.add(job)
        await db.commit()
        return

    try:
        bootstrap_result = await aws.bootstrap_account(
            account.aws_account_id, ou_id=account.organizational_unit
        )
        account.oidc_provider_arn = bootstrap_result["oidc_provider_arn"]
        account.status = "active"
        db.add(account)

        job.status = "completed"
        job.completed_at = datetime.now(timezone.utc)
        job.result = bootstrap_result
        db.add(job)

        await log_event(
            db,
            action="account.bootstrap.completed",
            user_id=job.started_by,
            resource_type="account",
            resource_id=str(account.id),
            detail={"aws_account_id": account.aws_account_id},
        )
        await db.commit()

    except Exception as exc:
        logger.exception("Bootstrap failed for account %s", account.id)
        safe_msg = _sanitize_error(exc)
        account.status = "failed"
        account.error_message = safe_msg
        db.add(account)

        job.status = "failed"
        job.error_message = safe_msg
        job.completed_at = datetime.now(timezone.utc)
        db.add(job)

        await log_event(
            db,
            action="account.bootstrap.failed",
            user_id=job.started_by,
            resource_type="account",
            resource_id=str(account.id),
            detail={"error": safe_msg},
        )
        await db.commit()
```

Also add a placeholder `run_sync_accounts` for now (will be implemented in Task 5):

```python
async def run_sync_accounts(job: Job, db: AsyncSession) -> None:
    """Placeholder — implemented in Task 5."""
    raise NotImplementedError("sync_accounts not yet implemented")
```

**Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=. pytest tests/unit/services/test_jobs.py -v -o "addopts="`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add backend/services/jobs.py tests/unit/services/test_jobs.py
git commit -m "feat: add run_bootstrap_account job handler"
```

---

### Task 5: Implement `run_sync_accounts` job handler

**Files:**
- Modify: `backend/services/jobs.py` (replace placeholder)
- Test: `tests/unit/services/test_jobs.py`

**Step 1: Write failing tests for `run_sync_accounts`**

In `tests/unit/services/test_jobs.py`, add imports and test classes:

```python
from backend.services.jobs import run_sync_accounts


class TestSyncAccountsNewAccounts:
    async def test_imports_new_active_account_and_spawns_bootstrap(self, db_session):
        """Discovers a new ACTIVE account, creates Account + bootstrap_account Job."""
        user = await _create_user(db_session)

        job = Job(
            job_type="sync_accounts",
            status="pending",
            started_by=user.id,
        )
        db_session.add(job)
        await db_session.flush()

        with (
            patch(
                "backend.services.jobs.aws.ensure_bootstrap_stackset",
                new_callable=AsyncMock,
            ),
            patch(
                "backend.services.jobs.aws.list_org_accounts",
                new_callable=AsyncMock,
                return_value=[
                    {
                        "aws_account_id": "222222222222",
                        "name": "Workload",
                        "email": "work@example.com",
                        "status": "ACTIVE",
                    },
                ],
            ),
            patch(
                "backend.services.jobs.aws.get_account_ou",
                new_callable=AsyncMock,
                return_value="ou-abc1-12345678",
            ),
            patch("backend.services.jobs.asyncio.create_task") as mock_create_task,
        ):
            await run_sync_accounts(job, db_session)

        await db_session.refresh(job)
        assert job.status == "completed"
        assert job.result["accounts_found"] == 1
        assert job.result["imported"] == 1
        assert job.result["bootstrap_triggered"] == 1

        # Verify account was created
        from sqlalchemy import select as sa_select

        result = await db_session.execute(
            sa_select(Account).where(Account.aws_account_id == "222222222222")
        )
        account = result.scalar_one()
        assert account.account_name == "Workload"
        assert account.account_email == "work@example.com"
        assert account.organizational_unit == "ou-abc1-12345678"
        assert account.aws_status == "ACTIVE"
        assert account.sso_user_email == "work@example.com"

        # Verify a bootstrap job was created
        result = await db_session.execute(
            sa_select(Job).where(
                Job.account_id == account.id,
                Job.job_type == "bootstrap_account",
            )
        )
        bootstrap_job = result.scalar_one()
        assert bootstrap_job.started_by == user.id

    async def test_imports_suspended_account_without_bootstrap(self, db_session):
        """Discovers a SUSPENDED account, imports it but skips bootstrap."""
        user = await _create_user(db_session)

        job = Job(
            job_type="sync_accounts",
            status="pending",
            started_by=user.id,
        )
        db_session.add(job)
        await db_session.flush()

        with (
            patch(
                "backend.services.jobs.aws.ensure_bootstrap_stackset",
                new_callable=AsyncMock,
            ),
            patch(
                "backend.services.jobs.aws.list_org_accounts",
                new_callable=AsyncMock,
                return_value=[
                    {
                        "aws_account_id": "333333333333",
                        "name": "Suspended Account",
                        "email": "sus@example.com",
                        "status": "SUSPENDED",
                    },
                ],
            ),
            patch(
                "backend.services.jobs.aws.get_account_ou",
                new_callable=AsyncMock,
                return_value="ou-abc1-12345678",
            ),
            patch("backend.services.jobs.asyncio.create_task") as mock_create_task,
        ):
            await run_sync_accounts(job, db_session)

        await db_session.refresh(job)
        assert job.result["imported"] == 1
        assert job.result["skipped_suspended"] == 1
        assert job.result["bootstrap_triggered"] == 0

        # Account exists but no bootstrap job
        from sqlalchemy import select as sa_select

        result = await db_session.execute(
            sa_select(Account).where(Account.aws_account_id == "333333333333")
        )
        account = result.scalar_one()
        assert account.aws_status == "SUSPENDED"

        result = await db_session.execute(
            sa_select(Job).where(
                Job.account_id == account.id,
                Job.job_type == "bootstrap_account",
            )
        )
        assert result.scalar_one_or_none() is None


class TestSyncAccountsExistingAccounts:
    async def test_updates_changed_account_name(self, db_session):
        """Updates account_name when it has changed in AWS."""
        user = await _create_user(db_session)

        existing = Account(
            account_name="Old Name",
            account_email="work@example.com",
            organizational_unit="ou-abc1-12345678",
            sso_user_email="work@example.com",
            aws_account_id="222222222222",
            status="active",
            aws_status="ACTIVE",
            oidc_provider_arn="arn:aws:iam::222222222222:oidc-provider/idp.example.com",
            created_by=user.id,
        )
        db_session.add(existing)
        await db_session.flush()

        job = Job(
            job_type="sync_accounts",
            status="pending",
            started_by=user.id,
        )
        db_session.add(job)
        await db_session.flush()

        with (
            patch(
                "backend.services.jobs.aws.ensure_bootstrap_stackset",
                new_callable=AsyncMock,
            ),
            patch(
                "backend.services.jobs.aws.list_org_accounts",
                new_callable=AsyncMock,
                return_value=[
                    {
                        "aws_account_id": "222222222222",
                        "name": "New Name",
                        "email": "work@example.com",
                        "status": "ACTIVE",
                    },
                ],
            ),
            patch(
                "backend.services.jobs.aws.get_account_ou",
                new_callable=AsyncMock,
                return_value="ou-abc1-12345678",
            ),
            patch("backend.services.jobs.asyncio.create_task") as mock_create_task,
        ):
            await run_sync_accounts(job, db_session)

        await db_session.refresh(existing)
        assert existing.account_name == "New Name"
        await db_session.refresh(job)
        assert job.result["updated"] == 1
        assert job.result["bootstrap_triggered"] == 0

    async def test_triggers_bootstrap_for_unbootstrapped_account(self, db_session):
        """Existing ACTIVE account with no oidc_provider_arn gets bootstrap job."""
        user = await _create_user(db_session)

        existing = Account(
            account_name="Unbootstrapped",
            account_email="un@example.com",
            organizational_unit="ou-abc1-12345678",
            sso_user_email="un@example.com",
            aws_account_id="222222222222",
            status="failed",
            aws_status="ACTIVE",
            created_by=user.id,
        )
        db_session.add(existing)
        await db_session.flush()

        job = Job(
            job_type="sync_accounts",
            status="pending",
            started_by=user.id,
        )
        db_session.add(job)
        await db_session.flush()

        with (
            patch(
                "backend.services.jobs.aws.ensure_bootstrap_stackset",
                new_callable=AsyncMock,
            ),
            patch(
                "backend.services.jobs.aws.list_org_accounts",
                new_callable=AsyncMock,
                return_value=[
                    {
                        "aws_account_id": "222222222222",
                        "name": "Unbootstrapped",
                        "email": "un@example.com",
                        "status": "ACTIVE",
                    },
                ],
            ),
            patch(
                "backend.services.jobs.aws.get_account_ou",
                new_callable=AsyncMock,
                return_value="ou-abc1-12345678",
            ),
            patch("backend.services.jobs.asyncio.create_task") as mock_create_task,
        ):
            await run_sync_accounts(job, db_session)

        await db_session.refresh(job)
        assert job.result["bootstrap_triggered"] == 1

        from sqlalchemy import select as sa_select

        result = await db_session.execute(
            sa_select(Job).where(
                Job.account_id == existing.id,
                Job.job_type == "bootstrap_account",
            )
        )
        assert result.scalar_one() is not None
```

**Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=. pytest tests/unit/services/test_jobs.py::TestSyncAccountsNewAccounts -v -o "addopts="`
Expected: FAIL — `run_sync_accounts` raises NotImplementedError

**Step 3: Implement `run_sync_accounts`**

In `backend/services/jobs.py`, replace the placeholder `run_sync_accounts` with the real implementation. Add `asyncio` to the imports if not already present (it's not currently imported in jobs.py):

```python
import asyncio
```

Replace the placeholder with:

```python
async def run_sync_accounts(job: Job, db: AsyncSession) -> None:
    """Discover org accounts, import/reconcile, and bootstrap active ones.

    1. Ensure bootstrap StackSet exists.
    2. List all org accounts (paginated).
    3. For each account: import new, reconcile existing, skip/mark suspended.
    4. Spawn bootstrap_account jobs for accounts needing deployment.
    """
    now = datetime.now(timezone.utc)
    job.status = "in_progress"
    job.started_at = now
    db.add(job)
    await db.commit()

    try:
        # Step 1: Ensure StackSet exists
        await aws.ensure_bootstrap_stackset()

        # Step 2: Discover accounts
        org_accounts = await aws.list_org_accounts()

        # Build lookup of existing accounts by aws_account_id
        result = await db.execute(
            select(Account).where(Account.aws_account_id.isnot(None))
        )
        existing_map: dict[str, Account] = {
            a.aws_account_id: a for a in result.scalars().all()
        }

        counts = {
            "accounts_found": len(org_accounts),
            "imported": 0,
            "updated": 0,
            "bootstrap_triggered": 0,
            "skipped_suspended": 0,
        }

        for org_acct in org_accounts:
            aws_id = org_acct["aws_account_id"]
            aws_status = org_acct["status"]
            ou_id = await aws.get_account_ou(aws_id)

            if aws_id not in existing_map:
                # New account — import
                account = Account(
                    aws_account_id=aws_id,
                    account_name=org_acct["name"],
                    account_email=org_acct["email"],
                    organizational_unit=ou_id,
                    sso_user_email=org_acct["email"],
                    status="active",
                    aws_status=aws_status,
                    created_by=job.started_by,
                )
                db.add(account)
                await db.flush()
                counts["imported"] += 1

                if aws_status != "ACTIVE":
                    counts["skipped_suspended"] += 1
                else:
                    # Spawn bootstrap job
                    bootstrap_job = Job(
                        account_id=account.id,
                        job_type="bootstrap_account",
                        status="pending",
                        started_by=job.started_by,
                    )
                    db.add(bootstrap_job)
                    await db.flush()
                    asyncio.create_task(execute_job(bootstrap_job.id))
                    counts["bootstrap_triggered"] += 1
            else:
                # Existing account — reconcile
                account = existing_map[aws_id]
                changed = False

                if account.account_name != org_acct["name"]:
                    account.account_name = org_acct["name"]
                    changed = True
                if account.account_email != org_acct["email"]:
                    account.account_email = org_acct["email"]
                    changed = True
                if account.organizational_unit != ou_id:
                    account.organizational_unit = ou_id
                    changed = True
                if account.aws_status != aws_status:
                    account.aws_status = aws_status
                    changed = True

                if changed:
                    db.add(account)
                    counts["updated"] += 1

                # Trigger bootstrap if needed
                needs_bootstrap = (
                    aws_status == "ACTIVE"
                    and (not account.oidc_provider_arn or account.status == "failed")
                )
                if needs_bootstrap:
                    bootstrap_job = Job(
                        account_id=account.id,
                        job_type="bootstrap_account",
                        status="pending",
                        started_by=job.started_by,
                    )
                    db.add(bootstrap_job)
                    await db.flush()
                    asyncio.create_task(execute_job(bootstrap_job.id))
                    counts["bootstrap_triggered"] += 1

                if aws_status != "ACTIVE":
                    counts["skipped_suspended"] += 1

        job.status = "completed"
        job.completed_at = datetime.now(timezone.utc)
        job.result = counts
        db.add(job)

        await log_event(
            db,
            action="accounts.sync.completed",
            user_id=job.started_by,
            resource_type="account",
            detail=counts,
        )
        await db.commit()

    except Exception as exc:
        logger.exception("Sync accounts failed")
        safe_msg = _sanitize_error(exc)
        job.status = "failed"
        job.error_message = safe_msg
        job.completed_at = datetime.now(timezone.utc)
        db.add(job)

        await log_event(
            db,
            action="accounts.sync.failed",
            user_id=job.started_by,
            resource_type="account",
            detail={"error": safe_msg},
        )
        await db.commit()
```

**Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=. pytest tests/unit/services/test_jobs.py -v -o "addopts="`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add backend/services/jobs.py tests/unit/services/test_jobs.py
git commit -m "feat: implement run_sync_accounts job handler"
```

---

### Task 6: Frontend — add `createJob` API + Sync button + job type filters

**Files:**
- Modify: `frontend/src/api/jobs.ts`
- Modify: `frontend/src/pages/Dashboard.tsx`
- Modify: `frontend/src/pages/JobList.tsx`

**Step 1: Add `createJob` to the API layer**

In `frontend/src/api/jobs.ts`, add after the `getJob` function:

```typescript
export interface JobCreate {
  job_type: string
}

export function createJob(data: JobCreate): Promise<JobResponse> {
  return apiFetch<JobResponse>('/api/jobs', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}
```

**Step 2: Add "Sync Accounts" button to Dashboard**

In `frontend/src/pages/Dashboard.tsx`:

Add imports:
```typescript
import { useNavigate } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { createJob } from '@/api/jobs'
import { RefreshCw } from 'lucide-react'
```

Inside the `Dashboard` component function, add the mutation and navigate hooks (after the existing `useState` and `useQuery` calls):

```typescript
const navigate = useNavigate()

const syncMutation = useMutation({
  mutationFn: () => createJob({ job_type: 'sync_accounts' }),
  onSuccess: () => navigate('/jobs'),
})
```

Then in the JSX, update the admin action buttons area (the `{isAdmin && (` block) to include the sync button alongside the existing "New Account" button:

```tsx
{isAdmin && (
  <div className="flex gap-2">
    <Button
      variant="outline"
      onClick={() => syncMutation.mutate()}
      disabled={syncMutation.isPending}
    >
      <RefreshCw className={`mr-1.5 size-3.5 ${syncMutation.isPending ? 'animate-spin' : ''}`} />
      Sync Accounts
    </Button>
    <Button asChild>
      <Link to="/accounts/new">+ New Account</Link>
    </Button>
  </div>
)}
```

**Step 3: Add new job types to JobList filter**

In `frontend/src/pages/JobList.tsx`, update the type filter `<SelectContent>` (around line 107-113) to include the new job types:

```tsx
<SelectContent>
  <SelectItem value={ALL}>All types</SelectItem>
  <SelectItem value="provision_account">Provision Account</SelectItem>
  <SelectItem value="sync_accounts">Sync Accounts</SelectItem>
  <SelectItem value="bootstrap_account">Bootstrap Account</SelectItem>
  <SelectItem value="create_role">Create Role</SelectItem>
  <SelectItem value="update_role">Update Role</SelectItem>
  <SelectItem value="delete_role">Delete Role</SelectItem>
</SelectContent>
```

Update the account column display (around line 144) to show "Org-wide" for null account_id jobs:

```tsx
<TableCell>
  {job.account_id
    ? accountMap.get(job.account_id) ?? job.account_id
    : 'Org-wide'}
</TableCell>
```

**Step 4: Build frontend to check for errors**

Run: `cd /Users/lcmessen/groundwork/frontend && npm run build`
Expected: Build succeeds

**Step 5: Commit**

```bash
git add frontend/src/api/jobs.ts frontend/src/pages/Dashboard.tsx frontend/src/pages/JobList.tsx
git commit -m "feat: add Sync Accounts button and job type filters to frontend"
```

---

### Task 7: Frontend — hide suspended/closed accounts, show aws_status badge

**Files:**
- Modify: `frontend/src/pages/Dashboard.tsx`
- Modify: `frontend/src/pages/AccountDetail.tsx`

**Step 1: Add suspended account toggle to Dashboard**

In `frontend/src/pages/Dashboard.tsx`, add a state toggle and filter logic.

Add new state:
```typescript
const [showClosed, setShowClosed] = useState(false)
```

Update the `grouped` memo to filter out suspended/closed accounts by default:

```typescript
const grouped = useMemo(() => {
  if (!accounts) return []
  let filtered = accounts

  // Hide suspended/closed accounts unless toggled
  if (!showClosed) {
    filtered = filtered.filter(
      (a) => !a.aws_status || a.aws_status === 'ACTIVE'
    )
  }

  const q = search.toLowerCase()
  if (q) {
    filtered = filtered.filter(
      (a) =>
        a.account_name.toLowerCase().includes(q) ||
        a.account_email.toLowerCase().includes(q) ||
        (a.aws_account_id ?? '').includes(q) ||
        a.organizational_unit.toLowerCase().includes(q)
    )
  }

  const map = new Map<string, typeof accounts>()
  for (const a of filtered) {
    const ou = a.organizational_unit
    if (!map.has(ou)) map.set(ou, [])
    map.get(ou)!.push(a)
  }
  return [...map.entries()].sort(([a], [b]) => a.localeCompare(b))
}, [accounts, search, showClosed])
```

Count suspended accounts and add a toggle button in the JSX. Add after the `<SearchInput>` component:

```tsx
{accounts && accounts.some((a) => a.aws_status && a.aws_status !== 'ACTIVE') && (
  <label className="flex items-center gap-2 text-sm text-muted-foreground">
    <input
      type="checkbox"
      checked={showClosed}
      onChange={(e) => setShowClosed(e.target.checked)}
      className="rounded"
    />
    Show suspended/closed accounts
  </label>
)}
```

Add grayed-out styling for suspended accounts in the table row. Update the `<TableRow>` for each account:

```tsx
<TableRow
  key={account.id}
  className={
    account.aws_status && account.aws_status !== 'ACTIVE'
      ? 'opacity-50'
      : undefined
  }
>
```

**Step 2: Show `aws_status` badge on AccountDetail page**

In `frontend/src/pages/AccountDetail.tsx`, add an `aws_status` badge next to the provisioning status badge. In the header section where the status badge is rendered:

```tsx
<div className="flex items-center gap-3">
  <h1 className="text-2xl font-semibold tracking-tight">
    {account.account_name}
  </h1>
  <Badge variant={statusVariant(account.status)}>{account.status}</Badge>
  {account.aws_status && account.aws_status !== 'ACTIVE' && (
    <Badge variant="secondary">{account.aws_status.toLowerCase()}</Badge>
  )}
</div>
```

**Step 3: Build frontend to check for errors**

Run: `cd /Users/lcmessen/groundwork/frontend && npm run build`
Expected: Build succeeds

**Step 4: Commit**

```bash
git add frontend/src/pages/Dashboard.tsx frontend/src/pages/AccountDetail.tsx
git commit -m "feat: hide suspended accounts by default, show aws_status badge"
```

---

### Task 8: Run full test suite + lint

**Files:** None (validation only)

**Step 1: Run the full test suite**

Run: `PYTHONPATH=. pytest`
Expected: ALL PASS with coverage >= 70%

**Step 2: Run linting and formatting**

Run:
```bash
black backend/ tests/ && isort backend/ tests/
flake8 backend/ tests/
```
Expected: Clean output

**Step 3: Fix any issues found**

If any tests or lint errors fail, fix them and re-run.

**Step 4: Build frontend one more time**

Run: `cd /Users/lcmessen/groundwork/frontend && npm run build`
Expected: Build succeeds

**Step 5: Commit any fixes**

```bash
git add -u
git commit -m "fix: lint and test fixes for org sync feature"
```

(Only if there were fixes to make.)
