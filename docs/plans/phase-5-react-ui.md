# Phase 5 — React UI

## Goal

Build the frontend that lets users authenticate, browse accounts/roles, create accounts and roles (admins), assume roles, and track provisioning jobs.

## Prerequisites

- Phases 1–4 complete (all API endpoints functional)
- Vite + React + TypeScript project initialized in `frontend/`

## Steps

### 5.1 — Project setup: `frontend/`

Initialize with Vite:
```bash
npm create vite@latest frontend -- --template react-ts
cd frontend && npm install
```

Key dependencies:
```
react-router-dom     # client-side routing
@tanstack/react-query # server state management, polling
```

No CSS framework specified — keep it minimal or use whatever the user prefers. The UI should be functional, not fancy.

Configure Vite proxy for development (`frontend/vite.config.ts`):
```typescript
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
```

### 5.2 — API client: `frontend/src/api/`

Thin fetch wrapper typed against the backend schemas.

**`api/client.ts`:**
- Base fetch wrapper that handles JSON, checks response status, throws on error
- All requests include `credentials: "include"` for session cookies

**`api/auth.ts`:**
- `getAuthStatus() -> AuthStatus`
- `getUserInfo() -> UserInfo`
- `logout() -> void`
- Login is a redirect, not an API call

**`api/accounts.ts`:**
- `listAccounts() -> AccountResponse[]`
- `getAccount(id) -> AccountResponse`
- `createAccount(data: AccountCreate) -> AccountResponse`
- `updateAccount(id, data: AccountUpdate) -> AccountResponse`

**`api/roles.ts`:**
- `listRoles() -> RoleResponse[]` (filtered by backend to user's accessible roles)
- `getRoleTemplates() -> RoleTemplate[]`
- `createRole(accountId, data: RoleCreate) -> RoleResponse`
- `updateRole(accountId, roleId, data: RoleUpdate) -> RoleResponse`
- `deleteRole(accountId, roleId) -> void`
- `assumeRole(roleId) -> AssumeRoleResponse`
- `getConsoleUrl(roleId) -> ConsoleUrlResponse`

**`api/jobs.ts`:**
- `listJobs(filters?) -> JobResponse[]`
- `getJob(id) -> JobResponse`

### 5.3 — Auth context: `frontend/src/context/AuthContext.tsx`

React context that:
1. On mount, calls `getAuthStatus()`
2. Provides `{ user, isAuthenticated, isAdmin, isLoading, logout }` to the app
3. Redirects to `/api/auth/login` when user clicks "Sign in"
4. After logout, clears state and redirects to landing page

### 5.4 — Routes and pages

**Route structure:**
```
/                    → Landing page (unauthenticated) or Dashboard (authenticated)
/accounts            → Account list (admin: all accounts, user: accounts with accessible roles)
/accounts/new        → Account creation form (admin only)
/accounts/:id        → Account detail + roles on this account
/accounts/:id/roles/new → Role creation form (admin only)
/jobs                → Job list with status (admin: all, user: own jobs)
```

**Pages:**

**Landing / Dashboard (`pages/Dashboard.tsx`):**
- If not authenticated: app name, description, "Sign in with SSO" button
- If authenticated: list of accounts/roles the user can access, grouped by account
- Each role shows: role name, description, account name, two action buttons

**Account List (`pages/AccountList.tsx`):**
- Table: account name, AWS account ID, OU, status, created date
- Admin sees "New Account" button
- Click row → account detail

**Account Detail (`pages/AccountDetail.tsx`):**
- Account info header (name, ID, status, OU, created by)
- Roles table for this account: role name, template, allowed groups, allowed users
- Admin sees "Add Role" button, edit/delete actions per role
- If account is pending/provisioning, show job status with auto-refresh

**Account Creation (`pages/AccountCreate.tsx`):**
- Form: account name, account email, OU (dropdown or text), SSO user email
- Submit → POST /api/accounts → redirect to account detail (shows provisioning job)

**Role Creation (`pages/RoleCreate.tsx`):**
- Account selector (pre-filled if navigated from account detail)
- Toggle: "From template" / "Custom"
- Template mode: dropdown of templates, auto-fills policy section
- Custom mode: managed policy ARN list (add/remove), inline policy JSON editor
- Allowed groups: multi-input (add/remove tags)
- Allowed users: multi-input (add/remove tags)
- Session durations: API (default 900s), Console (default 3600s)
- Description text field

**Job List (`pages/JobList.tsx`):**
- Table: job type, account, status, started by, started at, completed at
- Filter by status, job type
- Auto-refresh for in_progress jobs (react-query polling every 5s)

### 5.5 — Role assumption UI components

**`components/AssumeRoleButton.tsx`:**
- "Get Credentials" button
- On click: calls `assumeRole(roleId)`
- Shows modal/panel with credentials in env var format:
  ```
  export AWS_ACCESS_KEY_ID=AKIA...
  export AWS_SECRET_ACCESS_KEY=...
  export AWS_SESSION_TOKEN=...
  ```
- "Copy to clipboard" button
- Shows expiration countdown

**`components/ConsoleButton.tsx`:**
- "Open Console" button
- On click: calls `getConsoleUrl(roleId)`
- Opens returned URL in new tab (`window.open`)

### 5.6 — Build integration

Update `Dockerfile` to include frontend build:
```dockerfile
FROM node:20-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

FROM python:3.11-slim AS base
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ backend/
COPY alembic/ alembic/
COPY alembic.ini .
COPY --from=frontend /app/frontend/dist frontend/dist
EXPOSE 8000
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

The backend already serves `frontend/dist` as static files when the directory exists (see `backend/main.py`).

### 5.7 — Tests

Frontend testing is out of scope for this phase plan. Focus on manual testing against a running backend with mocked or real AWS APIs.

Basic smoke checks:
- Login flow redirects to OIDC provider and back
- Dashboard shows accessible roles after login
- Account creation form submits and shows provisioning job
- Role creation form works with template and custom modes
- Assume role shows credentials
- Console button opens AWS console in new tab
- Job list auto-refreshes

## New files

```
frontend/                    # entire new directory
  package.json
  tsconfig.json
  vite.config.ts
  index.html
  src/
    main.tsx
    App.tsx
    api/
      client.ts
      auth.ts
      accounts.ts
      roles.ts
      jobs.ts
    context/
      AuthContext.tsx
    pages/
      Dashboard.tsx
      AccountList.tsx
      AccountDetail.tsx
      AccountCreate.tsx
      RoleCreate.tsx
      JobList.tsx
    components/
      AssumeRoleButton.tsx
      ConsoleButton.tsx
      ProtectedRoute.tsx
      AdminRoute.tsx
```

## Definition of done

- Users can sign in via OIDC, see their accessible roles, and assume them
- Admins can create accounts and roles through the UI
- Job status is visible and auto-refreshes
- Credentials are displayed in copyable env var format
- Console URLs open in new tabs
- Multi-stage Docker build produces a single container serving both API and UI
