from fastapi import APIRouter, Response

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("")
async def list_audit_logs() -> Response:
    return Response(status_code=501, content='{"detail":"Not implemented"}', media_type="application/json")
