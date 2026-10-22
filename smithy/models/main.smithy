$version: "2.0"

namespace layertwo.groundwork

use aws.protocols#restJson1

/// Groundwork control plane: provisions and manages AWS accounts and IAM roles.
///
/// Resources own their lifecycle operations; extra non-CRUD operations are
/// listed on the resource. New resources are added here as routes migrate.
@restJson1
@title("Groundwork API")
service Groundwork {
    version: "2026-10-21"
    operations: []
    resources: [
        Account
        Job
        Role
        RoleTemplate
        AuditEntry
    ]
}
