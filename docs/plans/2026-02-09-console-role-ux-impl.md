# Console Role UX Improvements Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Improve the console role experience with alphabetical sorting, last-used tracking, cleaner session names, and a deep-linkable federate page.

**Architecture:** Backend changes add two model columns (`Role.last_used_at`, `User.preferred_username`) in one migration, modify the roles query ordering and federation session name. Frontend changes add a `/federate` deep-link page and redirect-after-login support.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, Alembic, React, TypeScript, React Router

---

### Task 1: Add `last_used_at` to Role model

**Files:**
- Modify: `backend/models/role.py:1-51`

**Step 1: Add the column**

In `backend/models/role.py`, add the import for `TIMESTAMP` and add the `last_used_at` column after `error_message`:

Add to imports (line 6):
```python
from sqlalchemy import ARRAY, ForeignKey, Index, Integer, String, Text, UniqueConstraint
```
becomes:
```python
from sqlalchemy import ARRAY, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
```

Wait — `JSONB` is already imported from `postgresql`. Change the import to:
```python
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
```

Add after `error_message` (after line 48):
```python
last_used_at: Mapped[Optional[datetime]] = mapped_column(
    TIMESTAMP(timezone=True), nullable=True
)
```

Also add `datetime` to the typing imports at line 2:
```python
from typing import TYPE_CHECKING, Any, Optional
```
becomes:
```python
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional
```

**Step 2: Commit**

```bash
git add backend/models/role.py
git commit -m "feat: add last_used_at column to Role model"
```

---

### Task 2: Add `preferred_username` to User model

**Files:**
- Modify: `backend/models/user.py:1-43`

**Step 1: Add the column**

In `backend/models/user.py`, add `preferred_username` after `display_name` (after line 17):

```python
preferred_username: Mapped[str] = mapped_column(
    String(255), nullable=False, server_default=""
)
```

**Step 2: Commit**

```bash
git add backend/models/user.py
git commit -m "feat: add preferred_username column to User model"
```

---

### Task 3: Create Alembic migration for both new columns

**Files:**
- Create: `alembic/versions/<auto>_add_last_used_at_and_preferred_username.py`

**Step 1: Generate the migration**

```bash
PYTHONPATH=. alembic revision --autogenerate -m "add last_used_at and preferred_username"
```

**Step 2: Review the generated migration**

Verify it contains:
- `op.add_column('roles', sa.Column('last_used_at', TIMESTAMP(timezone=True), nullable=True))`
- `op.add_column('users', sa.Column('preferred_username', sa.String(255), server_default='', nullable=False))`

And the downgrade drops both columns.

**Step 3: Apply the migration**

```bash
PYTHONPATH=. alembic upgrade head
```

**Step 4: Commit**

```bash
git add alembic/
git commit -m "chore: migration for last_used_at and preferred_username columns"
```

---

### Task 4: Add alphabetical ordering to list_roles query

**Files:**
- Modify: `backend/routers/roles.py:307-325`
- Test: `tests/unit/routers/test_roles.py`

**Step 1: Write the failing test**

Add to `class TestListRoles` in `tests/unit/routers/test_roles.py`:

```python
async def test_list_roles_alphabetical_order(self, client, db_session):
    """Roles are returned sorted alphabetically by role_name."""
    admin, session_id = await _create_authenticated_user(
        db_session, is_admin=True, groups=[], sub="admin-alpha-sort"
    )
    account = await _create_active_account(db_session, admin)

    for name in ["Zebra", "Admin", "PowerUser"]:
        db_session.add(
            Role(
                account_id=account.id,
                role_name=name,
                role_arn=f"arn:aws:iam::123456789012:role/{name}",
                allowed_groups=["devs"],
                status="active",
            )
        )
    await db_session.flush()

    response = await client.get("/api/roles", cookies=_cookies(session_id))

    assert response.status_code == 200
    names = [r["role_name"] for r in response.json()]
    assert names == sorted(names)
```

**Step 2: Run test to verify it fails**

```bash
PYTHONPATH=. pytest tests/unit/routers/test_roles.py::TestListRoles::test_list_roles_alphabetical_order -v
```

Expected: FAIL — roles returned in insertion order, not alphabetical.

**Step 3: Add ORDER BY to the query**

In `backend/routers/roles.py`, change line 312:

```python
result = await db.execute(select(Role).options(joinedload(Role.account)))
```

to:

```python
result = await db.execute(
    select(Role).options(joinedload(Role.account)).order_by(Role.role_name)
)
```

**Step 4: Run test to verify it passes**

```bash
PYTHONPATH=. pytest tests/unit/routers/test_roles.py::TestListRoles::test_list_roles_alphabetical_order -v
```

Expected: PASS

**Step 5: Run full test suite to check for regressions**

```bash
PYTHONPATH=. pytest tests/unit/routers/test_roles.py -v
```

**Step 6: Commit**

```bash
git add backend/routers/roles.py tests/unit/routers/test_roles.py
git commit -m "feat: return roles sorted alphabetically by role_name"
```

---

### Task 5: Update `last_used_at` on federation and add to response schema

**Files:**
- Modify: `backend/routers/roles.py:363-432`
- Modify: `backend/schemas/role.py:116-134`
- Test: `tests/unit/routers/test_roles.py`

**Step 1: Write the failing test**

Add to `class TestFederate` in `tests/unit/routers/test_roles.py`:

```python
async def test_federate_updates_last_used_at(self, client, db_session):
    """Federation updates the role's last_used_at timestamp."""
    user, session_id = await _create_user_with_tokens(
        db_session, groups=["devs"], sub="dev-last-used"
    )
    admin, _ = await _create_authenticated_user(db_session, is_admin=True)
    account = await _create_active_account(db_session, admin)
    role = await _create_role_for_assumption(
        db_session, account, allowed_groups=["devs"]
    )

    assert role.last_used_at is None

    with patch("backend.routers.roles.aws.assume_role", new_callable=AsyncMock) as mock_assume:
        mock_assume.return_value = FAKE_STS_CREDS

        await client.get(
            f"/api/federate?account_id={account.aws_account_id}"
            f"&role={role.role_name}&method=cli",
            cookies=_cookies(session_id),
        )

    await db_session.refresh(role)
    assert role.last_used_at is not None
```

Also add a test that `last_used_at` appears in the list response:

```python
async def test_list_roles_includes_last_used_at(self, client, db_session):
    """RoleResponse includes last_used_at field."""
    admin, session_id = await _create_authenticated_user(
        db_session, is_admin=True, groups=[], sub="admin-last-used-list"
    )
    account = await _create_active_account(db_session, admin)
    db_session.add(
        Role(
            account_id=account.id,
            role_name="TestRole",
            role_arn="arn:aws:iam::123456789012:role/TestRole",
            allowed_groups=["devs"],
            status="active",
        )
    )
    await db_session.flush()

    response = await client.get("/api/roles", cookies=_cookies(session_id))

    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert "last_used_at" in data[0]
    assert data[0]["last_used_at"] is None
```

Place the second test in `class TestListRoles`.

**Step 2: Run tests to verify they fail**

```bash
PYTHONPATH=. pytest tests/unit/routers/test_roles.py::TestFederate::test_federate_updates_last_used_at tests/unit/routers/test_roles.py::TestListRoles::test_list_roles_includes_last_used_at -v
```

Expected: FAIL — `last_used_at` not set and not in schema.

**Step 3: Add `last_used_at` to RoleResponse schema**

In `backend/schemas/role.py`, add after `updated_at` (line 131):

```python
last_used_at: Optional[datetime] = None
```

**Step 4: Update federation endpoint to set `last_used_at`**

In `backend/routers/roles.py`, add this import at the top:

```python
from datetime import datetime, timezone
```

In the `federate` function, after the `credentials = await aws.assume_role(...)` call (after line 382), add:

```python
loaded_role.last_used_at = datetime.now(timezone.utc)
db.add(loaded_role)
```

**Step 5: Run tests to verify they pass**

```bash
PYTHONPATH=. pytest tests/unit/routers/test_roles.py::TestFederate::test_federate_updates_last_used_at tests/unit/routers/test_roles.py::TestListRoles::test_list_roles_includes_last_used_at -v
```

Expected: PASS

**Step 6: Run full roles test suite**

```bash
PYTHONPATH=. pytest tests/unit/routers/test_roles.py -v
```

**Step 7: Commit**

```bash
git add backend/routers/roles.py backend/schemas/role.py tests/unit/routers/test_roles.py
git commit -m "feat: track and expose last_used_at on role federation"
```

---

### Task 6: Store `preferred_username` in auth callback

**Files:**
- Modify: `backend/routers/auth.py:89-117`
- Test: `tests/unit/routers/test_auth.py`

**Step 1: Write the failing test**

Add a test in `tests/unit/routers/test_auth.py` (in the appropriate callback test class):

```python
async def test_callback_stores_preferred_username(
    self, client, db_session, mock_oidc_exchange, mock_oidc_validate
):
    """Callback stores preferred_username from OIDC claims."""
    session = Session(
        state="test-state-pref", nonce="test-nonce-pref",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(session)
    await db_session.flush()

    mock_oidc_exchange.return_value = make_token_response(nonce="test-nonce-pref")
    mock_oidc_validate.return_value = {
        "sub": "pref-username-sub",
        "email": "alice@example.com",
        "name": "Alice Smith",
        "preferred_username": "alice",
        "groups": ["devs"],
        "nonce": "test-nonce-pref",
    }

    response = await client.get(
        "/api/auth/callback",
        params={"code": "auth-code", "state": "test-state-pref"},
        follow_redirects=False,
    )

    assert response.status_code == 302

    result = await db_session.execute(
        select(User).where(User.sub == "pref-username-sub")
    )
    user = result.scalar_one()
    assert user.preferred_username == "alice"
```

Check what imports and helpers are already in test_auth.py. The test needs `make_token_response` from `tests.fixtures.oidc` (verify this exists — if not, construct the token response dict inline).

**Step 2: Run test to verify it fails**

```bash
PYTHONPATH=. pytest tests/unit/routers/test_auth.py::TestCallback::test_callback_stores_preferred_username -v
```

Expected: FAIL — `preferred_username` not set on user.

**Step 3: Update auth callback to store preferred_username**

In `backend/routers/auth.py`, after line 96:

```python
display_name = claims.get("name") or claims.get("preferred_username", "")
groups = claims.get("groups", [])
```

Add:

```python
preferred_username = claims.get("preferred_username", "")
```

In the user creation block (line 103-109), add `preferred_username`:

```python
user = User(
    sub=sub,
    email=email,
    display_name=display_name,
    preferred_username=preferred_username,
    groups=groups,
    last_login_at=now,
)
```

In the user update block (lines 113-116), add:

```python
user.preferred_username = preferred_username
```

**Step 4: Run test to verify it passes**

```bash
PYTHONPATH=. pytest tests/unit/routers/test_auth.py::TestCallback::test_callback_stores_preferred_username -v
```

Expected: PASS

**Step 5: Run full auth test suite**

```bash
PYTHONPATH=. pytest tests/unit/routers/test_auth.py -v
```

**Step 6: Commit**

```bash
git add backend/routers/auth.py tests/unit/routers/test_auth.py
git commit -m "feat: store preferred_username from OIDC claims on login"
```

---

### Task 7: Change session name to `Groundwork-<username>`

**Files:**
- Modify: `backend/routers/roles.py:39-48,377-379`
- Test: `tests/unit/routers/test_roles.py`

**Step 1: Write the failing test**

Add to `class TestFederate` in `tests/unit/routers/test_roles.py`:

```python
async def test_session_name_uses_preferred_username(self, client, db_session):
    """Federation uses Groundwork-<preferred_username> as session name."""
    user, session_id = await _create_user_with_tokens(
        db_session, groups=["devs"], sub="dev-session-name"
    )
    user.preferred_username = "alice"
    db_session.add(user)
    await db_session.flush()

    admin, _ = await _create_authenticated_user(db_session, is_admin=True)
    account = await _create_active_account(db_session, admin)
    role = await _create_role_for_assumption(
        db_session, account, allowed_groups=["devs"]
    )

    with patch("backend.routers.roles.aws.assume_role", new_callable=AsyncMock) as mock_assume:
        mock_assume.return_value = FAKE_STS_CREDS

        await client.get(
            f"/api/federate?account_id={account.aws_account_id}"
            f"&role={role.role_name}&method=cli",
            cookies=_cookies(session_id),
        )

    call_kwargs = mock_assume.call_args.kwargs
    assert call_kwargs["session_name"] == "Groundwork-alice"
```

**Step 2: Run test to verify it fails**

```bash
PYTHONPATH=. pytest tests/unit/routers/test_roles.py::TestFederate::test_session_name_uses_preferred_username -v
```

Expected: FAIL — session name is still the sanitized email.

**Step 3: Update the session name logic**

In `backend/routers/roles.py`, rename and update the sanitizer function (lines 43-48):

```python
def _sanitize_session_name(raw: str) -> str:
    """Sanitize a string for use as STS RoleSessionName.

    AWS requires RoleSessionName to match [\\w+=,.@\\-]* and be <= 64 chars.
    """
    return _SESSION_NAME_RE.sub("_", raw)[:_SESSION_NAME_MAX_LEN]
```

Then change line 379:

```python
session_name=_sanitize_session_name(user.email),
```

to:

```python
session_name=_sanitize_session_name(f"Groundwork-{user.preferred_username}"),
```

**Step 4: Run test to verify it passes**

```bash
PYTHONPATH=. pytest tests/unit/routers/test_roles.py::TestFederate::test_session_name_uses_preferred_username -v
```

Expected: PASS

**Step 5: Run full roles test suite**

```bash
PYTHONPATH=. pytest tests/unit/routers/test_roles.py -v
```

Note: Existing tests that check `mock_assume.call_args.kwargs["session_name"]` may need updating if they assert the old email-based session name. Fix any failures by updating expected values.

**Step 6: Commit**

```bash
git add backend/routers/roles.py tests/unit/routers/test_roles.py
git commit -m "feat: use Groundwork-<username> as STS session name"
```

---

### Task 8: Add `last_used_at` to frontend TypeScript interface and display

**Files:**
- Modify: `frontend/src/api/roles.ts:3-19`
- Modify: `frontend/src/pages/AccountDetail.tsx`

**Step 1: Add `last_used_at` to RoleResponse interface**

In `frontend/src/api/roles.ts`, add after `updated_at: string` (line 18):

```typescript
last_used_at: string | null
```

**Step 2: Add relative time display to role cards**

In `frontend/src/pages/AccountDetail.tsx`, add a helper function before the component:

```typescript
function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.floor(hrs / 24)
  return `${days}d ago`
}
```

Then in the role card, add after the description/error section inside `<CardHeader>` (after the `CardDescription` and error `<p>` blocks, before `<CardAction>`):

```tsx
<p className="text-xs text-muted-foreground">
  {role.last_used_at ? `Last used ${relativeTime(role.last_used_at)}` : 'Never used'}
</p>
```

**Step 3: Verify the frontend builds**

```bash
cd frontend && npm run build
```

**Step 4: Commit**

```bash
git add frontend/src/api/roles.ts frontend/src/pages/AccountDetail.tsx
git commit -m "feat: display last_used_at on role cards"
```

---

### Task 9: Add redirect-after-login to ProtectedRoute

**Files:**
- Modify: `frontend/src/components/ProtectedRoute.tsx:1-20`
- Modify: `frontend/src/pages/Dashboard.tsx:32-46`

**Step 1: Save intended URL in ProtectedRoute**

Replace the contents of `frontend/src/components/ProtectedRoute.tsx`:

```tsx
import { useEffect } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

const REDIRECT_KEY = 'gw:redirect_after_login'

export function saveRedirectUrl() {
  const path = window.location.pathname + window.location.search
  if (path && path !== '/') {
    sessionStorage.setItem(REDIRECT_KEY, path)
  }
}

export function consumeRedirectUrl(): string | null {
  const url = sessionStorage.getItem(REDIRECT_KEY)
  sessionStorage.removeItem(REDIRECT_KEY)
  if (url && url.startsWith('/')) {
    return url
  }
  return null
}

export default function ProtectedRoute({
  children,
}: {
  children: React.ReactNode
}) {
  const { isAuthenticated, isLoading } = useAuth()

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      saveRedirectUrl()
    }
  }, [isLoading, isAuthenticated])

  if (isLoading) {
    return <div className="loading">Loading...</div>
  }

  if (!isAuthenticated) {
    return <Navigate to="/" replace />
  }

  return <>{children}</>
}
```

**Step 2: Consume redirect URL in Dashboard after login**

In `frontend/src/pages/Dashboard.tsx`, import `consumeRedirectUrl` and `useNavigate`:

At the top, add to imports:
```typescript
import { consumeRedirectUrl } from '@/components/ProtectedRoute'
```

(`useNavigate` is already imported.)

Inside the `Dashboard` component, after the `const { isAuthenticated, isAdmin, isLoading: authLoading } = useAuth()` line (line 49), add:

```typescript
useEffect(() => {
  if (isAuthenticated) {
    const redirect = consumeRedirectUrl()
    if (redirect) {
      navigate(redirect, { replace: true })
    }
  }
}, [isAuthenticated, navigate])
```

Also add `useEffect` to the React import if not already present (line 1):
```typescript
import { useEffect, useMemo, useState } from 'react'
```

**Step 3: Verify the frontend builds**

```bash
cd frontend && npm run build
```

**Step 4: Commit**

```bash
git add frontend/src/components/ProtectedRoute.tsx frontend/src/pages/Dashboard.tsx
git commit -m "feat: redirect to original URL after login"
```

---

### Task 10: Create FederatePage and add route

**Files:**
- Create: `frontend/src/pages/FederatePage.tsx`
- Modify: `frontend/src/App.tsx:1-79`

**Step 1: Create the FederatePage component**

Create `frontend/src/pages/FederatePage.tsx`:

```tsx
import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { federate } from '@/api/roles'
import { ApiError } from '@/api/client'
import type { ConsoleUrlResponse } from '@/api/roles'

export default function FederatePage() {
  const [params] = useSearchParams()
  const accountId = params.get('account_id')
  const roleName = params.get('role_name')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!accountId || !roleName) {
      setError('Missing account_id or role_name parameter')
      return
    }

    let cancelled = false

    federate(accountId, roleName, 'console')
      .then((res) => {
        if (cancelled) return
        const { console_url } = res as ConsoleUrlResponse
        const url = new URL(console_url)
        if (url.protocol !== 'https:' || !url.hostname.endsWith('.aws.amazon.com')) {
          setError('Invalid console URL returned')
          return
        }
        window.location.href = console_url
      })
      .catch((err) => {
        if (cancelled) return
        setError(err instanceof ApiError ? err.detail : 'Failed to federate')
      })

    return () => {
      cancelled = true
    }
  }, [accountId, roleName])

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[40vh] gap-4">
        <p className="text-destructive">{error}</p>
        <Link to="/" className="text-sm text-muted-foreground hover:underline">
          Back to Dashboard
        </Link>
      </div>
    )
  }

  return (
    <div className="flex flex-col items-center justify-center min-h-[40vh] gap-2">
      <p className="text-muted-foreground">Redirecting to AWS Console...</p>
    </div>
  )
}
```

**Step 2: Add the route in App.tsx**

In `frontend/src/App.tsx`, add the import:

```typescript
import FederatePage from '@/pages/FederatePage'
```

Add the route inside the `<Route element={<Layout />}>` block, after the role-templates route (after line 71):

```tsx
<Route
  path="/federate"
  element={
    <ProtectedRoute>
      <FederatePage />
    </ProtectedRoute>
  }
/>
```

**Step 3: Verify the frontend builds**

```bash
cd frontend && npm run build
```

**Step 4: Commit**

```bash
git add frontend/src/pages/FederatePage.tsx frontend/src/App.tsx
git commit -m "feat: add /federate deep-link page for console access"
```

---

### Task 11: Run full test suite and lint

**Step 1: Run backend tests**

```bash
PYTHONPATH=. pytest -v
```

Expected: All tests pass.

**Step 2: Run linting and formatting**

```bash
black backend/ tests/ && isort backend/ tests/
flake8 backend/ tests/
```

Fix any issues.

**Step 3: Build frontend**

```bash
cd frontend && npm run build
```

Expected: Clean build, no errors.

**Step 4: Commit any fixes**

```bash
git add -A
git commit -m "fix: lint and formatting cleanup"
```

(Only if there were changes.)
