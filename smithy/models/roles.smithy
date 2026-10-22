$version: "2.0"

namespace layertwo.groundwork

// ============================================================================
// Role Resource
// ============================================================================
@documentation("An IAM role provisioned in a member account, assumable through Groundwork")
resource Role {
    identifiers: {
        roleId: String
    }
    create: CreateRole
    update: UpdateRole
    delete: DeleteRole
    list: ListRoles
    operations: [
        FixRoleDrift
    ]
}

// ============================================================================
// Role Operations
// ============================================================================
@http(method: "POST", uri: "/api/accounts/{accountId}/roles", code: 201)
operation CreateRole {
    input: CreateRoleInput
    output: CreateRoleOutput
}

@http(method: "PATCH", uri: "/api/accounts/{accountId}/roles/{roleId}")
operation UpdateRole {
    input: UpdateRoleInput
    output: UpdateRoleOutput
}

@idempotent
@http(method: "DELETE", uri: "/api/accounts/{accountId}/roles/{roleId}", code: 202)
operation DeleteRole {
    input: DeleteRoleInput
}

@readonly
@http(method: "GET", uri: "/api/roles")
operation ListRoles {
    output: ListRolesOutput
}

/// Re-apply the stored policy configuration to a role that drifted in AWS.
@http(method: "POST", uri: "/api/accounts/{accountId}/roles/{roleId}/fix-drift", code: 202)
operation FixRoleDrift {
    input: FixRoleDriftInput
}

// ============================================================================
// Role Shapes
// ============================================================================
structure CreateRoleInput {
    @required
    @httpLabel
    accountId: String

    @required
    @length(min: 1, max: 128)
    @pattern("^[a-zA-Z0-9_+=,.@-]+$")
    roleName: String

    templateId: String

    managedPolicyArns: ManagedPolicyArnList = []

    inlinePolicy: Document

    allowedGroups: TrustPrincipalList = []

    allowedUsers: TrustPrincipalList = []

    @range(min: 900, max: 43200)
    apiSessionDuration: Integer = 900

    @range(min: 900, max: 43200)
    consoleSessionDuration: Integer = 3600

    @length(max: 1000)
    description: String
}

structure UpdateRoleInput {
    @required
    @httpLabel
    accountId: String

    @required
    @httpLabel
    roleId: String

    managedPolicyArns: ManagedPolicyArnList

    inlinePolicy: Document

    allowedGroups: TrustPrincipalList

    allowedUsers: TrustPrincipalList

    @range(min: 900, max: 43200)
    apiSessionDuration: Integer

    @range(min: 900, max: 43200)
    consoleSessionDuration: Integer

    @length(max: 1000)
    description: String
}

structure DeleteRoleInput {
    @required
    @httpLabel
    accountId: String

    @required
    @httpLabel
    roleId: String
}

structure FixRoleDriftInput {
    @required
    @httpLabel
    accountId: String

    @required
    @httpLabel
    roleId: String
}

structure ListRolesOutput {
    @required
    roles: RoleList
}

list RoleList {
    member: RoleResponse
}

// ============================================================================
// Role Data
// ============================================================================
@mixin
structure RoleFields {
    @required
    id: String

    @required
    accountId: String

    @required
    roleName: String

    @required
    roleArn: String

    @required
    status: String

    errorMessage: String

    allowedGroups: TrustPrincipalList

    managedPolicyArns: ManagedPolicyArnList

    inlinePolicy: Document

    allowedUsers: TrustPrincipalList

    @required
    apiSessionDuration: Integer

    @required
    consoleSessionDuration: Integer

    description: String

    @required
    @timestampFormat("date-time")
    createdAt: Timestamp

    @required
    @timestampFormat("date-time")
    updatedAt: Timestamp

    @timestampFormat("date-time")
    lastUsedAt: Timestamp
}

structure CreateRoleOutput with [RoleFields] {}
structure UpdateRoleOutput with [RoleFields] {}
structure RoleResponse with [RoleFields] {}

// ============================================================================
// Shared Shapes
// ============================================================================
@pattern("^arn:aws:iam::[A-Za-z0-9]*:policy/[A-Za-z0-9+=,.@_/-]+$")
string ManagedPolicyArn

@length(max: 20)
list ManagedPolicyArnList {
    @pattern("^arn:aws:iam::[A-Za-z0-9]*:policy/[A-Za-z0-9+=,.@_/-]+$")
    member: String
}

@length(min: 1, max: 256)
string TrustPrincipal

@length(max: 50)
list TrustPrincipalList {
    @length(min: 1, max: 256)
    member: String
}
