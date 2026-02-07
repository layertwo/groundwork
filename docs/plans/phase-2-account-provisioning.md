# Phase 2 — Account Provisioning

## Goal

Admins can create AWS accounts through Groundwork. The backend calls Control Tower, polls for completion, bootstraps the account with an OIDC identity provider and an admin management role, and tracks progress via jobs.

## Prerequisites

- Phase 1 complete (auth working, `get_current_user`/`get_current_admin` dependencies available)
- AWS credentials available to the backend (IAM role or env vars) with permissions for:
  - `controltower:CreateManagedAccount`
  - `controltower:GetAccountStatus` (or equivalent polling API)
  - `sts:AssumeRole` (to assume OrganizationAccountAccessRole in new accounts)
  - `iam:CreateOpenIDConnectProvider`, `iam:CreateRole`, `iam:AttachRolePolicy` (via assumed role)

## Steps

### 2.1 — Add boto3 dependency

Add to `requirements.txt`:
```
boto3==1.38.0
aioboto3==14.1.0
```

`aioboto3` wraps boto3 for async usage, avoiding blocking the event loop.

### 2.2 — AWS service layer: `backend/services/aws.py`

New file. All AWS API interactions live here.

**`get_session() -> aioboto3.Session`:**
Returns an aioboto3 session using default credential chain (env vars, instance role, etc.). Uses `settings.aws_region`.

**`create_managed_account(account_name, account_email, ou) -> str`:**
1. Call Control Tower `CreateManagedAccount` (or the appropriate API — check exact API name at implementation time)
2. Return the operation ID for polling

**`poll_account_creation(operation_id: str) -> dict`:**
1. Call the status API to check provisioning progress
2. Return status dict with `state` (IN_PROGRESS, SUCCEEDED, FAILED) and `account_id` when complete

**`bootstrap_account(aws_account_id: str) -> dict`:**
1. Assume `OrganizationAccountAccessRole` in the target account:
   ```python
   sts.assume_role(
       RoleArn=f"arn:aws:iam::{aws_account_id}:role/OrganizationAccountAccessRole",
       RoleSessionName="GroundworkBootstrap"
   )
   ```
2. Using the assumed credentials, create the OIDC provider:
   ```python
   iam.create_open_id_connect_provider(
       Url=settings.oidc_issuer_url,
       ClientIDList=[settings.oidc_client_id],
       ThumbprintList=[thumbprint]  # fetched from OIDC provider's JWKS endpoint
   )
   ```
3. Create the admin management role (`settings.admin_role_name`) with a trust policy allowing the management account to assume it:
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [{
       "Effect": "Allow",
       "Principal": {"AWS": "arn:aws:iam::MANAGEMENT_ACCOUNT:root"},
       "Action": "sts:AssumeRole"
     }]
   }
   ```
4. Attach `AdministratorAccess` managed policy to the admin management role
5. Return `{"oidc_provider_arn": "...", "admin_role_arn": "..."}`

**`get_oidc_thumbprint(issuer_url: str) -> str`:**
Fetch the TLS certificate from the OIDC issuer and compute the SHA-1 thumbprint. Required for `create_open_id_connect_provider`.

### 2.3 — Add config settings

Add to `backend/config.py`:
```python
aws_management_account_id: str = ""
admin_role_name: str = "GroundworkAdmin-DO-NOT-DELETE"
```

Update `.env.example`:
```
GW_AWS_MANAGEMENT_ACCOUNT_ID=111122223333
GW_ADMIN_ROLE_NAME=GroundworkAdmin-DO-NOT-DELETE
```

### 2.4 — Job executor: `backend/services/jobs.py`

New file. Background task runner for multi-step provisioning jobs.

**`async def execute_job(job_id: uuid.UUID) -> None`:**
1. Load job from DB
2. Dispatch based on `job_type`:
   - `provision_account` → run provisioning pipeline
   - `create_role` → run role creation (Phase 3)
   - `update_role` → run role update (Phase 3)
   - `delete_role` → run role deletion (Phase 3)
3. Update job status/result/error on completion or failure

**`async def run_provision_account(job: Job, db: AsyncSession) -> None`:**
1. Update job status to `in_progress`, set `started_at`
2. Load the associated account
3. **Step 1 — Create account:**
   - Call `create_managed_account()`
   - Store operation ID in `job.result`
   - Poll `poll_account_creation()` in a loop (sleep 30s between polls, max 30 min timeout)
   - On success, update `account.aws_account_id`
   - On failure, mark job failed, set `account.status = "failed"`
4. **Step 2 — Bootstrap:**
   - Call `bootstrap_account(aws_account_id)`
   - Store OIDC provider ARN in `account.oidc_provider_arn`
5. **Step 3 — Mark complete:**
   - Set `account.status = "active"`
   - Set `job.status = "completed"`, `job.completed_at = now()`
   - Store full result in `job.result`

Jobs are launched as background tasks via `asyncio.create_task()` from the router. They run in the same process — no separate worker.

### 2.5 — Implement accounts router: `backend/routers/accounts.py`

Replace all 501 stubs. All endpoints require `get_current_user`.

**`POST /api/accounts` (admin only):**
1. Validate `AccountCreate` body
2. Check `account_email` is not already used (ConflictError if exists)
3. Create `Account` row with `status="pending"`, `created_by=user.id`
4. Create `Job` row with `job_type="provision_account"`, `started_by=user.id`, `account_id=account.id`
5. Launch `execute_job(job.id)` as background task
6. Audit log: `account.create`
7. Return `AccountResponse` with 201 status

**`GET /api/accounts`:**
1. Query all accounts
2. If user is not admin, filter to accounts where user has at least one accessible role (group/user match) — or return all for now and filter in Phase 3
3. Return `list[AccountResponse]`

**`GET /api/accounts/{account_id}`:**
1. Look up account by UUID
2. Raise `NotFoundError` if missing
3. Return `AccountResponse`

**`PATCH /api/accounts/{account_id}` (admin only):**
1. Look up account
2. Apply `AccountUpdate` fields (only non-None values)
3. Audit log: `account.update`
4. Return `AccountResponse`

### 2.6 — Implement jobs router: `backend/routers/jobs.py`

Replace 501 stubs. All endpoints require `get_current_user`.

**`GET /api/jobs`:**
1. Query jobs, ordered by `created_at` desc
2. If not admin, filter to `started_by=user.id`
3. Support optional query params: `account_id`, `status`, `job_type`
4. Return `list[JobResponse]`

**`GET /api/jobs/{job_id}`:**
1. Look up job by UUID
2. Raise `NotFoundError` if missing
3. Return `JobResponse`

### 2.7 — Tests

**Mock AWS:** Create `tests/fixtures/aws.py` with:
- `mock_sts_client` — stubbed STS (AssumeRole returns fake creds)
- `mock_iam_client` — stubbed IAM (create_open_id_connect_provider, create_role, attach_role_policy)
- `mock_controltower_client` — stubbed Control Tower (CreateManagedAccount, polling)

Use `unittest.mock.patch` or `botocore.stub.Stubber` (following cortex pattern).

**Test cases:**
- `test_create_account_returns_201` — admin creates account, gets AccountResponse with pending status
- `test_create_account_non_admin_returns_403` — non-admin rejected
- `test_create_account_duplicate_email_returns_409` — duplicate email rejected
- `test_create_account_creates_job` — verify Job row created with correct type
- `test_list_accounts` — returns all accounts for admin
- `test_get_account_not_found` — 404 for invalid ID
- `test_update_account` — PATCH updates fields
- `test_provision_job_success` — full provisioning pipeline with mocked AWS (account created, bootstrapped, marked active)
- `test_provision_job_failure` — Control Tower returns failure, job/account marked failed
- `test_list_jobs` — returns jobs for user
- `test_get_job` — returns single job

## New files

```
backend/services/aws.py
backend/services/jobs.py
tests/fixtures/aws.py
tests/unit/routers/test_accounts.py (update existing)
tests/unit/routers/test_jobs.py (update existing)
tests/unit/services/test_aws.py
tests/unit/services/test_jobs.py
```

## Definition of done

- Admin can POST `/api/accounts` and a provisioning job starts
- Job progresses through Control Tower account creation, OIDC provider setup, and admin management role creation (all mocked in tests)
- Account status transitions: pending → provisioning → active (or failed)
- Job status visible via `/api/jobs` and `/api/jobs/{id}`
- All operations audit logged
- Tests pass with fully mocked AWS APIs
