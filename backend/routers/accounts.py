from fastapi import APIRouter, Response

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


@router.get("")
async def list_accounts() -> Response:
    return Response(status_code=501, content='{"detail":"Not implemented"}', media_type="application/json")


@router.post("")
async def create_account() -> Response:
    return Response(status_code=501, content='{"detail":"Not implemented"}', media_type="application/json")


@router.get("/{account_id}")
async def get_account(account_id: str) -> Response:
    return Response(status_code=501, content='{"detail":"Not implemented"}', media_type="application/json")


@router.patch("/{account_id}")
async def update_account(account_id: str) -> Response:
    return Response(status_code=501, content='{"detail":"Not implemented"}', media_type="application/json")
