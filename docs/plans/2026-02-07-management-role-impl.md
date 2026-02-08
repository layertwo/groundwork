# Management Account Role Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add `get_management_session()` that assumes a role in the management account for Organizations API calls. StackSet and admin role operations remain on the Groundwork account's default session.

**Architecture:** `get_session()` stays as the Groundwork account session. New `get_management_session()` uses STS to assume a role (configured via `aws_management_role_arn`) in the management account. Three functions switch to using it: `create_account`, `poll_account_creation`, `move_account_to_ou`.

**Tech Stack:** aioboto3, botocore (Stubber for tests), pydantic-settings

---

### Task 1: Add `aws_management_role_arn` Config Setting

**Files:**
- Modify: `backend/config.py`
- Modify: `tests/unit/test_config.py`

**Step 1: Add the setting to `backend/config.py`**

Add after `aws_org_root_id` in the AWS section:

```python
    aws_management_role_arn: str = ""
```

**Step 2: Add a test**

```python
class TestManagementRoleConfig:
    def test_management_role_arn_default(self):
        s = Settings(session_secret="test")
        assert s.aws_management_role_arn == ""
```

**Step 3: Run tests**

Run: `PYTHONPATH=. pytest tests/unit/test_config.py -v`

**Step 4: Commit**

```bash
git commit --no-verify -m "feat: add aws_management_role_arn config setting"
```

---

### Task 2: Add `get_management_session()` and Update Organizations Callers

**Files:**
- Modify: `backend/services/aws.py`

**Step 1: Add `get_management_session()` after `get_session()`**

```python
async def get_management_session() -> aioboto3.Session:
    """Assume the Organizations role in the management account.

    Used for Organizations API calls (CreateAccount, MoveAccount, etc.)
    that cannot be delegated to a member account.
    """
    session = get_session()
    async with session.client("sts") as sts:
        assumed = await sts.assume_role(
            RoleArn=settings.aws_management_role_arn,
            RoleSessionName="GroundworkOrganizations",
        )
    creds = assumed["Credentials"]
    return aioboto3.Session(
        aws_access_key_id=creds["AccessKeyId"],
        aws_secret_access_key=creds["SecretAccessKey"],
        aws_session_token=creds["SessionToken"],
        region_name=settings.aws_region,
    )
```

**Step 2: Update `create_account()` — change `session = get_session()` to `session = await get_management_session()`**

**Step 3: Update `poll_account_creation()` — same change**

**Step 4: Update `move_account_to_ou()` — same change**

**Step 5: Commit**

```bash
git commit --no-verify -m "feat: add get_management_session for Organizations API calls"
```

---

### Task 3: Add Tests for `get_management_session()`

**Files:**
- Modify: `tests/unit/services/test_aws.py`

**Step 1: Add `TestGetManagementSession` class**

```python
class TestGetManagementSession:
    async def test_assumes_role_with_configured_arn(self):
        _, sts_stubber = await create_stubbed_client("sts")
        sts_stubber.add_response(
            "assume_role",
            {
                "Credentials": {
                    "AccessKeyId": "AKIAMGMTEXAMPLE",
                    "SecretAccessKey": "secretMGMTkey1234567890example",
                    "SessionToken": "tokenMGMT1234567890",
                    "Expiration": datetime(2025, 1, 1),
                },
                "AssumedRoleUser": {
                    "AssumedRoleId": "AROAMGMT:GroundworkOrganizations",
                    "Arn": "arn:aws:sts::111122223333:assumed-role/GroundworkManagementRole/GroundworkOrganizations",
                },
            },
            expected_params={
                "RoleArn": "arn:aws:iam::111122223333:role/GroundworkManagementRole",
                "RoleSessionName": "GroundworkOrganizations",
            },
        )
        sts_stubber.activate()

        with (
            patch.object(
                aws, "get_session", return_value=_stubbed_session({"sts": sts_stubber})
            ),
            patch.object(
                settings,
                "aws_management_role_arn",
                "arn:aws:iam::111122223333:role/GroundworkManagementRole",
            ),
            patch("backend.services.aws.aioboto3") as mock_aioboto3,
        ):
            session = await aws.get_management_session()

        assert session is not None
        mock_aioboto3.Session.assert_called_once()
        call_kwargs = mock_aioboto3.Session.call_args[1]
        assert call_kwargs["aws_access_key_id"] == "AKIAMGMTEXAMPLE"
        sts_stubber.assert_no_pending_responses()
```

**Step 2: Run tests**

Run: `PYTHONPATH=. pytest tests/unit/services/test_aws.py::TestGetManagementSession -v`

**Step 3: Commit**

```bash
git commit --no-verify -m "test: add tests for get_management_session"
```

---

### Task 4: Update Organizations Tests to Mock `get_management_session`

**Files:**
- Modify: `tests/unit/services/test_aws.py`

`TestCreateAccount`, `TestPollAccountCreation`, and `TestMoveAccountToOu` currently mock `get_session`. Since these functions now call `get_management_session()` (async), update the mocks:

Change `patch.object(aws, "get_session", return_value=...)` to `patch.object(aws, "get_management_session", new_callable=AsyncMock, return_value=...)`.

**Step 1: Update `TestCreateAccount`**

```python
        with patch.object(
            aws,
            "get_management_session",
            new_callable=AsyncMock,
            return_value=_stubbed_session({"organizations": stubber}),
        ):
```

**Step 2: Update `TestPollAccountCreation` — all three test methods, same pattern**

**Step 3: Update `TestMoveAccountToOu` — both test methods, same pattern**

**Step 4: Run tests**

Run: `PYTHONPATH=. pytest tests/unit/services/test_aws.py -v`

**Step 5: Commit**

```bash
git commit --no-verify -m "test: update Organizations tests to mock get_management_session"
```

---

### Task 5: Update Documentation

**Files:**
- Replace: `docs/deployment/delegation-policy.md` → `docs/deployment/aws-setup.md`
- Modify: `README.md`
- Modify: `CLAUDE.md`
- Modify: `.env.example`

**Step 1: Delete `docs/deployment/delegation-policy.md` and create `docs/deployment/aws-setup.md`**

New doc covers:
- Management account role: trust policy (Groundwork account root) + permissions policy (Organizations actions)
- Groundwork account role: StackSets + `sts:AssumeRole` for management role + member admin roles
- CloudFormation StackSets delegated admin registration (existing)

**Step 2: Update README**

Replace the delegation policy sections (Steps 2 and 3 under "AWS permissions") with:
- Step 2: Create management account role (trust + permissions)
- Step 3: Create Groundwork account role (StackSets + AssumeRole for both management and member accounts)

Add `GW_AWS_MANAGEMENT_ROLE_ARN` to the config example and settings table.

**Step 3: Update CLAUDE.md**

Add `get_management_session()` to the AWS service layer bullet list.

**Step 4: Update `.env.example`**

Add `GW_AWS_MANAGEMENT_ROLE_ARN=arn:aws:iam::111122223333:role/GroundworkManagementRole`.

**Step 5: Commit**

```bash
git commit --no-verify -m "docs: replace delegation policy with management account role setup"
```

---

### Task 6: Full Test Suite + Lint + Security Review

**Step 1: Format and lint**

```bash
black backend/ tests/ && isort backend/ tests/ && flake8 backend/ tests/
```

**Step 2: Run full test suite**

```bash
PYTHONPATH=. pytest -o "addopts=" tests/ -v
```

**Step 3: Security review focus**

- `aws_management_role_arn` is not logged
- No credentials in log output
- `CallAs="DELEGATED_ADMIN"` still on all StackSet calls
- Management role permissions are narrowly scoped in docs
- AssumeRole resource in Groundwork role is scoped to the specific management role ARN

**Step 4: Commit any fixes**

```bash
git commit --no-verify -m "fix: address security review findings"
```
