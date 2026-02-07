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

- **One-click account provisioning** — Create new AWS accounts through AWS Organizations. Groundwork automatically bootstraps each account with an OIDC identity provider and management role.
- **Role templates and custom roles** — Spin up IAM roles from predefined templates (Admin, ReadOnly, PowerUser) or define custom roles with specific managed policies and inline policies. Assign access by group or individual user.
- **Federated access** — Users assume roles with their identity provider credentials. No long-lived AWS keys. Temporary API credentials and console sessions are generated on demand with configurable durations.
- **Dual-layer access control** — Access is enforced at both the application layer (group/user checks) and the IAM trust policy layer (aud + groups/sub conditions). Defense in depth, not just a UI gate.
- **Full audit trail** — Every account creation, role change, and role assumption is logged with user, IP, and timestamp.

## How it works

1. Admin creates an AWS account in Groundwork — Organizations provisions it, Groundwork bootstraps OIDC + management role
2. Admin creates roles on the account (from templates or custom) and assigns groups/users
3. Users sign in via SSO, see the roles they can access, and click to get temporary AWS credentials or open the console

## Prerequisites

- **AWS Organization** — Groundwork creates accounts via AWS Organizations, so you need an existing organization with the management account.
- **OIDC identity provider** — Any OpenID Connect provider that supports the Authorization Code flow (Okta, Entra ID, Google Workspace, Keycloak, etc.).
- **PostgreSQL 16+** — Used for storing accounts, roles, sessions, and audit logs.
- **Python 3.14+** — Required for the backend.

## Setup

### 1. AWS permissions

Groundwork runs as an IAM principal in your **management account**. It needs permissions to create accounts via Organizations and to assume roles into member accounts for bootstrapping and ongoing management.

Create an IAM role (or user, for local development) with the following policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ManageAccounts",
      "Effect": "Allow",
      "Action": [
        "organizations:CreateAccount",
        "organizations:DescribeCreateAccountStatus",
        "organizations:ListRoots",
        "organizations:MoveAccount"
      ],
      "Resource": "*"
    },
    {
      "Sid": "AssumeIntoMemberAccounts",
      "Effect": "Allow",
      "Action": "sts:AssumeRole",
      "Resource": [
        "arn:aws:iam::*:role/OrganizationAccountAccessRole",
        "arn:aws:iam::*:role/GroundworkAdmin-DO-NOT-DELETE"
      ]
    }
  ]
}
```

**How Groundwork uses these permissions:**

| Permission | Purpose |
|---|---|
| `organizations:CreateAccount` | Provision new AWS accounts |
| `organizations:DescribeCreateAccountStatus` | Poll account creation progress |
| `organizations:ListRoots` / `MoveAccount` | Move new accounts into a target OU |
| `sts:AssumeRole` → `OrganizationAccountAccessRole` | Initial bootstrap of new accounts (create OIDC provider + management role) |
| `sts:AssumeRole` → `GroundworkAdmin-DO-NOT-DELETE` | Ongoing IAM role management in member accounts |

**Trust policy for the Groundwork role** depends on how you run it:

- **EC2 instance profile** — set the principal to the EC2 service (`"Service": "ec2.amazonaws.com"`)
- **ECS task role** — set the principal to the ECS task service (`"Service": "ecs-tasks.amazonaws.com"`)
- **IAM user (local dev)** — set the principal to the user ARN (`"AWS": "arn:aws:iam::<mgmt-account-id>:user/<username>"`)

**What Groundwork creates in member accounts:** During account bootstrap, Groundwork assumes `OrganizationAccountAccessRole` (created automatically by AWS Organizations) and sets up two resources:

1. An **OIDC identity provider** — registers your IdP so IAM trust policies can validate tokens
2. A **`GroundworkAdmin-DO-NOT-DELETE` role** — with `AdministratorAccess`, trusted by the management account. Groundwork uses this role for all subsequent IAM operations (creating/updating/deleting user-facing roles). You do not need to create this manually.

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

The OIDC issuer URL **must use HTTPS**. During account bootstrap, Groundwork fetches the TLS certificate from the issuer to compute a thumbprint for the AWS IAM OIDC provider registration.

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
GW_AWS_MANAGEMENT_ACCOUNT_ID=111122223333

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
git clone https://github.com/your-org/groundwork.git && cd groundwork
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
