from fastapi import APIRouter, Response

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/login")
async def login() -> Response:
    return Response(status_code=501, content='{"detail":"Not implemented"}', media_type="application/json")


@router.get("/callback")
async def callback() -> Response:
    return Response(status_code=501, content='{"detail":"Not implemented"}', media_type="application/json")


@router.post("/logout")
async def logout() -> Response:
    return Response(status_code=501, content='{"detail":"Not implemented"}', media_type="application/json")


@router.get("/me")
async def me() -> Response:
    return Response(status_code=501, content='{"detail":"Not implemented"}', media_type="application/json")


@router.get("/status")
async def status() -> Response:
    return Response(status_code=501, content='{"detail":"Not implemented"}', media_type="application/json")
