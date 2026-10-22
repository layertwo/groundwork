$version: "2.0"

namespace layertwo.groundwork

// ============================================================================
// Account Resource
// ============================================================================
@documentation("An AWS account registered with Groundwork")
resource Account {
    identifiers: {
        id: String
    }
    create: CreateAccount
    read: GetAccount
    update: UpdateAccount
    list: ListAccounts
}

// ============================================================================
// Account Operations
// ============================================================================
@http(method: "POST", uri: "/api/accounts", code: 201)
operation CreateAccount {
    input: CreateAccountInput
    output: CreateAccountOutput
}

@readonly
@http(method: "GET", uri: "/api/accounts/{id}")
operation GetAccount {
    input: GetAccountInput
    output: GetAccountOutput
}

@http(method: "PATCH", uri: "/api/accounts/{id}")
operation UpdateAccount {
    input: UpdateAccountInput
    output: UpdateAccountOutput
}

@readonly
@http(method: "GET", uri: "/api/accounts")
operation ListAccounts {
    output: ListAccountsOutput
}

// ============================================================================
// Account Shapes
// ============================================================================
/// Request body for creating an AWS account.
///
/// Email fields are plain strings: Smithy has no email trait, so `format: email`
/// cannot be expressed here. `backend/schemas/account.py` re-applies EmailStr
/// to the generated model.
structure CreateAccountInput {
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

structure GetAccountInput {
    @required
    @httpLabel
    id: String
}

/// Request body for updating an AWS account. Omitted fields are left untouched.
structure UpdateAccountInput {
    @required
    @httpLabel
    id: String

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

structure ListAccountsOutput {
    @required
    accounts: AccountList
}

list AccountList {
    member: AccountResponse
}

// ============================================================================
// Account Data
// ============================================================================
/// Fields returned for a single account.
@mixin
structure AccountFields {
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

structure CreateAccountOutput with [AccountFields] {}
structure GetAccountOutput with [AccountFields] {}
structure UpdateAccountOutput with [AccountFields] {}
structure AccountResponse with [AccountFields] {}
