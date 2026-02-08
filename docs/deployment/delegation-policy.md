# AWS Organizations Delegation Policy

Groundwork runs in a dedicated AWS account (the "Groundwork account") rather than the
management account. To allow Groundwork to create and manage member accounts it needs
Organizations API access, which is granted through a **resource-based delegation policy**
attached to the organization. This policy gives the Groundwork account a scoped set of
Organizations permissions without requiring management account credentials at runtime.

## Prerequisites

1. The Groundwork account must already be a member of the AWS Organization.
2. The Groundwork account must be registered as a **delegated administrator for
   CloudFormation StackSets**. This is a separate registration step (not covered by the
   delegation policy) and is required for Groundwork to manage bootstrap StackSets with
   `CallAs="DELEGATED_ADMIN"`.

   ```bash
   # Run from the management account
   aws organizations register-delegated-administrator \
     --account-id GROUNDWORK_ACCOUNT_ID \
     --service-principal member.org.stacksets.cloudformation.amazonaws.com
   ```

## Delegation policy document

Save the following as `delegation-policy.json`, replacing the placeholder values:

| Placeholder              | Description                                       | Example              |
|--------------------------|---------------------------------------------------|----------------------|
| `GROUNDWORK_ACCOUNT_ID`  | 12-digit AWS account ID where Groundwork runs     | `123456789012`       |
| `MANAGEMENT_ACCOUNT_ID`  | 12-digit AWS account ID of the management account | `111111111111`       |
| `ORGANIZATION_ID`        | Organization ID (starts with `o-`)                | `o-abc123def4`       |

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "GroundworkOrganizationsAccess",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::GROUNDWORK_ACCOUNT_ID:root"
      },
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
      "Resource": [
        "arn:aws:organizations::MANAGEMENT_ACCOUNT_ID:account/ORGANIZATION_ID/*",
        "arn:aws:organizations::MANAGEMENT_ACCOUNT_ID:ou/ORGANIZATION_ID/*",
        "arn:aws:organizations::MANAGEMENT_ACCOUNT_ID:root/ORGANIZATION_ID/*",
        "arn:aws:organizations::MANAGEMENT_ACCOUNT_ID:organization/ORGANIZATION_ID"
      ]
    }
  ]
}
```

## Applying the policy

The delegation policy must be applied **from the management account**:

```bash
aws organizations put-resource-policy \
  --content file://delegation-policy.json
```

To verify the policy was applied:

```bash
aws organizations describe-resource-policy
```

## What this enables

The delegation policy grants the following Organizations operations to the Groundwork
account. Each action maps to a specific Groundwork capability:

| Action                                           | Used for                                                        |
|--------------------------------------------------|-----------------------------------------------------------------|
| `organizations:CreateAccount`                    | Provisioning new member accounts                                |
| `organizations:DescribeCreateAccountStatus`      | Polling account creation progress                               |
| `organizations:ListCreateAccountStatus`          | Listing in-flight account creation requests                     |
| `organizations:MoveAccount`                      | Moving newly created accounts into target OUs                   |
| `organizations:ListRoots`                        | Discovering the organization root (source parent for moves)     |
| `organizations:ListAccounts`                     | Enumerating all accounts in the organization                    |
| `organizations:ListAccountsForParent`            | Listing accounts within a specific OU                           |
| `organizations:ListOrganizationalUnitsForParent` | Navigating the OU tree                                          |
| `organizations:ListChildren`                     | Listing child OUs and accounts under a parent                   |
| `organizations:DescribeAccount`                  | Fetching account details (name, email, status)                  |
| `organizations:DescribeOrganization`             | Reading organization metadata                                   |
| `organizations:DescribeOrganizationalUnit`       | Fetching OU details (name, ID)                                  |

## Groundwork account IAM policy

The delegation policy grants the Groundwork account *permission to call* these
Organizations APIs. However, the IAM principal that Groundwork runs as (an IAM role,
instance profile, or ECS task role) also needs an **IAM identity policy** allowing the
same actions. Both layers must permit an action for it to succeed.

Attach the following IAM policy to the Groundwork execution role:

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
    },
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
      "Sid": "AssumeAdminRoleInMemberAccounts",
      "Effect": "Allow",
      "Action": "sts:AssumeRole",
      "Resource": "arn:aws:iam::*:role/GroundworkAdmin-DO-NOT-DELETE"
    }
  ]
}
```

The three statements cover:

1. **OrganizationsAccess** -- the same Organizations actions listed in the delegation
   policy. The delegation policy (resource-based) authorizes the *account*; this
   identity policy authorizes the *principal within* the account.
2. **CloudFormationStackSets** -- permissions to create and monitor the bootstrap
   StackSet that deploys OIDC providers and admin roles into member accounts. These
   calls use `CallAs="DELEGATED_ADMIN"` and require the delegated administrator
   registration described in the prerequisites.
3. **AssumeAdminRoleInMemberAccounts** -- allows the Groundwork execution role to
   assume the `GroundworkAdmin-DO-NOT-DELETE` role that the bootstrap StackSet creates
   in each member account. This is how Groundwork manages IAM roles in member accounts.
