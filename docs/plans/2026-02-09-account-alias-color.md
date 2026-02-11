# Account Alias, Color & Metadata Sync

## Overview

Extend Groundwork to support AWS account aliases and console colors, stored in the database and synced periodically from AWS. Also add role drift detection to the sync cycle.

- **Account alias**: IAM account alias, managed via `CreateAccountAlias` / `DeleteAccountAlias` / `ListAccountAliases`. Standard boto3.
- **Account color**: Console navigation bar color, managed via UXC service (`GET/PUT/DELETE /v1/account-color`). No boto3 support — raw HTTP with SigV4 signing.
- **Role drift detection**: Periodic check that IAM roles match Groundwork's stored configuration.

## Architecture

**Database as source of truth.** Alias and color are stored as columns on the `accounts` table. Reads are instant (no AWS API calls). Writes go to AWS first, then update the DB on success. A periodic sync task refreshes the data from AWS.

**No in-memory cache.** The `account_metadata.py` cache module is removed entirely.

## Database Changes

### Alembic migration

**`accounts` table — two new columns:**
- `alias: String(63), nullable` — IAM account alias
- `color: String(20), nullable` — UXC console color

**`roles` table — no new columns.** Drift is tracked using the existing `status` column with a new value: `"drifted"`.

## Backend — AWS Service Layer

### Account Alias (boto3 IAM)

Already implemented in `backend/services/aws.py`:

- `get_account_alias(account_id)` — calls `iam.list_account_aliases()`, returns alias string or `None`
- `set_account_alias(account_id, alias)` — calls `iam.create_account_alias(AccountAlias=alias)`
- `delete_account_alias(account_id, alias)` — calls `iam.delete_account_alias(AccountAlias=alias)`

### Account Color (raw HTTP + SigV4)

Already implemented in `backend/services/aws.py`:

- `get_account_color(account_id)` — signed `GET` to `https://uxc.us-east-1.api.aws/v1/account-color`
- `set_account_color(account_id, color)` — signed `PUT` with `{"color": "<value>"}`
- `delete_account_color(account_id)` — signed `DELETE`

Valid color values: `none`, `pink`, `purple`, `darkBlue`, `lightBlue`, `teal`, `green`, `yellow`, `orange`, `red`.

### IAM Role Metadata (new)

New function in `backend/services/aws.py`:

- `get_iam_role_metadata(aws_account_id, role_name)` — assumes role in member account, calls `iam.get_role()` and `iam.list_attached_role_policies()`. Returns dict with:
  - `exists: bool`
  - `max_session_duration: int | None`
  - `attached_policy_arns: list[str]`
  - `last_used: datetime | None`

## Backend — Periodic Sync

### Integrated into `run_sync_accounts`

After the existing org account reconciliation loop, a new phase runs:

```python
# Stagger across the sync interval
active = [a for a in accounts if a.status == "active" and a.aws_account_id]
delay = (settings.sync_interval_minutes * 60) / max(len(active), 1)

for account in active:
    await sync_account_metadata(account, db)
    await asyncio.sleep(delay)
```

### `sync_account_metadata(account, db)`

For a single account:

1. **Alias + color** (concurrent via `asyncio.gather`):
   - Fetch alias from IAM, color from UXC
   - Update `account.alias` and `account.color` in DB

2. **Role drift detection** (concurrent per role via `asyncio.gather`):
   For each role on the account with `status = "active"`:
   - Call `get_iam_role_metadata(aws_account_id, role_name)`
   - If role doesn't exist in IAM → set `role.status = "drifted"`
   - If `MaxSessionDuration` differs from `max(api_session_duration, console_session_duration)` → set `role.status = "drifted"`
   - If attached policy ARNs differ from `role.managed_policy_arns` → set `role.status = "drifted"`
   - If `last_used` is available, update `role.last_used_at`
   - If everything matches → leave `role.status = "active"`

3. Commit changes to DB.

Errors for individual accounts are logged and skipped — one account failing doesn't block the rest.

## Backend — API Changes

### Router changes

**`list_accounts` and `get_account`** — return Account model directly. Alias and color come from DB columns via `from_attributes = True`. No metadata cache calls. Fast.

**`update_account` (PATCH)** — when `alias` or `color` is in the payload:
1. Call the AWS API (IAM for alias, UXC for color)
2. On success, update the DB column (`account.alias = ...`, `account.color = ...`)
3. No cache — just a normal DB write alongside the other field updates

**Remove** all references to `account_metadata` module from the router.

### New endpoint: Fix Drift

`POST /api/accounts/{account_id}/roles/{role_id}/fix-drift` — admin only.

1. Verify role exists and `status == "drifted"`
2. Set `role.status = "updating"`
3. Create a job with `job_type = "update_role"` that re-applies all IAM fields (managed policies, inline policy, max session duration) from Groundwork's stored configuration
4. On job success, role status returns to `"active"` (existing update_role handler behavior)

No new job handler needed — reuses existing `run_update_role`.

### Schema changes

**`AccountResponse`** — already has `alias: str | None` and `color: str | None`. Now populated from model.

**`AccountUpdate`** — already has `alias` and `color` optional fields with validation.

**`RoleResponse`** — already has `status`. New `"drifted"` value handled by existing field.

### Remove

- `backend/services/account_metadata.py` — deleted entirely
- `tests/unit/services/test_account_metadata.py` — deleted entirely

## Frontend Changes

### Dashboard (`Dashboard.tsx`)

Already implemented:
- Color square (12x12px) before account name
- Alias text below account name
- Search matches against alias

### Account Detail (`AccountDetail.tsx`)

Already implemented:
- Color picker dropdown (admin only, active accounts)
- Inline alias editor with pencil icon (admin only, active accounts)

### Role drift indicator (new)

On the account detail page, role cards:
- Show a `drifted` badge (variant: `destructive` or `warning`) when `role.status === "drifted"`
- A "Fix Drift" button appears next to drifted roles (admin only)
- Clicking fires `POST /api/accounts/{account_id}/roles/{role_id}/fix-drift`
- Button disabled while `role.status === "updating"`

## Error Handling

- **Alias already taken:** IAM `EntityAlreadyExistsException` → 409 Conflict
- **Account not active:** PATCH rejected with 400 if `status != "active"` or no `aws_account_id`
- **UXC errors:** `Content-Type` only sent on PUT (body present). `AccessDeniedException` → 502.
- **Sync failures:** Per-account errors logged and skipped. One failing account doesn't block others.
- **Drift detection failures:** If IAM calls fail during sync, role status is not changed. Warning logged.

## Bootstrap Role Permissions

Already covered by the `AdministratorAccess` managed policy on the GroundworkAdmin role. The specific permissions needed are:

```json
{
  "Effect": "Allow",
  "Action": [
    "iam:CreateAccountAlias",
    "iam:DeleteAccountAlias",
    "iam:ListAccountAliases",
    "iam:GetRole",
    "iam:ListAttachedRolePolicies",
    "uxc:GetAccountColor",
    "uxc:PutAccountColor",
    "uxc:DeleteAccountColor"
  ],
  "Resource": "*"
}
```
