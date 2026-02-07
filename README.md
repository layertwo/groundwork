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

- **One-click account provisioning** — Create new AWS accounts through Control Tower. Groundwork automatically bootstraps each account with an OIDC identity provider and management role.
- **Role templates and custom roles** — Spin up IAM roles from predefined templates (Admin, ReadOnly, PowerUser) or define custom roles with specific managed policies and inline policies. Assign access by group or individual user.
- **Federated access** — Users assume roles with their identity provider credentials. No long-lived AWS keys. Temporary API credentials and console sessions are generated on demand with configurable durations.
- **Dual-layer access control** — Access is enforced at both the application layer (group/user checks) and the IAM trust policy layer (aud + groups/sub conditions). Defense in depth, not just a UI gate.
- **Full audit trail** — Every account creation, role change, and role assumption is logged with user, IP, and timestamp.

## How it works

1. Admin creates an AWS account in Groundwork — Control Tower provisions it, Groundwork bootstraps OIDC + management role
2. Admin creates roles on the account (from templates or custom) and assigns groups/users
3. Users sign in via SSO, see the roles they can access, and click to get temporary AWS credentials or open the console
