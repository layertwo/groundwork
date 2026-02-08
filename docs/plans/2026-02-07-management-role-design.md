# Add Management Account Role for Organizations API Calls

**Goal:** Organizations delegation policies do not support `CreateAccount` or `MoveAccount`. Add a `get_management_session()` function that assumes a narrowly-scoped role in the management account for all Organizations API calls. StackSet and admin role operations remain on the Groundwork account's default session.

**Architecture:** Two sessions — `get_session()` for Groundwork account operations (StackSets, admin role chaining, STS), and `get_management_session()` for Organizations API calls via an assumed role in the management account. A single config setting `aws_management_role_arn` provides the full ARN of the management account role.

---

## Summary of Changes

| Area | Before (current) | After |
|------|-------------------|-------|
| Organizations calls | `get_session()` (Groundwork account, delegation policy) | `get_management_session()` (assumed role in management account) |
| StackSet calls | `get_session()` | `get_session()` (no change) |
| Admin role chaining | `get_session()` | `get_session()` (no change) |
| Config | No management account reference | `aws_management_role_arn` added |
| Delegation policy docs | Exists | Replaced with management account role docs |

## Code Changes

### `backend/config.py`

Add one setting:

```python
aws_management_role_arn: str = ""
```

### `backend/services/aws.py`

Add `get_management_session()`:

```python
async def get_management_session() -> aioboto3.Session:
    """Assume the Organizations role in the management account."""
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

Update three functions to use it:
- `create_account()` — `session = await get_management_session()`
- `poll_account_creation()` — `session = await get_management_session()`
- `move_account_to_ou()` — `session = await get_management_session()`

### Tests

- Add `TestGetManagementSession` — verify STS assume_role is called with the configured ARN
- Update `TestCreateAccount`, `TestPollAccountCreation`, `TestMoveAccountToOu` to mock `get_management_session` instead of `get_session`

### Docs

- Replace `docs/deployment/delegation-policy.md` with `docs/deployment/aws-setup.md` covering both roles:
  1. Management account role (`GroundworkManagementRole`) — Organizations permissions, trusted by Groundwork account
  2. Groundwork account role — StackSets, STS assume-role for management + member accounts
- Update README to match
- Update CLAUDE.md to describe both sessions

## Management Account Role

### Trust policy

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

## Groundwork Account Role Updates

The Groundwork execution role needs `sts:AssumeRole` for the management role in addition to existing permissions:

```json
{
  "Sid": "AssumeManagementRole",
  "Effect": "Allow",
  "Action": "sts:AssumeRole",
  "Resource": "arn:aws:iam::MANAGEMENT_ACCOUNT_ID:role/GroundworkManagementRole"
}
```
