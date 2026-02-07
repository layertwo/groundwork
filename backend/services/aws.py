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
