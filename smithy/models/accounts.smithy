$version: "2.0"

namespace layertwo.groundwork

use aws.protocols#restJson1

/// Groundwork control plane: provisions and manages AWS accounts and IAM roles.
///
/// Operations are added per resource as routes migrate to the generated models.
/// `GET /api/accounts` (bare array response) is not modelled yet: restJson1
/// cannot express a top-level array body without wrapping it in a structure.
@restJson1
@title("Groundwork API")
service Groundwork {
    version: "2026-10-21"
    operations: [CreateAccount, GetAccount, UpdateAccount]
}

@http(method: "POST", uri: "/api/accounts", code: 201)
operation CreateAccount {
    input: AccountCreate
    output: AccountResponse
}

@readonly
@http(method: "GET", uri: "/api/accounts/{accountId}")
operation GetAccount {
    input := {
        @required
        @httpLabel
        accountId: String
    }
    output: AccountResponse
}

@http(method: "PATCH", uri: "/api/accounts/{accountId}")
operation UpdateAccount {
    input := {
        @required
        @httpLabel
        accountId: String

        @httpPayload
        body: AccountUpdate
    }
    output: AccountResponse
}

/// Request body for creating an AWS account.
///
/// Email fields are plain strings: Smithy has no email trait, so `format: email`
/// cannot be expressed here. `backend/schemas/validators.py` re-applies EmailStr
/// to the generated models.
structure AccountCreate {
    @required
    @length(min: 1, max: 50)
    accountName: String

    @required
    @length(min: 3, max: 320)
    accountEmail: String

    @required
    @length(min: 1, max: 128)
    @pattern("^(ou-|r-)[a-z0-9-]+$")
    organizationalUnit: String

    @required
    @length(min: 3, max: 320)
    ssoUserEmail: String
}

/// Request body for updating an AWS account. Every field is optional; omitted
/// fields are left untouched.
structure AccountUpdate {
    @length(min: 1, max: 50)
    accountName: String

    @length(min: 1, max: 128)
    @pattern("^(ou-|r-)[a-z0-9-]+$")
    organizationalUnit: String

    @length(min: 3, max: 320)
    ssoUserEmail: String

    /// Empty string clears the alias; otherwise AWS requires 3-63 chars.
    @length(max: 63)
    @pattern("^$|^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$")
    alias: String

    /// Empty string or "none" clears the color.
    @pattern("^$|^(none|pink|purple|darkBlue|lightBlue|teal|green|yellow|orange|red)$")
    color: String
}

/// An AWS account registered with Groundwork.
structure AccountResponse {
    @required
    id: String

    awsAccountId: String

    @required
    accountName: String

    @required
    accountEmail: String

    @required
    organizationalUnit: String

    @required
    status: String

    awsStatus: String

    @required
    ssoUserEmail: String

    provisionedProductId: String
    oidcProviderArn: String

    @required
    createdBy: String

    errorMessage: String

    @required
    @timestampFormat("date-time")
    createdAt: Timestamp

    @required
    @timestampFormat("date-time")
    updatedAt: Timestamp

    alias: String
    color: String
}
