# Migrate Account Bootstrap to CloudFormation StackSets

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace direct IAM API calls via `OrganizationAccountAccessRole` with a CloudFormation StackSet (service-managed, auto-deploy) to create the OIDC provider and GroundworkAdmin role in member accounts.

**Architecture:** The Groundwork service assumes a role in a dedicated Groundwork AWS account that is a delegated administrator for CloudFormation StackSets. A single service-managed StackSet with auto-deploy targets the entire organization, automatically deploying an OIDC provider and admin role to every member account. For newly provisioned accounts, the job handler polls until the StackSet instance reaches `CREATE_COMPLETE`. A manual trigger is available for accounts that need re-deployment. The GroundworkAdmin role trust policy changes from trusting the management account to trusting the Groundwork account. All Phase 3-4 operations (`assume_groundwork_admin`) chain through the Groundwork account session.

**Tech Stack:** aioboto3 (CloudFormation StackSets API), CloudFormation YAML template, existing FastAPI + SQLAlchemy stack

---

## Summary of Changes

| Area | Before | After |
|------|--------|-------|
| Bootstrap mechanism | Assume `OrganizationAccountAccessRole`, call IAM directly | StackSet auto-deploys, app polls for completion |
| Admin role trust | Management account root | Groundwork account root |
| `assume_groundwork_admin` base session | `get_session()` (management account) | `get_groundwork_session()` (Groundwork account) |
| OIDC thumbprint use | Called per-bootstrap in `bootstrap_account()` | Called once when creating StackSet |
| New config | — | `aws_groundwork_account_id`, `aws_groundwork_role_name`, `aws_org_root_id` |
| New files | — | `backend/templates/bootstrap_stackset.yaml` |

---

### Task 1: Add Config Settings

**Files:**
- Modify: `backend/config.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_config.py — add to existing or create
from backend.config import Settings

class TestStackSetConfig:
    def test_groundwork_account_id_default(self):
        s = Settings(session_secret="test")
        assert s.aws_groundwork_account_id == ""

    def test_groundwork_role_name_default(self):
        s = Settings(session_secret="test")
        assert s.aws_groundwork_role_name == "GroundworkStackSetRole"

    def test_org_root_id_default(self):
        s = Settings(session_secret="test")
        assert s.aws_org_root_id == ""
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest tests/unit/test_config.py::TestStackSetConfig -v`
Expected: FAIL — attributes don't exist

**Step 3: Write minimal implementation**

Add to `backend/config.py` in the `Settings` class, in the AWS section:

```python
    # AWS
    aws_region: str = "us-east-1"
    aws_portfolio_id: str = ""
    aws_management_account_id: str = ""
    aws_groundwork_account_id: str = ""
    aws_groundwork_role_name: str = "GroundworkStackSetRole"
    aws_org_root_id: str = ""
    admin_role_name: str = "GroundworkAdmin-DO-NOT-DELETE"
```

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. pytest tests/unit/test_config.py::TestStackSetConfig -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/config.py tests/unit/test_config.py
git commit -m "feat: add StackSet config settings for Groundwork account"
```

---

### Task 2: Create CloudFormation Template

**Files:**
- Create: `backend/templates/bootstrap_stackset.yaml`

**Step 1: Create the CloudFormation template**

```yaml
AWSTemplateFormatVersion: '2010-09-09'
Description: >-
  Groundwork bootstrap — creates OIDC identity provider and admin management
  role in each member account. Deployed via service-managed StackSet.

Parameters:
  OidcIssuerUrl:
    Type: String
    Description: OIDC issuer URL (e.g. https://idp.example.com)
  OidcClientId:
    Type: String
    Description: OIDC client ID registered with the issuer
  OidcThumbprint:
    Type: String
    Description: SHA-1 thumbprint of the OIDC issuer TLS certificate
    AllowedPattern: '[a-f0-9]{40}'
  GroundworkAccountId:
    Type: String
    Description: AWS account ID of the Groundwork service account
    AllowedPattern: '[0-9]{12}'
  AdminRoleName:
    Type: String
    Default: GroundworkAdmin-DO-NOT-DELETE
    Description: Name of the admin management role

Resources:
  OidcProvider:
    Type: AWS::IAM::OIDCProvider
    Properties:
      Url: !Ref OidcIssuerUrl
      ClientIdList:
        - !Ref OidcClientId
      ThumbprintList:
        - !Ref OidcThumbprint

  AdminRole:
    Type: AWS::IAM::Role
    Properties:
      RoleName: !Ref AdminRoleName
      Description: Groundwork admin management role — DO NOT DELETE
      MaxSessionDuration: 3600
      AssumeRolePolicyDocument:
        Version: '2012-10-17'
        Statement:
          - Effect: Allow
            Principal:
              AWS: !Sub 'arn:aws:iam::${GroundworkAccountId}:root'
            Action: sts:AssumeRole
      ManagedPolicyArns:
        - arn:aws:iam::aws:policy/AdministratorAccess

Outputs:
  OidcProviderArn:
    Description: ARN of the OIDC identity provider
    Value: !Ref OidcProvider
  AdminRoleArn:
    Description: ARN of the admin management role
    Value: !GetAtt AdminRole.Arn
```

**Step 2: Write a test that loads the template**

```python
# tests/unit/services/test_aws.py — add this class
import yaml
from pathlib import Path

TEMPLATE_PATH = Path(__file__).resolve().parents[3] / "backend" / "templates" / "bootstrap_stackset.yaml"

class TestBootstrapTemplate:
    def test_template_loads_as_valid_yaml(self):
        body = TEMPLATE_PATH.read_text()
        parsed = yaml.safe_load(body)
        assert parsed["AWSTemplateFormatVersion"] == "2010-09-09"
        assert "OidcProvider" in parsed["Resources"]
        assert "AdminRole" in parsed["Resources"]

    def test_template_has_required_parameters(self):
        parsed = yaml.safe_load(TEMPLATE_PATH.read_text())
        params = parsed["Parameters"]
        for key in ("OidcIssuerUrl", "OidcClientId", "OidcThumbprint",
                     "GroundworkAccountId", "AdminRoleName"):
            assert key in params, f"Missing parameter: {key}"

    def test_template_has_outputs(self):
        parsed = yaml.safe_load(TEMPLATE_PATH.read_text())
        outputs = parsed["Outputs"]
        assert "OidcProviderArn" in outputs
        assert "AdminRoleArn" in outputs
```

**Step 3: Run tests**

Run: `PYTHONPATH=. pytest tests/unit/services/test_aws.py::TestBootstrapTemplate -v`
Expected: PASS (template was created in step 1)

Note: add `pyyaml` to `requirements-dev.txt` if not already present (check first).

**Step 4: Commit**

```bash
git add backend/templates/bootstrap_stackset.yaml tests/unit/services/test_aws.py
git commit -m "feat: add CloudFormation template for bootstrap StackSet"
```

---

### Task 3: Add `get_groundwork_session()` Function

**Files:**
- Modify: `backend/services/aws.py`
- Modify: `tests/unit/services/test_aws.py`

This function assumes a role in the Groundwork account and returns a session. All StackSet and member-account admin operations will use it.

**Step 1: Write the failing test**

```python
# tests/unit/services/test_aws.py — add this class
class TestGetGroundworkSession:
    async def test_assumes_role_in_groundwork_account(self):
        _, sts_stubber = await create_stubbed_client("sts")
        sts_stubber.add_response(
            "assume_role",
            {
                "Credentials": {
                    "AccessKeyId": "AKIAEXAMPLE",
                    "SecretAccessKey": "secretEXAMPLE",
                    "SessionToken": "tokenEXAMPLE",
                    "Expiration": datetime(2025, 1, 1),
                },
                "AssumedRoleUser": {
                    "AssumedRoleId": "AROAEXAMPLE:GroundworkStackSet",
                    "Arn": "arn:aws:sts::222233334444:assumed-role/GroundworkStackSetRole/GroundworkStackSet",
                },
            },
            expected_params={
                "RoleArn": "arn:aws:iam::222233334444:role/GroundworkStackSetRole",
                "RoleSessionName": "GroundworkStackSet",
            },
        )
        sts_stubber.activate()

        with (
            patch.object(aws, "get_session", return_value=_stubbed_session({"sts": sts_stubber})),
            patch.object(settings, "aws_groundwork_account_id", "222233334444"),
            patch.object(settings, "aws_groundwork_role_name", "GroundworkStackSetRole"),
            patch("backend.services.aws.aioboto3") as mock_aioboto3,
        ):
            session = await aws.get_groundwork_session()

        assert session is not None
        mock_aioboto3.Session.assert_called_once()
        call_kwargs = mock_aioboto3.Session.call_args[1]
        assert call_kwargs["aws_access_key_id"] == "AKIAEXAMPLE"
        sts_stubber.assert_no_pending_responses()
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest tests/unit/services/test_aws.py::TestGetGroundworkSession -v`
Expected: FAIL — `aws.get_groundwork_session` doesn't exist

**Step 3: Write minimal implementation**

Add to `backend/services/aws.py` after `get_session()`:

```python
async def get_groundwork_session() -> aioboto3.Session:
    """Assume a role in the Groundwork account and return a session.

    Used for StackSet management and as the base session for assuming
    GroundworkAdmin roles in member accounts.
    """
    session = get_session()
    role_arn = (
        f"arn:aws:iam::{settings.aws_groundwork_account_id}"
        f":role/{settings.aws_groundwork_role_name}"
    )
    async with session.client("sts") as sts:
        assumed = await sts.assume_role(
            RoleArn=role_arn,
            RoleSessionName="GroundworkStackSet",
        )
    creds = assumed["Credentials"]
    return aioboto3.Session(
        aws_access_key_id=creds["AccessKeyId"],
        aws_secret_access_key=creds["SecretAccessKey"],
        aws_session_token=creds["SessionToken"],
        region_name=settings.aws_region,
    )
```

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. pytest tests/unit/services/test_aws.py::TestGetGroundworkSession -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/services/aws.py tests/unit/services/test_aws.py
git commit -m "feat: add get_groundwork_session for Groundwork account role assumption"
```

---

### Task 4: Add `ensure_bootstrap_stackset()` Function

**Files:**
- Modify: `backend/services/aws.py`
- Modify: `tests/unit/services/test_aws.py`

Idempotent function that creates the StackSet if it doesn't exist and deploys initial stack instances to the org root.

**Step 1: Write the failing tests**

```python
# tests/unit/services/test_aws.py — add these
from pathlib import Path
from botocore.exceptions import ClientError

STACKSET_NAME = "groundwork-bootstrap"

class TestEnsureBootstrapStackset:
    async def test_creates_stackset_when_not_exists(self):
        """When the StackSet doesn't exist, create it and deploy to org root."""
        _, cfn_stubber = await create_stubbed_client("cloudformation")

        # describe_stack_set raises StackSetNotFoundException
        cfn_stubber.add_client_error(
            "describe_stack_set",
            service_error_code="StackSetNotFoundException",
            service_message="StackSet not found",
        )
        cfn_stubber.add_response("create_stack_set", {"StackSetId": "ss-123"})
        cfn_stubber.add_response(
            "create_stack_instances", {"OperationId": "op-abc"}
        )
        cfn_stubber.activate()

        mock_gw_session = _stubbed_session({"cloudformation": cfn_stubber})

        with (
            patch.object(aws, "get_groundwork_session", new_callable=AsyncMock) as mock_gw,
            patch.object(aws, "get_oidc_thumbprint", new_callable=AsyncMock) as mock_thumb,
            patch.object(settings, "oidc_issuer_url", "https://idp.example.com"),
            patch.object(settings, "oidc_client_id", "gw-client"),
            patch.object(settings, "aws_groundwork_account_id", "222233334444"),
            patch.object(settings, "admin_role_name", "GroundworkAdmin-DO-NOT-DELETE"),
            patch.object(settings, "aws_region", "us-east-1"),
            patch.object(settings, "aws_org_root_id", "r-abc1"),
        ):
            mock_gw.return_value = mock_gw_session
            mock_thumb.return_value = "a" * 40

            await aws.ensure_bootstrap_stackset()

        cfn_stubber.assert_no_pending_responses()

    async def test_noop_when_stackset_exists(self):
        """When the StackSet already exists, do nothing."""
        _, cfn_stubber = await create_stubbed_client("cloudformation")
        cfn_stubber.add_response(
            "describe_stack_set",
            {
                "StackSet": {
                    "StackSetName": STACKSET_NAME,
                    "StackSetId": "ss-123",
                    "Status": "ACTIVE",
                }
            },
        )
        cfn_stubber.activate()

        mock_gw_session = _stubbed_session({"cloudformation": cfn_stubber})

        with (
            patch.object(aws, "get_groundwork_session", new_callable=AsyncMock) as mock_gw,
        ):
            mock_gw.return_value = mock_gw_session
            await aws.ensure_bootstrap_stackset()

        cfn_stubber.assert_no_pending_responses()
```

**Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=. pytest tests/unit/services/test_aws.py::TestEnsureBootstrapStackset -v`
Expected: FAIL — function doesn't exist

**Step 3: Write implementation**

Add a module-level constant and the function to `backend/services/aws.py`:

```python
from pathlib import Path

BOOTSTRAP_STACKSET_NAME = "groundwork-bootstrap"
_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"


async def ensure_bootstrap_stackset() -> None:
    """Create the bootstrap StackSet if it doesn't exist.

    Uses service-managed permissions with auto-deploy enabled, targeting
    the entire organization. Idempotent — skips creation if the StackSet
    already exists.
    """
    gw_session = await get_groundwork_session()

    async with gw_session.client("cloudformation") as cfn:
        # Check if StackSet already exists
        try:
            await cfn.describe_stack_set(
                StackSetName=BOOTSTRAP_STACKSET_NAME,
                CallAs="DELEGATED_ADMIN",
            )
            logger.info("Bootstrap StackSet already exists, skipping creation")
            return
        except cfn.exceptions.StackSetNotFoundException:
            pass

        # Compute thumbprint and read template
        thumbprint = await get_oidc_thumbprint(settings.oidc_issuer_url)
        template_body = (_TEMPLATE_DIR / "bootstrap_stackset.yaml").read_text()

        # Create the StackSet
        await cfn.create_stack_set(
            StackSetName=BOOTSTRAP_STACKSET_NAME,
            Description="Groundwork bootstrap — OIDC provider and admin role",
            TemplateBody=template_body,
            Parameters=[
                {"ParameterKey": "OidcIssuerUrl", "ParameterValue": settings.oidc_issuer_url},
                {"ParameterKey": "OidcClientId", "ParameterValue": settings.oidc_client_id},
                {"ParameterKey": "OidcThumbprint", "ParameterValue": thumbprint},
                {
                    "ParameterKey": "GroundworkAccountId",
                    "ParameterValue": settings.aws_groundwork_account_id,
                },
                {"ParameterKey": "AdminRoleName", "ParameterValue": settings.admin_role_name},
            ],
            PermissionModel="SERVICE_MANAGED",
            AutoDeployment={"Enabled": True, "RetainStacksOnAccountRemoval": False},
            CallAs="DELEGATED_ADMIN",
        )

        # Deploy to all existing accounts in the organization
        await cfn.create_stack_instances(
            StackSetName=BOOTSTRAP_STACKSET_NAME,
            DeploymentTargets={"OrganizationalUnitIds": [settings.aws_org_root_id]},
            Regions=[settings.aws_region],
            CallAs="DELEGATED_ADMIN",
        )
        logger.info("Created bootstrap StackSet and deployed to org root")
```

Note: The `cfn.exceptions.StackSetNotFoundException` pattern requires botocore exceptions. The test uses `add_client_error` to simulate this. In the implementation, catch `ClientError` and check the error code instead:

```python
        from botocore.exceptions import ClientError

        try:
            await cfn.describe_stack_set(
                StackSetName=BOOTSTRAP_STACKSET_NAME,
                CallAs="DELEGATED_ADMIN",
            )
            logger.info("Bootstrap StackSet already exists, skipping creation")
            return
        except ClientError as e:
            if e.response["Error"]["Code"] != "StackSetNotFoundException":
                raise
```

**Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=. pytest tests/unit/services/test_aws.py::TestEnsureBootstrapStackset -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/services/aws.py backend/templates/ tests/unit/services/test_aws.py
git commit -m "feat: add ensure_bootstrap_stackset with service-managed auto-deploy"
```

---

### Task 5: Add `get_stack_instance_status()` Function

**Files:**
- Modify: `backend/services/aws.py`
- Modify: `tests/unit/services/test_aws.py`

Checks whether a StackSet instance has been deployed to a specific account.

**Step 1: Write the failing tests**

```python
class TestGetStackInstanceStatus:
    async def test_returns_succeeded_when_current(self):
        _, cfn_stubber = await create_stubbed_client("cloudformation")
        cfn_stubber.add_response(
            "describe_stack_instance",
            {
                "StackInstance": {
                    "StackSetId": "ss-123",
                    "Account": "123456789012",
                    "Region": "us-east-1",
                    "Status": "CURRENT",
                    "StackInstanceStatus": {"DetailedStatus": "SUCCEEDED"},
                }
            },
        )
        cfn_stubber.activate()
        mock_gw_session = _stubbed_session({"cloudformation": cfn_stubber})

        with (
            patch.object(aws, "get_groundwork_session", new_callable=AsyncMock) as mock_gw,
            patch.object(settings, "aws_region", "us-east-1"),
        ):
            mock_gw.return_value = mock_gw_session
            result = await aws.get_stack_instance_status("123456789012")

        assert result["status"] == "CURRENT"
        assert result["detailed_status"] == "SUCCEEDED"
        assert result["deployed"] is True

    async def test_returns_not_found_when_instance_missing(self):
        _, cfn_stubber = await create_stubbed_client("cloudformation")
        cfn_stubber.add_client_error(
            "describe_stack_instance",
            service_error_code="StackInstanceNotFoundException",
            service_message="Instance not found",
        )
        cfn_stubber.activate()
        mock_gw_session = _stubbed_session({"cloudformation": cfn_stubber})

        with (
            patch.object(aws, "get_groundwork_session", new_callable=AsyncMock) as mock_gw,
            patch.object(settings, "aws_region", "us-east-1"),
        ):
            mock_gw.return_value = mock_gw_session
            result = await aws.get_stack_instance_status("123456789012")

        assert result["deployed"] is False
        assert result["status"] == "NOT_FOUND"

    async def test_returns_pending_when_running(self):
        _, cfn_stubber = await create_stubbed_client("cloudformation")
        cfn_stubber.add_response(
            "describe_stack_instance",
            {
                "StackInstance": {
                    "StackSetId": "ss-123",
                    "Account": "123456789012",
                    "Region": "us-east-1",
                    "Status": "OUTDATED",
                    "StackInstanceStatus": {"DetailedStatus": "RUNNING"},
                }
            },
        )
        cfn_stubber.activate()
        mock_gw_session = _stubbed_session({"cloudformation": cfn_stubber})

        with (
            patch.object(aws, "get_groundwork_session", new_callable=AsyncMock) as mock_gw,
            patch.object(settings, "aws_region", "us-east-1"),
        ):
            mock_gw.return_value = mock_gw_session
            result = await aws.get_stack_instance_status("123456789012")

        assert result["deployed"] is False
        assert result["detailed_status"] == "RUNNING"
```

**Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=. pytest tests/unit/services/test_aws.py::TestGetStackInstanceStatus -v`
Expected: FAIL — function doesn't exist

**Step 3: Write implementation**

```python
async def get_stack_instance_status(aws_account_id: str) -> dict:
    """Check whether the bootstrap StackSet has deployed to an account.

    Returns dict with:
    - deployed: bool — True if stack instance is CURRENT + SUCCEEDED
    - status: str — CURRENT, OUTDATED, INOPERABLE, or NOT_FOUND
    - detailed_status: str — SUCCEEDED, PENDING, RUNNING, FAILED, etc.
    """
    from botocore.exceptions import ClientError

    gw_session = await get_groundwork_session()
    async with gw_session.client("cloudformation") as cfn:
        try:
            resp = await cfn.describe_stack_instance(
                StackSetName=BOOTSTRAP_STACKSET_NAME,
                StackInstanceAccount=aws_account_id,
                StackInstanceRegion=settings.aws_region,
                CallAs="DELEGATED_ADMIN",
            )
        except ClientError as e:
            if e.response["Error"]["Code"] == "StackInstanceNotFoundException":
                return {"deployed": False, "status": "NOT_FOUND", "detailed_status": "NOT_FOUND"}
            raise

        instance = resp["StackInstance"]
        status = instance.get("Status", "UNKNOWN")
        detailed = instance.get("StackInstanceStatus", {}).get("DetailedStatus", "UNKNOWN")
        deployed = status == "CURRENT" and detailed == "SUCCEEDED"

        return {"deployed": deployed, "status": status, "detailed_status": detailed}
```

**Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=. pytest tests/unit/services/test_aws.py::TestGetStackInstanceStatus -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/services/aws.py tests/unit/services/test_aws.py
git commit -m "feat: add get_stack_instance_status for polling StackSet deployments"
```

---

### Task 6: Add `deploy_to_account()` Function

**Files:**
- Modify: `backend/services/aws.py`
- Modify: `tests/unit/services/test_aws.py`

Manual trigger to deploy the StackSet to a specific account (for existing accounts or retry).

**Step 1: Write the failing test**

```python
class TestDeployToAccount:
    async def test_creates_stack_instance_for_account(self):
        _, cfn_stubber = await create_stubbed_client("cloudformation")
        cfn_stubber.add_response(
            "create_stack_instances",
            {"OperationId": "op-manual-123"},
        )
        cfn_stubber.activate()
        mock_gw_session = _stubbed_session({"cloudformation": cfn_stubber})

        with (
            patch.object(aws, "get_groundwork_session", new_callable=AsyncMock) as mock_gw,
            patch.object(settings, "aws_region", "us-east-1"),
        ):
            mock_gw.return_value = mock_gw_session
            op_id = await aws.deploy_to_account("123456789012", "ou-abc1-12345678")

        assert op_id == "op-manual-123"
        cfn_stubber.assert_no_pending_responses()
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest tests/unit/services/test_aws.py::TestDeployToAccount -v`
Expected: FAIL

**Step 3: Write implementation**

```python
async def deploy_to_account(aws_account_id: str, ou_id: str) -> str:
    """Manually deploy the bootstrap StackSet to a specific account.

    Uses INTERSECTION filter to target a single account within its OU.
    Returns the StackSet operation ID for tracking.
    """
    gw_session = await get_groundwork_session()
    async with gw_session.client("cloudformation") as cfn:
        resp = await cfn.create_stack_instances(
            StackSetName=BOOTSTRAP_STACKSET_NAME,
            DeploymentTargets={
                "OrganizationalUnitIds": [ou_id],
                "AccountFilterType": "INTERSECTION",
                "Accounts": [aws_account_id],
            },
            Regions=[settings.aws_region],
            CallAs="DELEGATED_ADMIN",
        )
    op_id = resp["OperationId"]
    logger.info("Triggered manual deploy to account %s: operation=%s", aws_account_id, op_id)
    return op_id
```

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. pytest tests/unit/services/test_aws.py::TestDeployToAccount -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/services/aws.py tests/unit/services/test_aws.py
git commit -m "feat: add deploy_to_account for manual StackSet deployment"
```

---

### Task 7: Replace `bootstrap_account()` with StackSet-Based Implementation

**Files:**
- Modify: `backend/services/aws.py`
- Modify: `tests/unit/services/test_aws.py`

Replace direct IAM API calls with StackSet polling. The OIDC and admin role ARNs are computed deterministically from the known inputs (no need to query stack outputs).

**Step 1: Write the failing test for the new implementation**

```python
class TestBootstrapAccountStackSet:
    async def test_bootstrap_polls_until_deployed(self):
        """bootstrap_account() polls get_stack_instance_status until deployed."""
        call_count = 0

        async def mock_get_status(account_id):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return {"deployed": False, "status": "OUTDATED", "detailed_status": "RUNNING"}
            return {"deployed": True, "status": "CURRENT", "detailed_status": "SUCCEEDED"}

        with (
            patch.object(aws, "ensure_bootstrap_stackset", new_callable=AsyncMock),
            patch.object(aws, "get_stack_instance_status", side_effect=mock_get_status),
            patch("backend.services.aws.asyncio.sleep", new_callable=AsyncMock),
            patch.object(settings, "oidc_issuer_url", "https://idp.example.com"),
            patch.object(settings, "admin_role_name", "GroundworkAdmin-DO-NOT-DELETE"),
        ):
            result = await aws.bootstrap_account("123456789012")

        assert result["oidc_provider_arn"] == (
            "arn:aws:iam::123456789012:oidc-provider/idp.example.com"
        )
        assert result["admin_role_arn"] == (
            "arn:aws:iam::123456789012:role/GroundworkAdmin-DO-NOT-DELETE"
        )
        assert call_count == 3

    async def test_bootstrap_triggers_deploy_when_not_found(self):
        """If stack instance is NOT_FOUND, triggers manual deploy then polls."""
        first_call = True

        async def mock_get_status(account_id):
            nonlocal first_call
            if first_call:
                first_call = False
                return {"deployed": False, "status": "NOT_FOUND", "detailed_status": "NOT_FOUND"}
            return {"deployed": True, "status": "CURRENT", "detailed_status": "SUCCEEDED"}

        with (
            patch.object(aws, "ensure_bootstrap_stackset", new_callable=AsyncMock),
            patch.object(aws, "get_stack_instance_status", side_effect=mock_get_status),
            patch.object(aws, "deploy_to_account", new_callable=AsyncMock) as mock_deploy,
            patch("backend.services.aws.asyncio.sleep", new_callable=AsyncMock),
            patch.object(settings, "oidc_issuer_url", "https://idp.example.com"),
            patch.object(settings, "admin_role_name", "GroundworkAdmin-DO-NOT-DELETE"),
        ):
            mock_deploy.return_value = "op-123"
            result = await aws.bootstrap_account("123456789012", ou_id="ou-abc1")

        mock_deploy.assert_called_once_with("123456789012", "ou-abc1")
        assert result["oidc_provider_arn"] is not None

    async def test_bootstrap_times_out(self):
        """Raises RuntimeError if stack never deploys within timeout."""
        async def mock_get_status(account_id):
            return {"deployed": False, "status": "OUTDATED", "detailed_status": "RUNNING"}

        with (
            patch.object(aws, "ensure_bootstrap_stackset", new_callable=AsyncMock),
            patch.object(aws, "get_stack_instance_status", side_effect=mock_get_status),
            patch("backend.services.aws.asyncio.sleep", new_callable=AsyncMock),
            patch.object(settings, "oidc_issuer_url", "https://idp.example.com"),
            patch.object(settings, "admin_role_name", "GroundworkAdmin-DO-NOT-DELETE"),
        ):
            with pytest.raises(RuntimeError, match="timed out"):
                await aws.bootstrap_account("123456789012")

    async def test_bootstrap_fails_on_stack_failure(self):
        """Raises RuntimeError if stack instance reports FAILED."""
        async def mock_get_status(account_id):
            return {"deployed": False, "status": "INOPERABLE", "detailed_status": "FAILED"}

        with (
            patch.object(aws, "ensure_bootstrap_stackset", new_callable=AsyncMock),
            patch.object(aws, "get_stack_instance_status", side_effect=mock_get_status),
            patch("backend.services.aws.asyncio.sleep", new_callable=AsyncMock),
            patch.object(settings, "oidc_issuer_url", "https://idp.example.com"),
            patch.object(settings, "admin_role_name", "GroundworkAdmin-DO-NOT-DELETE"),
        ):
            with pytest.raises(RuntimeError, match="failed"):
                await aws.bootstrap_account("123456789012")
```

**Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=. pytest tests/unit/services/test_aws.py::TestBootstrapAccountStackSet -v`
Expected: FAIL — new bootstrap_account signature/behavior doesn't match

**Step 3: Replace the implementation**

Replace the existing `bootstrap_account` function in `backend/services/aws.py`:

```python
import asyncio
from urllib.parse import urlparse

BOOTSTRAP_POLL_INTERVAL_SECONDS = 30
BOOTSTRAP_POLL_TIMEOUT_SECONDS = 15 * 60  # 15 minutes


async def bootstrap_account(aws_account_id: str, ou_id: str | None = None) -> dict:
    """Bootstrap a new account via StackSet deployment.

    Ensures the bootstrap StackSet exists, then polls until the stack
    instance is deployed to the target account. If the instance is not
    found and ou_id is provided, triggers a manual deployment.

    Returns dict with oidc_provider_arn and admin_role_arn.
    """
    await ensure_bootstrap_stackset()

    elapsed = 0
    deploy_triggered = False

    while elapsed < BOOTSTRAP_POLL_TIMEOUT_SECONDS:
        status = await get_stack_instance_status(aws_account_id)

        if status["deployed"]:
            break

        if status["detailed_status"] == "FAILED":
            raise RuntimeError(
                f"Bootstrap stack deployment failed for account {aws_account_id}"
            )

        # If instance doesn't exist yet, trigger manual deploy
        if status["status"] == "NOT_FOUND" and ou_id and not deploy_triggered:
            await deploy_to_account(aws_account_id, ou_id)
            deploy_triggered = True

        await asyncio.sleep(BOOTSTRAP_POLL_INTERVAL_SECONDS)
        elapsed += BOOTSTRAP_POLL_INTERVAL_SECONDS
    else:
        raise RuntimeError(
            f"Bootstrap stack deployment timed out for account {aws_account_id}"
        )

    # Compute ARNs deterministically from known inputs
    issuer_host = urlparse(settings.oidc_issuer_url).hostname
    oidc_provider_arn = f"arn:aws:iam::{aws_account_id}:oidc-provider/{issuer_host}"
    admin_role_arn = f"arn:aws:iam::{aws_account_id}:role/{settings.admin_role_name}"

    logger.info(
        "Bootstrap complete for account %s: oidc=%s role=%s",
        aws_account_id,
        oidc_provider_arn,
        admin_role_arn,
    )
    return {
        "oidc_provider_arn": oidc_provider_arn,
        "admin_role_arn": admin_role_arn,
    }
```

**Step 4: Run new tests to verify they pass**

Run: `PYTHONPATH=. pytest tests/unit/services/test_aws.py::TestBootstrapAccountStackSet -v`
Expected: PASS

**Step 5: Update or remove old `TestBootstrapAccount` test class**

The old `TestBootstrapAccount` test that mocks STS + IAM for direct API calls is now obsolete. Remove it. The `test_bootstrap_creates_oidc_and_role` test tested the old implementation.

**Step 6: Run all aws tests to verify nothing is broken**

Run: `PYTHONPATH=. pytest tests/unit/services/test_aws.py -v`
Expected: PASS (old test removed, new tests pass)

**Step 7: Commit**

```bash
git add backend/services/aws.py tests/unit/services/test_aws.py
git commit -m "feat: replace bootstrap_account with StackSet-based implementation"
```

---

### Task 8: Update `assume_groundwork_admin()` to Chain Through Groundwork Account

**Files:**
- Modify: `backend/services/aws.py`
- Modify: `tests/unit/services/test_aws.py`

Since the GroundworkAdmin role now trusts the Groundwork account (not the management account), role assumption must originate from the Groundwork account context.

**Step 1: Write the failing test**

```python
class TestAssumeGroundworkAdminViaGW:
    async def test_chains_through_groundwork_account(self):
        """assume_groundwork_admin uses get_groundwork_session as base."""
        _, sts_stubber = await create_stubbed_client("sts")
        sts_stubber.add_response(
            "assume_role",
            {
                "Credentials": {
                    "AccessKeyId": "AKIATARGET",
                    "SecretAccessKey": "secretTARGET",
                    "SessionToken": "tokenTARGET",
                    "Expiration": datetime(2025, 1, 1),
                },
                "AssumedRoleUser": {
                    "AssumedRoleId": "AROATARGET:GroundworkRoleMgmt",
                    "Arn": "arn:aws:sts::123456789012:assumed-role/GroundworkAdmin/GroundworkRoleMgmt",
                },
            },
            expected_params={
                "RoleArn": "arn:aws:iam::123456789012:role/GroundworkAdmin-DO-NOT-DELETE",
                "RoleSessionName": "GroundworkRoleMgmt",
            },
        )
        sts_stubber.activate()

        gw_session = _stubbed_session({"sts": sts_stubber})

        with (
            patch.object(aws, "get_groundwork_session", new_callable=AsyncMock) as mock_gw,
            patch("backend.services.aws.aioboto3") as mock_aioboto3,
            patch.object(settings, "admin_role_name", "GroundworkAdmin-DO-NOT-DELETE"),
        ):
            mock_gw.return_value = gw_session
            session = await aws.assume_groundwork_admin("123456789012")

        mock_gw.assert_called_once()
        mock_aioboto3.Session.assert_called_once()
        call_kwargs = mock_aioboto3.Session.call_args[1]
        assert call_kwargs["aws_access_key_id"] == "AKIATARGET"
        sts_stubber.assert_no_pending_responses()
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest tests/unit/services/test_aws.py::TestAssumeGroundworkAdminViaGW -v`
Expected: FAIL — still uses `get_session()` instead of `get_groundwork_session()`

**Step 3: Update implementation**

Change `assume_groundwork_admin` in `backend/services/aws.py`:

```python
async def assume_groundwork_admin(aws_account_id: str) -> aioboto3.Session:
    """Assume the admin management role in a target account.

    Chains through the Groundwork account (since the admin role trusts
    the Groundwork account, not the management account).
    Returns an aioboto3 Session configured with the temporary credentials.
    """
    gw_session = await get_groundwork_session()
    role_arn = f"arn:aws:iam::{aws_account_id}:role/{settings.admin_role_name}"
    async with gw_session.client("sts") as sts:
        assumed = await sts.assume_role(
            RoleArn=role_arn,
            RoleSessionName="GroundworkRoleMgmt",
        )
    creds = assumed["Credentials"]
    return aioboto3.Session(
        aws_access_key_id=creds["AccessKeyId"],
        aws_secret_access_key=creds["SecretAccessKey"],
        aws_session_token=creds["SessionToken"],
        region_name=settings.aws_region,
    )
```

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. pytest tests/unit/services/test_aws.py::TestAssumeGroundworkAdminViaGW -v`
Expected: PASS

**Step 5: Remove old assume_groundwork_admin tests that assumed management account**

Check if any existing tests for `assume_groundwork_admin` exist and update them.

**Step 6: Commit**

```bash
git add backend/services/aws.py tests/unit/services/test_aws.py
git commit -m "feat: chain assume_groundwork_admin through Groundwork account"
```

---

### Task 9: Update `run_provision_account()` to Pass OU ID

**Files:**
- Modify: `backend/services/jobs.py`
- Modify: `tests/unit/services/test_jobs.py`

The new `bootstrap_account()` accepts an optional `ou_id` for manual deploy trigger. The provisioning job should pass it.

**Step 1: Write the failing test**

```python
# tests/unit/services/test_jobs.py — update TestProvisionJobSuccess
class TestProvisionJobSuccess:
    async def test_full_provisioning_pipeline(self, db_session):
        """Provisioning passes ou_id to bootstrap_account."""
        user = await _create_user(db_session)

        account = Account(
            account_name="Provision Test",
            account_email=f"prov-{id(db_session)}@example.com",
            organizational_unit="ou-1234",
            sso_user_email="sso@example.com",
            status="pending",
            created_by=user.id,
        )
        db_session.add(account)
        await db_session.flush()

        job = Job(
            account_id=account.id,
            job_type="provision_account",
            status="pending",
            started_by=user.id,
        )
        db_session.add(job)
        await db_session.flush()

        with (
            patch(
                "backend.services.jobs.aws.create_account",
                new_callable=AsyncMock,
                return_value="car-abc123",
            ),
            patch(
                "backend.services.jobs.aws.poll_account_creation",
                new_callable=AsyncMock,
                return_value={"status": "SUCCEEDED", "aws_account_id": "123456789012"},
            ),
            patch(
                "backend.services.jobs.aws.move_account_to_ou",
                new_callable=AsyncMock,
            ),
            patch(
                "backend.services.jobs.aws.bootstrap_account",
                new_callable=AsyncMock,
                return_value={
                    "oidc_provider_arn": "arn:aws:iam::123456789012:oidc-provider/ex",
                    "admin_role_arn": "arn:aws:iam::123456789012:role/GWAdmin",
                },
            ) as mock_bootstrap,
            patch("backend.services.jobs.asyncio.sleep", new_callable=AsyncMock),
        ):
            await run_provision_account(job, db_session)

        # Verify bootstrap_account was called with ou_id
        mock_bootstrap.assert_called_once_with(
            "123456789012", ou_id="ou-1234"
        )

        await db_session.refresh(account)
        await db_session.refresh(job)

        assert account.status == "active"
        assert account.aws_account_id == "123456789012"
        assert account.oidc_provider_arn is not None
        assert job.status == "completed"
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest tests/unit/services/test_jobs.py::TestProvisionJobSuccess -v`
Expected: FAIL — `bootstrap_account` called without `ou_id`

**Step 3: Update implementation**

In `backend/services/jobs.py`, change the bootstrap call in `run_provision_account()`:

```python
        # Step 4: Bootstrap
        bootstrap_result = await aws.bootstrap_account(
            account.aws_account_id, ou_id=account.organizational_unit
        )
```

This is a one-line change in the existing function.

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. pytest tests/unit/services/test_jobs.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/services/jobs.py tests/unit/services/test_jobs.py
git commit -m "feat: pass ou_id to bootstrap_account in provisioning job"
```

---

### Task 10: Update Test Fixtures and Clean Up

**Files:**
- Modify: `tests/fixtures/aws.py`
- Modify: `tests/unit/services/test_aws.py`
- Modify: `backend/services/aws.py` (remove dead code if any)

**Step 1: Update `mock_aws_bootstrap_account` fixture**

The fixture should still work as-is since it mocks at the function level. Verify the fixture signature matches the updated `bootstrap_account(aws_account_id, ou_id=None)`.

```python
# tests/fixtures/aws.py — update the mock signature if needed
@pytest.fixture
def mock_aws_bootstrap_account():
    with patch("backend.services.aws.bootstrap_account", new_callable=AsyncMock) as m:
        m.return_value = {
            "oidc_provider_arn": FAKE_OIDC_ARN,
            "admin_role_arn": FAKE_ADMIN_ROLE_ARN,
        }
        yield m
```

This should not require changes since `AsyncMock` accepts any arguments.

**Step 2: Run full test suite**

Run: `PYTHONPATH=. pytest -v`
Expected: ALL PASS

**Step 3: Run linting and formatting**

Run: `black backend/ tests/ && isort backend/ tests/ && flake8 backend/ tests/`
Expected: Clean

**Step 4: Commit**

```bash
git add -A
git commit -m "chore: clean up test fixtures and formatting after StackSet migration"
```

---

### Task 11: Security Review

**Step 1: Run security-focused code review**

Use the `code-reviewer` agent with security focus on:
- Role assumption chain (homelab → Groundwork account → member accounts)
- `CallAs=DELEGATED_ADMIN` usage — verify all StackSet API calls include it
- No credentials leaked in logs or error messages
- Template doesn't grant excessive permissions beyond what's needed
- `AdministratorAccess` on the admin role is intentional (matches existing behavior)
- `RetainStacksOnAccountRemoval: False` — resources cleaned up when account leaves org

**Step 2: Fix any findings**

Address all critical, high, and medium findings before merging.

**Step 3: Final commit if changes made**

```bash
git add -A
git commit -m "fix: address security review findings"
```
