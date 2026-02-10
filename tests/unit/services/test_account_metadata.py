"""Tests for the account metadata cache."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from backend.services import account_metadata


class TestGetAccountMetadata:
    async def test_fetches_from_aws_on_cache_miss(self):
        account_metadata._cache.clear()

        with (
            patch.object(
                account_metadata,
                "_fetch_metadata",
                new_callable=AsyncMock,
                return_value={"alias": "prod", "color": "red"},
            ) as mock_fetch,
        ):
            result = await account_metadata.get_account_metadata("123456789012")

        assert result["alias"] == "prod"
        assert result["color"] == "red"
        mock_fetch.assert_called_once_with("123456789012")

    async def test_returns_cached_entry_when_fresh(self):
        account_metadata._cache["123456789012"] = {
            "alias": "prod",
            "color": "red",
            "fetched_at": datetime.now(timezone.utc),
        }

        with patch.object(
            account_metadata,
            "_fetch_metadata",
            new_callable=AsyncMock,
        ) as mock_fetch:
            result = await account_metadata.get_account_metadata("123456789012")

        assert result["alias"] == "prod"
        mock_fetch.assert_not_called()
        account_metadata._cache.clear()

    async def test_refetches_when_stale(self):
        account_metadata._cache["123456789012"] = {
            "alias": "old",
            "color": None,
            "fetched_at": datetime.now(timezone.utc) - timedelta(minutes=20),
        }

        with patch.object(
            account_metadata,
            "_fetch_metadata",
            new_callable=AsyncMock,
            return_value={"alias": "new", "color": "green"},
        ) as mock_fetch:
            result = await account_metadata.get_account_metadata("123456789012")

        assert result["alias"] == "new"
        assert result["color"] == "green"
        mock_fetch.assert_called_once()
        account_metadata._cache.clear()


class TestGetAllAccountMetadata:
    async def test_fetches_all_concurrently(self):
        account_metadata._cache.clear()
        ids = ["111111111111", "222222222222"]

        async def fake_fetch(account_id):
            return {"alias": f"alias-{account_id[-1]}", "color": None}

        with patch.object(
            account_metadata,
            "_fetch_metadata",
            side_effect=fake_fetch,
        ):
            result = await account_metadata.get_all_account_metadata(ids)

        assert result["111111111111"]["alias"] == "alias-1"
        assert result["222222222222"]["alias"] == "alias-2"
        account_metadata._cache.clear()


class TestWriteThrough:
    async def test_update_alias_updates_cache(self):
        account_metadata._cache["123456789012"] = {
            "alias": "old",
            "color": "red",
            "fetched_at": datetime.now(timezone.utc),
        }

        account_metadata.update_cached_alias("123456789012", "new")

        assert account_metadata._cache["123456789012"]["alias"] == "new"
        account_metadata._cache.clear()

    async def test_update_color_updates_cache(self):
        account_metadata._cache["123456789012"] = {
            "alias": "prod",
            "color": "red",
            "fetched_at": datetime.now(timezone.utc),
        }

        account_metadata.update_cached_color("123456789012", "green")

        assert account_metadata._cache["123456789012"]["color"] == "green"
        account_metadata._cache.clear()

    async def test_update_creates_entry_if_missing(self):
        account_metadata._cache.clear()

        account_metadata.update_cached_alias("123456789012", "new")

        assert account_metadata._cache["123456789012"]["alias"] == "new"
        assert account_metadata._cache["123456789012"]["color"] is None
        account_metadata._cache.clear()
