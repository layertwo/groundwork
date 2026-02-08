```
   ╔═══════════╗   ___                     _                 _
   ║           ║  / __|_ _ ___ _  _ _ _  __| |_ __ _____ _ _| |__
   ╠═══════════╣ | (_ | '_/ _ \ || | ' \/ _` \ V  V / _ \ '_| / /
   ╠═══════════╣  \___|_| \___/\_,_|_||_\__,_|\_/\_/\___/_| |_\_\
   ╚═══════════╝
```

Self-service AWS account factory with federated access via OIDC.

Groundwork lets your team provision AWS accounts on demand and manage who can access them — without tickets, manual IAM work, or shared credentials. Users authenticate with your existing identity provider, pick a role, and get temporary AWS credentials or a console session in seconds.

## Features

- **One-click account provisioning** — Create new AWS accounts through AWS Organizations. A CloudFormation StackSet automatically bootstraps each account with an OIDC identity provider and management role.
- **Role templates and custom roles** — Spin up IAM roles from predefined templates (Admin, ReadOnly, PowerUser) or define custom roles with specific managed policies and inline policies. Assign access by group or individual user.
- **Federated access** — Users assume roles with their identity provider credentials. No long-lived AWS keys. Temporary API credentials and console sessions are generated on demand with configurable durations.
- **Dual-layer access control** — Access is enforced at both the application layer (group/user checks) and the IAM trust policy layer (aud + groups/sub conditions). Defense in depth, not just a UI gate.
- **Full audit trail** — Every account creation, role change, and role assumption is logged with user, IP, and timestamp.

## How it works

1. Admin creates an AWS account in Groundwork — Organizations provisions it, a CloudFormation StackSet automatically bootstraps OIDC + management role
2. Admin creates roles on the account (from templates or custom) and assigns groups/users
3. Users sign in via SSO, see the roles they can access, and click to get temporary AWS credentials or open the console

## Prerequisites

- **AWS Organization** — Groundwork creates accounts via AWS Organizations, so you need an existing organization.
- **Dedicated Groundwork AWS account** — A member account registered as a **delegated administrator for CloudFormation StackSets**, with an **Organizations delegation policy** granting account provisioning permissions. See [delegation policy setup](docs/deployment/delegation-policy.md).
- **OIDC identity provider** — Any OpenID Connect provider that supports the Authorization Code flow (Okta, Entra ID, Google Workspace, Keycloak, etc.).
- **PostgreSQL 16+** — Used for storing accounts, roles, sessions, and audit logs.
- **Python 3.14+** — Required for the backend.

## Setup

### 1. AWS permissions

Groundwork runs in a **dedicated Groundwork AWS account** that has two delegated capabilities:

1. **CloudFormation StackSets delegated administrator** — for bootstrapping member accounts
2. **Organizations delegation policy** — for creating and managing accounts

#### Groundwork account setup

Create a dedicated AWS account for Groundwork and register it as a delegated administrator for CloudFormation StackSets:

```bash
aws organizations register-delegated-administrator \
  --account-id <groundwork-account-id> \
  --service-principal member.org.stacksets.cloudformation.amazonaws.com
```

Then create an Organizations delegation policy granting the Groundwork account provisioning permissions. See [delegation policy setup](docs/deployment/delegation-policy.md) for the full policy document and IAM configuration.

#### How it works

| Step | Account | What happens |
|---|---|---|
| Account creation | Groundwork (via delegation policy) | Organizations API creates the account and moves it to a target OU |
| Account bootstrap | Groundwork (delegated admin) | A service-managed CloudFormation StackSet auto-deploys an OIDC provider and management role to all member accounts |
| Role management | Groundwork → member account | Groundwork assumes `GroundworkAdmin-DO-NOT-DELETE` in the member account to create/update/delete user-facing IAM roles |

**What Groundwork deploys via StackSets:** A service-managed StackSet with auto-deploy creates two resources in every member account:

1. An **OIDC identity provider** — registers your IdP so IAM trust policies can validate tokens
2. A **`GroundworkAdmin-DO-NOT-DELETE` role** — with `AdministratorAccess`, trusted by the Groundwork account. Groundwork uses this role for all subsequent IAM operations. You do not need to create this manually.

### 2. Identity provider (OIDC)

Register Groundwork as a client application in your identity provider:

- **Redirect URI:** `https://<your-groundwork-url>/api/auth/callback`
- **Grant type:** Authorization Code
- **Scopes:** `openid profile email groups`

Groundwork expects the following claims in the ID token:

| Claim | Required | Purpose |
|---|---|---|
| `sub` | Yes | Unique user identifier, used for user-level role access control |
| `email` | Yes | User email, stored for display and audit |
| `groups` | Yes | Group memberships, used for group-level role access control |
| `name` or `preferred_username` | No | Display name |

The `groups` claim is critical — Groundwork uses it to enforce role access at both the application layer and in IAM trust policy conditions. Make sure your IdP includes group memberships in the ID token.

The OIDC issuer URL **must use HTTPS**. When creating the bootstrap StackSet, Groundwork fetches the TLS certificate from the issuer to compute a thumbprint for the AWS IAM OIDC provider registration.

After registering, note your **issuer URL**, **client ID**, and **client secret** — you'll need them for configuration.

### 3. Database

**Production:** Provision a PostgreSQL 16+ instance and create a database. Note the connection string in the format `postgresql+asyncpg://<user>:<password>@<host>:5432/<dbname>`.

**Local development:** Use the included Docker Compose file:

```bash
docker compose up -d db
```

This starts PostgreSQL 16 on port 5432 with user `groundwork`, password `groundwork`, database `groundwork`.

### 4. Configuration

Create a `.env` file in the project root:

```bash
# Database
GW_DATABASE_URL=postgresql+asyncpg://groundwork:groundwork@localhost:5432/groundwork

# OIDC — from step 2
GW_OIDC_ISSUER_URL=https://your-idp.example.com
GW_OIDC_CLIENT_ID=your-client-id
GW_OIDC_CLIENT_SECRET=your-client-secret
GW_OIDC_REDIRECT_URI=https://your-groundwork-url/api/auth/callback

# AWS — from step 1
GW_AWS_REGION=us-east-1
GW_AWS_GROUNDWORK_ACCOUNT_ID=444455556666
GW_AWS_ORG_ROOT_ID=r-xxxx

# App
GW_APP_URL=https://your-groundwork-url
GW_SESSION_SECRET=generate-a-random-string-at-least-32-characters
```

All settings use the `GW_` prefix. Optional settings with their defaults:

| Setting | Default | Description |
|---|---|---|
| `GW_DB_POOL_SIZE` | `20` | Connection pool size |
| `GW_DB_MAX_OVERFLOW` | `10` | Max overflow connections |
| `GW_DB_POOL_RECYCLE` | `1800` | Connection recycle interval (seconds) |
| `GW_ADMIN_ROLE_NAME` | `GroundworkAdmin-DO-NOT-DELETE` | Name of the management role created in member accounts |
| `GW_APP_NAME` | `Groundwork` | Application display name |
| `GW_DEBUG` | `false` | Enable debug mode (CORS for localhost:5173) |

### 5. Run migrations

```bash
python3.14 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=. alembic upgrade head
```

### 6. Start the server

```bash
PYTHONPATH=. uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

The API is now available at `http://localhost:8000`. The frontend (if built) is served from `frontend/dist/`.

## Development

Quick setup for local evaluation and development:

```bash
git clone https://github.com/layertwo/groundwork.git && cd groundwork
python3.14 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
docker compose up -d db
cp .env.example .env  # then edit with your OIDC + AWS values
PYTHONPATH=. alembic upgrade head
GW_DEBUG=true PYTHONPATH=. uvicorn backend.main:app --reload --reload-dir backend
```

`GW_DEBUG=true` enables CORS for the Vite dev server at `localhost:5173`. Do not use this in production.

Run the test suite:

```bash
PYTHONPATH=. pytest
```
