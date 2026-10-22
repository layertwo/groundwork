"""Job request/response models, generated from ``smithy/models/jobs.smithy``."""

from backend.schemas.generated.models import (
    CreateJobRequestContent,
    CreateJobResponseContent,
    GetJobResponseContent,
    ListJobsResponseContent,
)

__all__ = [
    "JobCreate",
    "JobListResponse",
    "JobResponse",
    "CreateJobResponse",
]

JobCreate = CreateJobRequestContent
JobResponse = GetJobResponseContent
CreateJobResponse = CreateJobResponseContent
JobListResponse = ListJobsResponseContent
