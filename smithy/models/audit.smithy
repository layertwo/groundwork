$version: "2.0"

namespace layertwo.groundwork

// ============================================================================
// Audit Entry Resource
// ============================================================================
@documentation("An append-only record of who did what, when")
resource AuditEntry {
    identifiers: {
        id: String
    }
    list: ListAuditEntries
}

// ============================================================================
// Audit Operations
// ============================================================================
@readonly
@http(method: "GET", uri: "/api/audit")
operation ListAuditEntries {
    input: ListAuditEntriesInput
    output: ListAuditEntriesOutput
}

// ============================================================================
// Audit Shapes
// ============================================================================
structure ListAuditEntriesInput {
    @httpQuery("resourceType")
    resourceType: String

    @httpQuery("resourceId")
    resourceId: String

    @httpQuery("userId")
    userId: String

    @httpQuery("action")
    action: String

    @httpQuery("page")
    @range(min: 1, max: 1000000)
    page: Integer = 1

    @httpQuery("pageSize")
    @range(min: 1, max: 200)
    pageSize: Integer = 50
}

structure ListAuditEntriesOutput {
    @required
    items: AuditEntryList

    @required
    total: Long

    @required
    page: Integer

    @required
    pageSize: Integer
}

list AuditEntryList {
    member: AuditEntryResponse
}

@mixin
structure AuditEntryFields {
    @required
    id: Long

    userId: String

    @required
    action: String

    resourceType: String
    resourceId: String

    detail: Document

    ipAddress: String
    userAgent: String

    @required
    @timestampFormat("date-time")
    createdAt: Timestamp
}

structure AuditEntryResponse with [AuditEntryFields] {
    user: AuditUser
}

structure AuditUser {
    @required
    id: String

    @required
    displayName: String
}
