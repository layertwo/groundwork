"""Simple in-memory rate limiter for auth endpoints."""

import time
from collections import defaultdict

from fastapi import Request

from backend.exceptions import GroundworkError

# {ip: [timestamp, ...]}
_buckets: dict[str, list[float]] = defaultdict(list)

RATE_LIMIT = 20  # requests per window
RATE_WINDOW = 60  # seconds


class RateLimitError(GroundworkError):
    def __init__(self):
        super().__init__("Too many requests", status_code=429)


def rate_limit(request: Request) -> None:
    ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    bucket = _buckets[ip]

    # Prune old entries
    cutoff = now - RATE_WINDOW
    _buckets[ip] = [ts for ts in bucket if ts > cutoff]
    bucket = _buckets[ip]

    if len(bucket) >= RATE_LIMIT:
        raise RateLimitError()

    bucket.append(now)
