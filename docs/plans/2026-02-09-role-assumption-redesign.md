# Role Assumption Redesign: AssumeRole from Groundwork Account

## Overview

Replace the current OIDC-federation-to-child-account model (`AssumeRoleWithWebIdentity`) with a
centralized `AssumeRole` from the Groundwork AWS account. All access control moves to the
application layer. The OIDC provider is removed from child accounts.

## Current Model

1. User authenticates with Groundwork via OIDC.
2. Backend obtains fresh `id_token` from the OIDC provider.
3. Backend calls `sts:AssumeRoleWithWebIdentity` against a role in the child account, passing the
   user's JWT.
4. Child account trust policy validates `aud` and optionally `sub` claims from the JWT against an
   OIDC provider registered in that account.
5. Console URL generated via federation endpoint, returned as JSON from `POST /api/roles/console`.

## New Model

1. User authenticates with Groundwork via OIDC (unchanged).
2. Backend checks the user's OIDC claims (groups, sub) against the role's `allowed_groups` /
   `allowed_users` — all access control lives in the application layer.
3. Backend calls `sts:AssumeRole` from the Groundwork account into the child account role, passing
   an External ID.
4. For CLI/SDK credentials: `POST /api/roles/assume` returns temporary credentials as JSON.
5. For console access: `GET /api/federate?account_id=<id>&role=<name>` generates a federation URL
   and returns a 302 redirect to the AWS console.

## Trust Policy

Each role created in child accounts gets a single-statement trust policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowGroundworkAssume",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::{groundwork_account_id}:root"
      },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": {
          "sts:ExternalId": "Groundwork-{16_hex_chars}"
        }
      }
    }
  ]
}
```

- Principal: Groundwork AWS account root.
- Action: `sts:AssumeRole` (not `AssumeRoleWithWebIdentity`).
- Condition: External ID only.

## External ID

- Format: `Groundwork-{first 16 hex chars of SHA-256(role_id + account_id)}`.
- Deterministic — can be recomputed from existing data, no new database column.
- Provides confusion-deputy protection. Not a secret.

## Bootstrap StackSet Changes

**Removed:**

- `AWS::IAM::OIDCProvider` resource from the CloudFormation template.
- `get_oidc_thumbprint()` function and related OIDC thumbprint logic.
- OIDC-related parameters (issuer URL, client ID, thumbprint) from the template builder.

**Kept unchanged:**

- `GroundworkAdmin-DO-NOT-DELETE` role — still needed for backend to create/manage IAM roles in
  child accounts. Trust policy still references Groundwork account root with `sts:AssumeRole`.

## Endpoints

| Current | New | Method | Notes |
|---------|-----|--------|-------|
| `POST /api/roles/assume` | `POST /api/roles/assume` | POST | Switches to `sts:AssumeRole` internally |
| `POST /api/roles/console` | `GET /api/federate` | GET | Query params: `account_id`, `role`. Returns 302 redirect |

### POST /api/roles/assume

1. Authenticate user via OIDC session.
2. Check `allowed_groups` / `allowed_users` against user's claims.
3. Compute External ID.
4. Call `sts:AssumeRole` from default Groundwork session.
5. Return credentials as JSON.

### GET /api/federate

1. Query params: `account_id` (UUID), `role` (role name string).
2. Authenticate user via OIDC session.
3. Look up role by `(account_id, role_name)`.
4. Check `allowed_groups` / `allowed_users`.
5. Call `sts:AssumeRole` with `console_session_duration`.
6. Exchange credentials for signin token via AWS federation endpoint.
7. Return 302 redirect to the console login URL.

## Access Control

Single-layer enforcement at the application level:

- Backend checks `user.groups ∩ role.allowed_groups ≠ ∅` OR `user.sub ∈ role.allowed_users`.
- The IAM trust policy only verifies the call comes from the Groundwork account with the correct
  External ID. It has no knowledge of individual users.

## Database Changes

No schema changes. All existing columns on the Role model are retained:

- `allowed_groups`, `allowed_users` — enforced at application layer.
- `api_session_duration`, `console_session_duration` — passed to `sts:AssumeRole`.
- `role_arn` — set during IAM creation.
- External ID is computed, not stored.

## AWS Service Layer Changes (aws.py)

**Remove:**

- `assume_role_with_web_identity()` function.
- `get_oidc_thumbprint()` function.
- OIDC provider resource from StackSet template.

**Add:**

- `assume_role(role_arn, session_name, external_id, duration)` — STS call from default session.

**Modify:**

- `_build_trust_policy()` — simplified single-statement policy with account root principal and
  External ID condition.
- `get_console_url()` — receives credentials from `assume_role()` instead of
  `assume_role_with_web_identity()`.

## Other Removals

- `POST /api/roles/console` endpoint.
- `ConsoleUrlResponse` schema.
- `get_fresh_id_token()` dependency (if only used for STS calls).
- References to `AssumeRoleWithWebIdentity` throughout the codebase.

## Config

No config removals. `GW_OIDC_ISSUER_URL` and `GW_OIDC_CLIENT_ID` remain for the login flow.
