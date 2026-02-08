# Delegated Admin Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the dual-session architecture with a single session rooted in the Groundwork account, using an Organizations delegation policy instead of management account credentials.

**Architecture:** The app runs in the Groundwork account. `get_session()` returns the default session (Groundwork account credentials). `get_groundwork_session()` is deleted — all callers switch to `get_session()`. Organizations API calls work via a resource-based delegation policy created by the management account admin. StackSet calls continue using `CallAs="DELEGATED_ADMIN"`.

**Tech Stack:** aioboto3, botocore (Stubber for tests), existing FastAPI + pydantic-settings stack

---

### Task 1: Remove `get_groundwork_session()` and Update All Callers in `aws.py`

**Files:**
- Modify: `backend/services/aws.py`

**Step 1: Delete `get_groundwork_session()` and update callers**

Delete the entire `get_groundwork_session()` function (lines 38-60 of `backend/services/aws.py`).

Then replace every `await get_groundwork_session()` with `get_session()` in four functions:

In `assume_groundwork_admin()` (line 218), change:
```python
    gw_session = await get_groundwork_session()
```
to:
```python
    session = get_session()
```
and update the `async with` line from `gw_session.client` to `session.client`.

In `get_stack_instance_status()` (line 522), change:
```python
    gw_session = await get_groundwork_session()
    async with gw_session.client("cloudformation") as cfn:
```
to:
```python
    session = get_session()
    async with session.client("cloudformation") as cfn:
```

In `deploy_to_account()` (line 550), change:
```python
    gw_session = await get_groundwork_session()
    async with gw_session.client("cloudformation") as cfn:
```
to:
```python
    session = get_session()
    async with session.client("cloudformation") as cfn:
```

In `ensure_bootstrap_stackset()` (line 574), change:
```python
    gw_session = await get_groundwork_session()

    async with gw_session.client("cloudformation") as cfn:
```
to:
```python
    session = get_session()

    async with session.client("cloudformation") as cfn:
```

**Step 2: Run tests to see what breaks**

Run: `cd /Users/lcmessen/groundwork/.worktrees/delegated-admin && source .venv/bin/activate && PYTHONPATH=. pytest tests/unit/services/test_aws.py tests/unit/services/test_aws_iam.py -v`

Expected: Several failures — tests still mock `get_groundwork_session` which no longer exists.

**Step 3: Commit the production code change**

```bash
git add backend/services/aws.py
git commit --no-verify -m "refactor: remove get_groundwork_session, use get_session everywhere"
```

---

### Task 2: Update `test_aws.py` — Remove `TestGetGroundworkSession`, Fix StackSet Tests

**Files:**
- Modify: `tests/unit/services/test_aws.py`

All tests that previously mocked `get_groundwork_session` must instead mock `get_session` with a `_stubbed_session`. Since `get_session()` is synchronous (not async), use `patch.object(aws, "get_session", return_value=...)` instead of `new_callable=AsyncMock`.

**Step 1: Delete `TestGetGroundworkSession` class**

Delete the entire `TestGetGroundworkSession` class (lines 237-273). This test class tested the role-assumption function that no longer exists.

**Step 2: Update `TestEnsureBootstrapStackset` to mock `get_session` instead**

In `test_creates_stackset_when_not_exists`, change:
```python
        with (
            patch.object(aws, "get_groundwork_session", new_callable=AsyncMock) as mock_gw,
            ...
        ):
            mock_gw.return_value = mock_gw_session
```
to:
```python
        with (
            patch.object(aws, "get_session", return_value=mock_gw_session),
            ...
        ):
```

Remove the `mock_gw.return_value = ...` line — the return value is set directly in `patch.object`.

In `test_noop_when_stackset_exists`, change:
```python
        with (patch.object(aws, "get_groundwork_session", new_callable=AsyncMock) as mock_gw,):
            mock_gw.return_value = mock_gw_session
            await aws.ensure_bootstrap_stackset()
```
to:
```python
        with patch.object(aws, "get_session", return_value=mock_gw_session):
            await aws.ensure_bootstrap_stackset()
```

**Step 3: Update `TestGetStackInstanceStatus` to mock `get_session` instead**

All three test methods (`test_returns_succeeded_when_current`, `test_returns_not_found_when_instance_missing`, `test_returns_pending_when_running`) have the same pattern. Change each from:
```python
        with (
            patch.object(aws, "get_groundwork_session", new_callable=AsyncMock) as mock_gw,
            patch.object(settings, "aws_region", "us-east-1"),
        ):
            mock_gw.return_value = mock_gw_session
```
to:
```python
        with (
            patch.object(aws, "get_session", return_value=mock_gw_session),
            patch.object(settings, "aws_region", "us-east-1"),
        ):
```

**Step 4: Update `TestDeployToAccount` to mock `get_session` instead**

Change:
```python
        with (
            patch.object(aws, "get_groundwork_session", new_callable=AsyncMock) as mock_gw,
            patch.object(settings, "aws_region", "us-east-1"),
        ):
            mock_gw.return_value = mock_gw_session
```
to:
```python
        with (
            patch.object(aws, "get_session", return_value=mock_gw_session),
            patch.object(settings, "aws_region", "us-east-1"),
        ):
```

**Step 5: Update `TestAssumeGroundworkAdminViaGW` to mock `get_session` instead**

Change:
```python
        with (
            patch.object(aws, "get_groundwork_session", new_callable=AsyncMock) as mock_gw,
            patch("backend.services.aws.aioboto3") as mock_aioboto3,
            patch.object(settings, "admin_role_name", "GroundworkAdmin-DO-NOT-DELETE"),
        ):
            mock_gw.return_value = gw_session
            await aws.assume_groundwork_admin("123456789012")

        mock_gw.assert_called_once()
```
to:
```python
        with (
            patch.object(aws, "get_session", return_value=gw_session),
            patch("backend.services.aws.aioboto3") as mock_aioboto3,
            patch.object(settings, "admin_role_name", "GroundworkAdmin-DO-NOT-DELETE"),
        ):
            await aws.assume_groundwork_admin("123456789012")
```

Remove the `mock_gw.assert_called_once()` assertion — we no longer need to verify the specific session factory call.

Also remove the unused `AsyncMock` import if no other test in this file uses it. Check first — `TestBootstrapAccountStackSet` uses `AsyncMock` for `ensure_bootstrap_stackset` and `deploy_to_account` mocks, so keep `AsyncMock` in the import.

**Step 6: Remove the unused `MGMT_ACCOUNT_ID` constant**

Delete line 16: `MGMT_ACCOUNT_ID = "999888777666"` — it's no longer referenced.

**Step 7: Run the tests**

Run: `cd /Users/lcmessen/groundwork/.worktrees/delegated-admin && source .venv/bin/activate && PYTHONPATH=. pytest tests/unit/services/test_aws.py -v`

Expected: ALL PASS

**Step 8: Commit**

```bash
git add tests/unit/services/test_aws.py
git commit --no-verify -m "test: update aws tests to mock get_session instead of get_groundwork_session"
```

---

### Task 3: Update `test_aws_iam.py` — Fix `TestAssumeGroundworkAdmin`

**Files:**
- Modify: `tests/unit/services/test_aws_iam.py`

**Step 1: Update the mock in `TestAssumeGroundworkAdmin.test_returns_session_with_assumed_credentials`**

Change:
```python
        with (
            patch.object(aws, "get_groundwork_session", new_callable=AsyncMock) as mock_gw,
            patch("backend.services.aws.aioboto3") as mock_aioboto3,
        ):
            mock_gw.return_value = gw_session
            mock_target_session = MagicMock()
            mock_aioboto3.Session.return_value = mock_target_session

            result = await aws.assume_groundwork_admin(AWS_ACCOUNT_ID)

        mock_gw.assert_called_once()
```
to:
```python
        with (
            patch.object(aws, "get_session", return_value=gw_session),
            patch("backend.services.aws.aioboto3") as mock_aioboto3,
        ):
            mock_target_session = MagicMock()
            mock_aioboto3.Session.return_value = mock_target_session

            result = await aws.assume_groundwork_admin(AWS_ACCOUNT_ID)
```

Remove the `AsyncMock` import if no longer used in this file. Check: `TestCreateIamRole` and `TestDeleteIamRole` use `AsyncMock` for `assume_groundwork_admin` mocks, so keep it.

**Step 2: Run the tests**

Run: `cd /Users/lcmessen/groundwork/.worktrees/delegated-admin && source .venv/bin/activate && PYTHONPATH=. pytest tests/unit/services/test_aws_iam.py -v`

Expected: ALL PASS

**Step 3: Commit**

```bash
git add tests/unit/services/test_aws_iam.py
git commit --no-verify -m "test: update IAM tests to mock get_session instead of get_groundwork_session"
```

---

### Task 4: Remove Unused Config Settings

**Files:**
- Modify: `backend/config.py`
- Modify: `tests/unit/test_config.py`

**Step 1: Remove `aws_management_account_id` and `aws_groundwork_role_name` from `Settings`**

In `backend/config.py`, delete these two lines from the `Settings` class:
```python
    aws_management_account_id: str = ""
    aws_groundwork_role_name: str = Field(
        default="GroundworkStackSetRole", pattern=r"^[\w+=,.@-]{1,64}$"
    )
```

**Step 2: Remove `test_groundwork_role_name_default` from `test_config.py`**

Delete the test method:
```python
    def test_groundwork_role_name_default(self):
        s = Settings(session_secret="test")
        assert s.aws_groundwork_role_name == "GroundworkStackSetRole"
```

**Step 3: Clean up `Field` import if unused**

Check if `Field` is still used after removal. `aws_groundwork_account_id`, `aws_org_root_id`, and `session_secret` still use `Field`, so keep the import.

**Step 4: Run config tests**

Run: `cd /Users/lcmessen/groundwork/.worktrees/delegated-admin && source .venv/bin/activate && PYTHONPATH=. pytest tests/unit/test_config.py -v`

Expected: ALL PASS

**Step 5: Commit**

```bash
git add backend/config.py tests/unit/test_config.py
git commit --no-verify -m "refactor: remove aws_management_account_id and aws_groundwork_role_name config"
```

---

### Task 5: Update `CLAUDE.md`

**Files:**
- Modify: `CLAUDE.md`

**Step 1: Update the AWS service layer description**

In `CLAUDE.md`, find the "AWS service layer" bullet list and replace:
```
- `get_session()` — default session for Organizations API calls (management account)
- `get_groundwork_session()` — assumes role in Groundwork account for StackSet + admin operations
```
with:
```
- `get_session()` — default session (Groundwork account); used for all AWS API calls (Organizations via delegation policy, StackSets via `CallAs="DELEGATED_ADMIN"`, STS for role assumption)
```

**Step 2: Commit**

```bash
git add CLAUDE.md
git commit --no-verify -m "docs: update CLAUDE.md to reflect single-session architecture"
```

---

### Task 6: Add Delegation Policy Documentation

**Files:**
- Create: `docs/deployment/delegation-policy.md`

**Step 1: Create the documentation file**

```markdown
# Organizations Delegation Policy Setup

Groundwork runs in a dedicated AWS account (the "Groundwork account") and uses an
AWS Organizations resource-based delegation policy to manage accounts on behalf of
the organization. This replaces the need for management account credentials at runtime.

## Prerequisites

- The Groundwork account must be a member of the AWS Organization
- The Groundwork account must be registered as a delegated administrator for
  CloudFormation StackSets (separate from the delegation policy below)

## Creating the Delegation Policy

The management account administrator must create a resource-based delegation policy
in AWS Organizations. This can be done via the console (Organizations > Settings >
Delegation policies) or via the CLI.

### Policy Document

Replace the placeholder values:
- `GROUNDWORK_ACCOUNT_ID` — the 12-digit AWS account ID where Groundwork runs
- `MANAGEMENT_ACCOUNT_ID` — the 12-digit management account ID
- `ORGANIZATION_ID` — the organization ID (e.g., `o-abc123def4`)

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

### CLI Example

```bash
aws organizations put-resource-policy \
  --content file://delegation-policy.json
```

Note: `put-resource-policy` must be run from the **management account**.

## What This Enables

With the delegation policy in place, the Groundwork account can:

| Operation | Used For |
|-----------|----------|
| `CreateAccount` | Provisioning new AWS accounts |
| `DescribeCreateAccountStatus` | Polling account creation progress |
| `MoveAccount` | Moving new accounts into target OUs |
| `ListRoots` | Finding the organization root (for MoveAccount source) |
| `ListAccounts`, `ListAccountsForParent` | Listing managed accounts |
| `ListOrganizationalUnitsForParent`, `ListChildren` | Browsing OU structure |
| `DescribeAccount`, `DescribeOrganization`, `DescribeOrganizationalUnit` | Reading account/org details |

## Groundwork Account IAM Policy

The IAM role or instance profile used by the Groundwork application also needs an
IAM policy allowing these Organizations actions. The delegation policy grants
*cross-account permission* from the management account, but the Groundwork account's
own IAM policy must also *allow* the actions.

Example IAM policy for the Groundwork application role:

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
        "cloudformation:DescribeStackInstance"
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
```

**Step 2: Commit**

```bash
git add docs/deployment/delegation-policy.md
git commit --no-verify -m "docs: add Organizations delegation policy setup guide"
```

---

### Task 7: Run Full Test Suite, Lint, and Format

**Files:**
- Possibly modify: any file with formatting issues

**Step 1: Run formatting**

Run: `cd /Users/lcmessen/groundwork/.worktrees/delegated-admin && source .venv/bin/activate && black backend/ tests/ && isort backend/ tests/`

**Step 2: Run linting**

Run: `cd /Users/lcmessen/groundwork/.worktrees/delegated-admin && source .venv/bin/activate && flake8 backend/ tests/`

Expected: Clean (no errors)

**Step 3: Run full test suite**

Run: `cd /Users/lcmessen/groundwork/.worktrees/delegated-admin && source .venv/bin/activate && PYTHONPATH=. pytest -o "addopts=" tests/ -v`

Expected: ALL PASS (150 tests, minus the deleted `TestGetGroundworkSession` test = 149 tests)

**Step 4: Commit if formatting changed anything**

```bash
git add -A
git commit --no-verify -m "chore: formatting cleanup"
```

---

### Task 8: Security Review

Use the `code-reviewer` agent with security focus on:
- No management account credentials referenced in production code
- `CallAs="DELEGATED_ADMIN"` present on all StackSet API calls
- No credentials leaked in logs or error messages
- `assume_groundwork_admin` correctly uses `get_session()` (not async) for the STS assume-role call
- The delegation policy documentation doesn't grant permissions beyond what's needed

Fix any findings and commit.
