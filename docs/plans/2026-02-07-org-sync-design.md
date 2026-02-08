# Org Account Sync & Bootstrap Design

## Overview

Add a background job that discovers existing accounts in the AWS Organization, imports them into Groundwork's database, reconciles any changes, and ensures each active account is bootstrapped with the Groundwork StackSet (OIDC provider + admin role).

## Data Model Changes

### Account model — new field

- `aws_status: Optional[str]` — String(20), nullable. Values: `ACTIVE`, `SUSPENDED`, `PENDING_CLOSURE`. Null for legacy accounts (treated as `ACTIVE` by the UI).

### Job types — new values

- `sync_accounts` — Org-wide discovery and reconciliation job. `account_id` is null.
- `bootstrap_account` — Per-account StackSet deployment. `account_id` references the target account.

No schema changes to the Job model — `job_type` is already a freeform string.

### API — new endpoint

- `POST /api/jobs` — Admin-only. Accepts `{job_type: "sync_accounts"}`. Returns the created job. Unsupported job types return 400. Rejects if a `sync_accounts` job is already `pending` or `in_progress`.

## Sync Job Logic

`run_sync_accounts` handler in `backend/services/jobs.py`:

1. Call `ensure_bootstrap_stackset()` — idempotent StackSet creation.
2. Call `list_org_accounts()` via management session — paginated `ListAccounts`, filtering out the management account.
3. For each AWS account:
   - **Not in DB** (by `aws_account_id`): Create Account record with `status=active`, `aws_status` from AWS, `account_email` from AWS email, `sso_user_email` set to same email, `organizational_unit` from `get_account_ou()`. If `aws_status=ACTIVE`, create a `bootstrap_account` job and fire it off.
   - **Already in DB**: Compare `account_name`, `account_email`, `organizational_unit`, `aws_status` — update any diffs. If `aws_status=ACTIVE` and account lacks `oidc_provider_arn` or has `status=failed`, create a `bootstrap_account` job.
   - **Suspended/closed in AWS**: Set `aws_status` accordingly, skip bootstrapping.
4. Store summary in job `result`: `{accounts_found, imported, updated, bootstrap_triggered, skipped_suspended}`.
5. Mark sync job as `completed`.

## Bootstrap Job Logic

`run_bootstrap_account` handler — extracted from the tail end of `run_provision_account` (steps 4-5). Reuses `bootstrap_account()` and `get_stack_instance_status()` from the AWS service. On success, sets `account.status=active` and populates `oidc_provider_arn`.

## AWS Service Layer

### New functions in `backend/services/aws.py`

- `list_org_accounts()` — Management session, paginated `ListAccounts`. Returns list of `{aws_account_id, name, email, status, joined_timestamp}`. Filters out management account.
- `get_account_ou(aws_account_id)` — Management session, `ListParents`. Returns OU ID.

### No changes to existing functions

`ensure_bootstrap_stackset()`, `bootstrap_account()`, `get_stack_instance_status()` work as-is.

## Frontend Changes

### API layer

- Add `createJob(data: {job_type: string}): Promise<JobResponse>` — POST to `/api/jobs`.

### Dashboard

- "Sync Accounts" button (admin-only). Calls `createJob({job_type: "sync_accounts"})`, shows toast, navigates to job list.

### Account lists (Dashboard + elsewhere)

- Default: hide accounts where `aws_status` is `SUSPENDED` or `PENDING_CLOSURE`.
- Toggle: "Show closed/suspended accounts".
- Grayed-out styling for those accounts when visible.

### Account detail

- Show `aws_status` badge if not `ACTIVE` (muted/warning color).

### Job list

- Add `sync_accounts` and `bootstrap_account` to job type filter.
- `sync_accounts` jobs show "Org-wide" for the account column.

## Migration

- Alembic migration: add `aws_status` column to `accounts` — nullable String(20), no default.

## Testing

- Unit tests for `run_sync_accounts`: mock Organizations responses, verify create/update/skip logic, verify bootstrap jobs spawned correctly.
- Unit tests for `run_bootstrap_account`: mock StackSet polling, verify status and `oidc_provider_arn` on success/failure.
- Unit tests for `POST /api/jobs`: admin-only, 400 for bad job types, duplicate prevention, job creation.
- Unit tests for `list_org_accounts` and `get_account_ou`: mock boto3, verify pagination, verify management account filtering.

## Security

- `POST /api/jobs` requires `get_current_admin` dependency.
- Uses existing management session pattern — no new IAM permissions.
- Only one `sync_accounts` job allowed at a time (reject if one is already pending/in_progress).
