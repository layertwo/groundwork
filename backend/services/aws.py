"""AWS service layer — all AWS API interactions live here."""

import hashlib
import json
import logging
import ssl
from urllib.parse import urlparse

import aioboto3

from backend.config import settings

logger = logging.getLogger(__name__)

_session: aioboto3.Session | None = None


def get_session() -> aioboto3.Session:
    """Return a reusable aioboto3 session."""
    global _session
    if _session is None:
        _session = aioboto3.Session(region_name=settings.aws_region)
    return _session


async def create_account(account_name: str, account_email: str) -> str:
    """Create an AWS account via Organizations.

    Returns the CreateAccountRequest ID for polling.
    """
    session = get_session()
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
    session = get_session()
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
    session = get_session()
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


async def bootstrap_account(aws_account_id: str) -> dict:
    """Bootstrap a new account with OIDC provider and admin management role.

    1. Assume OrganizationAccountAccessRole in the target account
    2. Create OIDC identity provider
    3. Create admin management role with trust policy
    4. Attach AdministratorAccess

    Returns dict with oidc_provider_arn and admin_role_arn.
    """
    session = get_session()

    # Step 1: Assume role in the new account
    role_arn = f"arn:aws:iam::{aws_account_id}:role/OrganizationAccountAccessRole"
    async with session.client("sts") as sts:
        assumed = await sts.assume_role(RoleArn=role_arn, RoleSessionName="GroundworkBootstrap")
    creds = assumed["Credentials"]

    # Step 2–4: Use assumed credentials in the target account
    target_session = aioboto3.Session(
        aws_access_key_id=creds["AccessKeyId"],
        aws_secret_access_key=creds["SecretAccessKey"],
        aws_session_token=creds["SessionToken"],
        region_name=settings.aws_region,
    )

    async with target_session.client("iam") as iam:
        # Step 2: Create OIDC provider
        thumbprint = await get_oidc_thumbprint(settings.oidc_issuer_url)
        oidc_resp = await iam.create_open_id_connect_provider(
            Url=settings.oidc_issuer_url,
            ClientIDList=[settings.oidc_client_id],
            ThumbprintList=[thumbprint],
        )
        oidc_provider_arn = oidc_resp["OpenIDConnectProviderArn"]

        # Step 3: Create admin management role
        mgmt_account_id = settings.aws_management_account_id
        trust_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"AWS": f"arn:aws:iam::{mgmt_account_id}:root"},
                    "Action": "sts:AssumeRole",
                }
            ],
        }
        role_resp = await iam.create_role(
            RoleName=settings.admin_role_name,
            AssumeRolePolicyDocument=json.dumps(trust_policy),
            Description="Groundwork admin management role — DO NOT DELETE",
            MaxSessionDuration=3600,
        )
        admin_role_arn = role_resp["Role"]["Arn"]

        # Step 4: Attach AdministratorAccess
        await iam.attach_role_policy(
            RoleName=settings.admin_role_name,
            PolicyArn="arn:aws:iam::aws:policy/AdministratorAccess",
        )

    logger.info(
        "Bootstrapped account %s: oidc=%s role=%s",
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
    import asyncio

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
                from botocore.exceptions import ClientError

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
