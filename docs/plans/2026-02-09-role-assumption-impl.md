# Role Assumption Redesign Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace `AssumeRoleWithWebIdentity` with `AssumeRole` from the Groundwork account, remove OIDC providers from child accounts, add External ID protection, and create a `GET /api/federate` endpoint with 302 redirect.

**Architecture:** The Groundwork backend calls `sts:AssumeRole` directly from its AWS account into child account roles, gated by External ID. Access control (groups/users) is enforced entirely at the application layer before the STS call. The OIDC provider is removed from child account StackSets. Console access uses a GET endpoint that 302-redirects to the AWS federation URL.

**Tech Stack:** FastAPI, async SQLAlchemy, aioboto3, pytest

**Design doc:** `docs/plans/2026-02-09-role-assumption-redesign.md`

---

### Task 1: Add `compute_external_id` helper and rewrite `_build_trust_policy`

**Files:**
- Modify: `backend/services/aws.py:1-11` (imports), `backend/services/aws.py:280-341` (`_build_trust_policy`)
- Test: `tests/unit/services/test_aws_iam.py`

**Step 1: Write the failing tests**

Replace the contents of `TestBuildTrustPolicy` in `tests/unit/services/test_aws_iam.py` and add `TestComputeExternalId`:

```python
import hashlib

class TestComputeExternalId:
    def test_format(self):
        """External ID is Groundwork- prefix + 16 hex chars of SHA-256."""
        eid = aws.compute_external_id("role-uuid", "account-uuid")
        assert eid.startswith("Groundwork-")
        hex_part = eid[len("Groundwork-"):]
        assert len(hex_part) == 16
        # Verify it's valid hex
        int(hex_part, 16)

    def test_deterministic(self):
        """Same inputs produce the same External ID."""
        eid1 = aws.compute_external_id("role-1", "account-1")
        eid2 = aws.compute_external_id("role-1", "account-1")
        assert eid1 == eid2

    def test_different_inputs_differ(self):
        """Different role/account combos produce different External IDs."""
        eid1 = aws.compute_external_id("role-1", "account-1")
        eid2 = aws.compute_external_id("role-2", "account-1")
        assert eid1 != eid2

    def test_sha256_based(self):
        """Verify the hash matches expected SHA-256 computation."""
        expected = hashlib.sha256("role-1account-1".encode()).hexdigest()[:16]
        eid = aws.compute_external_id("role-1", "account-1")
        assert eid == f"Groundwork-{expected}"


class TestBuildTrustPolicy:
    def test_single_statement_with_external_id(self):
        """Trust policy has one statement with account root principal and External ID."""
        with patch.object(settings, "aws_groundwork_account_id", "999888777666"):
            policy_str = aws._build_trust_policy(external_id="Groundwork-abc123")

        policy = json.loads(policy_str)
        assert policy["Version"] == "2012-10-17"
        assert len(policy["Statement"]) == 1
        stmt = policy["Statement"][0]
        assert stmt["Sid"] == "AllowGroundworkAssume"
        assert stmt["Principal"]["AWS"] == "arn:aws:iam::999888777666:root"
        assert stmt["Action"] == "sts:AssumeRole"
        assert stmt["Condition"]["StringEquals"]["sts:ExternalId"] == "Groundwork-abc123"

    def test_no_oidc_references(self):
        """Trust policy must not reference Federated principal or AssumeRoleWithWebIdentity."""
        with patch.object(settings, "aws_groundwork_account_id", "999888777666"):
            policy_str = aws._build_trust_policy(external_id="Groundwork-abc123")

        assert "Federated" not in policy_str
        assert "AssumeRoleWithWebIdentity" not in policy_str
```

**Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=. pytest tests/unit/services/test_aws_iam.py::TestComputeExternalId -v`
Run: `PYTHONPATH=. pytest tests/unit/services/test_aws_iam.py::TestBuildTrustPolicy -v`
Expected: FAIL — `compute_external_id` doesn't exist, `_build_trust_policy` has wrong signature.

**Step 3: Implement `compute_external_id` and rewrite `_build_trust_policy`**

In `backend/services/aws.py`:

Add `compute_external_id` (after the imports, near line 28):

```python
def compute_external_id(role_id: str, account_id: str) -> str:
    """Compute a deterministic External ID for confusion-deputy protection.

    Format: Groundwork-{first 16 hex chars of SHA-256(role_id + account_id)}.
    """
    digest = hashlib.sha256(f"{role_id}{account_id}".encode()).hexdigest()[:16]
    return f"Groundwork-{digest}"
```

Replace `_build_trust_policy` (lines 280-341) with:

```python
def _build_trust_policy(external_id: str) -> str:
    """Build an IAM trust policy for AssumeRole from the Groundwork account.

    The trust policy allows the Groundwork AWS account root to assume
    the role, gated by an External ID condition for confusion-deputy
    protection.  User/group access control is enforced entirely at the
    application layer before the STS call.
    """
    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "AllowGroundworkAssume",
                "Effect": "Allow",
                "Principal": {
                    "AWS": f"arn:aws:iam::{settings.aws_groundwork_account_id}:root"
                },
                "Action": "sts:AssumeRole",
                "Condition": {
                    "StringEquals": {
                        "sts:ExternalId": external_id,
                    },
                },
            }
        ],
    }
    return json.dumps(policy)
```

**Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=. pytest tests/unit/services/test_aws_iam.py::TestComputeExternalId tests/unit/services/test_aws_iam.py::TestBuildTrustPolicy -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/services/aws.py tests/unit/services/test_aws_iam.py
git commit -m "feat: add compute_external_id and rewrite _build_trust_policy for AssumeRole"
```

---

### Task 2: Add `assume_role` function, remove `assume_role_with_web_identity`

**Files:**
- Modify: `backend/services/aws.py:497-547` (replace `assume_role_with_web_identity` with `assume_role`)
- Test: `tests/unit/services/test_aws_iam.py`

**Step 1: Write the failing test**

Add to `tests/unit/services/test_aws_iam.py`:

```python
from botocore.exceptions import ClientError
from tests.fixtures.aws import _stubbed_session, create_stubbed_client


class TestAssumeRole:
    async def test_assume_role_returns_credentials(self):
        _, sts_stubber = await create_stubbed_client("sts")
        sts_stubber.add_response(
            "assume_role",
            {
                "Credentials": {
                    "AccessKeyId": "ASIA1234567890EXAMPL",
                    "SecretAccessKey": "examplesecretaccesskey1234567890abcdefghij",
                    "SessionToken": "examplesessiontoken123456",
                    "Expiration": datetime(2025, 1, 1),
                },
                "AssumedRoleUser": {
                    "AssumedRoleId": "AROAEXAMPLE:user@example.com",
                    "Arn": "arn:aws:sts::123456789012:assumed-role/TestRole/user@example.com",
                },
            },
            expected_params={
                "RoleArn": "arn:aws:iam::123456789012:role/TestRole",
                "RoleSessionName": "user@example.com",
                "ExternalId": "Groundwork-abc123",
                "DurationSeconds": 900,
            },
        )
        sts_stubber.activate()

        gw_session = _stubbed_session({"sts": sts_stubber})

        with patch.object(aws, "get_session", return_value=gw_session):
            creds = await aws.assume_role(
                role_arn="arn:aws:iam::123456789012:role/TestRole",
                session_name="user@example.com",
                external_id="Groundwork-abc123",
                session_duration=900,
            )

        assert creds["access_key_id"] == "ASIA1234567890EXAMPL"
        assert creds["secret_access_key"] == "examplesecretaccesskey1234567890abcdefghij"
        assert creds["session_token"] == "examplesessiontoken123456"
        sts_stubber.assert_no_pending_responses()

    async def test_assume_role_access_denied_raises_forbidden(self):
        from backend.exceptions import ForbiddenError

        mock_session = MagicMock()
        mock_sts = AsyncMock()
        mock_sts.assume_role.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "denied"}}, "AssumeRole"
        )

        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_sts)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_session.client.return_value = mock_cm

        with patch.object(aws, "get_session", return_value=mock_session):
            with pytest.raises(ForbiddenError):
                await aws.assume_role(
                    role_arn="arn:aws:iam::123456789012:role/TestRole",
                    session_name="user@example.com",
                    external_id="Groundwork-abc123",
                    session_duration=900,
                )
```

**Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=. pytest tests/unit/services/test_aws_iam.py::TestAssumeRole -v`
Expected: FAIL — `aws.assume_role` doesn't exist.

**Step 3: Replace `assume_role_with_web_identity` with `assume_role`**

In `backend/services/aws.py`, replace lines 497-547 with:

```python
async def assume_role(
    role_arn: str,
    session_name: str,
    external_id: str,
    session_duration: int,
) -> STSCredentials:
    """Assume an IAM role from the Groundwork account via STS.

    Returns STSCredentials with access_key_id, secret_access_key,
    session_token, and expiration.

    Raises :class:`~backend.exceptions.ForbiddenError` when STS denies the
    assumption (trust policy mismatch, bad External ID, etc.).
    """
    from backend.exceptions import ForbiddenError

    session = get_session()
    try:
        async with session.client("sts") as sts:
            resp = await sts.assume_role(
                RoleArn=role_arn,
                RoleSessionName=session_name,
                ExternalId=external_id,
                DurationSeconds=session_duration,
            )
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        if code in ("AccessDenied", "AccessDeniedException"):
            logger.warning(
                "STS AssumeRole denied for role %s session %s: %s",
                role_arn,
                session_name,
                exc.response["Error"].get("Message", ""),
            )
            raise ForbiddenError(
                "Role assumption denied — check that the role's trust policy "
                "and External ID are correctly configured"
            ) from exc
        raise
    creds = resp["Credentials"]
    return STSCredentials(
        access_key_id=creds["AccessKeyId"],
        secret_access_key=creds["SecretAccessKey"],
        session_token=creds["SessionToken"],
        expiration=creds["Expiration"],
    )
```

**Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=. pytest tests/unit/services/test_aws_iam.py::TestAssumeRole -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/services/aws.py tests/unit/services/test_aws_iam.py
git commit -m "feat: add assume_role, remove assume_role_with_web_identity"
```

---

### Task 3: Update `create_iam_role` and `update_iam_role` signatures

These functions currently take `oidc_provider_arn` and pass it to `_build_trust_policy`. Change them to take `role_id` and `account_id` (as strings) and compute the External ID internally.

**Files:**
- Modify: `backend/services/aws.py:344-454` (`create_iam_role`, `update_iam_role`)
- Test: `tests/unit/services/test_aws_iam.py`

**Step 1: Update the tests**

In `tests/unit/services/test_aws_iam.py`, update `TestCreateIamRole`:

```python
class TestCreateIamRole:
    async def test_creates_role_with_policies(self):
        _, iam_stubber = await create_stubbed_client("iam")
        iam_stubber.add_response(
            "create_role",
            {
                "Role": {
                    "Path": "/",
                    "RoleName": ROLE_NAME,
                    "RoleId": "AROA1234567890EXAMPL",
                    "Arn": f"arn:aws:iam::{AWS_ACCOUNT_ID}:role/{ROLE_NAME}",
                    "CreateDate": datetime(2025, 1, 1),
                    "AssumeRolePolicyDocument": "{}",
                }
            },
        )
        iam_stubber.add_response("attach_role_policy", {})
        iam_stubber.add_response("put_role_policy", {})
        iam_stubber.activate()

        target_session = _stubbed_session({"iam": iam_stubber})

        with (
            patch.object(aws, "assume_groundwork_admin", new_callable=AsyncMock) as mock_assume,
            patch.object(settings, "aws_groundwork_account_id", "999888777666"),
        ):
            mock_assume.return_value = target_session

            role_arn = await aws.create_iam_role(
                aws_account_id=AWS_ACCOUNT_ID,
                role_name=ROLE_NAME,
                role_id="test-role-uuid",
                account_id="test-account-uuid",
                managed_policy_arns=["arn:aws:iam::aws:policy/ReadOnlyAccess"],
                inline_policy={"Version": "2012-10-17", "Statement": []},
                max_duration=3600,
            )

        assert role_arn == f"arn:aws:iam::{AWS_ACCOUNT_ID}:role/{ROLE_NAME}"
        mock_assume.assert_called_once_with(AWS_ACCOUNT_ID)
        iam_stubber.assert_no_pending_responses()
```

Update `update_iam_role` tests similarly — remove `oidc_provider_arn`, add `role_id` and `account_id` params. The update function should only rebuild the trust policy when explicitly requested (no more `allowed_groups`/`allowed_users` in changes triggering it — trust policy is static now). When trust policy fields change, the IAM trust policy does NOT need updating since groups/users are enforced at app layer only. However, `update_iam_role` should still accept a `rebuild_trust_policy` flag for cases where the External ID needs regeneration (shouldn't happen in practice, but good for completeness). Actually, simpler: the trust policy never changes after creation since the External ID is deterministic. Remove the trust policy update logic from `update_iam_role` entirely.

**Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=. pytest tests/unit/services/test_aws_iam.py::TestCreateIamRole -v`
Expected: FAIL — signature mismatch.

**Step 3: Implement the changes**

In `backend/services/aws.py`, replace `create_iam_role` (lines 344-380):

```python
async def create_iam_role(
    aws_account_id: str,
    role_name: str,
    role_id: str,
    account_id: str,
    managed_policy_arns: list[str],
    inline_policy: dict | None,
    max_duration: int,
) -> str:
    """Create an IAM role in the target account with Groundwork trust policy.

    Returns the role ARN.
    """
    target_session = await assume_groundwork_admin(aws_account_id)
    external_id = compute_external_id(role_id, account_id)
    trust_policy = _build_trust_policy(external_id)

    async with target_session.client("iam") as iam:
        resp = await iam.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=trust_policy,
            MaxSessionDuration=max_duration,
        )
        role_arn = resp["Role"]["Arn"]

        for arn in managed_policy_arns:
            await iam.attach_role_policy(RoleName=role_name, PolicyArn=arn)

        if inline_policy is not None:
            await iam.put_role_policy(
                RoleName=role_name,
                PolicyName="GroundworkInlinePolicy",
                PolicyDocument=json.dumps(inline_policy),
            )

    logger.info("Created IAM role %s in account %s", role_name, aws_account_id)
    return role_arn
```

Replace `update_iam_role` (lines 383-453) — remove the `oidc_provider_arn` parameter and the trust policy update logic (since the trust policy is now static after creation). Keep max_duration, managed_policies, and inline_policy update logic:

```python
async def update_iam_role(
    aws_account_id: str,
    role_name: str,
    changes: dict,
) -> None:
    """Update an IAM role in the target account.

    ``changes`` is a dict of field names to new values. Only fields present
    in the dict are updated. Trust policy is not updated since access control
    is enforced at the application layer and the External ID is static.
    """
    target_session = await assume_groundwork_admin(aws_account_id)

    async with target_session.client("iam") as iam:
        # Max session duration (derived from the larger of api/console duration)
        if "api_session_duration" in changes or "console_session_duration" in changes:
            max_dur = max(
                changes.get("api_session_duration", 900),
                changes.get("console_session_duration", 3600),
            )
            await iam.update_role(RoleName=role_name, MaxSessionDuration=max_dur)

        # Managed policies
        if "managed_policy_arns" in changes:
            paginator = iam.get_paginator("list_attached_role_policies")
            async for page in paginator.paginate(RoleName=role_name):
                for policy in page.get("AttachedPolicies", []):
                    await iam.detach_role_policy(
                        RoleName=role_name, PolicyArn=policy["PolicyArn"]
                    )
            for arn in changes["managed_policy_arns"]:
                await iam.attach_role_policy(RoleName=role_name, PolicyArn=arn)

        # Inline policy
        if "inline_policy" in changes:
            if changes["inline_policy"] is not None:
                await iam.put_role_policy(
                    RoleName=role_name,
                    PolicyName="GroundworkInlinePolicy",
                    PolicyDocument=json.dumps(changes["inline_policy"]),
                )
            else:
                try:
                    await iam.delete_role_policy(
                        RoleName=role_name,
                        PolicyName="GroundworkInlinePolicy",
                    )
                except ClientError as e:
                    if e.response["Error"]["Code"] != "NoSuchEntity":
                        raise

    logger.info("Updated IAM role %s in account %s", role_name, aws_account_id)
```

**Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=. pytest tests/unit/services/test_aws_iam.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/services/aws.py tests/unit/services/test_aws_iam.py
git commit -m "refactor: update create/update_iam_role signatures for AssumeRole model"
```

---

### Task 4: Update job handlers to use new `create_iam_role` / `update_iam_role` signatures

**Files:**
- Modify: `backend/services/jobs.py:456-604` (`run_create_role`, `run_update_role`)
- Test: `tests/unit/services/test_jobs.py`

**Step 1: Update the tests**

In tests for `run_create_role`, the mock for `aws.create_iam_role` should expect the new signature (no `oidc_provider_arn`, add `role_id` and `account_id`). In tests for `run_update_role`, the mock for `aws.update_iam_role` should expect no `oidc_provider_arn`.

Read the existing tests first and update the mock assertions. The `account.oidc_provider_arn` references in job handler tests should be removable since the handlers no longer pass it.

**Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=. pytest tests/unit/services/test_jobs.py -k "create_role or update_role" -v`
Expected: FAIL — handlers pass `oidc_provider_arn` which no longer exists in the function signature.

**Step 3: Update `run_create_role` in `backend/services/jobs.py`**

Change lines 479-488 from:

```python
        role_arn = await aws.create_iam_role(
            aws_account_id=account.aws_account_id,
            role_name=role.role_name,
            oidc_provider_arn=account.oidc_provider_arn,
            allowed_groups=role.allowed_groups,
            allowed_users=role.allowed_users,
            managed_policy_arns=role.managed_policy_arns,
            inline_policy=role.inline_policy,
            max_duration=max(role.api_session_duration, role.console_session_duration),
        )
```

To:

```python
        role_arn = await aws.create_iam_role(
            aws_account_id=account.aws_account_id,
            role_name=role.role_name,
            role_id=str(role.id),
            account_id=str(role.account_id),
            managed_policy_arns=role.managed_policy_arns,
            inline_policy=role.inline_policy,
            max_duration=max(role.api_session_duration, role.console_session_duration),
        )
```

Change `run_update_role` lines 558-563 from:

```python
        await aws.update_iam_role(
            aws_account_id=account.aws_account_id,
            role_name=role.role_name,
            oidc_provider_arn=account.oidc_provider_arn,
            changes=changes,
        )
```

To:

```python
        await aws.update_iam_role(
            aws_account_id=account.aws_account_id,
            role_name=role.role_name,
            changes=changes,
        )
```

**Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=. pytest tests/unit/services/test_jobs.py -k "create_role or update_role" -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/services/jobs.py tests/unit/services/test_jobs.py
git commit -m "refactor: update job handlers for new IAM role function signatures"
```

---

### Task 5: Rewrite `POST /api/roles/assume` to use `sts:AssumeRole`

**Files:**
- Modify: `backend/routers/roles.py:362-401`
- Test: `tests/unit/routers/test_roles.py`

**Step 1: Update the tests**

In `tests/unit/routers/test_roles.py`, update `TestAssumeRole`:

- Change all `patch("backend.routers.roles.aws.assume_role_with_web_identity"` to `patch("backend.routers.roles.aws.assume_role"`
- Remove the `id_token` assertion from `test_assume_role_token_refresh` (token refresh is no longer needed for STS calls — remove this test entirely)
- Update `test_assume_role_success` to assert `external_id` is passed instead of `id_token`
- The mock calls should expect `role_arn`, `session_name`, `external_id`, `session_duration`

Key test changes in `test_assume_role_success`:

```python
    async def test_assume_role_success(self, client, db_session):
        user, session_id = await _create_user_with_tokens(
            db_session, groups=["devs"], sub="dev-user-1"
        )
        admin, _ = await _create_authenticated_user(db_session, is_admin=True)
        account = await _create_active_account(db_session, admin)
        role = await _create_role_for_assumption(db_session, account, allowed_groups=["devs"])

        with patch(
            "backend.routers.roles.aws.assume_role",
            new_callable=AsyncMock,
        ) as mock_assume:
            mock_assume.return_value = FAKE_STS_CREDS

            response = await client.post(
                "/api/roles/assume",
                json={"role_id": str(role.id)},
                cookies=_cookies(session_id),
            )

        assert response.status_code == 200
        data = response.json()
        assert data["access_key_id"] == "ASIA1234567890EXAMPL"

        mock_assume.assert_called_once()
        call_kwargs = mock_assume.call_args.kwargs
        assert call_kwargs["role_arn"] == role.role_arn
        assert call_kwargs["session_duration"] == 900
        assert call_kwargs["session_name"] == user.email
        assert call_kwargs["external_id"].startswith("Groundwork-")
```

Delete `test_assume_role_token_refresh` — token refresh before STS is no longer applicable.

Update all other assume tests similarly (replace `assume_role_with_web_identity` mock with `assume_role`).

**Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=. pytest tests/unit/routers/test_roles.py::TestAssumeRole -v`
Expected: FAIL — endpoint still calls `assume_role_with_web_identity`.

**Step 3: Update the endpoint**

In `backend/routers/roles.py`, replace `assume_role` endpoint (lines 362-401):

```python
@router.post("/api/roles/assume", response_model=AssumeRoleResponse)
async def assume_role(
    body: AssumeRoleRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    role = await _load_role_for_assumption(body.role_id, user, db)

    external_id = aws.compute_external_id(str(role.id), str(role.account_id))
    credentials = await aws.assume_role(
        role_arn=role.role_arn,
        session_name=_sanitize_session_name(user.email),
        external_id=external_id,
        session_duration=role.api_session_duration,
    )

    await log_event(
        db,
        action="role.assume",
        user_id=user.id,
        resource_type="role",
        resource_id=str(role.id),
        detail={
            "role_name": role.role_name,
            "account_id": str(role.account_id),
            "role_arn": role.role_arn,
        },
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return AssumeRoleResponse(
        access_key_id=credentials["access_key_id"],
        secret_access_key=credentials["secret_access_key"],
        session_token=credentials["session_token"],
        expiration=credentials["expiration"],
    )
```

Note: This endpoint now uses `get_current_user` instead of `get_current_session` — it no longer needs the session object since there's no `get_fresh_id_token` call.

**Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=. pytest tests/unit/routers/test_roles.py::TestAssumeRole -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/routers/roles.py tests/unit/routers/test_roles.py
git commit -m "feat: rewrite POST /api/roles/assume to use sts:AssumeRole with External ID"
```

---

### Task 6: Add `GET /api/federate` endpoint with 302 redirect

**Files:**
- Modify: `backend/routers/roles.py` (add new endpoint, remove `POST /api/roles/console`)
- Test: `tests/unit/routers/test_roles.py`

**Step 1: Write the failing tests**

Replace `TestConsoleAccess` in `tests/unit/routers/test_roles.py` with `TestFederate`:

```python
class TestFederate:
    async def test_federate_redirects_to_console(self, client, db_session):
        user, session_id = await _create_user_with_tokens(
            db_session, groups=["devs"], sub="dev-federate"
        )
        admin, _ = await _create_authenticated_user(db_session, is_admin=True)
        account = await _create_active_account(db_session, admin)
        role = await _create_role_for_assumption(db_session, account, allowed_groups=["devs"])

        with (
            patch(
                "backend.routers.roles.aws.assume_role",
                new_callable=AsyncMock,
            ) as mock_assume,
            patch(
                "backend.routers.roles.aws.get_console_url",
                new_callable=AsyncMock,
            ) as mock_console,
        ):
            mock_assume.return_value = FAKE_STS_CREDS
            mock_console.return_value = (
                "https://signin.aws.amazon.com/federation?Action=login&SigninToken=abc"
            )

            response = await client.get(
                f"/api/federate?account_id={account.id}&role={role.role_name}",
                cookies=_cookies(session_id),
                follow_redirects=False,
            )

        assert response.status_code == 302
        assert response.headers["location"].startswith("https://signin.aws.amazon.com/federation")

        call_kwargs = mock_assume.call_args.kwargs
        assert call_kwargs["session_duration"] == role.console_session_duration
        assert call_kwargs["external_id"].startswith("Groundwork-")

    async def test_federate_forbidden_no_access(self, client, db_session):
        user, session_id = await _create_user_with_tokens(
            db_session, groups=["finance"], sub="finance-federate"
        )
        admin, _ = await _create_authenticated_user(db_session, is_admin=True)
        account = await _create_active_account(db_session, admin)
        role = await _create_role_for_assumption(
            db_session, account, allowed_groups=["devs"], allowed_users=[]
        )

        response = await client.get(
            f"/api/federate?account_id={account.id}&role={role.role_name}",
            cookies=_cookies(session_id),
            follow_redirects=False,
        )

        assert response.status_code == 403

    async def test_federate_role_not_found(self, client, db_session):
        user, session_id = await _create_user_with_tokens(
            db_session, groups=["devs"], sub="dev-federate-404"
        )
        admin, _ = await _create_authenticated_user(db_session, is_admin=True)
        account = await _create_active_account(db_session, admin)

        response = await client.get(
            f"/api/federate?account_id={account.id}&role=NonExistentRole",
            cookies=_cookies(session_id),
            follow_redirects=False,
        )

        assert response.status_code == 404

    async def test_federate_audit_logged(self, client, db_session):
        user, session_id = await _create_user_with_tokens(
            db_session, groups=["devs"], sub="dev-federate-audit"
        )
        admin, _ = await _create_authenticated_user(db_session, is_admin=True)
        account = await _create_active_account(db_session, admin)
        role = await _create_role_for_assumption(db_session, account, allowed_groups=["devs"])

        with (
            patch(
                "backend.routers.roles.aws.assume_role",
                new_callable=AsyncMock,
            ) as mock_assume,
            patch(
                "backend.routers.roles.aws.get_console_url",
                new_callable=AsyncMock,
            ) as mock_console,
        ):
            mock_assume.return_value = FAKE_STS_CREDS
            mock_console.return_value = "https://signin.aws.amazon.com/federation?Action=login"

            response = await client.get(
                f"/api/federate?account_id={account.id}&role={role.role_name}",
                cookies=_cookies(session_id),
                follow_redirects=False,
            )

        assert response.status_code == 302

        result = await db_session.execute(
            select(AuditLog).where(AuditLog.action == "role.federate")
        )
        log = result.scalar_one()
        assert log.user_id == user.id
        assert log.resource_type == "role"

    async def test_old_console_endpoint_removed(self, client, db_session):
        """POST /api/roles/console should no longer exist."""
        user, session_id = await _create_user_with_tokens(
            db_session, groups=["devs"], sub="dev-old-console"
        )

        response = await client.post(
            "/api/roles/console",
            json={"role_id": "00000000-0000-0000-0000-000000000000"},
            cookies=_cookies(session_id),
        )

        # Should be 404 or 405 since endpoint is removed
        assert response.status_code in (404, 405)
```

**Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=. pytest tests/unit/routers/test_roles.py::TestFederate -v`
Expected: FAIL — endpoint doesn't exist.

**Step 3: Add a helper to load role by account_id + role_name, add the endpoint, remove old endpoint**

Add a helper function for the federate lookup:

```python
async def _load_role_for_federation(
    account_id: UUID,
    role_name: str,
    user: User,
    db: AsyncSession,
) -> Role:
    """Load a role by account_id + role_name and verify access for federation."""
    result = await db.execute(
        select(Role)
        .options(joinedload(Role.account))
        .where(Role.account_id == account_id, Role.role_name == role_name)
    )
    role = result.scalar_one_or_none()
    if role is None:
        raise NotFoundError("Role not found")

    if role.status != "active":
        raise GroundworkError("Role is not available for assumption", status_code=400)

    user_groups = set(user.groups or [])
    role_groups = set(role.allowed_groups or [])
    if not (user_groups & role_groups) and user.sub not in (role.allowed_users or []):
        raise ForbiddenError("You do not have access to assume this role")

    if role.account.status != "active":
        raise GroundworkError("Account is not active", status_code=400)

    return role
```

Add the federate endpoint:

```python
from fastapi.responses import RedirectResponse


@router.get("/api/federate")
async def federate(
    account_id: UUID,
    role: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    loaded_role = await _load_role_for_federation(account_id, role, user, db)

    external_id = aws.compute_external_id(str(loaded_role.id), str(loaded_role.account_id))
    credentials = await aws.assume_role(
        role_arn=loaded_role.role_arn,
        session_name=_sanitize_session_name(user.email),
        external_id=external_id,
        session_duration=loaded_role.console_session_duration,
    )

    console_url = await aws.get_console_url(
        credentials=credentials,
        console_session_duration=loaded_role.console_session_duration,
        issuer=settings.app_url,
    )

    await log_event(
        db,
        action="role.federate",
        user_id=user.id,
        resource_type="role",
        resource_id=str(loaded_role.id),
        detail={
            "role_name": loaded_role.role_name,
            "account_id": str(loaded_role.account_id),
            "role_arn": loaded_role.role_arn,
        },
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return RedirectResponse(url=console_url, status_code=302)
```

Delete the old `console_access` endpoint (lines 404-447).

**Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=. pytest tests/unit/routers/test_roles.py::TestFederate -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/routers/roles.py tests/unit/routers/test_roles.py
git commit -m "feat: add GET /api/federate with 302 redirect, remove POST /api/roles/console"
```

---

### Task 7: Clean up imports and remove dead code

**Files:**
- Modify: `backend/routers/roles.py` (remove `get_fresh_id_token`, `get_current_session`, `ConsoleUrlResponse` imports)
- Modify: `backend/schemas/role.py` (remove `ConsoleUrlResponse` class)
- Modify: `backend/dependencies/auth.py` (remove `get_fresh_id_token`, `_decode_jwt_exp`, `_get_refresh_lock`, `_refresh_locks`, `TOKEN_REFRESH_MARGIN`)

**Step 1: Verify what to remove**

Before removing from `auth.py`, verify `get_fresh_id_token` is not imported anywhere else:
Run: `PYTHONPATH=. grep -rn "get_fresh_id_token\|_decode_jwt_exp\|TOKEN_REFRESH_MARGIN" backend/`

After confirming they're only in `auth.py` and `roles.py` (where we've already removed usage):

**Step 2: Remove `ConsoleUrlResponse` from `backend/schemas/role.py`**

Delete lines 147-149:
```python
class ConsoleUrlResponse(BaseModel):
    console_url: str
    expiration: datetime
```

**Step 3: Remove dead imports from `backend/routers/roles.py`**

Update the import block (lines 12-31) to remove `get_current_session`, `get_fresh_id_token`, and `ConsoleUrlResponse`. Add `RedirectResponse` import if not already added.

**Step 4: Remove `get_fresh_id_token` and helpers from `backend/dependencies/auth.py`**

Remove:
- `TOKEN_REFRESH_MARGIN` (line 116)
- `_decode_jwt_exp` function (lines 119-143)
- `_get_refresh_lock` function (lines 146-150)
- `_refresh_locks` dict (find its declaration, likely near the top)
- `get_fresh_id_token` function (lines 153-197)
- Associated imports: `base64`, `json` (if only used by these functions)

Keep `get_current_session` — verify if anything else uses it first. If nothing else imports it, remove it too.

**Step 5: Run the full test suite**

Run: `PYTHONPATH=. pytest tests/ -v`
Expected: PASS (all tests pass after cleanup)

**Step 6: Run linting**

Run: `black backend/ tests/ && isort backend/ tests/ && flake8 backend/ tests/`
Expected: Clean

**Step 7: Commit**

```bash
git add backend/routers/roles.py backend/schemas/role.py backend/dependencies/auth.py
git commit -m "chore: remove dead code — ConsoleUrlResponse, get_fresh_id_token, OIDC token refresh for STS"
```

---

### Task 8: Remove OIDC provider from bootstrap StackSet template

**Files:**
- Modify: `backend/services/aws.py:658-793` (`ensure_bootstrap_stackset`, `_build_bootstrap_template`)
- Modify: `backend/services/aws.py:174-221` (`bootstrap_account` — remove `oidc_provider_arn` from return value)
- Modify: `backend/services/aws.py:224-251` (remove `get_oidc_thumbprint`, `_fetch_server_cert`)
- Test: `tests/unit/services/test_aws.py`

**Step 1: Update tests for `_build_bootstrap_template`**

In `tests/unit/services/test_aws.py`, update `TestBuildBootstrapTemplate`:

```python
class TestBuildBootstrapTemplate:
    def test_template_has_admin_role(self):
        body = aws._build_bootstrap_template(
            groundwork_account_id="222233334444",
            admin_role_name="GroundworkAdmin-DO-NOT-DELETE",
        )
        parsed = json.loads(body)
        assert parsed["AWSTemplateFormatVersion"] == "2010-09-09"
        assert "AdminRole" in parsed["Resources"]

    def test_no_oidc_provider(self):
        """OIDC provider resource must not be in the template."""
        body = aws._build_bootstrap_template(
            groundwork_account_id="222233334444",
            admin_role_name="GroundworkAdmin-DO-NOT-DELETE",
        )
        parsed = json.loads(body)
        assert "OidcProvider" not in parsed["Resources"]
        assert "OidcProviderArn" not in parsed.get("Outputs", {})

    def test_admin_role_trusts_groundwork_account(self):
        body = aws._build_bootstrap_template(
            groundwork_account_id="222233334444",
            admin_role_name="GroundworkAdmin-DO-NOT-DELETE",
        )
        parsed = json.loads(body)
        role = parsed["Resources"]["AdminRole"]["Properties"]
        assert role["RoleName"] == "GroundworkAdmin-DO-NOT-DELETE"
        trust = role["AssumeRolePolicyDocument"]
        assert trust["Statement"][0]["Principal"]["AWS"] == "arn:aws:iam::222233334444:root"
```

Update `bootstrap_account` tests — return value should have `admin_role_arn` only (no `oidc_provider_arn`).

**Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=. pytest tests/unit/services/test_aws.py::TestBuildBootstrapTemplate -v`
Expected: FAIL — function signature has changed.

**Step 3: Implement changes**

Replace `_build_bootstrap_template` (lines 732-793):

```python
def _build_bootstrap_template(
    groundwork_account_id: str,
    admin_role_name: str = "GroundworkAdmin-DO-NOT-DELETE",
) -> str:
    """Build a CloudFormation template for bootstrapping member accounts.

    Generates a template that creates an admin management role trusted
    by the Groundwork service account.

    Returns a JSON string suitable for passing as ``TemplateBody``
    to CloudFormation ``CreateStackSet``.
    """
    template: dict = {
        "AWSTemplateFormatVersion": "2010-09-09",
        "Description": "Groundwork bootstrap - admin role for member accounts",
        "Resources": {
            "AdminRole": {
                "Type": "AWS::IAM::Role",
                "Properties": {
                    "RoleName": admin_role_name,
                    "Description": "Groundwork admin management role - DO NOT DELETE",
                    "MaxSessionDuration": 3600,
                    "AssumeRolePolicyDocument": {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Effect": "Allow",
                                "Principal": {
                                    "AWS": f"arn:aws:iam::{groundwork_account_id}:root"
                                },
                                "Action": "sts:AssumeRole",
                            }
                        ],
                    },
                    "ManagedPolicyArns": [
                        "arn:aws:iam::aws:policy/AdministratorAccess",
                    ],
                },
            },
        },
        "Outputs": {
            "AdminRoleArn": {
                "Description": "ARN of the Groundwork admin role",
                "Value": {"Fn::GetAtt": ["AdminRole", "Arn"]},
            },
        },
    }
    return json.dumps(template)
```

Update `ensure_bootstrap_stackset` (lines 658-725) — remove thumbprint fetch and OIDC params:

```python
async def ensure_bootstrap_stackset() -> None:
    """Create or update the bootstrap StackSet.

    Uses service-managed permissions with auto-deploy enabled, targeting
    the entire organization. On every call the StackSet template is
    re-applied so that configuration changes are picked up on restart.
    """
    session = get_session()

    template_body = _build_bootstrap_template(
        groundwork_account_id=settings.aws_groundwork_account_id,
        admin_role_name=settings.admin_role_name,
    )

    async with session.client("cloudformation") as cfn:
        # (rest of logic stays the same — check/create/update)
```

Update `bootstrap_account` (lines 174-221) — remove `oidc_provider_arn` from return dict:

```python
    # Compute ARN deterministically from known inputs
    admin_role_arn = f"arn:aws:iam::{aws_account_id}:role/{settings.admin_role_name}"

    logger.info(
        "Bootstrap complete for account %s: role=%s",
        aws_account_id,
        admin_role_arn,
    )
    return {
        "admin_role_arn": admin_role_arn,
    }
```

Remove `get_oidc_thumbprint` and `_fetch_server_cert` (lines 224-251).

Remove `ssl` from imports (line 7) if no longer used.

**Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=. pytest tests/unit/services/test_aws.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/services/aws.py tests/unit/services/test_aws.py
git commit -m "feat: remove OIDC provider from bootstrap StackSet, simplify template"
```

---

### Task 9: Update bootstrap job handlers and Account model references

**Files:**
- Modify: `backend/services/jobs.py:180-270` (bootstrap handlers — remove `oidc_provider_arn` storage)
- Modify: `tests/unit/services/test_jobs.py` (update assertions)
- Modify: `tests/fixtures/aws.py` (remove `FAKE_OIDC_ARN` from `mock_aws_bootstrap_account` fixture return)
- Modify: `tests/unit/routers/test_roles.py` (remove `oidc_provider_arn` from `_create_active_account` helper)

**Step 1: Update job handlers**

In `backend/services/jobs.py`, find all lines that set `account.oidc_provider_arn = bootstrap_result["oidc_provider_arn"]` and remove them. The `oidc_provider_arn` column still exists in the DB but will no longer be populated going forward (we won't remove the column in this change to avoid a migration).

**Step 2: Update fixtures**

In `tests/fixtures/aws.py`, update `mock_aws_bootstrap_account`:

```python
@pytest.fixture
def mock_aws_bootstrap_account():
    with patch("backend.services.aws.bootstrap_account", new_callable=AsyncMock) as m:
        m.return_value = {
            "admin_role_arn": FAKE_ADMIN_ROLE_ARN,
        }
        yield m
```

In `tests/unit/routers/test_roles.py`, the `_create_active_account` helper sets `oidc_provider_arn`. Remove that field — it's no longer needed for role operations:

```python
async def _create_active_account(db_session, admin_user):
    account = Account(
        account_name="Test Account",
        account_email=f"acct-{id(db_session)}@example.com",
        organizational_unit="ou-1234",
        sso_user_email="sso@example.com",
        created_by=admin_user.id,
        status="active",
        aws_account_id="123456789012",
    )
    db_session.add(account)
    await db_session.flush()
    return account
```

**Step 3: Update job tests**

Remove all assertions about `account.oidc_provider_arn` in `tests/unit/services/test_jobs.py`. Update mock return values to not include `oidc_provider_arn`.

**Step 4: Run the full test suite**

Run: `PYTHONPATH=. pytest tests/ -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/services/jobs.py tests/fixtures/aws.py tests/unit/services/test_jobs.py tests/unit/routers/test_roles.py
git commit -m "refactor: remove oidc_provider_arn from bootstrap flow and test fixtures"
```

---

### Task 10: Update status gating tests and run full suite

**Files:**
- Modify: `tests/unit/routers/test_roles.py` (update `TestRoleStatusGating` if it references old console endpoint)
- Run: Full test suite, linting, type checking

**Step 1: Update status gating tests**

In `tests/unit/routers/test_roles.py`, `TestRoleStatusGating` likely has tests for `POST /api/roles/console`. Replace those with equivalent tests for `GET /api/federate`. The gating logic should be the same — role must be `status="active"` and account must be active.

**Step 2: Run full test suite**

Run: `PYTHONPATH=. pytest tests/ -v`
Expected: PASS

**Step 3: Run linting and formatting**

Run: `black backend/ tests/ && isort backend/ tests/ && flake8 backend/ tests/`
Expected: Clean

**Step 4: Run type checking**

Run: `PYTHONPATH=. mypy backend/ tests/`
Expected: Clean (or only pre-existing issues)

**Step 5: Commit**

```bash
git add -A
git commit -m "test: update status gating tests for federate endpoint, full suite green"
```

---

### Task 11: Security review

**Run the code-reviewer agent** with a security focus covering:

1. External ID computation — is SHA-256 of predictable inputs a concern? (No — External ID is not a secret, just confusion-deputy protection)
2. Federation endpoint — can the 302 redirect be abused for open redirect? (No — URL is always constructed from AWS federation endpoint, not user input)
3. Access control — verify groups/users check is applied in both `/api/roles/assume` and `/api/federate`
4. Query parameter injection — verify `account_id` and `role` params in `/api/federate` are properly validated (UUID type for account_id, string for role name)
5. Audit logging — verify both endpoints log assumption events

Fix any findings before committing.

```bash
git add -A
git commit -m "security: address review findings from role assumption redesign"
```
