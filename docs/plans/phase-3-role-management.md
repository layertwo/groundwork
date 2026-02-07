# Phase 3 — Role Management

## Goal

Users can create, update, and delete IAM roles on managed accounts — from templates or custom. Groundwork creates the actual IAM role in the target account with the correct trust policy and attached policies.

## Prerequisites

- Phase 2 complete (account provisioning working, AWS service layer exists, job executor handles `provision_account`)
- Target accounts have `the admin management role` role (created during provisioning)
- OIDC provider exists in target accounts (created during provisioning)

## Steps

### 3.1 — AWS service layer additions: `backend/services/aws.py`

Add functions for IAM role management. All operate by first assuming `the admin management role` in the target account.

**`async def assume_groundwork_admin(aws_account_id: str) -> dict`:**
Assume the the admin management role role in the target account. Returns temporary credentials.

**`async def create_iam_role(aws_account_id: str, role_name: str, oidc_provider_arn: str, allowed_groups: list[str], allowed_users: list[str], managed_policy_arns: list[str], inline_policy: dict | None, max_duration: int) -> str`:**
1. Assume the admin management role
2. Build trust policy with two statements (groups OR users), each gated on `aud`. Omit a statement if its list is empty:
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Sid": "AllowGroupAccess",
         "Effect": "Allow",
         "Principal": {
           "Federated": "<oidc_provider_arn>"
         },
         "Action": "sts:AssumeRoleWithWebIdentity",
         "Condition": {
           "StringEquals": {
             "<issuer>:aud": "<client_id>"
           },
           "ForAnyValue:StringEquals": {
             "<issuer>:groups": ["<allowed_groups>"]
           }
         }
       },
       {
         "Sid": "AllowUserAccess",
         "Effect": "Allow",
         "Principal": {
           "Federated": "<oidc_provider_arn>"
         },
         "Action": "sts:AssumeRoleWithWebIdentity",
         "Condition": {
           "StringEquals": {
             "<issuer>:aud": "<client_id>",
             "<issuer>:sub": ["<allowed_users>"]
           }
         }
       }
     ]
   }
   ```
3. `iam.create_role(RoleName=role_name, AssumeRolePolicyDocument=trust_policy, MaxSessionDuration=max_duration)`
4. For each ARN in `managed_policy_arns`: `iam.attach_role_policy(RoleName=role_name, PolicyArn=arn)`
5. If `inline_policy` is provided: `iam.put_role_policy(RoleName=role_name, PolicyName="GroundworkInlinePolicy", PolicyDocument=inline_policy)`
6. Return the role ARN

**`async def update_iam_role(aws_account_id: str, role_name: str, oidc_provider_arn: str, allowed_groups: list[str] | None, allowed_users: list[str] | None, managed_policy_arns: list[str] | None, inline_policy: dict | None, max_duration: int | None) -> None`:**
1. Assume the admin management role
2. If `allowed_groups` or `allowed_users` changed: rebuild trust policy with the new groups/users lists and call `iam.update_assume_role_policy(RoleName=role_name, PolicyDocument=trust_policy)`
3. If `max_duration` changed: `iam.update_role(RoleName=role_name, MaxSessionDuration=max_duration)`
4. If `managed_policy_arns` changed: detach old policies, attach new ones
5. If `inline_policy` changed: `iam.put_role_policy()` or `iam.delete_role_policy()` if removed

**`async def delete_iam_role(aws_account_id: str, role_name: str) -> None`:**
1. Assume the admin management role
2. Detach all managed policies
3. Delete inline policies
4. `iam.delete_role(RoleName=role_name)`

### 3.2 — Job executor additions: `backend/services/jobs.py`

Add handlers for role job types.

**`async def run_create_role(job: Job, db: AsyncSession) -> None`:**
1. Load the role and its associated account from `job.result["role_id"]`
2. Call `create_iam_role()` with the role's config (including `allowed_groups`, `allowed_users`) and the account's `oidc_provider_arn`
3. Update `role.role_arn` with the returned ARN
4. Mark job completed

**`async def run_update_role(job: Job, db: AsyncSession) -> None`:**
1. Load role and account
2. Call `update_iam_role()` with changed fields (stored in `job.result["changes"]`), passing the account's `oidc_provider_arn` for trust policy rebuilds
3. Mark job completed

**`async def run_delete_role(job: Job, db: AsyncSession) -> None`:**
1. Load role and account
2. Call `delete_iam_role()`
3. Delete the Role row from the database
4. Mark job completed

### 3.3 — New endpoints on roles router: `backend/routers/roles.py`

Add role CRUD endpoints. Keep existing `GET /api/roles` and `POST /api/roles/assume` (assume implemented in Phase 4).

**`POST /api/accounts/{account_id}/roles` (admin only):**
1. Validate request body:
   ```python
   class RoleCreate(BaseModel):
       role_name: str
       template_id: Optional[uuid.UUID] = None  # if set, pre-fill managed_policy_arns from template
       managed_policy_arns: list[str] = []      # ignored if template_id set; user can edit before submit
       inline_policy: Optional[dict] = None
       allowed_groups: list[str] = []
       allowed_users: list[str] = []
       api_session_duration: int = 900
       console_session_duration: int = 3600
       description: Optional[str] = None
   ```
2. If `template_id` provided, look up template from DB and use its `managed_policy_arns` (user may have overridden them in the request)
3. Verify account exists and is `active`
4. Check no existing role with same name on this account (ConflictError)
5. Create `Role` row with `role_arn=""` (placeholder until IAM creation completes)
6. Create `Job` with `job_type="create_role"`, `result={"role_id": str(role.id)}`
7. Launch job as background task
8. Audit log: `role.create`
9. Return `RoleResponse` with 201 status

**`PATCH /api/accounts/{account_id}/roles/{role_id}` (admin only):**
1. Validate `RoleUpdate` body (all fields optional)
2. Look up role, verify it belongs to this account
3. Update DB fields that don't require IAM changes (description only)
4. If IAM-affecting fields changed (allowed_groups, allowed_users, managed_policy_arns, inline_policy, api/console duration): update DB fields and create `Job` with `job_type="update_role"`, `result={"role_id": ..., "changes": {...}}`
   - `allowed_groups`/`allowed_users` changes update the IAM trust policy
   - `managed_policy_arns`/`inline_policy` changes update attached policies
   - `api/console_session_duration` changes update the role's max session duration
5. Audit log: `role.update`
6. Return `RoleResponse`

**`DELETE /api/accounts/{account_id}/roles/{role_id}` (admin only):**
1. Look up role
2. Create `Job` with `job_type="delete_role"`, `result={"role_id": ..., "role_name": ..., "aws_account_id": ...}`
3. Audit log: `role.delete`
4. Return 202 Accepted

**`GET /api/roles` (update existing):**
1. Query all roles across all accounts
2. Filter to roles the current user can access: user's groups intersect `allowed_groups` OR user's sub in `allowed_users`
3. Join with Account to include account_name, aws_account_id in response
4. Return list grouped by account (or flat with account info)

**`GET /api/roles/templates`:**
1. Query all templates from DB
2. Return list of `RoleTemplateResponse`

Template CRUD endpoints (create, update, delete) are implemented in Phase 1.

### 3.4 — Schema updates: `backend/schemas/role.py`

Add/update schemas:

```python
class RoleCreate(BaseModel):
    role_name: str
    template_id: Optional[uuid.UUID] = None
    managed_policy_arns: list[str] = []
    inline_policy: Optional[dict[str, Any]] = None
    allowed_groups: list[str] = []
    allowed_users: list[str] = []
    api_session_duration: int = 900
    console_session_duration: int = 3600
    description: Optional[str] = None

class RoleUpdate(BaseModel):
    managed_policy_arns: Optional[list[str]] = None
    inline_policy: Optional[dict[str, Any]] = None
    allowed_groups: Optional[list[str]] = None
    allowed_users: Optional[list[str]] = None
    api_session_duration: Optional[int] = None
    console_session_duration: Optional[int] = None
    description: Optional[str] = None

class RoleTemplateResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str]
    managed_policy_arns: list[str]
```

Update `RoleResponse` to include all new fields.

### 3.5 — Tests

**Test cases:**
- `test_create_role_from_template` — admin creates role with template_id, managed_policy_arns auto-filled from DB template
- `test_create_role_custom` — admin creates role with explicit ARNs + inline policy
- `test_create_role_non_admin_returns_403`
- `test_create_role_duplicate_name_returns_409`
- `test_create_role_on_inactive_account_returns_400`
- `test_create_role_job_creates_iam_role` — job executor calls create_iam_role with mocked IAM, trust policy includes groups/users conditions
- `test_update_role_description_no_job` — updating description only doesn't create IAM job
- `test_update_role_groups_creates_job` — updating allowed_groups creates IAM job (trust policy update)
- `test_update_role_users_creates_job` — updating allowed_users creates IAM job (trust policy update)
- `test_update_role_policy_creates_job` — updating managed_policy_arns creates IAM job
- `test_delete_role_creates_job` — returns 202, job deletes IAM role
- `test_list_roles_filtered_by_groups` — user only sees roles matching their groups
- `test_list_roles_filtered_by_users` — user sees roles where their sub is in allowed_users
- `test_role_templates_endpoint` — returns templates from DB

## New files

```
backend/schemas/role.py (update existing)
tests/unit/routers/test_roles.py (update existing)
tests/unit/services/test_aws_iam.py
```

## Definition of done

- Admin can create roles on active accounts (from template or custom)
- IAM role created in target account with correct trust policy and attached policies
- Roles can be updated (DB-only changes are instant, IAM changes go through jobs)
- Roles can be deleted (IAM role removed, DB row deleted)
- Non-admin users see only roles they're allowed to assume
- Role templates endpoint works
- All operations audit logged
- Tests pass with mocked IAM
