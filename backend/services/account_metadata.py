"""In-memory TTL cache for account alias and color metadata.

These values are fetched from AWS (IAM for alias, UXC for color) and
cached to avoid per-request API calls. Cache TTL is 15 minutes.
Write-through updates are applied when changes are made via Groundwork.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

CACHE_TTL = timedelta(minutes=15)

# Keyed by AWS account ID → {"alias": str|None, "color": str|None, "fetched_at": datetime}
_cache: dict[str, dict] = {}


async def _fetch_metadata(aws_account_id: str) -> dict:
    """Fetch alias and color from AWS for a single account."""
    from backend.services.aws import get_account_alias, get_account_color

    alias, color = await asyncio.gather(
        get_account_alias(aws_account_id),
        get_account_color(aws_account_id),
        return_exceptions=True,
    )

    if isinstance(alias, Exception):
        logger.warning("Failed to fetch alias for account %s: %s", aws_account_id, alias)
        alias = None
    if isinstance(color, Exception):
        logger.warning("Failed to fetch color for account %s: %s", aws_account_id, color)
        color = None

    return {"alias": alias, "color": color}


def _is_fresh(entry: dict) -> bool:
    """Check if a cache entry is within the TTL."""
    return datetime.now(timezone.utc) - entry["fetched_at"] < CACHE_TTL


async def get_account_metadata(aws_account_id: str) -> dict:
    """Get alias and color for a single account, using cache when fresh."""
    entry = _cache.get(aws_account_id)
    if entry and _is_fresh(entry):
        return entry

    data = await _fetch_metadata(aws_account_id)
    entry = {**data, "fetched_at": datetime.now(timezone.utc)}
    _cache[aws_account_id] = entry
    return entry


async def get_all_account_metadata(aws_account_ids: list[str]) -> dict[str, dict]:
    """Get alias and color for multiple accounts concurrently.

    Returns a dict keyed by AWS account ID.
    """
    stale_ids = []
    result: dict[str, dict] = {}

    for account_id in aws_account_ids:
        entry = _cache.get(account_id)
        if entry and _is_fresh(entry):
            result[account_id] = entry
        else:
            stale_ids.append(account_id)

    if stale_ids:
        fetched = await asyncio.gather(
            *[_fetch_metadata(aid) for aid in stale_ids],
            return_exceptions=True,
        )
        now = datetime.now(timezone.utc)
        for account_id, data in zip(stale_ids, fetched):
            if isinstance(data, Exception):
                logger.warning("Failed to fetch metadata for account %s: %s", account_id, data)
                data = {"alias": None, "color": None}
            entry = {**data, "fetched_at": now}
            _cache[account_id] = entry
            result[account_id] = entry

    return result


def update_cached_alias(aws_account_id: str, alias: str | None) -> None:
    """Write-through update for alias."""
    entry = _cache.get(aws_account_id)
    if entry:
        entry["alias"] = alias
        entry["fetched_at"] = datetime.now(timezone.utc)
    else:
        _cache[aws_account_id] = {
            "alias": alias,
            "color": None,
            "fetched_at": datetime.now(timezone.utc),
        }


def update_cached_color(aws_account_id: str, color: str | None) -> None:
    """Write-through update for color."""
    entry = _cache.get(aws_account_id)
    if entry:
        entry["color"] = color
        entry["fetched_at"] = datetime.now(timezone.utc)
    else:
        _cache[aws_account_id] = {
            "alias": None,
            "color": color,
            "fetched_at": datetime.now(timezone.utc),
        }
