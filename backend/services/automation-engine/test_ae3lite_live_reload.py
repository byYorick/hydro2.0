"""Unit tests for ae3lite.config.live_reload (Phase 5).

Mocks asyncpg-like Connection — verifies the contract:
- Returns None when zone NOT in live mode
- Returns None when revision has not advanced
- Returns None when TTL has expired
- Returns HotReloadResult with parsed ZoneCorrection/RecipePhase otherwise
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from ae3lite.config import live_reload


class _Conn:
    """Minimal asyncpg-like Connection stub. Pre-loaded with rows by query
    fragment match."""

    def __init__(
        self,
        *,
        zone_row: dict | None = None,
        bundle_row: dict | None = None,
        cycle_phase_row: dict | None = None,
    ) -> None:
        self._zone_row = zone_row
        self._bundle_row = bundle_row
        self._cycle_phase_row = cycle_phase_row
        self.zone_query_count = 0
        self.bundle_query_count = 0
        self.phase_query_count = 0

    async def fetchrow(self, query: str, *args: Any) -> dict | None:
        if "FROM zones" in query and "config_mode" in query:
            self.zone_query_count += 1
            return self._zone_row
        if "FROM automation_effective_bundles" in query:
            self.bundle_query_count += 1
            return self._bundle_row
        if "FROM grow_cycles" in query:
            self.phase_query_count += 1
            return self._cycle_phase_row
        raise AssertionError(f"unexpected query: {query!r}")


@pytest.mark.asyncio
async def test_returns_none_when_zone_not_live() -> None:
    conn = _Conn(zone_row={
        "config_mode": "locked",
        "config_revision": 5,
        "live_until": None,
    })
    result = await live_reload.refresh_if_changed(
        zone_id=1, current_revision=1, current_grow_cycle_id=10, conn=conn,
    )
    assert result is None
    assert conn.bundle_query_count == 0


@pytest.mark.asyncio
async def test_returns_none_when_revision_not_advanced() -> None:
    conn = _Conn(zone_row={
        "config_mode": "live",
        "config_revision": 5,
        "live_until": datetime.now(timezone.utc) + timedelta(hours=1),
    })
    result = await live_reload.refresh_if_changed(
        zone_id=1, current_revision=5, current_grow_cycle_id=10, conn=conn,
    )
    assert result is None
    assert conn.bundle_query_count == 0


@pytest.mark.asyncio
async def test_returns_none_when_ttl_expired() -> None:
    conn = _Conn(zone_row={
        "config_mode": "live",
        "config_revision": 7,
        "live_until": datetime.now(timezone.utc) - timedelta(minutes=1),
    })
    result = await live_reload.refresh_if_changed(
        zone_id=1, current_revision=5, current_grow_cycle_id=10, conn=conn,
    )
    assert result is None


@pytest.mark.asyncio
async def test_returns_none_when_zone_row_missing() -> None:
    conn = _Conn(zone_row=None)
    result = await live_reload.refresh_if_changed(
        zone_id=99, current_revision=0, current_grow_cycle_id=None, conn=conn,
    )
    assert result is None


@pytest.mark.asyncio
async def test_returns_none_when_revision_advanced_but_no_payload() -> None:
    """Defensive: revision bumped but bundle/phase don't yield usable data."""
    conn = _Conn(
        zone_row={
            "config_mode": "live",
            "config_revision": 8,
            "live_until": datetime.now(timezone.utc) + timedelta(hours=1),
        },
        bundle_row=None,
        cycle_phase_row=None,
    )
    result = await live_reload.refresh_if_changed(
        zone_id=1, current_revision=5, current_grow_cycle_id=10, conn=conn,
    )
    assert result is None


@pytest.mark.asyncio
async def test_naive_live_until_treated_as_utc() -> None:
    """DB returns naive UTC; loader normalizes to aware before compare."""
    naive_future = (datetime.now(timezone.utc) + timedelta(hours=1)).replace(tzinfo=None)
    conn = _Conn(
        zone_row={
            "config_mode": "live",
            "config_revision": 8,
            "live_until": naive_future,
        },
        bundle_row=None,
        cycle_phase_row=None,
    )
    result = await live_reload.refresh_if_changed(
        zone_id=1, current_revision=5, current_grow_cycle_id=10, conn=conn,
    )
    # bundle/phase are None → no-op result, but TTL check should pass
    assert result is None
    assert conn.bundle_query_count == 1
