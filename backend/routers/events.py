"""SSE endpoint for real-time event streaming to authenticated clients."""

import asyncio
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.responses import Response

from backend.database import async_session_factory
from backend.dependencies.auth import _load_validated_session
from backend.exceptions import UnauthorizedError
from backend.services.events import event_bus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["events"])

# Re-validate the session every ~5 minutes (20 heartbeats * 15s timeout)
_REAUTH_EVERY_N_HEARTBEATS = 20


@router.get("/events", response_model=None)
async def event_stream(request: Request) -> Response:
    """SSE endpoint — validates session then streams events."""
    # Authenticate with a short-lived DB session so we don't hold a connection
    # while streaming.
    async with async_session_factory() as db:
        try:
            await _load_validated_session(request, db)
        except UnauthorizedError:
            raise

    queue = event_bus.subscribe()
    if queue is None:
        return JSONResponse(
            status_code=503,
            content={"detail": "Too many concurrent event streams"},
        )

    async def generate():
        heartbeats_since_reauth = 0
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=15)
                    yield message
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
                    heartbeats_since_reauth += 1
                    if heartbeats_since_reauth >= _REAUTH_EVERY_N_HEARTBEATS:
                        heartbeats_since_reauth = 0
                        try:
                            async with async_session_factory() as db:
                                await _load_validated_session(request, db)
                        except UnauthorizedError:
                            break
        finally:
            event_bus.unsubscribe(queue)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
