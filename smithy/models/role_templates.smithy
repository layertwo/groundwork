$version: "2.0"

namespace layertwo.groundwork

// ============================================================================
// Role Template Resource
// ============================================================================
@documentation("Reusable set of managed policies applied when creating a role")
resource RoleTemplate {
    identifiers: {
        templateId: String
    }
    create: CreateRoleTemplate
    update: UpdateRoleTemplate
    delete: DeleteRoleTemplate
    list: ListRoleTemplates
}

// ============================================================================
// Role Template Operations
// ============================================================================
@http(method: "POST", uri: "/api/roles/templates", code: 201)
operation CreateRoleTemplate {
    input: CreateRoleTemplateInput
    output: CreateRoleTemplateOutput
}

@http(method: "PATCH", uri: "/api/roles/templates/{templateId}")
operation UpdateRoleTemplate {
    input: UpdateRoleTemplateInput
    output: UpdateRoleTemplateOutput
}

@idempotent
@http(method: "DELETE", uri: "/api/roles/templates/{templateId}", code: 204)
operation DeleteRoleTemplate {
    input: DeleteRoleTemplateInput
}

@readonly
@http(method: "GET", uri: "/api/roles/templates")
operation ListRoleTemplates {
    output: ListRoleTemplatesOutput
}

// ============================================================================
// Role Template Shapes
// ============================================================================
structure CreateRoleTemplateInput {
    @required
    @length(min: 1, max: 128)
    name: String

    @length(max: 1000)
    description: String

    managedPolicyArns: ManagedPolicyArnList = []
}

structure UpdateRoleTemplateInput {
    @required
    @httpLabel
    templateId: String

    @length(min: 1, max: 128)
    name: String

    @length(max: 1000)
    description: String

    managedPolicyArns: ManagedPolicyArnList
}

structure DeleteRoleTemplateInput {
    @required
    @httpLabel
    templateId: String
}

structure ListRoleTemplatesOutput {
    @required
    templates: RoleTemplateList
}

list RoleTemplateList {
    member: RoleTemplateResponse
}

@mixin
structure RoleTemplateFields {
    @required
    id: String

    @required
    name: String

    description: String

    managedPolicyArns: ManagedPolicyArnList

    @required
    @timestampFormat("date-time")
    createdAt: Timestamp

    @required
    @timestampFormat("date-time")
    updatedAt: Timestamp
}

structure CreateRoleTemplateOutput with [RoleTemplateFields] {}
structure UpdateRoleTemplateOutput with [RoleTemplateFields] {}
structure RoleTemplateResponse with [RoleTemplateFields] {}
