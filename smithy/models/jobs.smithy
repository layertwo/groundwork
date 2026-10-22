$version: "2.0"

namespace layertwo.groundwork

// ============================================================================
// Job Resource
// ============================================================================
@documentation("A background job (account provisioning, org sync, role operations)")
resource Job {
    identifiers: {
        id: String
    }
    create: CreateJob
    read: GetJob
    list: ListJobs
}

// ============================================================================
// Job Operations
// ============================================================================
@http(method: "POST", uri: "/api/jobs", code: 201)
operation CreateJob {
    input: CreateJobInput
    output: CreateJobOutput
}

@readonly
@http(method: "GET", uri: "/api/jobs/{id}")
operation GetJob {
    input: GetJobInput
    output: GetJobOutput
}

@readonly
@http(method: "GET", uri: "/api/jobs")
operation ListJobs {
    input: ListJobsInput
    output: ListJobsOutput
}

// ============================================================================
// Job Shapes
// ============================================================================
structure CreateJobInput {
    @required
    @length(min: 1, max: 64)
    @pattern("^[a-z][a-z0-9_]*$")
    jobType: String
}

structure GetJobInput {
    @required
    @httpLabel
    id: String
}

structure ListJobsInput {
    @httpQuery("accountId")
    accountId: String

    @httpQuery("status")
    status: String

    @httpQuery("jobType")
    jobType: String
}

structure ListJobsOutput {
    @required
    jobs: JobList
}

list JobList {
    member: JobResponse
}

// ============================================================================
// Job Data
// ============================================================================
@mixin
structure JobFields {
    @required
    id: String

    accountId: String

    @required
    jobType: String

    @required
    status: String

    @required
    startedBy: String

    @timestampFormat("date-time")
    startedAt: Timestamp

    @timestampFormat("date-time")
    completedAt: Timestamp

    result: Document

    errorMessage: String

    @required
    @timestampFormat("date-time")
    createdAt: Timestamp

    @timestampFormat("date-time")
    scheduledAfter: Timestamp
}

structure CreateJobOutput with [JobFields] {}
structure GetJobOutput with [JobFields] {}
structure JobResponse with [JobFields] {}
