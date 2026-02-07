# Phase 1 — Database Updates & OIDC Authentication

## Goal

Get users logging in via OIDC and establish the auth dependency that all subsequent phases rely on.

## Prerequisites

- OIDC provider running with a configured client (client_id, client_secret, redirect_uri)
- `.env` populated with `GW_OIDC_ISSUER_URL`, `GW_OIDC_CLIENT_ID`, `GW_OIDC_CLIENT_SECRET`

## Steps

### 1.1 — Add authlib dependency

Add `authlib` to `requirements.txt`. This handles OIDC discovery, token exchange, and JWT validation.

```
authlib==1.6.0
```

### 1.2 — Alembic migration: update roles table

Add new columns to `backend/models/role.py`:

```python
managed_policy_arns: Mapped[list[str]] = mapped_column(
    ARRAY(String), nullable=False, server_default="{}"
)
inline_policy: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
allowed_users: Mapped[list[str]] = mapped_column(
    ARRAY(String), nullable=False, server_default="{}"
)
api_session_duration: Mapped[int] = mapped_column(
    Integer, nullable=False, default=900, server_default="900"
)
console_session_duration: Mapped[int] = mapped_column(
    Integer, nullable=False, default=3600, server_default="3600"
)
```

Remove the existing `max_session_duration` column (replaced by the two duration columns above).

Update `backend/schemas/role.py` `RoleResponse` to match.

Generate and apply migration:
```bash
PYTHONPATH=. alembic revision --autogenerate -m "add role policy and duration columns"
PYTHONPATH=. alembic upgrade head
```

### 1.3 — OIDC service: `backend/services/oidc.py`

New file. Wraps authlib's async OIDC client.

**Functions:**
- `get_oidc_client() -> AsyncOAuth2Client` — creates client from settings, uses OIDC discovery (`.well-known/openid-configuration`) to get endpoints
- `create_authorization_url(state: str, nonce: str) -> str` — builds the redirect URL to OIDC provider with `scope=openid profile email groups`
- `exchange_code(code: str) -> dict` — exchanges authorization code for tokens at the token endpoint
- `validate_id_token(id_token: str, nonce: str) -> dict` — validates JWT signature via OIDC provider's JWKS, checks nonce/expiry, returns claims
- `refresh_tokens(refresh_token: str) -> dict` — uses refresh token to get new access/id tokens

All functions use `httpx.AsyncClient` internally (authlib integrates with httpx).

### 1.4 — Auth dependency: `backend/dependencies/auth.py`

New file. FastAPI dependencies for authentication.

**`get_current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User`:**
1. Read session ID from cookie (`gw_session`)
2. Query `Session` by ID, check `expires_at > now()`
3. If expired or missing, raise `GroundworkError("Not authenticated", 401)`
4. If session's `id_token` is near expiry (< 5 min), call `refresh_tokens()` and update the session row
5. Return the associated `User`

**`get_current_admin(user: User = Depends(get_current_user)) -> User`:**
1. Check `user.is_admin`
2. If not, raise `ForbiddenError`

### 1.5 — Implement auth router: `backend/routers/auth.py`

Replace all 501 stubs.

**`GET /api/auth/login`:**
1. Generate cryptographically random `state` (32 bytes hex) and `nonce` (32 bytes hex)
2. Create `Session` row with `state`, `nonce`, no `user_id`
3. Build authorization URL via OIDC service
4. Return `RedirectResponse` to OIDC authorization endpoint

**`GET /api/auth/callback?code=...&state=...`:**
1. Look up `Session` by `state`, validate it exists and was created < 10 min ago
2. Exchange `code` for tokens via OIDC service
3. Validate `id_token`, check `nonce` matches session
4. Extract claims: `sub`, `email`, `name` (or `preferred_username`), `groups`
5. Upsert `User`: select by `sub`, create if not found, update `email`, `display_name`, `groups`, `last_login_at` if exists
6. Update `Session`: set `user_id`, `access_token`, `refresh_token`, `id_token`, `expires_at` (from token expiry), clear `state`/`nonce`
7. Set httponly secure cookie `gw_session` = session ID, `SameSite=Lax`
8. Redirect to `settings.app_url`

**`POST /api/auth/logout`:**
1. Read session ID from cookie
2. Delete the `Session` row
3. Clear the cookie
4. Return `{"detail": "logged out"}`

**`GET /api/auth/me` (requires `get_current_user`):**
1. Return `UserInfo` schema from the current user

**`GET /api/auth/status`:**
1. Try to read session cookie and look up user
2. Return `AuthStatus(authenticated=True, user=UserInfo(...))` or `AuthStatus(authenticated=False)`
3. Do NOT raise on missing/expired session — this is a check endpoint

### 1.6 — Role templates model and endpoints

**New model: `backend/models/role_template.py`:**
```python
class RoleTemplate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "role_templates"
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    managed_policy_arns: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, server_default="{}"
    )
```

**Seed data migration:** Create an Alembic data migration that inserts default templates:
- Admin — `arn:aws:iam::aws:policy/AdministratorAccess`
- ReadOnly — `arn:aws:iam::aws:policy/ReadOnlyAccess`
- PowerUser — `arn:aws:iam::aws:policy/PowerUserAccess`

**Endpoints on roles router:**

`GET /api/roles/templates` — returns all templates.

`POST /api/roles/templates` (admin only) — create a new template.

`PATCH /api/roles/templates/{template_id}` (admin only) — update a template.

`DELETE /api/roles/templates/{template_id}` (admin only) — delete a template.

### 1.7 — Audit helper: `backend/services/audit.py`

New file. Thin helper used by all phases.

```python
async def log_event(
    db: AsyncSession,
    action: str,
    user_id: uuid.UUID | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    detail: dict | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    entry = AuditLog(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        detail=detail,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(entry)
```

Log `auth.login` in callback and `auth.logout` in logout endpoint.

### 1.8 — Tests

**Mock OIDC provider:** Create `tests/fixtures/oidc.py` with:
- `mock_oidc_discovery` — returns fake `.well-known/openid-configuration`
- `mock_token_exchange` — returns fake access/id/refresh tokens
- `mock_jwks` — returns fake JWKS for token validation
- `fake_id_token` — helper to create a valid JWT signed with the mock key

**Test cases:**
- `test_login_redirects_to_pocket_id` — GET /auth/login returns 302 to OIDC provider
- `test_callback_creates_user_and_session` — full callback flow with mocked OIDC provider
- `test_callback_updates_existing_user` — second login updates groups/display_name
- `test_callback_invalid_state_returns_error` — wrong state param rejected
- `test_me_returns_user_info` — authenticated request returns UserInfo
- `test_me_unauthenticated_returns_401` — no cookie returns 401
- `test_status_unauthenticated_returns_false` — no cookie returns `{authenticated: false}`
- `test_logout_clears_session` — session deleted, cookie cleared
- `test_expired_session_returns_401` — expired session rejected
- `test_role_templates_list` — GET /roles/templates returns seeded templates
- `test_role_templates_create` — admin can create a new template
- `test_role_templates_create_non_admin_returns_403`
- `test_role_templates_update` — admin can update a template
- `test_role_templates_delete` — admin can delete a template

## New files

```
backend/services/__init__.py
backend/services/oidc.py
backend/services/audit.py
backend/models/role_template.py
backend/dependencies/__init__.py
backend/dependencies/auth.py
tests/fixtures/oidc.py
tests/unit/routers/test_auth.py (update existing)
tests/unit/services/__init__.py
tests/unit/services/test_oidc.py
```

## Definition of done

- User can click login, authenticate with OIDC provider, and be redirected back with a session cookie
- `/api/auth/me` returns user info for authenticated requests
- `/api/auth/status` returns auth state without erroring for anonymous requests
- Logout clears session
- Role templates CRUD works, default templates seeded
- All auth events are audit logged
- Tests pass with mocked OIDC provider (no real IdP needed)
