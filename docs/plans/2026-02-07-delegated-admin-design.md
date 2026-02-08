# Use Organizations Delegation Policy Instead of Management Account Role

**Goal:** Eliminate management account credentials from the Groundwork runtime. Replace the dual-session architecture (`get_session()` for management account, `get_groundwork_session()` for Groundwork account) with a single session rooted in the Groundwork account. Organizations API calls work via a resource-based delegation policy; StackSet calls continue using `CallAs="DELEGATED_ADMIN"`.

**Tech Stack:** No new dependencies. Changes are to `backend/services/aws.py`, `backend/config.py`, tests, and documentation.

---

## Summary of Changes

| Area | Before | After |
|------|--------|-------|
| Organizations calls (`create_account`, `move_account`, etc.) | `get_session()` (management account credentials) | `get_session()` (Groundwork account credentials + delegation policy) |
| StackSet calls | `get_groundwork_session()` (assume role into Groundwork account) | `get_session()` (already in Groundwork account) |
| Admin role chaining | `get_groundwork_session()` then assume into member account | `get_session()` then assume into member account |
| `get_groundwork_session()` | Exists, assumes role | Deleted |
| `aws_groundwork_role_name` config | Exists | Deleted |
| `aws_management_account_id` config | Exists | Deleted |
| `aws_groundwork_account_id` config | Exists | Kept (needed for bootstrap template) |

---

## Prerequisites (One-Time Manual Setup)

Before the app can use delegation, the management account admin must create a resource-based delegation policy in AWS Organizations granting the Groundwork account the required permissions.

### Example Organizations Delegation Policy

Replace `GROUNDWORK_ACCOUNT_ID` with the 12-digit Groundwork account ID and `MANAGEMENT_ACCOUNT_ID` and `ORGANIZATION_ID` with the corresponding values from your organization.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "GroundworkAccountProvisioning",
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

This policy is created in the management account using the Organizations `PutResourcePolicy` API or via the AWS console under Organizations > Settings > Delegation policies.

The Groundwork account must also be registered as a delegated administrator for CloudFormation StackSets (already done).

---

## Code Changes

### Task 1: Remove `get_groundwork_session()` and Update Callers

**Files:**
- `backend/services/aws.py`

Delete `get_groundwork_session()`. Replace all calls to it with `get_session()`:

- `get_stack_instance_status()` — change `await get_groundwork_session()` to `get_session()`
- `deploy_to_account()` — same
- `ensure_bootstrap_stackset()` — same
- `assume_groundwork_admin()` — same

Note: `get_session()` is synchronous (returns cached session), so the `await` is dropped.

### Task 2: Remove Unused Config Settings

**Files:**
- `backend/config.py`

Remove:
- `aws_groundwork_role_name`
- `aws_management_account_id`

Keep:
- `aws_groundwork_account_id` (used in `_build_bootstrap_template()`)

### Task 3: Update Tests

**Files:**
- `tests/unit/services/test_aws.py`
- Any test files that mock `get_groundwork_session`

- Remove `TestGetGroundworkSession` test class
- Replace all patches of `get_groundwork_session` with botocore Stubber on the relevant service clients (cloudformation, sts)
- Remove patches of `aws_groundwork_role_name` and `aws_management_account_id`

### Task 4: Add Delegation Policy Documentation

**Files:**
- `docs/deployment/delegation-policy.md` (or similar)

Document the example delegation policy from the Prerequisites section above, with instructions for creating it via the console or CLI.

### Task 5: Update Existing Docs

**Files:**
- `CLAUDE.md`
- `docs/plans/2026-02-06-groundwork-service-design.md`

Update references to the dual-session architecture. The AWS service layer description should reflect that all operations use a single session from the Groundwork account.
