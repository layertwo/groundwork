"""In-process event bus for SSE-based real-time UI updates."""

import asyncio
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


MAX_SUBSCRIBERS = 500


class EventBus:
    """Simple pub/sub using asyncio.Queue per subscriber.

    Event payloads must only contain entity IDs, never sensitive data,
    because all authenticated subscribers receive all events.
    """

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[str]] = set()

    def subscribe(self) -> asyncio.Queue[str] | None:
        """Add a subscriber. Returns None if the subscriber limit is reached."""
        if len(self._subscribers) >= MAX_SUBSCRIBERS:
            logger.warning("SSE subscriber limit reached (%d)", MAX_SUBSCRIBERS)
            return None
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=256)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[str]) -> None:
        self._subscribers.discard(queue)

    def publish(self, event_type: str, data: dict[str, Any]) -> None:
        message = f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
        for queue in self._subscribers:
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                logger.warning("Dropping SSE event for slow consumer")


event_bus = EventBus()


def emit_account_updated(account_id: str) -> None:
    event_bus.publish("account_updated", {"id": account_id})


def emit_role_updated(role_id: str, account_id: str) -> None:
    event_bus.publish("role_updated", {"id": role_id, "account_id": account_id})


def emit_job_updated(job_id: str, account_id: str | None = None) -> None:
    data: dict[str, Any] = {"id": job_id}
    if account_id is not None:
        data["account_id"] = account_id
    event_bus.publish("job_updated", data)


def emit_accounts_synced() -> None:
    event_bus.publish("accounts_synced", {})
