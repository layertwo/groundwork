"""AWS service layer — all AWS API interactions live here."""

import asyncio
import hashlib
import json
import logging
import ssl
from datetime import datetime
from typing import TypedDict
from urllib.parse import quote, urlparse

import aioboto3
import aiohttp
from botocore.exceptions import ClientError

from backend.config import settings

logger = logging.getLogger(__name__)

_session: aioboto3.Session | None = None


class STSCredentials(TypedDict):
    access_key_id: str
    secret_access_key: str
    session_token: str
    expiration: datetime


def get_session() -> aioboto3.Session:
    """Return a reusable aioboto3 session."""
    global _session
    if _session is None:
        _session = aioboto3.Session(region_name=settings.aws_region)
    return _session


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


async def create_account(account_name: str, account_email: str) -> str:
    """Create an AWS account via Organizations.

    Returns the CreateAccountRequest ID for polling.
    """
    session = await get_management_session()
    async with session.client("organizations") as orgs:
        resp = await orgs.create_account(
            Email=account_email,
            AccountName=account_name,
        )
        request_id = resp["CreateAccountStatus"]["Id"]
        logger.info(
            "Started account creation: request_id=%s name=%s",
            request_id,
            account_name,
        )
        return request_id


async def poll_account_creation(request_id: str) -> dict:
    """Check account creation status via Organizations.

    Returns dict with 'status' (IN_PROGRESS, SUCCEEDED, FAILED)
    and 'aws_account_id' on success or 'error' on failure.
    """
    session = await get_management_session()
    async with session.client("organizations") as orgs:
        resp = await orgs.describe_create_account_status(
            CreateAccountRequestId=request_id,
        )
        status_detail = resp["CreateAccountStatus"]
        state = status_detail["State"]

        result: dict = {"status": state}

        if state == "SUCCEEDED":
            result["aws_account_id"] = status_detail["AccountId"]
        elif state == "FAILED":
            result["error"] = status_detail.get("FailureReason", "Unknown error")

        return result


async def move_account_to_ou(aws_account_id: str, ou: str) -> None:
    """Move a newly created account into the target Organizational Unit."""
    session = await get_management_session()
    async with session.client("organizations") as orgs:
        # List roots to find the root ID (source for new accounts)
        roots_resp = await orgs.list_roots()
        roots = roots_resp.get("Roots", [])
        if not roots:
            raise RuntimeError("No organization root found — check AWS Organizations permissions")
        root_id = roots[0]["Id"]

        await orgs.move_account(
            AccountId=aws_account_id,
            SourceParentId=root_id,
            DestinationParentId=ou,
        )
        logger.info("Moved account %s to OU %s", aws_account_id, ou)


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
            raise RuntimeError(f"Bootstrap stack deployment failed for account {aws_account_id}")

        # If instance doesn't exist yet, trigger manual deploy
        if status["status"] == "NOT_FOUND" and ou_id and not deploy_triggered:
            await deploy_to_account(aws_account_id, ou_id)
            deploy_triggered = True

        await asyncio.sleep(BOOTSTRAP_POLL_INTERVAL_SECONDS)
        elapsed += BOOTSTRAP_POLL_INTERVAL_SECONDS
    else:
        raise RuntimeError(f"Bootstrap stack deployment timed out for account {aws_account_id}")

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


async def get_oidc_thumbprint(issuer_url: str) -> str:
    """Fetch the TLS certificate thumbprint for an OIDC issuer.

    AWS requires this for create_open_id_connect_provider.
    """
    parsed = urlparse(issuer_url)
    if parsed.scheme != "https":
        raise ValueError("OIDC issuer must use HTTPS")
    if not parsed.hostname:
        raise ValueError("OIDC issuer URL has no hostname")
    hostname = parsed.hostname
    port = parsed.port or 443

    ctx = ssl.create_default_context()
    der_cert = await _fetch_server_cert(hostname, port, ctx)

    thumbprint = hashlib.sha1(der_cert).hexdigest()  # noqa: S324
    return thumbprint


async def _fetch_server_cert(hostname: str, port: int, ctx: ssl.SSLContext) -> bytes:
    """Connect to host and return DER-encoded server certificate."""
    reader, writer = await asyncio.open_connection(hostname, port, ssl=ctx)
    ssl_object = writer.transport.get_extra_info("ssl_object")
    der_cert = ssl_object.getpeercert(binary_form=True)
    writer.close()
    await writer.wait_closed()
    return der_cert


# ---------------------------------------------------------------------------
# IAM role management (Phase 3)
# ---------------------------------------------------------------------------


async def assume_groundwork_admin(aws_account_id: str) -> aioboto3.Session:
    """Assume the admin management role in a target account.

    Returns an aioboto3 Session configured with the temporary credentials.
    """
    session = get_session()
    role_arn = f"arn:aws:iam::{aws_account_id}:role/{settings.admin_role_name}"
    async with session.client("sts") as sts:
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


def _build_trust_policy(
    oidc_provider_arn: str,
    allowed_groups: list[str],
    allowed_users: list[str],
) -> str:
    """Build an IAM trust policy for OIDC federation.

    Creates up to two statements: one for group-based access and one for
    user-based access. Each is gated on the ``aud`` claim matching the
    configured OIDC client ID.
    """
    # Extract issuer host from the OIDC provider ARN
    # ARN format: arn:aws:iam::<account>:oidc-provider/<issuer_host>
    issuer = oidc_provider_arn.split(":oidc-provider/", 1)[1]

    statements: list[dict] = []

    if allowed_groups:
        statements.append(
            {
                "Sid": "AllowGroupAccess",
                "Effect": "Allow",
                "Principal": {"Federated": oidc_provider_arn},
                "Action": "sts:AssumeRoleWithWebIdentity",
                "Condition": {
                    "StringEquals": {
                        f"{issuer}:aud": settings.oidc_client_id,
                    },
                    "ForAnyValue:StringEquals": {
                        f"{issuer}:groups": allowed_groups,
                    },
                },
            }
        )

    if allowed_users:
        statements.append(
            {
                "Sid": "AllowUserAccess",
                "Effect": "Allow",
                "Principal": {"Federated": oidc_provider_arn},
                "Action": "sts:AssumeRoleWithWebIdentity",
                "Condition": {
                    "StringEquals": {
                        f"{issuer}:aud": settings.oidc_client_id,
                        f"{issuer}:sub": allowed_users,
                    },
                },
            }
        )

    policy = {"Version": "2012-10-17", "Statement": statements}
    return json.dumps(policy)


async def create_iam_role(
    aws_account_id: str,
    role_name: str,
    oidc_provider_arn: str,
    allowed_groups: list[str],
    allowed_users: list[str],
    managed_policy_arns: list[str],
    inline_policy: dict | None,
    max_duration: int,
) -> str:
    """Create an IAM role in the target account with OIDC trust policy.

    Returns the role ARN.
    """
    target_session = await assume_groundwork_admin(aws_account_id)
    trust_policy = _build_trust_policy(oidc_provider_arn, allowed_groups, allowed_users)

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


async def update_iam_role(
    aws_account_id: str,
    role_name: str,
    oidc_provider_arn: str,
    changes: dict,
) -> None:
    """Update an IAM role in the target account.

    ``changes`` is a dict of field names to new values. Only fields present
    in the dict are updated. When updating trust policy fields, the caller
    must include both ``allowed_groups`` and ``allowed_users`` (with their
    full current values) to avoid losing existing access.
    """
    target_session = await assume_groundwork_admin(aws_account_id)

    async with target_session.client("iam") as iam:
        # Trust policy update if groups or users changed
        if "allowed_groups" in changes or "allowed_users" in changes:
            if "allowed_groups" not in changes or "allowed_users" not in changes:
                raise ValueError(
                    "Both allowed_groups and allowed_users must be provided "
                    "when updating trust policy"
                )
            trust_policy = _build_trust_policy(
                oidc_provider_arn,
                changes["allowed_groups"],
                changes["allowed_users"],
            )
            await iam.update_assume_role_policy(
                RoleName=role_name,
                PolicyDocument=trust_policy,
            )

        # Max session duration (derived from the larger of api/console duration)
        if "api_session_duration" in changes or "console_session_duration" in changes:
            max_dur = max(
                changes.get("api_session_duration", 900),
                changes.get("console_session_duration", 3600),
            )
            await iam.update_role(RoleName=role_name, MaxSessionDuration=max_dur)

        # Managed policies
        if "managed_policy_arns" in changes:
            # Detach all existing managed policies
            paginator = iam.get_paginator("list_attached_role_policies")
            async for page in paginator.paginate(RoleName=role_name):
                for policy in page.get("AttachedPolicies", []):
                    await iam.detach_role_policy(RoleName=role_name, PolicyArn=policy["PolicyArn"])
            # Attach new ones
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


async def delete_iam_role(aws_account_id: str, role_name: str) -> None:
    """Delete an IAM role from the target account.

    Detaches all managed policies and deletes inline policies first.
    """
    target_session = await assume_groundwork_admin(aws_account_id)

    async with target_session.client("iam") as iam:
        # Detach managed policies
        paginator = iam.get_paginator("list_attached_role_policies")
        async for page in paginator.paginate(RoleName=role_name):
            for policy in page.get("AttachedPolicies", []):
                await iam.detach_role_policy(RoleName=role_name, PolicyArn=policy["PolicyArn"])

        # Delete inline policies
        paginator = iam.get_paginator("list_role_policies")
        async for page in paginator.paginate(RoleName=role_name):
            for policy_name in page.get("PolicyNames", []):
                await iam.delete_role_policy(RoleName=role_name, PolicyName=policy_name)

        await iam.delete_role(RoleName=role_name)

    logger.info("Deleted IAM role %s from account %s", role_name, aws_account_id)


# ---------------------------------------------------------------------------
# Role assumption (Phase 4)
# ---------------------------------------------------------------------------


async def assume_role_with_web_identity(
    role_arn: str,
    id_token: str,
    session_duration: int,
    session_name: str,
) -> STSCredentials:
    """Assume an IAM role using an OIDC id_token via STS.

    Returns STSCredentials with access_key_id, secret_access_key,
    session_token, and expiration.
    """
    session = get_session()
    async with session.client("sts") as sts:
        resp = await sts.assume_role_with_web_identity(
            RoleArn=role_arn,
            RoleSessionName=session_name,
            WebIdentityToken=id_token,
            DurationSeconds=session_duration,
        )
    creds = resp["Credentials"]
    return STSCredentials(
        access_key_id=creds["AccessKeyId"],
        secret_access_key=creds["SecretAccessKey"],
        session_token=creds["SessionToken"],
        expiration=creds["Expiration"],
    )


async def get_console_url(
    credentials: STSCredentials,
    console_session_duration: int,
    issuer: str,
) -> str:
    """Build an AWS Console federation login URL from temporary credentials.

    Calls the AWS federation endpoint to obtain a signin token, then constructs
    a login URL that grants console access.
    """
    session_json = json.dumps(
        {
            "sessionId": credentials["access_key_id"],
            "sessionKey": credentials["secret_access_key"],
            "sessionToken": credentials["session_token"],
        }
    )

    federation_url = "https://signin.aws.amazon.com/federation"

    # Step 1: Get signin token
    async with aiohttp.ClientSession() as http:
        async with http.get(
            federation_url,
            params={
                "Action": "getSigninToken",
                "SessionDuration": str(console_session_duration),
                "Session": session_json,
            },
        ) as resp:
            resp.raise_for_status()
            data = await resp.json(content_type=None)
            signin_token = data["SigninToken"]

    # Step 2: Construct login URL
    login_url = (
        f"{federation_url}"
        f"?Action=login"
        f"&Issuer={quote(issuer, safe='')}"
        f"&Destination={quote('https://console.aws.amazon.com/', safe='')}"
        f"&SigninToken={quote(signin_token, safe='')}"
    )

    return login_url


# ---------------------------------------------------------------------------
# StackSet bootstrap (Phase 2)
# ---------------------------------------------------------------------------

BOOTSTRAP_STACKSET_NAME = "groundwork-bootstrap"
BOOTSTRAP_POLL_INTERVAL_SECONDS = 30
BOOTSTRAP_POLL_TIMEOUT_SECONDS = 15 * 60  # 15 minutes


async def get_stack_instance_status(aws_account_id: str) -> dict:
    """Check whether the bootstrap StackSet has deployed to an account.

    Returns dict with:
    - deployed: bool — True if stack instance is CURRENT + SUCCEEDED
    - status: str — CURRENT, OUTDATED, INOPERABLE, or NOT_FOUND
    - detailed_status: str — SUCCEEDED, PENDING, RUNNING, FAILED, etc.
    """
    session = get_session()
    async with session.client("cloudformation") as cfn:
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


async def deploy_to_account(aws_account_id: str, ou_id: str) -> str:
    """Manually deploy the bootstrap StackSet to a specific account.

    Uses INTERSECTION filter to target a single account within its OU.
    Returns the StackSet operation ID for tracking.
    """
    session = get_session()
    async with session.client("cloudformation") as cfn:
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


async def ensure_bootstrap_stackset() -> None:
    """Create the bootstrap StackSet if it doesn't exist.

    Uses service-managed permissions with auto-deploy enabled, targeting
    the entire organization. Idempotent — skips creation if the StackSet
    already exists.
    """
    session = get_session()

    async with session.client("cloudformation") as cfn:
        # Check if StackSet already exists
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

        # Compute thumbprint and generate template
        thumbprint = await get_oidc_thumbprint(settings.oidc_issuer_url)
        template_body = _build_bootstrap_template(
            oidc_issuer_url=settings.oidc_issuer_url,
            oidc_client_id=settings.oidc_client_id,
            oidc_thumbprint=thumbprint,
            groundwork_account_id=settings.aws_groundwork_account_id,
            admin_role_name=settings.admin_role_name,
        )

        # Create the StackSet
        await cfn.create_stack_set(
            StackSetName=BOOTSTRAP_STACKSET_NAME,
            Description="Groundwork bootstrap — OIDC provider and admin role",
            TemplateBody=template_body,
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


# ---------------------------------------------------------------------------
# CloudFormation template builder (Phase 2 — StackSet bootstrap)
# ---------------------------------------------------------------------------


def _build_bootstrap_template(
    oidc_issuer_url: str,
    oidc_client_id: str,
    oidc_thumbprint: str,
    groundwork_account_id: str,
    admin_role_name: str = "GroundworkAdmin-DO-NOT-DELETE",
) -> str:
    """Build a CloudFormation template for bootstrapping member accounts.

    Generates a template that creates:
    - An OIDC identity provider pointing at the configured issuer
    - An admin management role trusted by the Groundwork service account

    Returns a JSON string suitable for passing as ``TemplateBody``
    to CloudFormation ``CreateStackSet``.
    """
    template: dict = {
        "AWSTemplateFormatVersion": "2010-09-09",
        "Description": "Groundwork bootstrap — OIDC provider and admin role for member accounts",
        "Resources": {
            "OidcProvider": {
                "Type": "AWS::IAM::OIDCProvider",
                "Properties": {
                    "Url": oidc_issuer_url,
                    "ClientIdList": [oidc_client_id],
                    "ThumbprintList": [oidc_thumbprint],
                },
            },
            "AdminRole": {
                "Type": "AWS::IAM::Role",
                "Properties": {
                    "RoleName": admin_role_name,
                    "Description": "Groundwork admin management role — DO NOT DELETE",
                    "MaxSessionDuration": 3600,
                    "AssumeRolePolicyDocument": {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Effect": "Allow",
                                "Principal": {"AWS": f"arn:aws:iam::{groundwork_account_id}:root"},
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
            "OidcProviderArn": {
                "Description": "ARN of the OIDC identity provider",
                "Value": {"Ref": "OidcProvider"},
            },
            "AdminRoleArn": {
                "Description": "ARN of the Groundwork admin role",
                "Value": {"Fn::GetAtt": ["AdminRole", "Arn"]},
            },
        },
    }
    return json.dumps(template)
