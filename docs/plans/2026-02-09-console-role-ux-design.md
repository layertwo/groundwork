# Console Role UX Improvements

## Overview

Four targeted improvements to the console role experience: alphabetical sorting, last-used tracking,
cleaner session names, and a deep-linkable federate page.

## Changes

### 1. Alphabetical role sorting (backend)

Add `ORDER BY role_name` to the `GET /api/roles` query in `backend/routers/roles.py`. This ensures
roles are always returned alphabetically, which works correctly with future pagination.

**Files:**
- `backend/routers/roles.py` — add `.order_by(Role.role_name)` to the list query

### 2. `last_used_at` timestamp on roles

Record when a role was last assumed (by anyone, not per-user). Updated on every successful
federation (console or CLI).

**Model change:**
- Add `last_used_at: Mapped[Optional[datetime]]` to the `Role` model (nullable, defaults to `None`)

**Migration:**
- Single Alembic migration adds both `last_used_at` (Role) and `preferred_username` (User) columns

**Backend:**
- In the `/api/federate` endpoint, after successful `assume_role()`, set
  `loaded_role.last_used_at = datetime.now(timezone.utc)`

**Schema:**
- Add `last_used_at: Optional[datetime]` to `RoleResponse`

**Frontend:**
- Add `last_used_at: string | null` to the TypeScript `RoleResponse` interface
- Display on role cards as relative time (e.g., "Last used 3 hours ago") or "Never used"

### 3. Session name: `Groundwork-<username>`

Change the STS `RoleSessionName` from the sanitized email to `Groundwork-<preferred_username>`.
AWS displays this as `RoleName/RoleSessionName` in CloudTrail, so a role named `Admin` assumed by
user `alice` appears as `Admin/Groundwork-alice`.

**User model change:**
- Add `preferred_username: Mapped[str]` to the `User` model (non-nullable, default empty string)

**Migration:**
- Shared with change 2 above

**Auth callback change:**
- In `backend/routers/auth.py` callback, extract and store
  `claims.get("preferred_username", "")` on every login (create and update paths)

**Federation endpoint change:**
- Replace `session_name = _sanitize_session_name(user.email)` with
  `session_name = _sanitize_session_name(f"Groundwork-{user.preferred_username}")`
- The existing sanitizer handles invalid characters and 64-char truncation

### 4. `/federate` deep-link page

A new frontend route at `/federate?account_id=...&role_name=...` that redirects the user to the
AWS console. Supports sharing direct links to specific roles.

**Frontend:**
- New page `frontend/src/pages/FederatePage.tsx`:
  - Reads `account_id` and `role_name` from query params
  - Shows a loading state ("Redirecting to AWS Console...")
  - Calls the existing `federate()` API function
  - Redirects the browser via `window.location.href = console_url`
  - On error, shows message with link back to dashboard
- Add route in `App.tsx`: `/federate` wrapped in `ProtectedRoute`

**Redirect-after-login:**
- In `ProtectedRoute`, before redirecting unauthenticated users to `/`, save
  `window.location.pathname + window.location.search` to `sessionStorage` (key:
  `gw:redirect_after_login`)
- After login, when the user lands on the dashboard authenticated, check `sessionStorage` for the
  key. If present, remove it and navigate to that URL
- Validate the stored path starts with `/` to prevent open redirects

**No backend changes needed** — the existing `/api/federate` endpoint already accepts `account_id`
and `role_name` query params.
