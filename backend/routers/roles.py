from fastapi import APIRouter, Response

router = APIRouter(prefix="/api/roles", tags=["roles"])


@router.get("")
async def list_roles() -> Response:
    return Response(status_code=501, content='{"detail":"Not implemented"}', media_type="application/json")


@router.post("/assume")
async def assume_role() -> Response:
    return Response(status_code=501, content='{"detail":"Not implemented"}', media_type="application/json")
