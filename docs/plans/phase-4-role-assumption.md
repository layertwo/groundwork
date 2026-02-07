# Phase 4 — Role Assumption & Console Access

## Goal

Authenticated users can assume roles they have access to, receiving either temporary AWS API credentials or a console login URL.

## Prerequisites

- Phase 3 complete (roles exist in DB with valid `role_arn`, access control fields populated)
- OIDC provider exists in target accounts (created during account provisioning)
- User has a valid session with an `id_token` JWT

## Steps

### 4.1 — AWS service layer additions: `backend/services/aws.py`

**`async def assume_role_with_web_identity(role_arn: str, id_token: str, session_duration: int, session_name: str) -> dict`:**
1. Call STS in the target account's region:
   ```python
   sts.assume_role_with_web_identity(
       RoleArn=role_arn,
       RoleSessionName=session_name,  # use user's email or sub
       WebIdentityToken=id_token,
       DurationSeconds=session_duration,
   )
   ```
2. Return `{"access_key_id": ..., "secret_access_key": ..., "session_token": ..., "expiration": ...}`

**`async def get_console_url(credentials: dict, console_session_duration: int, issuer: str) -> str`:**
1. Package credentials as JSON:
   ```python
   session_json = json.dumps({
       "sessionId": credentials["access_key_id"],
       "sessionKey": credentials["secret_access_key"],
       "sessionToken": credentials["session_token"],
   })
   ```
2. Call federation endpoint to get signin token:
   ```
   GET https://signin.aws.amazon.com/federation
       ?Action=getSigninToken
       &SessionDuration={console_session_duration}
       &Session={url_encode(session_json)}
   ```
3. Construct login URL:
   ```
   https://signin.aws.amazon.com/federation
       ?Action=login
       &Issuer={url_encode(issuer)}
       &Destination={url_encode("https://console.aws.amazon.com/")}
       &SigninToken={signin_token}
   ```
4. Return the login URL

### 4.2 — Implement assume endpoints: `backend/routers/roles.py`

**`POST /api/roles/assume` (requires `get_current_user`):**
1. Validate `AssumeRoleRequest` body (contains `role_id`)
2. Look up Role by ID, join Account
3. **Access check:** verify user's groups intersect `role.allowed_groups` OR user's sub is in `role.allowed_users`. If not, raise `ForbiddenError`
4. Verify account status is `active`
5. Get user's `id_token` from their session
6. Call `assume_role_with_web_identity(role.role_arn, id_token, role.api_session_duration, user.email)`
7. Audit log: `role.assume` with detail including role_id, account_id, role_name
8. Return `AssumeRoleResponse`

**`POST /api/roles/console` (requires `get_current_user`):**
1. Same access check as assume
2. Call `assume_role_with_web_identity()` with `role.console_session_duration`
3. Call `get_console_url()` with the credentials, `role.console_session_duration`, and `settings.app_url` as issuer
4. Audit log: `role.console` with same detail
5. Return `ConsoleUrlResponse`

### 4.3 — Schema updates: `backend/schemas/role.py`

Add:
```python
class ConsoleUrlResponse(BaseModel):
    console_url: str
    expiration: datetime
```

Update `AssumeRoleResponse` — already has the right fields (access_key_id, secret_access_key, session_token, expiration).

### 4.4 — Handle token expiry

In the assume flow, the user's `id_token` must be valid (not expired) for STS to accept it. If it's near expiry:

1. Check token expiry before calling STS
2. If expired or < 60s remaining, use the session's `refresh_token` to get new tokens from the OIDC provider (via `backend/services/oidc.py` `refresh_tokens()`)
3. Update the session row with new tokens
4. Use the fresh `id_token` for the STS call

This logic should live in the auth dependency or a helper called before assumption.

### 4.5 — Tests

**Test cases:**
- `test_assume_role_success` — user with matching group gets credentials
- `test_assume_role_forbidden_no_group_match` — user without matching group/sub gets 403
- `test_assume_role_allowed_users_match` — user's sub in allowed_users can assume
- `test_assume_role_inactive_account_rejected` — account not active returns error
- `test_assume_role_token_refresh` — expired id_token triggers refresh before STS call
- `test_console_url_success` — returns valid federation URL
- `test_console_url_structure` — URL contains correct Action, Destination, SigninToken params
- `test_assume_role_audit_logged` — audit_log entry created with correct action/detail
- `test_assume_role_unauthenticated_returns_401`

Mock STS `assume_role_with_web_identity` to return fake credentials. Mock the federation endpoint (`signin.aws.amazon.com`) to return a fake signin token.

## New files

```
tests/unit/routers/test_roles.py (update existing)
tests/unit/services/test_aws_sts.py
```

## Definition of done

- Authenticated user can POST `/api/roles/assume` with a role_id and receive temporary AWS credentials
- Authenticated user can POST `/api/roles/console` with a role_id and receive a console login URL
- Access control enforced: only users matching allowed_groups or allowed_users can assume
- Expired OIDC tokens are refreshed transparently before STS calls
- Every assumption is audit logged with user, role, account, and IP details
- Tests pass with mocked STS and federation endpoint
