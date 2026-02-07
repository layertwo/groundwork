from fastapi import APIRouter, Response

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("")
async def list_jobs() -> Response:
    return Response(status_code=501, content='{"detail":"Not implemented"}', media_type="application/json")


@router.get("/{job_id}")
async def get_job(job_id: str) -> Response:
    return Response(status_code=501, content='{"detail":"Not implemented"}', media_type="application/json")
