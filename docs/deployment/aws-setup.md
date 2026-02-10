# AWS Setup

Groundwork runs in a **dedicated AWS account** (the "Groundwork account") rather than the
management account. It needs two things to manage your organization:

1. **A cross-account role in the management account** (`GroundworkManagementRole`) that the
   Groundwork account can assume — this provides Organizations API access.
2. **CloudFormation StackSets delegated administrator** registration — this lets the
   Groundwork account deploy bootstrap resources to member accounts.

## Prerequisites

1. The Groundwork account must already be a member of the AWS Organization.
2. You need administrative access to the **management account** to create the IAM role and
   register the delegated administrator.

## Placeholders

| Placeholder              | Description                                       | Example              |
|--------------------------|---------------------------------------------------|----------------------|
| `GROUNDWORK_ACCOUNT_ID`  | 12-digit AWS account ID where Groundwork runs     | `444455556666`       |
| `MANAGEMENT_ACCOUNT_ID`  | 12-digit AWS account ID of the management account | `111122223333`       |

## Step 1: Register as delegated administrator for CloudFormation StackSets

Run from the **management account**:

```bash
aws organizations register-delegated-administrator \
  --account-id GROUNDWORK_ACCOUNT_ID \
  --service-principal member.org.stacksets.cloudformation.amazonaws.com
```

This allows the Groundwork account to create and manage service-managed StackSets with
`CallAs="DELEGATED_ADMIN"`.

## Step 2: Create the management account role (`GroundworkManagementRole`)

Create an IAM role in the **management account** that the Groundwork account can assume.
This role provides Organizations API access without requiring management account credentials
at runtime.

### Trust policy

Allows the Groundwork account to assume this role:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::GROUNDWORK_ACCOUNT_ID:root"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

### Permissions policy

Scoped Organizations access:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "OrganizationsAccess",
      "Effect": "Allow",
      "Action": [
        "organizations:CreateAccount",
        "organizations:DescribeCreateAccountStatus",
        "organizations:ListCreateAccountStatus",
        "organizations:MoveAccount",
        "organizations:ListRoots",
        "organizations:ListAccounts",
        "organizations:ListAccountsForParent",
        "organizations:ListOrganizationalUnitsForParent",
        "organizations:ListChildren",
        "organizations:DescribeAccount",
        "organizations:DescribeOrganization",
        "organizations:DescribeOrganizationalUnit"
      ],
      "Resource": "*"
    }
  ]
}
```

## Step 3: Create the Groundwork account role

The Groundwork application needs an IAM role in the **Groundwork account** with permissions
for CloudFormation StackSets, assuming the management account role, and assuming the admin
role in member accounts.

The trust policy for this role depends on how you deploy Groundwork (ECS task role, EC2
instance profile, Kubernetes IRSA, etc.).

### Permissions policy

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "CloudFormationStackSets",
      "Effect": "Allow",
      "Action": [
        "cloudformation:CreateStackSet",
        "cloudformation:DescribeStackSet",
        "cloudformation:CreateStackInstances",
        "cloudformation:DescribeStackInstance",
        "cloudformation:ListStackInstances"
      ],
      "Resource": "*"
    },
    {
      "Sid": "AssumeManagementRole",
      "Effect": "Allow",
      "Action": "sts:AssumeRole",
      "Resource": "arn:aws:iam::MANAGEMENT_ACCOUNT_ID:role/GroundworkManagementRole"
    },
    {
      "Sid": "AssumeAdminRoleInMemberAccounts",
      "Effect": "Allow",
      "Action": "sts:AssumeRole",
      "Resource": "arn:aws:iam::*:role/GroundworkAdmin-DO-NOT-DELETE"
    },
    {
      "Sid": "AssumeUserRolesWithExternalId",
      "Effect": "Allow",
      "Action": "sts:AssumeRole",
      "Resource": "arn:aws:iam::*:role/*",
      "Condition": {
        "StringLike": {
          "sts:ExternalId": "Groundwork-*"
        }
      }
    }
  ]
}
```

The four statements cover:

1. **CloudFormationStackSets** -- permissions to create and monitor the bootstrap StackSet
   that deploys OIDC providers and admin roles into member accounts. These calls use
   `CallAs="DELEGATED_ADMIN"` and require the delegated administrator registration from
   Step 1.
2. **AssumeManagementRole** -- allows the Groundwork execution role to assume the
   `GroundworkManagementRole` in the management account for Organizations API calls
   (account creation, OU navigation, etc.).
3. **AssumeAdminRoleInMemberAccounts** -- allows the Groundwork execution role to assume
   the `GroundworkAdmin-DO-NOT-DELETE` role that the bootstrap StackSet creates in each
   member account. This is how Groundwork manages IAM roles in member accounts.
4. **AssumeUserRolesWithExternalId** -- allows the Groundwork execution role to assume
   user-created roles in member accounts for federation (console and CLI access). The
   `sts:ExternalId` condition restricts this to calls that include an External ID matching
   the `Groundwork-*` pattern. All Groundwork-managed roles are created with a deterministic
   External ID in this format (`Groundwork-{SHA-256 hash}`), so this condition scopes
   assumption to only Groundwork-managed roles without constraining role naming.

## How it works

| Operation | Account / Role | What happens |
|---|---|---|
| Account creation | Management account (via `GroundworkManagementRole`) | Groundwork assumes the management role and calls Organizations APIs to create the account and move it to a target OU |
| Account bootstrap | Groundwork account (delegated admin) | A service-managed CloudFormation StackSet auto-deploys an OIDC provider and management role to all member accounts |
| Role management | Groundwork account -> member account | Groundwork assumes `GroundworkAdmin-DO-NOT-DELETE` in the member account to create/update/delete user-facing IAM roles |
| Role assumption | Groundwork account -> member account | Groundwork assumes user-created roles via STS with an External ID (`Groundwork-*`) for console and CLI federation |

**What Groundwork deploys via StackSets:** A service-managed StackSet with auto-deploy
creates two resources in every member account:

1. An **OIDC identity provider** -- registers your IdP so IAM trust policies can validate
   tokens
2. A **`GroundworkAdmin-DO-NOT-DELETE` role** -- with `AdministratorAccess`, trusted by the
   Groundwork account. Groundwork uses this role for all subsequent IAM operations. You do
   not need to create this manually.

## Configuration

After setting up the roles, add the management role ARN to your Groundwork configuration:

```bash
GW_AWS_MANAGEMENT_ROLE_ARN=arn:aws:iam::MANAGEMENT_ACCOUNT_ID:role/GroundworkManagementRole
```

See the main [README](../../README.md) for all configuration settings.
