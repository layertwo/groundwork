# Groundwork Service Design

Self-service AWS account factory with federated access via OIDC.

## Architecture

FastAPI backend serves a React frontend from a single container. PostgreSQL for persistence. The backend acts as both the control plane (provisioning accounts, managing IAM roles) and the access broker (assuming roles on behalf of users, generating console URLs).

Three operational modes:

1. **Auth gateway** — OIDC login, session cookie, JWT storage
2. **Account provisioning** — Control Tower CreateManagedAccount, bootstrap OIDC provider + admin management role via IAM API calls
3. **Role management & assumption** — Create/manage IAM roles in target accounts, broker AssumeRoleWithWebIdentity + console federation

## Configuration

The admin management role name is configurable via `GW_ADMIN_ROLE_NAME` (default: `GroundworkAdmin-DO-NOT-DELETE`). This is the role Groundwork creates in each managed account for ongoing IAM operations.

## Auth Flow (OIDC)

**Login:**
1. `GET /api/auth/login` — backend generates state + nonce, creates Session row (no user yet), redirects to OIDC provider authorization endpoint with `scope=openid profile email groups`
2. User authenticates with OIDC provider
3. `GET /api/auth/callback?code=...&state=...` — backend validates state, exchanges code for tokens, validates id_token (signature, nonce, expiry), extracts claims (sub, email, name, groups)
4. Upserts User row (create on first login, update groups/display_name on subsequent), updates Session with user_id + tokens, sets last_login_at
5. Sets httponly secure session cookie, redirects to frontend

**Session management:**
- `/api/auth/me` — returns user info from session
- `/api/auth/status` — returns `{authenticated: true/false}`
- `/api/auth/logout` — clears session row + cookie
- Token refresh: when JWT nears expiry, backend uses refresh token transparently

**Auth dependency:**
`get_current_user` FastAPI dependency reads session cookie, looks up Session, checks expiry, returns User. All protected routes use this.

## Account Provisioning Pipeline

Admin creates an account specifying name, email, OU. Backend kicks off a multi-step job:

**Step 1 — Create account:**
Call Control Tower `CreateManagedAccount` API. Poll for completion. Store new AWS account ID.

**Step 2 — Bootstrap account:**
Assume `OrganizationAccountAccessRole` in the new account (exists by default in all Control Tower accounts). Then:
1. Create OIDC identity provider (`iam.create_open_id_connect_provider`) pointing to the configured OIDC issuer URL with Groundwork's client ID as audience
2. Create the admin management role (configurable, default `GroundworkAdmin-DO-NOT-DELETE`) with AdministratorAccess, trusting the management account

This is a one-time use of OrganizationAccountAccessRole. All future operations use the admin management role.

**Step 3 — Mark complete:**
Update account status to active, store OIDC provider ARN. If roles were requested during creation, kick off role creation jobs.

Job tracking: each step updates the jobs table with status and result JSONB. Failures mark the job as failed with error message, account stays in provisioning status.

## Role Management

Roles are per-account. Two creation paths:

1. **From template** — picks a predefined template (Admin, ReadOnly, PowerUser), pre-fills managed policy ARNs. User can edit before submitting and assigns groups/users.
2. **Custom** — user specifies role name, managed policy ARNs, optional inline policy JSON, assigns groups/users.

Templates are stored in the `role_templates` database table. Admins can create, update, and delete templates via API. Default templates are seeded during initial setup. Templates are a convenience for pre-filling — once a role is created, it has no ongoing link to the template. The user can freely edit the role's policies after creation.

**Creation flow:**
Backend assumes the admin management role in the target account → creates IAM role with trust policy referencing the account's OIDC provider (aud-gated to Groundwork's client ID) → attaches managed policies + optional inline policy → stores role metadata in DB.

**Trust policy structure:**

The trust policy enforces access at the IAM level using `aud` (audience) plus `groups` or `sub` conditions. Two statements provide OR semantics — a user can assume the role if they match either statement. IAM ANDs all conditions within a single statement, so groups and users must be separate statements.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowGroupAccess",
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::ACCOUNT:oidc-provider/idp.example.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "idp.example.com:aud": "groundwork-client-id"
        },
        "ForAnyValue:StringEquals": {
          "idp.example.com:groups": ["engineers", "platform-team"]
        }
      }
    },
    {
      "Sid": "AllowUserAccess",
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::ACCOUNT:oidc-provider/idp.example.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "idp.example.com:aud": "groundwork-client-id",
          "idp.example.com:sub": ["user-sub-1", "user-sub-2"]
        }
      }
    }
  ]
}
```

The OIDC issuer hostname in the trust policy is derived from `GW_OIDC_ISSUER_URL` at runtime. Statements with empty groups/users lists are omitted from the policy.

**Access control (dual enforcement):**
Access is enforced at two layers:
1. **Application layer** — Groundwork checks the user's groups/sub against the role's `allowed_groups`/`allowed_users` before calling STS
2. **IAM layer** — The trust policy independently validates `aud` + `groups`/`sub` claims in the JWT

A user can assume a role if their OIDC groups intersect `allowed_groups` OR their sub is in `allowed_users`. Changing `allowed_groups` or `allowed_users` requires updating the IAM trust policy (via a job), not just the DB.

## Role Assumption & Console Access

**API credentials:**
1. User clicks "Assume" in UI
2. Backend checks allowed_groups/allowed_users against user's session
3. Backend calls `AssumeRoleWithWebIdentity` with user's OIDC JWT, role ARN, and `api_session_duration`
4. Returns AccessKeyId, SecretAccessKey, SessionToken, expiration

**Console access:**
1. Same STS assume step
2. Backend packages temp creds as JSON, calls `https://signin.aws.amazon.com/federation?Action=getSigninToken&SessionDuration={console_session_duration}&Session={encoded_creds}`
3. Constructs login URL: `?Action=login&Destination=https://console.aws.amazon.com/&SigninToken=...`
4. Returns console URL to frontend, opened in new tab

**Per-role duration settings:**
- `api_session_duration` — TTL for STS temp credentials (default 900s / 15 min)
- `console_session_duration` — TTL for console signin token (default 3600s / 60 min)
- IAM role's max_session_duration set to the higher of the two

## Data Model Changes

Updates to the roles table from current schema:
- Add `managed_policy_arns: ARRAY(String)` — attached AWS managed policies
- Add `inline_policy: JSONB, nullable` — optional custom inline policy document
- Add `allowed_users: ARRAY(String)` — user subs who can assume (alongside existing allowed_groups)

New `role_templates` table (templates are a convenience for pre-filling role creation — no FK from roles back to templates):
- `id: UUID PK`
- `name: String(128) UNIQUE` — template name (e.g. "Admin", "ReadOnly")
- `description: Text` — human-readable description
- `managed_policy_arns: ARRAY(String)` — default managed policies for roles created from this template
- `created_at, updated_at: TimestampTZ`
- Add `api_session_duration: Integer, default 900` — STS credential TTL in seconds
- Add `console_session_duration: Integer, default 3600` — console session TTL in seconds

New config setting:
- `GW_ADMIN_ROLE_NAME: String, default "GroundworkAdmin-DO-NOT-DELETE"` — IAM role name created in managed accounts

## Audit

Every significant action logged to audit_log:
- `account.create`, `account.update` — account provisioning and changes
- `role.create`, `role.update`, `role.delete` — role lifecycle
- `role.assume` — every role assumption with role ID, account ID, user IP/user-agent
- `auth.login`, `auth.logout` — authentication events

## Build Phases

### Phase 1 — Database & Auth
- Update roles model with new columns
- Add get_current_user auth dependency
- Implement OIDC flow: /auth/login, /auth/callback, /auth/logout, /auth/me, /auth/status
- Role templates model + CRUD endpoints + seed data
- Tests: OIDC flow with mocked OIDC provider, session lifecycle

### Phase 2 — Account Provisioning
- AWS service layer (services/aws.py) with Control Tower, IAM, STS clients
- Account CRUD: create account kicks off provisioning job
- Job executor: background async task runner for the 3-step pipeline
- Job status endpoints: list/get
- Audit logging for account operations
- Tests: provisioning pipeline with mocked AWS APIs

### Phase 3 — Role Management
- Create/update/delete roles on an account (from template or custom)
- Job for IAM role creation: assume admin management role, create role + trust policy + attach policies
- Role list filtered by user's groups/subs
- Audit logging for role operations
- Tests: role lifecycle with mocked IAM

### Phase 4 — Role Assumption & Console
- Assume role endpoint: access check, AssumeRoleWithWebIdentity, return creds
- Console URL endpoint: get signin token from federation endpoint, return URL
- Audit logging for every assumption
- Tests: assumption flow, credential format, console URL construction

### Phase 5 — React UI
- Auth: login/logout, user info display
- Account list + creation form
- Job status tracking (polling)
- Role list per account, assume buttons, credential display, console link
- Role creation form (template picker + custom)
